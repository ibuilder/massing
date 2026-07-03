"""Subcontractor prequalification scoring + COI-expiry endpoints (project-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import prequalification as pq
from .. import procurement_gate
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/prequal/scores")
def prequal_scores(pid: str, project_size: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Q-score (0-100) + risk band + factor breakdown for every prequalified sub, worst first.
    Pass `project_size` to weight financial/experience factors against this job's value."""
    return pq.score_project(db, pid, project_size=project_size)


@router.get("/projects/{pid}/prequal/coi-expiry")
def coi_expiry(pid: str, soon_days: int = 30, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """Certificates of insurance expired or expiring within `soon_days`."""
    return pq.coi_expiry(db, pid, soon_days=max(1, min(soon_days, 365)))


@router.get("/projects/{pid}/procurement/gate")
def procurement_gate_check(pid: str, vendor: str, db: Session = Depends(get_db),
                           _: str = Depends(require_role("viewer"))):
    """Compliance gate for a vendor: can they bid (approved prequal + active insurance) and can they
    bill (executed subcontract + active insurance), with the specific blockers."""
    return procurement_gate.gate(db, pid, vendor)


@router.get("/projects/{pid}/procurement/compliance-feed")
def procurement_compliance_feed(pid: str, within_days: int = 30, db: Session = Depends(get_db),
                                _: str = Depends(require_role("viewer"))):
    """Outbound nudge list — vendors with an expiring/expired/missing COI or an unapproved prequal,
    before it blocks a bid invitation or a pay application."""
    return procurement_gate.compliance_feed(db, pid, within_days=max(1, min(within_days, 365)))
