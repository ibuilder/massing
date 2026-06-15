"""Analysis & QA endpoints (guide COORDINATION + ANALYSIS): clash detection (Navisworks
parity) and IDS validation (Bonsai parity). Both read the project's source IFC."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import audit
from ..rbac import require_role
from ..db import get_db
from ..models import Project, Topic

_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


def _source_ifc(db: Session, pid: str) -> str:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC")
    return p.source_ifc


def _classes(csv: str | None) -> list[str] | None:
    return [c.strip() for c in csv.split(",") if c.strip()] if csv else None


@router.post("/projects/{pid}/clash")
def run_clash(
    pid: str,
    a: str | None = None,
    b: str | None = None,
    min_volume: float = 1e-3,
    tolerance: float = 0.0,
    narrow: bool = True,
    max_narrow: int = 1500,
    create_topics: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    actor: str = Depends(require_role("editor")),
):
    """Detect clashes between two IFC-class groups (comma-separated in `a` / `b`).
    narrow=true runs the mesh boolean-intersection narrow phase (exact penetration volume).
    With create_topics=true, the top clashes become BCF `clash` topics (pins/issues)."""
    from aec_data import clash  # type: ignore

    ifc = _source_ifc(db, pid)
    results = clash.detect_file(ifc, _classes(a), _classes(b), min_volume, tolerance,
                               narrow=narrow, max_narrow=max_narrow)

    created = 0
    if create_topics:
        for c in results[:limit]:
            t = Topic(
                project_id=pid, type="clash", status="open",
                title=f"Clash: {c['a_class']} × {c['b_class']} ({c['method']} vol {c['volume']})",
                anchor=c["point"], element_guids=[c["a_guid"], c["b_guid"]],
            )
            db.add(t)
            created += 1
        audit.record(db, action="clash.create_topics", actor=actor, method="POST",
                     path=f"/projects/{pid}/clash", detail={"created": created})
        db.commit()

    return {"count": len(results), "created_topics": created, "clashes": results[:limit],
            "truncated": len(results) > limit}


@router.post("/projects/{pid}/validate")
async def run_validate(
    pid: str,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    """Validate the source IFC against an uploaded .ids (or the built-in default QA specs)."""
    from aec_data import validate  # type: ignore

    ifc = _source_ifc(db, pid)
    ids_path = None
    if file is not None:
        tmp = Path(_DATA_SRC).parent / "_tmp.ids"
        tmp.write_bytes(await file.read())
        ids_path = str(tmp)
    try:
        return validate.validate_file(ifc, ids_path)
    finally:
        if ids_path:
            Path(ids_path).unlink(missing_ok=True)
