"""ISO 19650 / openBIM standards endpoints — CDE container discipline + requirements register."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cde
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
