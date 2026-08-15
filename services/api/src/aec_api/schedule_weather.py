"""R46 ⑦ — the weather allowance a programme already carries, made visible.

Every construction programme in a wet or a hot climate carries weather loss. It is almost never
*modelled* — it is padded into activity durations, where a five-day pour becomes seven and nobody
afterwards can say which two days were weather. That matters when the weather actually arrives,
because a contractor claiming an extension has to show the allowance was exceeded, and an allowance
buried inside durations cannot be shown at all.

This models it as **non-working days on the calendar**, which is what it is, and then reports the
difference: schedule the job with the allowance and without it, and the gap is the allowance.

## Three things it will not do

**It does not invent an allowance.** Days per month come from the caller — a contract schedule, a
met-office table, the specification. There is no default, because a default would be a number nobody
agreed inserted into a programme somebody signs.

**`without_allowance` strips only the weather days.** A shutdown the source file carried — Christmas,
a plant holiday — is a fact about the job and stays. Removing every calendar exception to get a
"no weather" baseline would delete the holiday too and report a fortnight of it as weather recovered.
The engine marks the days it adds and removes only those.

**The added days are listed, not just counted.** An allowance is argued with; `by_month` and the
dates themselves are returned so a planner can say which day was allowed and check it against the
record.

## What "spread" means, and why it is stated

The allowance for a month is distributed across that month's available working days rather than taken
as a block. A block at the start of a month stops different work than a block at the end, and neither
is more truthful — spreading is the neutral choice, and it is a modelling assumption rather than a
fact, so it is said out loud here and on the response.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.model import Calendar
from massingplan.core.schedule import schedule_network
from massingplan.core.weather import Allowance, WeatherError, apply_allowance, without_allowance

from . import schedule_engine


def _months(raw: Any) -> tuple[dict[int, int], list[str]]:
    """`{month: days}` from `{"1": 3, "2": 2}` or `{"jan": 3}`, with the unusable named."""
    names = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
             "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    out: dict[int, int] = {}
    bad: list[str] = []
    for k, v in (raw or {}).items():
        key = str(k).strip().lower()
        month = names.get(key[:3]) if not key.isdigit() else int(key)
        try:
            days = int(float(v))
        except (TypeError, ValueError):
            bad.append(f"{k}: not a number of days")
            continue
        if month is None or not 1 <= month <= 12:
            bad.append(f"{k}: not a month")
            continue
        if days < 0:
            # The engine refuses this too; saying why here is clearer than the raise.
            bad.append(f"{k}: negative — weather does not create working days")
            continue
        out[month] = days
    return out, bad


def weather(activities: list[dict], days_by_month: dict,
            start: date | None = None, finish: date | None = None) -> dict[str, Any]:
    """Schedule with and without the allowance, and report the difference."""
    if not activities:
        return _unavailable("no activities — there is no programme to allow weather on")

    months, bad = _months(days_by_month)
    if not months or not any(months.values()):
        return _unavailable(
            "no weather allowance given. Days per month come from the contract, a met-office table "
            "or the specification — there is no default, because a default is a number nobody "
            "agreed inserted into a programme somebody signs", rejected_months=bad)

    tasks, links, calendars, _ = schedule_engine.build_network(activities)
    dd = schedule_engine.data_date_for(activities)
    base_out = schedule_network(tasks, links, calendars, data_date=dd)

    window_start = start or dd
    window_finish = finish or base_out.project_finish
    if window_finish < window_start:
        return _unavailable("the window runs backwards", rejected_months=bad)

    # The exchange-model Calendar the weather engine works on, built from the scheduling calendar so
    # the two runs differ ONLY by the weather days.
    cal_id = schedule_engine.DEFAULT_CALENDAR
    work_cal = calendars.get(cal_id) or next(iter(calendars.values()))
    exchange = Calendar(id=cal_id, name=cal_id,
                        working_weekdays=set(getattr(work_cal, "working_weekdays", {0, 1, 2, 3, 4})),
                        exceptions=[], hours_per_day=8.0, is_default=True)

    try:
        with_weather, applied = apply_allowance(
            exchange, Allowance(calendar_id=cal_id, days_by_month=months),
            start=window_start, finish=window_finish)
    except WeatherError:
        # Composed here, never relayed — the v0.3.962 rule.
        return _unavailable("the allowance window could not be applied; check the dates",
                            rejected_months=bad)

    # `without_allowance` strips ONLY the days marked as weather. Asserted by using it rather than
    # rebuilding a bare calendar, so a shutdown the schedule carried survives both runs.
    clean = without_allowance(with_weather)

    lost = applied.total_days
    return {
        "available": True,
        "allowance_days": lost,
        "by_month": applied.by_month(),
        # Listed, not just counted: an allowance is argued with.
        "days": list(applied.to_dict()["days"]),
        "window_start": window_start.isoformat(),
        "window_finish": window_finish.isoformat(),
        "finish_without_allowance": base_out.project_finish.isoformat(),
        "rejected_months": bad,
        "weather_days_only": len(clean.exceptions) == 0,
        # The modelling assumption, said out loud rather than left in the arithmetic.
        "distribution": "spread across each month's available working days, not taken as a block — "
                        "a block at the start of a month stops different work than one at the end, "
                        "and neither is more truthful",
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Counts `None`, never 0 — 'no weather allowed' and 'not modelled' must not render alike."""
    out: dict[str, Any] = {
        "available": False, "reason": reason, "allowance_days": None, "by_month": {},
        "days": [], "window_start": None, "window_finish": None,
        "finish_without_allowance": None, "rejected_months": [], "weather_days_only": None,
        "distribution": None,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out
