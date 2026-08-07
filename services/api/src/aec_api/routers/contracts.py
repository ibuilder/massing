"""Contract document lifecycle: generate (agreement / prime / change-order / Exhibit A scope),
fetch the scope-clause library, and capture signatures on a contract record. Documents render from
the existing config-driven contract modules (no new tables); signatures live on the record `data`."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import audit, contracts, esign, esign_bridge, scope_library
from .. import modules as me
from ..db import get_db
from ..rbac import current_user, require_role
from ..throttle import rate_limited

router = APIRouter()

# contract module -> the document it generates (for one-click digital signing)
_DEFAULT_DOC = {"prime_contract": "prime", "subcontract": "agreement", "commitment": "agreement", "cor": "co"}


@router.get("/esign/status")
def esign_status(_: str = Depends(current_user)):
    """Digital-signature capability: built-in PAdES (always available) + the optional 3rd-party bridge."""
    return {"pades": esign.status(), "bridge": esign_bridge.status()}


@router.get("/scope-library")
def scope_library_list(division: str | None = None, trade: str | None = None,
                       _: str = Depends(current_user)):
    """The scope-of-work clause library used to compose Exhibit A (ids + titles, no bodies).

    `division` (a CSI MasterFormat key) or `trade` (which resolves to one) narrows the catalog to that
    division plus the universal clauses. The filter is not a nicety: the library spans every
    MasterFormat division, and an unnarrowed composer asks somebody to pick a subcontract exhibit out
    of a list where most entries belong to other trades. The response carries `divisions` so a caller
    can offer the filter without knowing the catalog.

    No clause count is quoted here on purpose. This docstring is published into `/openapi.json`, so a
    number in it is a live claim to every API consumer that nothing re-checks — the same reason the
    web standards stopped quoting a test count. `GET /scope-library` with no filter returns the
    current catalog; that is the number, and it cannot drift from itself.

    `trade` is resolved server-side rather than by the caller so the mapping lives in one place; an
    unrecognised trade returns the whole catalog rather than an empty one, which is the same
    fall-back `default_ids` makes.

    `exhibit_categories` says which of the returned clauses can actually go INTO Exhibit A, so a
    composer can offer only those without restating the rule. It is not decoration: `library()`
    returns clauses whose division matches **or is None**, and every `gc-*`/`sc-*` conditions clause
    has division None — so a narrowed catalog still contains clauses the exhibit renderer will drop.
    Without this the picker offers a tick that silently does nothing, which teaches a user the control
    is broken.

    Served rather than hardcoded client-side because a second copy of this exact rule is what caused
    the preview/document divergence: the route filtered and the PDF did not. One authority, read by
    everyone who needs it.
    """
    div = division or scope_library.division_for_trade(trade)
    return {"clauses": scope_library.library(div),
            "division": div, "division_name": scope_library.division_name(div),
            "divisions": sorted({c["division"] for c in scope_library.CLAUSES if c.get("division")}),
            "exhibit_categories": sorted(scope_library.EXHIBIT_CATEGORIES)}


@router.get("/scope-library/exhibit")
def scope_library_exhibit(trade: str | None = None, clauses: str | None = None,
                          _: str = Depends(current_user)):
    """Assemble a scope of work: the clauses that would go into Exhibit A, numbered, with bodies.

    This is the read-only half of the exhibit that `document.pdf?doc=exhibit` renders, and it exists
    so the composer can show what it is about to produce **before** a PDF is generated and attached to
    a record. It takes the same `clauses` override and the same trade default, so what is previewed
    here and what is signed there come from one code path rather than two that drift.

    Only exhibit categories are returned — inclusions, exclusions, clarifications. The conditions
    clauses belong to the agreement body, not to Exhibit A, and returning them here would invite a
    caller to render them twice in one contract package.
    """
    picked = scope_library.exhibit_clauses([c for c in (clauses or "").split(",") if c] or None, trade)
    return {"trade": trade,
            "division": (div := scope_library.division_for_trade(trade)),
            "division_name": scope_library.division_name(div),
            "clauses": scope_library.numbered(picked),
            "counts": {cat: sum(1 for c in picked if c["category"] == cat)
                       for cat in sorted({c["category"] for c in picked})}}


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


@router.get("/projects/{pid}/contracts/{key}/{rid}/exhibit.docx")
def contract_exhibit_docx(pid: str, key: str, rid: str, clauses: str | None = None,
                          attach: bool = False, db: Session = Depends(get_db),
                          user: str = Depends(require_role("viewer"))):
    """Exhibit A as an editable Word document — the copy a subcontractor redlines and sends back.

    Same clause selection and same merge context as `document.pdf?doc=exhibit`; only the container
    differs. The PDF is the signed instrument, this is the negotiating copy, and scope negotiation is
    redlining — a PDF is the wrong object to hand somebody who has to strike what they do not hold.

    A separate path rather than `document.pdf?fmt=docx` because the extension is what a browser, a
    mail client and a document management system all key on; a `.pdf` URL that returns a Word file is
    the kind of thing that arrives at a subcontractor as a file their machine refuses to open.
    """
    clause_ids = [c for c in (clauses or "").split(",") if c] or None
    try:
        blob = contracts.exhibit_docx(db, key, pid, rid, clause_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    name = f"exhibit-a-{rid}.docx"
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if attach:
        me.add_attachment(db, key, pid, rid, name, mime, blob, user)
    return Response(blob, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


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


_ESIGN_HOOK_THROTTLE = rate_limited("esign_webhook", 60)


def _esign_hook_secret() -> str:
    """Shared secret for provider webhook signatures. Set AEC_ESIGN_WEBHOOK_SECRET to the value
    configured in the e-signature provider; unset leaves the endpoint unauthenticated (see below)."""
    return os.environ.get("AEC_ESIGN_WEBHOOK_SECRET", "").strip()


@router.post("/esign/webhook")
async def esign_webhook(request: Request, db: Session = Depends(get_db),
                        _t: None = Depends(_ESIGN_HOOK_THROTTLE)):
    """Receive a provider completion webhook (e.g. DocuSeal form.completed).

    Anonymous by necessity — the provider cannot hold a user credential — and the payload carries no
    authority: nothing here marks a contract signed, it only records a normalized completion for
    reconciliation. That design is what keeps a forged callback from executing a contract, and it is
    worth stating because the obvious fear is the wrong one.

    The real exposure was the audit table itself. This wrote a row per request with
    caller-controlled `submission_id`, `event` and `signer` of unbounded length, from the internet,
    unauthenticated and unthrottled. That is write access to the record the platform relies on to say
    who did what: flood it and real entries are buried in noise (and the table grows without limit),
    which is indistinguishable from tampering when someone later needs the trail. An audit log an
    anonymous caller can write to is not an audit log.

    So: verify an HMAC-SHA256 signature over the RAW body when a secret is configured, throttle per
    caller, and bound every stored string. When no secret is set the endpoint stays open, because
    silently dropping callbacks would break an operator who is relying on it today — but it is then
    only rate-limited and bounded, and `signature_verified` records which posture produced the row so
    an unverified entry can never be read as a verified one.
    """
    raw = await request.body()
    if len(raw) > 64 * 1024:                       # a completion callback is ~1 KB; refuse a bulk write
        raise HTTPException(413, "webhook payload too large")
    secret = _esign_hook_secret()
    verified = False
    if secret:
        # Providers differ on the header name; accept the common ones rather than force one provider.
        sent = (request.headers.get("x-signature") or request.headers.get("x-docuseal-signature")
                or request.headers.get("x-hub-signature-256") or "")
        sent = sent.split("=", 1)[1] if sent.startswith("sha256=") else sent
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        # compare_digest: a plain `==` leaks the prefix length through timing, which is enough to
        # recover a signature byte by byte given an endpoint that can be called at will.
        if not (sent and hmac.compare_digest(sent.strip().lower(), expected)):
            raise HTTPException(403, "invalid webhook signature")
        verified = True
    try:
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict):
            raise ValueError("payload must be a JSON object")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "webhook body must be a JSON object")
    info = esign_bridge.parse_completion(body)
    # Bound what reaches the audit row. parse_completion fixes the SHAPE to four keys, which is not
    # the same as bounding the SIZE — every value in it is a string the caller chose.
    detail = {k: (v[:200] if isinstance(v, str) else v) for k, v in info.items()}
    detail["signature_verified"] = verified
    audit.record(db, action="contract.esign_webhook", actor="provider", method="POST",
                 path="/esign/webhook", detail=detail)
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
