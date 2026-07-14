"""SAML 2.0 SSO endpoints — SP metadata, login initiation (redirect to the IdP), and the Assertion
Consumer Service (ACS) that verifies the signed response and mints a Massing session. Mirrors the
OAuth flow in routers/auth.py: a verified email maps to a plain free-tier user (auto-provisioned
unless AEC_OAUTH_NO_AUTOPROVISION=1), honoring the same AEC_OAUTH_ALLOWED_DOMAINS gate. All the
cryptographic verification lives in saml.py.
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from .. import audit, auth, saml
from ..db import get_db
from ..models import User

router = APIRouter()


def _safe_relay(target: str) -> bool:
    """A RelayState/return-URL is only safe to redirect to if it's a same-site absolute path — one
    leading slash, and NOT a protocol-relative (`//host`) or backslash (`/\\host`) form that browsers
    resolve to another origin. Guards against open redirects."""
    return bool(target) and target.startswith("/") and not target.startswith(("//", "/\\"))


def _acs(request: Request) -> str:
    """Our ACS URL: the configured value (needed behind a reverse proxy where the internal URL
    differs from the public one), else computed from the request."""
    return saml.acs_url() or str(request.url_for("saml_acs"))


def _cookie(resp: Response, token: str, request: Request) -> None:
    """Set the session cookie (mirrors routers/auth._cookie; secure when the request is https)."""
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie("aec-token", token, httponly=True, secure=secure, samesite="lax", path="/")


@router.get("/auth/saml/metadata")
def saml_metadata(request: Request):
    """SP metadata XML to register with the IdP (entityID + ACS). Available whenever SAML is on."""
    if not saml.is_enabled():
        raise HTTPException(404, "SAML sign-in is not configured")
    return Response(content=saml.sp_metadata(_acs(request)), media_type="application/xml")


@router.get("/auth/saml/login")
def saml_login(request: Request, relay_state: str = ""):
    """Redirect to the IdP's SSO URL with a SAMLRequest (SP-initiated, HTTP-Redirect binding)."""
    if not saml.is_enabled():
        raise HTTPException(404, "SAML sign-in is not configured")
    url = saml.redirect_url(_acs(request), f"_{uuid.uuid4().hex}", saml._now(), relay_state)
    return RedirectResponse(url, status_code=307)


@router.post("/auth/saml/acs", name="saml_acs")
def saml_acs(request: Request, SAMLResponse: str = Form(...), RelayState: str = Form(default=""),
             db: Session = Depends(get_db)):
    """Assertion Consumer Service — verify the signed response, map the email to an account, mint the
    session, and return to the app. Any verification failure is a 403 (never leak crypto detail)."""
    if not saml.is_enabled():
        raise HTTPException(404, "SAML sign-in is not configured")
    try:
        ident = saml.verify_response(SAMLResponse, _acs(request))
    except saml.SamlError as e:
        raise HTTPException(403, f"SAML assertion rejected: {e}") from e

    email = (ident.email or ident.name_id or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(403, "SAML assertion did not carry an email identity")

    domains = [d.strip().lower().lstrip("@") for d in
               os.environ.get("AEC_OAUTH_ALLOWED_DOMAINS", "").split(",") if d.strip()]
    if domains and email.rsplit("@", 1)[-1] not in domains:
        raise HTTPException(403, "this email domain is not permitted to sign in")

    u = db.get(User, email)
    if u is None:
        if os.environ.get("AEC_OAUTH_NO_AUTOPROVISION") == "1":
            raise HTTPException(403, "no account for this email — ask an admin to invite you first")
        u = User(username=email, password_hash="saml!" + uuid.uuid4().hex,   # unusable password
                 role="user", email=email, tier="free", provisioned=True)
        db.add(u)
    elif not u.email:
        u.email = email
    if u.active is False:
        raise HTTPException(403, "account is deactivated")
    audit.record(db, action="auth.sso_login", actor=email, method="POST",
                 path="/auth/saml/acs", detail={"provider": "saml"})
    db.commit()

    # only allow a same-site absolute path — reject protocol-relative ("//evil.com") and
    # backslash ("/\evil.com") forms that browsers treat as cross-origin (open-redirect guard)
    dest = RelayState if _safe_relay(RelayState) else os.environ.get("AEC_APP_URL", "/")
    resp = RedirectResponse(dest, status_code=303)
    _cookie(resp, auth.create_token(email), request)
    return resp
