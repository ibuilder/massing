"""Adapter between `mod_schedule_activity` records and the massingplan engine.

The module engine stores every activity as a row with a JSON `data` blob, and
the vendored engine (`services/api/src/massingplan`, see its VENDOR.md) works on
typed `Task`/`Link`/`WorkCalendar` values. This is the only place the two meet.
Nothing else in the API should import `massingplan` directly -- keeping the
translation in one file is what makes an upstream re-sync a copy rather than a
refactor.

What the previous engine (`schedule_cpm.py`, 105 lines) could not represent, and
this adapter now carries through:

* **SS, FF and SF relationships, with leads and lags.** Predecessor tokens are
  parsed as `<ref>[FS|SS|FF|SF][+/-N]`, the notation planners already type.
  Before, every token was a bare Finish-to-Start tie.
* **Calendars.** An activity can name one; without them the forward pass could
  not tell a five-day week from a seven-day one.
* **Constraints, actual dates and remaining duration**, so a progressed schedule
  reschedules from the data date instead of from day zero.

The one idea worth keeping from the old module is its predecessor alias map:
a token may be an activity `ref`, its `wbs` code, or a raw record id, because
the engine's own output emits ids for activities that have no ref. That
resolution lives here rather than in the engine, which knows nothing about
records.
"""

from __future__ import annotations

import re
from collections.abc import Container
from datetime import date, datetime
from typing import Any

from massingplan.core.constraints import ConstraintType
from massingplan.core.constraints import parse as parse_constraint
from massingplan.core.issues import IssueLog
from massingplan.core.network import ActivityKind, Link, RelationType, Task
from massingplan.core.timeaxis import WorkCalendar, WorkPattern

#: A trailing signed lag -- "+3", "-2d", "- 10".
_LAG_SUFFIX = re.compile(r"([+-]\s*\d+)\s*[dD]?$")
#: A trailing relationship type -- "FS", "ss".
_TYPE_SUFFIX = re.compile(r"(FS|SS|FF|SF)$", re.IGNORECASE)

_KINDS = {
    "task": ActivityKind.TASK,
    "milestone": ActivityKind.FINISH_MILESTONE,
    "start milestone": ActivityKind.START_MILESTONE,
    "finish milestone": ActivityKind.FINISH_MILESTONE,
    "summary": ActivityKind.WBS_SUMMARY,
    "level of effort": ActivityKind.LEVEL_OF_EFFORT,
}

#: Named work patterns an activity may reference by `data.calendar`. A project
#: that says nothing gets the five-day week, which is what the old engine
#: assumed implicitly and never wrote down.
CALENDARS: dict[str, WorkCalendar] = {
    "5D": WorkCalendar("5D", "Mon-Fri", WorkPattern(frozenset({0, 1, 2, 3, 4}))),
    "6D": WorkCalendar("6D", "Mon-Sat", WorkPattern(frozenset({0, 1, 2, 3, 4, 5}))),
    "7D": WorkCalendar("7D", "Every day", WorkPattern(frozenset({0, 1, 2, 3, 4, 5, 6}))),
}
DEFAULT_CALENDAR = "5D"


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _duration_days(data: dict) -> int:
    """Duration in days: the stated field if usable, else derived from the dates.

    **The derived convention is deliberately unchanged**: `(finish - start).days`,
    so a span of 1 to 11 January is ten days. That treats the stored `finish` as
    an exclusive boundary. P6's own `target_end_date` is inclusive, which would
    make it eleven -- so this is arguably off by one against the source files.
    It is left alone on purpose: every existing record in every existing project
    was entered under this reading, and silently adding a day to all of them is
    a data migration disguised as a bug fix. Worth deciding explicitly; not worth
    deciding by side effect.

    What *is* fixed is the unambiguous case. The previous engine returned
    `max(0, delta)`, so an activity recorded as starting and finishing on the
    same day came back with **zero** duration -- which made it a milestone and
    silently removed it from the critical path. A day of work is a day.
    """
    explicit = _as_int(data.get("duration"))
    if explicit is not None and explicit >= 0:
        return explicit
    start, finish = _as_date(data.get("start")), _as_date(data.get("finish"))
    if start and finish and finish >= start:
        return max(1, (finish - start).days)
    return 1


