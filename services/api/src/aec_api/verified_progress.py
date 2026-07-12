"""Schedule-linked verified-as-built progress (Wave 8 ③b).

The OpenSpace / Disperse / Buildots value proposition, done as pure software over the model we already
hold: instead of trusting a self-reported "% complete", roll **element-level field verification** up to
each schedule activity and show the **trust gap** — where the claimed percentage runs ahead of what has
actually been verified in place. Every element is anchored to its IFC GlobalId, and each deviated element
can be pushed to the BCF coordination model.

Verification comes from `field_verification` records (one per element), whose workflow state is the truth:
  * captured  — the field team captured it, not yet checked (pending)
  * verified  — checked, in place, within tolerance
  * deviated  — checked, out of tolerance (needs rework)
  * resolved  — was deviated, reworked and accepted

An element counts as *verified in place* when its state is `verified` or `resolved`. Records seed straight
from the `layout.verify` as-installed check (in-tolerance -> verified, out-of-tolerance -> deviated), or
from a manual field walk / the reality-capture overlay.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import fourd
from . import modules as me

_VERIFIED_STATES = ("verified", "resolved")


def index(db: Session, pid: str, elements: list[dict]) -> dict[str, Any]:
    """Read the field_verification + schedule_activity records for a project and roll them up against
    the given model element list. `elements`: [{guid, ifc_class, storey}] (from the published index)."""
    acts = me.list_records(db, "schedule_activity", pid, limit=100_000) if "schedule_activity" in me.TABLES else []
    fvs = me.list_records(db, "field_verification", pid, limit=100_000) if "field_verification" in me.TABLES else []
    verifications: dict[str, dict] = {}
    for r in fvs:
        d = r.get("data") or {}
        g = d.get("guid")
        if g:
            verifications[g] = {"state": r.get("workflow_state"), "deviation_mm": d.get("deviation_mm")}
    # schedule_activity records carry their tagged GUIDs at the top level (element_guids), like the 5D map
    acts2 = [{**a, "element_guids": (a.get("data") or {}).get("element_guids") or a.get("element_guids") or []}
             for a in acts]
    out = rollup(elements, acts2, verifications)
    out["verification_records"] = len(fvs)
    return out


def seed_from_layout(db: Session, pid: str, verify_result: dict, actor: str, party: str = "GC") -> dict[str, Any]:
    """Create field_verification records from a `layout.verify` result — one per checked point, moved to
    `verified` or `deviated` by whether it was in tolerance. Idempotent per GUID (skips ones already
    logged). Returns counts."""
    if "field_verification" not in me.TABLES:
        return {"created": 0, "skipped": 0, "reason": "field_verification module not installed"}
    existing = {(r.get("data") or {}).get("guid")
                for r in me.list_records(db, "field_verification", pid, limit=100_000)}
    created = skipped = 0
    for rec in from_layout_verify(verify_result):
        if rec["guid"] in existing:
            skipped += 1
            continue
        state = rec.pop("_state")
        data = {k: v for k, v in rec.items() if v is not None}
        row = me.create_record(db, "field_verification", pid, {"data": data}, actor, party)
        action = "verify" if state == "verified" else "flag"
        try:
            me.transition(db, "field_verification", pid, row["id"], action, actor, party, "seeded from as-installed survey")
        except Exception:        # noqa: BLE001 — record still created in the initial 'captured' state
            pass
        created += 1
    return {"created": created, "skipped": skipped}


def resolve_activity_refs(elements: list[dict], activities: list[dict]) -> dict[str, str | None]:
    """Map each element GUID -> the ref of the schedule activity that builds it, using the same
    hard-tie-or-by-trade resolution as the 5D map: (A) an activity that hard-tags the GUID via
    `element_guids`, else (B) class -> trade -> that trade's activities distributed by floor."""
    tied: dict[str, dict] = {}
    by_trade: dict[str, list] = {}
    for r in activities:
        d = r.get("data") or {}
        for g in (r.get("element_guids") or []):
            tied[g] = r
        if d.get("trade"):
            by_trade.setdefault(d["trade"], []).append(r)
    for v in by_trade.values():
        v.sort(key=lambda r: str((r.get("data") or {}).get("start") or ""))
    floors = max([fourd._floor_index(e.get("storey")) for e in elements] + [0]) + 1

    out: dict[str, str | None] = {}
    for el in elements:
        g = el.get("guid")
        if not g:
            continue
        if g in tied:
            out[g] = tied[g].get("ref")
            continue
        trade = fourd._CLASS_TRADE_TO_ACTIVITY_TRADE.get(
            fourd.TRADE_FOR_CLASS.get(el.get("ifc_class"), fourd._DEFAULT_TRADE))
        pool = by_trade.get(trade) or []
        if not pool:
            out[g] = None
            continue
        f = fourd._floor_index(el.get("storey"))
        i = round(f / max(1, floors - 1) * (len(pool) - 1)) if len(pool) > 1 else 0
        out[g] = pool[i].get("ref")
    return out


