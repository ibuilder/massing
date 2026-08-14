"""R45-SCHED-REACH ① — location-based (linear) scheduling, reachable from the API.

`massingplan/core/locations.py` was the one vendored module with **no counterpart anywhere in this
codebase** — verified by reading it and then searching our tree for the domain's own terms (*flowline*,
*line of balance*, *location-based*) rather than a guessed pattern, which is how three earlier attempts
at that classification went wrong.

What it does that nothing here can: CPM answers *"when can this activity start"*. It cannot answer
*"where is each crew, and does anyone get in anyone else's way"*. A tower is the same twelve trades on
forty floors, and CPM models that as 480 independent activities with no notion that one gang does all
forty floors of drywall in order. **The thing CPM structurally cannot express is crew continuity** — a
forward pass gives every activity its earliest start, which is exactly what fragments a gang into
work-a-floor-then-wait. A subcontractor cannot price that, and it is where the money leaks.

## The two fields that make this free

Our `schedule_activity` records already carry **`trade`** and **`location`**. That is a linear schedule
in all but name: `trade` is the crew that flows, `location` is the place it flows through. No new data
model, no migration, no UI to fill in first — which is why this is an adapter and not a feature.

## Work content is expressed as quantity-at-unit-rate, and that is deliberate

`LinearTask.duration_days` is **one number for every location**, so it cannot say "drywall takes 4 days
on level 1 and 6 on level 2" — but our records can, because each activity has its own duration. The
engine's other input can: `quantities` per location at a `rate` per day. So the adapter passes
`quantities[location] = <summed duration for that trade there>` with `rate = 1.0`, i.e. *work measured
in crew-days, produced at one crew-day per day*.

That is an encoding, and the alternative was worse: collapsing each trade to a single flat duration
would silently average away exactly the per-location variation a flowline exists to show. The engine's
own docstring makes the same distinction in the other direction — quantities are "the honest input"
because *380 m² of slab at 95 m²/day is a fact about the work, where '4 days' is a fact about somebody's
arithmetic*. We only have the arithmetic, so we say so in the units rather than pretending to a take-off.

## Trade order is handover order, and it is NOT alphabetical

The engine takes `tasks` **in handover order** — each trade follows the one before it through every
location. The first version of this adapter sorted trades alphabetically, which put *Drywall* ahead of
*Framing* and produced a fully-formed flowline, a duration, and per-trade continuity costs that were
all confidently wrong. Nothing errored; the numbers were simply about a building nobody is going to
build. That is the most dangerous shape a result can have.

So the order is **derived from when each trade actually starts** in the existing schedule, and when the
records carry no dates to derive it from, the adapter **refuses and says so** rather than falling back
to alphabetical. An explicit `trade_order` overrides both, because the sequence is a planner's call.

## What it refuses, and why refusing is the feature

A flowline of one location is a bar chart, and a flowline with no trades is nothing. Both come back
`available: false` with a reason rather than a drawn-but-meaningless diagram — the same rule
`schedule_health` follows, and for the same reason: a chart that renders is read as a finding.
"""
from __future__ import annotations

import re
from typing import Any

from massingplan.core.issues import IssueLog
from massingplan.core.locations import (
    LinearScheduleError,
    LinearTask,
    Location,
    compute,
)

#: Trailing integers are what make "Level 2" sort before "Level 10". Plain string order is the classic
#: way a forty-storey flowline comes out with L10 between L1 and L2, which reads as a logic error in
#: the schedule rather than a sort bug in the chart.
_NUM = re.compile(r"(\d+)")


def _natural_key(name: str) -> tuple[object, ...]:
    parts = _NUM.split(name.strip().lower())
    return tuple(int(p) if p.isdigit() else p for p in parts if p != "")


def _text(row: dict, *names: str) -> str:
    data = row.get("data") or {}
    for n in names:
        v = row.get(n) or data.get(n)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _days(row: dict) -> float:
    data = row.get("data") or {}
    for n in ("duration", "duration_days"):
        v = row.get(n, data.get(n))
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return 1.0