def _readings(token: str) -> list[tuple[str, RelationType, int]]:
    """Every way a predecessor token could be read, best first.

    The grammar is genuinely ambiguous and a single regex cannot resolve it.
    `SA-0001` is either the activity `SA-0001`, or the activity `SA` with a lag
    of minus one -- and `PREFIX-NNNN` is exactly the ref format the records
    module generates, so this is the common case rather than a corner.

    An earlier version used one non-greedy pattern, which always preferred the
    *shortest* ref and therefore read every `SA-0001` as `SA` lag -1. The
    predecessor then resolved to nothing, the relationship was dropped, and a
    sequential chain came back as a fully parallel network whose duration was
    the longest single activity. That is the same failure the whole adoption
    exists to fix, reintroduced one layer up.

    So the readings are ordered and the caller picks the first that names a real
    activity. Preferring "this is a ref" over "this is a ref plus a lag" is the
    safe direction: the worst case is a lag nobody meant being ignored, against
    a dependency silently vanishing.
    """
    out: list[tuple[str, RelationType, int]] = [(token, RelationType.FS, 0)]

    lag_match = _LAG_SUFFIX.search(token)
    if lag_match:
        body = token[: lag_match.start()].rstrip()
        lag = int(lag_match.group(1).replace(" ", ""))
        type_match = _TYPE_SUFFIX.search(body)
        if type_match:
            out.append(
                (
                    body[: type_match.start()].strip(),
                    RelationType[type_match.group(1).upper()],
                    lag,
                )
            )
        if body:
            out.append((body, RelationType.FS, lag))

    type_only = _TYPE_SUFFIX.search(token)
    if type_only:
        stem = token[: type_only.start()].strip()
        if stem:
            out.append((stem, RelationType[type_only.group(1).upper()], 0))

    return [(ref, rel, lag) for ref, rel, lag in out if ref]


def parse_predecessor_tokens(
    raw: Any, known: Container[str] | None = None
) -> list[tuple[str, RelationType, int]]:
    """`"A1010FS+3, A1020SS"` -> `[("A1010", FS, 3), ("A1020", SS, 0)]`.

    `known` is the set of resolvable activity keys -- refs, WBS codes and ids.
    When it is supplied, a token that names a real activity in full is read as
    that activity and nothing is stripped from it. Without it the first reading
    is returned, which is the whole token: callers that cannot resolve are
    better served by an unresolved-token report than by a confident mis-parse.
    """
    if not raw:
        return []
    out: list[tuple[str, RelationType, int]] = []
    for chunk in str(raw).replace(";", ",").split(","):
        token = chunk.strip()
        if not token:
            continue
        readings = _readings(token)
        if not readings:
            continue
        if known is None:
            out.append(readings[0])
            continue
        resolved = next((r for r in readings if r[0] in known), None)
        # Nothing resolves: fall back to the whole token. Reporting a *stripped*
        # form would quote something the planner never typed -- telling someone
        # who wrote `SA-0001` that "SA matches no activity" sends them looking
        # for the wrong thing.
        out.append(resolved if resolved is not None else readings[0])
    return out


