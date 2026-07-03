"""Design-lifecycle endpoints — the RIBA/AIA phase spine + itemized soft costs for a project."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import design_phase, soft_costs
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

router = APIRouter()


def _hard_cost(p: Project) -> float:
    """Project hard cost from the seeded dev budget (category='hard'); 0 if not seeded yet."""
    budget = getattr(p, "dev_budget", None) or {}
    total = 0.0
    for ln in budget.get("lines", []):
        if (ln.get("category") or "").lower() == "hard":
            total += float(ln.get("unit_cost") or 0) * float(ln.get("quantity") or 1)
    return total


@router.get("/projects/{pid}/lifecycle")
def lifecycle(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The project's design phases (RIBA 0–7 ↔ AIA) with gate state, deliverables, ISO-19650 status,
    and the phase-allocated A/E design fee from the itemized soft costs."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    hard = _hard_cost(p)
    lc = design_phase.lifecycle(db, pid, hard_cost=hard, soft_cost_pct=25.0)
    lc["soft_costs"] = soft_costs.itemize(hard, 25.0) if hard else None
    lc["hard_cost"] = hard
    return lc


@router.post("/projects/{pid}/lifecycle/seed")
def seed(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Seed the eight design-phase records on a project (idempotent)."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return design_phase.seed_phases(db, pid, actor)


@router.get("/lifecycle/reference")
def reference(_: str = Depends(current_user)):
    """The canonical RIBA↔AIA phase definitions + soft-cost taxonomy (for the UI, no project needed)."""
    return {"phases": design_phase.PHASES,
            "soft_cost_components": soft_costs.COMPONENTS,
            "ae_phase_split": soft_costs.AE_PHASE_SPLIT}
