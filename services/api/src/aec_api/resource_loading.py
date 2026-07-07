"""Resource-loaded scheduling (C2): a resource histogram, cumulative S-curve and over-allocation
flags built from the schedule activities' crew sizes and date ranges.

Each activity carries a `crew_size` (workers/day) and a start/finish. The engine buckets every week an
activity spans and sums the concurrent crew — by trade and overall — giving the classic resource
histogram (peak-manpower-per-week), a cumulative man-week S-curve, and, against an optional availability
cap, the weeks a trade is over-allocated. Rides on the existing CPM schedule; no new module.
"""
from __future__ import annotations

from datetime import date, timedelta
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


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def loading(db: Session, pid: str, cap: float | None = None) -> dict[str, Any]:
    """Weekly resource histogram + S-curve + peak + over-allocation, from crew-loaded activities."""
    rows = me.list_records(db, "schedule_activity", pid, limit=100000) \
        if "schedule_activity" in me.TABLES else []
    weeks: dict[str, dict[str, Any]] = {}
    loaded = 0
    for r in rows:
        d = _d(r)
        crew = _num(d.get("crew_size"))
        s, f = _date(d.get("start")), _date(d.get("finish"))
        if not crew or crew <= 0 or not s or not f or f < s:
            continue
        loaded += 1
        trade = d.get("trade") or "(unassigned)"
        wk = s - timedelta(days=s.weekday())          # Monday of the start week
        while wk <= f:
            b = weeks.setdefault(wk.isoformat(), {"total": 0.0, "by_trade": {}})
            b["total"] += crew
            b["by_trade"][trade] = b["by_trade"].get(trade, 0.0) + crew
            wk += timedelta(days=7)

    series = sorted(weeks.items())
    peak = {"week": None, "crew": 0.0}
    cum = 0.0
    scurve = []
    for k, v in series:
        if v["total"] > peak["crew"]:
            peak = {"week": k, "crew": round(v["total"], 1)}
        cum += v["total"]
        scurve.append({"week": k, "cumulative": round(cum, 1)})
    over = ([{"week": k, "crew": round(v["total"], 1), "cap": cap}
             for k, v in series if v["total"] > cap] if cap else [])
    trades = sorted({t for _, v in series for t in v["by_trade"]})

    return {
        "activities_loaded": loaded, "weeks_span": len(series), "cap": cap,
        "trades": trades, "peak": peak,
        "histogram": [{"week": k, "total": round(v["total"], 1),
                       "by_trade": {t: round(x, 1) for t, x in sorted(v["by_trade"].items())}}
                      for k, v in series],
        "scurve": scurve, "over_allocation": over,
        "note": "Weekly concurrent crew per trade (resource histogram) + cumulative man-weeks (S-curve). "
                "Over-allocation flags weeks where total crew exceeds the availability cap. Load activities "
                "with a crew size + start/finish to populate.",
    }
