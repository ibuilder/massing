"""Contract document lifecycle: generate (agreement / prime / change-order / Exhibit A scope),
fetch the scope-clause library, and capture signatures on a contract record. Documents render from
the existing config-driven contract modules (no new tables); signatures live on the record `data`."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit, contracts, scope_library
from .. import modules as me
from ..db import get_db
from ..rbac import current_user, require_role

router = APIRouter()


@router.get("/scope-library")
def scope_library_list(_: str = Depends(current_user)):
    """The scope-of-work clause library used to compose Exhibit A (ids + titles, grouped by category)."""
    return {"clauses": scope_library.library()}


@router.get("/projects/{pid}/contracts/{key}/{rid}/document.pdf")
def contract_document(pid: str, key: str, rid: str, doc: str = "agreement",
                      clauses: str | None = None, attach: bool = False,
                      db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    """Render a contract document for a record. doc = agreement | prime | co | exhibit. `clauses` is a
    comma-separated list of scope_library ids for Exhibit A (defaults to the record's trade). With
    attach=1 the PDF is also saved as an attachment on the record."""
    clause_ids = [c for c in (clauses or "").split(",") if c] or None
    try:
        pdf = contracts.render(db, key, pid, rid, doc, clause_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    if attach:
        me.add_attachment(db, key, pid, rid, f"{doc}-{rid}.pdf", "application/pdf", pdf, user)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc}-{rid}.pdf"'})


@router.post("/projects/{pid}/contracts/{key}/{rid}/sign")
def sign_contract(pid: str, key: str, rid: str, body: dict = Body(...),
                  db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Record a party's signature on a contract/CO (typed name + date) on the record `data`, audited.
    One signature per party (re-signing replaces). Advancing the workflow state is a separate
    transition — sign captures the executed signature; the UI calls /transition to move the record."""
    party = (body.get("party") or "").strip()
    name = (body.get("name") or user or "").strip()
    if not party or not name:
        raise HTTPException(422, "party and name are required")
    rec = me.get_record(db, key, pid, rid)
    sigs = [s for s in ((rec.get("data") or {}).get("signatures") or []) if s.get("party") != party]
    sigs.append({"party": party, "name": name, "method": "typed",
                 "signed_at": datetime.now(timezone.utc).date().isoformat()})
    out = me.update_record(db, key, pid, rid, {"signatures": sigs}, user, party)
    audit.record(db, action="contract.sign", actor=user, method="POST",
                 path=f"/projects/{pid}/contracts/{key}/{rid}/sign", detail={"party": party})
    db.commit()
    return {"signatures": (out.get("data") or {}).get("signatures", [])}
