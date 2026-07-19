"""JOB-QUEUE — a durable background-job queue for the heavy operations (then-bucket item).

Heavy work (full-model COBie export, bundle generation, PAdES signing, generative runs) ran inline in
the request thread — a big model meant a long-hanging HTTP call and a lost result on restart. This is
the smallest durable queue that fixes that with **no new dependencies**:

  · jobs persist as `Job` rows (queued → running → done | error), so a restart loses nothing;
  · one daemon worker per process claims the oldest queued job, runs its registered handler with its
    own DB session, and stores the result/error on the row;
  · **crash recovery**: on worker start, any job still marked `running` (orphaned by a crash) is reset
    to `queued` and runs again — handlers must therefore be idempotent, which every registered kind is
    (they re-derive from the model/records, they don't increment anything);
  · handlers come from a small registry (`register_kind`) — the same shape as the edit-recipe registry,
    so a plugin or a new engine adds a kind in one line.

Cross-worker note: like `pid_lock`, the in-process claim is safe for the supported single-writer
deployment; multi-worker deployments would add a DB row-lock claim (`SELECT … FOR UPDATE SKIP LOCKED`)
— the schema already supports it."""
from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Job
from .timeutil import utc_now

log = logging.getLogger(__name__)

KINDS: dict[str, Callable[[Session, dict], Any]] = {}
_WAKE = threading.Event()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LOCK = threading.Lock()


def register_kind(name: str, fn: Callable[[Session, dict], Any]) -> None:
    """Register a job handler: `fn(db, params) -> JSON-serializable result`. Handlers MUST be
    idempotent (crash recovery re-runs an orphaned job)."""
    KINDS[name] = fn


def enqueue(db: Session, kind: str, project_id: str | None, params: dict | None,
            actor: str | None = None) -> Job:
    """Queue a job. Raises ValueError on an unregistered kind (a typo should fail at submit, not sit
    forever as an un-runnable row)."""
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind!r}; registered: {sorted(KINDS)}")
    j = Job(kind=kind, project_id=project_id, params=params or {}, actor=actor, state="queued")
    db.add(j)
    db.commit()
    db.refresh(j)
    _WAKE.set()                                     # nudge the worker without waiting the poll interval
    return j


def job_dict(j: Job) -> dict[str, Any]:
    return {"id": j.id, "kind": j.kind, "project_id": j.project_id, "state": j.state,
            "params": j.params, "result": j.result, "error": j.error, "actor": j.actor,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


def _claim_next(db: Session) -> Job | None:
    j = db.scalars(select(Job).where(Job.state == "queued").order_by(Job.created_at).limit(1)).first()
    if j is None:
        return None
    j.state = "running"
    j.started_at = utc_now()
    db.commit()
    return j


def _run_one(SessionLocal) -> bool:
    """Claim + run one job. Returns False when the queue is empty."""
    db = SessionLocal()
    try:
        j = _claim_next(db)
        if j is None:
            return False
        fn = KINDS.get(j.kind)
        try:
            if fn is None:                           # kind vanished across a restart (plugin removed)
                raise ValueError(f"job kind {j.kind!r} is no longer registered")
            result = fn(db, j.params or {})
            j.result = result if isinstance(result, (dict, list)) else {"value": result}
            j.state = "done"
        except Exception as e:  # noqa: BLE001 — the job row carries the failure; the worker never dies
            j.state = "error"
            j.error = f"{e.__class__.__name__}: {e}"
            log.warning("job %s (%s) failed: %s\n%s", j.id, j.kind, e, traceback.format_exc())
        j.finished_at = utc_now()
        db.commit()
        return True
    finally:
        db.close()


def _worker(SessionLocal) -> None:
    while not _STOP.is_set():
        try:
            while _run_one(SessionLocal):
                pass                                  # drain the queue
        except Exception:  # noqa: BLE001 — a claim-layer failure must not kill the worker thread
            log.exception("job worker: claim cycle failed; continuing")
        _WAKE.wait(timeout=2.0)                       # poll floor; enqueue() wakes us sooner
        _WAKE.clear()


def start_worker() -> None:
    """Start the per-process worker (idempotent) and recover orphans: any job left `running` by a
    crashed process is re-queued — handlers are idempotent by contract, so a re-run is safe."""
    global _THREAD
    from .db import SessionLocal
    with _LOCK:
        db = SessionLocal()
        try:
            orphans = list(db.scalars(select(Job).where(Job.state == "running")))
            for j in orphans:
                j.state = "queued"
                j.started_at = None
            if orphans:
                db.commit()
                log.warning("job queue: re-queued %d orphaned running job(s) from a previous process",
                            len(orphans))
        finally:
            db.close()
        if _THREAD is not None and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_worker, args=(SessionLocal,), daemon=True,
                                   name="aec-job-worker")
        _THREAD.start()


def stop_worker() -> None:
    _STOP.set()
    _WAKE.set()


