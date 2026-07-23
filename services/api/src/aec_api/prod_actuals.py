"""PROD-ACTUALS (R16 Tier-2) — the **productivity actuals loop**: installed-rate *actual vs planned* +
crew utilization, so the LOB / 4D view shows whether the field is gaining or losing ground against takt.

Each actual is a `{task_id, qto_line, material_class, qty, cycle_time, idle_time, unit, ts}` row — what got
installed, the **productive** hours it took (`cycle_time`) and the **idle** hours around it (`idle_time`).
Grouped by activity (qto_line / task_id), the engine computes the **installed rate** (qty ÷ productive
hours) and **crew utilization** (productive ÷ (productive + idle)), then compares the installed rate to the
**planned** rate to flag ahead / on-track / behind and — when a planned quantity is known — project the
remaining hours at the current rate.

Pure arithmetic over the rows the caller supplies (field log, telematics CSV, or a manual entry), so it's
deterministic and unit-testable. Units differ across trades, so rates are compared *within* a group, never
summed across — the rollup reports utilization (dimensionless) and a per-group variance count, not a single
cross-trade rate.
"""
from __future__ import annotations

from typing import Any

_AHEAD = 5.0    # ± this % of the planned rate is "on track"; beyond is ahead / behind


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _group_key(row: dict) -> str:
    return str(row.get("qto_line") or row.get("activity") or row.get("task_id") or "(unassigned)")


def _planned_rate(planned: dict | None, key: str) -> tuple[float | None, float | None]:
    """(planned installed-rate units/hr, planned total qty) for a group — either given directly, or a rate
    derived from planned_qty ÷ planned_hours."""
    if not planned:
        return None, None
    p = planned.get(key)
    if not isinstance(p, dict):
        return None, None
    rate = _num(p.get("rate")) or _num(p.get("planned_rate"))
    pqty = _num(p.get("qty")) or _num(p.get("planned_qty"))
    phrs = _num(p.get("hours")) or _num(p.get("planned_hours"))
    if rate is None and pqty and phrs:
        rate = round(pqty / phrs, 4) if phrs else None
    return rate, pqty


def analyze(actuals: list[dict], planned: dict | None = None) -> dict[str, Any]:
    """Roll the actuals up per activity → installed rate + utilization, compared to the planned rate."""
    groups: dict[str, dict[str, Any]] = {}
    for row in actuals or []:
        if not isinstance(row, dict):
            continue
        key = _group_key(row)
        g = groups.setdefault(key, {"qty": 0.0, "productive": 0.0, "idle": 0.0, "unit": "",
                                    "material_class": row.get("material_class") or "", "rows": 0})
        g["qty"] += _num(row.get("qty")) or 0.0
        g["productive"] += _num(row.get("cycle_time")) or 0.0
        g["idle"] += _num(row.get("idle_time")) or 0.0
        g["unit"] = g["unit"] or (row.get("unit") or "")
        g["rows"] += 1

    out_groups = []
    ahead = on_track = behind = 0
    tot_prod = tot_idle = 0.0
    for key, g in groups.items():
        prod, idle, qty = g["productive"], g["idle"], g["qty"]
        actual_rate = round(qty / prod, 4) if prod > 0 else None
        util = round(prod / (prod + idle), 4) if (prod + idle) > 0 else None
        p_rate, p_qty = _planned_rate(planned, key)
        variance_pct = status = None
        if actual_rate is not None and p_rate:
            variance_pct = round((actual_rate - p_rate) / p_rate * 100.0, 1)
            status = "ahead" if variance_pct > _AHEAD else "behind" if variance_pct < -_AHEAD else "on_track"
            ahead += status == "ahead"
            on_track += status == "on_track"
            behind += status == "behind"
        pct_complete = remaining_qty = projected_hours = None
        if p_qty and p_qty > 0:
            pct_complete = round(min(1.0, qty / p_qty), 3)
            remaining_qty = round(max(0.0, p_qty - qty), 2)
            if actual_rate and actual_rate > 0:
                projected_hours = round(remaining_qty / actual_rate, 1)
        tot_prod += prod
        tot_idle += idle
        out_groups.append({
            "group": key, "material_class": g["material_class"], "unit": g["unit"], "entries": g["rows"],
            "installed_qty": round(qty, 2), "productive_hours": round(prod, 2), "idle_hours": round(idle, 2),
            "installed_rate": actual_rate, "utilization": util,
            "planned_rate": p_rate, "variance_pct": variance_pct, "status": status,
            "planned_qty": p_qty, "pct_complete": pct_complete, "remaining_qty": remaining_qty,
            "projected_hours_at_rate": projected_hours,
        })

    out_groups.sort(key=lambda r: (r["variance_pct"] if r["variance_pct"] is not None else 1e9))
    overall_util = round(tot_prod / (tot_prod + tot_idle), 4) if (tot_prod + tot_idle) > 0 else None
    return {
        "group_count": len(out_groups),
        "groups": out_groups,
        "overall_utilization": overall_util,
        "total_productive_hours": round(tot_prod, 2), "total_idle_hours": round(tot_idle, 2),
        "planned_compared": ahead + on_track + behind,
        "ahead": ahead, "on_track": on_track, "behind": behind,
        "worst": out_groups[0]["group"] if out_groups and out_groups[0].get("variance_pct") is not None else None,
        "note": "Installed rate = qty ÷ productive (cycle) hours; utilization = productive ÷ (productive + "
                "idle). Compared to the planned rate per activity: >±5% is ahead / behind, else on track. "
                "Rates are compared within a group only — units differ across trades, so no cross-trade rate "
                "is summed.",
    }
