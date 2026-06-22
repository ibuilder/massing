"""Authentication endpoints: register / login / me. Issues signed bearer tokens that the
RBAC layer accepts as identity (see rbac.current_user). The first registered user bootstraps
as admin; after that, registering others requires an admin token."""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, auth, oauth, settings_store
from ..db import get_db
from ..models import AuditLog, User
from .. import rbac
from ..rbac import current_user

router = APIRouter()


def _platform_admin_emails() -> set[str]:
    """Ops-controlled platform admins for the cloud build (no in-app admin tier for end users).
    Set AEC_ADMIN_EMAILS to a comma-separated list of usernames/emails who may touch platform
    Settings / audit. Lower-cased for case-insensitive match."""
    raw = os.environ.get("AEC_ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _is_platform_admin(u: User | None) -> bool:
    """A user is a platform admin if listed in AEC_ADMIN_EMAILS, or (back-compat) carries the
    legacy global `admin` role. Regular SSO users are never platform admins."""
    if u is None:
        return False
    allow = _platform_admin_emails()
    if (u.username or "").lower() in allow or (u.email or "").lower() in allow:
        return True
    return u.role == "admin"


def require_admin_user(db: Session = Depends(get_db), user: str = Depends(current_user)) -> User:
    """Gate platform settings / audit / user-management. The cloud product has **no admin tier
    for end users** — these are ops endpoints: open in single-operator local mode, otherwise
    allowed for AEC_ADMIN_EMAILS (or a legacy `admin` account for back-compat)."""
    if rbac.LOCAL_MODE:
        return User(username="local", password_hash="", role="admin", active=True)
    u = db.get(User, user)
    if not _is_platform_admin(u):
        raise HTTPException(403, "platform-admin access required (set AEC_ADMIN_EMAILS)")
    return u


def _other_active_admins(db: Session, exclude: str) -> int:
    """Count active admins other than `exclude` — used to prevent locking out the last one."""
    return (db.query(User)
            .filter(User.role == "admin", User.active.isnot(False), User.username != exclude)
            .count())


def _public(u: User) -> dict:
    return {"username": u.username, "role": u.role, "active": u.active is not False,
            "email": u.email, "created_at": u.created_at}


@router.post("/auth/register", status_code=201)
def register(username: str = Body(..., embed=True), password: str = Body(..., embed=True),
             role: str = Body("user", embed=True), authorization: str | None = Header(default=None),
             db: Session = Depends(get_db)):
    if db.query(User).count() == 0:
        role = "admin"                       # bootstrap: the first account is admin
    else:
        tok = authorization[7:] if (authorization or "").startswith("Bearer ") else ""
        sub = auth.verify_token(tok)
        admin = db.get(User, sub) if sub else None
        if not admin or admin.role != "admin":
            raise HTTPException(403, "an admin token is required to register users")
        if role not in ("admin", "user"):
            raise HTTPException(400, "role must be admin or user")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if db.get(User, username):
        raise HTTPException(409, "username already taken")
    db.add(User(username=username, password_hash=auth.hash_password(password), role=role))
    db.commit()
    return {"username": username, "role": role}


@router.post("/auth/login")
def login(response: Response, username: str = Body(..., embed=True),
          password: str = Body(..., embed=True), db: Session = Depends(get_db)):
    u = db.get(User, username)
    if not u or not auth.verify_password(password, u.password_hash):
        raise HTTPException(401, "invalid username or password")
    if u.active is False:
        raise HTTPException(403, "account is deactivated")
    token = auth.create_token(username)
    # httpOnly cookie so SSE + direct-download links (which can't set a header) authenticate
    # same-origin (via the /api proxy in prod). Fetches use the token in the body for the header.
    response.set_cookie("aec_token", token, httponly=True, samesite="lax",
                        max_age=7 * 24 * 3600, path="/")
    return {"token": token, "username": username, "role": u.role}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("aec_token", path="/")
    return {"ok": True}


# --- OAuth / SSO (Google, Microsoft, Procore) ---------------------------------
@router.get("/auth/providers")
def auth_providers():
    """Enabled SSO providers (those with client id + secret configured) — drives the login UI."""
    return {"providers": oauth.enabled_providers()}


def _cookie(response: Response, token: str) -> None:
    response.set_cookie("aec_token", token, httponly=True, samesite="lax",
                        max_age=7 * 24 * 3600, path="/")


@router.get("/auth/oauth/{provider}/login")
def oauth_login(provider: str, request: Request):
    """Redirect to the provider's consent screen."""
    if not oauth.is_enabled(provider):
        raise HTTPException(404, f"{provider} sign-in is not configured")
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    state = auth.create_oauth_state(provider)
    return RedirectResponse(oauth.authorize_url(provider, redirect_uri, state), status_code=307)


@router.get("/auth/oauth/{provider}/callback", name="oauth_callback")
def oauth_callback(provider: str, request: Request, code: str | None = None,
                   state: str | None = None, db: Session = Depends(get_db)):
    """Exchange the code, map the verified email to an account, mint the session, and return
    to the app. SSO accounts are always plain free-tier users (no admin tier for end users)."""
    if not oauth.is_enabled(provider):
        raise HTTPException(404, f"{provider} sign-in is not configured")
    if not code or auth.verify_oauth_state(state or "") != provider:
        raise HTTPException(400, "invalid oauth callback (missing code or bad state)")
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    try:
        email = oauth.email_from_login(provider, code, redirect_uri)
    except Exception:
        raise HTTPException(502, "oauth provider exchange failed")
    if not email:
        raise HTTPException(403, "provider did not return a verified email")

    u = db.get(User, email)
    if u is None:
        # SSO accounts are always plain users — no admin tier for end users. Platform admins are
        # ops, set via AEC_ADMIN_EMAILS. Free tier by default (entitlements seam).
        u = User(username=email, password_hash="oauth!" + provider,  # unusable for password login
                 role="user", email=email, tier="free")
        db.add(u)
    elif not u.email:
        u.email = email
    if u.active is False:
        raise HTTPException(403, "account is deactivated")
    audit.record(db, action="auth.sso_login", actor=email, method="GET",
                 path=f"/auth/oauth/{provider}/callback", detail={"provider": provider})
    db.commit()
    resp = RedirectResponse(os.environ.get("AEC_APP_URL", "/"), status_code=303)
    _cookie(resp, auth.create_token(email))
    return resp


@router.get("/auth/me")
def me(db: Session = Depends(get_db), user: str = Depends(current_user)):
    from .. import entitlements
    u = db.get(User, user)
    tier = entitlements.normalize(u.tier if u else None)
    return {"username": user, "role": (u.role if u else None), "authenticated": u is not None,
            "tier": tier, "features": entitlements.features_for(tier),
            "platform_admin": _is_platform_admin(u)}


# --- self-service -------------------------------------------------------------
@router.post("/auth/password")
def change_password(current: str = Body(..., embed=True), new: str = Body(..., embed=True),
                    db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Change your own password (requires the current one)."""
    u = db.get(User, user)
    if not u:
        raise HTTPException(401, "not authenticated")
    if not auth.verify_password(current, u.password_hash):
        raise HTTPException(403, "current password is incorrect")
    if len(new) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    u.password_hash = auth.hash_password(new)
    db.commit()
    return {"ok": True}


# --- admin: user management ---------------------------------------------------
class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    email: str | None = None


@router.get("/auth/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    return [_public(u) for u in db.query(User).order_by(User.created_at).all()]


@router.post("/auth/users", status_code=201)
def create_user(username: str = Body(..., embed=True), password: str = Body(..., embed=True),
                role: str = Body("user", embed=True), email: str | None = Body(None, embed=True),
                db: Session = Depends(get_db), admin: User = Depends(require_admin_user)):
    """Admin-created account (the open path after bootstrap; /auth/register stays for the
    very first user)."""
    if role not in ("admin", "user"):
        raise HTTPException(400, "role must be admin or user")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if db.get(User, username):
        raise HTTPException(409, "username already taken")
    db.add(User(username=username, password_hash=auth.hash_password(password), role=role, email=email))
    audit.record(db, action="user.create", actor=admin.username, method="POST",
                 path="/auth/users", detail={"username": username, "role": role})
    db.commit()
    return _public(db.get(User, username))


@router.patch("/auth/users/{username}")
def update_user(username: str, body: UserPatch, db: Session = Depends(get_db),
                admin: User = Depends(require_admin_user)):
    """Change a user's role and/or activate/deactivate them. Won't lock out the last admin."""
    u = db.get(User, username)
    if not u:
        raise HTTPException(404, "no such user")
    demoting = body.role is not None and body.role != "admin"
    deactivating = body.active is False
    if u.role == "admin" and (demoting or deactivating) and _other_active_admins(db, username) == 0:
        raise HTTPException(400, "cannot remove the last active admin")
    if body.role is not None:
        if body.role not in ("admin", "user"):
            raise HTTPException(400, "role must be admin or user")
        u.role = body.role
    if body.active is not None:
        u.active = body.active
    if body.email is not None:
        u.email = body.email or None
    audit.record(db, action="user.update", actor=admin.username, method="PATCH",
                 path=f"/auth/users/{username}",
                 detail={"username": username, "role": body.role, "active": body.active})
    db.commit()
    return _public(u)


@router.post("/auth/users/{username}/password")
def reset_password(username: str, password: str = Body(..., embed=True),
                   db: Session = Depends(get_db), admin: User = Depends(require_admin_user)):
    """Admin reset of another user's password."""
    u = db.get(User, username)
    if not u:
        raise HTTPException(404, "no such user")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    u.password_hash = auth.hash_password(password)
    audit.record(db, action="user.password_reset", actor=admin.username, method="POST",
                 path=f"/auth/users/{username}/password", detail={"username": username})
    db.commit()
    return {"ok": True}


@router.post("/auth/users/{username}/reset-token", status_code=201)
def issue_reset_token(username: str, db: Session = Depends(get_db),
                      _: User = Depends(require_admin_user)):
    """Admin issues a single-use, 1-hour reset token for a user to set their own password
    (no email infra needed — hand the token to the user). The token can't be used as a
    bearer token and is invalidated once the password changes."""
    u = db.get(User, username)
    if not u:
        raise HTTPException(404, "no such user")
    return {"username": username, "reset_token": auth.create_reset_token(username, u.password_hash),
            "expires_in": 3600}


# --- admin: integration settings (AI / email / SSO keys) ----------------------
@router.get("/settings/integrations")
def get_integrations(_: User = Depends(require_admin_user)):
    """Integration config for the Settings panel. Secret values are never returned — only
    whether each is configured."""
    return {"groups": settings_store.public_catalog()}


@router.put("/settings/integrations")
def put_integrations(values: dict = Body(..., embed=True), db: Session = Depends(get_db),
                     admin: User = Depends(require_admin_user)):
    """Set/clear integration settings. A value here overrides the matching env var; an empty
    string clears it. Keys are validated against the catalog; secret values are not echoed back."""
    unknown = [k for k in values if k not in settings_store.ALL_KEYS]
    if unknown:
        raise HTTPException(400, f"unknown setting(s): {unknown}")
    for k, v in values.items():
        settings_store.set_value(db, k, None if v is None else str(v))
    audit.record(db, action="settings.update", actor=admin.username, method="PUT",
                 path="/settings/integrations", detail={"keys": sorted(values)})  # keys only — no secrets
    db.commit()
    return {"groups": settings_store.public_catalog()}


@router.get("/audit")
def audit_log(action: str | None = Query(None), actor: str | None = Query(None),
              since: str | None = Query(None), limit: int = Query(100, ge=1, le=500),
              offset: int = Query(0, ge=0), db: Session = Depends(get_db),
              _: User = Depends(require_admin_user)):
    """Admin read of the audit trail, newest first. Filter by action/actor substring and a
    `since` ISO timestamp."""
    q = db.query(AuditLog).order_by(AuditLog.ts.desc())
    if action:
        q = q.filter(AuditLog.action.contains(action))
    if actor:
        q = q.filter(AuditLog.actor.contains(actor))
    if since:
        try:
            q = q.filter(AuditLog.ts >= datetime.fromisoformat(since))
        except ValueError:
            raise HTTPException(400, "since must be an ISO timestamp")
    rows = q.offset(offset).limit(limit).all()
    return [{"id": r.id, "ts": r.ts, "actor": r.actor, "action": r.action, "method": r.method,
             "path": r.path, "topic_id": r.topic_id, "detail": r.detail} for r in rows]


@router.post("/auth/reset")
def reset_with_token(token: str = Body(..., embed=True), new: str = Body(..., embed=True),
                     db: Session = Depends(get_db)):
    """Unauthenticated: set a new password using a reset token (the token is the credential)."""
    if len(new) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    # the token carries the subject; verify it against that account's current password hash
    sub = auth.token_subject(token)
    u = db.get(User, sub) if sub else None
    if not u or not auth.verify_reset_token(token, u.password_hash):
        raise HTTPException(403, "invalid or expired reset token")
    u.password_hash = auth.hash_password(new)
    db.commit()
    return {"ok": True, "username": u.username}
