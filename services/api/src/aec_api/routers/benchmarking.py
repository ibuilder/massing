"""Portfolio benchmarking endpoints — cross-project intelligence from your own historical records.
Cross-project by design, so each roll-up is scoped to the caller's member projects
(rbac.member_project_ids) — portfolio aggregations must never leak other tenants' data."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import benchmarking
from ..db import get_db
from ..rbac import current_user, member_project_ids

router = APIRouter()


@router.get("/benchmarks/costs")
def cost_benchmarks(min_samples: int = 3, db: Session = Depends(get_db),
                    user: str = Depends(current_user)):
    """Actual-cost distribution (low/p25/median/p75/high) per cost code across your projects."""
    return benchmarking.cost_benchmarks(db, min_samples=max(1, min(min_samples, 50)),
                                        project_ids=member_project_ids(db, user))


@router.get("/benchmarks/response-rates")
def response_rates(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """RFI + submittal turnaround and overdue % across your projects (ball-in-court accountability)."""
    return benchmarking.response_rates(db, project_ids=member_project_ids(db, user))


@router.get("/benchmarks/pull-planning")
def pull_planning(min_committed: int = 3, db: Session = Depends(get_db),
                  user: str = Depends(current_user)):
    """Pull-planning reliability across your projects: PPC + Tasks-Made-Ready % distribution vs the
    ≥80% target — so a plan can be judged against the team's own portfolio."""
    return benchmarking.pull_planning(db, min_committed=max(1, min(min_committed, 50)),
                                      project_ids=member_project_ids(db, user))
