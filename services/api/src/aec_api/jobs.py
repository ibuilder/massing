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

## Running the worker somewhere other than the API process (JOB-WORKER-SPLIT)

**The note that used to sit here was stale and said the opposite of the truth.** It read: "like
`pid_lock`, the in-process claim is safe for the supported single-writer deployment; multi-worker
deployments would add a DB row-lock claim". Both halves stopped being true:

  · `_claim_next` is a **CAS** (`UPDATE … WHERE id = :id AND state = 'queued'`), which is already
    safe across processes and hosts — no `FOR UPDATE SKIP LOCKED` needed, and deliberately not used,
    since `FOR UPDATE` is a silent no-op on SQLite;
  · `pid_lock` became **cross-process** in R35-PIDLOCK-XPROC (a Postgres session advisory lock), so
    per-project serialisation no longer depends on there being one process.

A comment that talks the reader out of the thing the code already supports is worse than no comment:
this one would have stopped someone from scaling the queue out, which is the *entire* reason the CAS
and the advisory lock were written. Hence `AEC_JOB_WORKER`:

  · `inline` (**default**) — the API process runs the worker thread, as it always has. Nothing about
    an existing single-container deployment changes.
  · `off` — the API serves requests only. A dedicated worker process (`python -m aec_api.worker`)
    must be running, or **jobs queue forever and nothing raises**. That silence is the whole risk of
    this split, so it is defended twice: `main.py` logs a warning naming the required process at
    boot, and `test_worker_split.py` fails the build if a compose file sets `off` without also
    defining a service that runs the worker.

Splitting matters because the heavy kinds here (full-model COBie, bundle generation, generative runs)
are CPU- and memory-bound IFC parses. Inline, one large reconvert degrades every HTTP request sharing
that container. Split, conversion throughput scales by adding worker containers and does not touch
the latency of the API at all."""
from __future__ import annotations

import logging
import os
import threading
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_ as sa_and
from sqlalchemy import or_ as sa_or
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from .models import Job
from .timeutil import utc_now

log = logging.getLogger(__name__)

KINDS: dict[str, Callable[[Session, dict], Any]] = {}
# kinds that WRITE project state (records / republished model) rather than only reading + parking an
# artifact. Their handler runs under `pid_lock.mutating(project_id)` so a queued mutating job can't
# interleave with a concurrent API edit (which takes the same lock) or another mutating job on the
# same project — the read-modify-write race pid_lock already guards for docmanager/edit_history.
_MUTATING_KINDS: set[str] = set()
_WAKE = threading.Event()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LOCK = threading.Lock()


def register_kind(name: str, fn: Callable[[Session, dict], Any], *, mutating: bool = False) -> None:
    """Register a job handler: `fn(db, params) -> JSON-serializable result`. Handlers MUST be
    idempotent (crash recovery re-runs an orphaned job). Set `mutating=True` for a handler that writes
    project state — the worker then runs it under the project's mutation lock (needs `project_id`)."""
    KINDS[name] = fn
    if mutating:
        _MUTATING_KINDS.add(name)
    else:
        _MUTATING_KINDS.discard(name)


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
    """Claim the oldest queued job — by COMPARE-AND-SWAP, not by read-then-write.

    The original read the oldest queued row, set `state = "running"` on the ORM object and
    committed. Correct with one worker; with two processes sharing the database (uvicorn
    `--workers`, or two dev servers on one preview.db) both could SELECT the same row and both
    commit `running`, and the job body then executed **twice concurrently**. "Handlers are
    idempotent" is the contract for a crash-recovery RE-RUN — it says nothing about two copies
    interleaving at the same time, which for a mutating job means two writers inside the same
    project serialised only by `pid_lock`, which is in-process and cannot see the other worker.

    The CAS closes it portably: `UPDATE … WHERE id = :id AND state = 'queued'` matches exactly one
    row across all workers combined — whoever matched rowcount 1 owns the job; a loser saw
    rowcount 0, and LOOPS to try the next queued job rather than going to sleep, because "I lost
    the race for job A" does not mean "the queue is empty".
    """
    while True:
        j = db.scalars(select(Job).where(Job.state == "queued")
                       .order_by(Job.created_at).limit(1)).first()
        if j is None:
            return None
        won = db.execute(
            sa_update(Job).where(Job.id == j.id, Job.state == "queued")
            # JOB-WORKER-SCALE: stamp the heartbeat in the SAME statement that wins the row. Setting
            # it afterwards would leave a window in which the job is `running` with no sign of life,
            # and a sibling worker booting inside that window would read it as an orphan and re-queue
            # a job this process is about to start.
            .values(state="running", started_at=utc_now(), heartbeat_at=utc_now())
        ).rowcount
        db.commit()
        if won:
            db.refresh(j)
            return j
        db.expire_all()          # the loser's snapshot of j is stale; drop it before re-selecting


