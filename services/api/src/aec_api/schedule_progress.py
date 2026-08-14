"""R45-SCHED-DEDUPE ② — schedule progress against a baseline: BEI, variance, slippage.

**The R45 table filed this as an overlap with `progress_rollup.py`. It is not one — they measure
different objects, and only the word is shared.**

* `progress_rollup.py` measures **the building**: percent complete rolled up from as-built element
  presence, keyed by GlobalId, by IFC class / discipline / level, by count *and* by value.
* `massingplan/core/progress.py` measures **the schedule**: how activities are standing against their
  baseline dates, as at a data date.

A tower can be 60% erected and four weeks late, or on programme and barely started. Neither number
substitutes for the other, and reading one as the other is how a report reassures somebody wrongly.
That makes this the fifth entry in the R45 table classified wrong by name rather than by capability —
caught before it was acted on this time, by reading both modules.

## Where the baseline comes from, and why this works when `compare` did not

`compare` needs two computed *networks* and our snapshot has no predecessors, so it stays blocked.
**This needs only dates**, and `schedule_baselines._snapshot` stores `start` and `finish` per record
id — which is exactly `build_report`'s `baseline_start` / `baseline_finish` mappings. Same snapshot,
different requirement: one is satisfiable and the other is not.

## Two judgements preserved from the engine, both easy to "simplify" into a wrong answer

* **BEI is `None` when nothing was due — not `1.0`.** An empty ratio is not perfect performance, it is
  no information, and reporting it as 1.0 puts a green tile on the dashboard of a project that has not
  started.
* **`behind` is deliberately broader than DCMA check 11.** An activity that was due to start and never
  did counts as behind, even though check 11 only looks at finishes. It is the more urgent problem,
  and a report that misses it is missing what the reader most needs to see.

Variances are in **working days on the activity's own calendar**. Calendar-day variance overstates
every slip that spans a weekend, which is most of them.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.progress import build_report

from . import schedule_baselines, schedule_engine


def _dates(snapshot: dict[str, dict], key: str) -> dict[str, date]:
    """Pull one date field out of a baseline snapshot, skipping records that never had it."""
    out: dict[str, date] = {}
    for rid, row in snapshot.items():
        d = schedule_baselines._date(row.get(key))
        if d is not None:
            out[rid] = d
    return out


def progress(activities: list[dict], pid: str, *, baseline_id: str | None = None,
             data_date: date | None = None) -> dict[str, Any]:
    """Measure recorded progress against a captured baseline.

    `baseline_id` defaults to the most recent capture. **A project with no baseline is refused**, not
    measured against its own current dates — comparing a schedule to itself yields zero variance
    everywhere, which reads as a project perfectly on programme.
    """
    if not activities:
        return _unavailable("no activities — there is no progress to measure")

    baseline = schedule_baselines._get(pid, baseline_id)
    if not baseline:
        return _unavailable(
            "no baseline has been captured for this project. Progress is measured *against* a "
            "baseline; without one there is nothing to measure against, and comparing the schedule "
            "to its own current dates would report every activity as perfectly on programme.")

    snapshot = baseline.get("activities") or {}
    if not snapshot:
        return _unavailable("the captured baseline holds no activities",
                            baseline=schedule_baselines._meta(baseline))

    tasks, _links, calendars, issues = schedule_engine.build_network(activities)
    dd = data_date or schedule_engine.data_date_for(activities)

    try:
        report = build_report(
            tasks, dd,
            baseline_start=_dates(snapshot, "start"),
            baseline_finish=_dates(snapshot, "finish"),
            calendars=calendars,
        )
    except ScheduleCycleError as exc:
        return _unavailable(
            "the logic contains a loop, so the activities have no computed dates to measure",
            cycle=list(exc.cycle))

    bei = report.baseline_execution_index
    worst = report.worst_slippage
    return {
        "available": True,
        "baseline": schedule_baselines._meta(baseline),
        "data_date": report.data_date.isoformat(),
        "activity_count": len(report.activities),
        "complete": len(report.complete),
        # Broader than DCMA 11 on purpose — see the module docstring.
        "behind": len(report.behind),
        "not_started_but_due": len(report.not_started_but_due),
        # `None` when nothing was due. NOT 1.0: an empty ratio is no information, and a green tile on
        # a project that has not started is worse than a blank one.
        "baseline_execution_index": bei,
        "average_finish_variance_days": report.average_finish_variance,
        # `worst_slippage` is the ACTIVITY, not a number -- the property returns an ActivityProgress.
        # Reported as both, because "12 days late, and it is A20 that says so" is the actionable form
        # and a bare number is not. Naming the key `..._days` while returning a dataclass is exactly
        # the kind of thing that serialises to garbage in a route rather than failing loudly.
        "worst_slippage_days": (worst.finish_variance_days if worst else None),
        "worst_slippage_activity": (worst.activity_id if worst else None),
        # Actuals the engine could not use — a finish before its start, a date in the future. Surfaced
        # rather than dropped, because a silently ignored actual is a progress report that is quietly
        # measuring fewer activities than the reader thinks.
        "invalid_actuals": list(report.invalid_actuals),
        "issues": [i.to_dict() for i in issues],
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Nothing measured. Every count is `None`, never `0` — "none behind" and "not measured" differ."""
    return {
        "available": False,
        "reason": reason,
        "baseline": None,
        "data_date": None,
        "activity_count": None,
        "complete": None,
        "behind": None,
        "not_started_but_due": None,
        "baseline_execution_index": None,
        "average_finish_variance_days": None,
        "worst_slippage_days": None,
        "worst_slippage_activity": None,
        "invalid_actuals": [],
        "issues": [],
        **extra,
    }
