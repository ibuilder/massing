"""Earned Schedule: how far along in *time* the project is.

`progress.py` reports BEI and variance -- whether activities finished when they
were supposed to. This answers a different question: given what has been
earned, what date was the plan expecting to be at?

Why not SPI
-----------
The classic Schedule Performance Index is `EV / PV`, a ratio of *money* used to
describe *time*. It has a defect that shows up exactly when it matters:

    **SPI converges to 1.0 as any project finishes, however late.**

At completion every activity is earned in full, so `EV = PV = BAC` and the
index reads 1.0 -- perfect schedule performance, on a job that ran a year over.
The metric stops telling the truth in the last third of the project, which is
the third where somebody is reading it to decide whether to intervene.

Earned Schedule fixes it by measuring on the time axis instead. `ES` is the
point on the baseline curve where the planned progress equals what has actually
been earned; `AT` is how much time has actually passed. On a late project at
100% complete, `ES` is the planned duration and `AT` is the longer real one, so
`SPI(t)` stays below 1.0 and keeps saying so. `test_the_index_stays_honest_at_
completion` holds this module to that.

What is measured
----------------
Duration-days, not cost. This engine has no cost model and inventing one to
express a schedule metric would be the tail wagging the dog: an activity's
weight here is the working days it was baselined to take.

Progress **within** an activity is taken as linear -- an activity baselined at
ten days and half done has earned five. That is the standard assumption for an
earned-schedule curve, and it is deliberately *not* the same judgement as
`resources.py`'s refusal to spread demand linearly. There the objection is that
spreading makes peak demand a function of duration, so levelling can raise the
peak it was asked to lower; the peak is the output and the shape drives it.
Here the output is a cumulative total at one instant, where the within-activity
shape cancels out across a portfolio of activities and no decision depends on
it. Different question, different answer, stated so the two do not look like an
inconsistency.

What is refused
---------------
`SPI(t)` is `None` when no time has passed, not 1.0 -- the same rule
`progress.py` applies to BEI. A ratio with a zero denominator is not perfect
performance, it is no information, and reporting it as 1.0 puts a green tile on
a dashboard for a project that has not started.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .network import Task
from .timeaxis import WorkCalendar, instant_of


class EarnedScheduleError(ValueError):
    """The inputs cannot support the measure. Refused rather than defaulted."""


@dataclass(frozen=True)
class EarnedScheduleResult:
    """Where the project is on its own baseline's time axis.

    Every duration here is **working days on the project calendar**, because a
    schedule metric quoted in calendar days silently rewards a project for
    having weekends in the right places.
    """

    data_date: date
    #: Working days the baseline planned, start to finish.
    planned_duration_days: int
    #: `AT` -- working days elapsed from the baseline start to the data date.
    #:
    #: Measured *to* the data date and not through it, because the data date is
    #: the first day of remaining work -- which is how `cpm.py` floors it, and
    #: therefore what it has to mean here too. A project whose last day worked
    #: was Friday has a Monday data date and an `AT` that counts the Friday.
    #: Counting the data date itself as elapsed would add a day to `AT` and
    #: none to `ES`, and every project would read fractionally behind for a
    #: reason that is purely a convention applied twice.
    actual_time_days: int
    #: `ES` -- the point on the baseline curve matching what has been earned.
    #: Fractional on purpose; rounding it up would flatter every project by
    #: up to a day and rounding down would penalise every project by the same.
    earned_days: float
    #: Duration-days earned, and the baseline total they are measured against.
    earned_duration_days: float
    baseline_duration_days: float

    @property
    def schedule_variance_days(self) -> float:
        """`SV(t) = ES - AT`. Negative is behind. Never clamped."""
        return self.earned_days - self.actual_time_days

    @property
    def performance_index(self) -> float | None:
        """`SPI(t) = ES / AT`, or `None` when no time has passed.

        Below 1.0 is behind, and stays below 1.0 at completion on a late
        project -- which is the whole reason this exists.
        """
        if self.actual_time_days <= 0:
            return None
        return self.earned_days / self.actual_time_days

    @property
    def percent_complete(self) -> float:
        """Earned duration-days over baseline duration-days, unrounded."""
        if self.baseline_duration_days <= 0:
            return 0.0
        return self.earned_duration_days / self.baseline_duration_days

    @property
    def classic_performance_index(self) -> float | None:
        """`EV / PV` as at the data date, for the comparison that motivates this.

        Reported so the two can be shown side by side. It is not the number to
        act on: it converges to 1.0 as the project completes however late it
        finishes, and this class exists because of that.
        """
        if self.planned_duration_days <= 0:
            return None
        planned = _planned_value(
            min(float(self.actual_time_days), float(self.planned_duration_days)),
            self._curve,
        )
        if planned <= 0:
            return None
        return self.earned_duration_days / planned

    #: The baseline curve, kept so `classic_performance_index` can be derived
    #: from the same arithmetic rather than a second implementation of it.
    _curve: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, object]:
        index = self.performance_index
        classic = self.classic_performance_index
        return {
            "data_date": self.data_date.isoformat(),
            "planned_duration_days": self.planned_duration_days,
            "actual_time_days": self.actual_time_days,
            "earned_days": round(self.earned_days, 3),
            "schedule_variance_days": round(self.schedule_variance_days, 3),
            "performance_index": None if index is None else round(index, 3),
            "classic_performance_index": None if classic is None else round(classic, 3),
            "percent_complete": round(self.percent_complete, 4),
            "is_behind": index is not None and index < 1.0,
        }


def _fraction_complete(task: Task) -> float:
    """How much of this activity has been earned, as a fraction of its duration.

    Percent complete is preferred when the planner supplied one, because it is
    a claim they made and can defend. Remaining duration is the fallback, and a
    completed activity is 1.0 whatever either of them says -- an actual finish
    is a fact and the other two are estimates.
    """
    if task.actual_finish is not None:
        return 1.0
    if task.percent_complete is not None:
        return max(0.0, min(1.0, task.percent_complete / 100.0))
    if task.remaining_days is not None and task.duration_days > 0:
        done = task.duration_days - task.remaining_days
        return max(0.0, min(1.0, done / task.duration_days))
    if task.actual_start is not None and task.duration_days == 0:
        return 1.0
    return 0.0


def _planned_value(at: float, curve: Sequence[float]) -> float:
    """The baseline's cumulative duration-days at working-day offset `at`.

    Interpolates between whole days, because `at` is a position on a curve and
    not an index into it.
    """
    if not curve:
        return 0.0
    if at <= 0:
        return curve[0]
    if at >= len(curve) - 1:
        return curve[-1]
    low = int(at)
    return curve[low] + (curve[low + 1] - curve[low]) * (at - low)


def _earned_time(earned: float, curve: Sequence[float]) -> float:
    """The offset on the baseline curve where planned progress equals `earned`.

    The inverse of the curve, which is the whole of Earned Schedule. Flat
    stretches -- days the baseline planned no work -- are stepped over rather
    than divided by, since a zero-width segment has no position to interpolate
    within and the next day that moves is the honest answer.
    """
    if not curve or earned <= curve[0]:
        return 0.0
    if earned >= curve[-1]:
        # Everything planned has been earned. The project cannot be further
        # along its own baseline than the end of it, however much time it took
        # to get there -- and that cap is what keeps SPI(t) below 1.0 at a late
        # completion instead of letting it drift back up.
        return float(len(curve) - 1)

    index = bisect_right(curve, earned) - 1
    remainder = earned - curve[index]
    step = curve[index + 1] - curve[index]
    if step <= 0:  # pragma: no cover - bisect_right lands past equal values
        return float(index)
    return index + remainder / step


def measure(
    tasks: Sequence[Task],
    baseline: Mapping[str, tuple[date, date]],
    *,
    data_date: date,
    calendar: WorkCalendar,
) -> EarnedScheduleResult:
    """Earned Schedule as at ``data_date``, against the baseline dates given.

    ``baseline`` maps activity id to its baselined ``(start, finish)``, both
    inclusive -- the same convention `schedule.to_rows()` emits, so a stored
    baseline feeds straight in.

    Activities with no baseline entry are **excluded from both sides**. They
    are scope added after the baseline, and counting their progress against a
    plan that never contained them inflates the index for doing unplanned work.
    """
    scoped = [t for t in tasks if t.id in baseline]
    if not scoped:
        raise EarnedScheduleError(
            "no activity has a baseline; there is no plan to measure progress against"
        )

    origin = min(instant_of(baseline[t.id][0]) for t in scoped)
    horizon = max(instant_of(baseline[t.id][1]) for t in scoped)
    planned_duration = (
        calendar.count_working_days(
            calendar.snap_start_forward(origin), calendar.snap_start_forward(horizon)
        )
        + 1
    )

    # The baseline curve: cumulative duration-days planned complete by each
    # working day. Index n is "after n working days", so index 0 is the start.
    curve = [0.0] * (planned_duration + 1)
    total_baseline = 0.0
    for task in scoped:
        start, finish = baseline[task.id]
        offset = calendar.count_working_days(
            calendar.snap_start_forward(origin), calendar.snap_start_forward(instant_of(start))
        )
        span = (
            calendar.count_working_days(
                calendar.snap_start_forward(instant_of(start)),
                calendar.snap_start_forward(instant_of(finish)),
            )
            + 1
        )
        total_baseline += span
        for n in range(len(curve)):
            done = min(max(n - offset, 0), span)
            curve[n] += float(done)

    earned = sum(
        _fraction_complete(task)
        * (
            calendar.count_working_days(
                calendar.snap_start_forward(instant_of(baseline[task.id][0])),
                calendar.snap_start_forward(instant_of(baseline[task.id][1])),
            )
            + 1
        )
        for task in scoped
    )

    actual_time = calendar.count_working_days(
        calendar.snap_start_forward(origin), calendar.snap_start_forward(instant_of(data_date))
    )

    return EarnedScheduleResult(
        data_date=data_date,
        planned_duration_days=planned_duration,
        actual_time_days=max(0, actual_time),
        earned_days=_earned_time(earned, curve),
        earned_duration_days=earned,
        baseline_duration_days=total_baseline,
        _curve=tuple(curve),
    )


__all__ = [
    "EarnedScheduleError",
    "EarnedScheduleResult",
    "measure",
]