#: How often a running job re-stamps `heartbeat_at`, and how long a silence means "orphan".
#:
#: The stale window is deliberately several intervals wide. It is the only thing standing between a
#: momentarily slow database and a live job being handed to a second worker, and re-queueing a job
#: that is genuinely running is the expensive mistake here — the cheap one is leaving a truly dead
#: job queued for a few minutes longer.
_HEARTBEAT_SECONDS = float(os.environ.get("AEC_JOB_HEARTBEAT_SECONDS", "20"))
_STALE_AFTER_SECONDS = float(os.environ.get("AEC_JOB_ORPHAN_AFTER_SECONDS",
                                            str(max(120.0, _HEARTBEAT_SECONDS * 6))))


class _Heartbeat:
    """Keeps one running job's `heartbeat_at` current for as long as its handler is executing.

    A separate thread and a separate SESSION, both on purpose. The handler owns `db` for the whole of
    a long IFC parse and may be inside a transaction; writing the heartbeat on that session would
    either block behind it or interleave with the handler's own writes. And it must be a thread
    rather than a between-steps call because the handlers this exists for are single blocking calls
    lasting minutes — there is no "between steps" to hook.
    """

    def __init__(self, SessionLocal, job_id: str):
        self._SessionLocal, self._job_id = SessionLocal, job_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> _Heartbeat:
        self._thread = threading.Thread(target=self._beat, daemon=True,
                                        name=f"aec-job-heartbeat-{self._job_id[:8]}")
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _beat(self) -> None:
        while not self._stop.wait(_HEARTBEAT_SECONDS):
            try:
                with self._SessionLocal() as hb:
                    # Scoped to `running`: once the job finishes, this must not resurrect a heartbeat
                    # on a done/error row, which would make a finished job look alive to `queue_stats`.
                    hb.execute(sa_update(Job)
                               .where(Job.id == self._job_id, Job.state == "running")
                               .values(heartbeat_at=utc_now()))
                    hb.commit()
            except Exception:  # noqa: BLE001 — a missed beat must never kill the job it is watching
                log.debug("job %s: heartbeat failed", self._job_id, exc_info=True)


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
            # JOB-WORKER-SCALE: hold the claim alive for the whole handler. Without this a job that
            # runs longer than the stale window is re-queued by the next worker to boot and then runs
            # twice — and the jobs this queue exists for are precisely the long ones.
            with _Heartbeat(SessionLocal, j.id):
                if j.kind in _MUTATING_KINDS and j.project_id:
                    from . import pid_lock
                    with pid_lock.mutating(j.project_id):   # serialize against concurrent edits/jobs
                        result = fn(db, j.params or {})
                else:
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


