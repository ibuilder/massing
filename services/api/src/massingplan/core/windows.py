"""Contemporaneous windows analysis: where the time actually went, window by window.

`compare` answers "what moved between these two schedules". That is the right
question for a re-baseline and the wrong one for a claim, because a project
that finished eighty days late did not do it in one step. It did it in eleven
monthly updates, and the answer a tribunal wants is *which* of those eleven,
and what was driving at the time.

This is **AACE 29R-03 MIP 3.3** -- observational, dynamic, contemporaneous
as-is -- the method that reads the project's own updates and quantifies the
loss or gain along the driving path between consecutive data dates. The SCL
Delay and Disruption Protocol calls the same family a time-slice windows
analysis, and both documents make the same point about it: it is preferred
*when the contemporaneous updates exist*, because it uses the critical path the
project actually had at the time rather than one reconstructed afterwards by
somebody who knows how the story ends.

Observational, and that is the whole discipline
-----------------------------------------------
Nothing here inserts, removes or reshapes a delay event. It observes what the
updates already say. The modelled methods -- 3.6 through 3.9, impacted
as-planned and collapsed as-built -- do change the network, and they are a
separate exercise with separate assumptions; conflating the two is how an
analysis acquires a conclusion its inputs do not support. If this module ever
grows a `what_if`, it belongs in a different one.

The invariant
-------------
**The windows sum to the whole.** Total movement from the first update's finish
to the last equals the sum of the per-window movements, exactly, always. An
analysis whose parts do not sum to the whole is an opinion with numbers
attached -- `compare` says the same thing about its attribution, and this is
that rule applied one level up.

It is not a tautology. Windows are consecutive so the sum telescopes *provided
every window is measured between the same pair of schedules the next one starts
from*, and provided the finish each window is measured against is the one the
update actually reported. Skip an update, reorder two, or measure the last
window against the baseline instead of its predecessor, and it stops holding.
Those are the mistakes this module exists to make impossible.

What a window reports
---------------------
The finish movement, the driving path *at the time* -- both ends of it, since a
path that changes mid-window is itself the finding -- and `compare`'s
attribution for that window. Critical path changes between windows are surfaced
rather than smoothed: a path that switches in window 6 is the fact the whole
claim usually turns on.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from .compare import Comparison, MatchKey, compare
from .issues import IssueLog
from .network import Link, Task


class WindowsError(ValueError):
    """The updates cannot support a windows analysis. Refused, not approximated."""


@dataclass(frozen=True)
class Update:
    """One contemporaneous schedule update: the project as it stood on a date.

    `data_date` is the update's own data date, not the day somebody exported
    it. Windows are the intervals between these, so a wrong one silently moves
    a delay into the neighbouring window -- and the neighbouring window is very
    often the other party's.
    """

    data_date: date
    outcome: object
    tasks: Sequence[Task]
    links: Sequence[Link] = ()
    name: str = ""

    @property
    def label(self) -> str:
        return self.name or self.data_date.isoformat()


@dataclass(frozen=True)
class Window:
    """One interval between consecutive data dates, and what happened in it."""

    index: int
    opened: date
    closed: date
    opening_finish: date
    closing_finish: date
    comparison: Comparison

    @property
    def slip_days(self) -> int:
        """Calendar days the projected finish moved in this window.

        Signed. A window that pulled time back is negative, and it is reported
        as a negative rather than dropped -- acceleration is as much a fact as
        delay, and a claim that counts only the slips overstates itself.
        """
        return (self.closing_finish - self.opening_finish).days

    @property
    def driving_path_changed(self) -> bool:
        return self.comparison.driving_path.baseline_path != (
            self.comparison.driving_path.current_path
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "opened": self.opened.isoformat(),
            "closed": self.closed.isoformat(),
            "opening_finish": self.opening_finish.isoformat(),
            "closing_finish": self.closing_finish.isoformat(),
            "slip_days": self.slip_days,
            "driving_path_changed": self.driving_path_changed,
            "driving_path": list(self.comparison.driving_path.current_path),
            "attribution": [c.to_dict() for c in self.comparison.driving_path.attribution],
        }


@dataclass(frozen=True)
class WindowsAnalysis:
    """The whole series, and the arithmetic that has to hold across it."""

    windows: tuple[Window, ...]
    first_finish: date
    last_finish: date
    issues: IssueLog = field(default_factory=IssueLog)
    method: str = "AACE 29R-03 MIP 3.3 — observational, dynamic, contemporaneous as-is"

    @property
    def total_slip_days(self) -> int:
        return (self.last_finish - self.first_finish).days

    @property
    def windows_sum(self) -> bool:
        """The invariant, re-checked on the way out rather than trusted."""
        return sum(w.slip_days for w in self.windows) == self.total_slip_days

    @property
    def worst(self) -> Window | None:
        """The window that lost the most time. Ties break on the earlier one.

        The earlier window wins deliberately: when two periods slipped equally,
        the one that happened first is the one whose cause was available to be
        managed, and it is where an investigation starts.
        """
        candidates = [w for w in self.windows if w.slip_days > 0]
        if not candidates:
            return None
        return min(candidates, key=lambda w: (-w.slip_days, w.index))

    def by_cause(self) -> dict[str, int]:
        """Days attributed to each cause across every window.

        These sum to the total slip for the same reason the windows do, and the
        residual causes -- ``PATH_SWITCH`` and ``UNEXPLAINED`` -- are in here
        with the rest. Reporting only the causes that flatter the analysis is
        the thing the sum exists to prevent.
        """
        totals: dict[str, int] = {}
        for window in self.windows:
            for contribution in window.comparison.driving_path.attribution:
                key = contribution.cause.value
                totals[key] = totals.get(key, 0) + contribution.days
        return totals

    def summary(self) -> dict[str, object]:
        worst = self.worst
        return {
            "method": self.method,
            "window_count": len(self.windows),
            "first_finish": self.first_finish.isoformat(),
            "last_finish": self.last_finish.isoformat(),
            "total_slip_days": self.total_slip_days,
            "windows_sum": self.windows_sum,
            "worst_window": None if worst is None else worst.index,
            "worst_window_slip_days": None if worst is None else worst.slip_days,
            "path_changes": sum(1 for w in self.windows if w.driving_path_changed),
            "by_cause": self.by_cause(),
            "issue_count": len(self.issues.entries),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.summary(),
            "windows": [w.to_dict() for w in self.windows],
            "issues": [i.to_dict() for i in self.issues.entries],
        }


def analyse(
    updates: Sequence[Update],
    *,
    match: MatchKey = MatchKey.ID,
) -> WindowsAnalysis:
    """Run a contemporaneous windows analysis across an ordered series of updates.

    Refuses rather than approximates. Two updates sharing a data date have no
    window between them to measure; updates out of order would attribute a
    delay to the period after it was recovered. Both are input errors a claim
    cannot survive, and neither is something to guess through -- so they raise
    instead of being sorted or deduplicated silently.
    """
    if len(updates) < 2:
        raise WindowsError(
            f"a windows analysis needs at least two updates to have a window, got {len(updates)}"
        )

    for earlier, later in itertools.pairwise(updates):
        if later.data_date == earlier.data_date:
            raise WindowsError(
                f"two updates share the data date {earlier.data_date.isoformat()}; "
                "there is no window between them to measure"
            )
        if later.data_date < earlier.data_date:
            raise WindowsError(
                f"updates run backwards: {earlier.data_date.isoformat()} is followed by "
                f"{later.data_date.isoformat()}. Sorting them here would move a delay into "
                "a window it did not happen in"
            )

    issues = IssueLog()
    windows: list[Window] = []

    for index, (earlier, later) in enumerate(itertools.pairwise(updates)):
        # Each window is measured against its own predecessor, never against the
        # first update. Measuring everything against the baseline is a different
        # method -- and one whose parts do not sum to the whole.
        comparison = compare(
            earlier.outcome,
            later.outcome,
            baseline_network=(earlier.tasks, earlier.links),
            current_network=(later.tasks, later.links),
            match=match,
        )
        window = Window(
            index=index,
            opened=earlier.data_date,
            closed=later.data_date,
            opening_finish=comparison.baseline_finish,
            closing_finish=comparison.current_finish,
            comparison=comparison,
        )
        windows.append(window)

        if not comparison.driving_path.attribution_sums:  # pragma: no cover - compare guarantees it
            issues.warn(
                "WINDOWS.ATTRIBUTION_DOES_NOT_SUM",
                f"window {index} ({earlier.label} to {later.label}) attributes "
                f"{sum(c.days for c in comparison.driving_path.attribution)} days to a "
                f"{window.slip_days}-day movement",
                "the window's causes do not account for its movement",
                row_key=str(index),
            )
        if comparison.ambiguous_matches:
            issues.warn(
                "WINDOWS.AMBIGUOUS_MATCH",
                f"window {index}: {len(comparison.ambiguous_matches)} activities could not be "
                f"paired unambiguously, e.g. {list(comparison.ambiguous_matches[:3])}",
                "an unmatched activity is invisible to the analysis; match on CODE or WBS "
                "if the updates were re-baselined from P6",
                row_key=str(index),
            )

    first_finish = windows[0].opening_finish
    last_finish = windows[-1].closing_finish
    analysis = WindowsAnalysis(
        windows=tuple(windows),
        first_finish=first_finish,
        last_finish=last_finish,
        issues=issues,
    )

    if not analysis.windows_sum:  # pragma: no cover - telescoping makes this unreachable
        issues.error(
            "WINDOWS.DO_NOT_SUM",
            f"the windows total {sum(w.slip_days for w in windows)} days against an overall "
            f"movement of {analysis.total_slip_days}",
            "the series has a gap: a window is not measured against the schedule the next "
            "one starts from",
        )
    return analysis


__all__ = [
    "Update",
    "Window",
    "WindowsAnalysis",
    "WindowsError",
    "analyse",
]
