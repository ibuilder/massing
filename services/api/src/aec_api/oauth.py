"""OAuth2 / OIDC social login — Google, Microsoft (Entra), Procore. Stdlib only (urllib).

A provider is *enabled* when its client id + secret are set in the environment:
  AEC_OAUTH_GOOGLE_CLIENT_ID / _SECRET
  AEC_OAUTH_MICROSOFT_CLIENT_ID / _SECRET   (+ optional AEC_OAUTH_MICROSOFT_TENANT, default "common")
  AEC_OAUTH_PROCORE_CLIENT_ID / _SECRET

The flow: /auth/oauth/{provider}/login → provider consent → /auth/oauth/{provider}/callback,
which exchanges the code, reads the verified email, find-or-creates the account, and mints the
normal aec_token (so SSO users join the same identity/RBAC layer as password accounts)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from . import settings_store


def _ms_tenant() -> str:
    return settings_store.get("AEC_OAUTH_MICROSOFT_TENANT", "common")


# email extractors normalize each provider's userinfo shape to an address
def _google_email(u: dict) -> str | None:
    return u.get("email")


def _ms_email(u: dict) -> str | None:
    return u.get("email") or u.get("preferred_username") or u.get("upn")


def _procore_email(u: dict) -> str | None:
    return u.get("login") or u.get("email_address") or u.get("email")


PROVIDERS: dict[str, dict[str, Any]] = {
    "google": {
        "label": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "email": _google_email,
    },
    "microsoft": {
        "label": "Microsoft",
        "authorize": lambda: f"https://login.microsoftonline.com/{_ms_tenant()}/oauth2/v2.0/authorize",
        "token": lambda: f"https://login.microsoftonline.com/{_ms_tenant()}/oauth2/v2.0/token",
        "userinfo": "https://graph.microsoft.com/oidc/userinfo",
        "scope": "openid email profile",
        "email": _ms_email,
    },
    "procore": {
        "label": "Procore",
        "authorize": "https://login.procore.com/oauth/authorize",
        "token": "https://login.procore.com/oauth/token",
        "userinfo": "https://api.procore.com/rest/v1.0/me",
        "scope": "",
        "email": _procore_email,
    },
}


def _env(provider: str, key: str) -> str | None:
    return settings_store.get(f"AEC_OAUTH_{provider.upper()}_{key}")


def client_id(provider: str) -> str | None:
    return _env(provider, "CLIENT_ID")


def _client_secret(provider: str) -> str | None:
    return _env(provider, "CLIENT_SECRET")


def _url(value: Any) -> str:
    return value() if callable(value) else value


def is_enabled(provider: str) -> bool:
    return provider in PROVIDERS and bool(client_id(provider)) and bool(_client_secret(provider))


def enabled_providers() -> list[dict[str, str]]:
    return [{"id": p, "label": PROVIDERS[p]["label"]} for p in PROVIDERS if is_enabled(p)]


def authorize_url(provider: str, redirect_uri: str, state: str) -> str:
    cfg = PROVIDERS[provider]
    params = {
        "client_id": client_id(provider),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "online"
    return f"{_url(cfg['authorize'])}?{urllib.parse.urlencode({k: v for k, v in params.items() if v})}"


def _post_json(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded",
        **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 — known provider endpoints
        return json.loads(r.read().decode())


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read().decode())


# overridable seams so tests can exercise the callback without real providers
exchange_code: Callable[[str, str, str], dict]
fetch_userinfo: Callable[[str, str], dict]


def _exchange_code(provider: str, code: str, redirect_uri: str) -> dict:
    cfg = PROVIDERS[provider]
    return _post_json(_url(cfg["token"]), {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id(provider), "client_secret": _client_secret(provider)})


def _fetch_userinfo(provider: str, access_token: str) -> dict:
    return _get_json(PROVIDERS[provider]["userinfo"], access_token)


exchange_code = _exchange_code
fetch_userinfo = _fetch_userinfo


def email_from_login(provider: str, code: str, redirect_uri: str) -> str | None:
    """Run the code→token→userinfo exchange and return the verified email (or None)."""
    tok = exchange_code(provider, code, redirect_uri)
    access = tok.get("access_token")
    if not access:
        return None
    info = fetch_userinfo(provider, access)
    email = PROVIDERS[provider]["email"](info)
    return email.strip().lower() if email else None
