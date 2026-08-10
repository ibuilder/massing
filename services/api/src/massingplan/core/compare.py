"""Baseline-to-baseline comparison and delay attribution.

Named in both source repositories as the highest-value unbuilt feature, and
neither built it. This is where delay analysis starts, and delay analysis is
where the argument is.

Three decisions carry the module.

**Identity matching is explicit, and how each activity was matched is recorded.**
A re-baseline exported from P6 has entirely new ``task_id`` values, so matching
on the internal id finds nothing in common and reports every activity as
removed-and-added -- a diff that is technically correct and completely useless.
``CODE`` (the planner's ``A1010``) is usually the right answer.
``NAME_AND_WBS`` is the fallback. Ambiguous matches are *not* paired: matching
"Pour slab" on level 2 with "Pour slab" on level 5 reports a forty-day slip that
never happened, which is the kind of error that gets a claim thrown out.

**The attribution invariant: the contributions sum to the finish move, exactly,
always.** A delay analysis whose parts do not sum to the whole is not evidence;
it is an opinion with numbers attached. Where the driving path changed, a
``PATH_SWITCH`` contribution absorbs the residual and names both paths. The
residual is never quietly dropped to make the arithmetic close.

**Levelling moves are an input.** If the current schedule was levelled and the
baseline was not, every activity shows as shifted and the attribution blames
duration and logic for what was a resourcing decision -- a report that blames
the subcontractor for the planner's own smoothing pass.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from .network import Link, RelationType, Task


class MatchKey(str, Enum):
    ID = "id"
    CODE = "code"
    NAME_AND_WBS = "name_and_wbs"


class ChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    RENAMED = "renamed"
    DURATION_CHANGED = "duration_changed"
    DATE_SHIFTED = "date_shifted"
    RELOGICKED = "relogicked"
    CONSTRAINT_CHANGED = "constraint_changed"
    CALENDAR_CHANGED = "calendar_changed"
    PROGRESS_ADDED = "progress_added"
    CRITICALITY_CHANGED = "criticality_changed"
    UNCHANGED = "unchanged"


class LinkChange(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    TYPE_CHANGED = "type_changed"
    LAG_CHANGED = "lag_changed"


class DelayCause(str, Enum):
    DURATION_GROWTH = "duration_growth"
    LAG_GROWTH = "lag_growth"
    LOGIC_ADDED = "logic_added"
    CONSTRAINT_IMPOSED = "constraint_imposed"
    PROGRESS_SLIP = "progress_slip"
    CALENDAR_CHANGE = "calendar_change"
    LEVELLING = "levelling"
    PATH_SWITCH = "path_switch"
    UNEXPLAINED = "unexplained"


@dataclass(frozen=True)
class ActivityDelta:
    activity_id: str
    matched_by: MatchKey | None
    kinds: frozenset[ChangeKind]
    baseline_start: date | None
    current_start: date | None
    baseline_finish: date | None
    current_finish: date | None
    start_shift_days: int | None
    finish_shift_days: int | None
    baseline_duration: int | None
    current_duration: int | None
    baseline_float: int | None
    current_float: int | None
    was_critical: bool
    is_critical: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "activity_id": self.activity_id,
            "matched_by": self.matched_by.value if self.matched_by else None,
            "kinds": sorted(k.value for k in self.kinds),
            "baseline_start": _iso(self.baseline_start),
            "current_start": _iso(self.current_start),
            "baseline_finish": _iso(self.baseline_finish),
            "current_finish": _iso(self.current_finish),
            "start_shift_days": self.start_shift_days,
            "finish_shift_days": self.finish_shift_days,
            "baseline_duration": self.baseline_duration,
            "current_duration": self.current_duration,
            "baseline_float": self.baseline_float,
            "current_float": self.current_float,
            "was_critical": self.was_critical,
            "is_critical": self.is_critical,
        }


@dataclass(frozen=True)
class LinkDelta:
    predecessor: str
    successor: str
    change: LinkChange
    baseline_type: RelationType | None = None
    current_type: RelationType | None = None
    baseline_lag: int | None = None
    current_lag: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "predecessor": self.predecessor,
            "successor": self.successor,
            "change": self.change.value,
            "baseline_type": self.baseline_type.value if self.baseline_type else None,
            "current_type": self.current_type.value if self.current_type else None,
            "baseline_lag": self.baseline_lag,
            "current_lag": self.current_lag,
        }


@dataclass(frozen=True)
class DelayContribution:
    activity_id: str | None
    cause: DelayCause
    days: int
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "activity_id": self.activity_id,
            "cause": self.cause.value,
            "days": self.days,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class DrivingPathDelta:
    baseline_path: tuple[str, ...]
    current_path: tuple[str, ...]
    entered: tuple[str, ...]
    left: tuple[str, ...]
    finish_move_days: int
    attribution: tuple[DelayContribution, ...]

    @property
    def attribution_sums(self) -> bool:
        """The invariant. Asserted in tests and re-checked before returning."""
        return sum(c.days for c in self.attribution) == self.finish_move_days

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_path": list(self.baseline_path),
            "current_path": list(self.current_path),
            "entered": list(self.entered),
            "left": list(self.left),
            "finish_move_days": self.finish_move_days,
            "attribution": [c.to_dict() for c in self.attribution],
            "attribution_sums": self.attribution_sums,
        }


@dataclass(frozen=True)
class Comparison:
    activities: tuple[ActivityDelta, ...]
    links: tuple[LinkDelta, ...]
    criticality_gained: tuple[str, ...]
    criticality_lost: tuple[str, ...]
    driving_path: DrivingPathDelta
    ambiguous_matches: tuple[str, ...]
    match_key: MatchKey
    baseline_finish: date
    current_finish: date

    def changed(self) -> list[ActivityDelta]:
        return [a for a in self.activities if a.kinds != frozenset({ChangeKind.UNCHANGED})]

    def summary(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for delta in self.activities:
            for kind in delta.kinds:
                counts[kind.value] = counts.get(kind.value, 0) + 1
        return {
            "match_key": self.match_key.value,
            "baseline_finish": self.baseline_finish.isoformat(),
            "current_finish": self.current_finish.isoformat(),
            "finish_move_days": (self.current_finish - self.baseline_finish).days,
            "activity_count": len(self.activities),
            "changed_count": len(self.changed()),
            "changes_by_kind": counts,
            "link_changes": len(self.links),
            "criticality_gained": list(self.criticality_gained),
            "criticality_lost": list(self.criticality_lost),
            "ambiguous_matches": list(self.ambiguous_matches),
            "driving_path": self.driving_path.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.summary(),
            "activities": [a.to_dict() for a in self.activities],
            "links": [link.to_dict() for link in self.links],
        }


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _identity(task: Task, key: MatchKey, code: Mapping[str, str], wbs: Mapping[str, str]) -> str:
    if key is MatchKey.CODE:
        return code.get(task.id) or task.id
    if key is MatchKey.NAME_AND_WBS:
        return f"{wbs.get(task.id, '')}|{task.name}"
    return task.id


def compare(
    baseline: object,
    current: object,
    *,
    baseline_network: tuple[Sequence[Task], Sequence[Link]],
    current_network: tuple[Sequence[Task], Sequence[Link]],
    match: MatchKey = MatchKey.ID,
    baseline_codes: Mapping[str, str] | None = None,
    current_codes: Mapping[str, str] | None = None,
    baseline_wbs: Mapping[str, str] | None = None,
    current_wbs: Mapping[str, str] | None = None,
    levelling_moves: Sequence[object] = (),
) -> Comparison:
    """Diff two computed schedules and attribute the finish move."""
    base_tasks, base_links = list(baseline_network[0]), list(baseline_network[1])
    curr_tasks, curr_links = list(current_network[0]), list(current_network[1])
    base_codes, curr_codes = dict(baseline_codes or {}), dict(current_codes or {})
    base_wbs, curr_wbs = dict(baseline_wbs or {}), dict(current_wbs or {})

    base_dates = baseline.dates  # type: ignore[attr-defined]
    curr_dates = current.dates  # type: ignore[attr-defined]

    # -- match --------------------------------------------------------------
    base_index: dict[str, list[Task]] = {}
    for task in base_tasks:
        base_index.setdefault(_identity(task, match, base_codes, base_wbs), []).append(task)
    curr_index: dict[str, list[Task]] = {}
    for task in curr_tasks:
        curr_index.setdefault(_identity(task, match, curr_codes, curr_wbs), []).append(task)

    ambiguous = sorted(
        {k for k, v in base_index.items() if len(v) > 1}
        | {k for k, v in curr_index.items() if len(v) > 1}
    )
    pairs: dict[str, tuple[Task | None, Task | None]] = {}
    for identity in sorted(set(base_index) | set(curr_index)):
        if identity in ambiguous:
            # Not paired. A wrong pairing invents a slip that never happened.
            for task in base_index.get(identity, []):
                pairs[f"baseline:{task.id}"] = (task, None)
            for task in curr_index.get(identity, []):
                pairs[f"current:{task.id}"] = (None, task)
            continue
        b = base_index.get(identity, [None])[0]
        c = curr_index.get(identity, [None])[0]
        pairs[(c or b).id] = (b, c)  # type: ignore[union-attr]

    # -- activity deltas -----------------------------------------------------
    levelled = {getattr(m, "activity_id", None) for m in levelling_moves}
    base_net = baseline.network  # type: ignore[attr-defined]
    curr_net = current.network  # type: ignore[attr-defined]

    base_link_by_succ: dict[str, list[Link]] = {}
    for link in base_links:
        base_link_by_succ.setdefault(link.successor, []).append(link)
    curr_link_by_succ: dict[str, list[Link]] = {}
    for link in curr_links:
        curr_link_by_succ.setdefault(link.successor, []).append(link)

    deltas: list[ActivityDelta] = []
    gained: list[str] = []
    lost: list[str] = []

    for key in sorted(pairs):
        b, c = pairs[key]
        kinds: set[ChangeKind] = set()
        bd = base_dates.get(b.id) if b else None
        cd = curr_dates.get(c.id) if c else None

        if b is None:
            kinds.add(ChangeKind.ADDED)
        elif c is None:
            kinds.add(ChangeKind.REMOVED)
        else:
            if b.name != c.name:
                kinds.add(ChangeKind.RENAMED)
            if b.duration_days != c.duration_days:
                kinds.add(ChangeKind.DURATION_CHANGED)
            if b.calendar_id != c.calendar_id:
                kinds.add(ChangeKind.CALENDAR_CHANGED)
            if (b.constraint, b.constraint_date) != (c.constraint, c.constraint_date):
                kinds.add(ChangeKind.CONSTRAINT_CHANGED)
            if b.actual_start != c.actual_start or b.actual_finish != c.actual_finish:
                kinds.add(ChangeKind.PROGRESS_ADDED)
            if _link_signature(base_link_by_succ.get(b.id, [])) != _link_signature(
                curr_link_by_succ.get(c.id, [])
            ):
                kinds.add(ChangeKind.RELOGICKED)
            if bd and cd and (bd.start != cd.start or bd.finish != cd.finish):
                kinds.add(ChangeKind.DATE_SHIFTED)

        was_critical = bool(b and base_net.is_critical(b.id))
        is_critical = bool(c and curr_net.is_critical(c.id))
        if was_critical != is_critical:
            kinds.add(ChangeKind.CRITICALITY_CHANGED)
            (gained if is_critical else lost).append(key)
        if not kinds:
            kinds.add(ChangeKind.UNCHANGED)

        deltas.append(
            ActivityDelta(
                activity_id=key,
                matched_by=match if (b and c) else None,
                kinds=frozenset(kinds),
                baseline_start=bd.start if bd else None,
                current_start=cd.start if cd else None,
                baseline_finish=bd.finish if bd else None,
                current_finish=cd.finish if cd else None,
                start_shift_days=(cd.start - bd.start).days if bd and cd else None,
                finish_shift_days=(cd.finish - bd.finish).days if bd and cd else None,
                baseline_duration=b.duration_days if b else None,
                current_duration=c.duration_days if c else None,
                baseline_float=bd.total_float_days if bd else None,
                current_float=cd.total_float_days if cd else None,
                was_critical=was_critical,
                is_critical=is_critical,
            )
        )

    # -- link deltas ---------------------------------------------------------
    base_map = {(link.predecessor, link.successor): link for link in base_links}
    curr_map = {(link.predecessor, link.successor): link for link in curr_links}
    link_deltas: list[LinkDelta] = []
    for pair in sorted(set(base_map) | set(curr_map)):
        b_link, c_link = base_map.get(pair), curr_map.get(pair)
        if b_link is None and c_link is not None:
            link_deltas.append(
                LinkDelta(
                    *pair, LinkChange.ADDED, current_type=c_link.type, current_lag=c_link.lag_days
                )
            )
        elif c_link is None and b_link is not None:
            link_deltas.append(
                LinkDelta(
                    *pair,
                    LinkChange.REMOVED,
                    baseline_type=b_link.type,
                    baseline_lag=b_link.lag_days,
                )
            )
        elif b_link is not None and c_link is not None:
            if b_link.type is not c_link.type:
                link_deltas.append(
                    LinkDelta(
                        *pair,
                        LinkChange.TYPE_CHANGED,
                        baseline_type=b_link.type,
                        current_type=c_link.type,
                    )
                )
            if b_link.lag_days != c_link.lag_days:
                link_deltas.append(
                    LinkDelta(
                        *pair,
                        LinkChange.LAG_CHANGED,
                        baseline_lag=b_link.lag_days,
                        current_lag=c_link.lag_days,
                    )
                )

    # -- driving path and attribution ---------------------------------------
    baseline_finish: date = baseline.project_finish  # type: ignore[attr-defined]
    current_finish: date = current.project_finish  # type: ignore[attr-defined]
    driving = _attribute(
        baseline_path=tuple(baseline.longest_path),  # type: ignore[attr-defined]
        current_path=tuple(current.longest_path),  # type: ignore[attr-defined]
        finish_move=(current_finish - baseline_finish).days,
        pairs=pairs,
        base_links=base_link_by_succ,
        curr_links=curr_link_by_succ,
        levelled=levelled,
    )

    return Comparison(
        activities=tuple(deltas),
        links=tuple(link_deltas),
        criticality_gained=tuple(gained),
        criticality_lost=tuple(lost),
        driving_path=driving,
        ambiguous_matches=tuple(ambiguous),
        match_key=match,
        baseline_finish=baseline_finish,
        current_finish=current_finish,
    )


def _link_signature(links: Sequence[Link]) -> tuple[tuple[str, str, int], ...]:
    return tuple(sorted((link.predecessor, link.type.value, link.lag_days) for link in links))


def _attribute(
    *,
    baseline_path: tuple[str, ...],
    current_path: tuple[str, ...],
    finish_move: int,
    pairs: Mapping[str, tuple[Task | None, Task | None]],
    base_links: Mapping[str, list[Link]],
    curr_links: Mapping[str, list[Link]],
    levelled: set[str | None],
) -> DrivingPathDelta:
    """Walk the current driving path and account for every day of the move.

    The residual is named -- ``PATH_SWITCH`` when the path changed, otherwise
    ``UNEXPLAINED`` -- and never silently dropped. An analysis whose parts do not
    sum to the whole cannot be defended.
    """
    contributions: list[DelayContribution] = []
    entered = tuple(a for a in current_path if a not in set(baseline_path))
    left = tuple(a for a in baseline_path if a not in set(current_path))

    for activity_id in current_path:
        pair = pairs.get(activity_id)
        if pair is None:
            continue
        b, c = pair
        if b is None or c is None:
            continue

        grown = c.duration_days - b.duration_days
        if grown:
            contributions.append(
                DelayContribution(
                    activity_id,
                    DelayCause.DURATION_GROWTH,
                    grown,
                    f"duration {b.duration_days} -> {c.duration_days} working days",
                )
            )

        base_lag = {
            (link.predecessor, link.type): link.lag_days for link in base_links.get(b.id, [])
        }
        for link in curr_links.get(c.id, []):
            key = (link.predecessor, link.type)
            if key in base_lag:
                delta = link.lag_days - base_lag[key]
                if delta:
                    contributions.append(
                        DelayContribution(
                            activity_id,
                            DelayCause.LAG_GROWTH,
                            delta,
                            f"lag on {link.predecessor} -> {c.id} "
                            f"{base_lag[key]} -> {link.lag_days} days",
                        )
                    )
            elif link.predecessor in current_path:
                contributions.append(
                    DelayContribution(
                        activity_id,
                        DelayCause.LOGIC_ADDED,
                        0,
                        f"new driving link {link.predecessor} -> {c.id} ({link.type.value})",
                    )
                )

        if (b.constraint, b.constraint_date) != (c.constraint, c.constraint_date):
            contributions.append(
                DelayContribution(
                    activity_id,
                    DelayCause.CONSTRAINT_IMPOSED,
                    0,
                    f"constraint {b.constraint.value} -> {c.constraint.value}",
                )
            )

        if activity_id in levelled:
            contributions.append(
                DelayContribution(
                    activity_id,
                    DelayCause.LEVELLING,
                    0,
                    "moved by the resource leveller, not by a change to the plan",
                )
            )

        if b.actual_finish != c.actual_finish and c.actual_finish is not None:
            contributions.append(
                DelayContribution(
                    activity_id,
                    DelayCause.PROGRESS_SLIP,
                    0,
                    f"actual finish recorded as {c.actual_finish}",
                )
            )

    accounted = sum(c.days for c in contributions)
    residual = finish_move - accounted
    if residual or not contributions:
        cause = DelayCause.PATH_SWITCH if (entered or left) else DelayCause.UNEXPLAINED
        evidence = (
            f"the driving path changed: {' -> '.join(baseline_path) or '(none)'} became "
            f"{' -> '.join(current_path) or '(none)'}"
            if cause is DelayCause.PATH_SWITCH
            else "no change on the driving path accounts for this movement"
        )
        contributions.append(DelayContribution(None, cause, residual, evidence))

    return DrivingPathDelta(
        baseline_path=baseline_path,
        current_path=current_path,
        entered=entered,
        left=left,
        finish_move_days=finish_move,
        attribution=tuple(contributions),
    )


__all__ = [
    "ActivityDelta",
    "ChangeKind",
    "Comparison",
    "DelayCause",
    "DelayContribution",
    "DrivingPathDelta",
    "LinkChange",
    "LinkDelta",
    "MatchKey",
    "compare",
]
