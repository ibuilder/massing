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

import logging
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


_LOG = logging.getLogger(__name__)


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


#: The one-sided bound on a requested buffer. A planner asking for "a fortnight between the drywall
#: and the paint" is making an ordinary request; one asking for a year is making a mistake, and a
#: silently-honoured one pushes the whole line out and reads as an engine fault.
MAX_BUFFER_DAYS = 90


def parse_buffer_pairs(pairs: list[str] | None) -> tuple[dict[str, int], list[str]]:
    """`["Paint:-1", "Drywall:2"]` → `({"Paint": -1, "Drywall": 2}, [])`, plus what did not parse.

    **Here rather than in the router, so it can be tested without a server.** The transport shape is
    a repeated query parameter, and leaving its parsing in the route meant the one part of this
    feature a user actually types had no test at all — the engine suite could not reach it and no
    route suite covered the flowline. *A parser that only a live request can exercise is a parser
    nobody exercises.*

    Split on the LAST colon, so a trade whose name contains one survives. A pair that cannot be read
    is RETURNED rather than dropped: a typo in a query string is otherwise indistinguishable from a
    buffer the engine declined, and those have different fixes.
    """
    out: dict[str, int] = {}
    bad: list[str] = []
    for raw in pairs or []:
        trade, sep, days = str(raw).rpartition(":")
        if not sep or not trade.strip():
            bad.append(str(raw))
            continue
        try:
            out[trade.strip()] = int(days)
        except ValueError:
            bad.append(str(raw))
    return out, bad


def _buffer_map(buffer_days: Any, trades: list[str]) -> dict[str, int]:
    """`{trade: days}`, from either a flat number or a per-trade mapping.

    **A FLAT NUMBER IS NOT APPLIED TO THE FIRST TRADE, and that is the engine's shape rather than a
    choice here.** `LinearTask.buffer_days` is the lag on the link *into* that task
    (`locations.py`: `finishes[previous.id][loc] + task.buffer_days`), so the first trade in the
    order has no predecessor and its value is **inert** — measured: `buffer_days` 3 on the first of
    two trades moves nothing at all. The field's own docstring says the opposite (*"between this task
    finishing a location and the next task starting it"*), which is the sort of description that
    makes a caller set the wrong trade and conclude the feature is broken. So the map is built
    skipping the first trade, and `buffer_days_ignored` below says whose value was dropped.
    """
    if buffer_days is None:
        return {}
    out: dict[str, int] = {}
    if isinstance(buffer_days, dict):
        for k, v in buffer_days.items():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
    else:
        try:
            flat = int(buffer_days)
        except (TypeError, ValueError):
            return {}
        out = dict.fromkeys(trades, flat)
    # Clamped, not refused: a flowline is a planning view and a single silly number should not cost
    # the whole diagram. The clamp is reported (`buffer_days_clamped`) so it is not silent.
    return {t: max(-MAX_BUFFER_DAYS, min(MAX_BUFFER_DAYS, d)) for t, d in out.items()}


