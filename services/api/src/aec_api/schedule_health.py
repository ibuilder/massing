"""R45-SCHED-REACH ① — DCMA 14-point schedule quality, reachable from the API.

`massingplan/core/health.py` has implemented the Defense Contract Management Agency's fourteen checks
since the `d1e4bf16` vendor sync, and **nothing in this application could call it.** 634 lines of the
closest thing the industry has to a shared definition of *"is this schedule trustworthy?"*, sitting
one import away from a portal whose users get asked that question by owners and lenders.

This is the adapter, and it is deliberately thin. The direction is one-way: **we convert our records
into the engine's types, never the reverse.** `massingplan.core` is stdlib-only *by contract* — it
must not learn what a SQLAlchemy row is — so every mapping happens here, and the vendored tree stays
re-syncable rather than becoming a fork. That is the same rule `schedule_cpm.py` follows and the same
rule whose *other* half (hardening untrusted XML at the application layer) was quietly deleted in the
same sync that shipped this module. The contract only works if both sides keep it.

## Three states, and none of them is a grade of F

A score is a claim, and the failure this file is most careful about is the one the engine itself calls
out in its own docstring: *"A tool that scores a schedule 14/14 because four of the checks could not
run is worse than one that does not score it at all."* The engine handles that internally by excluding
skipped checks from the denominator. The adapter has to handle the cases where there is no denominator
at all:

* **No activities** → `available: False`, not a grade. An empty schedule is not a failing schedule.
  Returning `F` for a project nobody has planned yet is a number that reads as a finding.
* **A cyclic network** → `available: False`, with the cycle. `schedule_network` raises rather than
  returning fabricated dates (see `schedule_cpm._cyclic` for why), and there is nothing to assess:
  every date the checks would read does not exist. Grading it would be grading a crash.
* **Assessed** → the engine's own report, verbatim.

Callers get `available` to branch on, so "we could not assess this" and "we assessed this and it is
bad" never render as the same thing.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.health import assess
from massingplan.core.schedule import schedule_network

from . import schedule_engine


def health(
    activities: list[dict],
    *,
    data_date: date | None = None,
    baseline_finish: dict[str, date] | None = None,
    resourced_activity_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Assess a schedule against the DCMA 14 checks.

    `activities` is the same record shape `schedule_cpm.compute` takes — `id`, `ref`, `title`,
    `data{}` — so a caller that can run the CPM can run this with no extra plumbing.

    `baseline_finish` and `resourced_activity_ids` are optional and **stay optional on purpose**.
    Checks 9, 10, 11 and 14 need baseline dates or resource assignments; without them the engine
    reports each as *skipped* and drops it from the score's denominator. Passing empty stand-ins to
    make the checks "run" would convert an honest gap into a passed check, which is the exact
    dishonesty the engine was written to avoid.
    """
    if not activities:
        return _unavailable("no activities — there is no schedule to assess")

    tasks, links, calendars, issues = schedule_engine.build_network(activities)
    dd = data_date or schedule_engine.data_date_for(activities)

    try:
        outcome = schedule_network(tasks, links, calendars, data_date=dd)
    except ScheduleCycleError as exc:
        # Not a failing grade. A cyclic network has no computed dates at all, so every check that
        # reads one would be scoring absent data.
        return _unavailable(
            "the logic contains a loop, so no dates could be computed and no check can be run",
            cycle=list(exc.cycle),
            issues=[i.to_dict() for i in issues],
        )

    report = assess(
        outcome,
        tasks,
        links,
        calendars,
        baseline_finish=baseline_finish,
        resourced_activity_ids=resourced_activity_ids,
    )
    return {
        "available": True,
        "activity_count": len(tasks),
        "relationship_count": len(links),
        "data_date": dd.isoformat(),
        "issues": [i.to_dict() for i in issues],
        **report.to_dict(),
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """The shape a caller gets when there is nothing to grade.

    Every key the assessed shape carries is present and empty, so a caller reading `checks` or
    `failed` does not need to special-case this — but `grade` and `score` are **`None`, not `"F"` and
    `0`**. A zero that means "we did not measure" is indistinguishable from a zero that means "this
    is terrible", and only one of those should make somebody's afternoon worse.
    """
    return {
        "available": False,
        "reason": reason,
        "grade": None,
        "score": None,
        "optimisable": None,
        "assessed": 0,
        "skipped": 0,
        "failed": 0,
        "checks": [],
        "issues": [],
        **extra,
    }
