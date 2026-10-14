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

#: Estimates accepted per batch. Each one becomes a `schedule_activity` write, so an uncapped list
#: is an editor-role request that performs an unbounded number of them. REFUSED rather than
#: truncated: writing 500 of a 5,000-estimate sweep and reporting success is the defect
#: `write_coverage` below exists to prevent, and silently doing it at the door would be worse than
#: declining. The limit is named in the refusal so the integrator can split the sweep.
MAX_BATCH = 500


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
    # The note USED to read "Wire this to schedule_activity.percent in your CV integration" — work
    # the router has done since the write path landed, so the sentence told an integrator to build
    # something that already existed, beside an `applied: true` saying it had happened. *A contract
    # sentence that outlived its own caveat is read as current by whoever implements against it.*
    return {"accepted": True, "activity": v["activity"], "percent": v["percent"],
            "source": v["source"], "image_ref": v["image_ref"], "observed_at": v.get("observed_at"),
            "note": ("Estimate accepted and written to that activity's percent." if v["activity"]
                     else "Estimate accepted and NOT written: give `activity` (a schedule_activity "
                          "id or name) to have it applied.")}


def ingest_batch(estimates: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate a batch of estimates (no DB). Returns per-item validation + counts; the router writes
    the accepted ones to their activities. No-op when the bridge is disabled."""
    if not enabled():
        return {"accepted": False, "reason": "bridge disabled (set AEC_CV_BRIDGE to enable)", **status()}
    if not isinstance(estimates, list):
        return {"accepted": False, "reason": "estimates must be a list of {activity, percent}"}
    if len(estimates) > MAX_BATCH:
        return {"accepted": False, "received": len(estimates), "limit": MAX_BATCH,
                "reason": f"batch of {len(estimates)} estimates exceeds the {MAX_BATCH}-estimate "
                          f"limit; split the sweep rather than having part of it applied"}
    items = [validate(e if isinstance(e, dict) else {}) for e in estimates]
    return {"accepted": True, "count": len(items), "valid": sum(1 for i in items if i["ok"]),
            "items": items}


def write_coverage(items: list[dict[str, Any]]) -> dict[str, Any]:
    """What `accepted: True` does NOT say about a batch: how much of it was actually written.

    **`accepted` is a verdict about the PAYLOAD, decided before any write is attempted** — the
    bridge was enabled and the body was a list of the right shape. It stays `True` on a sweep in
    which every single write failed, and the per-item outcomes that say so are inside `items`,
    which an integrator logging the summary line never reads. *A boolean fixed before the work
    begins cannot report on the work*, and a 200 beside `accepted: true` is exactly what an
    integration treats as "the sweep landed".

    So the counts are stated here, in the shape the rest of this service uses for the same
    question: `written` is the only one that means a `schedule_activity.percent` moved, and each
    of the other three is a different reason one did not. There is deliberately NO boolean — a
    `complete: true` would just be `accepted` again, one layer along.

    Called by the router rather than by `ingest_batch`, because the router is the only place that
    knows the write outcomes: the engine validates, the router applies. *The narrowest place that
    can carry a fact is where it belongs* — and here that is one step further out than usual.
    """
    ok = [i for i in items if i.get("ok")]
    written = [i for i in ok if i.get("applied")]
    no_activity = [i for i in ok if not i.get("activity")]
    failed = [i for i in ok if i.get("activity") and not i.get("applied")]
    return {
        "received": len(items),
        "written": len(written),
        "write_failed": len(failed),
        "no_activity": len(no_activity),
        "invalid": len(items) - len(ok),
        # NO boolean, and no `complete: null` placeholder either — a null key named `complete` is
        # falsy in both JavaScript and Python and would be read as "not complete" by the first
        # consumer that touches it.
        #
        # The empty case is FIRST on purpose. `len(written) == len(items)` is true of a batch with
        # nothing in it, so a reason computed in the obvious order says "every estimate was
        # written" about zero estimates — the vacuous-quantifier shape
        # `services/api/test_quant_vacuous.py` exists for, in a sentence written days after that
        # gate landed. *A presence guard is not something you remember to add; it is something a
        # check has to demand.*
        "reason": ("the batch was empty, so nothing was written" if not items
                   else "nothing was written" if not written
                   else "every estimate in the batch was written" if len(written) == len(items)
                   else f"{len(written)} of {len(items)} estimate(s) were written"),
    }
