"""Data date, actuals, remaining duration, and what an out-of-sequence update means.

The single most consequential thing missing from both source engines. A schedule
with actuals must be scheduled *from the data date*, not from day zero, and what
happens when the field works out of sequence is a choice the planner makes --
not something the engine should decide silently.

The implementation trick that keeps this cheap: **the progress mode is a
transformation of the link set, applied before the forward pass.** Threading a
mode flag down into the pass would create three code paths through the
most-tested function in the package, and the two rarer ones would rot. As a link
transform, the CPM kernel never learns that progress exists, and each mode is
testable as "which links survived, and why".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .issues import IssueLog
from .network import Link, ProgressMode, RelationType, Status, Task
from .timeaxis import Instant, WorkCalendar, day_of, instant_of


@dataclass(frozen=True)
class ActivityStatus:
    """Where an activity stands as at the data date, and how we know.

    ``remaining_source`` is recorded rather than inferred later, because
    "20 days remaining because the file said so" and "20 days remaining because
    we multiplied the original duration by 1 minus a percentage" are different
    claims, and only one of them is evidence.
    """

    activity_id: str
    status: Status
    actual_start: Instant | None
    actual_finish: Instant | None
    remaining_days: int
    remaining_source: str

    @property
    def is_complete(self) -> bool:
        return self.status is Status.COMPLETE

    @property
    def is_started(self) -> bool:
        return self.status is not Status.NOT_STARTED


@dataclass(frozen=True)
class OutOfSequenceLink:
    """A successor that started before its predecessor finished.

    Not an error. It is a fact about the job, and it is the fact that makes the
    retained-logic / progress-override choice matter at all.
    """

    predecessor: str
    successor: str
    type: RelationType
    successor_started: date
    predecessor_incomplete: bool


@dataclass(frozen=True)
class EffectiveLink:
    """A link as the forward pass will actually see it.

    ``suppressed`` links are kept in the list rather than filtered out so the
    caller can report *what progress override dropped* -- a mode that silently
    removes logic and never says which is indistinguishable from a bug.
    """

    predecessor: str
    successor: str
    type: RelationType
    lag_days: int
    suppressed: bool = False
    origin: str = "logic"

    @property
    def source(self) -> Link:
        return Link(self.predecessor, self.successor, self.type, self.lag_days)


def derive_status(
    task: Task,
    data_date: Instant,
    cal: WorkCalendar,
    issues: IssueLog,
) -> ActivityStatus:
    """Classify one activity and settle how much work is left.

    Remaining duration precedence, most trustworthy first:

    1. an explicit ``remaining_days`` -- somebody stated it;
    2. zero, if the activity is finished;
    3. the original duration, if it has not started;
    4. **last resort**, ``original x (1 - percent)``, with a warning.

    Step 4 is the one that lies, so it is the only one that emits an issue.
    """
    actual_start = instant_of(task.actual_start) if task.actual_start else None
    actual_finish = instant_of(task.actual_finish) if task.actual_finish else None

    if actual_finish is not None:
        status = Status.COMPLETE
    elif actual_start is not None:
        status = Status.IN_PROGRESS
    else:
        status = Status.NOT_STARTED

    # Actuals in the future are reported and used as given. Clamping them
    # fabricates history, and it makes DCMA check 9 pass on a schedule that
    # should fail it.
    for label, value in (("actual_start", actual_start), ("actual_finish", actual_finish)):
        if value is not None and value > data_date:
            issues.error(
                "PROGRESS.ACTUAL_IN_FUTURE",
                f"{task.id}: {label} {day_of(value)} is after the data date {day_of(data_date)}",
                "used as given; the data date or the actual is wrong",
                row_key=task.id,
                field_name=label,
                raw_value=day_of(value),
            )

    if task.remaining_days is not None:
        remaining, source = max(0, task.remaining_days), "explicit"
        if status is Status.COMPLETE and remaining != 0:
            issues.warn(
                "PROGRESS.REMAINING_ON_COMPLETE",
                f"{task.id}: finished, but carries {remaining} days remaining",
                "remaining set to 0; the actual finish is the stronger statement",
                row_key=task.id,
                field_name="remaining_days",
                raw_value=remaining,
            )
            remaining, source = 0, "complete"
    elif status is Status.COMPLETE:
        remaining, source = 0, "complete"
    elif status is Status.NOT_STARTED:
        remaining, source = task.duration_days, "original"
    elif task.percent_complete is not None:
        pct = min(max(task.percent_complete, 0.0), 1.0)
        remaining = max(0, round(task.duration_days * (1.0 - pct)))
        source = "derived_from_percent"
        issues.warn(
            "PROGRESS.REMAINING_DERIVED_FROM_PERCENT",
            f"{task.id}: in progress with no remaining duration; derived "
            f"{remaining} days from {pct:.0%} complete",
            "assumes linear productivity, which is how an updated schedule lies",
            row_key=task.id,
            field_name="remaining_days",
        )
    else:
        remaining, source = task.duration_days, "original"
        issues.warn(
            "PROGRESS.REMAINING_UNKNOWN",
            f"{task.id}: in progress with neither remaining duration nor percent complete",
            "assumed the full original duration remains",
            row_key=task.id,
            field_name="remaining_days",
        )

    _ = cal  # calendars matter for dates, not for classification; kept for symmetry
    return ActivityStatus(
        activity_id=task.id,
        status=status,
        actual_start=actual_start,
        actual_finish=actual_finish,
        remaining_days=remaining,
        remaining_source=source,
    )


def out_of_sequence(
    statuses: Mapping[str, ActivityStatus], links: Sequence[Link]
) -> list[OutOfSequenceLink]:
    """Links where the successor started before the predecessor delivered."""
    found: list[OutOfSequenceLink] = []
    for link in links:
        pred = statuses.get(link.predecessor)
        succ = statuses.get(link.successor)
        if pred is None or succ is None:
            continue
        if not succ.is_started or succ.actual_start is None:
            continue
        if link.type in (RelationType.FS, RelationType.FF) and pred.is_complete:
            continue
        if link.type in (RelationType.SS, RelationType.SF) and pred.is_started:
            continue
        found.append(
            OutOfSequenceLink(
                predecessor=link.predecessor,
                successor=link.successor,
                type=link.type,
                successor_started=day_of(succ.actual_start),
                predecessor_incomplete=not pred.is_complete,
            )
        )
    return found


def effective_links(
    links: Sequence[Link],
    statuses: Mapping[str, ActivityStatus],
    mode: ProgressMode,
) -> list[EffectiveLink]:
    """Rewrite the link set for the chosen progress mode.

    This is the entire implementation of retained logic versus progress
    override. The forward pass reads the result and never knows a choice was
    made.
    """
    out: list[EffectiveLink] = []
    for link in links:
        pred = statuses.get(link.predecessor)
        succ = statuses.get(link.successor)
        suppressed = False
        origin = "logic"

        if mode is ProgressMode.PROGRESS_OVERRIDE and pred is not None and succ is not None:
            # Drop the constraint only where the field has already contradicted
            # it: an incomplete predecessor feeding a successor that has started.
            # Dropping it anywhere else would discard logic that is still true.
            if succ.is_started and not pred.is_complete:
                suppressed = True
                origin = "override"
        elif mode is ProgressMode.RETAINED_LOGIC and pred is not None and succ is not None:
            if succ.is_started and not pred.is_complete:
                origin = "retained"
        elif mode is ProgressMode.ACTUAL_DATES:
            origin = "actual"

        out.append(
            EffectiveLink(
                predecessor=link.predecessor,
                successor=link.successor,
                type=link.type,
                lag_days=link.lag_days,
                suppressed=suppressed,
                origin=origin,
            )
        )
    return out


def default_data_date(tasks: Sequence[Task], fallback: date) -> date:
    """The data date to use when the caller did not supply one.

    The latest recorded actual, if there is one -- a schedule carrying actuals
    and scheduled from its planned start would report all of that work as still
    to do. Otherwise the caller's fallback, normally the project start.
    """
    actuals = [t.actual_finish or t.actual_start for t in tasks]
    dated = [d for d in actuals if d is not None]
    return max(dated) if dated else fallback
