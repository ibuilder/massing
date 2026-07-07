"""Field labor productivity (E1): units installed per man-hour, from the field productivity log.

Each entry records what got installed (quantity + unit), by whom (workers × hours = man-hours), on a
day. The engine computes the productivity rate per entry (units / man-hour) and rolls it up by trade and
by unit, so a super can see whether crews are gaining or losing ground — the field-productivity signal
that Rhumbix-style tools surface, kept on the same project record.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me


def _d(r: dict) -> dict:
    return r.get("data") or r


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def summary(db: Session, pid: str) -> dict[str, Any]:
    rows = me.list_records(db, "productivity_log", pid, limit=100000) \
        if "productivity_log" in me.TABLES else []
    entries = []
    by_trade: dict[str, dict[str, float]] = {}
    total_qty = total_mh = 0.0
    for r in rows:
        d = _d(r)
        qty, workers, hours = _num(d.get("quantity")), _num(d.get("workers")), _num(d.get("hours"))
        mh = (workers or 0) * (hours or 0)
        rate = round(qty / mh, 3) if qty is not None and mh else None
        entries.append({"date": d.get("date", ""), "activity": d.get("activity", ""),
                        "trade": d.get("trade", "") or "(unassigned)", "unit": d.get("unit", ""),
                        "quantity": qty, "workers": workers, "hours": hours,
                        "man_hours": round(mh, 1) if mh else None, "units_per_manhour": rate})
        if qty is not None and mh:
            t = by_trade.setdefault(d.get("trade", "") or "(unassigned)", {"quantity": 0.0, "man_hours": 0.0})
            t["quantity"] += qty
            t["man_hours"] += mh
            total_qty += qty
            total_mh += mh
    trade_rows = [{"trade": t, "quantity": round(v["quantity"], 2), "man_hours": round(v["man_hours"], 1),
                   "units_per_manhour": round(v["quantity"] / v["man_hours"], 3) if v["man_hours"] else None}
                  for t, v in sorted(by_trade.items())]
    return {
        "count": len(entries), "entries": entries, "by_trade": trade_rows,
        "total_quantity": round(total_qty, 2), "total_man_hours": round(total_mh, 1),
        "overall_units_per_manhour": round(total_qty / total_mh, 3) if total_mh else None,
        "note": "Productivity = quantity installed / man-hours (workers × hours). Rolled up by trade; "
                "units differ across trades, so compare rates within a trade/unit, not across.",
    }
