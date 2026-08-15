"""Modelled delay analysis: impacted as-planned, and collapsed as-built.

`windows.py` is observational -- AACE 29R-03 MIP 3.3 -- and changes nothing. It
reads the updates the project produced and says which period lost the time.
These two methods do the opposite: they **alter the network** to answer a
counterfactual.

* **Impacted as-planned** (MIP 3.6, additive, single base) inserts delay events
  into the as-planned programme and reports what the finish becomes. It answers
  "if these events had happened to the plan, when would it have finished".
* **Collapsed as-built** (MIP 3.9, subtractive) removes them from the as-built
  programme and reports what the finish would have been. It answers "but for
  these events, when would it actually have finished".

They live here and not in `windows` on purpose. Mixing an observational method
with a modelled one in the same call is how an analysis acquires a conclusion
its inputs do not support, and both standards are emphatic that the choice of
method is itself an argument to be made and defended. The method names itself
in every result so a report cannot quietly present one as the other.

Concurrency is the finding, not a footnote
------------------------------------------
Insert two delays separately and each may push the finish five days. Insert
them together and the finish may move five days, not ten -- because they ran
concurrently and only one of them was ever driving. That gap is the single most
argued number in delay disputes, and an analysis that reports only the sum is
making the claimant's case rather than measuring.

So both are reported: each event's impact **on its own**, and the impact of all
of them **together**, with the difference named `concurrency_days`. When they
agree the events were independent and the sum is honest. When they do not, the
difference is the overlap, and it is stated rather than left for somebody to
notice.

What this cannot do
-------------------
It does not decide whose delay it was. `responsibility` is carried through
untouched because it is a contractual question settled by the contract, not by
a critical path -- and an engine that assigned it would be answering a question
nobody asked it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from .constraints import ConstraintType
from .network import Link, RelationType, SchedulerOptions, Task
from .schedule import ScheduleOutcome, schedule_network
from .timeaxis import WorkCalendar, instant_of, standard_calendar

#: Prefixed so an inserted event can never collide with a real activity id, and
#: so a reader of the impacted network can see at a glance what was added.
EVENT_PREFIX = "DELAY::"


class ModelledDelayError(ValueError):
    """The model cannot be built as described. Refused, not approximated."""


@dataclass(frozen=True)
class DelayEvent:
    """One delay, and where it attaches to the network.

    `impacts` names the activity the event delays. The event is inserted as its
    predecessor, Finish-to-Start -- which is what "this held that up" means in a
    network, and is the only attachment that needs no further assumption.
    """

    id: str
    name: str
    duration_days: int
    impacts: str
    calendar_id: str | None = None
    #: The earliest the event could have begun. Without one it is free to float
    #: back to the data date, which understates its impact; with one it cannot
    #: start before the thing that caused it.
    onset: date | None = None
    #: Carried, never computed. Whose delay it was is a contractual question.
    responsibility: str = ""

    def __post_init__(self) -> None:
        if self.duration_days < 0:
            raise ModelledDelayError(f"{self.id}: a delay cannot have a negative duration")
        if not str(self.id).strip():
            raise ModelledDelayError("every delay event needs an id")

    @property
    def activity_id(self) -> str:
        return f"{EVENT_PREFIX}{self.id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "duration_days": self.duration_days,
            "impacts": self.impacts,
            "onset": self.onset.isoformat() if self.onset else None,
            "responsibility": self.responsibility,
        }


@dataclass(frozen=True)
class EventImpact:
    """What one event does on its own."""

    event: DelayEvent
    finish_without: date
    finish_with: date
    #: **Working days**, counted on the project calendar. Not calendar days.
    #:
    #: A schedule metric quoted in calendar days silently rewards a programme
    #: for having its weekends in the right places, and here it did worse than
    #: that: two delays of two and one working days, in series, moved the
    #: finish three working days -- which spanned a weekend and read as *five*
    #: calendar days against a "sum" of three. The result was a **negative
    #: concurrency**, a number that cannot exist, reported on 14 of 150 random
    #: networks. Delays were never amplifying each other; the arithmetic was
    #: being done on the wrong axis.
    days: int = 0

    @property
    def calendar_days(self) -> int:
        """The same move in calendar days, for a reader who wants elapsed time.

        Reported alongside rather than instead: it is the right number for "how
        long did the client wait" and the wrong one for any arithmetic.
        """
        return (self.finish_with - self.finish_without).days

    def to_dict(self) -> dict[str, object]:
        return {
            **self.event.to_dict(),
            "finish_without": self.finish_without.isoformat(),
            "finish_with": self.finish_with.isoformat(),
            "days": self.days,
            "calendar_days": self.calendar_days,
        }


@dataclass(frozen=True)
class ModelledResult:
    """A counterfactual, with the method that produced it attached."""

    method: str
    mip: str
    unimpacted_finish: date
    impacted_finish: date
    per_event: tuple[EventImpact, ...]
    events: tuple[DelayEvent, ...]
    #: Working days, on the same axis as every `EventImpact.days`.
    total_days: int = 0
    outcome: ScheduleOutcome | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_calendar_days(self) -> int:
        return (self.impacted_finish - self.unimpacted_finish).days

    @property
    def sum_of_individual_days(self) -> int:
        return sum(impact.days for impact in self.per_event)

    @property
    def concurrency_days(self) -> int:
        """How much the individual impacts overstate the combined one.

        Zero when the events were independent. Positive when they overlapped:
        two five-day delays running concurrently move the finish five days, not
        ten, and this is the five nobody is entitled to twice.
        """
        return self.sum_of_individual_days - self.total_days

    @property
    def is_concurrent(self) -> bool:
        return self.concurrency_days != 0

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "mip": self.mip,
            "unimpacted_finish": self.unimpacted_finish.isoformat(),
            "impacted_finish": self.impacted_finish.isoformat(),
            "total_days": self.total_days,
            "total_calendar_days": self.total_calendar_days,
            "sum_of_individual_days": self.sum_of_individual_days,
            "concurrency_days": self.concurrency_days,
            "is_concurrent": self.is_concurrent,
            "per_event": [impact.to_dict() for impact in self.per_event],
            "notes": list(self.notes),
        }


def _as_activity(event: DelayEvent, default_calendar: str) -> Task:
    kwargs: dict[str, object] = {}
    if event.onset is not None:
        # Soft, never mandatory: the event cannot start before it happened, but
        # it must not be able to drag work *earlier* than the logic allows.
        kwargs["constraint"] = ConstraintType.START_ON_OR_AFTER
        kwargs["constraint_date"] = event.onset
    return Task(
        id=event.activity_id,
        name=event.name or event.id,
        duration_days=event.duration_days,
        calendar_id=event.calendar_id or default_calendar,
        **kwargs,  # type: ignore[arg-type]
    )


def _impose(
    tasks: Sequence[Task],
    links: Sequence[Link],
    events: Sequence[DelayEvent],
    default_calendar: str,
) -> tuple[list[Task], list[Link]]:
    """The network with these events inserted *into* the chain, not beside it.

    An event delaying activity X takes over X's incoming logic: whatever fed X
    now feeds the event, and the event feeds X. That is what inserting a delay
    into a network means, and the alternative -- hanging the event off X as an
    extra predecessor with no predecessors of its own -- is subtly wrong in a
    way that took a failing control test to notice.

    An event with no predecessors floats back to the data date. So it runs
    alongside everything upstream of it, and **every pair of events comes out
    concurrent** however far apart in the programme they actually sat. Every
    construction tried against the loose version reported the same seven days
    of concurrency, which is the shape of an artefact rather than a finding:
    two delays a month apart on the same path are sequential, and the analysis
    said they overlapped entirely.

    Inheriting the predecessors makes an event driven by the work in front of
    it, so a delay early in the chain pushes a later one, and the two add up
    exactly as they did on site.
    """
    out_tasks = list(tasks)
    out_links: list[Link] = []
    impacted = {event.impacts for event in events}
    # Everything that fed an impacted activity now feeds the event instead.
    # Two events on the same activity both inherit its predecessors and both
    # feed it, so they run in parallel -- which is the concurrent case, and is
    # what happened on site when two things held up the same work at once.
    rerouted: dict[str, list[str]] = {aid: [] for aid in impacted}
    for event in events:
        rerouted[event.impacts].append(event.activity_id)

    for link in links:
        # **Only Finish-Start logic is rerouted.** An FS link says "that must
        # finish before this starts", and putting the delay in between preserves
        # exactly that meaning.
        #
        # SS, FF and SF do not survive the move. `A --SS--> B` ties B's *start*
        # to A's start; reroute it and B instead starts after an event that
        # began with A, which is a longer and different constraint -- and the
        # original tie on B is gone. Probing caught this as **negative
        # concurrency**: two delays together moved the finish further than the
        # sum of each alone, which is impossible for real delays and was the
        # rerouting inventing path length. So the other three stay pointing at
        # the activity and the event is simply an additional FS predecessor.
        if link.successor in rerouted and link.type is RelationType.FS:
            for event_id in rerouted[link.successor]:
                out_links.append(replace(link, successor=event_id))
        else:
            out_links.append(link)

    for event in events:
        out_tasks.append(_as_activity(event, default_calendar))
        out_links.append(Link(event.activity_id, event.impacts, RelationType.FS, 0))
    return out_tasks, out_links


def _project_calendar(calendars: Mapping[str, WorkCalendar] | None) -> WorkCalendar:
    """The calendar the finish move is counted on.

    The first supplied, which for a single-calendar programme is the only one.
    On a mixed-calendar network the project finish is a single date and any
    consistent calendar makes the count comparable between runs, which is what
    the arithmetic needs.
    """
    return next(iter((calendars or {}).values()), standard_calendar())


def _moved(calendar: WorkCalendar, before: date, after: date) -> int:
    """Working days between two finishes. Signed; never clamped."""
    if after == before:
        return 0
    if after > before:
        return calendar.count_working_days(instant_of(before), instant_of(after))
    return -calendar.count_working_days(instant_of(after), instant_of(before))


def _check(tasks: Sequence[Task], events: Sequence[DelayEvent]) -> None:
    known = {t.id for t in tasks}
    for event in events:
        if event.impacts not in known:
            raise ModelledDelayError(
                f"event {event.id!r} impacts activity {event.impacts!r}, which is not in this "
                "network. An event attached to nothing delays nothing, and would be reported "
                "as a zero-day impact rather than as the mistake it is"
            )
        if event.activity_id in known:
            raise ModelledDelayError(
                f"event {event.id!r} collides with an existing activity {event.activity_id!r}"
            )
    seen: set[str] = set()
    for event in events:
        if event.id in seen:
            raise ModelledDelayError(f"event {event.id!r} appears twice")
        seen.add(event.id)


def impacted_as_planned(
    tasks: Sequence[Task],
    links: Sequence[Link],
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    events: Sequence[DelayEvent],
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> ModelledResult:
    """**AACE 29R-03 MIP 3.6** -- modelled, additive, single base.

    Insert the events into the as-planned programme and reschedule. The network
    passed in should be the *baseline*: impacting a progressed schedule is a
    different method with a different name, and doing it here by accident is
    how an analysis ends up unable to say what it did.
    """
    if not events:
        raise ModelledDelayError(
            "impacted as-planned with no events models nothing. That is not an empty "
            "result, it is a missing input"
        )
    _check(tasks, events)
    default_calendar = next(iter(calendars or {}), tasks[0].calendar_id if tasks else "STD")

    calendar = _project_calendar(calendars)
    base = schedule_network(tasks, links, calendars, data_date=data_date, options=options)

    per_event: list[EventImpact] = []
    for event in events:
        one_tasks, one_links = _impose(tasks, links, [event], default_calendar)
        alone = schedule_network(
            one_tasks, one_links, calendars, data_date=data_date, options=options
        )
        per_event.append(
            EventImpact(
                event=event,
                finish_without=base.project_finish,
                finish_with=alone.project_finish,
                days=_moved(calendar, base.project_finish, alone.project_finish),
            )
        )

    all_tasks, all_links = _impose(tasks, links, events, default_calendar)
    together = schedule_network(
        all_tasks, all_links, calendars, data_date=data_date, options=options
    )

    notes = []
    if any(impact.days == 0 for impact in per_event):
        absorbed = [i.event.id for i in per_event if i.days == 0]
        notes.append(
            f"{len(absorbed)} event(s) moved the finish by nothing on their own "
            f"({absorbed}): they were not on the driving path and their delay was "
            "absorbed by float"
        )
    return ModelledResult(
        method="impacted as-planned",
        mip="AACE 29R-03 MIP 3.6 - modelled, additive, single base",
        unimpacted_finish=base.project_finish,
        impacted_finish=together.project_finish,
        per_event=tuple(per_event),
        events=tuple(events),
        total_days=_moved(calendar, base.project_finish, together.project_finish),
        outcome=together,
        notes=tuple(notes),
    )


def collapsed_as_built(
    tasks: Sequence[Task],
    links: Sequence[Link],
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    events: Sequence[DelayEvent],
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> ModelledResult:
    """**AACE 29R-03 MIP 3.9** -- modelled, subtractive.

    The network passed in is the **as-built**, with the delay events already in
    it as activities. They are removed and the remainder rescheduled: the
    "but-for" programme.

    Actual dates are stripped from the collapse, and that is not a detail. An
    as-built activity carries the date it really happened, and the whole point
    of removing a delay is to ask when the work *would* have happened instead.
    Leaving the actuals in pins every activity exactly where it was and the
    collapsed network reports no change at all -- a nil result that looks like
    a finding.
    """
    if not events:
        raise ModelledDelayError(
            "collapsed as-built with no events removes nothing. That is a missing input"
        )
    present = {t.id for t in tasks}
    missing = [e.id for e in events if e.activity_id not in present and e.id not in present]
    if missing:
        raise ModelledDelayError(
            f"these events are not in the as-built network: {missing}. Collapsed as-built "
            "removes activities that are there; use impacted as-planned to add ones that "
            "are not"
        )

    def _remove(chosen: Sequence[DelayEvent]) -> ScheduleOutcome:
        drop = {e.activity_id for e in chosen} | {e.id for e in chosen}
        kept = [
            replace(t, actual_start=None, actual_finish=None) for t in tasks if t.id not in drop
        ]
        kept_ids = {t.id for t in kept}
        kept_links = [
            link for link in links if link.predecessor in kept_ids and link.successor in kept_ids
        ]
        return schedule_network(kept, kept_links, calendars, data_date=data_date, options=options)

    as_built = schedule_network(
        [replace(t, actual_start=None, actual_finish=None) for t in tasks],
        links,
        calendars,
        data_date=data_date,
        options=options,
    )

    calendar = _project_calendar(calendars)
    per_event = [
        EventImpact(
            event=event,
            # Read in the direction the additive method reports: "with" is the
            # programme containing the event, "without" is the collapse. Both
            # methods then use one sign convention and a report can put their
            # numbers side by side.
            finish_without=_remove([event]).project_finish,
            finish_with=as_built.project_finish,
            days=_moved(calendar, _remove([event]).project_finish, as_built.project_finish),
        )
        for event in events
    ]
    together = _remove(events)

    return ModelledResult(
        method="collapsed as-built",
        mip="AACE 29R-03 MIP 3.9 - modelled, subtractive",
        unimpacted_finish=together.project_finish,
        impacted_finish=as_built.project_finish,
        per_event=tuple(per_event),
        events=tuple(events),
        total_days=_moved(calendar, together.project_finish, as_built.project_finish),
        outcome=together,
        notes=(
            "actual dates were stripped before collapsing: an as-built activity pinned to "
            "the date it really happened cannot move, and the collapse would report no "
            "change however much was removed",
        ),
    )


__all__ = [
    "EVENT_PREFIX",
    "DelayEvent",
    "EventImpact",
    "ModelledDelayError",
    "ModelledResult",
    "collapsed_as_built",
    "impacted_as_planned",
]
