"""Location-based (linear) scheduling: line of balance, and the flow behind it.

CPM answers "when can this activity start". It cannot answer the question a
construction planner actually has, which is **"where is each crew, and does
anyone get in anyone else's way"**. A tower is the same twelve trades repeated
on forty floors; a road is the same six operations repeated along ten
kilometres. CPM models that as 480 independent activities and has no concept
that one gang does all forty floors of drywall in order.

The thing CPM structurally cannot express is **crew continuity**. Its forward
pass gives every activity its earliest start, which is exactly what fragments a
crew: work a floor, wait, work a floor, wait. A subcontractor cannot be
demobilised and remobilised eleven times, so a schedule that assumes it is a
schedule that will not be followed -- and a schedule nobody follows produces
delay claims rather than buildings.

What this module does
---------------------
It is **not a second scheduler**. It computes where each crew's line has to sit
so the crew never waits and never trespasses, and then emits an ordinary
network -- one activity per (task x location), the crew chain, the handover
logic, and a start constraint pinning the line. The existing engine schedules
that, so calendars, constraints, actuals, DCMA, risk, levelling and baseline
comparison all keep working. Nothing downstream has to learn a new shape.

The line-shift, which is the whole calculation
----------------------------------------------
For a task `t` following `p`, with `d[L]` working days in location `L`::

    offset(t, L) = sum(d[0 .. L-1])              # from the crew's own start
    start(t, L)  = S(t) + offset(t, L)           # continuity, by construction
    S(t)         = max over L of
                     ( finish(p, L) + buffer - offset(t, L) )

That `max` is the entire idea. Taking the maximum over **every** location, not
just the first, is what stops the successor overtaking the predecessor
somewhere in the middle of the building -- which is what happens when the
successor is the faster trade, and what a Gantt chart cannot show you.

The location achieving the maximum is the **binding location**: the one place
where the buffer is exactly consumed, and therefore the place a slip is felt
first. It is reported, because "your schedule is tight on level 7" is actionable
and "your float is 3 days" is not.

Deliberate limits, stated rather than discovered
------------------------------------------------
* **One calendar.** The flow arithmetic is in working days, so mixing calendars
  between tasks would compare quantities that are not commensurable -- the same
  error the engine's absolute time axis exists to prevent. Differing calendars
  raise an issue rather than being averaged.
* **One crew per task.** Splitting a task across parallel crews changes the
  slope and the continuity rule, and guessing at it would produce a plausible
  wrong answer. `crews > 1` raises an issue and is scheduled as one crew.
* **Constant crew direction.** Every task runs locations in the same order.
  Reverse flow is real (strip-out often runs top-down) and is not modelled here.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date

from .constraints import ConstraintType
from .issues import IssueLog
from .network import Link, RelationType, Task
from .timeaxis import WorkCalendar, day_of, instant_of, standard_calendar
from .units import ROUNDING_EPSILON


class LinearScheduleError(ValueError):
    """The location model cannot be scheduled as stated."""


@dataclass(frozen=True)
class Location:
    """One place work happens, in flow order.

    `sequence` is explicit rather than the list index, because a location
    breakdown is edited -- a floor is added, a zone is split -- and an implicit
    index silently renumbers everything below it.
    """

    id: str
    name: str = ""
    sequence: int = 0

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise LinearScheduleError("every location needs an id")


@dataclass
class LinearTask:
    """One trade, flowing through the locations in order.

    Duration per location comes from `quantities` and `rate` when both are
    given, and from `duration_days` otherwise. Quantities are the honest input
    -- 380 m2 of slab at 95 m2/day is a fact about the work, where "4 days" is
    a fact about somebody's arithmetic -- but a planner without a take-off must
    still be able to say four days.
    """

    id: str
    name: str = ""
    #: Working days in each location, keyed by location id. Used when there is
    #: no quantity/rate pair for that location.
    duration_days: int = 1
    #: Quantity of work per location id, in whatever unit `rate` is per day.
    quantities: dict[str, float] = field(default_factory=dict)
    #: Units per working day for one crew. Must be positive when quantities are
    #: supplied; a zero rate is a division by zero wearing a hat.
    rate: float | None = None
    #: Working days between this task finishing a location and the next task
    #: starting it. Negative is legal and means deliberate overlap.
    buffer_days: int = 0
    crews: int = 1
    calendar_id: str = "STD"

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise LinearScheduleError("every task needs an id")
        if self.duration_days < 0:
            raise LinearScheduleError(f"{self.id}: duration_days cannot be negative")
        if self.rate is not None and self.rate <= 0:
            raise LinearScheduleError(
                f"{self.id}: a production rate must be positive, not {self.rate}"
            )


@dataclass(frozen=True)
class Segment:
    """One task in one location: the unit the emitted network is built from."""

    task_id: str
    location_id: str
    start_offset: int
    duration_days: int

    @property
    def finish_offset(self) -> int:
        """Half-open, like everywhere else: the first day *not* worked."""
        return self.start_offset + self.duration_days

    @property
    def activity_id(self) -> str:
        return f"{self.task_id}@{self.location_id}"


@dataclass(frozen=True)
class Interference:
    """Where two consecutive tasks come closest, and by how much.

    `gap_days` is the *actual* clearance at the binding location after the line
    has been shifted. It equals the requested buffer when the two tasks run at
    the same pace, and it is the requested buffer at exactly one location when
    they do not -- which is the point of reporting the location.
    """

    predecessor_id: str
    successor_id: str
    location_id: str
    gap_days: int
    converging: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "predecessor_id": self.predecessor_id,
            "successor_id": self.successor_id,
            "location_id": self.location_id,
            "gap_days": self.gap_days,
            "converging": self.converging,
        }


@dataclass(frozen=True)
class LinearResult:
    """The computed flow, and what it cost to keep the crews continuous."""

    segments: tuple[Segment, ...]
    interferences: tuple[Interference, ...]
    issues: IssueLog
    #: Working days from the project start to the last location of the last task.
    duration_days: int
    #: Per task, the days its crew was pushed later than its earliest possible
    #: start in order not to be fragmented. This is the price of continuity, and
    #: it is the number that decides whether location-based scheduling is worth
    #: it on this job -- so it is reported rather than absorbed.
    continuity_cost_days: dict[str, int]

    def by_task(self, task_id: str) -> tuple[Segment, ...]:
        return tuple(s for s in self.segments if s.task_id == task_id)

    def to_rows(self, *, start: date, calendar: WorkCalendar) -> list[dict[str, object]]:
        """Offsets rendered as dates. **The only conversion site in this module.**

        Everything above is working-day arithmetic on one calendar; a second
        place that turned offsets into dates would be a second place to get the
        half-open convention wrong.
        """
        origin = calendar.snap_start_forward(instant_of(start))
        rows = []
        for segment in self.segments:
            begins = calendar.add_working_days(origin, segment.start_offset)
            ends = calendar.add_working_days(origin, segment.finish_offset)
            # `ends - 1` is the calendar day before the boundary, which is not
            # necessarily a *working* day: a location that finishes on a Friday
            # has its boundary on the Monday, and a bare `- 1` prints Sunday.
            # `snap_start_back` returns the last day actually worked, which is
            # what `schedule._present` does for exactly the same reason.
            last_worked = calendar.snap_start_back(ends - 1) if ends > begins else begins
            rows.append(
                {
                    "activity_id": segment.activity_id,
                    "task_id": segment.task_id,
                    "location_id": segment.location_id,
                    "start": day_of(begins).isoformat(),
                    "finish": day_of(last_worked).isoformat(),
                    "duration_days": segment.duration_days,
                }
            )
        return rows


def _durations(
    task: LinearTask, locations: tuple[Location, ...], issues: IssueLog
) -> dict[str, int]:
    """Working days per location, from quantity and rate or from the flat value.

    The only rounding in this module, and it rounds **up**: two-thirds of a
    crew-day is a day on site. `ROUNDING_EPSILON` is applied for the same reason
    `units.py` applies it -- `380 / 95` is not always exactly `4.0` in binary,
    and without it a four-day activity becomes five.
    """
    out: dict[str, int] = {}
    for location in locations:
        quantity = task.quantities.get(location.id)
        if quantity is None or task.rate is None:
            if quantity is not None and task.rate is None:
                issues.warn(
                    "LOB.NO_RATE",
                    f"{task.id} has a quantity for {location.id} but no production rate",
                    f"used the flat duration of {task.duration_days} days",
                    row_key=task.id,
                    field_name="rate",
                )
            out[location.id] = task.duration_days
            continue
        if quantity < 0:
            raise LinearScheduleError(
                f"{task.id}: a negative quantity in {location.id} is not work"
            )
        out[location.id] = max(0, math.ceil(quantity / task.rate - ROUNDING_EPSILON))
    return out


def compute(
    tasks: list[LinearTask],
    locations: list[Location],
    *,
    issues: IssueLog | None = None,
) -> LinearResult:
    """Place every crew's line so it never waits and never trespasses.

    `tasks` are in handover order: each follows the one before it through every
    location. `locations` are sorted by `sequence`, which is the direction of
    flow.
    """
    issues = issues if issues is not None else IssueLog()
    if not tasks:
        raise LinearScheduleError("a linear schedule needs at least one task")
    if not locations:
        raise LinearScheduleError("a linear schedule needs at least one location")

    ordered = tuple(sorted(locations, key=lambda loc: (loc.sequence, loc.id)))
    seen: set[str] = set()
    for location in ordered:
        if location.id in seen:
            raise LinearScheduleError(f"duplicate location id {location.id!r}")
        seen.add(location.id)

    calendars = {t.calendar_id for t in tasks}
    if len(calendars) > 1:
        issues.warn(
            "LOB.MIXED_CALENDARS",
            "the tasks name more than one calendar: " + ", ".join(sorted(calendars)),
            f"the flow was computed in working days on {sorted(calendars)[0]}",
            field_name="calendar_id",
        )

    durations = {t.id: _durations(t, ordered, issues) for t in tasks}
    for task in tasks:
        if task.crews > 1:
            issues.warn(
                "LOB.CREWS_NOT_MODELLED",
                f"{task.id} asks for {task.crews} crews",
                "scheduled as one continuous crew; parallel crews change the "
                "slope and are not modelled",
                row_key=task.id,
                field_name="crews",
            )
        if all(d == 0 for d in durations[task.id].values()):
            issues.warn(
                "LOB.ZERO_DURATION",
                f"{task.id} takes no time in any location",
                "kept in the flow as a zero-length line",
                row_key=task.id,
            )

    # Offset of each location's start from the crew's own start. Continuity is
    # this line and nothing else: location L begins the instant L-1 ends.
    cumulative: dict[str, dict[str, int]] = {}
    for task in tasks:
        running = 0
        per_location = {}
        for location in ordered:
            per_location[location.id] = running
            running += durations[task.id][location.id]
        cumulative[task.id] = per_location

    segments: list[Segment] = []
    interferences: list[Interference] = []
    continuity_cost: dict[str, int] = {}
    finishes: dict[str, dict[str, int]] = {}
    previous: LinearTask | None = None

    for task in tasks:
        if previous is None:
            crew_start = 0
            earliest_possible = 0
        else:
            # The line shift. The maximum over *every* location, not just the
            # first -- taking only the first is what lets a faster successor
            # overtake its predecessor halfway up the building.
            requirements = [
                finishes[previous.id][loc.id] + task.buffer_days - cumulative[task.id][loc.id]
                for loc in ordered
            ]
            crew_start = max(requirements)
            # What CPM alone would have given the crew: the earliest it could
            # begin location 0, ignoring what happens to it further up.
            earliest_possible = requirements[0]

        crew_start = max(0, crew_start)
        continuity_cost[task.id] = max(0, crew_start - max(0, earliest_possible))

        per_location_finish = {}
        for location in ordered:
            offset = crew_start + cumulative[task.id][location.id]
            segments.append(Segment(task.id, location.id, offset, durations[task.id][location.id]))
            per_location_finish[location.id] = offset + durations[task.id][location.id]
        finishes[task.id] = per_location_finish

        if previous is not None:
            gaps = {
                loc.id: (crew_start + cumulative[task.id][loc.id]) - finishes[previous.id][loc.id]
                for loc in ordered
            }
            binding = min(gaps, key=lambda loc_id: (gaps[loc_id], loc_id))
            # Converging when the clearance shrinks along the flow: the
            # successor is the faster trade and is catching up. That is the
            # case where a slip in the predecessor is felt immediately at the
            # far end, and it is invisible on a bar chart.
            first, last = ordered[0].id, ordered[-1].id
            interferences.append(
                Interference(
                    predecessor_id=previous.id,
                    successor_id=task.id,
                    location_id=binding,
                    gap_days=gaps[binding],
                    converging=gaps[last] < gaps[first],
                )
            )
            if gaps[binding] < 0:
                issues.error(
                    "LOB.OVERLAP",
                    f"{task.id} starts {abs(gaps[binding])} days before {previous.id} "
                    f"finishes in {binding}",
                    "the buffer is negative, so the two trades share the space",
                    row_key=task.id,
                    field_name="buffer_days",
                )

        previous = task

    duration = max((s.finish_offset for s in segments), default=0)
    return LinearResult(
        segments=tuple(segments),
        interferences=tuple(interferences),
        issues=issues,
        duration_days=duration,
        continuity_cost_days=continuity_cost,
    )


def to_network(
    result: LinearResult,
    tasks: list[LinearTask],
    locations: list[Location],
    *,
    start: date,
    calendar: WorkCalendar | None = None,
) -> tuple[list[Task], list[Link], dict[str, WorkCalendar]]:
    """The flow as an ordinary network, so the existing engine can schedule it.

    This is what keeps location-based scheduling from becoming a second product
    inside the first. One activity per (task x location), two kinds of link, and
    a start constraint pinning each crew's line:

    * **crew continuity** -- `(t, L-1) -> (t, L)` Finish-Start, no lag. The gang
      moves to the next location the moment it finishes this one.
    * **handover** -- `(p, L) -> (t, L)` Finish-Start with the buffer as lag.
      The following trade cannot enter a location the preceding one still holds.

    The links alone would let CPM fragment a crew again, because its forward
    pass takes the earliest start everywhere. The `START_ON_OR_AFTER` constraint
    on each task's first location is what holds the whole line where `compute`
    put it. It is a *soft* constraint, so it never overrides logic -- if it ever
    disagrees with the network, the network wins and the violation is reported
    rather than silently obeyed.
    """
    cal = calendar or standard_calendar()
    origin = cal.snap_start_forward(instant_of(start))
    by_task = {t.id: t for t in tasks}
    ordered = tuple(sorted(locations, key=lambda loc: (loc.sequence, loc.id)))
    order = [loc.id for loc in ordered]

    segments = {(s.task_id, s.location_id): s for s in result.segments}
    out_tasks: list[Task] = []
    links: list[Link] = []

    for task in tasks:
        for index, location_id in enumerate(order):
            segment = segments[(task.id, location_id)]
            first = index == 0
            out_tasks.append(
                Task(
                    id=segment.activity_id,
                    name=f"{by_task[task.id].name or task.id} — {location_id}",
                    duration_days=segment.duration_days,
                    calendar_id=task.calendar_id,
                    constraint=ConstraintType.START_ON_OR_AFTER if first else ConstraintType.NONE,
                    constraint_date=(
                        day_of(cal.add_working_days(origin, segment.start_offset))
                        if first
                        else None
                    ),
                )
            )
            if index:
                links.append(
                    Link(
                        f"{task.id}@{order[index - 1]}",
                        segment.activity_id,
                        RelationType.FS,
                        0,
                    )
                )

    for previous, task in itertools.pairwise(tasks):
        for location_id in order:
            links.append(
                Link(
                    f"{previous.id}@{location_id}",
                    f"{task.id}@{location_id}",
                    RelationType.FS,
                    task.buffer_days,
                )
            )

    return out_tasks, links, {cal.id: cal}
