"""Takeoff pricing endpoints — price quantities from the book / live feed + variance."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import pricing, pricing_bridge
from ..db import get_db
from ..rbac import current_user, require_role

router = APIRouter()


@router.get("/projects/{pid}/pricing/reconcile")
def reconcile(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Price the project's takeoff (production_quantity) against the unit price book / live feed, with
    per-line variance vs any estimated unit price."""
    return pricing.project_pricing(db, pid)


@router.get("/pricing/status")
def pricing_status(_: str = Depends(current_user)):
    """Whether a live pricing feed is configured (else the built-in book is used)."""
    return pricing_bridge.status()
