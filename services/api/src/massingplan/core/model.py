"""The format-neutral schedule model -- the hub of a hub-and-spoke converter.

Every reader produces one of these and every writer consumes one, so adding the
Nth format costs one adapter rather than N-1 converters. It is also the shape
the application layer persists, which is why it carries things the scheduler
does not use -- notes, activity codes, user-defined fields, resource costs. A
round trip that silently drops a planner's activity codes is a round trip nobody
will run twice.

Ported from ibuilder/AIHackScheduler ``core/exchange.py`` (MIT), with three
deliberate changes:

* ``warnings: list[str]`` becomes an :class:`IssueLog`. See ``issues.py``.
* ``Calendar`` carries real exceptions, and converts to a :class:`WorkCalendar`.
* **``to_cpm()`` is deleted.** It was the lossy reduction that dropped calendars,
  constraints and actuals -- the exact defect this engine exists to fix. Leaving
  it in place as a convenience guarantees somebody calls it and gets single
  calendar, FS-only answers from a multi-calendar schedule, with no error.
  :meth:`ExchangeSchedule.to_network` replaces it and loses nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from .constraints import ConstraintType
from .issues import IssueLog
from .network import ActivityKind, Link, RelationType, SchedulerOptions, Task
from .timeaxis import WorkCalendar, WorkPattern
from .units import HOURS_PER_DAY_DEFAULT, days_from_hours, hours_from_days


@dataclass
class CalendarException:
    """A day that departs from the weekly pattern.

    ``working`` distinguishes a shutdown from a make-up day. Both are exceptions;
    only one subtracts.
    """

    day: date
    working: bool = False
    name: str = ""


@dataclass
class Calendar:
    """A named work pattern as the source file describes it.

    Kept separate from :class:`~massingplan.core.timeaxis.WorkCalendar` because
    this one is a record of what the file said -- mutable, partially populated,
    possibly contradictory -- and that one is a frozen object the scheduler can
    share safely across a Monte Carlo run.
    """

    id: str
    name: str = ""
    working_weekdays: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})
    exceptions: list[CalendarException] = field(default_factory=list)
    hours_per_day: float = HOURS_PER_DAY_DEFAULT
    is_default: bool = False

    def __post_init__(self) -> None:
        if self.hours_per_day <= 0:
            raise ValueError(f"calendar {self.id!r}: hours_per_day must be positive")

    @property
    def holidays(self) -> frozenset[date]:
        return frozenset(e.day for e in self.exceptions if not e.working)

    @property
    def extra_work_days(self) -> frozenset[date]:
        return frozenset(e.day for e in self.exceptions if e.working)

    def hours_to_days(self, hours: float | None) -> int:
        return days_from_hours(hours, self.hours_per_day)

    def days_to_hours(self, days: int) -> float:
        return hours_from_days(days, self.hours_per_day)

    def to_work_calendar(self) -> WorkCalendar:
        return WorkCalendar(
            id=self.id,
            name=self.name or self.id,
            pattern=WorkPattern(
                working_weekdays=frozenset(self.working_weekdays),
                holidays=self.holidays,
                extra_work_days=self.extra_work_days,
            ),
            hours_per_day=self.hours_per_day,
        )


@dataclass
class WBSNode:
    id: str
    name: str
    parent_id: str | None = None
    code: str = ""
    sequence: int = 0


@dataclass
class ExchangeResource:
    id: str
    name: str
    type: str = "labor"
    unit: str = ""
    unit_cost: float | None = None
    max_units_per_day: float | None = None
    calendar_id: str | None = None


@dataclass
class ExchangeAssignment:
    activity_id: str
    resource_id: str
    units_per_day: float | None = None
    budgeted_units: float | None = None
    budgeted_cost: float | None = None
    actual_cost: float | None = None


@dataclass
class ExchangeActivity:
    """One activity, with everything any supported format can say about it."""

    id: str
    name: str = ""
    kind: ActivityKind = ActivityKind.TASK
    wbs_id: str | None = None
    calendar_id: str | None = None
    duration_days: int = 0
    remaining_duration_days: int | None = None
    early_start: date | None = None
    early_finish: date | None = None
    late_start: date | None = None
    late_finish: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    constraint: ConstraintType = ConstraintType.NONE
    constraint_date: date | None = None
    secondary_constraint: ConstraintType = ConstraintType.NONE
    secondary_constraint_date: date | None = None
    suspend_date: date | None = None
    resume_date: date | None = None
    duration_percent_complete: float | None = None
    physical_percent_complete: float | None = None
    total_float_days: int | None = None
    free_float_days: int | None = None
    is_longest_path: bool = False
    #: The planner's own identifier -- ``A1010``. Survives a re-baseline, unlike
    #: the internal id, which is why ``compare`` can match on it.
    code: str = ""
    trade: str = ""
    location: str = ""
    notes: str = ""
    activity_codes: dict[str, str] = field(default_factory=dict)
    udf: dict[str, str | float | date | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind.is_milestone and self.duration_days:
            raise ValueError(f"{self.id}: a {self.kind.value} cannot have a duration")

    @property
    def is_complete(self) -> bool:
        """Driven by the recorded finish, not by a status label.

        A label can say "complete" while the finish date is empty; the date is
        the stronger statement, and it is the one the engine can compute with.
        """
        return self.actual_finish is not None

    @property
    def is_started(self) -> bool:
        return self.actual_start is not None

    @property
    def percent_complete(self) -> float | None:
        """Physical percent if the file carried it, else duration percent.

        Physical first because it is a claim about the work; duration percent is
        a claim about elapsed time, and on a stalled activity those diverge.
        """
        if self.physical_percent_complete is not None:
            return self.physical_percent_complete
        return self.duration_percent_complete


@dataclass
class ExchangeRelationship:
    predecessor_id: str
    successor_id: str
    type: RelationType = RelationType.FS
    lag_days: int = 0


@dataclass
class ExchangeSchedule:
    """A whole schedule, as read from or written to a file."""

    project_id: str = ""
    project_name: str = ""
    data_date: date | None = None
    planned_start: date | None = None
    must_finish_by: date | None = None
    default_calendar_id: str | None = None
    calendars: list[Calendar] = field(default_factory=list)
    wbs: list[WBSNode] = field(default_factory=list)
    activities: list[ExchangeActivity] = field(default_factory=list)
    relationships: list[ExchangeRelationship] = field(default_factory=list)
    resources: list[ExchangeResource] = field(default_factory=list)
    assignments: list[ExchangeAssignment] = field(default_factory=list)
    options: SchedulerOptions = field(default_factory=SchedulerOptions)
    issues: IssueLog = field(default_factory=IssueLog)
    source_format: str = ""

    # -- lookups -----------------------------------------------------------

    def activity(self, activity_id: str) -> ExchangeActivity | None:
        return next((a for a in self.activities if a.id == activity_id), None)

    def calendar(self, calendar_id: str | None) -> Calendar | None:
        if calendar_id is None:
            return None
        return next((c for c in self.calendars if c.id == calendar_id), None)

    def default_calendar(self) -> Calendar | None:
        explicit = self.calendar(self.default_calendar_id)
        if explicit is not None:
            return explicit
        flagged = next((c for c in self.calendars if c.is_default), None)
        if flagged is not None:
            return flagged
        return self.calendars[0] if self.calendars else None

    def calendar_for(self, activity: ExchangeActivity) -> Calendar | None:
        return self.calendar(activity.calendar_id) or self.default_calendar()

    # -- validation --------------------------------------------------------

    def validate(self) -> list[str]:
        """Every problem at once, as a list -- not the first one, as an exception.

        An import that reports one error per run makes the operator fix, re-run,
        fix, re-run. Ten problems in one pass is one conversation.
        """
        problems: list[str] = []

        seen: set[str] = set()
        for a in self.activities:
            if a.id in seen:
                problems.append(f"duplicate activity id {a.id!r}")
            seen.add(a.id)
            if a.duration_days < 0:
                problems.append(f"{a.id}: negative duration {a.duration_days}")
            if a.constraint.needs_date and a.constraint_date is None:
                problems.append(f"{a.id}: constraint {a.constraint.value} has no constraint date")
            if a.actual_finish and not a.actual_start:
                problems.append(f"{a.id}: has an actual finish but no actual start")
            if a.actual_start and a.actual_finish and a.actual_finish < a.actual_start:
                problems.append(
                    f"{a.id}: actual finish {a.actual_finish} precedes start {a.actual_start}"
                )
            if a.calendar_id and self.calendar(a.calendar_id) is None:
                problems.append(f"{a.id}: references unknown calendar {a.calendar_id!r}")
            if a.wbs_id and not any(w.id == a.wbs_id for w in self.wbs):
                problems.append(f"{a.id}: references unknown WBS node {a.wbs_id!r}")

        for r in self.relationships:
            if r.predecessor_id not in seen:
                problems.append(f"relationship references unknown predecessor {r.predecessor_id!r}")
            if r.successor_id not in seen:
                problems.append(f"relationship references unknown successor {r.successor_id!r}")
            if r.predecessor_id == r.successor_id:
                problems.append(f"{r.predecessor_id}: depends on itself")

        resource_ids = {r.id for r in self.resources}
        for asg in self.assignments:
            if asg.activity_id not in seen:
                problems.append(f"assignment references unknown activity {asg.activity_id!r}")
            if asg.resource_id not in resource_ids:
                problems.append(f"assignment references unknown resource {asg.resource_id!r}")

        wbs_ids = {w.id for w in self.wbs}
        for node in self.wbs:
            if node.parent_id and node.parent_id not in wbs_ids:
                problems.append(f"WBS {node.id!r}: unknown parent {node.parent_id!r}")

        if not self.calendars:
            problems.append("no calendars: every activity would fall back to a guess")

        return problems

    # -- conversion --------------------------------------------------------

    def work_calendars(self) -> dict[str, WorkCalendar]:
        """The frozen calendars the scheduler works with."""
        if not self.calendars:
            from .timeaxis import standard_calendar

            return {"STD": standard_calendar()}
        return {c.id: c.to_work_calendar() for c in self.calendars}

    def to_network(self) -> tuple[list[Task], list[Link], dict[str, WorkCalendar]]:
        """Reduce to the scheduler's inputs, losing nothing the scheduler uses.

        The replacement for the deleted ``to_cpm()``. Where that dropped
        calendars, constraints and actuals on the floor, this carries all three,
        and the things it genuinely does not need -- notes, codes, costs -- stay
        on this object for the writer to pick up again.
        """
        calendars = self.work_calendars()
        default_id = self.default_calendar() or next(iter(self.calendars), None)
        fallback = default_id.id if default_id else next(iter(calendars))

        tasks: list[Task] = []
        for a in self.activities:
            if a.kind.is_derived:
                # Summary bars and level-of-effort spans are rollups of their
                # children. Scheduling them as work would double-count it.
                continue
            tasks.append(
                Task(
                    id=a.id,
                    name=a.name,
                    duration_days=a.duration_days,
                    calendar_id=a.calendar_id or fallback,
                    kind=a.kind,
                    constraint=a.constraint,
                    constraint_date=a.constraint_date,
                    actual_start=a.actual_start,
                    actual_finish=a.actual_finish,
                    remaining_days=a.remaining_duration_days,
                    percent_complete=a.percent_complete,
                )
            )

        scheduled = {t.id for t in tasks}
        links = [
            Link(r.predecessor_id, r.successor_id, r.type, r.lag_days)
            for r in self.relationships
            if r.predecessor_id in scheduled and r.successor_id in scheduled
        ]
        return tasks, links, calendars

    def summary(self) -> dict[str, object]:
        by_kind: dict[str, int] = {}
        for a in self.activities:
            by_kind[a.kind.value] = by_kind.get(a.kind.value, 0) + 1
        by_type: dict[str, int] = {}
        for r in self.relationships:
            by_type[r.type.value] = by_type.get(r.type.value, 0) + 1
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "source_format": self.source_format,
            "data_date": self.data_date.isoformat() if self.data_date else None,
            "activities": len(self.activities),
            "activities_by_kind": by_kind,
            "relationships": len(self.relationships),
            "relationships_by_type": by_type,
            "calendars": len(self.calendars),
            "wbs_nodes": len(self.wbs),
            "resources": len(self.resources),
            "assignments": len(self.assignments),
            "issues": len(self.issues),
        }

    def replace_activities(self, activities: Iterable[ExchangeActivity]) -> ExchangeSchedule:
        """A shallow copy carrying new activities.

        Used by ``apply_to`` so computing a schedule never mutates the object the
        caller handed in -- a failed database write would otherwise leave a
        half-updated schedule in memory that the next request reads as truth.
        """
        import copy

        clone = copy.copy(self)
        clone.activities = list(activities)
        return clone
