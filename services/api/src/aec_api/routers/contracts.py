"""Contract document lifecycle: generate (agreement / prime / change-order / Exhibit A scope),
fetch the scope-clause library, and capture signatures on a contract record. Documents render from
the existing config-driven contract modules (no new tables); signatures live on the record `data`."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit, contracts, esign, esign_bridge, scope_library
from .. import modules as me
from ..db import get_db
from ..rbac import current_user, require_role

router = APIRouter()

# contract module -> the document it generates (for one-click digital signing)
_DEFAULT_DOC = {"prime_contract": "prime", "subcontract": "agreement", "commitment": "agreement", "cor": "co"}


@router.get("/esign/status")
def esign_status(_: str = Depends(current_user)):
    """Digital-signature capability: built-in PAdES (always available) + the optional 3rd-party bridge."""
    return {"pades": esign.status(), "bridge": esign_bridge.status()}


@router.get("/scope-library")
def scope_library_list(_: str = Depends(current_user)):
    """The scope-of-work clause library used to compose Exhibit A (ids + titles, grouped by category)."""
    return {"clauses": scope_library.library()}


@router.get("/projects/{pid}/contracts/{key}/{rid}/document.pdf")
def contract_document(pid: str, key: str, rid: str, doc: str = "agreement",
                      clauses: str | None = None, attach: bool = False,
                      db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    """Render a contract/change document for a record. doc = agreement | prime | co | exhibit | asi
    (G710) | bulletin | ccd (G714, from a directive record). `clauses` is a comma-separated list of
    scope_library ids for Exhibit A (defaults to the record's trade). With attach=1 the PDF is also
    saved as an attachment on the record."""
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


@router.post("/projects/{pid}/contracts/{key}/{rid}/send-for-signature")
def send_for_signature(pid: str, key: str, rid: str, body: dict = Body(default={}),
                       db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Route a contract/CO document through the configured 3rd-party e-signature provider (DocuSeal et
    al.) for legally-binding multi-party signing. `signers` is a list of {email, name?, party?}. Stores
    the submission id + per-signer signing URLs on the record `data.esign_submission` (audited)."""
    if not esign_bridge.is_enabled():
        raise HTTPException(409, esign_bridge.status()["message"])
    signers = [s for s in (body.get("signers") or []) if (s or {}).get("email")]
    if not signers:
        raise HTTPException(422, "at least one signer with an email is required")
    doc = (body or {}).get("doc") or _DEFAULT_DOC.get(key, "agreement")
    clause_ids = [c for c in ((body or {}).get("clauses") or "").split(",") if c] or None
    rec = me.get_record(db, key, pid, rid)
    subject = (rec.get("data") or {}).get("subject") or f"{key} {rec.get('ref') or rid}"
    try:
        pdf = contracts.render(db, key, pid, rid, doc, clause_ids)
        result = esign_bridge.send_for_signature(pdf, signers, subject)
    except (RuntimeError, NotImplementedError) as e:
        raise HTTPException(502, f"e-signature provider error: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"send-for-signature failed: {e}")
    me.update_record(db, key, pid, rid, {"esign_submission": result}, user, None)
    audit.record(db, action="contract.send_for_signature", actor=user, method="POST",
                 path=f"/projects/{pid}/contracts/{key}/{rid}/send-for-signature",
                 detail={"provider": result.get("provider"), "submission_id": result.get("submission_id")})
    db.commit()
    return result


@router.post("/esign/webhook")
def esign_webhook(body: dict = Body(default={}), db: Session = Depends(get_db)):
    """Receive a provider completion webhook (e.g. DocuSeal form.completed). Anonymous surface — the
    payload carries no authority; we only log the normalized completion for audit/reconciliation."""
    info = esign_bridge.parse_completion(body or {})
    audit.record(db, action="contract.esign_webhook", actor="provider", method="POST",
                 path="/esign/webhook", detail=info)
    db.commit()
    return {"ok": True, **info}


@router.post("/projects/{pid}/contracts/{key}/{rid}/digital-sign")
def digital_sign(pid: str, key: str, rid: str, body: dict = Body(default={}),
                 db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Apply a certificate-based PAdES digital signature to the contract/CO document — tamper-evident,
    self-validating. Renders the document, signs it, attaches the signed PDF, and records the signer +
    cert fingerprint on the record (audit). Falls back cleanly if signing isn't available."""
    from datetime import datetime, timezone
    doc = (body or {}).get("doc") or _DEFAULT_DOC.get(key, "agreement")
    clause_ids = [c for c in ((body or {}).get("clauses") or "").split(",") if c] or None
    try:
        pdf = contracts.render(db, key, pid, rid, doc, clause_ids)
        signed = esign.digitally_sign(pdf, reason="Executed", name=user)
        fp = esign.signer_fingerprint()
    except Exception as e:  # noqa: BLE001 — never 500 the request over a signing failure
        raise HTTPException(503, f"digital signing unavailable: {e}")
    me.add_attachment(db, key, pid, rid, f"{doc}-signed-{rid}.pdf", "application/pdf", signed, user)
    rec = me.get_record(db, key, pid, rid)
    ds = list((rec.get("data") or {}).get("digital_signatures") or [])
    ds.append({"signer": user, "fingerprint": fp, "kind": esign.status()["kind"], "doc": doc,
               "signed_at": datetime.now(timezone.utc).isoformat()})
    me.update_record(db, key, pid, rid, {"digital_signatures": ds}, user, None)
    audit.record(db, action="contract.digital_sign", actor=user, method="POST",
                 path=f"/projects/{pid}/contracts/{key}/{rid}/digital-sign", detail={"doc": doc, "fingerprint": fp})
    db.commit()
    return {"signed": True, "fingerprint": fp, "kind": esign.status()["kind"]}