def recover_orphans(db: Session, now: datetime | None = None) -> list[str]:
    """Re-queue jobs left `running` by a process that is no longer alive. Returns the ids re-queued.

    **This re-queued EVERY `running` row in the database**, which was right while exactly one process
    ever ran the queue and became wrong the moment `docker compose --scale worker=N` was documented.
    Under it, a worker booting re-queued the jobs its siblings were mid-execution on, and each of
    those then ran in two processes at once — for a mutating kind, two writers in one project.

    The compare-and-swap in `_claim_next` does not help and it is worth being precise about why: it
    arbitrates who may take a row that is *already* `queued`. A row reset to `queued` underneath a
    live worker is not a race it can see — it is the CAS faithfully handing out a job somebody is
    still running.

    So recovery now asks whether anyone is still working the row, using the heartbeat the claim
    stamps and the running worker refreshes. Silence beyond `_STALE_AFTER_SECONDS` means the process
    is gone.

    `heartbeat_at IS NULL` counts as stale only when `started_at` is ALSO older than the window. Rows
    claimed by a build that predates the column have no heartbeat and would otherwise be immortal;
    the `started_at` clause recovers them without also catching a row claimed microseconds ago by a
    sibling running new code, whose claim stamps both fields in one statement.
    """
    now = now or utc_now()
    cutoff = now - timedelta(seconds=_STALE_AFTER_SECONDS)
    rows = list(db.scalars(
        select(Job).where(
            Job.state == "running",
            sa_or(Job.heartbeat_at < cutoff,
                  sa_and(Job.heartbeat_at.is_(None),
                         sa_or(Job.started_at.is_(None), Job.started_at < cutoff))),
        )))
    for j in rows:
        j.state = "queued"
        j.started_at = None
        j.heartbeat_at = None
    if rows:
        db.commit()
    return [j.id for j in rows]


def start_worker() -> None:
    """Start the per-process worker (idempotent) and recover orphans: a job left `running` by a
    crashed process is re-queued — handlers are idempotent by contract, so a re-run is safe. A job
    a LIVE sibling worker is running is left alone; see `recover_orphans`."""
    global _THREAD
    from .db import SessionLocal
    with _LOCK:
        db = SessionLocal()
        try:
            requeued = recover_orphans(db)
            if requeued:
                log.warning("job queue: re-queued %d orphaned running job(s) from a previous process",
                            len(requeued))
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


# --- JOB-STALL-VISIBLE: is the queue actually moving? ---------------------------------------------
def queue_stats(db: Session) -> dict[str, Any]:
    """Depth and head-of-line age for the whole queue, across every project.

    **This is the only thing that can tell a wedged worker from an idle one.** Every other signal
    says the same thing in both cases: the API is healthy either way (it does not run the jobs), the
    worker container is up either way, and `/projects/{pid}/jobs` is project-scoped so no operator
    view exists at all. What differs is that a stalled queue has an old job at its head, and a
    healthy idle queue has no head.

    So the age is measured from `created_at` of the oldest **queued** row — not from the count.
    Depth alone is a bad alarm in both directions: a deep queue draining fast is fine, and a queue
    of ONE job stuck for six hours is an incident that never trips a threshold on depth.

    `oldest_queued_seconds` is **None when nothing is queued**, never 0.0. Zero would be a lie of the
    same kind the photo verdict avoids: it reads as "the oldest job is brand new" when the truth is
    "there is no oldest job". The renderer omits the series entirely in that case.
    """
    from sqlalchemy import func
    rows = dict(db.execute(select(Job.state, func.count()).group_by(Job.state)).all())
    oldest = db.scalars(select(Job.created_at).where(Job.state == "queued")
                        .order_by(Job.created_at).limit(1)).first()
    age = None
    if oldest is not None:
        # SQLite hands back a naive datetime even from DateTime(timezone=True); Postgres does not.
        # Subtracting an aware from a naive raises, so normalise before the arithmetic rather than
        # after — a TypeError here would take out the whole /metrics scrape.
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age = max(0.0, (utc_now() - oldest).total_seconds())
    return {"queued": int(rows.get("queued", 0)), "running": int(rows.get("running", 0)),
            "done": int(rows.get("done", 0)), "error": int(rows.get("error", 0)),
            "oldest_queued_seconds": age}


# --- JOB-WORKER-SPLIT: where does the worker run? -------------------------------------------------
WORKER_ENV = "AEC_JOB_WORKER"


