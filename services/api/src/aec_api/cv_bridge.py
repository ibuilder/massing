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
                "/cv-progress/ingest. The platform does not run the model or fabricate progress.",
        "contract": {"activity": "schedule_activity id or name", "percent": "0–100",
                     "source": "the external estimator", "image_ref": "optional photo reference"},
    }


def ingest(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept an external CV progress estimate. No-op (accepted=False) when the bridge is disabled."""
    if not enabled():
        return {"accepted": False, "reason": "bridge disabled (set AEC_CV_BRIDGE to enable)",
                **status()}
    try:
        pct = float(payload.get("percent"))
    except (TypeError, ValueError):
        return {"accepted": False, "reason": "percent must be a number 0–100"}
    pct = max(0.0, min(100.0, pct))
    return {"accepted": True, "activity": payload.get("activity", ""), "percent": pct,
            "source": payload.get("source", "cv"), "image_ref": payload.get("image_ref"),
            "note": "Estimate accepted. Wire this to schedule_activity.percent in your CV integration."}
