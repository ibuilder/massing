"""CMMS — preventive-maintenance generation + work-order KPIs for the operations phase.

Post-turnover, 80% of a building's lifetime cost is operations; the discipline that controls it is a
CMMS loop: PM schedules generate work orders before failures happen, and KPIs (PM compliance, MTTR,
open-by-priority) show whether maintenance is proactive or reactive. Deterministic, on the config-
driven `work_order` / `pm_schedule` modules; emergency replacements typically cost 40–65% more than
planned work, which is the economic case for the PM loop."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import modules as me
from .timeutil import utc_today

_DONE = ("completed", "verified")


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _parse(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def generate_pm(db, pid: str, actor: str, as_of: date | None = None) -> dict[str, Any]:
    """Create preventive work orders for every ACTIVE pm_schedule that's due (next_due <= today, or
    never done). Idempotent per cycle: skips a schedule that already has an open PM work order linked.
    Advances next_due by frequency_days."""
    today = as_of or utc_today()
    scheds = me.list_records(db, "pm_schedule", pid, state="active", limit=1000)
    open_pm_for = set()
    for wo in me.list_records(db, "work_order", pid, limit=10000):
        if wo.get("workflow_state") not in _DONE and _d(wo).get("pm_schedule"):
            open_pm_for.add(_d(wo)["pm_schedule"])
    created = []
    for s in scheds:
        d = _d(s)
        freq = int(float(d.get("frequency_days") or 0) or 0)
        if freq <= 0 or s["id"] in open_pm_for:
            continue
        nxt = _parse(d.get("next_due")) or _parse(d.get("last_done"))
        if nxt and nxt > today:
            continue
        wo = me.create_record(db, "work_order", pid, {"data": {
            "subject": f"PM: {s.get('title') or d.get('subject') or s.get('ref')}",
            "wo_type": "Preventive", "priority": "Medium",
            "description": d.get("tasks") or "", "asset": d.get("asset"),
            "due_date": (today + timedelta(days=7)).isoformat(),
            "pm_schedule": s["id"],
        }}, actor, "GC")
        me.update_record(db, "pm_schedule", pid, s["id"],
                         {"next_due": (today + timedelta(days=freq)).isoformat()}, actor, "GC")
        created.append({"work_order": wo["ref"], "schedule": s.get("ref")})
    return {"generated": len(created), "work_orders": created, "as_of": today.isoformat()}


def kpis(db, pid: str, as_of: date | None = None) -> dict[str, Any]:
    """Maintenance KPIs: open by priority/type, overdue, PM compliance % (preventive WOs done on/before
    due), and MTTR in days (created → completed_date, corrective+emergency only)."""
    today = as_of or utc_today()
    wos = me.list_records(db, "work_order", pid, limit=10000)
    open_by_priority: dict[str, int] = {}
    by_type: dict[str, int] = {}
    overdue = pm_total = pm_on_time = 0
    ttr_days: list[float] = []
    for wo in wos:
        d = _d(wo)
        st = wo.get("workflow_state")
        typ = d.get("wo_type") or "Corrective"
        by_type[typ] = by_type.get(typ, 0) + 1
        done = st in _DONE
        if not done:
            pri = d.get("priority") or "(none)"
            open_by_priority[pri] = open_by_priority.get(pri, 0) + 1
            due = _parse(d.get("due_date"))
            if due and due < today:
                overdue += 1
        if typ == "Preventive" and done:
            pm_total += 1
            due, comp = _parse(d.get("due_date")), _parse(d.get("completed_date"))
            if comp and (not due or comp <= due):
                pm_on_time += 1
        if typ in ("Corrective", "Emergency") and done:
            comp = _parse(d.get("completed_date"))
            created = wo.get("created_at")
            if comp and created:
                try:
                    c0 = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
                    ttr_days.append(max(0, (comp - c0).days))
                except ValueError:
                    pass
    total = len(wos)
    done_n = sum(1 for w in wos if w.get("workflow_state") in _DONE)
    return {
        "total": total, "open": total - done_n, "completed": done_n, "overdue": overdue,
        "open_by_priority": open_by_priority, "by_type": by_type,
        "pm_compliance_pct": round(100 * pm_on_time / pm_total, 1) if pm_total else None,
        "mttr_days": round(sum(ttr_days) / len(ttr_days), 1) if ttr_days else None,
    }
