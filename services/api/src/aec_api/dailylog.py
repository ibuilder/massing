"""Field-log analytics — rolls up daily reports into manpower trend (total/avg/peak), weather-impact
lost-day equivalents, and reporting coverage (days logged, gaps). Pure read-side aggregation over the
daily_report module; no writes. Mirrors the submittals/rfi/quality register engines."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# weather_impact -> lost-day equivalent (working days)
WEATHER_LOST = {"None": 0.0, "Minor Delay": 0.1, "Half-Day Lost": 0.5,
                "Full-Day Lost": 1.0, "Stoppage": 1.0}
SUBMITTED = ("submitted",)


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _d(r: dict) -> dict:
    return r.get("data") or r


def summary(reports: list[dict]) -> dict[str, Any]:
    by_weather, by_impact = {}, {}
    manpower_total = weather_lost_days = 0.0
    peak = {"count": 0, "date": None}
    delay_days = submitted = 0
    dates: list[date] = []
    rows = []
    for r in reports:
        d = _d(r)
        st = r.get("workflow_state") or "draft"
        if st in SUBMITTED:
            submitted += 1
        rd = _parse(d.get("report_date"))
        if rd:
            dates.append(rd)
        # manpower: prefer the manpower_log rollup (crew_total) when present, else the typed count
        mp = _num(d.get("crew_total")) or _num(d.get("manpower"))
        manpower_total += mp
        if mp > peak["count"]:
            peak = {"count": int(mp) if mp == int(mp) else mp, "date": d.get("report_date")}
        weather = (d.get("weather") or "(unrecorded)").strip() or "(unrecorded)"
        by_weather[weather] = by_weather.get(weather, 0) + 1
        impact = (d.get("weather_impact") or "None").strip() or "None"
        by_impact[impact] = by_impact.get(impact, 0) + 1
        weather_lost_days += WEATHER_LOST.get(impact, 0.0)
        has_delay = bool((d.get("delays") or "").strip())
        if has_delay:
            delay_days += 1
        rows.append({
            "ref": r.get("ref"), "report_date": d.get("report_date"), "weather": weather,
            "temp_f": d.get("temp_f"), "weather_impact": impact, "manpower": mp,
            "has_delay": has_delay, "state": st,
        })
    n = len(rows)
    span_days = (max(dates) - min(dates)).days + 1 if dates else 0
    logged_days = len(set(dates))
    coverage = round(100 * logged_days / span_days, 1) if span_days else None
    return {
        "report_count": n, "submitted_count": submitted, "draft_count": n - submitted,
        "first_date": min(dates).isoformat() if dates else None,
        "last_date": max(dates).isoformat() if dates else None,
        "span_days": span_days, "logged_days": logged_days, "coverage_pct": coverage,
        "total_manpower": round(manpower_total, 1),
        "avg_manpower": round(manpower_total / n, 1) if n else None,
        "peak_manpower": peak,
        "weather_lost_days": round(weather_lost_days, 2),
        "delay_days": delay_days,
        "by_weather": dict(sorted(by_weather.items())),
        "by_impact": by_impact,
        "rows": sorted(rows, key=lambda r: (r.get("report_date") or ""), reverse=True),
    }


def field_log_summary(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    reps = me.list_records(db, "daily_report", pid, limit=100000) if "daily_report" in me.TABLES else []
    return summary(reps)
