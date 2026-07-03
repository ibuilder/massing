"""ISO 19650 / openBIM standards endpoints — CDE container discipline + requirements register."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cde, ids_authoring, openbim_quality
from ..db import get_db
from ..models import Project
from ..rbac import current_user

router = APIRouter()


def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.get("/projects/{pid}/cde/status")
def cde_status(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """CDE container rollup (ISO 19650): state distribution WIP/Shared/Published/Archived,
    suitability spread, and CDE-discipline metrics (revision control, approval-status coverage,
    metadata completeness)."""
    _project(db, pid)
    return cde.status(db, pid)


@router.get("/projects/{pid}/info-requirements/register")
def requirements_register(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The information-requirements register (OIR/AIR/PIR/EIR/BEP/MIDP/TIDP) with issued/draft
    counts and core-document coverage (EIR, BEP, AIR)."""
    _project(db, pid)
    return cde.requirements(db, pid)


@router.get("/projects/{pid}/openbim/quality")
def openbim_quality_scan(pid: str, use_case: str | None = None, db: Session = Depends(get_db),
                         _: str = Depends(current_user)):
    """openBIM quality of the loaded model: LOIN per element, IFC export health, bSDD alignment, and
    (when ?use_case= names an IDS use case) IDS rule-compliance scoring. Needs a loaded model."""
    _project(db, pid)
    from .properties import _INDEX, _ensure_loaded
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project — load a model first")
    specs = ids_authoring.specs_for_use_case(use_case) if use_case else None
    out = openbim_quality.summary(idx, specs)
    out["use_case"] = use_case
    return out

