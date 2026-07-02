"""Server configuration store for integrations (AI / email / SSO). Admin-editable via the
Settings panel, persisted in the app_settings table and cached in-process. A configured value
overrides the matching environment variable, so deployments can still bake config via env.

Secrets are WRITE-ONLY over the API: the store keeps the value for server-side use, but the
GET endpoint never returns a secret — only whether it's configured.

Per-process cache: a write updates this worker + the DB; other workers refresh on their next
load (restart) — fine for single-worker/dev, note it for multi-worker (or call load() per read)."""
from __future__ import annotations

import os
import threading
from typing import Any

# admin-configurable integration settings (drives the Settings UI + validation)
CATALOG: list[dict[str, Any]] = [
    {"group": "Massing licence", "keys": [
        {"key": "MASSING_LICENSE_KEY", "label": "Licence key", "secret": True},
        {"key": "MASSING_LICENSE_TIER", "label": "Plan (free/home/commercial/enterprise)",
         "secret": False, "default": "free"},
        {"key": "MASSING_LICENSE_ENFORCE", "label": "Enforce plan limits (1/0) — off = open, licence optional",
         "secret": False, "default": "0"},
    ]},
    {"group": "AI assist (Draft RFI)", "keys": [
        {"key": "ANTHROPIC_API_KEY", "label": "Anthropic API key", "secret": True},
        {"key": "AEC_AI_MODEL", "label": "Model", "secret": False, "default": "claude-opus-4-8"},
    ]},
    {"group": "Email (SMTP digests)", "keys": [
        {"key": "AEC_SMTP_HOST", "label": "SMTP host", "secret": False},
        {"key": "AEC_SMTP_PORT", "label": "Port", "secret": False, "default": "587"},
        {"key": "AEC_SMTP_USER", "label": "Username", "secret": False},
        {"key": "AEC_SMTP_PASSWORD", "label": "Password", "secret": True},
        {"key": "AEC_SMTP_FROM", "label": "From address", "secret": False},
        {"key": "AEC_SMTP_TLS", "label": "STARTTLS (1/0)", "secret": False, "default": "1"},
    ]},
    {"group": "SSO — Google", "keys": [
        {"key": "AEC_OAUTH_GOOGLE_CLIENT_ID", "label": "Client ID", "secret": False},
        {"key": "AEC_OAUTH_GOOGLE_CLIENT_SECRET", "label": "Client secret", "secret": True},
    ]},
    {"group": "SSO — Microsoft (Entra)", "keys": [
        {"key": "AEC_OAUTH_MICROSOFT_CLIENT_ID", "label": "Client ID", "secret": False},
        {"key": "AEC_OAUTH_MICROSOFT_CLIENT_SECRET", "label": "Client secret", "secret": True},
        {"key": "AEC_OAUTH_MICROSOFT_TENANT", "label": "Tenant", "secret": False, "default": "common"},
    ]},
    {"group": "SSO — Procore", "keys": [
        {"key": "AEC_OAUTH_PROCORE_CLIENT_ID", "label": "Client ID", "secret": False},
        {"key": "AEC_OAUTH_PROCORE_CLIENT_SECRET", "label": "Client secret", "secret": True},
    ]},
    {"group": "Speckle (interoperability)", "keys": [
        {"key": "SPECKLE_SERVER", "label": "Server URL (e.g. https://speckle.yourco.com)", "secret": False},
        {"key": "SPECKLE_TOKEN", "label": "Personal access token", "secret": True},
    ]},
    {"group": "Autodesk APS (paid RVT-to-IFC bridge)", "keys": [
        {"key": "APS_CLIENT_ID", "label": "APS client ID", "secret": False},
        {"key": "APS_CLIENT_SECRET", "label": "APS client secret", "secret": True},
        {"key": "APS_DA_ACTIVITY", "label": "Design-Automation activity id", "secret": False},
    ]},
]
SECRET_KEYS = {k["key"] for g in CATALOG for k in g["keys"] if k.get("secret")}
ALL_KEYS = {k["key"] for g in CATALOG for k in g["keys"]}

_lock = threading.Lock()
_cache: dict[str, str] = {}


def load(db) -> None:
    """Populate the cache from the app_settings table (called at startup)."""
    from .models import AppSetting
    with _lock:
        _cache.clear()
        for s in db.query(AppSetting).all():
            if s.value is not None:
                _cache[s.key] = s.value


def get(key: str, default: str | None = None) -> str | None:
    """A configured value (DB) wins; else the environment; else the default."""
    with _lock:
        if key in _cache:
            return _cache[key]
    return os.environ.get(key, default)


def is_set(key: str) -> bool:
    return bool(get(key))


def set_value(db, key: str, value: str | None) -> None:
    """Upsert (or clear, if value is empty) a setting and refresh the cache."""
    from .models import AppSetting
    value = (value or "").strip() or None
    row = db.get(AppSetting, key)
    if value is None:
        if row:
            db.delete(row)
        with _lock:
            _cache.pop(key, None)
    else:
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        with _lock:
            _cache[key] = value


def public_catalog() -> list[dict[str, Any]]:
    """Catalog for the admin UI — secrets reported as configured/not, never their value."""
    out = []
    for grp in CATALOG:
        keys = []
        for k in grp["keys"]:
            entry = {"key": k["key"], "label": k["label"], "secret": bool(k.get("secret")),
                     "configured": is_set(k["key"])}
            if not k.get("secret"):
                entry["value"] = get(k["key"], k.get("default", "")) or ""
            keys.append(entry)
        out.append({"group": grp["group"], "keys": keys})
    return out
