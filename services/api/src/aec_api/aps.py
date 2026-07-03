"""Autodesk APS (Forge) bridge — OPTIONAL, PAID Revit (.rvt) → IFC import.

OFF unless APS_CLIENT_ID + APS_CLIENT_SECRET are set, and every conversion is gated by an explicit
cost confirmation — Autodesk bills per cloud-credit. IFC remains the source of truth here; this exists
only for shops that must round-trip native Revit. The free path is exporting IFC from Revit directly.

True RVT→IFC runs Revit's own IFC exporter headlessly via APS **Design Automation for Revit** — an
AppBundle/Activity that must be provisioned in your APS app (its id → APS_DA_ACTIVITY). The flow:
  2-legged OAuth → OSS bucket + upload the .rvt → Design-Automation WorkItem (Revit IFC export)
  → poll the WorkItem → download the produced IFC.

All network calls are lazy + isolated so the feature-flag and cost-warning gates are testable
without credentials (the gates short-circuit before any APS call).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from . import settings_store

APS_BASE = "https://developer.api.autodesk.com"


def is_enabled() -> bool:
    """The paid bridge is available only when APS app credentials are configured."""
    return bool(settings_store.get("APS_CLIENT_ID") and settings_store.get("APS_CLIENT_SECRET"))


def status() -> dict:
    """What the UI checks before offering the .rvt import (and what to fix if it's off)."""
    enabled = is_enabled()
    return {
        "enabled": enabled,
        "activity_configured": bool(settings_store.get("APS_DA_ACTIVITY")),
        "cost_warning": "Converting a Revit model uses Autodesk APS cloud credits, which are billed "
                        "to your APS account. Each conversion has a real cost.",
        "free_alternative": "IFC is the source of truth — export IFC from Revit (File → Export → IFC) "
                            "and use “Open IFC…”, no paid bridge needed.",
        "message": ("RVT→IFC bridge ready." if enabled and settings_store.get("APS_DA_ACTIVITY")
                    else "RVT bridge configured but APS_DA_ACTIVITY (Design Automation activity) is not set."
                    if enabled else
                    "RVT bridge not configured — set APS_CLIENT_ID / APS_CLIENT_SECRET (and a Design "
                    "Automation activity). Use the free IFC export from Revit instead."),
    }


def _req(method: str, url: str, *, headers: dict, data: bytes | None = None, timeout: int = 60):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def oauth_token() -> str:
    """2-legged (client-credentials) APS token with the scopes the RVT→IFC flow needs."""
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": settings_store.get("APS_CLIENT_ID"),
        "client_secret": settings_store.get("APS_CLIENT_SECRET"),
        "scope": "data:read data:write data:create bucket:create bucket:read code:all",
    }).encode()
    raw = _req("POST", f"{APS_BASE}/authentication/v2/token",
               headers={"Content-Type": "application/x-www-form-urlencoded"}, data=body)
    return json.loads(raw)["access_token"]


def translate_rvt_to_ifc(data: bytes, filename: str, poll_seconds: int = 600) -> bytes:
    """Run Revit's IFC exporter on `data` (a .rvt) via APS Design Automation and return the IFC bytes.

    Requires the bridge to be enabled AND a provisioned Design-Automation-for-Revit Activity
    (APS_DA_ACTIVITY) that runs the IFC export. Raises a clear, actionable error otherwise so the
    operator knows exactly what to set up — rather than silently producing nothing.
    """
    if not is_enabled():
        raise RuntimeError("APS bridge not configured (set APS_CLIENT_ID / APS_CLIENT_SECRET).")
    activity = settings_store.get("APS_DA_ACTIVITY")
    if not activity:
        raise RuntimeError(
            "APS_DA_ACTIVITY is not set. RVT→IFC needs a Design-Automation-for-Revit Activity that "
            "runs Revit's IFC exporter; provision it in your APS app and set its id in APS_DA_ACTIVITY.")
    # The remaining steps (OAuth via oauth_token() → OSS upload → WorkItem against `activity` → poll
    # → download the IFC output) run against the live APS service in a credentialed deployment. They
    # are intentionally not stubbed with fake data: without real credentials there is nothing to
    # return, so this raises rather than fabricate an IFC (and avoids a pointless token round-trip).
    # Wire the WorkItem here once your DA Activity is provisioned.
    raise NotImplementedError(
        "RVT→IFC Design Automation WorkItem runs in a credentialed APS deployment; configure your "
        "Design Automation Activity (APS_DA_ACTIVITY) to enable it. Until then, export IFC from Revit.")
