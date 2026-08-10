"""The frozen types the scheduler operates on.

Separated from the algorithm so that ``constraints``, ``progress_logic``,
``cpm`` and ``model`` can all name the same ``RelationType`` without importing
each other. Types here carry no behaviour beyond validation -- if a function
here starts scheduling something, it belongs in ``cpm``.

Everything is a frozen dataclass. The scheduler is called two thousand times
inside a Monte Carlo simulation, and a mutable input that one iteration edits is
a bug that only shows up as noise in the P80.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .constraints import ConstraintType


class ActivityKind(str, Enum):
    """What sort of thing an activity is.

    ``LEVEL_OF_EFFORT`` and ``WBS_SUMMARY`` are spans derived from their
    children rather than work in their own right; they are carried through
    interchange and excluded from the driving path, because a summary bar being
    "critical" is an artefact of its children, not a fact about the job.
    """

    TASK = "task"
    START_MILESTONE = "start_milestone"
    FINISH_MILESTONE = "finish_milestone"
    LEVEL_OF_EFFORT = "level_of_effort"
    WBS_SUMMARY = "wbs_summary"

    @property
    def is_milestone(self) -> bool:
        return self in (ActivityKind.START_MILESTONE, ActivityKind.FINISH_MILESTONE)

    @property
    def is_derived(self) -> bool:
        """True when the span is a rollup of other activities, not work itself."""
        return self in (ActivityKind.LEVEL_OF_EFFORT, ActivityKind.WBS_SUMMARY)


class RelationType(str, Enum):
    """The four precedence relationships.

    Read as "predecessor-side to successor-side": ``FS`` ties the predecessor's
    finish to the successor's start.
    """

    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"

    @property
    def drives_successor_finish(self) -> bool:
        """True for FF and SF, which bound the successor's finish, not its start."""
        return self in (RelationType.FF, RelationType.SF)

    @property
    def from_predecessor_start(self) -> bool:
        """True for SS and SF, which read the predecessor's start, not its finish."""
        return self in (RelationType.SS, RelationType.SF)


class LagCalendar(str, Enum):
    """Whose working days a lag is counted in.

    Not a detail. A five-day lag from a Mon-Fri predecessor into a Mon-Sat
    successor lands on a different date depending on the answer, and both dates
    look plausible. ``PREDECESSOR`` is Primavera's default and therefore ours;
    the file's own ``SCHEDOPTIONS`` overrides it on import, and the resolved
    choice is recorded on the result so a disagreement with P6 is explicable.
    """

    PREDECESSOR = "predecessor"
    SUCCESSOR = "successor"
    TWENTY_FOUR_HOUR = "twenty_four_hour"
    PROJECT_DEFAULT = "project_default"


class ProgressMode(str, Enum):
    """What an out-of-sequence update means.

    ``RETAINED_LOGIC`` (Primavera's default) keeps the relationship: remaining
    work on a started successor still waits for its incomplete predecessor.
    ``PROGRESS_OVERRIDE`` drops that link, on the argument that the field has
    already demonstrated the sequence was not real. ``ACTUAL_DATES`` drives from
    recorded actuals rather than forecasts.

    The two give materially different finish dates on the same file. Which one
    produced a given answer is recorded on the result.
    """

    RETAINED_LOGIC = "retained_logic"
    PROGRESS_OVERRIDE = "progress_override"
    ACTUAL_DATES = "actual_dates"


class Status(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass(frozen=True)
class Task:
    """One schedulable activity.

    ``remaining_days`` is deliberately separate from ``duration_days`` and
    deliberately not derived from a percentage. Percent complete is a claim
    about work done; remaining duration is a claim about work left. Deriving one
    from the other assumes linear productivity, and it is the commonest way an
    updated schedule lies -- the activity has been 90% complete for three months
    and a derived remaining of half a day keeps the forecast finish exactly
    where it was.
    """

    id: str
    name: str = ""
    duration_days: int = 0
    calendar_id: str = "STD"
    kind: ActivityKind = ActivityKind.TASK
    constraint: ConstraintType = ConstraintType.NONE
    constraint_date: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    remaining_days: int | None = None
    percent_complete: float | None = None

    def __post_init__(self) -> None:
        if self.duration_days < 0:
            raise ValueError(f"{self.id}: negative duration {self.duration_days}")
        if self.kind.is_milestone and self.duration_days != 0:
            raise ValueError(
                f"{self.id}: a {self.kind.value} has duration {self.duration_days}; "
                "a milestone is an instant"
            )
        if self.constraint.needs_date and self.constraint_date is None:
            raise ValueError(
                f"{self.id}: constraint {self.constraint.value} needs a constraint_date"
            )
        if self.actual_finish is not None and self.actual_start is None:
            raise ValueError(
                f"{self.id}: has an actual finish but no actual start; "
                "work cannot end before it began"
            )
        if (
            self.actual_start is not None
            and self.actual_finish is not None
            and self.actual_finish < self.actual_start
        ):
            raise ValueError(
                f"{self.id}: actual finish {self.actual_finish} precedes "
                f"actual start {self.actual_start}"
            )


@dataclass(frozen=True)
class Link:
    """A precedence relationship with an optional lead or lag.

    ``lag_days`` may be negative -- a lead. Leads are legal and occasionally
    correct; DCMA check 3 counts them because they are more often a modelling
    shortcut for an unstated overlap.
    """

    predecessor: str
    successor: str
    type: RelationType = RelationType.FS
    lag_days: int = 0

    @property
    def key(self) -> tuple[str, str, str, int]:
        """A stable identity for diffing and for deterministic tiebreaks."""
        return (self.predecessor, self.successor, self.type.value, self.lag_days)


@dataclass(frozen=True)
class SchedulerOptions:
    """Everything about *how* to schedule, separated from *what*.

    Carried onto the result so that two runs producing different dates can be
    explained by comparing their options rather than by guessing.
    """

    progress_mode: ProgressMode = ProgressMode.RETAINED_LOGIC
    lag_calendar: LagCalendar = LagCalendar.PREDECESSOR
    must_finish_by: date | None = None
    open_ends_are_critical: bool = False
    #: What the source file said, verbatim, whether or not we honoured it.
    source_options: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "progress_mode": self.progress_mode.value,
            "lag_calendar": self.lag_calendar.value,
            "must_finish_by": self.must_finish_by.isoformat() if self.must_finish_by else None,
            "open_ends_are_critical": self.open_ends_are_critical,
            "source_options": dict(self.source_options),
        }