def flowline(activities: list[dict], *, sequence: list[str] | None = None,
             trade_order: list[str] | None = None,
             buffer_days: Any = None,
             buffer_pairs: list[str] | None = None) -> dict[str, Any]:
    """Compute the linear schedule for a project's activities.

    `sequence` optionally names the location order explicitly — the direction of flow up a building is
    a planner's decision, not something to infer. Absent it, locations are sorted naturally, which puts
    `Level 2` before `Level 10` instead of after it.

    `trade_order` names the handover order. Absent it, the order is derived from when each trade first
    starts in the existing schedule; if the records carry no dates, the call is **refused** rather than
    guessed — see the module docstring on why alphabetical is worse than nothing here.

    `buffer_days` (FLOW-BUFFER) is the clearance a planner WANTS between handovers — a flat number
    for every trade, or `{trade: days}`. `buffer_pairs` is the same thing in the transport's own
    shape, a list of `"<trade>:<days>"`, and it OVERRIDES the flat number per trade; it is parsed
    here rather than in the router so the part a user types has a test that needs no server. Negative is legal and means deliberate overlap, which is
    what makes the engine's `LOB.OVERLAP` error reachable from this route for the first time. Until
    this parameter existed the adapter never set `LinearTask.buffer_days`, so every line was placed
    as tight as it could go, `gap_days` was 0 on every pair, and that branch was dead from the
    product.

    **The request and the result are two different numbers, and the response carries both.** The
    realised overlap SATURATES at the predecessor's per-location duration — a successor cannot start
    before its predecessor did — so asking for 5 days of overlap on a trade with 2 crew-days per
    floor yields 2. Measured against the engine at 2/4/6/10 crew-days per location: a request of −5
    returns −2, −4, −5, −5. *A planner who asked for five and got two has been told nothing by a
    response that reports only the two.*
    """
    # Parsed FIRST, so a typo is reported even when the flowline itself is unavailable. An
    # empty `buffer_malformed` on a refusal would say "nothing was malformed", which is a
    # different claim from "we did not get that far" — and the one a consumer acts on.
    per, malformed = parse_buffer_pairs(buffer_pairs)

    def gone(reason: str, **extra: Any) -> dict[str, Any]:
        """`_unavailable`, carrying the parse result every early return would otherwise drop."""
        return _unavailable(reason, buffer_malformed=malformed, **extra)

    if not activities:
        return gone("no activities — there is no flow to compute")

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
        return gone(
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
            return gone(
                "cannot tell what order the trades hand over in: "
                f"{', '.join(missing[:5])} have no start date. A flowline drawn in alphabetical order "
                "is a confident answer about a building nobody is going to build — pass `trade_order` "
                "or date the activities.",
                locations=locs, trades=sorted(all_trades, key=_natural_key))
        trades = sorted(all_trades, key=lambda t: (starts[t], _natural_key(t)))

    if len(locs) < 2:
        return gone(
            f"only one location ({locs[0]!r}) — a flowline through a single place is a bar chart",
            locations=locs, trades=trades)

    issues = IssueLog()
    # FLOW-BUFFER. Built over the ORDERED trades, so "the first trade" means the first handover in
    # this flow rather than the first key a caller happened to send.
    wanted = _buffer_map(buffer_days, trades)
    # The per-trade pairs win over the flat number, which is what "override" means — and they are
    # clamped by the same rule, so a pair cannot smuggle past the bound the flat path respects.
    wanted.update(_buffer_map(per, trades) if per else {})
    applied = {t: d for t, d in wanted.items() if t in set(trades[1:])}
    # Whose request was dropped, and why — the first trade (no predecessor to space away from) and
    # any name that is not a trade on this project at all. Two different mistakes, kept apart: one
    # is a misunderstanding of the model, the other a typo.
    ignored_first = sorted(t for t in wanted if t == (trades[0] if trades else None))
    ignored_unknown = sorted(t for t in wanted if t not in set(trades))
    # Derived from what was APPLIED, not from what was asked — and my own test caught the
    # difference. Reading it off `wanted` named the first trade as clamped while `ignored_first`
    # named it as ignored, which is two contradictory statements about one value: a clamp says *we
    # used a smaller number*, and nothing was used at all. *Two reports of the same input must agree
    # about whether it had any effect.*
    clamped = sorted(t for t, d in applied.items() if abs(d) == MAX_BUFFER_DAYS)
    tasks = [
        LinearTask(
            id=t, name=t,
            # Crew-days at one crew-day per day. See the module docstring: this is how per-location
            # work content is expressed at all, since `duration_days` is a single flat number.
            quantities={loc: content[(t, loc)] for loc in locs if (t, loc) in content},
            rate=1.0,
            duration_days=1,
            buffer_days=applied.get(t, 0),
        )
        for t in trades
    ]
    places = [Location(id=loc, name=loc, sequence=i) for i, loc in enumerate(locs)]

    try:
        result = compute(tasks, places, issues=issues)
    except LinearScheduleError as exc:
        # The engine refusing is a real answer about the data, not a server fault -- but the message
        # is engine-authored and `py/stack-trace-exposure` is right that it should not be relayed
        # verbatim to a caller. The detail goes to the log; the client gets a stable sentence.
        _LOG.warning("flowline refused for %d activities: %s", len(activities), exc)
        return gone(
            "the schedule's locations could not be arranged into a flow — the activity locations are "
            "inconsistent. See the server log for the engine's reason.",
            locations=locs, trades=trades)

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
        # `to_dict()`, not a hasattr projection — and the line below has always called it.
        #
        # FLOW-CLEAR: this read `{k: getattr(i, k) for k in ("task_id", "location_id")
        # if hasattr(i, k)}`. `Interference` is a frozen dataclass with FIVE fields —
        # `predecessor_id`, `successor_id`, `location_id`, `gap_days`, `converging` — and **no
        # `task_id` at all** (that belongs to `Segment`). So the projection asked for a field the
        # type never had, `hasattr` skipped it in silence, and four of the five survived as one:
        # `[{"location_id": "L01"}]`, measured. Both task ids, the clearance in days and the
        # converging flag were discarded by the adapter before any client could decline to read
        # them.
        #
        # `gap_days` negative means the lines actually cross, and `converging` is, in the
        # dataclass's own words, *"the case where a slip in the predecessor is felt immediately at
        # the far end, and it is invisible on a bar chart"* — the one thing a flowline tells you
        # that CPM structurally cannot, dropped by the function whose docstring is about exactly
        # that. *A defensive projection fails silently by design, which is the wrong failure mode
        # for a field list: `to_dict()` would have raised the day the shape changed.*
        "interferences": [i.to_dict() for i in result.interferences],
        # NOT A COUNT OF COLLISIONS, and reading it as one is the trap FLOW-CLEAR found while
        # looking for something else. `locations.linear_schedule` appends an `Interference` for
        # EVERY consecutive pair of trade lines, unconditionally, recording the location where they
        # come CLOSEST and the clearance there — so this figure is `len(trades) - 1` and says
        # nothing about whether anybody is in anybody's way. Measured: two trades through three
        # floors with ample clearance return `interference_count: 1`.
        #
        # Kept, because it is the population every per-pair figure is drawn from, and a consumer
        # that renders it needs to know which of the two it is.
        #
        # *A name that sounds like a finding and measures a population is worse than no figure at
        # all, because a careful consumer renders it.*
        "interference_count": len(result.interferences),
        # `converging_count` is the signal that actually VARIES from this route, and it is the one
        # the `Interference` docstring says matters: *"the successor is the faster trade and is
        # catching up … a slip in the predecessor is felt immediately at the far end, and it is
        # invisible on a bar chart."*
        #
        # **AN `overlap_count` AND A `touching_count` WERE WRITTEN HERE AND DELETED BEFORE SHIPPING,
        # because measuring them showed both are constants from this route.** `compute()` places
        # each line at `max(0, max(requirements))`, so the clearance at the binding location is
        # exactly the declared buffer — and `LinearTask.buffer_days` *("Negative is legal and means
        # deliberate overlap")* is **never set by this adapter**. Measured directly against the
        # engine: buffer 0 → gap 0, buffer +2 → gap +2, buffer −3 → gap −3 **and** a `LOB.OVERLAP`
        # error. So from the HTTP route `gap_days` is always 0, `overlap_count` would always be 0
        # and `touching_count` always `len(trades) - 1`.
        #
        # *A count whose value the caller fixes is the same defect as a name that measures a
        # population — it reads as a measurement and carries no information* — which is why they
        # were not here, and why FLOW-BUFFER was filed: the gap was that nobody could REQUEST a
        # buffer, not that the engine failed to report one.
        #
        # **FLOW-BUFFER settled it, and `overlap_count` is published now**, because the thing that
        # comment was waiting for happened: a buffer is requestable, so this counts the pairs that
        # actually cross rather than restating the trade count. `touching_count` stays out — over a
        # fixed population it is the complement of the overlaps, so it is derivable and adds
        # nothing. *The deferral said "publish it then"; this is then.*
        "converging_count": sum(1 for i in result.interferences if i.converging),
        "overlap_count": sum(1 for i in result.interferences if i.gap_days < 0),
        # FLOW-BUFFER — WHAT WAS ASKED FOR, beside what came out. `gap_days` on each interference is
        # the clearance the engine ACHIEVED, and it saturates: the realised overlap cannot exceed the
        # predecessor's per-location duration, because a successor cannot start before its
        # predecessor did. Measured at 2/4/6/10 crew-days per location, a request of −5 returns
        # −2/−4/−5/−5. So a response carrying only `gap_days` tells a planner who asked for five and
        # got two precisely nothing, which is the TRUNC-COUNTED shape in a different currency.
        "buffer_days_requested": dict(applied),
        # The requests that could not be honoured, per pair: the trade, what it asked for and what
        # it got. Empty when every request landed exactly, which is the ordinary case for a
        # non-negative buffer — the saturation only ever bites on overlap.
        "buffer_days_unmet": [
            {"trade": i.successor_id, "requested": applied[i.successor_id],
             "realised": i.gap_days}
            for i in result.interferences
            if i.successor_id in applied and i.gap_days != applied[i.successor_id]
        ],
        # A value sent for the FIRST trade in the flow. The engine applies `buffer_days` to the link
        # INTO a task, so the first has no predecessor and the number is inert — reported rather
        # than dropped, because its own field docstring describes the other side and a caller
        # following that description sets exactly this trade.
        "buffer_days_ignored_first": ignored_first,
        # A name that is not a trade on this project. A typo, not a misunderstanding.
        "buffer_days_ignored_unknown": ignored_unknown,
        "buffer_days_clamped": clamped,
        "max_buffer_days": MAX_BUFFER_DAYS,
        # A `<trade>:<days>` pair that could not be read, echoed verbatim. Reported by the ENGINE
        # rather than bolted on by the router, so it is present on the refusal path too and a
        # consumer never reads it as `undefined`.
        "buffer_malformed": malformed,
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
        # `0`, not `None`, and this is the one place that is right: these count members of a list
        # that is certainly empty because nothing was computed, which is not the same shape as
        # `duration_days` above — a duration we could not compute, where a zero would read as a
        # project that takes no time.
        "interference_count": 0,
        "converging_count": 0,
        "overlap_count": 0,
        # FLOW-BUFFER. Empty, not absent: this function's whole contract is that *"every key the
        # computed shape carries is present and empty"*, and a key that appears only on the
        # available path is one a consumer reads as `undefined` on the refusal and renders as
        # nothing-was-requested. `max_buffer_days` is the one exception that carries its real value,
        # because it is a property of this module rather than of this call.
        "buffer_days_requested": {},
        "buffer_days_unmet": [],
        "buffer_days_ignored_first": [],
        "buffer_days_ignored_unknown": [],
        "buffer_days_clamped": [],
        "max_buffer_days": MAX_BUFFER_DAYS,
        "buffer_malformed": [],
        "issues": [],
        **extra,
    }