def build_network(
    records: list[dict], *, issues: IssueLog | None = None
) -> tuple[list[Task], list[Link], dict[str, WorkCalendar], IssueLog]:
    """Map activity records to the engine's inputs.

    Unresolvable predecessor tokens are reported rather than dropped in silence.
    The old engine discarded them, so a typo in a predecessor field produced a
    schedule with a missing dependency and no indication anywhere.
    """
    issues = issues if issues is not None else IssueLog()
    tasks: list[Task] = []
    alias: dict[str, str] = {}
    token_lists: dict[str, list[tuple[str, RelationType, int]]] = {}

    for record in records:
        data = record.get("data") or {}
        rid = record["id"]
        for key in (record.get("ref"), data.get("wbs")):
            if key:
                alias[str(key).strip()] = rid
    # A record id is a legitimate token: the engine emits ids for activities with
    # no ref, so refusing to consume one would make its output unusable as its
    # own input. `setdefault`, so an explicit ref or wbs always wins over an id
    # that happens to collide with one.
    for record in records:
        alias.setdefault(str(record["id"]), record["id"])

    for record in records:
        data = record.get("data") or {}
        rid = record["id"]
        kind = _KINDS.get(str(data.get("activity_type", "")).strip().lower(), ActivityKind.TASK)
        duration = 0 if kind.is_milestone else _duration_days(data)

        calendar_id = str(data.get("calendar") or DEFAULT_CALENDAR).upper()
        if calendar_id not in CALENDARS:
            issues.warn(
                "MASSING.CALENDAR_UNKNOWN",
                f"{record.get('ref') or rid}: calendar {calendar_id!r} is not defined",
                f"used {DEFAULT_CALENDAR}",
                row_key=rid,
                field_name="calendar",
                raw_value=calendar_id,
            )
            calendar_id = DEFAULT_CALENDAR

        constraint = parse_constraint(data.get("constraint"))
        constraint_date = _as_date(data.get("constraint_date"))
        if constraint.needs_date and constraint_date is None:
            constraint = ConstraintType.NONE

        percent = data.get("percent")
        percent_complete = None
        parsed_percent = None if percent in (None, "") else float(percent)
        if parsed_percent is not None:
            percent_complete = parsed_percent / 100 if parsed_percent > 1 else parsed_percent

        tasks.append(
            Task(
                id=rid,
                name=record.get("title") or data.get("name") or rid,
                duration_days=duration,
                calendar_id=calendar_id,
                kind=kind,
                constraint=constraint,
                constraint_date=constraint_date,
                actual_start=_as_date(data.get("actual_start")),
                actual_finish=_as_date(data.get("actual_finish")),
                remaining_days=_as_int(data.get("remaining_duration")),
                percent_complete=percent_complete,
            )
        )
        # `alias` is complete before this loop starts, which is what lets a
        # token that names a real activity be read as that activity rather than
        # split into a ref and a lag that happens to parse.
        token_lists[rid] = parse_predecessor_tokens(data.get("predecessors"), alias)

    known = {t.id for t in tasks}
    links: list[Link] = []
    seen: set[tuple[str, str]] = set()
    for successor, tokens in token_lists.items():
        for ref, rel, lag in tokens:
            predecessor = alias.get(ref)
            if predecessor is None:
                issues.warn(
                    "MASSING.PREDECESSOR_UNRESOLVED",
                    f"{successor}: predecessor {ref!r} matches no activity",
                    "relationship dropped",
                    row_key=successor,
                    field_name="predecessors",
                    raw_value=ref,
                )
                continue
            if predecessor == successor or predecessor not in known:
                continue
            if (predecessor, successor) in seen:
                continue
            seen.add((predecessor, successor))
            links.append(Link(predecessor, successor, rel, lag))

    return tasks, links, dict(CALENDARS), issues


def data_date_for(records: list[dict], fallback: date | None = None) -> date:
    """The date to schedule from: the latest recorded actual, else the earliest
    planned start, else today.

    Scheduling a progressed job from its planned start reports every completed
    activity as still to do.
    """
    actuals: list[date] = []
    starts: list[date] = []
    for record in records:
        data = record.get("data") or {}
        for key in ("actual_finish", "actual_start"):
            parsed = _as_date(data.get(key))
            if parsed:
                actuals.append(parsed)
        planned = _as_date(data.get("start"))
        if planned:
            starts.append(planned)
    if actuals:
        return max(actuals)
    if starts:
        return min(starts)
    return fallback or date.today()


