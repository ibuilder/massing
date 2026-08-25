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
    """A RelayState/return-URL is only safe to redirect to if it is a same-site absolute path.

    The prefix checks are necessary and were not sufficient. Measured 2026-08-09 against the real
    function — it admitted FIVE off-site targets, all of which a browser resolves away from us:

        /\\tevil.example.com     TAB then host      ADMITTED
        /\\revil.example.com     CR then host       ADMITTED
        /\\n//evil.example.com   LF then //host     ADMITTED
        /\\t/evil.example.com    the known variant  ADMITTED
        /x:y/evil               colon first seg    ADMITTED

    **A browser strips TAB, CR and LF before resolving the URL**, so `/<TAB>/evil.example.com`
    becomes `//evil.example.com` — protocol-relative, off-site. Rejecting `//` and `/\\` therefore
    rejects the *spelling* of the attack and not the attack: the guard has to refuse the bytes,
    because it cannot see the form the browser will act on.

    A colon in the first path segment is refused for the same reason — `/x:y` is read as a scheme by
    some resolvers.

    Found by reading MassingCloud/massingplan's adversarial suite, which hit the same class from the
    other side: its guard was `startswith("/") and not startswith("//")` and `/\\evil.example.com`
    walked through it. We already had the backslash; we did not have the control characters. Two
    codebases, one bug class, neither complete alone.
    """
    if not target or not target.startswith("/"):
        return False
    if target.startswith(("//", "/\\")):
        return False
    # Refuse C0 controls and DEL anywhere — not just at the front. A browser removes them wherever
    # they sit, so their position is the attacker's choice and not a property we can rely on.
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in target):
        return False
    # Only the first PATH segment can be mistaken for a scheme. A colon in a query string or a
    # fragment is ordinary — `/search?q=a:b` is a real destination, and the first draft of this fix
    # refused it, caught by the paired "real destinations still work" test rather than by review.
    rest = target[1:]
    first_segment = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return ":" not in first_segment


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

    def _make_user() -> User:
        if os.environ.get("AEC_OAUTH_NO_AUTOPROVISION") == "1":
            raise HTTPException(403, "no account for this email — ask an admin to invite you first")
        return User(username=email, password_hash="saml!" + uuid.uuid4().hex,   # unusable password
                    role="user", email=email, tier="free", provisioned=True)

    # Same seeding race as the OAuth and cloud doors — see `auth.get_or_create_sso_user`.
    u, created = auth.get_or_create_sso_user(db, email, _make_user)
    if not created and not u.email:
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
