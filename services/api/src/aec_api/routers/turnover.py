"""Turnover endpoints — substantial-completion readiness, architect certification (G704), and the
turnover package status (signed cert + record model)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, turnover
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/turnover/readiness")
def readiness(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Punch-list rollup + latest model version — is the project ready for a G704 certification?"""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return turnover.readiness(db, pid)


@router.get("/projects/{pid}/turnover/status")
def status(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Turnover package status: substantial-completion cert (signed?), record model, punch readiness."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return turnover.package_status(db, pid)


@router.post("/projects/{pid}/turnover/certify")
def certify(pid: str, cert_rid: str = Body(..., embed=True), architect: str = Body(..., embed=True),
            owner: str | None = Body(default=None, embed=True),
            contractor: str | None = Body(default=None, embed=True),
            occupancy_date: str | None = Body(default=None, embed=True),
            db: Session = Depends(get_db), actor: str = Depends(require_role("reviewer"))):
    """Architect certifies substantial completion on a completion_certificate record: gate on a prepared
    punch list, record the Architect (certifying) + Owner/Contractor signatures, stamp the record model
    version, and issue the certificate. Render the G704 via .../contracts/completion_certificate/{rid}/
    document.pdf?doc=g704."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    try:
        out = turnover.certify(db, pid, cert_rid, architect, owner, contractor, occupancy_date, actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.record(db, action="turnover.certify", actor=actor, method="POST",
                 path=f"/projects/{pid}/turnover/certify", detail={"cert_rid": cert_rid})
    db.commit()
    return out