#: Keys a caller may do arithmetic on without checking, on **every** exit of
#: `compute()` -- the normal one, the empty one and the cyclic one.
#:
#: The split matters and is not arbitrary. `total_float` is a *filter* key:
#: every consumer compares it against a threshold (`0 < tf <= 5` in
#: `px.optimize`), and a completed or unschedulable activity reporting 0 falls
#: outside every "watch this one" filter, which is the right answer. The date
#: and offset keys are *position* keys: 0 there would put every activity on day
#: zero and draw a Gantt of two hundred bars stacked at the origin, which is
#: fabricating a schedule -- the exact thing the cyclic refusal exists to
#: prevent.
#:
#: So: numeric where a number is safe, `None` where a number would be a lie.
NUMERIC_ROW_KEYS = ("duration", "total_float", "free_float")

#: Keys that are `None` when there is no computed schedule. A caller that
#: renders `None` shows a gap; a caller that renders a fabricated 0 shows a
#: schedule.
NULLABLE_ROW_KEYS = (
    "es",
    "ef",
    "ls",
    "lf",
    "start_date",
    "finish_date",
    "late_start_date",
    "late_finish_date",
    "total_float_days",
    "free_float_days",
)


def blank_result() -> dict[str, Any]:
    """The top-level envelope every exit of `compute()` fills in.

    Same argument as `blank_row`, one level up. The three exits disagreed here
    too: `cycle` existed only on the cyclic and empty exits, so a caller reading
    `cpm["cycle"]` on a normal schedule got a KeyError, and the five date and
    driving-path keys existed only on the computed one. Both are the sort of
    break that shows up the first time somebody draws a loop, in code that has
    worked for a year.
    """
    return {
        "project_duration": 0,
        "activity_count": 0,
        "critical_count": 0,
        "has_cycle": False,
        "activities": [],
        "critical_path": [],
        "cycle": [],
        "issues": [],
        # Additive keys. Present everywhere, `None` where there is nothing to
        # say, so `in` and `[...]` behave the same on every exit.
        "data_date": None,
        "project_start_date": None,
        "project_finish_date": None,
        "driving_path": [],
        "violations": [],
    }


def blank_row(task: Task, ref: str | None) -> dict[str, Any]:
    """One activity with **no computed schedule** — the cyclic and empty exits.

    Every legacy row is built from this, including the computed one, so the key
    sets cannot drift between exits and a coercion applied in one place cannot
    be missing from another. That is not hypothetical: the float coercion
    originally landed on the computed exit only, and a cyclic network then
    crashed `px.optimize` on `0 < None` instead of refusing.
    """
    return {
        "id": task.id,
        "ref": ref,
        "name": task.name,
        "duration": task.duration_days,
        "es": None,
        "ef": None,
        "ls": None,
        "lf": None,
        # Numeric even here. See NUMERIC_ROW_KEYS.
        "total_float": 0,
        "free_float": 0,
        "total_float_days": None,
        "free_float_days": None,
        "has_float": False,
        "critical": False,
        "predecessors": [],
        "start_date": None,
        "finish_date": None,
        "late_start_date": None,
        "late_finish_date": None,
        "calendar": task.calendar_id,
        "status": "not_started",
        "remaining_days": task.duration_days,
        "on_driving_path": False,
        "constraint_satisfied": True,
    }


def _numeric_float(value: int | None) -> int:
    """`None` -> 0, for the legacy float keys only.

    Zero rather than a sentinel because every existing reader compares it
    against a threshold, and a completed activity should fall outside every
    "watch this one" filter -- which `0` does and `-1` or a large number would
    not. The unmodified value is available as `total_float_days`, and
    `has_float` distinguishes "no float" from "genuinely zero float".
    """
    return 0 if value is None else value


