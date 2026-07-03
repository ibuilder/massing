"""Subcontractor prequalification scoring + COI-expiry endpoints (project-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import prequalification as pq
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
