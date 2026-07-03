"""Embodied-carbon endpoint — kgCO2e from the project's material quantities."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import carbon
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/carbon")
def project_carbon(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Embodied carbon (A1-A3) from `production_quantity` records: per-line kgCO2e, total tCO2e, and
    rollups by material + cost code. Built-in EPD factors (design-stage signal, not a certified LCA)."""
    return carbon.project_carbon(db, pid)
