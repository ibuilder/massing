"""Schedule compression: what finishing earlier would take, and cost.

Levelling answers "when can this be built with the crews I have". Nothing here
answered "what would it take to finish three weeks earlier", which is the
question asked on every programme that is late -- usually in a meeting, usually
with somebody guessing.

Two levers, and only two that are honest
----------------------------------------
**Crashing** shortens a driving activity by spending money on it: more crews,
more shifts, more plant. Its cost is the activity's own cost slope -- pounds
per day saved -- and it buys days only while the activity stays on the driving
path. The fourth day bought on an activity with three days of advantage over
the next path buys nothing, and this module stops rather than selling it.

**Fast-tracking** overlaps two activities that were sequential: a Finish-Start
link becomes Start-Start with a lag. It costs nothing in money and it buys the
overlap in **risk** -- the successor starts on information the predecessor has
not finished producing, so rework becomes possible in a way it was not before.
That risk is not a number this engine can compute, so it is not invented; the
option states what was overlapped and by how much, and the planner prices it.

Options, never applied
----------------------
Nothing here changes a schedule. Every function returns *options with a
consequence attached*, because compression is a commercial decision and a tool
that quietly shortened durations would be making it. `apply` exists and takes
an explicit list of the options the caller chose -- it is the caller's
signature on the decision, not the module's.

Determinism
-----------
A compression plan that differs each time it is asked for cannot be taken to a
client, so the answer is identical under any hash seed -- asserted by a test
that runs it in three subprocesses and compares.

What provides that is the **construction order**: candidates are built by
walking the crash costs sorted on `(cost_per_day, activity_id)` and the
fast-trackable pairs sorted outright, and Python's sort is stable, so equal
prices keep that order. The `(price, key)` tie-break in the final sort is belt
to those braces and nothing more -- removing it leaves every test green, which
was measured rather than assumed. The earlier version of this paragraph
claimed the tie-break was what made the module deterministic; it is not, and a
comment asserting a guarantee the code does not provide is the kind of thing
this codebase has spent a lot of effort removing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from .network import Link, RelationType, SchedulerOptions, Task
from .schedule import ScheduleOutcome, schedule_network
from .timeaxis import WorkCalendar


class CompressionError(ValueError):
    """The compression cannot be described as asked."""


@dataclass(frozen=True)
class CrashCost:
    """What one activity costs to shorten, and how far it can go.

    `max_days` is a fact about the work -- a pour cures in the time it cures,
    whatever it costs -- and it is required rather than defaulted, because a
    default of "as far as you like" produces a plan that finishes on any date
    somebody asks for.
    """

    activity_id: str
    cost_per_day: float
    max_days: int

    def __post_init__(self) -> None:
        if self.cost_per_day < 0:
            raise CompressionError(
                f"{self.activity_id}: a negative cost per day would mean the schedule "
                "pays you to shorten it"
            )
        if self.max_days < 0:
            raise CompressionError(f"{self.activity_id}: max_days cannot be negative")


@dataclass(frozen=True)
class CrashOption:
    """Shorten one activity by one day, and what that day is worth."""

    activity_id: str
    days: int
    cost: float
    finish_before: date
    finish_after: date

    @property
    def days_saved(self) -> int:
        """Calendar days the *project* finish moved, which is what was bought.

        Not the days taken off the activity. Shortening a driving activity by
        five days when it is only three days ahead of the next path buys three;
        the other two are spent and gone, and reporting them as saved is how a
        compression plan overruns.
        """
        return (self.finish_before - self.finish_after).days

    @property
    def cost_per_day_saved(self) -> float | None:
        return None if self.days_saved <= 0 else self.cost / self.days_saved

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "crash",
            "activity_id": self.activity_id,
            "days_shortened": self.days,
            "cost": round(self.cost, 2),
            "days_saved": self.days_saved,
            "cost_per_day_saved": (
                None if self.cost_per_day_saved is None else round(self.cost_per_day_saved, 2)
            ),
            "finish_before": self.finish_before.isoformat(),
            "finish_after": self.finish_after.isoformat(),
        }


@dataclass(frozen=True)
class FastTrackOption:
    """Overlap two activities that were sequential.

    `risk` is prose, not a number. The engine can say what was overlapped and
    by how much; what that is worth depends on how much of the predecessor's
    output the successor actually needs, which is a judgement about the work.
    Producing a score here would be inventing a number that reads as measured.
    """

    predecessor_id: str
    successor_id: str
    overlap_days: int
    finish_before: date
    finish_after: date
    risk: str

    @property
    def days_saved(self) -> int:
        return (self.finish_before - self.finish_after).days

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "fast_track",
            "predecessor_id": self.predecessor_id,
            "successor_id": self.successor_id,
            "overlap_days": self.overlap_days,
            "days_saved": self.days_saved,
            "cost": 0.0,
            "risk": self.risk,
            "finish_before": self.finish_before.isoformat(),
            "finish_after": self.finish_after.isoformat(),
        }


#: The two levers, as one type. `object` was standing in for this and cost the
#: type checker every attribute on both.
CompressionOption = CrashOption | FastTrackOption


@dataclass(frozen=True)
class CompressionPlan:
    """Everything that could be done, cheapest useful day first."""

    target_days: int
    finish_before: date
    best_finish: date
    options: tuple[CompressionOption, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def days_available(self) -> int:
        return (self.finish_before - self.best_finish).days

    @property
    def total_cost(self) -> float:
        return sum(o.cost if isinstance(o, CrashOption) else 0.0 for o in self.options)

    @property
    def meets_target(self) -> bool:
        return self.days_available >= self.target_days

    def to_dict(self) -> dict[str, object]:
        return {
            "target_days": self.target_days,
            "finish_before": self.finish_before.isoformat(),
            "best_finish": self.best_finish.isoformat(),
            "days_available": self.days_available,
            "meets_target": self.meets_target,
            "total_cost": round(self.total_cost, 2),
            "options": [o.to_dict() for o in self.options],
            "notes": list(self.notes),
        }


def _finish(
    tasks: Sequence[Task],
    links: Sequence[Link],
    calendars: Mapping[str, WorkCalendar] | None,
    data_date: date | None,
    options: SchedulerOptions | None,
) -> ScheduleOutcome:
    return schedule_network(tasks, links, calendars, data_date=data_date, options=options)


def plan(
    tasks: Sequence[Task],
    links: Sequence[Link],
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    target_days: int,
    costs: Sequence[CrashCost] = (),
    fast_trackable: Sequence[tuple[str, str]] = (),
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> CompressionPlan:
    """Options for finishing ``target_days`` earlier, cheapest useful day first.

    Greedy, one day at a time, rescheduling after each: the driving path moves
    as it is compressed, and an algorithm that picks its whole shopping list
    from the *original* critical path keeps spending on an activity that
    stopped driving three days ago. That is the classic way a crash plan comes
    in over budget and short of the date.

    Returns what it found even when it cannot reach the target. A plan that
    gets eight days of the ten asked for is the answer to the question; raising
    instead would leave the caller to discover the eight by bisection.
    """
    if target_days < 0:
        raise CompressionError("a negative target would be asking to finish later")

    by_id = {t.id: t for t in tasks}
    cost_of = {c.activity_id: c for c in costs}
    for activity_id in cost_of:
        if activity_id not in by_id:
            raise CompressionError(
                f"a crash cost names {activity_id!r}, which is not in this network"
            )
    link_index = {(link.predecessor, link.successor): link for link in links}
    for pair in fast_trackable:
        if pair not in link_index:
            raise CompressionError(
                f"{pair[0]} -> {pair[1]} is offered for fast-tracking but there is no link "
                "between them. Overlapping two activities that are not sequential is not "
                "compression, it is a change to the logic"
            )
        if link_index[pair].type is not RelationType.FS:
            raise CompressionError(
                f"{pair[0]} -> {pair[1]} is {link_index[pair].type.value}, not Finish-Start. "
                "Only a sequential pair can be overlapped"
            )

    current_tasks = list(tasks)
    current_links = list(links)
    base = _finish(current_tasks, current_links, calendars, data_date, options)
    start_finish = base.project_finish

    chosen: list[CompressionOption] = []
    notes: list[str] = []
    spent: dict[str, int] = {}
    overlapped: dict[tuple[str, str], int] = {}

    while (start_finish - base.project_finish).days < target_days:
        candidates: list[tuple[float, str, CompressionOption, list[Task], list[Link]]] = []

        # -- crash one day off each activity that still has room -------------
        for cost in sorted(cost_of.values(), key=lambda c: (c.cost_per_day, c.activity_id)):
            used = spent.get(cost.activity_id, 0)
            if used >= cost.max_days:
                continue
            task = by_id[cost.activity_id]
            trial = [
                replace(t, duration_days=t.duration_days - 1) if t.id == cost.activity_id else t
                for t in current_tasks
            ]
            if any(t.id == cost.activity_id and t.duration_days < 1 for t in trial):
                continue
            outcome = _finish(trial, current_links, calendars, data_date, options)
            saved = (base.project_finish - outcome.project_finish).days
            if saved <= 0:
                # It is not driving. Spending here buys nothing, and a plan that
                # sells it is selling a day that does not exist.
                continue
            candidates.append(
                (
                    cost.cost_per_day / saved,
                    cost.activity_id,
                    CrashOption(
                        activity_id=cost.activity_id,
                        days=used + 1,
                        cost=cost.cost_per_day,
                        finish_before=base.project_finish,
                        finish_after=outcome.project_finish,
                    ),
                    trial,
                    list(current_links),
                )
            )
            del task

        # -- overlap one more day on each offered pair -----------------------
        for pair in sorted(fast_trackable):
            predecessor, successor = pair
            used = overlapped.get(pair, 0)
            room = by_id[predecessor].duration_days - 1
            if used >= room:
                continue
            trial_links = [
                Link(
                    predecessor,
                    successor,
                    RelationType.SS,
                    by_id[predecessor].duration_days - (used + 1),
                )
                if (link.predecessor, link.successor) == pair
                else link
                for link in current_links
            ]
            outcome = _finish(current_tasks, trial_links, calendars, data_date, options)
            saved = (base.project_finish - outcome.project_finish).days
            if saved <= 0:
                continue
            candidates.append(
                (
                    0.0,  # free in money; the price is in the risk line
                    f"{predecessor}->{successor}",
                    FastTrackOption(
                        predecessor_id=predecessor,
                        successor_id=successor,
                        overlap_days=used + 1,
                        finish_before=base.project_finish,
                        finish_after=outcome.project_finish,
                        risk=(
                            f"{successor} starts {used + 1} working day(s) before {predecessor} "
                            f"finishes, so it begins on information {predecessor} has not "
                            "finished producing. Rework becomes possible where it was not"
                        ),
                    ),
                    list(current_tasks),
                    trial_links,
                )
            )

        if not candidates:
            notes.append(
                f"ran out of compression after {(start_finish - base.project_finish).days} "
                f"of the {target_days} days asked for: every remaining lever is either "
                "exhausted or no longer on the driving path"
            )
            break

        # Cheapest per day actually saved; ties on the id so the answer does not
        # depend on hash order.
        candidates.sort(key=lambda c: (c[0], c[1]))
        _price, _key, option, next_tasks, next_links = candidates[0]
        chosen.append(option)
        current_tasks, current_links = next_tasks, next_links
        base = _finish(current_tasks, current_links, calendars, data_date, options)
        if isinstance(option, CrashOption):
            spent[option.activity_id] = option.days
        else:
            overlapped[(option.predecessor_id, option.successor_id)] = option.overlap_days

    return CompressionPlan(
        target_days=target_days,
        finish_before=start_finish,
        best_finish=base.project_finish,
        options=tuple(chosen),
        notes=tuple(notes),
    )


def apply(
    tasks: Sequence[Task],
    links: Sequence[Link],
    chosen: Sequence[CompressionOption],
) -> tuple[list[Task], list[Link]]:
    """The network with the chosen options applied. **The caller's decision.**

    Separate from `plan` on purpose, and taking the options explicitly rather
    than a plan object: compression costs money and creates risk, and a module
    that returned a compressed schedule from the same call that evaluated it
    would be making a commercial choice on somebody's behalf.
    """
    # `days` and `overlap_days` are **cumulative**, not per-step: buying three
    # days off A produces options reading 1, 2 and 3, because "A shortened by
    # three days" is what a reader needs and "the third day cost £100" is what
    # a price list needs. Applying them by subtraction sums to six.
    #
    # So the final state is the maximum, not the total. This was caught by the
    # test asserting the applied network finishes where the plan said it would
    # -- which is the only assertion that can catch it, since the compressed
    # schedule is perfectly valid, just three days shorter than anybody agreed.
    crash_to: dict[str, int] = {}
    overlap_to: dict[tuple[str, str], int] = {}
    for option in chosen:
        if isinstance(option, CrashOption):
            crash_to[option.activity_id] = max(crash_to.get(option.activity_id, 0), option.days)
        elif isinstance(option, FastTrackOption):
            key = (option.predecessor_id, option.successor_id)
            overlap_to[key] = max(overlap_to.get(key, 0), option.overlap_days)
        else:  # pragma: no cover - defensive
            raise CompressionError(f"not a compression option: {option!r}")

    out_tasks = [
        replace(t, duration_days=t.duration_days - crash_to[t.id]) if t.id in crash_to else t
        for t in tasks
    ]
    by_id = {t.id: t for t in tasks}
    out_links = [
        Link(
            link.predecessor,
            link.successor,
            RelationType.SS,
            by_id[link.predecessor].duration_days - overlap_to[(link.predecessor, link.successor)],
        )
        if (link.predecessor, link.successor) in overlap_to
        else link
        for link in links
    ]
    return out_tasks, out_links


__all__ = [
    "CompressionError",
    "CompressionOption",
    "CompressionPlan",
    "CrashCost",
    "CrashOption",
    "FastTrackOption",
    "apply",
    "plan",
]
