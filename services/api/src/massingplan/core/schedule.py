"""Compute a schedule and return dates fit to persist.

This is the module the rest of the world calls. It exists to hold one piece of
discipline in one place:

**Instants become dates here and nowhere else.** ``_present`` is the only
function in the package that turns a half-open boundary into the inclusive
"last day worked" a human reads. Scatter that conversion across modules and the
convention drifts by a day in one code path and not the others, which is how
every scheduling tool acquires its off-by-one folklore.

Two supporting rules:

* **``to_rows()`` is the persistence contract.** Its key set is frozen by a test,
  so a rename in the engine cannot silently drop a column in a consumer.
* **``apply_to()`` returns a new schedule.** Mutating in place means a failed
  database write leaves a half-updated object in memory that the next request
  reads as truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

from .cpm import NetworkResult, calculate
from .issues import Issue, IssueLog
from .model import ExchangeSchedule
from .network import ActivityKind, Link, SchedulerOptions, Status, Task
from .timeaxis import Instant, WorkCalendar, day_of


@dataclass(frozen=True)
class ActivityDates:
    """One activity's computed dates, as a human and a database both read them.

    ``start`` and ``finish`` are inclusive -- ``finish`` is the last day worked.
    The early/late pairs are the same convention, so a row can be written
    straight into a table without a second conversion.
    """

    activity_id: str
    start: date
    finish: date
    early_start: date
    early_finish: date
    late_start: date
    late_finish: date
    total_float_days: int | None
    free_float_days: int | None
    is_critical: bool
    is_longest_path: bool
    constraint_satisfied: bool
    status: Status
    remaining_days: int
    duration_days: int

    def to_row(self) -> dict[str, str | int | bool | None]:
        return {
            "activity_id": self.activity_id,
            "start": self.start.isoformat(),
            "finish": self.finish.isoformat(),
            "early_start": self.early_start.isoformat(),
            "early_finish": self.early_finish.isoformat(),
            "late_start": self.late_start.isoformat(),
            "late_finish": self.late_finish.isoformat(),
            "total_float_days": self.total_float_days,
            "free_float_days": self.free_float_days,
            "is_critical": self.is_critical,
            "is_longest_path": self.is_longest_path,
            "constraint_satisfied": self.constraint_satisfied,
            "status": self.status.value,
            "remaining_days": self.remaining_days,
            "duration_days": self.duration_days,
        }


#: The exact keys ``to_row`` emits. Frozen so that a rename here is a test
#: failure rather than a column that silently stops being written downstream.
ROW_KEYS: frozenset[str] = frozenset(
    {
        "activity_id",
        "start",
        "finish",
        "early_start",
        "early_finish",
        "late_start",
        "late_finish",
        "total_float_days",
        "free_float_days",
        "is_critical",
        "is_longest_path",
        "constraint_satisfied",
        "status",
        "remaining_days",
        "duration_days",
    }
)


@dataclass(frozen=True)
class ScheduleOutcome:
    """Everything a caller needs from a scheduling run."""

    data_date: date
    project_start: date
    project_finish: date
    duration_working_days: int
    dates: Mapping[str, ActivityDates]
    longest_path: tuple[str, ...]
    violations: tuple[object, ...]
    issues: tuple[Issue, ...]
    options: SchedulerOptions
    order: tuple[str, ...]
    #: Kept so downstream analysis (health, risk, comparison) can reach float and
    #: driving links without re-running the passes.
    network: NetworkResult

    def to_rows(self) -> list[dict[str, str | int | bool | None]]:
        return [self.dates[aid].to_row() for aid in self.order if aid in self.dates]

    def summary(self) -> dict[str, object]:
        return {
            "data_date": self.data_date.isoformat(),
            "project_start": self.project_start.isoformat(),
            "project_finish": self.project_finish.isoformat(),
            "duration_working_days": self.duration_working_days,
            "activity_count": len(self.dates),
            "critical_count": sum(1 for d in self.dates.values() if d.is_critical),
            "longest_path": list(self.longest_path),
            "violation_count": len(self.violations),
            "issue_count": len(self.issues),
            "options": self.options.to_dict(),
        }

    def apply_to(self, source: ExchangeSchedule) -> ExchangeSchedule:
        """A copy of ``source`` carrying these dates. Never mutates its argument."""
        updated = []
        for activity in source.activities:
            computed = self.dates.get(activity.id)
            if computed is None:
                updated.append(activity)
                continue
            import copy

            clone = copy.copy(activity)
            clone.early_start = computed.early_start
            clone.early_finish = computed.early_finish
            clone.late_start = computed.late_start
            clone.late_finish = computed.late_finish
            clone.total_float_days = computed.total_float_days
            clone.free_float_days = computed.free_float_days
            clone.is_longest_path = computed.is_longest_path
            updated.append(clone)
        out = source.replace_activities(updated)
        out.data_date = self.data_date
        return out


def _present(
    start: Instant, finish: Instant, cal: WorkCalendar, kind: ActivityKind
) -> tuple[date, date]:
    """The one place a half-open span becomes the pair of dates a human reads.

    ``finish - 1`` is the last day worked. Milestones are asymmetric: a start
    milestone shows at its start, a finish milestone at the boundary snapped back
    to the previous working day. Without that asymmetry, "Substantial Completion"
    -- a finish milestone tied FS to the last work -- prints one day *after* the
    work it marks, and every contractual milestone in the export is a day late.
    """
    if start == finish:
        if kind is ActivityKind.FINISH_MILESTONE:
            try:
                marker = day_of(cal.snap_start_back(start - 1))
            except Exception:  # noqa: BLE001 - a milestone at the window edge
                marker = day_of(start)
            return marker, marker
        marker = day_of(start)
        return marker, marker
    return day_of(start), day_of(finish - 1)


def schedule(
    source: ExchangeSchedule,
    *,
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> ScheduleOutcome:
    """Schedule an :class:`ExchangeSchedule` and return dates ready to persist."""
    tasks, links, calendars = source.to_network()
    resolved = options or source.options
    if source.must_finish_by and resolved.must_finish_by is None:
        resolved = replace(resolved, must_finish_by=source.must_finish_by)
    dd = data_date or source.data_date or source.planned_start
    issues = IssueLog()
    issues.extend(source.issues)
    result = calculate(tasks, links, calendars, data_date=dd, options=resolved, issues=issues)
    return _outcome(tasks, calendars, result, issues)


def schedule_network(
    tasks: Sequence[Task],
    links: Sequence[Link] = (),
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> ScheduleOutcome:
    """Schedule a bare network. The path massing's adapter takes."""
    issues = IssueLog()
    result = calculate(tasks, links, calendars, data_date=data_date, options=options, issues=issues)
    return _outcome(tasks, calendars or {}, result, issues)


