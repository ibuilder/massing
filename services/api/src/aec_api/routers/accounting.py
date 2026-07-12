"""Accounting export endpoints — GL CSV + QuickBooks IIF from construction cost records."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from .. import accounting, rbac
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/accounting/journal")
def journal(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Preview the flattened GL/AP entries (sub invoices + posted direct costs) as JSON."""
    entries = accounting.journal(db, pid)
    return {"entries": entries, "count": len(entries),
            "total": round(sum(e["amount"] for e in entries), 2)}


@router.get("/projects/{pid}/accounting/chart-of-accounts")
def chart_of_accounts(pid: str, _: str = Depends(require_role("viewer"))):
    """The standard construction chart of accounts (code, name, type, normal balance)."""
    return {"accounts": accounting.chart_of_accounts()}


@router.get("/projects/{pid}/accounting/journal-entries")
def journal_entries(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Balanced double-entry journal from job cost + billing + the WIP percentage-of-completion adjustment."""
    return accounting.journal_entries(db, pid)


@router.get("/projects/{pid}/accounting/trial-balance")
def trial_balance(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Trial balance — debits and credits per account (must tie), from the double-entry journal."""
    return accounting.trial_balance(db, pid)


@router.get("/projects/{pid}/accounting/gl.csv")
def gl_csv(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Double-entry general-ledger CSV (universal import for QuickBooks / Sage / Xero)."""
    body = accounting.to_gl_csv(accounting.journal(db, pid))
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="gl.csv"'})


@router.get("/projects/{pid}/accounting/bills.iif")
def bills_iif(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """QuickBooks IIF bills file (AP bills from subcontractor invoices)."""
    body = accounting.to_iif_bills(accounting.journal(db, pid))
    return Response(body, media_type="application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="bills.iif"'})


@router.post("/projects/{pid}/accounting/journal-batch")
def create_journal_batch(pid: str, body: dict = Body(default={}),
                         db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Freeze the current books into an approval-gated journal batch. The batch then moves
    submit → approve → export via the standard workflow (the config engine gates each step by party);
    export emits the CSV/IIF from the frozen snapshot, so the accountant imports the approved figures."""
    period = (body.get("period") or "").strip()
    if not period:
        raise HTTPException(422, "period is required")
    party = rbac.party_role_for(db, pid, user)
    return accounting.create_batch(db, pid, period, (body.get("memo") or "").strip(), user, party)


@router.get("/projects/{pid}/accounting/journal-batch/{bid}/export")
def export_journal_batch(pid: str, bid: str, fmt: str = Query("gl"),
                         db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Download an **approved** batch's frozen GL: fmt=gl → CSV, fmt=iif → QuickBooks IIF.
    409 until the batch is approved (nothing exports to the books without passing the gate)."""
    try:
        out, media, filename = accounting.export_batch(db, pid, bid, fmt)
    except ValueError as e:
        raise HTTPException(404 if str(e) == "not found" else 409, str(e)) from e
    return Response(out, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
