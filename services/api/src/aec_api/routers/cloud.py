"""CLOUD-SSO / CLOUD-LIBRARY routes — sign in through **massing.cloud** and read the user's library.

Two groups behind one module because they share a credential:

    GET  /auth/cloud/login       → 307 to the broker (PKCE S256; verifier sealed into a cookie)
    GET  /auth/cloud/callback    → exchange, link, mint this app's session, redirect into the app
    GET  /auth/cloud/status      → is cloud sign-in available / is this account linked / what it grants
    POST /auth/cloud/disconnect  → revoke at the broker and delete the link row
    POST /auth/cloud/refresh     → re-read userinfo (tier/role change picked up without a re-login)

    GET  /cloud/library/projects        → the user's vaults
    GET  /cloud/library/projects/{id}   → one vault
    GET  /cloud/library/models/{id}     → a model + its signed download URL

**Why the exchange is server-side.** The browser never sees the cloud tokens: they are the
credential for the Vault API and a refresh token is good for 30 days. Keeping them here also means
massing.cloud never has to CORS-allow this origin. PKCE needs no client secret, so nothing about
being a *public* client is compromised by doing the exchange from the server.

**Tier gate.** `has_library_access` is "any tier but free". A free user who is signed in gets a 402
naming the upgrade page rather than an empty list — an empty library and an ungranted one must not
look the same, which is the same rule as everywhere else in this codebase.

**Role gate.** Cloud `administrator`/`editor` → platform admin *here*, and only for this provider.
See `massing_cloud_auth.role_sync_enabled` for why that is a deliberate exception to the standing
"regular SSO users are never platform admins" rule in `routers/auth.py`.

**Two assumptions this rests on, written down because neither is enforced in code.**

*The broker's `email` is verified.* `_link_account` matches a cloud identity to a local account by
email on first link, so an unverified address would let someone claim another person's account.
massing.cloud creates its accounts through provider OIDC or its own registration and does not expose
an `email_verified` claim to check, so this is trust in a **first-party** identity provider, not an
oversight — but it is the load-bearing assumption behind email matching. If the broker ever federates
an IdP that does not verify addresses, this must become an explicit check.

*The cloud tokens are stored unencrypted.* `CloudIdentity.access_token` / `refresh_token` are
plaintext at rest, which matches how this codebase already stores `Connection.config` (DSN passwords,
vendor access tokens) — there is no at-rest encryption helper in `services/api/src` to use. Noted
rather than hidden: a 30-day first-party refresh token is a more valuable row than a vendor token, so
if secrets-at-rest is ever taken up, this table is the one to start from.
"""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import audit, auth
from .. import massing_cloud_auth as cloud
from .. import massing_cloud_vault as vault
from ..db import get_db
from ..models import CloudIdentity, User
from ..rbac import current_user, require_identified

router = APIRouter()

_PKCE_COOKIE = "mc_pkce"
# Refresh the access token this many seconds before it actually expires, so a long Vault call
# started just under the wire does not die mid-flight.
_REFRESH_SKEW = 120


def _cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https"


def _app_url() -> str:
    return os.environ.get("AEC_APP_URL", "/")


def _require_enabled() -> None:
    if not cloud.is_enabled():
        raise HTTPException(404, "massing.cloud sign-in is not enabled on this deployment")


# ── sign-in ───────────────────────────────────────────────────────────────────────────────────

@router.get("/auth/cloud/login")
def cloud_login(request: Request):
    """Start the PKCE flow. An opaque **flow id** is sealed into an HttpOnly cookie (never into
    `state`); the verifier is derived from it and never leaves this process."""
    _require_enabled()
    redirect_uri = str(request.url_for("cloud_callback"))
    # The cookie carries an opaque flow id; the verifier is DERIVED from it plus the server signing
    # key and never leaves this process. See massing_cloud_auth.verifier_for.
    flow_id = cloud.new_flow_id()
    verifier = cloud.verifier_for(flow_id)
    state = auth.create_oauth_state("massing-cloud")
    resp = RedirectResponse(cloud.authorize_url(redirect_uri, state, verifier), status_code=307)
    resp.set_cookie(
        _PKCE_COOKIE, auth.seal_pkce(flow_id, state),
        max_age=600, httponly=True, samesite="lax", path="/auth/cloud",
        secure=_cookie_secure(request))
    return resp