def _outcome(
    tasks: Sequence[Task],
    calendars: Mapping[str, WorkCalendar],
    result: NetworkResult,
    issues: IssueLog,
) -> ScheduleOutcome:
    by_id = {t.id: t for t in tasks}
    violated = {v.activity_id for v in result.violations}
    on_path = set(result.longest_path())

    # The calendars the *pass* used, which may include one it had to synthesise
    # because the caller passed none. Resolving them independently here is how
    # the two ends of the instant/date conversion drift apart.
    calendars = dict(result.calendars) or dict(calendars)
    fallback = next(iter(calendars.values())) if calendars else None
    dates: dict[str, ActivityDates] = {}
    for aid in result.order:
        task = by_id[aid]
        cal = calendars.get(task.calendar_id) or fallback
        if cal is None:  # pragma: no cover - calculate() always supplies one
            raise ValueError(f"{aid}: no calendar available to present dates against")
        es, ef = result.early_start[aid], result.early_finish[aid]
        ls, lf = result.late_start[aid], result.late_finish[aid]
        start, finish = _present(es, ef, cal, task.kind)
        late_start, late_finish = _present(ls, lf, cal, task.kind)
        status = result.statuses[aid]
        dates[aid] = ActivityDates(
            activity_id=aid,
            start=start,
            finish=finish,
            early_start=start,
            early_finish=finish,
            late_start=late_start,
            late_finish=late_finish,
            total_float_days=result.total_float_days[aid],
            free_float_days=result.free_float_days[aid],
            is_critical=result.is_critical(aid),
            is_longest_path=aid in on_path,
            constraint_satisfied=aid not in violated,
            status=status.status,
            remaining_days=status.remaining_days,
            duration_days=task.duration_days,
        )

    project_cal = fallback
    duration = 0
    if project_cal is not None:
        duration = project_cal.count_working_days(result.project_start, result.project_finish)

    return ScheduleOutcome(
        data_date=day_of(result.data_date),
        project_start=day_of(result.project_start),
        project_finish=day_of(result.project_finish - 1)
        if result.project_finish > result.project_start
        else day_of(result.project_finish),
        duration_working_days=duration,
        dates=dates,
        longest_path=tuple(result.longest_path()),
        violations=tuple(result.violations),
        issues=tuple(issues.entries),
        options=result.options,
        order=result.order,
        network=result,
    )