def to_legacy_rows(outcome: Any, tasks: list[Task], links: list[Link], records: list[dict]) -> dict:
    """Render an engine result in the shape `schedule_cpm.compute()` always returned.

    Existing callers -- EVM, the extension-of-time analysis, resource loading,
    the vitals dashboard, the Gantt renderer -- read working-day offsets from day
    zero, so those are preserved exactly. Real dates, calendars, constraint
    violations and the driving path are added as *new* keys, which no caller can
    be broken by.
    """
    network = outcome.network
    by_ref = {r["id"]: r.get("ref") for r in records}
    project_start = network.project_start
    default_cal = CALENDARS[DEFAULT_CALENDAR]
    incoming: dict[str, list[str]] = {}
    for link in links:
        incoming.setdefault(link.successor, []).append(link.predecessor)

    def offset(instant: int, calendar_id: str) -> int:
        cal = CALENDARS.get(calendar_id, default_cal)
        return cal.count_working_days(project_start, instant)

    rows = []
    for task in tasks:
        aid = task.id
        dates = outcome.dates[aid]
        # Built *from* the blank row, so the computed and uncomputed exits
        # cannot drift apart in their key sets.
        rows.append(
            {
                **blank_row(task, by_ref.get(aid)),
                "es": offset(network.early_start[aid], task.calendar_id),
                "ef": offset(network.early_finish[aid], task.calendar_id),
                "ls": offset(network.late_start[aid], task.calendar_id),
                "lf": offset(network.late_finish[aid], task.calendar_id),
                # Numeric, always -- the legacy contract. The engine reports
                # `None` for completed work, and that is the better answer: a
                # finished activity has no float, and writing 0 puts it on the
                # critical path. But existing callers do arithmetic on this key
                # without checking. `px.optimize` filters on
                # `0 < total_float <= 5` behind an `_open()` test that decides
                # completeness from `percent`, while the engine decides it from
                # actual dates -- so an activity with an actual finish and no
                # recorded percent is open to one and complete to the other, and
                # the comparison raises TypeError.
                #
                # So the legacy keys stay numeric and the honest value is
                # carried alongside, which is the same additive rule the rest of
                # this function follows.
                "total_float": _numeric_float(network.total_float_days[aid]),
                "free_float": _numeric_float(network.free_float_days[aid]),
                "total_float_days": network.total_float_days[aid],
                "free_float_days": network.free_float_days[aid],
                "has_float": network.total_float_days[aid] is not None,
                "critical": network.is_critical(aid),
                "predecessors": incoming.get(aid, []),
                # -- new, additive --------------------------------------------
                "start_date": dates.start.isoformat(),
                "finish_date": dates.finish.isoformat(),
                "late_start_date": dates.late_start.isoformat(),
                "late_finish_date": dates.late_finish.isoformat(),
                "calendar": task.calendar_id,
                "status": dates.status.value,
                "remaining_days": dates.remaining_days,
                "on_driving_path": dates.is_longest_path,
                "constraint_satisfied": dates.constraint_satisfied,
            }
        )
    rows.sort(key=lambda r: (r["es"], r["ef"], r["id"]))

    return {
        **blank_result(),
        "project_duration": offset(network.project_finish, DEFAULT_CALENDAR),
        "activity_count": len(rows),
        "critical_count": sum(1 for r in rows if r["critical"]),
        # The old engine returned `has_cycle: True` and carried on with wrong
        # numbers. The new one raises, and the shim converts that into this flag
        # plus an empty result -- so a cyclic network can no longer be mistaken
        # for a scheduled one.
        "has_cycle": False,
        "activities": rows,
        "critical_path": [r["ref"] or r["id"] for r in rows if r["critical"]],
        # -- new, additive ------------------------------------------------
        "data_date": outcome.data_date.isoformat(),
        "project_start_date": outcome.project_start.isoformat(),
        "project_finish_date": outcome.project_finish.isoformat(),
        "driving_path": list(outcome.longest_path),
        "violations": [v.to_dict() for v in outcome.violations],
        "issues": [i.to_dict() for i in outcome.issues],
    }
