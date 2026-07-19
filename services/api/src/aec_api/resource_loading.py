"""Resource-loaded scheduling (C2, deepened): a cost-loaded resource histogram, manpower + cost
S-curves, per-week over-allocation flags, and a leveling/smoothing advisory.

The primary source is the **`resource_assignment`** module — each record ties a resource (labor /
equipment / material, with a rate) to a **schedule activity** and a **cost code**, giving the
schedule ↔ resource ↔ cost join. Units are spread linearly across the assignment's (or its activity's)
date window into weekly buckets: concurrent units → the manpower **histogram** (by trade / type /
resource); cost (budgeted, or units × rate × days) → the cumulative **cost S-curve**. Over-allocation
flags weeks above an availability cap; `level()` proposes shifting non-critical work within its CPM
float (smoothing) to shave the peak. Falls back to activities' `crew_size` when no assignments exist,
so the classic manpower curve still renders. Rides on the existing schedule; keyed on cost code.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import schedule_cpm


def _d(r: dict) -> dict:
    return r.get("data") or r


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _weeks(s: date, f: date) -> list[date]:
    """Monday-aligned weeks spanned by [s, f] inclusive."""
    wk = s - timedelta(days=s.weekday())
    out = []
    while wk <= f:
        out.append(wk)
        wk += timedelta(days=7)
    return out


def _loads(db: Session, pid: str) -> tuple[list[dict], str]:
    """Normalize to a list of loads {resource, trade, rtype, start, finish, units, cost}. Prefers
    resource_assignment records; falls back to schedule_activity crew_size. Returns (loads, source)."""
    acts = {r["id"]: _d(r) for r in me.list_records(db, "schedule_activity", pid, limit=100_000)} \
        if "schedule_activity" in me.TABLES else {}
    loads: list[dict] = []
    assigns = me.list_records(db, "resource_assignment", pid, limit=100_000) \
        if "resource_assignment" in me.TABLES else []
    for r in assigns:
        d = _d(r)
        act = acts.get(d.get("activity"), {})
        s = _date(d.get("start")) or _date(act.get("start"))
        f = _date(d.get("finish")) or _date(act.get("finish"))
        units = _num(d.get("units")) or 0.0
        if not s or not f or f < s or units <= 0:
            continue
        span_days = (f - s).days + 1
        cost = _num(d.get("budgeted_cost"))
        if cost is None:                                  # rate is $/unit/day → units concurrent × days
            cost = units * (_num(d.get("rate")) or 0.0) * span_days
        loads.append({"resource": d.get("resource_name") or "(resource)",
                      "trade": d.get("trade") or "(unassigned)", "rtype": d.get("resource_type") or "Labor",
                      "start": s, "finish": f, "units": units, "cost": cost})
    if loads:
        return loads, "resource_assignment"
    # fallback: crew-loaded activities (the original C2 behaviour)
    for r in me.list_records(db, "schedule_activity", pid, limit=100_000) if acts else []:
        d = _d(r)
        crew = _num(d.get("crew_size"))
        s, f = _date(d.get("start")), _date(d.get("finish"))
        if not crew or crew <= 0 or not s or not f or f < s:
            continue
        loads.append({"resource": d.get("name") or r.get("title") or "(crew)",
                      "trade": d.get("trade") or "(unassigned)", "rtype": "Labor",
                      "start": s, "finish": f, "units": crew, "cost": _num(d.get("budget")) or 0.0})
    return loads, "schedule_activity.crew_size"


def loading(db: Session, pid: str, cap: float | None = None) -> dict[str, Any]:
    """Weekly cost-loaded resource histogram + manpower/cost S-curves + peak + over-allocation."""
    loads, source = _loads(db, pid)
    weeks: dict[str, dict[str, Any]] = {}
    for ld in loads:
        wk_list = _weeks(ld["start"], ld["finish"])
        cost_per_wk = ld["cost"] / len(wk_list) if wk_list else 0.0
        for wk in wk_list:
            b = weeks.setdefault(wk.isoformat(), {"units": 0.0, "cost": 0.0, "by_trade": {}, "by_type": {}})
            b["units"] += ld["units"]; b["cost"] += cost_per_wk
            b["by_trade"][ld["trade"]] = b["by_trade"].get(ld["trade"], 0.0) + ld["units"]
            b["by_type"][ld["rtype"]] = b["by_type"].get(ld["rtype"], 0.0) + ld["units"]

    series = sorted(weeks.items())
    peak = {"week": None, "units": 0.0}
    cum_u = cum_c = 0.0
    scurve, cost_curve = [], []
    for k, v in series:
        if v["units"] > peak["units"]:
            peak = {"week": k, "units": round(v["units"], 1)}
        cum_u += v["units"]; cum_c += v["cost"]
        scurve.append({"week": k, "cumulative": round(cum_u, 1)})
        cost_curve.append({"week": k, "cumulative": round(cum_c, 2)})
    over = ([{"week": k, "units": round(v["units"], 1), "cap": cap}
             for k, v in series if v["units"] > cap] if cap else [])
    return {
        "source": source, "loads": len(loads), "weeks_span": len(series), "cap": cap,
        "trades": sorted({t for _, v in series for t in v["by_trade"]}),
        "types": sorted({t for _, v in series for t in v["by_type"]}),
        "peak": peak, "total_cost": round(cum_c, 2),
        "histogram": [{"week": k, "total": round(v["units"], 1), "cost": round(v["cost"], 2),
                       "by_trade": {t: round(x, 1) for t, x in sorted(v["by_trade"].items())},
                       "by_type": {t: round(x, 1) for t, x in sorted(v["by_type"].items())}}
                      for k, v in series],
        "scurve": scurve, "cost_curve": cost_curve, "over_allocation": over,
        "note": "Weekly concurrent resource units per trade (histogram) + cumulative units and cost "
                "(S-curves). Over-allocation flags weeks above the availability cap. Add resource "
                "assignments (activity + cost code + units + rate) to cost-load the schedule.",
    }


def level(db: Session, pid: str, cap: float) -> dict[str, Any]:
    """Resource-leveling advisory: for each over-allocated week, list the assignments whose activity
    still has CPM **total float**, so they can be smoothed (shifted within float) to shave the peak
    without moving the finish. Advisory only — it never mutates the schedule."""
    load = loading(db, pid, cap)
    over = load["over_allocation"]
    if not over:
        return {"cap": cap, "peak": load["peak"], "over_weeks": 0, "suggestions": [],
                "note": "No weeks exceed the availability cap — the plan is within resource limits."}
    acts = me.list_records(db, "schedule_activity", pid, limit=100_000)
    cpm = schedule_cpm.compute(acts)
    float_by_id = {a["id"]: a.get("total_float", 0) for a in cpm["activities"]}
    act_data = {r["id"]: _d(r) for r in acts}
    over_weeks = {o["week"] for o in over}
    suggestions: list[dict] = []
    seen: set[str] = set()
    for r in me.list_records(db, "resource_assignment", pid, limit=100_000):
        d = _d(r)
        aid = d.get("activity")
        act = act_data.get(aid, {})
        s = _date(d.get("start")) or _date(act.get("start"))
        f = _date(d.get("finish")) or _date(act.get("finish"))
        if not s or not f:
            continue
        if not ({w.isoformat() for w in _weeks(s, f)} & over_weeks):
            continue
        fl = float_by_id.get(aid, 0)
        if fl and fl > 0 and r["id"] not in seen:
            seen.add(r["id"])
            suggestions.append({
                "assignment": r.get("ref"), "resource": d.get("resource_name"),
                "activity": act.get("name") or aid, "activity_id": aid, "trade": d.get("trade"),
                "total_float_days": fl, "units": _num(d.get("units")),
                "action": f"shift within {fl}-day float to smooth the peak"})
    suggestions.sort(key=lambda x: -(x["total_float_days"] or 0))
    return {
        "cap": cap, "peak": load["peak"], "over_weeks": len(over_weeks),
        "critical_locked": sum(1 for o in over) - len(suggestions),
        "suggestions": suggestions,
        "note": "Smoothing candidates: over-allocated work with positive CPM float can move without "
                "delaying the finish. Assignments on the critical path (no float) can only be leveled "
                "by extending the schedule or raising the cap.",
    }


def apply_level(db: Session, pid: str, cap: float, actor: str = "leveler") -> dict[str, Any]:
    """RESOURCE-LEVEL-2: APPLY one leveling round — the write half of the advisory above. Each
    smoothing candidate's ACTIVITY is shifted forward by up to a week, bounded by its CPM total float
    (so the project finish never moves), most-float-first, one shift per activity per round. Mutates
    `schedule_activity` start/finish via the module engine (audited, modified_at bumps) — callers gate
    this behind an explicit confirm. Returns the moves + before/after peak and over-allocated weeks;
    re-run for another round if over-allocation remains."""
    from datetime import timedelta

    before = loading(db, pid, cap)
    plan = level(db, pid, cap)
    moves: list[dict] = []
    moved_acts: set[str] = set()
    for s in plan.get("suggestions", []):
        aid = s.get("activity_id")
        fl = int(s.get("total_float_days") or 0)
        if not aid or aid in moved_acts or fl < 1:
            continue
        try:
            rec = me.get_record(db, "schedule_activity", pid, aid)
        except Exception:                            # noqa: BLE001 — assignment points at a gone activity
            continue
        d = rec.get("data") or {}
        s0, f0 = _date(d.get("start")), _date(d.get("finish"))
        if not s0 or not f0:
            continue
        shift = min(fl, 7)                           # week-granular: the loading buckets are weekly
        ns, nf = s0 + timedelta(days=shift), f0 + timedelta(days=shift)
        me.update_record(db, "schedule_activity", pid, aid,
                         {"start": ns.isoformat(), "finish": nf.isoformat()}, actor, "GC")
        moved_acts.add(aid)
        moves.append({"activity_id": aid, "activity": s.get("activity"), "shifted_days": shift,
                      "new_start": ns.isoformat(), "new_finish": nf.isoformat(),
                      "float_remaining": fl - shift})
    after = loading(db, pid, cap)
    return {"cap": cap, "moved": len(moves), "moves": moves,
            "peak_before": before["peak"], "peak_after": after["peak"],
            "over_weeks_before": len(before["over_allocation"]),
            "over_weeks_after": len(after["over_allocation"]),
            "note": "One leveling round applied (shifts bounded by CPM float — the finish never "
                    "moves). Re-run for another round if over-allocation remains; critical-path "
                    "work is never shifted."}
