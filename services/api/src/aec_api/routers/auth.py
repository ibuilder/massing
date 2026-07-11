"""Authentication endpoints: register / login / me. Issues signed bearer tokens that the
RBAC layer accepts as identity (see rbac.current_user). The first registered user bootstraps
as admin; after that, registering others requires an admin token."""
from __future__ import annotations

import os
import time
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, auth, oauth, rbac, settings_store, totp
from ..db import get_db
from ..models import AuditLog, User
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


# brute-force throttle: lock a username out after too many failed logins in a sliding window.
# In-process by default (good enough for the single-worker / desktop posture); when AEC_REDIS_URL
# is set the count is shared across workers via Redis (atomic INCR + EXPIRE), so the limit holds in
# a multi-process deployment. Redis is fail-open (any error falls back to the in-process counter) so
# the lockout infra can never lock everyone out or take login down. Cleared on a successful auth.
_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_MAX = int(os.environ.get("AEC_LOGIN_MAX_FAILS", "8"))
_LOGIN_WINDOW = int(os.environ.get("AEC_LOGIN_WINDOW_SEC", "300"))

_LOGIN_REDIS = None
_login_redis_url = os.environ.get("AEC_REDIS_URL", "").strip()
if _login_redis_url:
    try:                                          # lazy: redis is only a dependency when configured
        import redis as _redis
        _LOGIN_REDIS = _redis.Redis.from_url(_login_redis_url, socket_timeout=0.25,
                                             socket_connect_timeout=0.25)
    except Exception:                             # noqa: BLE001 — not installed / bad URL → in-process
        _LOGIN_REDIS = None


def _login_key(username: str) -> str:
    return f"login_fails:{(username or '').lower()}"


def _login_blocked(username: str) -> bool:
    if _LOGIN_REDIS is not None:
        try:
            n = _LOGIN_REDIS.get(_login_key(username))
            return n is not None and int(n) >= _LOGIN_MAX
        except Exception:                          # noqa: BLE001 — Redis hiccup → fall back, fail-open
            pass
    import time as _t
    now = _t.time()
    fails = [t for t in _LOGIN_FAILS.get(username, []) if now - t < _LOGIN_WINDOW]
    _LOGIN_FAILS[username] = fails
    return len(fails) >= _LOGIN_MAX


def _login_record_fail(username: str) -> None:
    if _LOGIN_REDIS is not None:
        try:
            key = _login_key(username)
            pipe = _LOGIN_REDIS.pipeline()
            pipe.incr(key)
            pipe.expire(key, _LOGIN_WINDOW)        # window starts at the first failure
            pipe.execute()
            return
        except Exception:                          # noqa: BLE001 — fall through to in-process on error
            pass
    import time as _t
    _LOGIN_FAILS.setdefault(username, []).append(_t.time())


def _login_clear(username: str) -> None:
    if _LOGIN_REDIS is not None:
        try:
            _LOGIN_REDIS.delete(_login_key(username))
        except Exception:                          # noqa: BLE001
            pass
    _LOGIN_FAILS.pop(username, None)


@router.post("/auth/login")
def login(request: Request, response: Response, username: str = Body(..., embed=True),
          password: str = Body(..., embed=True), db: Session = Depends(get_db)):
    if _login_blocked(username):
        raise HTTPException(429, "too many failed attempts — try again later")
    u = db.get(User, username)
    if not u or not auth.verify_password(password, u.password_hash):
        _login_record_fail(username)
        raise HTTPException(401, "invalid username or password")
    if u.active is False:
        raise HTTPException(403, "account is deactivated")
    _login_clear(username)                      # successful auth clears the counter (Redis + in-proc)
    if u.mfa_enabled:
        # password OK but MFA is on: don't mint a session yet — hand back a short-lived challenge
        # ticket; the client completes at /auth/mfa/verify with a TOTP or recovery code.
        return {"mfa_required": True, "mfa_token": auth.create_mfa_token(username), "username": username}
    return _issue_session(response, request, u)


def _issue_session(response: Response, request: Request, u: User) -> dict:
    """Mint a bearer token, set the httpOnly cookie (so SSE + direct-download links authenticate
    same-origin), and return the login payload. Shared by password login + MFA verify."""
    token = auth.create_token(u.username)
    _cookie(response, token, request)
    return {"token": token, "username": u.username, "role": u.role}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("aec_token", path="/")
    return {"ok": True}


