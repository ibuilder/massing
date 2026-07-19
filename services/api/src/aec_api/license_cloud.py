"""CLOUD-BRIDGE — optional online licence validation against **massing.cloud**.

Offline-first: the tier recorded in Settings (`MASSING_LICENSE_TIER`) is authoritative on its own, so
the self-hosted app never *requires* a network call (matching the open-mode default and the other
feature-flagged bridges — cv_bridge, procurement_bridge, re_bridge). When the operator turns this on
(`MASSING_CLOUD_ONLINE=1` + a base URL + the shared secret), the app can ask massing.cloud to validate
the recorded key and return the authoritative entitlements; a successful check writes the validated tier
back to Settings so the entitlement gates ([[licensing]]) read a cloud-confirmed plan without a network
hop per request.

The shared secret is read from `settings_store` (`MASSING_CLOUD_SECRET`, a secret field — masked in the
Settings catalog, never returned by GET, never logged) — it is NEVER hardcoded in this repo.

Contract (this app → massing.cloud), mirrored by the massing.cloud WordPress plugin:

    POST  {MASSING_CLOUD_URL}/validate
    Headers: X-Massing-Secret: <MASSING_CLOUD_SECRET>   Content-Type: application/json
    Body:    {"key": "<licence key>", "instance": "<optional install id>", "app": "massing"}
    200:     {"valid": true,  "tier": "commercial", "seats": 5, "expires": "2027-01-01",
              "features": {...optional...}, "message": "..."}
      or     {"valid": false, "reason": "revoked|expired|unknown"}

The response `tier` must be one of licensing.TIER_ORDER; an unknown/absent tier falls back to "free".
Any transport/parse failure is reported as an offline result (never raises) — the caller keeps the
locally-recorded tier, so a massing.cloud outage can't lock a paying operator out of their own app.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from .net import validate_outbound_url

_DEFAULT_URL = "https://www.massing.cloud/wp-json/massing/v1"
_TIMEOUT = 15


def _get(key: str, default: str = "") -> str:
    from . import settings_store
    return (settings_store.get(key, default) or default).strip()


def base_url() -> str:
    return (_get("MASSING_CLOUD_URL") or _DEFAULT_URL).rstrip("/")


def _secret() -> str:
    return _get("MASSING_CLOUD_SECRET")


def online_enabled() -> bool:
    """Online validation is opt-in AND needs the secret configured (the URL has a sane default)."""
    return _get("MASSING_CLOUD_ONLINE", "0").lower() in ("1", "true", "yes", "on") and bool(_secret())


def status() -> dict[str, Any]:
    """Bridge status for the Settings UI — reports configuration WITHOUT ever exposing the secret."""
    return {
        "feature": "license_cloud",
        "online": online_enabled(),
        "url": base_url(),
        "secret_configured": bool(_secret()),
        "note": ("Online licence validation is ON — the app confirms the recorded key against "
                 "massing.cloud and stores the returned plan." if online_enabled() else
                 "Offline mode (default): the recorded plan is authoritative. Set MASSING_CLOUD_ONLINE=1 "
                 "and the shared secret to validate the key against massing.cloud."),
    }


# --- transport seam (monkeypatched in tests; no real network in the suite) --------------------------
def _http_json(url: str, secret: str, payload: dict) -> dict[str, Any]:
    validate_outbound_url(url, require_https=True, label="MASSING_CLOUD_URL")   # https-only, no file://
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "X-Massing-Secret": secret, "User-Agent": "Massing-App"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:   # noqa: S310 — url validated above
        return json.loads(resp.read().decode() or "{}")


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a massing.cloud response into a stable shape; an unknown tier degrades to 'free'."""
    from . import licensing
    tier = str(raw.get("tier") or "").strip().lower()
    if tier not in licensing.TIER_FEATURES:
        tier = "free"
    return {"valid": bool(raw.get("valid")), "tier": tier,
            "seats": raw.get("seats"), "expires": raw.get("expires"),
            "reason": raw.get("reason"), "message": raw.get("message")}


def validate(key: str, instance: str | None = None) -> dict[str, Any]:
    """Validate a licence key against massing.cloud. Best-effort: returns
    `{checked_online: True, valid, tier, seats, expires, reason}` on a reachable endpoint, or
    `{checked_online: False, error}` when disabled/unreachable/garbled — NEVER raises, so a cloud
    outage leaves the locally-recorded tier intact."""
    if not online_enabled():
        return {"checked_online": False, "error": "online validation disabled"}
    if not key:
        return {"checked_online": False, "error": "no licence key recorded"}
    url = f"{base_url()}/validate"
    try:
        raw = _http_json(url, _secret(), {"key": key, "instance": instance, "app": "massing"})
    except Exception as e:  # noqa: BLE001 — network/parse errors are an offline state, not a crash
        return {"checked_online": False, "error": f"{e.__class__.__name__}: {str(e)[:160]}"}
    if not isinstance(raw, dict):
        return {"checked_online": False, "error": "unexpected response (not a JSON object)"}
    return {"checked_online": True, **_normalize(raw)}


def check_and_apply(db, actor: str = "system") -> dict[str, Any]:
    """Validate the recorded licence key online and, on a valid result, WRITE the authoritative tier
    back to Settings (so the entitlement gates read a cloud-confirmed plan). Returns the check result
    plus `applied` / `tier_before` / `tier_after`. The local tier is never downgraded on an
    *unreachable* cloud (offline → no change); only an explicit `valid=false` verdict downgrades."""
    from . import audit, licensing, settings_store
    key = _get("MASSING_LICENSE_KEY")
    before = licensing.current_tier()
    res = validate(key)
    applied = False
    if res.get("checked_online"):
        if res.get("valid"):
            settings_store.set_value(db, "MASSING_LICENSE_TIER", res["tier"])
            applied = res["tier"] != before
        elif res.get("reason") in ("revoked", "expired", "unknown"):
            settings_store.set_value(db, "MASSING_LICENSE_TIER", "free")   # reachable cloud said "no"
            applied = before != "free"
    after = licensing.current_tier()
    audit.record(db, action="license.cloud_check", actor=actor, method="POST",
                 path="/license/cloud-check",
                 detail={"checked_online": res.get("checked_online"), "valid": res.get("valid"),
                         "tier_before": before, "tier_after": after, "applied": applied})
    db.commit()
    return {**res, "applied": applied, "tier_before": before, "tier_after": after}
