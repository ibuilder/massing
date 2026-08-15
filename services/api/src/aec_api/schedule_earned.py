"""R46 ④ — Earned Schedule: how far along in *time*, where SPI stops working.

`aec_api/evm.py` computes the ANSI/EIA-748 set — PV, EV, AC, CPI, SPI — and its own docstring defers
this: *"the time-based Earned Schedule extension come in later phases"*. This is that phase.

## Why a second schedule index is not a duplicate

Classic `SPI = EV / PV` is a **cost ratio used as a time signal**, and it has a known terminal defect:
as a project finishes, EV converges on PV whatever the dates did, so **SPI returns to exactly 1.0 on
a project that finished a year late**. The number stops being wrong gradually; it stops being wrong
by arriving at "perfectly on schedule" for a job everyone can see was not.

`SPI(t) = ES / AT` compares two *durations*: where the baseline curve says you should have been by
now, against how long you have actually been going. It stays below 1.0 at completion on a late
project, which is the entire reason it exists. Both ship; `evm.py` is untouched.

## Two properties of the input worth knowing

**This needs only DATES, so a schema-1 baseline works.** Everything else built on the baseline library
this week — `compare`, `windows`, `modelled` — needs frozen logic and refuses the older snapshots.
Earned Schedule reads baselined start/finish per activity, which every baseline we have ever captured
carries. It is the one method here that works on the whole library.

**Activities with no baseline entry are excluded from both sides**, by the engine and deliberately.
They are scope added after the baseline, and counting progress on work the plan never contained
inflates the index for doing unplanned things.

## Units

Working days on the project calendar, throughout. A schedule metric quoted in calendar days rewards a
project for where its weekends fell — the same axis error that made concurrency come out negative in
`schedule_modelled`, and that `schedule_compare` reports as its calendar/working gap.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.earned import EarnedScheduleError, measure

from . import schedule_baselines, schedule_engine


def earned(activities: list[dict], pid: str, baseline_id: str | None = None,
           data_date: date | None = None) -> dict[str, Any]:
    """Earned Schedule for the live schedule against a captured baseline."""
    if not activities:
        return _unavailable("no activities — there is no progress to measure")

    base = schedule_baselines._get(pid, baseline_id)
    if base is None:
        return _unavailable(
            "no baseline to measure against. Earned Schedule asks where the plan said you would be "
            "by now, and without a plan there is no curve to read")

    # Dates only — no `logic_gap` check. This is the one method on the baseline library that a
    # schema-1 snapshot can serve, and refusing it would be a refusal the data does not require.
    baseline: dict[str, tuple[date, date]] = {}
    undated: list[str] = []
    for rid, a in (base.get("activities") or {}).items():
        start = schedule_baselines._date(a.get("start"))
        finish = schedule_baselines._date(a.get("finish"))
        if start is None or finish is None:
            undated.append(str(a.get("ref") or rid))
            continue
        baseline[rid] = (start, finish)

    if not baseline:
        return _unavailable(
            "no activity in the baseline carries both a start and a finish, so there is no curve "
            "to measure against", baseline=schedule_baselines._meta(base), undated=len(undated))

    tasks, _links, calendars, _ = schedule_engine.build_network(activities)
    dd = data_date or schedule_engine.data_date_for(activities)
    calendar = ((calendars or schedule_engine.CALENDARS).get(schedule_engine.DEFAULT_CALENDAR)
                or next(iter(schedule_engine.CALENDARS.values())))

    try:
        result = measure(tasks, baseline, data_date=dd, calendar=calendar)
    except EarnedScheduleError:
        # Composed here rather than relayed — the v0.3.962 rule. The one condition the engine
        # raises for is "no activity has a baseline", which after the filtering above means the
        # live schedule and the baseline share no ids at all.
        return _unavailable(
            "no current activity appears in this baseline — they share no ids, so there is nothing "
            "to measure. This usually means the schedule was re-imported rather than updated",
            baseline=schedule_baselines._meta(base), undated=len(undated))

    spi_t = result.performance_index
    return {
        "available": True,
        "baseline": schedule_baselines._meta(base),
        "data_date": result.data_date.isoformat(),
        "planned_duration_days": result.planned_duration_days,
        # AT — elapsed. ES — where the baseline curve says that much earned work sits.
        "actual_time_days": result.actual_time_days,
        "earned_days": round(result.earned_days, 2),
        "earned_duration_days": round(result.earned_duration_days, 2),
        "baseline_duration_days": round(result.baseline_duration_days, 2),
        # Negative is behind. Never clamped — a project ahead of plan is a fact too.
        "schedule_variance_days": round(result.schedule_variance_days, 2),
        # `None` when no time has passed, NOT 1.0: a project that has not started is not on schedule.
        "performance_index": None if spi_t is None else round(spi_t, 3),
        "unit": "working days",
        # Activities the baseline could not date, and activities not in the baseline at all — both
        # excluded, both counted, because a metric quietly computed over half the job is worse than
        # one that says which half.
        "baseline_undated": len(undated),
        "unbaselined_activities": sum(1 for t in tasks if t.id not in baseline),
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Counts `None`, never 0 — 'exactly on schedule' and 'not measured' must not render alike."""
    out: dict[str, Any] = {
        "available": False, "reason": reason, "baseline": None, "data_date": None,
        "planned_duration_days": None, "actual_time_days": None, "earned_days": None,
        "earned_duration_days": None, "baseline_duration_days": None,
        "schedule_variance_days": None, "performance_index": None, "unit": "working days",
        "baseline_undated": None, "unbaselined_activities": None,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out
