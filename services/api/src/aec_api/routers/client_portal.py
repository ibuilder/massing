"""CLIENT-PORTAL routes — share-token management (owner-authenticated) + the public read-only digest.

The management routes are gated to editors on the project; the public digest route takes only the token
(the token IS the credential) and exposes a curated readiness summary. An unknown/revoked token 404s.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import client_portal
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.post("/projects/{pid}/share-tokens")
def create_share_token(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                       actor: str = Depends(require_role("editor"))):
    """Mint a revocable, read-only share token for the project (owner/editor only). The returned token
    string is the shareable credential — anyone with it can read the project's readiness digest."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    try:
        return client_portal.create_token(db, pid, body.get("label"), actor)
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


@router.get("/shared/{token}/digest")
def shared_digest(token: str, db: Session = Depends(get_db)):
    """PUBLIC (no auth) — the curated read-only project digest for a valid share token. High-level
    readiness only; no record-level data. An unknown or revoked token returns 404 (no enumeration)."""
    try:
        return client_portal.digest(db, token)
    except KeyError:
        raise HTTPException(404, "not found") from None
