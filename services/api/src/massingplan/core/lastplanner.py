"""Last Planner: commitments, the constraints that block them, and PPC.

Everything else in this package answers "when *can* this happen". Last Planner
answers a different question -- "what did we say we would do, and did we do
it" -- and the gap between those two is where construction projects are
actually lost. A schedule is a forecast; a commitment is a promise, and only
the second one can be broken.

The measurement is PPC: **commitments completed, over commitments made**, per
week. It is a measure of *plan reliability*, not of progress. A crew that
finished twice what it promised has a PPC of 100%, not 200%, because promising
badly is the thing being measured.

What this module is built to make hard
--------------------------------------
PPC is trivially gameable, and every way of gaming it is a way of making the
number go up while the site gets worse. So:

* **The denominator is frozen when the week is committed.** A commitment added
  mid-week does not join it and a commitment quietly withdrawn does not leave
  it. Re-planning the week after seeing how it went is how PPC becomes a
  measure of nothing.
* **Partial completion is not partial credit.** A commitment is met or it is
  not. "80% done" is a commitment that was not met, and the whole value of the
  number is that it refuses to average away a broken promise.
* **An unassessed commitment makes the week unmeasurable, not perfect.** PPC is
  `None` until every commitment has an answer -- the same tri-state the DCMA
  checks use, for the same reason: a missing measurement reported as a good
  one is worse than no measurement.
* **A missed commitment must carry a reason.** Not optional and never
  defaulted. The reasons are the entire learning loop; PPC without them is a
  number nobody can act on.
* **Only make-ready work can be committed.** Committing work whose constraints
  are still live is precisely what this method exists to stop, so it is
  refused rather than warned about.

What it deliberately does not do
--------------------------------
* **No lifetime average PPC.** The signal is the trend; one number across six
  months hides the month it collapsed. `trend()` returns the series.
* **No automatic constraint removal.** A constraint is removed by a person who
  says so, on a date. Inferring it from the schedule would mean the plan
  marking its own homework.
* **No scheduling.** This module never moves a date. It records what was
  promised against a plan the rest of the package produced.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .issues import IssueLog


class LastPlannerError(ValueError):
    """A commitment or plan that cannot be recorded as stated."""


class ConstraintKind(str, Enum):
    """The categories work gets stuck behind.

    Named rather than free text: a constraint log where everyone writes their
    own category cannot be counted, and counting them is what tells a project
    whether it has a design problem or a procurement problem.
    """

    DESIGN = "design"
    INFORMATION = "information"
    MATERIALS = "materials"
    LABOUR = "labour"
    EQUIPMENT = "equipment"
    PERMITS = "permits"
    PREREQUISITE_WORK = "prerequisite_work"
    SPACE = "space"
    EXTERNAL = "external"


class VarianceReason(str, Enum):
    """Why a commitment was not met.

    `NOT_RECORDED` exists and is *named* rather than left as an empty field. A
    blank reason and "nobody wrote down why" are the same fact, and having a
    value for it means the count of unexplained failures is itself reportable
    -- which is usually the first thing worth fixing about a Last Planner
    implementation.
    """

    PREREQUISITE_WORK = "prerequisite_work"
    MATERIALS = "materials"
    LABOUR = "labour"
    EQUIPMENT = "equipment"
    INFORMATION = "information"
    DESIGN_CHANGE = "design_change"
    DIRECTIVE = "directive"
    WEATHER = "weather"
    ACCESS = "access"
    #: The commitment was never achievable in the time promised. Distinct from
    #: every other reason: those are things that happened *to* the plan, and
    #: this one is the plan.
    OVER_COMMITMENT = "over_commitment"
    NOT_RECORDED = "not_recorded"


@dataclass(frozen=True)
class Constraint:
    """Something that must be cleared before work can be promised.

    `owner` and `promised_by` are required rather than optional. A constraint
    with no owner is not being removed by anybody, and a constraint with no
    date is not being removed this week -- both are how a constraint log turns
    into a list nobody reads.
    """

    id: str
    description: str
    kind: ConstraintKind
    owner: str
    promised_by: date
    #: The day somebody said it was cleared. `None` means still live.
    removed_on: date | None = None

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise LastPlannerError("every constraint needs an id")
        if not str(self.owner).strip():
            raise LastPlannerError(f"{self.id}: a constraint needs an owner")
        if self.removed_on is not None and self.removed_on < self.promised_by - timedelta(days=365):
            raise LastPlannerError(f"{self.id}: removed_on is implausibly early")

    def is_live(self, on: date) -> bool:
        """Still blocking, as at `on`.

        A constraint removed *later* than the day being asked about is still
        live on that day. Reading `removed_on is None` alone would let a
        constraint cleared next Friday make this Monday's plan look ready.
        """
        return self.removed_on is None or self.removed_on > on

    def is_overdue(self, on: date) -> bool:
        return self.is_live(on) and self.promised_by < on


@dataclass
class Commitment:
    """One promise, by one crew, for one week.

    `completed` is tri-state on purpose. `None` is "not yet assessed", which is
    a different fact from `False` and must not be counted as either.
    """

    id: str
    activity_id: str
    description: str
    crew: str
    constraints: tuple[Constraint, ...] = ()
    completed: bool | None = None
    reason: VarianceReason | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise LastPlannerError("every commitment needs an id")
        if not str(self.crew).strip():
            raise LastPlannerError(f"{self.id}: a commitment needs a crew to make it")
        if self.completed is False and self.reason is None:
            # Refused, not defaulted. A missed commitment with no reason is the
            # one piece of data this whole method exists to collect, and
            # silently filling it in with OTHER is how a constraint log becomes
            # a hundred rows of "other".
            raise LastPlannerError(
                f"{self.id}: a commitment that was not met needs a reason -- "
                f"use {VarianceReason.NOT_RECORDED.value!r} if nobody gave one, "
                "so that it can be counted"
            )
        if self.completed is True and self.reason is not None:
            raise LastPlannerError(f"{self.id}: a completed commitment has no variance reason")

    def live_constraints(self, on: date) -> tuple[Constraint, ...]:
        return tuple(c for c in self.constraints if c.is_live(on))

    def is_make_ready(self, on: date) -> bool:
        """Every constraint cleared as at `on`. The precondition for promising."""
        return not self.live_constraints(on)


@dataclass(frozen=True)
class WeeklyPlan:
    """The commitments made for one week, and how they turned out.

    `week_starting` is the Monday. The week is the half-open span
    `[week_starting, week_starting + 7)`, the same convention the rest of the
    package uses for every other span -- so the last day *in* the week is
    `week_starting + 6`, and the boundary belongs to the next week.
    """

    week_starting: date
    commitments: tuple[Commitment, ...]

    def __post_init__(self) -> None:
        if self.week_starting.weekday() != 0:
            raise LastPlannerError(
                f"a weekly work plan starts on a Monday, not a {self.week_starting.strftime('%A')}"
            )
        seen: set[str] = set()
        for commitment in self.commitments:
            if commitment.id in seen:
                raise LastPlannerError(f"duplicate commitment id {commitment.id!r}")
            seen.add(commitment.id)

    @property
    def week_ends(self) -> date:
        """The first day *not* in this week. Half-open, like every other span."""
        return self.week_starting + timedelta(days=7)

    @property
    def last_day(self) -> date:
        return self.week_starting + timedelta(days=6)

    @property
    def committed(self) -> int:
        """The denominator, and it is every commitment made.

        Not "every commitment still on the list", and not "every commitment
        that was assessed". Shrinking the denominator after the fact is the
        commonest way PPC is made to look good.
        """
        return len(self.commitments)

    @property
    def completed(self) -> int:
        return sum(1 for c in self.commitments if c.completed is True)

    @property
    def unassessed(self) -> tuple[Commitment, ...]:
        return tuple(c for c in self.commitments if c.completed is None)

    def ppc(self) -> float | None:
        """Completed over committed, or `None` when the week cannot be measured.

        `None` in two cases, and both are honest:

        * nothing was committed -- there is no reliability to report, and 0%
          would blame a crew for a week nobody planned;
        * something is still unassessed -- the answer would move once it is
          filled in, and a number that will change is not a measurement.
        """
        if not self.commitments or self.unassessed:
            return None
        return self.completed / self.committed

    def variance(self) -> dict[VarianceReason, int]:
        """Counts by reason. The half of PPC that can actually be acted on."""
        counted = Counter(
            c.reason for c in self.commitments if c.completed is False and c.reason is not None
        )
        return dict(counted)


def screen(
    commitments: list[Commitment], *, on: date, issues: IssueLog | None = None
) -> tuple[list[Commitment], list[Commitment]]:
    """Split a lookahead into what can be promised and what cannot.

    Returns `(make_ready, blocked)`. The blocked list is the more useful half:
    it is the make-ready meeting's agenda, and every entry names an owner and a
    date somebody agreed to.
    """
    issues = issues if issues is not None else IssueLog()
    ready: list[Commitment] = []
    blocked: list[Commitment] = []
    for commitment in commitments:
        live = commitment.live_constraints(on)
        if not live:
            ready.append(commitment)
            continue
        blocked.append(commitment)
        for constraint in live:
            if constraint.is_overdue(on):
                issues.warn(
                    "LP_CONSTRAINT_OVERDUE",
                    f"{constraint.description} was promised by "
                    f"{constraint.promised_by.isoformat()} and is still open",
                    f"{constraint.owner} owns it; it blocks {commitment.description}",
                    row_key=constraint.id,
                    raw_value=constraint.kind.value,
                )
    return ready, blocked


def commit(
    week_starting: date,
    commitments: list[Commitment],
    *,
    on: date | None = None,
    allow_constrained: bool = False,
) -> WeeklyPlan:
    """Freeze a week's promises, refusing work that is not make-ready.

    This refusal is the method. Committing work whose constraints are still
    live is exactly what Last Planner exists to prevent, and a system that
    merely warns about it will be used to commit constrained work every week --
    the warning becomes wallpaper by the third sprint.

    `allow_constrained` exists for importing history, where the constraints
    were never recorded and refusing would mean losing the data. It is not a
    convenience for planning.
    """
    if on is None:
        on = week_starting
    if not allow_constrained:
        blocked = [c for c in commitments if not c.is_make_ready(on)]
        if blocked:
            detail = "; ".join(
                f"{c.description} ({', '.join(x.kind.value for x in c.live_constraints(on))})"
                for c in blocked[:5]
            )
            more = f" -- and {len(blocked) - 5} more" if len(blocked) > 5 else ""
            raise LastPlannerError(
                f"{len(blocked)} of {len(commitments)} commitments are not make-ready: "
                f"{detail}{more}"
            )
    return WeeklyPlan(week_starting=week_starting, commitments=tuple(commitments))


@dataclass(frozen=True)
class Reliability:
    """PPC over time, and what went wrong. Never a single lifetime number."""

    weeks: tuple[WeeklyPlan, ...]
    issues: IssueLog = field(default_factory=IssueLog)

    def trend(self) -> list[tuple[date, float | None]]:
        """`(week, ppc)` in order. `None` where the week is unmeasurable.

        A list rather than an average, because the average is the one shape
        that cannot show the thing worth seeing: PPC at 80% for five weeks and
        30% for one is a project with a problem in week six, and 72% is a
        project with nothing to look at.
        """
        return [
            (w.week_starting, w.ppc()) for w in sorted(self.weeks, key=lambda w: w.week_starting)
        ]

    def measurable_weeks(self) -> tuple[WeeklyPlan, ...]:
        return tuple(w for w in self.weeks if w.ppc() is not None)

    def mean_ppc(self) -> float | None:
        """The average across *measurable* weeks, or `None` when there are none.

        Provided because it is asked for, and computed only over weeks that
        have an answer -- averaging `None` as zero would punish a project for
        weeks nobody assessed, which is a reporting failure and not a
        production one.
        """
        measurable = self.measurable_weeks()
        if not measurable:
            return None
        values = [w.ppc() or 0.0 for w in measurable]
        return sum(values) / len(values)

    def variance(self) -> dict[VarianceReason, int]:
        """Every missed commitment, by reason, across every week."""
        total: Counter[VarianceReason] = Counter()
        for week in self.weeks:
            total.update(week.variance())
        return dict(total)

    def top_reasons(self, limit: int = 3) -> list[tuple[VarianceReason, int]]:
        """The biggest causes first. Ties broken by name, so the answer is
        stable across runs rather than dependent on dict ordering.
        """
        return sorted(self.variance().items(), key=lambda kv: (-kv[1], kv[0].value))[:limit]

    def to_dict(self) -> dict[str, object]:
        return {
            "weeks": [
                {
                    "week_starting": week.week_starting.isoformat(),
                    "last_day": week.last_day.isoformat(),
                    "committed": week.committed,
                    "completed": week.completed,
                    "unassessed": len(week.unassessed),
                    "ppc": week.ppc(),
                    "variance": {k.value: v for k, v in week.variance().items()},
                }
                for week in sorted(self.weeks, key=lambda w: w.week_starting)
            ],
            "mean_ppc": self.mean_ppc(),
            "measurable_weeks": len(self.measurable_weeks()),
            "top_reasons": [{"reason": r.value, "count": n} for r, n in self.top_reasons()],
            "issues": self.issues.to_list(),
        }


def assess(weeks: list[WeeklyPlan], *, issues: IssueLog | None = None) -> Reliability:
    """Build the reliability picture, and say what makes it unreliable.

    The issues are about the *measurement* rather than the work: a week nobody
    assessed, a week nobody planned, and unexplained failures. Each one makes
    the number mean less, and none of them is visible in the number itself.
    """
    issues = issues if issues is not None else IssueLog()
    for week in sorted(weeks, key=lambda w: w.week_starting):
        label = week.week_starting.isoformat()
        if not week.commitments:
            issues.warn(
                "LP_EMPTY_WEEK",
                f"the week of {label} has no commitments",
                "a week with no plan has no reliability to measure -- it is "
                "excluded rather than scored zero",
                row_key=label,
            )
            continue
        if week.unassessed:
            issues.warn(
                "LP_WEEK_NOT_ASSESSED",
                f"{len(week.unassessed)} of {week.committed} commitments in the "
                f"week of {label} were never assessed",
                "PPC for this week is reported as unmeasurable rather than "
                "computed over the ones that were answered",
                row_key=label,
                raw_value=len(week.unassessed),
            )
        unexplained = sum(1 for c in week.commitments if c.reason is VarianceReason.NOT_RECORDED)
        if unexplained:
            issues.info(
                "LP_VARIANCE_UNEXPLAINED",
                f"{unexplained} missed commitments in the week of {label} have no reason",
                "the reasons are the learning loop; PPC without them is a number nobody can act on",
                row_key=label,
                raw_value=unexplained,
            )
    return Reliability(weeks=tuple(weeks), issues=issues)
