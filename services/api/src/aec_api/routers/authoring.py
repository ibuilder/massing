"""Authoring endpoints (Phase 6): apply an IFC edit recipe and publish the round-trip
(reconvert -> reindex) so the viewer refreshes. Edits keep GUIDs stable, so pins/RFIs/
clashes survive. This is the server-side / AI-driven path; the desktop path is Blender +
Bonsai driven over Bonsai-MCP (same ifcopenshell.api operations)."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, storage
from ..auth import require_writer
from ..db import get_db
from ..models import Project
from . import properties as props_router

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


@router.post("/projects/{pid}/edit")
def edit(pid: str, recipe: str = Body(...), params: dict = Body(default={}),
         publish: bool = Body(default=False), db: Session = Depends(get_db),
         actor: str = Depends(require_writer)):
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
    published = _publish(p) if publish else None
    return {**result, "published": published}


@router.post("/projects/{pid}/publish")
def publish(pid: str, reconvert: bool = Body(default=True), db: Session = Depends(get_db),
            actor: str = Depends(require_writer)):
    """Re-run the pipeline on the current source IFC: convert to .frag + rebuild the
    properties index, so the viewer streams the updated model."""
    p = _project(db, pid)
    audit.record(db, action="ifc.publish", actor=actor, method="POST",
                 path=f"/projects/{pid}/publish")
    db.commit()
    return _publish(p, reconvert=reconvert)


def _publish(p: Project, reconvert: bool = True) -> dict:
    from aec_data import properties_index  # type: ignore

    out = {"reconverted": False, "reindexed": 0}
    # 1. reconvert IFC -> .frag (Node converter), store under the project key
    if reconvert and _CONVERTER.exists():
        frag_key = f"{p.id}/model.frag"
        frag_path = storage.path(frag_key)
        frag_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["node", str(_CONVERTER), p.source_ifc, str(frag_path)],
                           check=True, capture_output=True, timeout=600)
            out["reconverted"] = True
            out["frag_key"] = frag_key
        except Exception as e:  # node missing / convert failed — non-fatal
            out["reconvert_error"] = str(e)
    # 2. rebuild + hot-load the properties index
    idx = properties_index.index_file(p.source_ifc)
    props_router._load(p.id, idx)  # hot-swap the in-memory index
    storage.put(f"{p.id}/props.json", __import__("json").dumps(idx).encode("utf-8"))
    out["reindexed"] = idx["counts"]["elements"]
    return out
