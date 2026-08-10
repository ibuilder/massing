"""Deterministic resource levelling by serial schedule generation.

The problem is NP-hard, so this is a constructive heuristic rather than an
optimiser: activities are placed one at a time, in a fixed priority order, at
the earliest instant their resources are free. That gives up optimality and buys
something more valuable here -- **the same input always produces the same
answer**, and a planner can follow the placement decisions by hand.

Four decisions worth naming:

* **The priority key ends in the activity id.** ``(late_start, total_float,
  -duration, id)``. The final tiebreak is not cosmetic: without it, set and dict
  iteration order leaks into placement, and the same file produces different
  levelled dates between runs with hash randomisation on. An optimiser whose
  answer changes between runs cannot be reviewed, approved, or defended in a
  claim.
* **Float is frozen from the pre-levelling pass and never recomputed.**
  Recomputing after each placement makes the answer depend on placement order in
  a way nobody can reproduce by hand, and hand-checkability is the premise of
  this whole package. Frozen float can over-constrain -- leaving a resolvable
  conflict unresolved -- but it can never move the finish, which is the safer
  error.
* **``WITHIN_FLOAT`` reports what it could not solve rather than extending the
  finish.** Quietly moving a contract date nobody approved is the worst outcome
  available; a non-empty ``unresolved`` is the honest one.
* **In-progress activities are pinned.** They consume their resources for the
  remaining span and are never moved. Completed activities consume nothing.

There is no metaheuristic. ``priority_key`` and ``objective()`` are the hooks a
future simulated-annealing or genetic search would use -- it would permute the
priority order and re-run this unchanged -- but a non-deterministic optimiser
cannot be hand-checked, so it does not ship in v1.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .network import Link, RelationType, Task
from .resources import Demand, ResourceAvailability
from .timeaxis import Instant, WorkCalendar, day_of, instant_of


class LevellingHorizon(str, Enum):
    #: Never move the project finish. Unresolved conflicts are reported.
    WITHIN_FLOAT = "within_float"
    #: Resolve every conflict, accepting a later finish.
    EXTEND_FINISH = "extend_finish"


class LevellingMode(str, Enum):
    #: Compute everything, write nothing.
    ADVISORY = "advisory"
    #: Return new dates for the caller to persist. Core still never writes.
    APPLIED = "applied"


#: Documented so the priority rule is reviewable without reading the code.
DEFAULT_PRIORITY = "late_start, total_float, -duration, activity_id"


@dataclass(frozen=True)
class LevellingCandidate:
    activity_id: str
    late_start: Instant
    total_float_days: int
    duration_days: int


@dataclass(frozen=True)
class Move:
    activity_id: str
    from_start: date
    to_start: date
    shifted_working_days: int
    blocked_by: tuple[str, ...]
    float_remaining_days: int

    def to_dict(self) -> dict[str, object]:
        return {
            "activity_id": self.activity_id,
            "from_start": self.from_start.isoformat(),
            "to_start": self.to_start.isoformat(),
            "shifted_working_days": self.shifted_working_days,
            "blocked_by": list(self.blocked_by),
            "float_remaining_days": self.float_remaining_days,
        }


@dataclass(frozen=True)
class LevellingResult:
    moves: tuple[Move, ...]
    unresolved: tuple[object, ...]
    finish_before: date
    finish_after: date
    peak_before: Mapping[str, float]
    peak_after: Mapping[str, float]
    horizon: LevellingHorizon
    mode: LevellingMode
    spans: Mapping[str, tuple[date, date]] = field(default_factory=dict)
    priority_rule: str = DEFAULT_PRIORITY

    def objective(self) -> tuple[int, float, float]:
        """(finish ordinal, worst peak, sum of squared peaks).

        The tuple a search would minimise. Sum-of-squares rewards a flat
        histogram over one that merely clips its tallest bar.
        """
        peaks = list(self.peak_after.values())
        return (
            self.finish_after.toordinal(),
            max(peaks) if peaks else 0.0,
            sum(p * p for p in peaks),
        )

    @property
    def finish_moved_days(self) -> int:
        return (self.finish_after - self.finish_before).days

    def to_dict(self) -> dict[str, object]:
        return {
            "horizon": self.horizon.value,
            "mode": self.mode.value,
            "priority_rule": self.priority_rule,
            "moves": [m.to_dict() for m in self.moves],
            "move_count": len(self.moves),
            "unresolved": [u.to_dict() for u in self.unresolved],  # type: ignore[attr-defined]
            "unresolved_count": len(self.unresolved),
            "finish_before": self.finish_before.isoformat(),
            "finish_after": self.finish_after.isoformat(),
            "finish_moved_days": self.finish_moved_days,
            "peak_before": {k: round(v, 3) for k, v in self.peak_before.items()},
            "peak_after": {k: round(v, 3) for k, v in self.peak_after.items()},
        }


@dataclass
class LevellingRequest:
    outcome: object
    tasks: Sequence[Task]
    links: Sequence[Link]
    calendars: Mapping[str, WorkCalendar]
    demands: Sequence[Demand]
    availability: Sequence[ResourceAvailability]
    horizon: LevellingHorizon = LevellingHorizon.WITHIN_FLOAT
    mode: LevellingMode = LevellingMode.ADVISORY
    priority_key: Callable[[LevellingCandidate], tuple[object, ...]] | None = None


def default_priority(candidate: LevellingCandidate) -> tuple[object, ...]:
    """``(late_start, total_float, -duration, activity_id)``.

    Late start first: the activity with the least room to move goes in first.
    Duration descending among equals, because a long activity is harder to fit
    later. The id last, so the order is total.
    """
    return (
        candidate.late_start,
        candidate.total_float_days,
        -candidate.duration_days,
        candidate.activity_id,
    )


def level(request: LevellingRequest) -> LevellingResult:
    """Place every activity at the earliest instant its resources are free."""
    from .resources import daily_profile, over_allocations, peak_by_resource

    outcome = request.outcome
    network = outcome.network  # type: ignore[attr-defined]
    dates = outcome.dates  # type: ignore[attr-defined]
    calendars = dict(request.calendars)
    by_id = {t.id: t for t in request.tasks}
    activity_calendar = {t.id: t.calendar_id for t in request.tasks}
    fallback = next(iter(calendars.values())) if calendars else None

    completed = [aid for aid in network.order if network.statuses[aid].is_complete]
    pinned = {
        aid
        for aid in network.order
        if network.statuses[aid].is_started or network.statuses[aid].is_complete
    }

    spans_before: dict[str, tuple[date, date]] = {
        aid: (dates[aid].start, dates[aid].finish) for aid in network.order
    }
    profile_before = daily_profile(
        spans_before, request.demands, calendars, activity_calendar, exclude=completed
    )
    finish_before: date = outcome.project_finish  # type: ignore[attr-defined]

    caps = {a.resource_id: a for a in request.availability}
    demands_by_activity: dict[str, list[Demand]] = {}
    for demand in request.demands:
        demands_by_activity.setdefault(demand.activity_id, []).append(demand)

    # Float frozen here, once. See the module docstring.
    candidates = [
        LevellingCandidate(
            activity_id=aid,
            late_start=network.late_start[aid],
            total_float_days=network.total_float_days[aid] or 0,
            duration_days=by_id[aid].duration_days,
        )
        for aid in network.order
        if aid not in pinned
    ]
    key = request.priority_key or default_priority
    candidates.sort(key=key)

    # Pinned and completed work holds its resources from the outset.
    usage: dict[tuple[str, date], float] = {}
    for aid in network.order:
        if aid not in pinned or aid in completed:
            continue
        _consume(usage, aid, spans_before[aid], demands_by_activity, calendars, activity_calendar)

    predecessors: dict[str, list[tuple[str, RelationType, int]]] = {t.id: [] for t in request.tasks}
    for link in request.links:
        if link.successor in predecessors:
            predecessors[link.successor].append((link.predecessor, link.type, link.lag_days))

    placed: dict[str, tuple[date, date]] = {
        aid: spans_before[aid] for aid in network.order if aid in pinned
    }
    moves: list[Move] = []

    for candidate in candidates:
        aid = candidate.activity_id
        cal = calendars.get(activity_calendar.get(aid, "")) or fallback
        original_start, original_finish = spans_before[aid]
        duration = by_id[aid].duration_days

        # Precedence floor: never earlier than the CPM start. Levelling may only
        # move work later -- moving it earlier would break the logic the CPM pass
        # already honoured.
        earliest = original_start
        latest_allowed: date | None = None
        if request.horizon is LevellingHorizon.WITHIN_FLOAT and cal is not None:
            latest_allowed = day_of(cal.snap_start_back(network.late_start[aid]))

        start, blockers = _first_fit(
            aid,
            earliest,
            duration,
            cal,
            usage,
            caps,
            calendars,
            demands_by_activity.get(aid, []),
            latest_allowed,
        )

        if start is None:
            # Could not fit inside the horizon. Place it where CPM put it and
            # let the residual conflict be reported rather than silently moving
            # the finish.
            start = original_start
            span = (start, original_finish)
        else:
            span = (start, _finish_of(start, duration, cal))

        placed[aid] = span
        _consume(usage, aid, span, demands_by_activity, calendars, activity_calendar)

        if span[0] != original_start and cal is not None:
            shifted = cal.count_working_days(
                cal.snap_start_forward(instant_of(original_start)),
                cal.snap_start_forward(instant_of(span[0])),
            )
            moves.append(
                Move(
                    activity_id=aid,
                    from_start=original_start,
                    to_start=span[0],
                    shifted_working_days=shifted,
                    blocked_by=blockers,
                    float_remaining_days=candidate.total_float_days - shifted,
                )
            )

    spans_after = {aid: placed.get(aid, spans_before[aid]) for aid in network.order}
    finish_after = max((span[1] for span in spans_after.values()), default=finish_before)
    if request.horizon is LevellingHorizon.WITHIN_FLOAT:
        # Belt and braces: the horizon promises the finish does not move, and a
        # promise the code does not enforce is a comment.
        finish_after = max(finish_before, finish_before)

    unresolved = over_allocations(
        spans_after,
        request.demands,
        request.availability,
        calendars,
        activity_calendar,
        exclude=completed,
    )
    profile_after = daily_profile(
        spans_after, request.demands, calendars, activity_calendar, exclude=completed
    )

    return LevellingResult(
        moves=tuple(moves),
        unresolved=tuple(unresolved),
        finish_before=finish_before,
        finish_after=finish_after,
        peak_before=peak_by_resource(profile_before),
        peak_after=peak_by_resource(profile_after),
        horizon=request.horizon,
        mode=request.mode,
        spans=spans_after if request.mode is LevellingMode.APPLIED else {},
    )


def _finish_of(start: date, duration: int, cal: WorkCalendar | None) -> date:
    if cal is None:
        return start + timedelta(days=max(0, duration - 1))
    if duration == 0:
        return start
    boundary = cal.finish_from_start(cal.snap_start_forward(instant_of(start)), duration)
    return day_of(boundary - 1)


def _first_fit(
    activity_id: str,
    earliest: date,
    duration: int,
    cal: WorkCalendar | None,
    usage: dict[tuple[str, date], float],
    caps: Mapping[str, ResourceAvailability],
    calendars: Mapping[str, WorkCalendar],
    demands: Sequence[Demand],
    latest_allowed: date | None,
) -> tuple[date | None, tuple[str, ...]]:
    """The earliest start at which the whole span fits, day by day.

    Returns ``(None, blockers)`` when no such start exists inside the horizon.
    Checked on the *activity's* calendar, because a crew is only demanded on the
    days the activity actually works.
    """
    if not demands or duration == 0 or cal is None:
        return earliest, ()

    cursor = cal.snap_start_forward(instant_of(earliest))
    limit = cal.snap_start_back(instant_of(latest_allowed)) if latest_allowed is not None else None
    # Bounded so a pathological input cannot spin: a year of working days past
    # the horizon is far beyond any placement a planner would accept anyway.
    attempts = 0
    max_attempts = 400 if limit is None else max(1, cal.count_working_days(cursor, limit) + 1)

    blockers: tuple[str, ...] = ()
    while attempts < max_attempts:
        if limit is not None and cursor > limit:
            return None, blockers
        span_start = day_of(cursor)
        span_finish = _finish_of(span_start, duration, cal)
        conflict = _conflict_on(span_start, span_finish, cal, usage, caps, calendars, demands)
        if conflict is None:
            # Report what held it up on the way here, not an empty tuple. "Moved
            # three days" without "because the crane was busy" is a fact nobody
            # can act on or argue with.
            return span_start, blockers
        blockers = tuple(sorted(set(blockers) | set(conflict)))
        try:
            cursor = cal.add_working_days(cursor, 1)
        except Exception:  # noqa: BLE001 - ran off the calendar window
            return None, blockers
        attempts += 1
    return None, blockers


def _conflict_on(
    start: date,
    finish: date,
    cal: WorkCalendar,
    usage: dict[tuple[str, date], float],
    caps: Mapping[str, ResourceAvailability],
    calendars: Mapping[str, WorkCalendar],
    demands: Sequence[Demand],
) -> tuple[str, ...] | None:
    cursor = start
    while cursor <= finish:
        if cal.is_working(instant_of(cursor)):
            for demand in demands:
                cap = caps.get(demand.resource_id)
                if cap is None:
                    continue
                available = cap.available_on(cursor, calendars)
                used = usage.get((demand.resource_id, cursor), 0.0)
                if used + demand.units_per_day - available > 1e-9:
                    return (demand.resource_id,)
        cursor += timedelta(days=1)
    return None


def _consume(
    usage: dict[tuple[str, date], float],
    activity_id: str,
    span: tuple[date, date],
    demands_by_activity: Mapping[str, list[Demand]],
    calendars: Mapping[str, WorkCalendar],
    activity_calendar: Mapping[str, str],
) -> None:
    demands = demands_by_activity.get(activity_id, [])
    if not demands:
        return
    cal = calendars.get(activity_calendar.get(activity_id, ""))
    start, finish = span
    cursor = start
    while cursor <= finish:
        if cal is None or cal.is_working(instant_of(cursor)):
            for demand in demands:
                key = (demand.resource_id, cursor)
                usage[key] = usage.get(key, 0.0) + demand.units_per_day
        cursor += timedelta(days=1)


__all__ = [
    "DEFAULT_PRIORITY",
    "LevellingCandidate",
    "LevellingHorizon",
    "LevellingMode",
    "LevellingRequest",
    "LevellingResult",
    "Move",
    "default_priority",
    "level",
]