def worker_enabled() -> bool:
    """Should THIS process run the worker thread? Read per call, never cached at import.

    Default `inline` — an unset variable must mean "behave exactly as before", because every existing
    single-container deployment has it unset and none of them should change on upgrade. The dangerous
    default here is the *plausible* one: defaulting to `off` would be defensible ("the split is the
    better architecture") and would silently stop every existing deployment from running any job at
    all, with no error anywhere. So the safe direction is the default and the split is opt-in.

    Anything other than `off` is inline, including a typo. Refusing to start on an unrecognised value
    would turn a fat-fingered env var into a boot failure; running the worker is the recoverable
    reading of an ambiguous instruction, whereas not running it is the silent one.
    """
    return os.environ.get(WORKER_ENV, "inline").strip().lower() != "off"


def run_forever() -> None:
    """Run the queue in the foreground until SIGTERM/SIGINT — the dedicated worker-process entrypoint.

    This deliberately **reuses `start_worker()`** rather than reimplementing the loop in the foreground.
    A second copy of the drain loop is the kind of duplicate that stays correct for one release and
    then drifts: the orphan recovery, the CAS retry, and the `_MUTATING_KINDS` lock handling would all
    have to be kept in step by hand, and nothing would fail when they weren't. The cost of reuse is one
    idle thread in the main process, which is not a cost.
    """
    import signal

    def _bye(signum, _frame):                            # noqa: ANN001 — signal handler signature
        log.info("job worker: signal %s — finishing the current job, then exiting", signum)
        stop_worker()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _bye)
        except (ValueError, OSError):                    # not the main thread, or not supported here
            log.debug("job worker: could not install a handler for %s", sig)

    start_worker()
    t = _THREAD
    if t is None:                                        # start_worker always sets it; be explicit
        raise RuntimeError("job worker failed to start")
    log.info("job worker: running in a dedicated process (queue kinds: %s)",
             ", ".join(sorted(KINDS)) or "none registered")
    while t.is_alive():
        t.join(timeout=1.0)
    log.info("job worker: stopped")


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


def _escalation_scan(db: Session, params: dict) -> dict:
    """WORKFLOW-ENGINE: run the overdue-escalation pass for a project off the request path, so it can be
    scheduled (nightly) or fired on demand without holding a request slot. Idempotent — each overdue
    record is escalated to a given level at most once (guarded by its timeline), so the crash-recovery
    re-run is safe. Params: {project_id, ladder?}. Returns the escalation summary."""
    from . import escalation
    pid = params.get("project_id") or ""
    if not pid:
        raise ValueError("escalation_scan needs a project_id")
    return escalation.run(db, pid, actor=escalation.SYSTEM_ACTOR, ladder=params.get("ladder"))


def _model_ci(db: Session, params: dict) -> dict:
    """MODEL-CI-2: run the quality-gate check pack off the request path. Auto-enqueued after every
    successful publish so the badge is always fresh; also schedulable. Idempotent — a re-run just
    recomputes and re-stores the report."""
    from . import model_ci
    from .model_index import _INDEX, _ensure_loaded
    pid = params.get("project_id") or ""
    if not pid:
        raise ValueError("model_ci needs a project_id")
    try:
        _ensure_loaded(pid)
    except Exception:                                # noqa: BLE001 — no index → checks skip honestly
        pass
    return model_ci.run(db, pid, _INDEX.get(pid))


def _echo(db: Session, params: dict) -> dict:
    """Test/diagnostic kind: returns its params (and proves the queue round-trips)."""
    return {"echo": params}


register_kind("echo", _echo)
register_kind("cobie_export", _cobie_export)            # read → artifact (no project-state write)
register_kind("compiled_set_pdf", _compiled_set_pdf)   # read → artifact
register_kind("model_export", _model_export)           # read → artifact
register_kind("clash_detect", _clash_detect)           # read-only
register_kind("escalation_scan", _escalation_scan, mutating=True)   # WRITES records (me.update_record)
register_kind("model_ci", _model_ci, mutating=True)    # writes the CI report; wants a consistent model read