def rollup(elements: list[dict], activities: list[dict], verifications: dict[str, dict]) -> dict[str, Any]:
    """Per-activity verified-as-built vs. claimed progress + the overall trust gap.

    `verifications`: {guid: {"state": <workflow state>, "deviation_mm": float|None}}.
    Returns per-activity rows and portfolio-level totals; `trust_gap` = claimed% − verified%."""
    ref_for = resolve_activity_refs(elements, activities)
    act_by_ref = {a.get("ref"): a for a in activities}

    # accumulate element buckets per activity ref
    agg: dict[str, dict[str, int]] = {}
    for el in elements:
        ref = ref_for.get(el.get("guid"))
        if ref is None:
            continue
        b = agg.setdefault(ref, {"total": 0, "captured": 0, "verified": 0, "deviated": 0, "resolved": 0})
        b["total"] += 1
        v = verifications.get(el.get("guid"))
        if v:
            st = v.get("state")
            if st in b:
                b[st] += 1

    rows = []
    tot = {"total": 0, "verified": 0, "deviated": 0, "captured": 0}
    for ref, b in agg.items():
        a = act_by_ref.get(ref) or {}
        d = a.get("data") or {}
        verified = b["verified"] + b["resolved"]
        planned = _num(d.get("percent"))
        vpct = round(verified / b["total"] * 100, 1) if b["total"] else 0.0
        rows.append({
            "ref": ref, "activity": a.get("title") or d.get("name") or ref, "trade": d.get("trade"),
            "elements": b["total"], "verified": verified, "deviated": b["deviated"],
            "captured_pending": b["captured"], "verified_pct": vpct,
            "planned_pct": planned, "trust_gap": round((planned or 0) - vpct, 1),
            "state": a.get("workflow_state"),
        })
        tot["total"] += b["total"]; tot["verified"] += verified
        tot["deviated"] += b["deviated"]; tot["captured"] += b["captured"]
    rows.sort(key=lambda r: r["trust_gap"], reverse=True)   # worst over-claim first

    overall_verified_pct = round(tot["verified"] / tot["total"] * 100, 1) if tot["total"] else 0.0
    # element-count-weighted mean of claimed %, to compare like-for-like against verified %
    claimed_num = sum((r["planned_pct"] or 0) * r["elements"] for r in rows)
    overall_planned_pct = round(claimed_num / tot["total"], 1) if tot["total"] else 0.0
    return {
        "activities": rows,
        "elements_total": tot["total"],
        "elements_verified": tot["verified"],
        "elements_deviated": tot["deviated"],
        "elements_captured_pending": tot["captured"],
        "elements_unverified": tot["total"] - tot["verified"],
        "verified_pct": overall_verified_pct,
        "claimed_pct": overall_planned_pct,
        "trust_gap": round(overall_planned_pct - overall_verified_pct, 1),
        "coverage_pct": round((tot["verified"] + tot["deviated"] + tot["captured"]) / tot["total"] * 100, 1)
        if tot["total"] else 0.0,
        "note": "Verified-as-built rolls element-level field verification up to each schedule activity. "
                "trust_gap = claimed % − verified %; a positive gap means the reported progress runs "
                "ahead of what has been physically verified in place.",
    }


def from_layout_verify(verify_result: dict) -> list[dict]:
    """Turn a `layout.verify` result into field_verification record payloads: each checked point becomes
    an element verification (out-of-tolerance -> deviated, else verified), carrying its GlobalId + the
    measured deviation in millimetres."""
    out_ids = {d.get("guid"): d for d in (verify_result.get("out_of_tolerance") or [])}
    recs = []
    for d in verify_result.get("deviations") or []:
        guid = d.get("guid")
        if not guid:
            continue
        bad = guid in out_ids
        recs.append({
            "guid": guid, "element": d.get("number") or d.get("ifc_class") or guid,
            "ifc_class": d.get("ifc_class"), "method": "Total station",
            "deviation_mm": round(float(d.get("deviation_m", 0.0)) * 1000, 1),
            "_state": "deviated" if bad else "verified",
        })
    return recs


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
