"""CLOUD-SSO — **massing.cloud as the identity broker** (OAuth2 Authorization Code + PKCE, RFC 8252).

The difference from [[oauth]]: `oauth.py` federates *directly* to Google/Microsoft/Procore/Autodesk,
which means this deployment holds four client secrets. Here massing.cloud holds them and we hold
none — we are a **public client** (`massing-desktop`, already registered site-side) authenticating
with PKCE/S256 and no secret at all. The user picks their IdP on massing.cloud; we only ever see the
broker. That is the whole point of the site's SSO plugin (massing.cloud docs 18/31).

    app → GET  {site}/massing-sso/authorize?...code_challenge=S256(verifier)   (system browser)
        ← 302  {redirect_uri}?code=…&state=…
    app → POST {site}/wp-json/massing-sso/v1/token    code + code_verifier  → access/refresh tokens
    app → GET  {site}/wp-json/massing-sso/v1/userinfo (Bearer)              → sub/name/email/avatar/tier
    app → POST {site}/wp-json/massing-sso/v1/revoke   on disconnect

**`redirect_uri` is our own callback**, which for the normal desktop/self-hosted install is already a
loopback URL (`http://127.0.0.1:8093/auth/cloud/callback`) — exactly what the `massing-desktop`
public client is registered to allow. A hosted deployment must register its https callback site-side.
Doing the exchange **server-side rather than in the browser** keeps the cloud refresh token out of
`localStorage` and avoids needing massing.cloud to CORS-allow this origin; PKCE means no secret is
required to do so, so nothing about the public-client model is bent.

**Roles.** `userinfo` on Massing SSO v1.1.0 returns `{sub, name, email, avatar_url, tier, providers}`
and **no role** — verified against the plugin source, not the docs. `roles_from_userinfo` therefore
reads several plausible spellings and returns `[]` when none are present, and `[]` never grants
anything (fail closed). The site can add roles in a few lines through its own `massing_sso_userinfo`
filter; until it does, cloud-driven admin simply never triggers and `AEC_ADMIN_EMAILS` remains the
way in. See `docs/internal/massing-cloud-sso.md`.

Stdlib only (urllib) + `safe_urlopen`, matching `oauth.py`: every hop is re-validated and pinned to
https, because a 302 would otherwise carry the code or the Bearer token somewhere else entirely.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import urllib.parse
import urllib.request
from typing import Any

from . import settings_store
from .net import safe_urlopen

_DEFAULT_SITE = "https://www.massing.cloud"
_DEFAULT_CLIENT_ID = "massing-desktop"
# WordPress ships `administrator` and `editor` as the two roles that can change site content. The
# user-facing rule is "admin or editor on massing.cloud ⇒ admin in the app"; `shop_manager` is
# deliberately NOT here (a store role, not an authoring one).
_DEFAULT_ADMIN_ROLES = "administrator,editor"
_TIMEOUT = 15
# The tier below which the cloud project library is not offered. massing.cloud tiers are
# free | home | commercial | enterprise — everything above `free` is a paying plan.
FREE_TIER = "free"


def _get(key: str, default: str = "") -> str:
    return (settings_store.get(key, default) or default).strip()


def _flag(key: str, default: str = "0") -> bool:
    return _get(key, default).lower() in ("1", "true", "yes", "on")


def site_url() -> str:
    """Base URL of the massing.cloud site (no trailing slash)."""
    return (_get("MASSING_CLOUD_SITE_URL") or _DEFAULT_SITE).rstrip("/")


def client_id() -> str:
    return _get("MASSING_CLOUD_SSO_CLIENT_ID") or _DEFAULT_CLIENT_ID


def is_enabled() -> bool:
    """Cloud sign-in is opt-in: an operator turns it on. Unlike the four direct IdPs there is no
    secret to configure, so the flag is the whole switch."""
    return _flag("MASSING_CLOUD_SSO_ENABLED", "0")


def role_sync_enabled() -> bool:
    """Whether a cloud `administrator`/`editor` role grants platform-admin in this app.

    On by default *for this provider only*. `routers/auth.py` states the standing rule — "Regular
    SSO users are never platform admins" — and that rule is deliberately kept for the generic IdPs
    in `oauth.py`: a Google account proves an email, not a relationship to this product. The
    massing.cloud broker is different in kind, because it is first-party: the role it reports is the
    role the operator granted on their own site. An operator who does not want that coupling sets
    `MASSING_CLOUD_ROLE_SYNC=0` and falls back to `AEC_ADMIN_EMAILS`."""
    return _flag("MASSING_CLOUD_ROLE_SYNC", "1")


def admin_roles() -> set[str]:
    raw = _get("MASSING_CLOUD_ADMIN_ROLES") or _DEFAULT_ADMIN_ROLES
    return {r.strip().lower() for r in raw.split(",") if r.strip()}


# ── PKCE ──────────────────────────────────────────────────────────────────────────────────────

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def new_flow_id() -> str:
    """A random, **non-secret** handle for one authorization attempt.

    This is what the browser carries between `/login` and `/callback`. It is not a credential:
    holding it reveals nothing and permits nothing, because the verifier is derived from it *and*
    the server signing key (see `verifier_for`)."""
    return _b64url(secrets.token_bytes(32))


def verifier_for(flow_id: str) -> str:
    """Derive this flow's PKCE `code_verifier` from the server signing key + the flow id.

    **The verifier is never stored and never leaves this process.** It is recomputed at callback
    time from the same two inputs, so nothing the browser holds contains secret material.

    The earlier design sealed the verifier itself into the cookie — signed, HttpOnly, `Path=/auth/
    cloud`, 600 s — which was defensible and is what most OAuth libraries do. CodeQL's
    `py/weak-sensitive-data-hashing` flagged it, and although the rule's own concern (never hash
    passwords with a fast digest) was a false positive here — SHA-256 inside HMAC is the correct
    primitive for authenticating a blob, and a slow KDF would be *wrong* — the alert pointed at a
    real question the rule does not ask: the verifier sat in a client-held value in recoverable
    form. Deriving it removes that entirely rather than arguing the alert away. Reading the cookie
    now yields an opaque id and no path to the verifier without `AEC_AUTH_SECRET`.

    43 characters of unreserved base64url, satisfying RFC 7636 §4.1 (43–128) at its floor."""
    from .auth import signing_key
    return _b64url(hmac.new(signing_key(), b"massing-cloud-pkce:" + flow_id.encode(),
                            hashlib.sha256).digest())


def challenge_for(verifier: str) -> str:
    """S256 challenge. `plain` is never offered — the broker requires S256 for the public client."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def authorize_url(redirect_uri: str, state: str, verifier: str, scope: str = "profile email") -> str:
    params = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "code_challenge": challenge_for(verifier),
        "code_challenge_method": "S256",
        "state": state,
        "scope": scope,
    }
    return f"{site_url()}/massing-sso/authorize?{urllib.parse.urlencode(params)}"