# --- MFA (TOTP) ---------------------------------------------------------------
@router.post("/auth/mfa/verify")
def mfa_verify(request: Request, response: Response, mfa_token: str = Body(..., embed=True),
               code: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Login step 2: exchange the challenge ticket + a TOTP (or one-time recovery) code for a
    session. A used recovery code is burned."""
    sub = auth.verify_mfa_token(mfa_token)
    u = db.get(User, sub) if sub else None
    if not u or not u.mfa_enabled or not u.mfa_secret:
        raise HTTPException(401, "invalid or expired MFA challenge")
    if u.active is False:
        raise HTTPException(403, "account is deactivated")
    if totp.verify(u.mfa_secret, code):
        return _issue_session(response, request, u)
    # fall back to a one-time recovery code
    remaining = list(u.mfa_recovery or [])
    for h in remaining:
        if totp.check_recovery(code, h):
            remaining.remove(h)
            u.mfa_recovery = remaining
            audit.record(db, action="auth.mfa_recovery_used", actor=u.username, method="POST",
                         path="/auth/mfa/verify", detail={"remaining": len(remaining)})
            db.commit()
            return _issue_session(response, request, u)
    raise HTTPException(401, "invalid authentication code")


@router.get("/auth/mfa/status")
def mfa_status(db: Session = Depends(get_db), user: str = Depends(current_user)):
    u = db.get(User, user)
    return {"enabled": bool(u and u.mfa_enabled),
            "pending": bool(u and u.mfa_secret and not u.mfa_enabled),
            "recovery_remaining": len(u.mfa_recovery or []) if u else 0}


@router.post("/auth/mfa/setup")
def mfa_setup(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Begin enrollment: generate (and store, pending) a fresh secret; return it + an otpauth URI
    to show as a QR/manual key. Not active until confirmed at /auth/mfa/enable with a valid code."""
    u = db.get(User, user)
    if not u:
        raise HTTPException(401, "not authenticated")
    if u.mfa_enabled:
        raise HTTPException(409, "MFA is already enabled — disable it first to re-enroll")
    u.mfa_secret = totp.random_secret()
    db.commit()
    return {"secret": u.mfa_secret, "otpauth_uri": totp.provisioning_uri(u.mfa_secret, u.username)}


@router.post("/auth/mfa/enable")
def mfa_enable(code: str = Body(..., embed=True), db: Session = Depends(get_db),
               user: str = Depends(current_user)):
    """Confirm enrollment with a code from the authenticator; on success turn MFA on and return
    one-time recovery codes (shown once — the server stores only their hashes)."""
    u = db.get(User, user)
    if not u or not u.mfa_secret:
        raise HTTPException(400, "start enrollment at /auth/mfa/setup first")
    if u.mfa_enabled:
        raise HTTPException(409, "MFA is already enabled")
    if not totp.verify(u.mfa_secret, code):
        raise HTTPException(401, "code did not match — check the authenticator and try again")
    codes = totp.make_recovery_codes()
    u.mfa_enabled = True
    u.mfa_recovery = [totp.hash_recovery(c) for c in codes]
    audit.record(db, action="auth.mfa_enable", actor=user, method="POST", path="/auth/mfa/enable")
    db.commit()
    return {"enabled": True, "recovery_codes": codes}


@router.post("/auth/mfa/disable")
def mfa_disable(password: str = Body(..., embed=True), code: str = Body("", embed=True),
                db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Turn MFA off. Requires the account password AND a current TOTP/recovery code, so a merely
    hijacked session can't strip the second factor."""
    u = db.get(User, user)
    if not u:
        raise HTTPException(401, "not authenticated")
    if not auth.verify_password(password, u.password_hash):
        raise HTTPException(403, "password is incorrect")
    if u.mfa_enabled:
        ok = totp.verify(u.mfa_secret or "", code) or \
            any(totp.check_recovery(code, h) for h in (u.mfa_recovery or []))
        if not ok:
            raise HTTPException(401, "a valid authentication code is required to disable MFA")
    u.mfa_enabled = None
    u.mfa_secret = None
    u.mfa_recovery = None
    audit.record(db, action="auth.mfa_disable", actor=user, method="POST", path="/auth/mfa/disable")
    db.commit()
    return {"enabled": False}


# --- OAuth / SSO (Google, Microsoft, Procore) ---------------------------------
@router.get("/auth/providers")
def auth_providers():
    """Enabled SSO providers (those with client id + secret configured) — drives the login UI."""
    return {"providers": oauth.enabled_providers()}


def _cookie_secure(request: Request) -> bool:
    """Mark the auth cookie Secure over HTTPS (incl. behind a TLS-terminating proxy) or when the
    operator forces it. Off for plain-http local/dev so the cookie still works there."""
    if os.environ.get("AEC_COOKIE_SECURE") == "1":
        return True
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie("aec_token", token, httponly=True, samesite="lax",
                        secure=_cookie_secure(request), max_age=7 * 24 * 3600, path="/")


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

    # Enterprise gate: only self-provision accounts for allowed email domains. Without an allowlist,
    # any verified email at an enabled provider could create an account (and, with cross-tenant reads
    # closed, still see only its own projects — but provisioning itself should be controlled).
    import os as _os
    _domains = [d.strip().lower().lstrip("@") for d in
                _os.environ.get("AEC_OAUTH_ALLOWED_DOMAINS", "").split(",") if d.strip()]
    _dom = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    if _domains and _dom not in _domains:
        raise HTTPException(403, "this email domain is not permitted to sign in")

    u = db.get(User, email)
    if u is None:
        if _os.environ.get("AEC_OAUTH_NO_AUTOPROVISION") == "1":
            raise HTTPException(403, "no account for this email — ask an admin to invite you first")
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
    _cookie(resp, auth.create_token(email), request)
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
def change_password(request: Request, response: Response,
                    current: str = Body(..., embed=True), new: str = Body(..., embed=True),
                    db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Change your own password (requires the current one). Rotating the password revokes every
    other outstanding session (bumps token_epoch); a fresh token is issued so the current tab
    stays signed in."""
    u = db.get(User, user)
    if not u:
        raise HTTPException(401, "not authenticated")
    if not auth.verify_password(current, u.password_hash):
        raise HTTPException(403, "current password is incorrect")
    if len(new) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    u.password_hash = auth.hash_password(new)
    u.token_epoch = int(time.time())            # revoke all sessions issued before now
    audit.record(db, action="auth.password_change", actor=user, method="POST", path="/auth/password")
    db.commit()
    token = auth.create_token(user)             # issued now → passes the epoch check, keeps this tab in
    _cookie(response, token, request)
    return {"ok": True, "token": token}


@router.post("/auth/logout-all")
def logout_all(request: Request, response: Response,
               db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Sign out everywhere: revoke every outstanding session for the caller (bump token_epoch),
    then re-mint the current session so this tab stays in. Use after a suspected token leak."""
    u = db.get(User, user)
    if not u:
        raise HTTPException(401, "not authenticated")
    u.token_epoch = int(time.time())
    audit.record(db, action="auth.logout_all", actor=user, method="POST", path="/auth/logout-all")
    db.commit()
    token = auth.create_token(user)
    _cookie(response, token, request)
    return {"ok": True, "token": token}


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
    u.token_epoch = int(time.time())            # an admin reset revokes the user's live sessions
    audit.record(db, action="user.password_reset", actor=admin.username, method="POST",
                 path=f"/auth/users/{username}/password", detail={"username": username})
    db.commit()
    return {"ok": True}


@router.post("/auth/users/{username}/revoke-sessions")
def revoke_sessions(username: str, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin_user)):
    """Admin: force-revoke all of a user's outstanding tokens (e.g. offboarding / lost device).
    They must sign in again; deactivating the account (active=false) blocks re-login entirely."""
    u = db.get(User, username)
    if not u:
        raise HTTPException(404, "no such user")
    u.token_epoch = int(time.time())
    audit.record(db, action="user.revoke_sessions", actor=admin.username, method="POST",
                 path=f"/auth/users/{username}/revoke-sessions", detail={"username": username})
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
    # validate the Massing licence key format (empty clears it; non-empty must be MASS-XXXX-XXXX-XXXX-XXXX)
    from .. import licensing
    lk = values.get("MASSING_LICENSE_KEY")
    if lk and not licensing.valid_key_format(lk):
        raise HTTPException(400, "invalid licence key — expected MASS-XXXX-XXXX-XXXX-XXXX")
    lt = values.get("MASSING_LICENSE_TIER")
    if lt and lt.strip().lower() not in licensing.TIER_FEATURES:
        raise HTTPException(400, f"invalid plan — choose one of: {', '.join(licensing.TIER_ORDER)}")
    for k, v in values.items():
        settings_store.set_value(db, k, None if v is None else str(v))
    audit.record(db, action="settings.update", actor=admin.username, method="PUT",
                 path="/settings/integrations", detail={"keys": sorted(values)})  # keys only — no secrets
    db.commit()
    return {"groups": settings_store.public_catalog()}


@router.post("/settings/integrations/test")
def test_integration(body: dict = Body(...), _: User = Depends(require_admin_user)):
    """Live 'Test connection' for one integration group (by its catalog name) → {ok, message}.
    Gives a non-technical admin instant confirmation a key actually works."""
    from .. import conntest
    group = (body or {}).get("group") or ""
    if group not in {g["group"] for g in settings_store.CATALOG}:
        raise HTTPException(400, "unknown integration group")
    return conntest.test_group(group)


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


@router.get("/webhooks/deliveries")
def webhook_deliveries(limit: int = Query(100, ge=1, le=500), _: User = Depends(require_admin_user)):
    """Recent outbound-webhook delivery attempts (newest first) — url, event, ok, status, attempts,
    error — plus whether HMAC signing is configured. Process-local ring; for 'did my hook fire?'."""
    from .. import webhooks
    return {"signing_enabled": bool(webhooks._secret()),
            "configured_urls": len(webhooks._urls()),
            "deliveries": webhooks.recent(limit)}


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
    u.token_epoch = int(time.time())            # a password reset revokes any live sessions
    db.commit()
    return {"ok": True, "username": u.username}
