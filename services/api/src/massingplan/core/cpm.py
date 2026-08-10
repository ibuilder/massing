"""Multi-calendar forward and backward pass.

Works on absolute instants (``date.toordinal()``) with half-open spans, so every
activity may carry its own calendar and the comparisons between them are still
meaningful. See SPEC.md 4 for why working-day offsets -- which both source
engines used -- silently compare dates nine days apart and call them equal.

The precedence stack
--------------------
When several things want to move the same activity, this is the order. It is
asserted by ``test_the_precedence_stack_holds_when_everything_applies_at_once``.

1. **Actual dates.** Recorded history. Nothing moves an actual.
2. **Data date floor.** No remaining work is scheduled before the data date.
3. **Mandatory constraints.** Override logic in both passes; still floored
   by (2), and the violation is recorded with ``overridden_by="data_date"``.
4. **Soft constraints.** Never override logic. An unmet one is negative float
   plus a :class:`ConstraintViolation`.
5. **Network logic and lag.**
6. **Calendar snapping.** Always last inside the pass; every computed date lands
   on a working day of the activity's own calendar.
7. **ALAP post-pass.** Shift right by *free* float, in reverse topological
   order. Shifting by total float would move the project finish, which is
   precisely what ALAP is defined never to do.
8. **Resource levelling.** A separate module, strictly after this one.

Float
-----
Measured in the **activity's own calendar's working days**, and signed. Float in
calendar days makes an activity with five days of slack across a Christmas
shutdown report fourteen, so DCMA check 6 fires on healthy schedules and check 7
misses real ones.

Free float is **not clamped at zero**. The source engine's ``max(0, free)`` is a
defect not to port: under retained logic, or with a mandatory constraint,
negative free float is exactly the signal that a recorded actual contradicts the
remaining logic.

The driving path
----------------
Recovered by recording, per activity, which incoming link produced the
forward-pass maximum, then walking those links backwards from the activity that
actually sets the project finish. The source engine instead collected every
zero-float activity and walked forward greedily, which returns an arbitrary
branch when two are equally critical and changes its answer when the input list
is reordered.

Portions derive from ibuilder/AIHackScheduler ``core/cpm.py`` (MIT).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from .constraints import EFFECTS, ConstraintType, ConstraintViolation, check, early_floor, late_cap
from .graph import driving_chain, topological_order, validate_network
from .issues import IssueLog
from .network import (
    ActivityKind,
    LagCalendar,
    Link,
    ProgressMode,
    RelationType,
    SchedulerOptions,
    Status,
    Task,
)
from .progress_logic import ActivityStatus, derive_status, effective_links
from .timeaxis import Instant, WorkCalendar, day_of, instant_of


class UnknownCalendarError(KeyError):
    """An activity names a calendar the caller did not supply."""


@dataclass(frozen=True)
class NetworkResult:
    """Everything the passes computed, in instants. Dates are presented elsewhere."""

    early_start: Mapping[str, Instant]
    early_finish: Mapping[str, Instant]
    late_start: Mapping[str, Instant]
    late_finish: Mapping[str, Instant]
    total_float_days: Mapping[str, int | None]
    free_float_days: Mapping[str, int | None]
    project_start: Instant
    project_finish: Instant
    #: The instant the schedule was computed *from*. Carried because DCMA checks
    #: 9, 11 and 14 all compare against it, and deriving it downstream as "the
    #: earliest early start" is wrong the moment anything carries an actual --
    #: which is exactly when those three checks become runnable.
    data_date: Instant
    driving_predecessor: Mapping[str, str | None]
    terminal_activity: str | None
    violations: tuple[ConstraintViolation, ...]
    statuses: Mapping[str, ActivityStatus]
    options: SchedulerOptions
    order: tuple[str, ...]
    suppressed_links: tuple[Link, ...] = ()
    #: The calendars actually used, including any this function had to
    #: synthesise. Carried on the result because the caller may have passed
    #: none, and the presenter needs the same objects to convert instants back
    #: to dates -- resolving them a second time is how the two ends of the
    #: conversion drift apart.
    calendars: Mapping[str, WorkCalendar] = field(default_factory=dict)

    def is_critical(self, activity_id: str) -> bool:
        """Zero or negative total float, and not already finished.

        Completed activities are excluded deliberately. They have no float --
        their dates are history -- and counting them floods the critical path
        with work that already happened and inflates DCMA check 7's negative
        float count.
        """
        tf = self.total_float_days.get(activity_id)
        return tf is not None and tf <= 0

    def longest_path(self) -> list[str]:
        """The driving chain that sets the project finish. Order-independent."""
        return driving_chain(self.driving_predecessor, self.terminal_activity)

    @property
    def critical_ids(self) -> list[str]:
        return [aid for aid in self.order if self.is_critical(aid)]


def _resolve_calendar(
    task: Task, calendars: Mapping[str, WorkCalendar], issues: IssueLog
) -> WorkCalendar:
    cal = calendars.get(task.calendar_id)
    if cal is not None:
        return cal
    if not calendars:
        raise UnknownCalendarError("no calendars supplied")
    fallback = next(iter(calendars.values()))
    issues.warn(
        "CPM.CALENDAR_MISSING",
        f"{task.id}: calendar {task.calendar_id!r} was not supplied",
        f"fell back to {fallback.id!r}",
        row_key=task.id,
        field_name="calendar_id",
        raw_value=task.calendar_id,
    )
    return fallback


#: Which end of an activity a value refers to. Lag arithmetic differs between
#: the two, and conflating them is a one-day error that only shows up on links
#: that cross a weekend -- so it survives every test written on a seven-day
#: calendar.
_START_SPACE = "start"
_FINISH_SPACE = "finish"


def _lag_calendar(
    mode: LagCalendar,
    *,
    pred_cal: WorkCalendar,
    succ_cal: WorkCalendar,
    project_cal: WorkCalendar,
) -> WorkCalendar:
    if mode is LagCalendar.SUCCESSOR:
        return succ_cal
    if mode is LagCalendar.PROJECT_DEFAULT:
        return project_cal
    return pred_cal


def _advance_lag(
    at: Instant,
    lag_days: int,
    space: str,
    *,
    pred_cal: WorkCalendar,
    succ_cal: WorkCalendar,
    mode: LagCalendar,
    project_cal: WorkCalendar,
) -> Instant:
    """Move ``at`` by ``lag_days`` working days, in the right space.

    A **start** instant is anchored to the next working day and stepped. A
    **finish boundary** lives one past the last day worked, so it is stepped as
    ``last_worked + n + 1``. Applying the start rule to a boundary gains a day on
    every lagged FF link -- and the schedule still looks reasonable, which is
    what makes it expensive.

    ``TWENTY_FOUR_HOUR`` counts elapsed days rather than working days, which is
    what a concrete cure or a delivery window actually is: chemistry does not
    observe the working week.

    Zero lag short-circuits, deliberately. It leaves the value in whatever space
    it arrived in, so an FF link with no lag ties two boundaries together exactly.
    """
    if lag_days == 0:
        return at
    if mode is LagCalendar.TWENTY_FOUR_HOUR:
        return at + lag_days
    cal = _lag_calendar(mode, pred_cal=pred_cal, succ_cal=succ_cal, project_cal=project_cal)
    if space == _FINISH_SPACE:
        last_worked = cal.snap_start_back(at - 1)
        return cal.add_working_days(last_worked, lag_days) + 1
    return cal.add_working_days(cal.snap_start_forward(at), lag_days)


def _forward_bound(
    rel: RelationType,
    lag: int,
    *,
    pred_start: Instant,
    pred_finish: Instant,
    pred_cal: WorkCalendar,
    succ_cal: WorkCalendar,
    duration: int,
    mode: LagCalendar,
    project_cal: WorkCalendar,
) -> Instant:
    """The earliest **start** the relationship permits the successor.

    Every relation type is reduced to a start bound here so the forward pass
    only ever compares one kind of thing. FF and SF bound the successor's
    *finish*, so they are converted back through the successor's own calendar
    and duration -- which is why this needs the duration at all.
    """
    space = _START_SPACE if rel.from_predecessor_start else _FINISH_SPACE
    base = pred_start if rel.from_predecessor_start else pred_finish
    bound = _advance_lag(
        base,
        lag,
        space,
        pred_cal=pred_cal,
        succ_cal=succ_cal,
        mode=mode,
        project_cal=project_cal,
    )
    if rel.drives_successor_finish:
        return succ_cal.start_from_finish(succ_cal.snap_finish_forward(bound), duration)
    return bound


def _backward_bound(
    rel: RelationType,
    lag: int,
    *,
    succ_start: Instant,
    succ_finish: Instant,
    pred_cal: WorkCalendar,
    succ_cal: WorkCalendar,
    duration: int,
    mode: LagCalendar,
    project_cal: WorkCalendar,
) -> Instant:
    """The latest **finish** the relationship permits the predecessor.

    The exact mirror of :func:`_forward_bound`. Written as its own function
    rather than sharing one signed implementation, because the two differ in
    which side is snapped and getting that backwards is invisible in a
    single-calendar test.
    """
    if rel.drives_successor_finish:
        base, space = succ_finish, _FINISH_SPACE
    else:
        base, space = succ_start, _START_SPACE
    bound = _advance_lag(
        base,
        -lag,
        space,
        pred_cal=pred_cal,
        succ_cal=succ_cal,
        mode=mode,
        project_cal=project_cal,
    )
    if rel.from_predecessor_start:
        return pred_cal.finish_from_start(pred_cal.snap_start_back(bound), duration)
    return bound


def calculate(
    tasks: Sequence[Task],
    links: Sequence[Link] = (),
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
    issues: IssueLog | None = None,
) -> NetworkResult:
    """Run the forward and backward pass.

    ``data_date`` defaults to the earliest date the network mentions, which for
    an unprogressed schedule is its planned start.
    """
    options = options or SchedulerOptions()
    issues = issues if issues is not None else IssueLog()
    if not tasks:
        raise ValueError("cannot schedule an empty network")

    ids = [t.id for t in tasks]
    edges = [(link.predecessor, link.successor) for link in links]
    validate_network(ids, edges)

    calendars = dict(calendars or {})
    if not calendars:
        from .timeaxis import standard_calendar

        calendars = {"STD": standard_calendar()}
    project_cal = calendars.get("STD") or next(iter(calendars.values()))

    by_id = {t.id: t for t in tasks}
    cal_for = {t.id: _resolve_calendar(t, calendars, issues) for t in tasks}

    # -- window --------------------------------------------------------------
    # Bind every calendar once, over a window generous enough for the whole run
    # including a DCMA check-12 probe. Rebuilding a lattice inside a Monte Carlo
    # loop is two thousand times slower than it needs to be, and nothing in the
    # output would say why.
    mentioned: list[date] = []
    for t in tasks:
        mentioned += [d for d in (t.constraint_date, t.actual_start, t.actual_finish) if d]
    if data_date:
        mentioned.append(data_date)
    if options.must_finish_by:
        mentioned.append(options.must_finish_by)
    anchor = min(mentioned) if mentioned else date.today()
    horizon = max(mentioned) if mentioned else date.today()
    total_duration = sum(max(t.duration_days, t.remaining_days or 0) for t in tasks)
    span_days = max(365, min(total_duration * 2 + 365, 60 * 365))
    from datetime import timedelta

    for cal in calendars.values():
        cal.bind(anchor - timedelta(days=365), horizon + timedelta(days=span_days))

    dd = instant_of(data_date) if data_date else instant_of(anchor)

    statuses = {t.id: derive_status(t, dd, cal_for[t.id], issues) for t in tasks}
    eff = effective_links(links, statuses, options.progress_mode)
    active = [e for e in eff if not e.suppressed]
    suppressed = tuple(e.source for e in eff if e.suppressed)

    order = topological_order(ids, [(e.predecessor, e.successor) for e in active])

    predecessors: dict[str, list[tuple[str, RelationType, int]]] = {i: [] for i in ids}
    successors: dict[str, list[tuple[str, RelationType, int]]] = {i: [] for i in ids}
    for e in active:
        predecessors[e.successor].append((e.predecessor, e.type, e.lag_days))
        successors[e.predecessor].append((e.successor, e.type, e.lag_days))

    es: dict[str, Instant] = {}
    ef: dict[str, Instant] = {}
    driving: dict[str, str | None] = dict.fromkeys(ids)
    violations: list[ConstraintViolation] = []

    # -- forward pass --------------------------------------------------------
    for aid in order:
        task = by_id[aid]
        cal = cal_for[aid]
        status = statuses[aid]
        duration = status.remaining_days if status.is_started else task.duration_days

        # (1) Actuals are history. A finished activity's dates are facts, and
        #     they are used exactly as recorded -- not snapped onto the calendar.
        #     If the crew worked a Saturday the calendar does not know about,
        #     that is a fact about the job, and moving it to the following Monday
        #     would be the engine editing the record.
        if status.is_complete and status.actual_start is not None:
            if status.actual_finish is None:  # pragma: no cover - Task validates this
                raise ValueError(f"{aid}: complete with no actual finish")
            es[aid] = status.actual_start
            ef[aid] = status.actual_finish + 1
            driving[aid] = None
            continue

        # (5) Network logic, recording which link drove the maximum.
        logic_bound: Instant | None = None
        driver: str | None = None
        for pred_id, rel, lag in predecessors[aid]:
            if pred_id not in ef:
                continue
            bound = _forward_bound(
                rel,
                lag,
                pred_start=es[pred_id],
                pred_finish=ef[pred_id],
                pred_cal=cal_for[pred_id],
                succ_cal=cal,
                duration=duration,
                mode=options.lag_calendar,
                project_cal=project_cal,
            )
            # Ties break on the first predecessor in declaration order, so the
            # driving path does not depend on dict iteration.
            if logic_bound is None or bound > logic_bound:
                logic_bound, driver = bound, pred_id

        if logic_bound is None:
            # An open start: the data date, or the activity's own actual start.
            earliest = status.actual_start if status.actual_start is not None else dd
        else:
            earliest = logic_bound

        # (2) The data date floor -- you cannot work yesterday. Remaining work on
        #     an in-progress activity is floored too, even though its actual
        #     start is behind us.
        earliest = max(earliest, dd)

        # (3) and (4) Constraints.
        overridden: str | None = None
        if task.constraint is not ConstraintType.NONE and task.constraint_date is not None:
            cdate = instant_of(task.constraint_date)
            effect = EFFECTS[task.constraint]
            floor = early_floor(task.constraint, cdate, duration, cal)
            start_side_only = effect.floors_early_start and not effect.floors_early_finish
            if status.is_started and start_side_only:
                # The activity has already started. A "must start on" is moot,
                # and honouring it would move recorded work. P6 ignores it too --
                # but it is recorded as overridden rather than dropped, so the
                # planner sees that their constraint did not apply.
                overridden = "actual_dates"
            elif floor is not None:
                if effect.is_mandatory:
                    pinned = floor
                    if pinned < dd:
                        # A mandatory constraint does not beat the data date. The
                        # override is recorded so the constraint's failure stays
                        # visible rather than being absorbed.
                        pinned = dd
                        overridden = "data_date"
                    earliest = pinned
                else:
                    earliest = max(earliest, floor)

        # (6) Snap last, always.
        start = cal.snap_start_forward(earliest)
        es[aid] = start
        ef[aid] = cal.finish_from_start(start, duration)

        # Only credit a predecessor with driving this activity if the logic bound
        # is what actually set the start. When the data date or a constraint
        # pushed it out, the predecessor is no longer driving, and saying it is
        # would send the delay analysis after the wrong activity.
        driving[aid] = driver if (logic_bound is not None and earliest == logic_bound) else None

        if task.constraint is not ConstraintType.NONE and task.constraint_date is not None:
            v = check(
                aid,
                task.constraint,
                instant_of(task.constraint_date),
                early_start=es[aid],
                early_finish=ef[aid],
                cal=cal,
                overridden_by=overridden,
            )
            if v is not None:
                violations.append(v)

    project_start = min(es.values())
    project_finish = max(ef.values())

    # The terminal activity is the one whose finish sets the project finish.
    # Ties break on the topological order, so the answer does not depend on dict
    # iteration order.
    terminal: str | None = None
    for aid in order:
        if ef[aid] == project_finish and not statuses[aid].is_complete:
            terminal = aid
            break
    if terminal is None:
        terminal = next((aid for aid in order if ef[aid] == project_finish), None)

    # -- backward pass -------------------------------------------------------
    # `must_finish_by` is a date a planner writes on a contract, meaning "done by
    # the end of that day". Spans are half-open, so the boundary is the day
    # after. Reading the date as the boundary directly loses a day, and the
    # resulting negative float is off by one on every deadline in the project.
    deadline = project_finish
    if options.must_finish_by is not None:
        deadline = instant_of(options.must_finish_by) + 1

    lf: dict[str, Instant] = {}
    ls: dict[str, Instant] = {}
    for aid in reversed(order):
        task = by_id[aid]
        cal = cal_for[aid]
        status = statuses[aid]
        duration = status.remaining_days if status.is_started else task.duration_days

        if status.is_complete:
            lf[aid] = ef[aid]
            ls[aid] = es[aid]
            continue

        latest = None
        for succ_id, rel, lag in successors[aid]:
            if succ_id not in ls:
                continue
            bound = _backward_bound(
                rel,
                lag,
                succ_start=ls[succ_id],
                succ_finish=lf[succ_id],
                pred_cal=cal,
                succ_cal=cal_for[succ_id],
                duration=duration,
                mode=options.lag_calendar,
                project_cal=project_cal,
            )
            if latest is None or bound < latest:
                latest = bound

        if latest is None:
            latest = deadline

        if task.constraint is not ConstraintType.NONE and task.constraint_date is not None:
            cdate = instant_of(task.constraint_date)
            effect = EFFECTS[task.constraint]
            cap = late_cap(task.constraint, cdate, duration, cal)
            if cap is not None:
                latest = cap if effect.is_mandatory else min(latest, cap)

        finish = cal.snap_finish_back(latest) if duration else latest
        lf[aid] = finish
        ls[aid] = cal.start_from_finish(finish, duration)

    # -- ALAP post-pass (7) --------------------------------------------------
    alap = [aid for aid in order if by_id[aid].constraint is ConstraintType.AS_LATE_AS_POSSIBLE]
    if alap:
        _apply_alap(alap, order, successors, cal_for, by_id, statuses, es, ef, project_finish)

    # -- float ---------------------------------------------------------------
    total_float: dict[str, int | None] = {}
    free_float: dict[str, int | None] = {}
    for aid in ids:
        cal = cal_for[aid]
        if statuses[aid].is_complete:
            # Not zero. Zero float and "this already happened" are different
            # statements, and conflating them puts finished work on the critical
            # path.
            total_float[aid] = None
            free_float[aid] = None
            continue
        total_float[aid] = cal.count_working_days(es[aid], ls[aid])
        onward = successors[aid]
        if onward:
            # Free float: how far this activity can slip before it moves any
            # successor's *early* date. Measured by recomputing the bound this
            # activity imposes and comparing it against where the successor
            # actually landed -- so it uses exactly the arithmetic the forward
            # pass used, rather than a second formulation that can drift from it.
            #
            # Not clamped at zero. Under retained logic, or with a mandatory
            # constraint, a negative value is the signal that a recorded actual
            # contradicts the remaining logic. The source engine's `max(0, free)`
            # erased precisely that.
            slack = None
            for succ_id, rel, lag in onward:
                bound = _forward_bound(
                    rel,
                    lag,
                    pred_start=es[aid],
                    pred_finish=ef[aid],
                    pred_cal=cal,
                    succ_cal=cal_for[succ_id],
                    duration=(
                        statuses[succ_id].remaining_days
                        if statuses[succ_id].is_started
                        else by_id[succ_id].duration_days
                    ),
                    mode=options.lag_calendar,
                    project_cal=project_cal,
                )
                # count is signed, so a successor that starts before the bound
                # (out-of-sequence progress) reports negative slack rather than
                # silently reading as "no float".
                available = cal.count_working_days(cal.snap_start_forward(bound), es[succ_id])
                slack = available if slack is None else min(slack, available)
            free_float[aid] = slack
        else:
            free_float[aid] = cal.count_working_days(ef[aid], deadline)

    return NetworkResult(
        early_start=es,
        early_finish=ef,
        late_start=ls,
        late_finish=lf,
        total_float_days=total_float,
        free_float_days=free_float,
        project_start=project_start,
        project_finish=project_finish,
        data_date=dd,
        driving_predecessor=driving,
        terminal_activity=terminal,
        violations=tuple(violations),
        statuses=statuses,
        options=options,
        order=tuple(order),
        suppressed_links=suppressed,
        calendars=calendars,
    )


def _apply_alap(
    alap_ids: Sequence[str],
    order: Sequence[str],
    successors: Mapping[str, list[tuple[str, RelationType, int]]],
    cal_for: Mapping[str, WorkCalendar],
    by_id: Mapping[str, Task],
    statuses: Mapping[str, ActivityStatus],
    es: dict[str, Instant],
    ef: dict[str, Instant],
    project_finish: Instant,
) -> None:
    """Shift ALAP activities right by their *free* float, latest first.

    Free, not total: total float belongs to the path, and consuming it delays
    successors and moves the project finish -- the one thing ALAP is defined
    never to do. Reverse topological order so a chain of ALAP activities slides
    coherently rather than each one measuring slack against an unmoved neighbour.
    """
    pending = set(alap_ids)
    for aid in reversed(list(order)):
        if aid not in pending or statuses[aid].is_complete:
            continue
        cal = cal_for[aid]
        onward = successors[aid]
        if onward:
            room = min(cal.count_working_days(ef[aid], es[succ]) for succ, _r, _l in onward)
        else:
            room = cal.count_working_days(ef[aid], project_finish)
        if room <= 0:
            continue
        duration = by_id[aid].duration_days
        new_start = cal.add_working_days(cal.snap_start_forward(es[aid]), room)
        es[aid] = new_start
        ef[aid] = cal.finish_from_start(new_start, duration)


def summarise(result: NetworkResult) -> dict[str, object]:
    """A JSON-safe headline. Used by the API layer and by tests as a stable digest."""
    return {
        "project_start": day_of(result.project_start).isoformat(),
        "project_finish": day_of(result.project_finish).isoformat(),
        "activity_count": len(result.order),
        "critical_count": len(result.critical_ids),
        "terminal_activity": result.terminal_activity,
        "longest_path": result.longest_path(),
        "violation_count": len(result.violations),
        "suppressed_link_count": len(result.suppressed_links),
        "options": result.options.to_dict(),
    }


__all__ = [
    "ActivityKind",
    "LagCalendar",
    "Link",
    "NetworkResult",
    "ProgressMode",
    "RelationType",
    "SchedulerOptions",
    "Status",
    "Task",
    "UnknownCalendarError",
    "calculate",
    "summarise",
]