def _first_start(row: dict) -> str:
    """The activity's start as an ISO string, or "" — ISO sorts correctly as text, so no parsing."""
    data = row.get("data") or {}
    for n in ("start", "actual_start", "early_start"):
        v = row.get(n, data.get(n))
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def flowline(activities: list[dict], *, sequence: list[str] | None = None,
             trade_order: list[str] | None = None) -> dict[str, Any]:
    """Compute the linear schedule for a project's activities.

    `sequence` optionally names the location order explicitly — the direction of flow up a building is
    a planner's decision, not something to infer. Absent it, locations are sorted naturally, which puts
    `Level 2` before `Level 10` instead of after it.

    `trade_order` names the handover order. Absent it, the order is derived from when each trade first
    starts in the existing schedule; if the records carry no dates, the call is **refused** rather than
    guessed — see the module docstring on why alphabetical is worse than nothing here.
    """
    if not activities:
        return _unavailable("no activities — there is no flow to compute")

    # (trade, location) -> crew-days. Summed, because several activities of one trade in one place are
    # that crew's work there; taking the max or the first would discard real content.
    content: dict[tuple[str, str], float] = {}
    for row in activities:
        trade = _text(row, "trade")
        loc = _text(row, "location", "location_loc")
        if not trade or not loc:
            continue
        content[(trade, loc)] = content.get((trade, loc), 0.0) + _days(row)

    if not content:
        return _unavailable(
            "no activity carries both a trade and a location — a flowline needs to know which crew "
            "is working where, and those two fields are what say so")

    locs = sorted({loc for _, loc in content}, key=_natural_key)
    if sequence:
        wanted = [s for s in sequence if s in set(locs)]
        locs = wanted + [x for x in locs if x not in set(wanted)]

    all_trades = {t for t, _ in content}
    if trade_order:
        ordered = [t for t in trade_order if t in all_trades]
        trades = ordered + sorted(all_trades - set(ordered), key=_natural_key)
    else:
        # Earliest start per trade. Framing before drywall because that is when they were planned,
        # not because F precedes D in the alphabet.
        starts: dict[str, str] = {}
        for row in activities:
            t, st = _text(row, "trade"), _first_start(row)
            if t and st and (t not in starts or st < starts[t]):
                starts[t] = st
        missing = sorted(all_trades - set(starts), key=_natural_key)
        if missing:
            return _unavailable(
                "cannot tell what order the trades hand over in: "
                f"{', '.join(missing[:5])} have no start date. A flowline drawn in alphabetical order "
                "is a confident answer about a building nobody is going to build — pass `trade_order` "
                "or date the activities.",
                locations=locs, trades=sorted(all_trades, key=_natural_key))
        trades = sorted(all_trades, key=lambda t: (starts[t], _natural_key(t)))

    if len(locs) < 2:
        return _unavailable(
            f"only one location ({locs[0]!r}) — a flowline through a single place is a bar chart",
            locations=locs, trades=trades)

    issues = IssueLog()
    tasks = [
        LinearTask(
            id=t, name=t,
            # Crew-days at one crew-day per day. See the module docstring: this is how per-location
            # work content is expressed at all, since `duration_days` is a single flat number.
            quantities={loc: content[(t, loc)] for loc in locs if (t, loc) in content},
            rate=1.0,
            duration_days=1,
        )
        for t in trades
    ]
    places = [Location(id=loc, name=loc, sequence=i) for i, loc in enumerate(locs)]

    try:
        result = compute(tasks, places, issues=issues)
    except LinearScheduleError as exc:
        # The engine refusing is a real answer about the data, not a server fault.
        return _unavailable(str(exc), locations=locs, trades=trades)

    return {
        "available": True,
        "locations": [{"id": p.id, "name": p.name, "sequence": p.sequence} for p in places],
        "trades": trades,
        "duration_days": result.duration_days,
        # The number that decides whether location-based scheduling is worth it on this job. The
        # engine reports it rather than absorbing it, and so do we.
        "continuity_cost_days": dict(result.continuity_cost_days),
        "segments": [
            {"task_id": s.task_id, "location_id": s.location_id,
             "start_offset": s.start_offset, "finish_offset": s.finish_offset,
             "duration_days": s.duration_days}
            for s in result.segments
        ],
        "interferences": [
            {k: getattr(i, k) for k in ("task_id", "location_id") if hasattr(i, k)}
            for i in result.interferences
        ],
        "interference_count": len(result.interferences),
        "issues": [i.to_dict() for i in issues],
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Nothing to draw. Every key the computed shape carries is present and empty.

    `duration_days` is `None`, not `0`. A zero-day flowline reads as a project that takes no time
    rather than one we could not compute — the same distinction `schedule_health` draws between an
    unassessable schedule and a failing one.
    """
    return {
        "available": False,
        "reason": reason,
        "locations": [],
        "trades": [],
        "duration_days": None,
        "continuity_cost_days": {},
        "segments": [],
        "interferences": [],
        "interference_count": 0,
        "issues": [],
        **extra,
    }
