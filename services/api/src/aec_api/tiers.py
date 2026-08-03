"""Subscription-tier entitlements — the single place that decides what a tier unlocks.

Product decision (2026-06): **everyone is on the free tier** and the free tier has *every*
feature. This module exists so the eventual paid tiers are a one-line change here (and a
`tier` set on the User) rather than scattered `if` checks across the app. Today every gate
returns True; flip individual features per tier when the paid plans launch.
"""
from __future__ import annotations

TIERS = ("free", "pro", "enterprise")
DEFAULT_TIER = "free"

# Feature flags per tier. Free currently unlocks everything; the paid columns are placeholders
# for when we differentiate (e.g. seat counts, private cloud storage, SSO enforcement, AI quota).
_MATRIX: dict[str, dict[str, bool]] = {
    "free":       {"viewer": True, "portal": True, "proforma": True, "generate": True,
                   "connections": True, "ai": True, "private_cloud": True},
    "pro":        {"viewer": True, "portal": True, "proforma": True, "generate": True,
                   "connections": True, "ai": True, "private_cloud": True},
    "enterprise": {"viewer": True, "portal": True, "proforma": True, "generate": True,
                   "connections": True, "ai": True, "private_cloud": True},
}


def normalize(tier: str | None) -> str:
    return tier if tier in TIERS else DEFAULT_TIER


def features_for(tier: str | None) -> dict[str, bool]:
    return dict(_MATRIX[normalize(tier)])


def allows(tier: str | None, feature: str) -> bool:
    return features_for(tier).get(feature, False)
