"""Pay-app ↔ lien-waiver reconciliation + payment-bridge status."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import payapp, payments_bridge
from ..db import get_db
from ..rbac import current_user, require_role

router = APIRouter()


@router.get("/projects/{pid}/payapp/lien-exposure")
def lien_exposure(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Per-vendor billed / paid / waiver coverage and lien exposure (money paid without an
    unconditional waiver on file), worst first, with a project rollup."""
    return payapp.reconcile(db, pid)


@router.get("/payments/status")
def payments_status(_: str = Depends(current_user)):
    """Whether payment disbursement is configured. Off by default — Massing never moves money itself;
    it tracks the pay-app/lien-waiver workflow and gates release on waiver coverage."""
    return payments_bridge.status()