@router.get("/auth/cloud/callback", name="cloud_callback")
def cloud_callback(request: Request, code: str | None = None, state: str | None = None,
                   error: str | None = None, db: Session = Depends(get_db)):
    _require_enabled()
    if error:
        raise HTTPException(400, f"massing.cloud sign-in was refused: {error}")
    sealed = request.cookies.get(_PKCE_COOKIE) or ""
    if not code or not state or auth.verify_oauth_state(state) != "massing-cloud":
        raise HTTPException(400, "invalid callback (missing code or bad state)")
    flow_id = auth.open_pkce(sealed, state)
    if not flow_id:
        # Either the cookie is gone (browser blocked it / flow resumed in another browser) or it is
        # bound to a different attempt. Both are "start again", not "trust the code".
        raise HTTPException(400, "sign-in session expired — please start again")
    verifier = cloud.verifier_for(flow_id)

    redirect_uri = str(request.url_for("cloud_callback"))
    try:
        tok = cloud.exchange_code(code, verifier, redirect_uri)
    except Exception as e:
        raise HTTPException(502, "massing.cloud token exchange failed") from e
    access = str(tok.get("access_token") or "")
    if not access:
        raise HTTPException(502, "massing.cloud did not return an access token")
    try:
        info = cloud.fetch_userinfo(access)
    except Exception as e:
        raise HTTPException(502, "massing.cloud userinfo failed") from e

    email = str(info.get("email") or "").strip().lower()
    sub = str(info.get("sub") or "").strip()
    if not email or not sub:
        raise HTTPException(403, "massing.cloud did not return an identified account")

    username = _link_account(db, info, tok, access)
    resp = RedirectResponse(_app_url(), status_code=303)
    _set_session_cookie(resp, auth.create_token(username), request)
    resp.delete_cookie(_PKCE_COOKIE, path="/auth/cloud")
    return resp


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    """Mirror this app's own session token into the cookie the SSE layer needs (see routers/auth)."""
    response.set_cookie("aec_token", token, max_age=604800, httponly=False, samesite="lax",
                        path="/", secure=_cookie_secure(request))


def _link_account(db: Session, info: dict, tok: dict, access: str) -> str:
    """Find-or-create the local account for a broker identity and (re)write its cloud link.

    Returns the local username. Identity is resolved by the broker's `sub` first and by email
    second: `sub` is stable across an email change on massing.cloud, so resolving by email alone
    would silently fork one person into two accounts the first time they change their address."""
    sub = str(info.get("sub") or "").strip()
    email = str(info.get("email") or "").strip().lower()
    roles = cloud.roles_from_userinfo(info)
    cloud_tier = cloud.normalize_tier(info.get("tier"))
    is_admin = cloud.is_cloud_admin(roles)

    link = db.query(CloudIdentity).filter(CloudIdentity.cloud_sub == sub).one_or_none()
    username = link.username if link else email

    u = db.get(User, username)
    # Provenance snapshot, taken BEFORE role sync writes anything. On a first link this records
    # whether the account was already an admin without the cloud's help; on later logins we keep
    # what was recorded then, because the provenance of the original elevation does not change.
    was_local_admin = bool(link.local_admin_at_link) if link is not None else (
        u is not None and u.role == "admin")
    if u is None:
        if os.environ.get("AEC_OAUTH_NO_AUTOPROVISION") == "1":
            raise HTTPException(403, "no account for this cloud user — ask an admin to invite you first")
        u = User(username=username, password_hash="cloud!massing",  # unusable for password login
                 role="admin" if is_admin else "user", email=email,
                 tier=cloud.app_tier_for(cloud_tier))
        db.add(u)
        db.flush()
    else:
        if not u.email:
            u.email = email
        u.tier = cloud.app_tier_for(cloud_tier)
        # Role sync **may promote freely, and may only demote an elevation it granted.**
        #
        # `was_local_admin` is the whole rule. Without it the code cannot tell "admin because of
        # the cloud" from "admin before the cloud", and three separate lockouts followed from
        # exactly that gap — each one reproduced before being fixed:
        #
        #   1. first link demoted a pre-existing local admin (`link` is None here, `username` is
        #      just the email, so this branch is reached for accounts that were never cloud-linked);
        #   2. after a first-link-only guard, the SECOND sign-in demoted them instead — the lockout
        #      was delayed by one login, not prevented;
        #   3. `disconnect` demoted them on the way out (see `cloud_disconnect`).
        #
        # None of the three is hypothetical: `userinfo` ships no roles at all today, so `is_admin`
        # is ALWAYS False, and the bootstrap admin's username IS their email. Every one of them was
        # a guaranteed lockout in the default configuration, not an edge case.
        #
        # Note the consequence, which is intended: for a cloud-linked account that was NOT already
        # an admin, the site is authoritative — promoting it locally under "Manage users" will be
        # undone at the next sign-in. Set `MASSING_CLOUD_ROLE_SYNC=0` if that is not wanted.
        if cloud.role_sync_enabled():
            if is_admin:
                u.role = "admin"
            elif not was_local_admin:
                u.role = "user"
    if u.active is False:
        raise HTTPException(403, "account is deactivated")

    if link is None:
        link = db.get(CloudIdentity, username) or CloudIdentity(username=username, cloud_sub=sub)
        db.add(link)
    link.cloud_sub = sub
    link.cloud_email = email
    link.display_name = str(info.get("name") or "") or None
    link.avatar_url = str(info.get("avatar_url") or "") or None
    link.cloud_tier = cloud_tier
    link.cloud_roles = roles
    # Written on every sync, but the value is the FIRST-link snapshot carried forward (see above):
    # the provenance of the original elevation does not change because the user signed in again.
    link.local_admin_at_link = was_local_admin
    link.providers = info.get("providers") if isinstance(info.get("providers"), list) else []
    link.access_token = access
    link.refresh_token = str(tok.get("refresh_token") or "") or link.refresh_token
    link.expires_at = int(time.time()) + int(tok.get("expires_in") or 0)
    link.last_sync = _utcnow()

    audit.record(db, action="auth.cloud_login", actor=username, method="GET",
                 path="/auth/cloud/callback",
                 detail={"sub": sub, "tier": cloud_tier, "roles": roles, "admin": is_admin})
    db.commit()
    return username


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ── link state ────────────────────────────────────────────────────────────────────────────────

