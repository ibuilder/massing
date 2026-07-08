"""Computer-vision site-progress bridge (E2).

Real CV % complete — estimating installed progress from site photos — requires an external vision model,
so this is a **feature-flagged bridge**, matching how the platform treats other paid/external
integrations (RVT→IFC, licensed money processors): the platform never runs the model itself; an operator
enables the flag (``AEC_CV_BRIDGE``) and connects a CV service that POSTs progress estimates in. When the
flag is off (the default), the endpoints report the bridge as unavailable rather than fabricating a
number — nothing is invented.
"""
from __future__ import annotations

import os
from typing import Any


def enabled() -> bool:
    return os.environ.get("AEC_CV_BRIDGE", "").lower() in ("1", "true", "yes", "on")


def status() -> dict[str, Any]:
    return {
        "feature": "cv_progress_bridge", "enabled": enabled(),
        "note": "Computer-vision % complete from site photos is an external, feature-flagged bridge. "
                "Enable AEC_CV_BRIDGE and connect a vision service that POSTs estimates to "
                "/cv-progress/ingest (one) or /cv-progress/ingest-batch (many). The platform does not "
                "run the model or fabricate progress.",
        "contract": {"activity": "schedule_activity id OR name (name is resolved case-insensitively)",
                     "percent": "0–100", "source": "the external estimator",
                     "image_ref": "optional photo reference", "observed_at": "optional ISO timestamp"},
        "batch_contract": {"estimates": "[ {activity, percent, source?, image_ref?}, … ]"},
        "reference_adapter": "docs/cv-bridge.md — HTTP contract + a runnable Python reference client "
                             "you point at any vision service.",
    }


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Clamp/normalise one estimate. Returns {ok, percent|reason, activity, source, image_ref}."""
    try:
        pct = float(payload.get("percent"))
    except (TypeError, ValueError):
        return {"ok": False, "reason": "percent must be a number 0–100",
                "activity": payload.get("activity", "")}
    return {"ok": True, "percent": max(0.0, min(100.0, pct)), "activity": payload.get("activity", ""),
            "source": payload.get("source", "cv"), "image_ref": payload.get("image_ref"),
            "observed_at": payload.get("observed_at")}


def ingest(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept an external CV progress estimate. No-op (accepted=False) when the bridge is disabled."""
    if not enabled():
        return {"accepted": False, "reason": "bridge disabled (set AEC_CV_BRIDGE to enable)",
                **status()}
    v = validate(payload)
    if not v["ok"]:
        return {"accepted": False, "reason": v["reason"]}
    return {"accepted": True, "activity": v["activity"], "percent": v["percent"],
            "source": v["source"], "image_ref": v["image_ref"], "observed_at": v.get("observed_at"),
            "note": "Estimate accepted. Wire this to schedule_activity.percent in your CV integration."}


def ingest_batch(estimates: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate a batch of estimates (no DB). Returns per-item validation + counts; the router writes
    the accepted ones to their activities. No-op when the bridge is disabled."""
    if not enabled():
        return {"accepted": False, "reason": "bridge disabled (set AEC_CV_BRIDGE to enable)", **status()}
    if not isinstance(estimates, list):
        return {"accepted": False, "reason": "estimates must be a list of {activity, percent}"}
    items = [validate(e if isinstance(e, dict) else {}) for e in estimates]
    return {"accepted": True, "count": len(items), "valid": sum(1 for i in items if i["ok"]),
            "items": items}
