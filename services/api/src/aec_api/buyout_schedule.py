"""BUYOUT-SCHED (R17 Sprint C) — a **time-phased procurement / buyout schedule** from the model QTO joined to
the construction schedule. Only we hold both the model *and* the CPM/Takt schedule, so we can answer the
buyer's real question deterministically: *what* must be bought, *how much*, and by *when to order it*.

For each QTO line we find the schedule activity that installs it (by explicit activity id, then cost code,
then trade — the earliest matching install), and compute the **last-responsible-order date**:

    last_responsible_order = install_start − lead_time

Sorted soonest-LRO first, with an `as_of` date turning each into overdue / urgent / upcoming / ok — the
buyout calendar a PM works from. Pure arithmetic over the lines + activities + lead times supplied; no model
load, no wall-clock (pass `as_of`).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

_URGENT_DAYS = 14
_UPCOMING_DAYS = 30


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def schedule(qto_lines: list[dict], activities: list[dict], lead_times: dict | None = None,
             as_of: str | None = None, default_lead_days: int = 0) -> dict[str, Any]:
    """Join QTO lines to their installing activity → a buyout schedule keyed on the last-responsible-order
    date. `lead_times` maps a material or trade (lower-cased) → lead days; a line's own `lead_time_days`
    wins. `as_of` (ISO date) classifies each entry overdue / urgent / upcoming / ok."""
    lead_times = {(_norm(k)): _num(v) for k, v in (lead_times or {}).items()}
    today = _date(as_of)

    by_id: dict[str, date] = {}
    by_code: dict[str, date] = {}
    by_trade: dict[str, date] = {}
    for a in activities or []:
        start = _date(a.get("start") or a.get("actual_start") or a.get("planned_start"))
        if start is None:
            continue
        aid = str(a.get("id") or a.get("activity_id") or "")
        if aid:
            by_id[aid] = min(by_id.get(aid, start), start)
        cc = _norm(a.get("cost_code"))
        if cc:
            by_code[cc] = min(by_code.get(cc, start), start)
        tr = _norm(a.get("trade") or a.get("discipline"))
        if tr:
            by_trade[tr] = min(by_trade.get(tr, start), start)

    entries = []
    unscheduled = 0
    for ln in qto_lines or []:
        if not isinstance(ln, dict):
            continue
        material = ln.get("material") or ln.get("item") or ln.get("description") or ""
        cc, tr = _norm(ln.get("cost_code")), _norm(ln.get("trade"))
        aid = str(ln.get("activity_id") or "")
        install = by_id.get(aid) or by_code.get(cc) or by_trade.get(tr)
        lead = _num(ln.get("lead_time_days")) or lead_times.get(_norm(material)) \
            or lead_times.get(tr) or lead_times.get(cc) or float(default_lead_days)
        lro = (install - timedelta(days=int(lead))) if install else None
        status, buffer_days = "unscheduled", None
        if install is None:
            unscheduled += 1
        elif today is not None:
            buffer_days = (lro - today).days
            status = ("overdue" if buffer_days < 0 else "urgent" if buffer_days <= _URGENT_DAYS
                      else "upcoming" if buffer_days <= _UPCOMING_DAYS else "ok")
        else:
            status = "scheduled"
        entries.append({
            "material": material, "cost_code": ln.get("cost_code"), "trade": ln.get("trade"),
            "qty": _num(ln.get("qty")) or None, "unit": ln.get("unit"),
            "value": round(_num(ln.get("cost")) or _num(ln.get("qty")) * _num(ln.get("unit_price")), 2) or None,
            "install_start": install.isoformat() if install else None,
            "lead_time_days": int(lead), "last_responsible_order": lro.isoformat() if lro else None,
            "buffer_days": buffer_days, "status": status,
        })

    # soonest LRO first; unscheduled last
    entries.sort(key=lambda e: (e["last_responsible_order"] is None, e["last_responsible_order"] or ""))
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {
        "line_count": len(entries), "unscheduled": unscheduled,
        "as_of": today.isoformat() if today else None,
        "status_counts": counts,
        "overdue": counts.get("overdue", 0),
        "next_30_days": counts.get("urgent", 0) + counts.get("upcoming", 0),
        "total_value": round(sum(e["value"] or 0 for e in entries), 2),
        "entries": entries,
        "note": "Buyout schedule = QTO joined to the installing activity (by id / cost code / trade); "
                "last-responsible-order = install start − lead time. Sorted soonest-order first; with an "
                "as_of date each line is overdue / urgent (≤14d) / upcoming (≤30d) / ok. Lines with no "
                "matching activity are 'unscheduled' — assign a cost code or trade to place them.",
    }