@router.get("/auth/cloud/status")
def cloud_status(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """What the UI needs to render the account chip and the library entry point.

    **Identify-only on purpose — this is the one cloud route an ANONYMOUS caller must reach.** The
    sign-in modal calls it while signed out to decide whether to offer "Continue with massing.cloud";
    gating it with `require_identified` would 401 exactly the caller it exists to serve, and the
    button would never appear. Safe because an anonymous or unlinked caller gets only
    `{enabled, linked: false, site_url}` — deployment configuration, no user data and never a token.
    Every route below that reads or mutates a *link* takes `require_identified`, and `test_global_authz`
    flags only mutating routes, so this read is outside that gate by its rule as well as by intent.
    """
    link = db.get(CloudIdentity, user) if user else None
    if link is None:
        return {"enabled": cloud.is_enabled(), "linked": False, "site_url": cloud.site_url()}
    tier = cloud.normalize_tier(link.cloud_tier)
    return {
        "enabled": cloud.is_enabled(),
        "linked": True,
        "site_url": cloud.site_url(),
        "sub": link.cloud_sub,
        "email": link.cloud_email,
        "name": link.display_name,
        "avatar_url": link.avatar_url,
        "tier": tier,
        "tier_label": _tier_label(tier),
        "roles": link.cloud_roles or [],
        "providers": link.providers or [],
        "is_admin": cloud.is_cloud_admin(list(link.cloud_roles or [])),
        "library_access": cloud.has_library_access(tier),
        "linked_at": link.linked_at,
        "last_sync": link.last_sync,
    }


def _tier_label(tier: str) -> str:
    from .. import licensing
    return licensing.TIER_LABEL.get(tier, tier.title())


@router.post("/auth/cloud/refresh")
def cloud_refresh_profile(db: Session = Depends(get_db), user: str = Depends(require_identified)):
    """Re-read `userinfo` and re-apply tier + role. Lets an upgrade or a role change take effect
    without making the user sign out and back in."""
    link = _linked_or_403(db, user)
    token = _fresh_access_token(db, link)
    try:
        info = cloud.fetch_userinfo(token)
    except Exception as e:
        raise HTTPException(502, "could not reach massing.cloud") from e
    roles = cloud.roles_from_userinfo(info)
    link.cloud_roles = roles
    link.cloud_tier = cloud.normalize_tier(info.get("tier"))
    link.display_name = str(info.get("name") or "") or link.display_name
    link.avatar_url = str(info.get("avatar_url") or "") or link.avatar_url
    link.last_sync = _utcnow()
    u = db.get(User, user)
    if u is not None:
        u.tier = cloud.app_tier_for(link.cloud_tier)
        # Same rule as `_link_account`: promote freely, demote only an elevation this path granted.
        # This site had the bug too — a plain two-way write here demoted a pre-existing local admin
        # the moment they hit "Refresh" in their profile.
        if cloud.role_sync_enabled():
            if cloud.is_cloud_admin(roles):
                u.role = "admin"
            elif not link.local_admin_at_link:
                u.role = "user"
    db.commit()
    return cloud_status(db=db, user=user)


@router.post("/auth/cloud/disconnect")
def cloud_disconnect(db: Session = Depends(get_db), user: str = Depends(require_identified)):
    """Unlink. Revokes at the broker best-effort, then deletes the row — the local account and its
    projects survive; only the cloud credential is destroyed."""
    link = db.get(CloudIdentity, user)
    if link is None:
        return {"ok": True, "linked": False}
    for tok in (link.access_token, link.refresh_token):
        if tok:
            cloud.revoke_token(tok)
    # Read the provenance BEFORE deleting the row — it is the only record of where the admin bit
    # came from, and after `db.delete` there is nothing left to ask.
    was_local_admin = bool(link.local_admin_at_link)
    db.delete(link)
    u = db.get(User, user)
    # An elevation this path GRANTED must not survive the link being removed — but an account that
    # was already an admin before it ever linked must keep what it had. The comment here used to
    # assert the first half while the code could not evaluate it, so a pre-existing local admin was
    # demoted by pressing "Disconnect" — the same lockout as the sign-in path, reachable by a user
    # doing exactly what the button is for. Caught in review; reproduced before fixing.
    if u is not None and cloud.role_sync_enabled() and u.role == "admin" and not was_local_admin:
        u.role = "user"
    audit.record(db, action="auth.cloud_disconnect", actor=user, method="POST",
                 path="/auth/cloud/disconnect", detail={})
    db.commit()
    return {"ok": True, "linked": False}


# ── the library ───────────────────────────────────────────────────────────────────────────────

def _linked_or_403(db: Session, user: str) -> CloudIdentity:
    link = db.get(CloudIdentity, user) if user else None
    if link is None:
        raise HTTPException(403, "this account is not linked to massing.cloud")
    return link


def _fresh_access_token(db: Session, link: CloudIdentity) -> str:
    """The access token, refreshed if it is at or near expiry. Refresh tokens rotate on use, so the
    new one is stored — dropping it would strand the link at the next refresh."""
    if link.expires_at and link.expires_at - _REFRESH_SKEW > int(time.time()) and link.access_token:
        return link.access_token
    if not link.refresh_token:
        if link.access_token:
            return link.access_token
        raise HTTPException(401, "massing.cloud session expired — sign in again")
    try:
        tok = cloud.refresh_token(link.refresh_token)
    except Exception as e:
        raise HTTPException(401, "massing.cloud session expired — sign in again") from e
    access = str(tok.get("access_token") or "")
    if not access:
        raise HTTPException(401, "massing.cloud session expired — sign in again")
    link.access_token = access
    link.refresh_token = str(tok.get("refresh_token") or "") or link.refresh_token
    link.expires_at = int(time.time()) + int(tok.get("expires_in") or 0)
    db.commit()
    return access


def _library_token(db: Session, user: str) -> str:
    """Linked + entitled, or the specific refusal that says which of the two failed."""
    link = _linked_or_403(db, user)
    tier = cloud.normalize_tier(link.cloud_tier)
    if not cloud.has_library_access(tier):
        raise HTTPException(402, "the cloud project library is included with any paid Massing plan — "
                                 f"upgrade at {cloud.site_url()}/pricing/")
    return _fresh_access_token(db, link)


def _vault(fn, *args):
    try:
        return fn(*args)
    except vault.VaultError as e:
        # Pass the site's own message through: a 409 names the plan limit that was hit, and
        # rewording it would lose the only part the user can act on.
        raise HTTPException(e.status if e.status in (401, 402, 403, 404, 409) else 502,
                            e.message) from e
    except Exception as e:
        raise HTTPException(502, "could not reach the massing.cloud library") from e


@router.get("/cloud/library/projects")
def library_projects(db: Session = Depends(get_db), user: str = Depends(require_identified)):
    token = _library_token(db, user)
    return {"projects": _vault(vault.list_projects, token)}


@router.get("/cloud/library/projects/{project_id}")
def library_project(project_id: str, db: Session = Depends(get_db), user: str = Depends(require_identified)):
    token = _library_token(db, user)
    return _vault(vault.get_project, token, project_id)


@router.get("/cloud/library/models/{model_id}")
def library_model(model_id: str, db: Session = Depends(get_db), user: str = Depends(require_identified)):
    """A model record plus its signed `download_url`.

    The URL is handed to the browser deliberately: it is short-lived, model-scoped, and carries its
    own token, so proxying the bytes through this app would add a hop without adding a check. It
    must be fetched **without** an Authorization header."""
    token = _library_token(db, user)
    return _vault(vault.get_model, token, model_id)
