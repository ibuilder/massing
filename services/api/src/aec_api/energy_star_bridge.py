"""ENERGY STAR Portfolio Manager bridge — feature-flagged stub (offline-first, never fabricates).

Benchmarking scores (the 1–100 ENERGY STAR score) come from EPA's Portfolio Manager web services and
require an account + property share — an online, per-deployment integration. Per platform policy the
core stays offline (meters + EUI computed locally in `energy.py`); this bridge activates only when a
deployment sets ENERGY_STAR_* env vars, and until then reports exactly what would happen instead of
inventing a score."""
from __future__ import annotations

import os
from typing import Any


def provider() -> str:
    return (os.environ.get("ENERGY_STAR_PROVIDER") or "").strip().lower()


def is_enabled() -> bool:
    return bool(provider() and os.environ.get("ENERGY_STAR_API_KEY"))


def status() -> dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "provider": provider() or None,
        "message": ("ENERGY STAR Portfolio Manager sync configured." if is_enabled() else
                    "No benchmarking provider configured. EUI and monthly trends are computed locally "
                    "from meter readings; set ENERGY_STAR_PROVIDER + ENERGY_STAR_API_KEY to sync a "
                    "property with EPA Portfolio Manager for the official 1-100 score."),
    }


def sync_property(project_id: str) -> dict[str, Any]:
    """Push meter data / pull the score for a property. Raises until a deployment wires the
    credentialed Portfolio Manager web-services account — never returns a fabricated score."""
    if not is_enabled():
        raise RuntimeError(
            "ENERGY STAR sync is not configured. Set ENERGY_STAR_PROVIDER=portfolio_manager and "
            "ENERGY_STAR_API_KEY (EPA web-services credentials), then map the property share. "
            "Local EUI/trends remain available without it.")
    raise NotImplementedError(
        f"ENERGY STAR provider '{provider()}' is flagged on but the web-services client is not wired "
        "for this deployment; implement the credentialed exchange in energy_star_bridge.sync_property.")
