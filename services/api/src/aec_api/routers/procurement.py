"""Materials procure-to-pay endpoints — quote leveling, 3-way match, RFQ-dispatch status."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from .. import procurement, procurement_bridge
from ..db import get_db
from ..rbac import current_user, require_role

router = APIRouter()


@router.post("/projects/{pid}/procurement/level-quotes")
def level_quotes(pid: str, quotes: list[dict] = Body(..., embed=True),
                 _: str = Depends(require_role("viewer"))):
    """Level competing material quotes into an apples-to-apples grid + low price per line + best supplier.
    Body: {quotes:[{supplier, lines:[{item, qty, unit, unit_price}]}]}."""
    return procurement.level_quotes(quotes)


@router.get("/projects/{pid}/procurement/three-way-match")
def three_way_match(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Reconcile each PO (commitment) against its deliveries and invoices — flags over-billing,
    pay-before-receipt, and un-invoiced deliveries."""
    return procurement.three_way_match(db, pid)


@router.get("/procurement/rfq-status")
def rfq_status(_: str = Depends(current_user)):
    """Whether RFQ dispatch to suppliers is configured (else quote leveling + 3-way match still work)."""
    return procurement_bridge.status()
