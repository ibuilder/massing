"""Authoring endpoints (Phase 6): apply an IFC edit recipe and publish the round-trip
(reconvert -> reindex) so the viewer refreshes. Edits keep GUIDs stable, so pins/RFIs/
clashes survive. This is the server-side / AI-driven path; the desktop path is Blender +
Bonsai driven over Bonsai-MCP (same ifcopenshell.api operations)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import audit, storage
from ..rbac import current_user, require_role
from ..db import get_db
from ..models import Project
from . import properties as props_router

_IFC_DIR = Path(os.environ.get("IFC_DIR", "/app/ifc"))   # local IFC copies the converter can read
_REPO = Path(__file__).resolve().parents[5]
_DATA_SRC = _REPO / "services" / "data" / "src"
_CONVERTER = _REPO / "services" / "converter" / "src" / "cli.mjs"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC")
    return p


@router.get("/projects/{pid}/types")
def list_types(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Catalog of placeable types ("families") in the project's source IFC, for the place-family
    picker. Deduped by (class, name)."""
    from aec_data import edit as ed  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return {"types": ed.list_types(open_model(p.source_ifc))}


@router.get("/families/catalog")
def family_catalog(_: str = Depends(current_user)):
    """Starter IFC family library (furniture / sanitary / appliances / plants) you can add to any
    model — generated parametrically, so it's available even for a from-scratch massing model. Place
    one via the `add_family` edit recipe (POST /projects/{id}/edit, recipe='add_family')."""
    from aec_data import families  # type: ignore

    items = families.catalog()
    cats: dict[str, list] = {}
    for it in items:
        cats.setdefault(it["category"], []).append(it)
    return {"count": len(items), "categories": cats}


@router.post("/projects/{pid}/edit")
def edit(pid: str, recipe: str = Body(...), params: dict = Body(default={}),
         publish: bool = Body(default=False), db: Session = Depends(get_db),
         actor: str = Depends(require_role("editor"))):
    """Apply an authoring recipe (set_pset | batch_tag | place_type) to the source IFC,
    saving a new version. GUIDs of existing elements are preserved."""
    from aec_data import edit as ed  # type: ignore

    p = _project(db, pid)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    out = str(Path(p.source_ifc).with_name(f"{Path(p.source_ifc).stem}_{stamp}.ifc"))
    result = ed.apply_recipe(p.source_ifc, recipe, params, out)
    p.source_ifc = out  # new version becomes the source of truth
    audit.record(db, action="ifc.edit", actor=actor, method="POST",
                 path=f"/projects/{pid}/edit", detail=result)
    db.commit()
    if publish:                       # reconvert off-thread; client polls publish/status
        _publish_bg(pid)
        result["publish"] = "running"
    return result


@router.post("/projects/{pid}/publish", status_code=202)
def publish(pid: str, reconvert: bool = Body(default=True), db: Session = Depends(get_db),
            actor: str = Depends(require_role("editor"))):
    """Re-run the pipeline on the current source IFC (convert to .frag + reindex), off the
    request thread. Returns immediately; poll GET publish/status for completion."""
    p = _project(db, pid)
    audit.record(db, action="ifc.publish", actor=actor, method="POST",
                 path=f"/projects/{pid}/publish")
    db.commit()
    _publish_bg(pid)
    return {"state": "running"}


@router.post("/projects/{pid}/source-ifc")
async def upload_source_ifc(pid: str, file: UploadFile = File(...), publish: bool = True,
                            db: Session = Depends(get_db),
                            actor: str = Depends(require_role("editor"))):
    """Upload a project's source IFC (enables authoring + republish). Saves a local copy
    the converter can read plus a durable copy in object storage, then publishes."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    data = await file.read()
    _IFC_DIR.joinpath(pid).mkdir(parents=True, exist_ok=True)
    ifc_path = _IFC_DIR / pid / "source.ifc"
    ifc_path.write_bytes(data)
    storage.put(f"{pid}/source.ifc", data)          # durable copy
    p.source_ifc = str(ifc_path)
    db.commit()
    audit.record(db, action="ifc.upload", actor=actor, method="POST",
                 path=f"/projects/{pid}/source-ifc")
    db.commit()
    out: dict = {"source_ifc": str(ifc_path), "size": len(data)}
    if publish:                       # convert off-thread; client polls publish/status
        _publish_bg(pid)
        out["publish"] = "running"
    return out


def _publish(p: Project, reconvert: bool = True) -> dict:
    from aec_data import properties_index  # type: ignore

    out = {"reconverted": False, "reindexed": 0}
    # 1. reconvert IFC -> .frag (Node converter); convert to a temp file then push through
    #    storage.put so it works with both the local and S3/MinIO backends.
    if reconvert and _CONVERTER.exists() and p.source_ifc and Path(p.source_ifc).exists():
        frag_key = f"{p.id}/model.frag"
        try:
            with tempfile.TemporaryDirectory() as td:
                frag_tmp = Path(td) / "model.frag"
                subprocess.run(["node", str(_CONVERTER), p.source_ifc, str(frag_tmp)],
                               check=True, capture_output=True, timeout=600)
                storage.put(frag_key, frag_tmp.read_bytes())
            out["reconverted"] = True
            out["frag_key"] = frag_key
        except Exception as e:  # node missing / convert failed — non-fatal
            out["reconvert_error"] = str(e)[:300]
    # 2. rebuild + hot-load the properties index
    idx = properties_index.index_file(p.source_ifc)
    props_router._load(p.id, idx)  # hot-swap the in-memory index
    storage.put(f"{p.id}/props.json", __import__("json").dumps(idx).encode("utf-8"))
    out["reindexed"] = idx["counts"]["elements"]
    try:                              # snapshot a model version (GUID set) for history/diff
        from .. import versions
        out["version"] = versions.snapshot(p.id, idx)
    except Exception as e:            # noqa: BLE001 — versioning must never break a publish
        out["version_error"] = str(e)[:160]
    return out


# --- background publish (convert/reindex off the request thread) -------------
def _set_pub_status(pid: str, state: str, detail: dict | None = None) -> None:
    storage.put(f"{pid}/publish_status.json", json.dumps(
        {"state": state, "detail": detail,
         "at": datetime.now(timezone.utc).isoformat()}).encode())


def _publish_bg(pid: str) -> None:
    """Run _publish in a daemon thread (fresh DB session). A 50MB IFC convert takes
    minutes — doing it in-request would tie up a worker; clients poll publish/status."""
    from ..db import SessionLocal

    def run():
        try:
            with SessionLocal() as db:
                p = db.get(Project, pid)
                if not p:
                    return
                result = _publish(p)
            _set_pub_status(pid, "error" if result.get("reconvert_error") else "done", result)
        except Exception as e:
            _set_pub_status(pid, "error", {"error": str(e)[:300]})

    _set_pub_status(pid, "running")
    threading.Thread(target=run, daemon=True).start()


@router.get("/projects/{pid}/publish/status")
def publish_status(pid: str, _: str = Depends(require_role("viewer"))):
    """Poll the async publish job: idle | running | done | error (+ detail)."""
    key = f"{pid}/publish_status.json"
    if storage.exists(key):
        return json.loads(storage.get(key))
    return {"state": "idle"}
