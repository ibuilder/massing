"""Progress measurement against a baseline: BEI, variance, slippage.

Ported from ibuilder/AIHackScheduler ``core/progress.py`` (MIT). Two of its
judgements are preserved deliberately, because both are the kind of thing that
gets "simplified" into a wrong answer:

* **Baseline Execution Index returns ``None`` when nothing was due.** Not 1.0.
  An empty ratio is not perfect performance; it is no information, and reporting
  it as 1.0 puts a green tile on a dashboard for a project that has not started.
* **``is_behind`` is deliberately broader than DCMA check 11.** An activity that
  was due to start and never did counts as behind, even though check 11 only
  looks at finishes. It is the more urgent problem, and a report that misses it
  is missing the thing the reader most needs to see.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from .network import Task
from .timeaxis import WorkCalendar


@dataclass(frozen=True)
class ActivityProgress:
    """One activity's standing against its baseline as at the data date."""

    activity_id: str
    baseline_start: date | None
    baseline_finish: date | None
    actual_start: date | None
    actual_finish: date | None
    forecast_finish: date | None
    remaining_days: int
    start_variance_days: int | None
    finish_variance_days: int | None

    @property
    def is_complete(self) -> bool:
        return self.actual_finish is not None

    @property
    def is_started(self) -> bool:
        return self.actual_start is not None

    def is_behind(self, data_date: date) -> bool:
        """Broader than DCMA check 11, on purpose.

        Three ways to be behind, and check 11 only sees the first:
        finished later than baseline; still running past the baseline finish;
        or due to have started and never started at all. The third is the most
        urgent and the easiest to lose in a report that only counts finishes.
        """
        if self.actual_finish is not None and self.baseline_finish is not None:
            return self.actual_finish > self.baseline_finish
        if self.baseline_finish is not None and self.baseline_finish < data_date:
            return True
        return (
            self.baseline_start is not None
            and self.baseline_start < data_date
            and self.actual_start is None
        )


@dataclass
class ProgressReport:
    data_date: date
    activities: list[ActivityProgress] = field(default_factory=list)
    invalid_actuals: list[str] = field(default_factory=list)

    @property
    def complete(self) -> list[ActivityProgress]:
        return [a for a in self.activities if a.is_complete]

    @property
    def behind(self) -> list[ActivityProgress]:
        return [a for a in self.activities if a.is_behind(self.data_date)]

    @property
    def not_started_but_due(self) -> list[str]:
        return sorted(
            a.activity_id
            for a in self.activities
            if a.baseline_start is not None
            and a.baseline_start < self.data_date
            and a.actual_start is None
        )

    @property
    def baseline_execution_index(self) -> float | None:
        """Completed / should-have-completed, or ``None`` when nothing was due.

        ``None`` rather than 1.0. See the module docstring.
        """
        due = [
            a
            for a in self.activities
            if a.baseline_finish is not None and a.baseline_finish <= self.data_date
        ]
        if not due:
            return None
        done = sum(1 for a in due if a.is_complete)
        return done / len(due)

    @property
    def average_finish_variance(self) -> float | None:
        variances = [
            a.finish_variance_days for a in self.activities if a.finish_variance_days is not None
        ]
        if not variances:
            return None
        return sum(variances) / len(variances)

    @property
    def worst_slippage(self) -> ActivityProgress | None:
        slipped = [a for a in self.activities if a.finish_variance_days is not None]
        if not slipped:
            return None
        return max(slipped, key=lambda a: (a.finish_variance_days or 0, a.activity_id))

    def to_dict(self) -> dict[str, object]:
        bei = self.baseline_execution_index
        avg = self.average_finish_variance
        worst = self.worst_slippage
        return {
            "data_date": self.data_date.isoformat(),
            "activity_count": len(self.activities),
            "complete_count": len(self.complete),
            "behind_count": len(self.behind),
            "not_started_but_due": self.not_started_but_due,
            # `None` travels as null, with a reason the caller can render, rather
            # than as a zero that reads as a measurement.
            "baseline_execution_index": None if bei is None else round(bei, 3),
            "baseline_execution_index_reason": (
                None if bei is not None else "no baselined activity was due by the data date"
            ),
            "average_finish_variance_days": None if avg is None else round(avg, 2),
            "worst_slippage": None
            if worst is None
            else {
                "activity_id": worst.activity_id,
                "days": worst.finish_variance_days,
            },
            "invalid_actuals": self.invalid_actuals,
        }


def build_report(
    tasks: Sequence[Task],
    data_date: date,
    *,
    baseline_start: Mapping[str, date] | None = None,
    baseline_finish: Mapping[str, date] | None = None,
    forecast_finish: Mapping[str, date] | None = None,
    calendars: Mapping[str, WorkCalendar] | None = None,
) -> ProgressReport:
    """Measure recorded progress against a baseline.

    Variances are in **working days on the activity's own calendar**, signed and
    positive-is-late. Calendar-day variance overstates every slip that spans a
    weekend, which is most of them.
    """
    baseline_start = baseline_start or {}
    baseline_finish = baseline_finish or {}
    forecast_finish = forecast_finish or {}
    calendars = dict(calendars or {})
    fallback = next(iter(calendars.values())) if calendars else None

    report = ProgressReport(data_date=data_date)
    for task in tasks:
        cal = calendars.get(task.calendar_id) or fallback

        if task.actual_finish is not None and task.actual_start is None:
            report.invalid_actuals.append(task.id)
        if (
            task.actual_start is not None
            and task.actual_finish is not None
            and task.actual_finish < task.actual_start
        ):
            report.invalid_actuals.append(task.id)

        bs = baseline_start.get(task.id)
        bf = baseline_finish.get(task.id)
        report.activities.append(
            ActivityProgress(
                activity_id=task.id,
                baseline_start=bs,
                baseline_finish=bf,
                actual_start=task.actual_start,
                actual_finish=task.actual_finish,
                forecast_finish=forecast_finish.get(task.id),
                remaining_days=task.remaining_days
                if task.remaining_days is not None
                else task.duration_days,
                start_variance_days=_variance(bs, task.actual_start, cal),
                finish_variance_days=_variance(
                    bf, task.actual_finish or forecast_finish.get(task.id), cal
                ),
            )
        )
    return report


def _variance(baseline: date | None, actual: date | None, cal: WorkCalendar | None) -> int | None:
    """Signed working-day variance, positive when late. ``None`` when unmeasurable."""
    if baseline is None or actual is None:
        return None
    if cal is None:
        return (actual - baseline).days
    from .timeaxis import instant_of

    return cal.count_working_days(instant_of(baseline), instant_of(actual))
