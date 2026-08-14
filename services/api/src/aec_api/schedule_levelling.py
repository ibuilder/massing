"""R45-SCHED-DEDUPE ② — deterministic resource levelling by serial schedule generation.

`aec_api/resource_loading.py` already has a `level()`, so the R45 table filed this as an overlap — and
it is one, but not a redundant one. Ours **shifts non-critical work within its CPM float** to shave a
peak: a smoothing advisory that never moves the finish and gives up when float runs out. The vendored
engine places every activity one at a time, in a fixed priority order, at the earliest instant its
resources are actually free — so it resolves conflicts our smoother can only report, and tells you
what that cost.

Both are worth having and they answer different questions. Ours: *"can I flatten this peak for free?"*
Theirs: *"what does a schedule that genuinely respects the crew limit look like?"*

## Determinism is the feature, not a nice property

The problem is NP-hard, so this is a constructive heuristic rather than an optimiser. It gives up
optimality and buys something more valuable on a construction job: **the same input always produces
the same answer**, and a planner can follow the placement decisions by hand.

The priority key ends in the activity id — `(late_start, total_float, -duration, id)` — and that final
tiebreak is load-bearing rather than cosmetic. Without it, set and dict iteration order leaks into
placement and the same file produces different levelled dates between runs under hash randomisation.
**An optimiser whose answer changes between runs cannot be reviewed, approved, or defended in a claim**,
which on a delay argument is the only thing that matters.

## Two horizons, and the choice is the user's

`within_float` never moves the project finish and **reports** the conflicts it could not resolve.
`extend_finish` resolves every conflict and accepts a later finish. Neither is the safe default in
general — a job with liquidated damages wants the first, a job that has already blown its float wants
the truth of the second — so the parameter is explicit and `within_float` is chosen only because it is
the non-destructive one.

## Where the demand comes from

`trade` + `crew_size` on each activity, the same pair `schedule_locations` and `schedule_takt` read.
`crew_size` is the units-per-day draw on the trade; the availability cap is the caller's, because how
many carpenters exist is a fact about the company and not about the schedule.
"""
from __future__ import annotations

from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.levelling import (
    LevellingHorizon,
    LevellingMode,
    LevellingRequest,
    level,
)
from massingplan.core.resources import Demand, ResourceAvailability
from massingplan.core.schedule import schedule_network

from . import schedule_engine
from .schedule_locations import _text


def _crew(row: dict) -> float:
    data = row.get("data") or {}
    for n in ("crew_size", "crew"):
        v = row.get(n, data.get(n))
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return 0.0


def levelling(activities: list[dict], *, caps: dict[str, float] | None = None,
              horizon: str = "within_float") -> dict[str, Any]:
    """Level the schedule against per-trade crew caps.

    `caps` maps a trade to the crews available per day. A trade with no cap is **left unconstrained
    rather than capped at a guess** — inventing an availability would silently move real work for a
    limit nobody set.
    """
    if not activities:
        return _unavailable("no activities — there is nothing to level")

    demands = [
        Demand(activity_id=row["id"], resource_id=_text(row, "trade"), units_per_day=_crew(row))
        for row in activities
        if row.get("id") and _text(row, "trade") and _crew(row) > 0
    ]
    if not demands:
        return _unavailable(
            "no activity carries both a trade and a crew size — levelling needs to know who is "
            "drawing on what, and those two fields are what say so")

    caps = {k: float(v) for k, v in (caps or {}).items() if float(v) > 0}
    if not caps:
        return _unavailable(
            "no crew caps supplied — levelling against an unlimited supply of every trade returns "
            "the schedule you already have. Pass `caps`, e.g. {\"Carpentry\": 8}.",
            trades=sorted({d.resource_id for d in demands}))

    try:
        h = LevellingHorizon(horizon)
    except ValueError:
        return _unavailable(
            f"unknown horizon {horizon!r} — use "
            f"{' or '.join(repr(x.value) for x in LevellingHorizon)}")

    tasks, links, calendars, issues = schedule_engine.build_network(activities)
    dd = schedule_engine.data_date_for(activities)
    try:
        outcome = schedule_network(tasks, links, calendars, data_date=dd)
    except ScheduleCycleError as exc:
        # Same reasoning as `schedule_health`: with a loop there are no dates to level against, so
        # levelling would be shuffling values that do not exist.
        return _unavailable(
            "the logic contains a loop, so no dates could be computed and there is nothing to level",
            cycle=list(exc.cycle))

    availability = [
        ResourceAvailability(resource_id=r, units_per_day=u) for r, u in sorted(caps.items())
    ]
    # Only demands whose trade is actually capped: an uncapped trade is unconstrained by definition,
    # and feeding it in with no matching availability would look like an infinite over-allocation.
    capped = [d for d in demands if d.resource_id in caps]
    if not capped:
        return _unavailable(
            "none of the capped trades appear on any activity — check the trade spelling",
            trades=sorted({d.resource_id for d in demands}), caps=sorted(caps))

    result = level(LevellingRequest(
        outcome=outcome, tasks=tasks, links=links, calendars=calendars,
        demands=capped, availability=availability,
        horizon=h, mode=LevellingMode.ADVISORY,
    ))

    return {
        "available": True,
        "horizon": result.horizon.value,
        "mode": result.mode.value,
        "finish_before": result.finish_before.isoformat(),
        "finish_after": result.finish_after.isoformat(),
        "finish_moved_days": (result.finish_after - result.finish_before).days,
        "moves": [m.to_dict() for m in result.moves],
        "move_count": len(result.moves),
        # Under `within_float` this is the honest remainder: conflicts the horizon would not let it
        # solve. An empty list here with a non-empty one under `extend_finish` is the trade-off made
        # visible, which is the reason the horizon is a parameter rather than a default.
        "unresolved_count": len(result.unresolved),
        "peak_before": dict(result.peak_before),
        "peak_after": dict(result.peak_after),
        "caps": caps,
        "issues": [i.to_dict() for i in issues],
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Nothing levelled. Counts are `None`, not `0` — "no moves" and "we did not run" differ."""
    return {
        "available": False,
        "reason": reason,
        "horizon": None,
        "mode": None,
        "finish_before": None,
        "finish_after": None,
        "finish_moved_days": None,
        "moves": [],
        "move_count": None,
        "unresolved_count": None,
        "peak_before": {},
        "peak_after": {},
        "caps": {},
        "issues": [],
        **extra,
    }
