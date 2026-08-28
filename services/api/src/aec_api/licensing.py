"""Massing licensing — records the workspace's Massing licence key + plan tier and exposes the
per-tier feature entitlements the rest of the app gates on. Pure/std-lib.

Plans (see https://www.massing.cloud/docs/): Free · Home · Commercial · Enterprise. A key looks like
`MASS-XXXX-XXXX-XXXX-XXXX`. The authoritative entitlement is provisioned by massing.cloud at purchase;
in the self-hosted app the admin records the key + tier under Settings (offline activation), and an
optional online check can be wired later (feature-flagged, like the other bridges). The key/tier are
stored via settings_store (`MASSING_LICENSE_KEY` secret, `MASSING_LICENSE_TIER`)."""
from __future__ import annotations

import re
from typing import Any

KEY_RE = re.compile(r"^MASS-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

# ordered cheapest -> richest; each tier is a superset of the previous
TIER_ORDER = ["free", "home", "commercial", "enterprise"]
TIER_LABEL = {"free": "Free", "home": "Home", "commercial": "Commercial", "enterprise": "Enterprise"}

# feature entitlements per tier (cumulative). Export formats + capability flags per the docs.
_BASE_EXPORTS = ["png", "gltf", "glb", "pdf", "obj", "dxf"]   # Home and up (glb = binary glTF)
# openBIM data-out formats (IFC + the IFC5/ifcJSON write path) — the interchange the paid tiers unlock
_OPENBIM_EXPORTS = ["ifc", "ifcx", "rvt"]
TIER_FEATURES: dict[str, dict[str, Any]] = {
    "free": {"exports": [], "api_access": False, "sso": False, "navisworks": False},
    "home": {"exports": list(_BASE_EXPORTS), "api_access": False, "sso": False, "navisworks": False},
    "commercial": {"exports": _BASE_EXPORTS + _OPENBIM_EXPORTS, "api_access": True, "sso": False,
                   "navisworks": False},
    "enterprise": {"exports": _BASE_EXPORTS + _OPENBIM_EXPORTS + ["nwd"], "api_access": True,
                   "sso": True, "navisworks": True},
}


def enforcement_enabled():
    """Whether tier entitlements are *enforced*. OFF by default — the app stays fully open and a
    licence is optional (no registration required) until the operator flips MASSING_LICENSE_ENFORCE on.
    Set once the activation/seat infrastructure is ready."""
    from . import settings_store
    return (settings_store.get("MASSING_LICENSE_ENFORCE", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def normalize_key(key: str | None) -> str:
    return (key or "").strip().upper()


def valid_key_format(key: str | None) -> bool:
    return bool(KEY_RE.match(normalize_key(key)))


def _mask(key: str) -> str:
    k = normalize_key(key)
    if not valid_key_format(k):
        return ""
    return "MASS-****-****-****-" + k.rsplit("-", 1)[-1]


def current_tier() -> str:
    """The recorded plan tier (defaults to free). Read from settings_store / env."""
    from . import settings_store
    t = (settings_store.get("MASSING_LICENSE_TIER", "free") or "free").strip().lower()
    return t if t in TIER_FEATURES else "free"


def _key() -> str:
    from . import settings_store
    return normalize_key(settings_store.get("MASSING_LICENSE_KEY"))


def features(tier: str | None = None) -> dict[str, Any]:
    return dict(TIER_FEATURES.get((tier or current_tier()), TIER_FEATURES["free"]))


def allows(feature: str, tier: str | None = None) -> bool:
    """True if the capability is permitted. When enforcement is OFF (default) everything is allowed —
    a licence is optional. When ON, gate on the (current or given) tier's boolean entitlement."""
    if tier is None and not enforcement_enabled():
        return True
    return bool(features(tier).get(feature, False))


def allows_export(fmt: str, tier: str | None = None) -> bool:
    if tier is None and not enforcement_enabled():
        return True
    return fmt.lower() in features(tier).get("exports", [])


def min_tier_for(feature: str) -> str | None:
    """Label of the cheapest tier whose entitlements include `feature`, or None if no tier grants it.

    Derived from TIER_FEATURES rather than hand-listed. The two dicts this replaces were a second copy
    of the matrix and were INCOMPLETE, which reached users: `_EXPORT_MIN_TIER` named only the openBIM
    formats, so every Home-tier export fell through to a `"a higher"` default and the 402 read
    *"PNG export requires the Massing a higher plan (or higher)"* — for png/pdf/dxf/obj/gltf/glb, the
    most common refusal a Free-tier workspace would ever see. A duplicated derivation is where the
    unmaintained half hides; there is now one source for what a tier unlocks."""
    for t in TIER_ORDER:
        if TIER_FEATURES[t].get(feature):
            return TIER_LABEL[t]
    return None


def min_tier_for_export(fmt: str) -> str | None:
    """Label of the cheapest tier that can export `fmt`, or None if no tier can."""
    f = (fmt or "").lower()
    for t in TIER_ORDER:
        if f in TIER_FEATURES[t].get("exports", []):
            return TIER_LABEL[t]
    return None


def require(feature, label=None):
    """Raise 402 (payment required) when enforcement is on and the current tier lacks `feature`.
    No-op when enforcement is off — so callers can sprinkle these freely without affecting open mode."""
    if allows(feature):
        return
    from fastapi import HTTPException
    what = label or feature
    need = min_tier_for(feature)
    if need is None:                 # no tier grants it — say that, rather than implying an upgrade helps
        raise HTTPException(402, f"{what} is not included on any Massing plan.")
    raise HTTPException(402, f"{what} requires the Massing {need} plan (or higher). Add a licence "
                             "in Settings, or see massing.cloud.")


def require_export(fmt, label=None):
    """Raise 402 when enforcement is on and the current tier can't export `fmt`. No-op when off."""
    if allows_export(fmt):
        return
    from fastapi import HTTPException
    what = label or fmt.upper()
    need = min_tier_for_export(fmt)
    if need is None:
        raise HTTPException(402, f"{what} export is not included on any Massing plan.")
    raise HTTPException(402, f"{what} export requires the Massing {need} plan (or higher). Add a "
                            "licence in Settings, or see massing.cloud.")


def state() -> dict[str, Any]:
    """Licence state for the Settings panel + capability gating (no secret leaked — key is masked)."""
    tier = current_tier()
    key = _key()
    configured = bool(key)
    fmt_ok = valid_key_format(key) if configured else None
    enforced = enforcement_enabled()
    if not enforced:
        msg = ("Open mode — all features are available and a licence is optional. (Adding a key now is "
               "fine; entitlement enforcement is off until the operator enables it.)")
    elif configured and fmt_ok:
        msg = f"Massing {TIER_LABEL.get(tier, tier)} plan active."
    elif not configured:
        msg = ("Enforcement is on but no licence key is recorded — running on the Free tier. Paste your "
               "key (MASS-XXXX-XXXX-XXXX-XXXX) under Settings; get one at massing.cloud.")
    else:
        msg = "The recorded licence key isn't a valid MASS-XXXX-XXXX-XXXX-XXXX format — re-check it in Settings."
    return {
        "tier": tier,
        "tier_label": TIER_LABEL.get(tier, tier.title()),
        "enforced": enforced,
        "features": TIER_FEATURES[tier],
        "tiers": [{"id": t, "label": TIER_LABEL[t], "features": TIER_FEATURES[t]} for t in TIER_ORDER],
        "key_configured": configured,
        "key_masked": _mask(key) if configured else "",
        "key_format_valid": fmt_ok,
        "message": msg,
        "manage_url": "https://www.massing.cloud/docs/",
        "cloud": _cloud_status(),
    }


def _cloud_status() -> dict[str, Any]:
    """massing.cloud online-validation status for the Settings panel (never leaks the secret)."""
    try:
        from . import license_cloud
        return license_cloud.status()
    except Exception:                     # noqa: BLE001 — the bridge is optional; never break /license
        return {"online": False}
