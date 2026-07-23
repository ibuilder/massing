"""CLIENT-PORTAL routes — share-token management (owner-authenticated) + the public read-only digest.

The management routes are gated to editors on the project; the public digest route takes only the token
(the token IS the credential) and exposes a curated readiness summary. An unknown/revoked token 404s.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session  # noqa: F401

from .. import client_portal
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.post("/projects/{pid}/share-tokens")
def create_share_token(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                       actor: str = Depends(require_role("editor"))):
    """Mint a revocable, read-only share token for the project (owner/editor only). The returned token
    string is the shareable credential — anyone with it can read the project's readiness digest.
    `show_payments: true` is the explicit OPT-IN for THIS token's digest to carry the owner-invoice
    payment schedule (display only); the default digest exposes no financials."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    try:
        return client_portal.create_token(db, pid, body.get("label"), actor,
                                          show_payments=bool(body.get("show_payments")))
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.get("/projects/{pid}/share-tokens")
def list_share_tokens(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """List the project's share tokens with their view counts (editor only)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return {"tokens": client_portal.list_tokens(db, pid)}


@router.delete("/projects/{pid}/share-tokens/{token}")
def revoke_share_token(pid: str, token: str, db: Session = Depends(get_db),
                       _: str = Depends(require_role("editor"))):
    """Revoke a share token — access stops immediately (editor only)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    if not client_portal.revoke(db, pid, token):
        raise HTTPException(404, "token not found or already revoked")
    return {"revoked": True}


@router.get("/projects/{pid}/client-decisions")
def list_client_decisions(pid: str, limit: int = 500, db: Session = Depends(get_db),
                          _: str = Depends(require_role("editor"))):
    """PORTAL-TXN — the project's client-decision feed (approve/acknowledge/decline recorded through share
    tokens), newest first (editor only)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return {"decisions": client_portal.decisions_for_project(db, pid, limit)}


@router.post("/shared/{token}/decision")
def shared_decision(token: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """PUBLIC (no auth) — PORTAL-TXN: record a client decision through a live share token — a timestamped,
    token-stamped **approve / acknowledge / decline** on a shared item. NOT a payment and NOT an e-signature
    of record. Inputs are whitelisted + length-capped and each token carries a hard decision cap. Body:
    `{item_type, item_ref, action, client_name?, note?}`. Unknown/revoked token → 404."""
    try:
        return client_portal.record_decision(db, token, body.get("item_type"), body.get("item_ref"),
                                             body.get("action"), body.get("client_name"), body.get("note"))
    except KeyError:
        raise HTTPException(404, "not found") from None
    except ValueError as e:
        raise HTTPException(409 if "limit" in str(e) else 422, str(e)) from None


@router.get("/shared/{token}/digest")
def shared_digest(token: str, db: Session = Depends(get_db)):
    """PUBLIC (no auth) — the curated read-only project digest for a valid share token. High-level
    readiness only; no record-level data. An unknown or revoked token returns 404 (no enumeration)."""
    try:
        return client_portal.digest(db, token)
    except KeyError:
        raise HTTPException(404, "not found") from None


@router.get("/shared/{token}")
def shared_page(token: str, db: Session = Depends(get_db)):
    """PUBLIC (no auth) — a self-contained read-only HTML page rendering the share digest (the same
    curated readiness data as the .json digest). All values are HTML-escaped. Unknown/revoked → 404."""
    try:
        d = client_portal.digest(db, token)
    except KeyError:
        raise HTTPException(404, "not found") from None
    return Response(client_portal.to_html(d), media_type="text/html")
