"""DCMA 14-point schedule quality assessment.

The Defense Contract Management Agency's fourteen checks are the closest thing
the industry has to a shared definition of "is this schedule trustworthy?". They
are used well beyond defence work -- infrastructure, energy and commercial
construction all lean on them to tell a genuine planning instrument apart from a
document produced to satisfy a contract clause.

Optimising a schedule that fails these checks produces confident nonsense, so
this runs *before* any optimisation and gates it via
:attr:`HealthReport.is_optimisable`.

The honesty rule that makes the score mean something
----------------------------------------------------
``passed=None`` is **skipped, not passed**, and skipped checks are excluded from
the score's denominator. Checks 9, 10, 11 and 14 need baseline dates, actuals or
resource assignments; without them the check reports what it is missing. A tool
that scores a schedule 14/14 because four of the checks could not run is worse
than one that does not score it at all.

Ported from ibuilder/AIHackScheduler ``core/schedule_health.py`` (MIT). Four
checks needed surgery for the new engine:

* **Check 5** counted only ``constraint_start is not None`` -- two of the ten
  constraint types. Eight types were invisible to the check that exists to find
  them. It now weighs hard against soft.
* **Checks 6 and 7** take signed working-day float from the activity's own
  calendar, and skip completed work (``total_float is None``). Float in calendar
  days makes five days of slack across a shutdown report as fourteen.
* **Check 12** restates the probe for multiple calendars; under a single
  calendar it reduces exactly to the classic "the finish moved by 600", and a
  test asserts that reduction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from .constraints import EFFECTS, ConstraintType
from .cpm import calculate
from .network import Link, RelationType, Task
from .timeaxis import WorkCalendar

# DCMA thresholds. Fractions where the check is a percentage.
MAX_MISSING_LOGIC = 0.05
MAX_LEADS = 0.0
MAX_LAGS = 0.05
MIN_FS_RELATIONSHIPS = 0.90
MAX_HARD_CONSTRAINTS = 0.05
MAX_HIGH_FLOAT = 0.05
MAX_NEGATIVE_FLOAT = 0.0
MAX_HIGH_DURATION = 0.05
MAX_INVALID_DATES = 0.0
MAX_MISSING_RESOURCES = 0.0
MAX_MISSED_TASKS = 0.05
MIN_CPLI = 0.95
MIN_BEI = 0.95

HIGH_FLOAT_DAYS = 44
HIGH_DURATION_DAYS = 44

#: The delay injected by check 12. Long enough that no ordinary float absorbs it.
PROBE_DAYS = 600

#: Checks whose failure corrupts the critical path, and therefore every
#: optimisation decision that depends on it.
BLOCKING_CHECKS = frozenset({1, 7, 13})


@dataclass
class CheckResult:
    """One of the fourteen checks.

    ``passed`` is tri-state on purpose: ``None`` means the check could not run,
    and ``detail`` then says what was missing.
    """

    number: int
    name: str
    passed: bool | None
    value: float | None
    threshold: str
    detail: str
    offenders: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.passed is None:
            return "skipped"
        return "pass" if self.passed else "fail"

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "name": self.name,
            "status": self.status,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
            # Truncated for transport; the full list stays on the object for a
            # caller that wants to page through it.
            "offenders": self.offenders[:20],
            "offender_count": len(self.offenders),
        }


@dataclass
class HealthReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def assessed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.passed is not None]

    @property
    def skipped(self) -> list[CheckResult]:
        return [c for c in self.checks if c.passed is None]

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.passed is False]

    @property
    def score(self) -> float:
        """Percentage of *runnable* checks that passed."""
        runnable = self.assessed
        if not runnable:
            return 0.0
        return 100.0 * sum(1 for c in runnable if c.passed) / len(runnable)

    @property
    def grade(self) -> str:
        score = self.score
        for floor, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
            if score >= floor:
                return letter
        return "F"

    @property
    def is_optimisable(self) -> bool:
        """Whether the logic is sound enough to optimise against."""
        return not any(c.number in BLOCKING_CHECKS and c.passed is False for c in self.checks)

    def check(self, number: int) -> CheckResult:
        return next(c for c in self.checks if c.number == number)

    def to_dict(self) -> dict[str, object]:
        return {
            "grade": self.grade,
            "score": round(self.score, 1),
            "optimisable": self.is_optimisable,
            "assessed": len(self.assessed),
            "skipped": len(self.skipped),
            "failed": len(self.failures),
            "checks": [c.to_dict() for c in self.checks],
        }


def _pct(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def assess(
    outcome: object,
    tasks: Sequence[Task],
    links: Sequence[Link] = (),
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    baseline_finish: Mapping[str, date] | None = None,
    resourced_activity_ids: Sequence[str] | None = None,
) -> HealthReport:
    """Run the fourteen checks against a computed schedule.

    ``outcome`` is a :class:`~massingplan.core.schedule.ScheduleOutcome`; it is
    typed loosely here only to keep this module free of an import cycle.
    """
    network = outcome.network  # type: ignore[attr-defined]
    data_date: date = outcome.data_date  # type: ignore[attr-defined]
    calendars = dict(calendars or {})

    links = list(links)
    tasks = list(tasks)
    n_act = len(tasks)
    n_rel = len(links)
    report = HealthReport()
    add = report.checks.append

    ids = [t.id for t in tasks]
    by_id = {t.id: t for t in tasks}
    has_pred = {link.successor for link in links}
    has_succ = {link.predecessor for link in links}

    actual_finish = {t.id: t.actual_finish for t in tasks if t.actual_finish is not None}

    # --- 1. Logic ----------------------------------------------------------
    # Exactly one activity may legitimately open the schedule with no
    # predecessor, and one may close it with no successor. Those are the project
    # start and the project finish, identified by position in the *network* --
    # not by position in the input list, which says nothing about the plan.
    open_starts = [aid for aid in ids if aid not in has_pred]
    open_finishes = [aid for aid in ids if aid not in has_succ]

    exempt: set[str] = set()
    if open_starts:
        exempt.add(min(open_starts, key=lambda aid: (network.early_start[aid], aid)))
    if open_finishes:
        exempt.add(max(open_finishes, key=lambda aid: (network.early_finish[aid], aid)))

    dangling = sorted(
        {aid for aid in open_starts + open_finishes if aid not in exempt}
        # An activity with neither a predecessor nor a successor is detached from
        # the plan entirely, wherever it sits in time.
        | {aid for aid in ids if aid not in has_pred and aid not in has_succ}
    )
    value = _pct(len(dangling), n_act)
    add(
        CheckResult(
            1,
            "Logic",
            value <= MAX_MISSING_LOGIC,
            round(value * 100, 1),
            "<= 5% missing predecessor or successor",
            f"{len(dangling)} of {n_act} activities are dangling",
            dangling,
        )
    )

    # --- 2. Leads ----------------------------------------------------------
    leads = [f"{r.predecessor}->{r.successor}" for r in links if r.lag_days < 0]
    value = _pct(len(leads), n_rel)
    add(
        CheckResult(
            2,
            "Leads",
            len(leads) == 0,
            round(value * 100, 1),
            "0% negative lag",
            f"{len(leads)} relationships use a lead; a lead is usually an unstated overlap",
            leads,
        )
    )

    # --- 3. Lags -----------------------------------------------------------
    lags = [f"{r.predecessor}->{r.successor}" for r in links if r.lag_days > 0]
    value = _pct(len(lags), n_rel)
    add(
        CheckResult(
            3,
            "Lags",
            value <= MAX_LAGS,
            round(value * 100, 1),
            "<= 5% of relationships",
            f"{len(lags)} of {n_rel} relationships carry a lag",
            lags,
        )
    )

    # --- 4. Relationship types ---------------------------------------------
    fs = [r for r in links if r.type is RelationType.FS]
    value = _pct(len(fs), n_rel)
    add(
        CheckResult(
            4,
            "Relationship Types",
            value >= MIN_FS_RELATIONSHIPS if n_rel else True,
            round(value * 100, 1),
            ">= 90% Finish-to-Start",
            f"{len(fs)} of {n_rel} relationships are FS",
            [
                f"{r.predecessor}->{r.successor} ({r.type.value})"
                for r in links
                if r.type is not RelationType.FS
            ],
        )
    )

    # --- 5. Hard constraints -----------------------------------------------
    # All ten types, split. A Start-No-Earlier-Than is how a planner records a
    # delivery date -- a fact about the world, not an override of the network --
    # so it is reported separately rather than counted against the threshold.
    hard = sorted(
        t.id
        for t in tasks
        if t.constraint is not ConstraintType.NONE and EFFECTS[t.constraint].is_hard
    )
    soft = sorted(
        t.id
        for t in tasks
        if t.constraint is not ConstraintType.NONE and not EFFECTS[t.constraint].is_hard
    )
    value = _pct(len(hard), n_act)
    add(
        CheckResult(
            5,
            "Hard Constraints",
            value <= MAX_HARD_CONSTRAINTS,
            round(value * 100, 1),
            "<= 5% of activities",
            f"{len(hard)} activities are pinned by a hard constraint "
            f"({len(soft)} more carry a soft one, which is not counted here)",
            hard,
        )
    )

    # --- 6. High float ------------------------------------------------------
    # Completed work has no float, not zero float, so it is excluded from both
    # this check and check 7.
    high_float = sorted(
        aid
        for aid in ids
        if network.total_float_days[aid] is not None
        and network.total_float_days[aid] > HIGH_FLOAT_DAYS
    )
    value = _pct(len(high_float), n_act)
    add(
        CheckResult(
            6,
            "High Float",
            value <= MAX_HIGH_FLOAT,
            round(value * 100, 1),
            f"<= 5% above {HIGH_FLOAT_DAYS} working days total float",
            f"{len(high_float)} activities have more than {HIGH_FLOAT_DAYS} days of float, "
            "which usually means missing logic rather than genuine slack",
            high_float,
        )
    )

    # --- 7. Negative float --------------------------------------------------
    negative_float = sorted(
        aid
        for aid in ids
        if network.total_float_days[aid] is not None and network.total_float_days[aid] < 0
    )
    value = _pct(len(negative_float), n_act)
    add(
        CheckResult(
            7,
            "Negative Float",
            len(negative_float) == 0,
            round(value * 100, 1),
            "0% below zero total float",
            f"{len(negative_float)} activities cannot meet their required dates",
            negative_float,
        )
    )

    # --- 8. High duration ---------------------------------------------------
    long_tasks = sorted(t.id for t in tasks if t.duration_days > HIGH_DURATION_DAYS)
    value = _pct(len(long_tasks), n_act)
    add(
        CheckResult(
            8,
            "High Duration",
            value <= MAX_HIGH_DURATION,
            round(value * 100, 1),
            f"<= 5% longer than {HIGH_DURATION_DAYS} days",
            f"{len(long_tasks)} activities run longer than one reporting quarter and "
            "cannot be progressed meaningfully",
            long_tasks,
        )
    )

    # --- 9. Invalid dates ---------------------------------------------------
    if not actual_finish:
        add(
            CheckResult(
                9,
                "Invalid Dates",
                None,
                None,
                "0% actuals in the future",
                "Skipped: no actual finish dates supplied",
            )
        )
    else:
        invalid = sorted(aid for aid, fin in actual_finish.items() if fin > data_date)
        add(
            CheckResult(
                9,
                "Invalid Dates",
                len(invalid) == 0,
                round(_pct(len(invalid), n_act) * 100, 1),
                "0% actuals in the future",
                f"{len(invalid)} activities record work completed after the data date",
                invalid,
            )
        )

    # --- 10. Resources ------------------------------------------------------
    if resourced_activity_ids is None:
        add(
            CheckResult(
                10,
                "Resources",
                None,
                None,
                "100% of working activities resourced",
                "Skipped: no resource assignments supplied",
            )
        )
    else:
        resourced = set(resourced_activity_ids)
        unresourced = sorted(t.id for t in tasks if t.duration_days > 0 and t.id not in resourced)
        working = sum(1 for t in tasks if t.duration_days > 0)
        add(
            CheckResult(
                10,
                "Resources",
                len(unresourced) == 0,
                round(_pct(len(unresourced), working) * 100, 1),
                "100% of working activities resourced",
                f"{len(unresourced)} of {working} working activities carry no resource",
                unresourced,
            )
        )

    # --- 11. Missed tasks ---------------------------------------------------
    if baseline_finish is None or not actual_finish:
        add(
            CheckResult(
                11,
                "Missed Tasks",
                None,
                None,
                "<= 5% finished late against baseline",
                "Skipped: needs both baseline and actual finish dates",
            )
        )
    else:
        missed = sorted(
            aid
            for aid, actual in actual_finish.items()
            if aid in baseline_finish and actual > baseline_finish[aid]
        )
        value = _pct(len(missed), len(actual_finish))
        add(
            CheckResult(
                11,
                "Missed Tasks",
                value <= MAX_MISSED_TASKS,
                round(value * 100, 1),
                "<= 5% finished late against baseline",
                f"{len(missed)} of {len(actual_finish)} completed activities slipped past baseline",
                missed,
            )
        )

    # --- 12. Critical path test ---------------------------------------------
    add(_critical_path_test(outcome, tasks, links, calendars, by_id))

    # --- 13. Critical Path Length Index -------------------------------------
    cp_length = outcome.duration_working_days  # type: ignore[attr-defined]
    if cp_length > 0:
        terminal = network.terminal_activity
        finish_float = network.total_float_days.get(terminal) if terminal else None
        if finish_float is None:
            finish_float = 0
        cpli = (cp_length + finish_float) / cp_length
        add(
            CheckResult(
                13,
                "Critical Path Length Index",
                cpli >= MIN_CPLI,
                round(cpli, 3),
                ">= 0.95",
                f"CPLI of {cpli:.3f} on a {cp_length}-day critical path",
            )
        )
    else:
        add(
            CheckResult(
                13,
                "Critical Path Length Index",
                None,
                None,
                ">= 0.95",
                "Skipped: zero-length critical path",
            )
        )

    # --- 14. Baseline Execution Index ---------------------------------------
    if baseline_finish is None:
        add(
            CheckResult(
                14,
                "Baseline Execution Index",
                None,
                None,
                ">= 0.95",
                "Skipped: no baseline finish dates supplied",
            )
        )
    else:
        due = [aid for aid, fin in baseline_finish.items() if fin <= data_date]
        if not due:
            # Not 1.0. Nothing was due, so the index has no denominator, and
            # calling an empty ratio "perfect" is the friendlier of two lies.
            add(
                CheckResult(
                    14,
                    "Baseline Execution Index",
                    None,
                    None,
                    ">= 0.95",
                    "Skipped: no baselined activity was due by the data date",
                )
            )
        else:
            completed = [aid for aid in due if aid in actual_finish]
            bei = _pct(len(completed), len(due))
            add(
                CheckResult(
                    14,
                    "Baseline Execution Index",
                    bei >= MIN_BEI,
                    round(bei, 3),
                    ">= 0.95",
                    f"{len(completed)} of {len(due)} activities due by the data date are complete",
                    sorted(set(due) - set(completed)),
                )
            )

    return report


def _critical_path_test(
    outcome: object,
    tasks: Sequence[Task],
    links: Sequence[Link],
    calendars: Mapping[str, WorkCalendar],
    by_id: Mapping[str, Task],
) -> CheckResult:
    """Check 12: actually run the probe rather than asserting the answer.

    Inject a long delay into the first activity on the driving path and re-run.
    A sound network moves the project finish with it; if it does not, something
    downstream -- a constraint, a broken link, a calendar -- is absorbing the
    delay, and the "critical path" the schedule reports is not the one that
    governs.

    **Restated for multiple calendars.** "The finish moved by exactly 600" is
    only well posed when one calendar governs, because the delay propagates
    through calendars of different working-day density. So: the probe passes if
    the project finish moved by the same number of calendar days as the probed
    activity's own finish moved, *and* the probe is still on the driving path.
    Under a single calendar that reduces exactly to the classic assertion, and
    ``test_check_twelve_reduces_to_the_classic_assertion`` holds us to it.
    """
    network = outcome.network  # type: ignore[attr-defined]
    path = network.longest_path()
    # Probe the first *incomplete* activity: delaying finished work proves
    # nothing, because its dates are history and will not move.
    probe_id = next(
        (aid for aid in path if not network.statuses[aid].is_complete and by_id[aid].duration_days),
        None,
    )
    if probe_id is None:
        return CheckResult(
            12,
            "Critical Path Test",
            None,
            None,
            "Project finish moves by the injected delay",
            "Skipped: no incomplete driving activity to probe",
        )

    probed_tasks = [
        replace(t, duration_days=t.duration_days + PROBE_DAYS) if t.id == probe_id else t
        for t in tasks
    ]
    try:
        probed = calculate(
            probed_tasks,
            links,
            calendars,
            data_date=outcome.data_date,  # type: ignore[attr-defined]
            options=network.options,
        )
    except Exception as exc:  # noqa: BLE001 - a probe that cannot run is a finding
        return CheckResult(
            12,
            "Critical Path Test",
            False,
            None,
            "Project finish moves by the injected delay",
            f"The probe could not be scheduled: {exc}",
            [probe_id],
        )

    finish_moved = probed.project_finish - network.project_finish
    probe_moved = probed.early_finish[probe_id] - network.early_finish[probe_id]
    still_driving = probe_id in set(probed.longest_path())

    single_calendar = len({t.calendar_id for t in tasks}) <= 1
    if single_calendar:
        cal = calendars.get(by_id[probe_id].calendar_id) or next(iter(calendars.values()))
        moved_working = cal.count_working_days(network.project_finish, probed.project_finish)
        passed = moved_working == PROBE_DAYS
        detail = (
            f"A {PROBE_DAYS}-day delay on {probe_id!r} moved the finish by "
            f"{moved_working} working days"
        )
        value: float | None = float(moved_working)
    else:
        passed = finish_moved == probe_moved and still_driving
        detail = (
            f"A {PROBE_DAYS}-day delay on {probe_id!r} moved its own finish by "
            f"{probe_moved} calendar days and the project finish by {finish_moved}; "
            f"the probe is {'still' if still_driving else 'no longer'} on the driving path"
        )
        value = float(finish_moved)

    return CheckResult(
        12,
        "Critical Path Test",
        passed,
        value,
        "Project finish moves by the injected delay",
        detail,
        [] if passed else [probe_id],
    )