# --- built-in kinds -------------------------------------------------------------------------------
def _cobie_export(db: Session, params: dict) -> dict:
    """Full-model COBie handover export — the canonical heavy parse that used to run inline. Stores
    the per-sheet row counts (the deliverable itself is regenerated on download; this proves the model
    exports cleanly and how big the handover set is)."""
    from aec_data import cobie  # type: ignore

    from .models import Project
    p = db.get(Project, params.get("project_id") or "")
    if not p or not p.source_ifc:
        raise ValueError("project has no source IFC")
    sheets = cobie.cobie_file(p.source_ifc)
    return {"sheets": {k: len(v) for k, v in sheets.items()},
            "total_rows": sum(len(v) for v in sheets.values())}


def _compiled_set_pdf(db: Session, params: dict) -> dict:
    """JOB-QUEUE migration of the heaviest inline path: compile the WHOLE drawing set into one
    multi-page PDF (cover + a plan per storey + schedules) off the request thread. The PDF parks in
    object storage; the poll result carries `artifact_key` and `GET /jobs/{id}/artifact` streams it.
    Params: {project_id, scale?, max_sheets?, schedules?} (same knobs as the inline endpoint).
    Idempotent: a re-run just writes a fresh artifact."""
    import uuid
    from pathlib import Path

    from . import drawingset, storage
    from .models import Project
    p = db.get(Project, params.get("project_id") or "")
    if not p:
        raise ValueError("project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise ValueError("project has no source IFC — the compiled set renders from the model")
    pdf = drawingset.compiled_set_pdf(p.source_ifc, p.name or p.id,
                                      scale=int(params.get("scale") or 200),
                                      max_sheets=int(params.get("max_sheets") or 16),
                                      include_schedules=bool(params.get("schedules", True)))
    key = f"{p.id}/jobs/{uuid.uuid4().hex}-drawing-set.pdf"
    storage.put(key, pdf)
    return {"artifact_key": key, "media_type": "application/pdf",
            "filename": f"{(p.name or p.id)}-drawing-set.pdf", "bytes": len(pdf)}


def _model_export(db: Session, params: dict) -> dict:
    """JOB-QUEUE: the heavy **geometry exports** (.glb / .gltf) as artifact jobs — a large model's
    tessellation runs off the request thread and the file parks in object storage
    (`GET /jobs/{id}/artifact` streams it). The inline `/model/export.glb|.gltf` routes stay for
    small models; this is the no-timeout path for big ones. Params: {project_id, format: glb|gltf}."""
    import uuid
    from pathlib import Path

    from aec_data import gltf_export  # type: ignore

    from . import storage
    from .models import Project
    p = db.get(Project, params.get("project_id") or "")
    if not p:
        raise ValueError("project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise ValueError("project has no source IFC to export")
    fmt = str(params.get("format") or "glb").lower()
    if fmt == "glb":
        data = gltf_export.export_glb_bytes(p.source_ifc, p.name or p.id)
        media, ext = "model/gltf-binary", "glb"
    elif fmt == "gltf":
        data = gltf_export.export_gltf_bytes(p.source_ifc, p.name or p.id)
        media, ext = "model/gltf+json", "gltf"
    else:
        raise ValueError(f"unknown export format {fmt!r} — glb or gltf")
    key = f"{p.id}/jobs/{uuid.uuid4().hex}-model.{ext}"
    storage.put(key, data if isinstance(data, bytes) else data.encode())
    return {"artifact_key": key, "media_type": media,
            "filename": f"model-{p.id}.{ext}", "bytes": len(data)}


def _clash_detect(db: Session, params: dict) -> dict:
    """PERF-3 (CLASH-JOBS): the narrow-phase clash off the request path for large models. Same engine
    as `POST /projects/{pid}/clash`, but the (potentially minutes-long, mesh-boolean) run happens on
    the durable worker so it never holds a request slot or hits the HTTP timeout. Params:
    {project_id, a, b (comma class lists), min_volume?, tolerance?, narrow?, max_narrow?, limit?}.
    Returns the clash summary + the top rows (topic creation stays on the interactive route)."""
    from aec_data import clash  # type: ignore

    from .models import Project
    p = db.get(Project, params.get("project_id") or "")
    if not p or not p.source_ifc:
        raise ValueError("project has no source IFC")

    def _classes(s: str | None) -> list[str]:
        return [c.strip() for c in (s or "").split(",") if c.strip()]

    limit = int(params.get("limit") or 200)
    results = clash.detect_file(
        p.source_ifc, _classes(params.get("a")), _classes(params.get("b")),
        float(params.get("min_volume") or 1e-3), float(params.get("tolerance") or 0.0),
        narrow=bool(params.get("narrow", True)), max_narrow=int(params.get("max_narrow") or 200))
    return {"count": len(results), "clashes": results[:limit],
            "truncated": len(results) > limit}


def _echo(db: Session, params: dict) -> dict:
    """Test/diagnostic kind: returns its params (and proves the queue round-trips)."""
    return {"echo": params}


register_kind("echo", _echo)
register_kind("cobie_export", _cobie_export)
register_kind("compiled_set_pdf", _compiled_set_pdf)
register_kind("model_export", _model_export)
register_kind("clash_detect", _clash_detect)
