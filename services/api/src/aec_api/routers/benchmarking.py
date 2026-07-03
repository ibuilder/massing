"""Portfolio benchmarking endpoints — cross-project intelligence from your own historical records.
Not project-scoped (they aggregate across every project), so gated by authentication rather than a
project role."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import benchmarking
from ..db import get_db
from ..rbac import current_user

router = APIRouter()


@router.get("/benchmarks/costs")
def cost_benchmarks(min_samples: int = 3, db: Session = Depends(get_db),
                    _: str = Depends(current_user)):
    """Actual-cost distribution (low/p25/median/p75/high) per cost code across all projects."""
    return benchmarking.cost_benchmarks(db, min_samples=max(1, min(min_samples, 50)))


@router.get("/benchmarks/response-rates")
def response_rates(db: Session = Depends(get_db), _: str = Depends(current_user)):
    """RFI + submittal turnaround and overdue % across all projects (ball-in-court accountability)."""
    return benchmarking.response_rates(db)
