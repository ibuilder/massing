"""Portfolio benchmarking endpoints — cross-project intelligence from your own historical records.
Cross-project by design, so each roll-up is scoped to the caller's member projects
(rbac.member_project_ids) — portfolio aggregations must never leak other tenants' data."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import benchmarking, unit_rate_memory
from ..db import get_db
from ..rbac import current_user, member_project_ids

router = APIRouter()


@router.get("/benchmarks/costs")
def cost_benchmarks(min_samples: int = 3, db: Session = Depends(get_db),
                    user: str = Depends(current_user)):
    """Actual-cost distribution (low/p25/median/p75/high) per cost code across your projects."""
    return benchmarking.cost_benchmarks(db, min_samples=max(1, min(min_samples, 50)),
                                        project_ids=member_project_ids(db, user))


@router.get("/benchmarks/unit-rates")
def unit_rates(min_projects: int = 3, db: Session = Depends(get_db),
               user: str = Depends(current_user)):
    """Actual **unit** rates per cost code — `direct_cost` divided by installed
    `production_quantity` — distributed across your projects.

    The sibling of `/benchmarks/costs`, and the one that needs the field's own quantity records:
    that endpoint says what a cost code has cost, this one says what it cost **per unit**, which is
    the difference between "this project was expensive" and "concrete is dear".

    Each rate is ONE project's cost over that project's quantity, and the distribution is over
    projects. `pooled_rate` — the portfolio-wide blend — is reported beside it and answers a
    different question; one large project sets it. Units are grouped, never converted, and a project
    that records one cost code under two units is excluded rather than split. Everything excluded
    comes back with a count and a reason."""
    return unit_rate_memory.unit_rates(db, min_projects=max(1, min(min_projects, 50)),
                                       project_ids=member_project_ids(db, user))


@router.get("/benchmarks/response-rates")
def response_rates(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """RFI + submittal turnaround and overdue % across your projects (ball-in-court accountability)."""
    return benchmarking.response_rates(db, project_ids=member_project_ids(db, user))


@router.get("/benchmarks/space-utilization")
def space_utilization(area_per_person: float = 10.0, db: Session = Depends(get_db),
                      user: str = Depends(current_user)):
    """SPACE-UTIL benchmarking — capacity/utilization across your modelled projects (space count,
    total area, capacity at the given m²/person standard, m² per space vs the portfolio median).
    Bounded to 12 models per call (newest first; skips are counted, never silent)."""
    return benchmarking.space_utilization(db, area_per_person=max(1.0, min(area_per_person, 100.0)),
                                          project_ids=member_project_ids(db, user))


@router.get("/benchmarks/pull-planning")
def pull_planning(min_committed: int = 3, db: Session = Depends(get_db),
                  user: str = Depends(current_user)):
    """Pull-planning reliability across your projects: PPC + Tasks-Made-Ready % distribution vs the
    ≥80% target — so a plan can be judged against the team's own portfolio."""
    return benchmarking.pull_planning(db, min_committed=max(1, min(min_committed, 50)),
                                      project_ids=member_project_ids(db, user))