# ── broker endpoints ──────────────────────────────────────────────────────────────────────────

def _api(path: str) -> str:
    return f"{site_url()}/wp-json/massing-sso/v1{path}"


def _post_form(url: str, data: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    with safe_urlopen(req, timeout=_TIMEOUT, require_https=True, label="massing.cloud SSO token") as r:
        return json.loads(r.read().decode())


def _get_json(url: str, token: str, label: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json"})
    with safe_urlopen(req, timeout=_TIMEOUT, require_https=True, label=label) as r:
        return json.loads(r.read().decode())


def _exchange_code(code: str, verifier: str, redirect_uri: str) -> dict:
    return _post_form(_api("/token"), {
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "client_id": client_id(), "redirect_uri": redirect_uri})


def _refresh_token(refresh: str) -> dict:
    return _post_form(_api("/token"), {
        "grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id()})


def _fetch_userinfo(access_token: str) -> dict:
    return _get_json(_api("/userinfo"), access_token, "massing.cloud SSO userinfo")


def _revoke_token(token: str) -> None:
    try:
        _post_form(_api("/revoke"), {"token": token, "client_id": client_id()})
    except Exception:
        # A failed revoke must not block a local disconnect — the user asked to unlink, and leaving
        # them linked because the site was unreachable is the worse outcome. The token still expires.
        pass


# Overridable seams so the suite can exercise the whole callback without a live massing.cloud —
# the same recipe `oauth.py` uses (`exchange_code` / `fetch_userinfo` module attributes).
exchange_code = _exchange_code
refresh_token = _refresh_token
fetch_userinfo = _fetch_userinfo
revoke_token = _revoke_token


# ── identity shaping ──────────────────────────────────────────────────────────────────────────

def roles_from_userinfo(info: dict[str, Any]) -> list[str]:
    """Best-effort role extraction, lower-cased.

    Massing SSO v1.1.0 sends none of these keys, so this returns `[]` today and callers must treat
    `[]` as "no elevation" rather than "not an admin, probably". Several spellings are accepted so
    that whichever shape the site's `massing_sso_userinfo` filter adopts, this keeps working:
    `roles: [...]`, `role: "editor"`, or the OIDC-ish `wp_roles`."""
    out: list[str] = []
    for key in ("roles", "wp_roles", "role"):
        val = info.get(key)
        if isinstance(val, str):
            out.extend(v.strip() for v in val.split(",") if v.strip())
        elif isinstance(val, (list, tuple)):
            out.extend(str(v).strip() for v in val if str(v).strip())
    # de-duplicate, preserve order
    seen: set[str] = set()
    roles: list[str] = []
    for r in out:
        low = r.lower()
        if low and low not in seen:
            seen.add(low)
            roles.append(low)
    return roles


def is_cloud_admin(roles: list[str]) -> bool:
    """True when the cloud roles include one that should map to platform-admin here.

    Fails closed on an empty list, which is the live case until the site publishes roles."""
    if not role_sync_enabled():
        return False
    return bool(set(roles) & admin_roles())


def normalize_tier(raw: Any) -> str:
    """Coerce the broker's `tier` onto the **licence** vocabulary.

    There are two tier vocabularies in this app and picking the wrong one here is silently
    catastrophic: `licensing.TIER_ORDER` is `free|home|commercial|enterprise` — which is exactly what
    massing.cloud sends — while `tiers.TIERS` is `free|pro|enterprise`, the per-user entitlement
    seam on `User.tier`. Running a cloud tier through `tiers.normalize` maps **`commercial` → `free`**,
    because `commercial` is not in that tuple, and a paying customer would be told they have no
    library. So the cloud tier is normalised here against `licensing`, and converted for storage by
    `app_tier_for` below. Unknown or missing still degrades to `free` — an unreadable plan must never
    unlock a paid surface."""
    from . import licensing
    val = str(raw or "").strip().lower()
    return val if val in licensing.TIER_ORDER else FREE_TIER


def app_tier_for(cloud_tier: str) -> str:
    """Map a massing.cloud licence tier onto the `User.tier` entitlement vocabulary (`tiers.TIERS`).

    `home` and `commercial` are both paid plans with no separate representation in the three-value
    entitlement seam, so both land on `pro`; `enterprise` carries across by name."""
    return {"free": "free", "home": "pro", "commercial": "pro", "enterprise": "enterprise"}.get(
        normalize_tier(cloud_tier), "free")


def has_library_access(tier: str) -> bool:
    """The user's rule: *anything but free* gets their massing.cloud project library."""
    return normalize_tier(tier) != FREE_TIER
