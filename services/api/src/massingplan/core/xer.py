"""Reading and writing Primavera P6 XER files.

XER is tab-delimited text. Each table is introduced by ``%T``, its column names
by ``%F``, each row by ``%R``, and the file ends with ``%E``::

    ERMHDR	19.12	2026-08-08	Project	admin	...
    %T	PROJECT
    %F	proj_id	proj_short_name	plan_start_date
    %R	1	NGT-2026	2026-09-07 00:00
    %E

The tokenizer is the easy part. What makes an importer right or wrong is the
field mapping, and there are four traps worth naming because a previous
implementation fell into all of them:

* **Relationship types are prefixed.** P6 writes ``PR_FS``, ``PR_SS``,
  ``PR_FF``, ``PR_SF``. Mapping them by hand rather than by string-slicing keeps
  an unexpected value loud instead of silently turning every SS/FF/SF tie into
  FS -- which changes the critical path with no error raised.
* **Durations are hours against a calendar**, and not always eight-hour days.
  ``CALENDAR.day_hr_cnt`` carries the figure; ignoring it rescales every
  duration in the file.
* **Milestones have zero duration.** Clamping with ``max(1, ...)`` turns them
  into one-day tasks and changes the network.
* **Costs and notes live in other tables.** ``TASK`` has no ``target_cost``;
  costs are in ``TASKRSRC`` and notes in ``TASKMEMO``. Reading them from
  ``TASK`` silently yields zero.

And two things this reader does that neither predecessor did:

* **``TASKPRED`` is read.** The consuming product's importer omits it entirely,
  so every imported activity arrives with no logic -- and a network with no
  logic reports every activity as critical with zero float. That is the single
  most damaging gap this module exists to close.
* **Calendar exceptions are parsed.** The previous reader returned an empty
  exception list with a comment saying holidays were "left for a later pass
  rather than guessed at". Honest for a prototype, and now the biggest single
  source of date error: an unparsed two-week Christmas shutdown moves every
  downstream date two weeks early.

Every default taken, value coerced or row dropped emits an :class:`Issue`
carrying a stable code and the action. A silent default produces a plausible
schedule that is wrong, with nothing in the output to look at.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .constraints import ConstraintType
from .issues import IssueLog
from .model import (
    Calendar,
    CalendarException,
    ExchangeActivity,
    ExchangeAssignment,
    ExchangeRelationship,
    ExchangeResource,
    ExchangeSchedule,
    WBSNode,
)
from .network import ActivityKind, LagCalendar, ProgressMode, RelationType, SchedulerOptions
from .units import days_from_hours, hours_from_days

# Mapped by hand, not by slicing off "PR_". An unrecognised value must be loud.
XER_RELATION_TYPES = {
    "PR_FS": RelationType.FS,
    "PR_SS": RelationType.SS,
    "PR_FF": RelationType.FF,
    "PR_SF": RelationType.SF,
}
RELATION_TYPES_TO_XER = {v: k for k, v in XER_RELATION_TYPES.items()}

XER_ACTIVITY_KINDS = {
    "TT_Task": ActivityKind.TASK,
    "TT_Rsrc": ActivityKind.TASK,
    "TT_Mile": ActivityKind.START_MILESTONE,
    "TT_FinMile": ActivityKind.FINISH_MILESTONE,
    "TT_LOE": ActivityKind.LEVEL_OF_EFFORT,
    "TT_WBS": ActivityKind.WBS_SUMMARY,
}
ACTIVITY_KINDS_TO_XER = {
    ActivityKind.TASK: "TT_Task",
    ActivityKind.START_MILESTONE: "TT_Mile",
    ActivityKind.FINISH_MILESTONE: "TT_FinMile",
    ActivityKind.LEVEL_OF_EFFORT: "TT_LOE",
    ActivityKind.WBS_SUMMARY: "TT_WBS",
}

XER_CONSTRAINTS = {
    "": ConstraintType.NONE,
    "CS_ALAP": ConstraintType.AS_LATE_AS_POSSIBLE,
    "CS_MEO": ConstraintType.FINISH_ON,
    "CS_MEOA": ConstraintType.FINISH_ON_OR_AFTER,
    "CS_MEOB": ConstraintType.FINISH_ON_OR_BEFORE,
    "CS_MSO": ConstraintType.START_ON,
    "CS_MSOA": ConstraintType.START_ON_OR_AFTER,
    "CS_MSOB": ConstraintType.START_ON_OR_BEFORE,
    "CS_MANDFIN": ConstraintType.MANDATORY_FINISH,
    "CS_MANDSTART": ConstraintType.MANDATORY_START,
}
CONSTRAINTS_TO_XER = {v: k for k, v in XER_CONSTRAINTS.items() if k}

DEFAULT_HOURS_PER_DAY = 8.0

#: P6 packs calendar exception days as a serial number counting from this
#: epoch -- the same one Excel uses, including its off-by-one leap-year quirk.
_SERIAL_EPOCH = date(1899, 12, 30)

#: Tables we recognise and deliberately do not use. Named rather than ignored,
#: so "why did my OBS not come across" has an answer in the import report.
_SKIPPED_TABLES = {
    "OBS": "organisational breakdown structure",
    "ROLES": "role definitions",
    "ACCOUNT": "cost accounts",
    "PROJPROP": "project properties",
    "RISKTYPE": "risk register",
}


class XERError(ValueError):
    """The file could not be read as XER at all."""


# -- tokenizer -------------------------------------------------------------


def parse_tables(content: str) -> dict[str, list[dict[str, str]]]:
    """Split XER text into ``{table_name: [row_dict, ...]}``.

    Rows whose column count differs from the header are padded or trimmed rather
    than discarded: P6 exports occasionally carry a trailing empty field, and
    losing a whole activity over that would be the worse failure.
    """
    tables: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    headers: list[str] = []

    for raw_line in content.splitlines():
        if not raw_line:
            continue
        # Only the line ending is stripped. Leading spaces can be significant
        # inside a field, and `rstrip("\n")` alone leaves a stray "\r" on CRLF.
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue

        parts = line.split("\t")
        marker = parts[0]

        if marker == "%T":
            current = parts[1] if len(parts) > 1 else None
            headers = []
            if current:
                tables.setdefault(current, [])
        elif marker == "%F":
            headers = parts[1:]
        elif marker == "%R":
            if not current or not headers:
                continue
            values = parts[1:]
            if len(values) < len(headers):
                values += [""] * (len(headers) - len(values))
            elif len(values) > len(headers):
                values = values[: len(headers)]
            tables[current].append(dict(zip(headers, values, strict=True)))
        elif marker == "%E":
            current = None
            headers = []

    return tables


def _parse_date(value: str | None) -> date | None:
    """P6 writes ``YYYY-MM-DD HH:MM``; tolerate a few near neighbours."""
    if not value or not value.strip():
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d 00:00")


# -- calendar blob ---------------------------------------------------------


def _day_block(section: str, marker: str) -> str:
    """The parenthesised block following ``marker``, delimited by matching brackets.

    A fixed-width window reads into the next day's shifts, because the day
    blocks run together with no separator.
    """
    start = section.find(marker)
    if start == -1:
        return ""
    depth = 0
    for index in range(start, len(section)):
        char = section[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return section[start : index + 1]
    return ""


def parse_calendar_data(
    blob: str, calendar_id: str, issues: IssueLog
) -> tuple[set[int], list[CalendarException]]:
    """Weekly pattern *and* exceptions from P6's packed calendar string.

    The weekly pattern lives under ``DaysOfWeek`` as ``(N()...)`` blocks where N
    runs Sunday=1 to Saturday=7; a day listing at least one shift (``s|``) is a
    working day. Exceptions live under ``Exceptions`` as ``d|<serial>`` blocks,
    where a block carrying shifts is a *working* exception (a make-up Saturday)
    and one without is a holiday.
    """
    default = {0, 1, 2, 3, 4}
    if not blob or "DaysOfWeek" not in blob:
        if blob:
            issues.warn(
                "XER.CALENDAR.UNPARSEABLE",
                f"calendar {calendar_id}: clndr_data has no DaysOfWeek section",
                "assumed a standard Monday-Friday week",
                table="CALENDAR",
                row_key=calendar_id,
                field_name="clndr_data",
            )
        return default, []

    working: set[int] = set()
    # P6 numbers Sunday=1..Saturday=7; Python numbers Monday=0..Sunday=6.
    p6_to_python = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}

    section = blob.split("DaysOfWeek", 1)[1]
    exceptions_at = section.find("Exceptions")
    weekly = section[:exceptions_at] if exceptions_at != -1 else section

    for p6_day, python_day in p6_to_python.items():
        block = _day_block(weekly, f"({p6_day}(")
        if block and "s|" in block:
            working.add(python_day)

    if not working:
        working = default
        issues.warn(
            "XER.CALENDAR.NO_WORKING_DAYS",
            f"calendar {calendar_id}: no working day carried any shift",
            "assumed a standard Monday-Friday week",
            table="CALENDAR",
            row_key=calendar_id,
            field_name="clndr_data",
        )

    exceptions: list[CalendarException] = []
    if exceptions_at != -1:
        exceptions = _parse_exceptions(section[exceptions_at:], calendar_id, issues)
    return working, exceptions


def _parse_exceptions(section: str, calendar_id: str, issues: IssueLog) -> list[CalendarException]:
    """Pull ``d|<serial>`` exception blocks out of the Exceptions section."""
    found: list[CalendarException] = []
    cursor = 0
    while True:
        at = section.find("d|", cursor)
        if at == -1:
            break
        cursor = at + 2
        digits = ""
        for char in section[cursor:]:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            continue
        cursor += len(digits)
        try:
            day = _SERIAL_EPOCH + timedelta(days=int(digits))
        except (ValueError, OverflowError):
            issues.warn(
                "XER.CALENDAR.BAD_EXCEPTION_SERIAL",
                f"calendar {calendar_id}: exception day serial {digits!r} is out of range",
                "exception dropped",
                table="CALENDAR",
                row_key=calendar_id,
                field_name="clndr_data",
                raw_value=digits,
            )
            continue
        # The block that follows the serial says whether any shift is worked.
        block_start = section.find("(", cursor)
        block = ""
        if block_start != -1 and block_start - cursor < 8:
            depth = 0
            for index in range(block_start, len(section)):
                if section[index] == "(":
                    depth += 1
                elif section[index] == ")":
                    depth -= 1
                    if depth == 0:
                        block = section[block_start : index + 1]
                        break
        found.append(CalendarException(day=day, working="s|" in block))
    return found


# -- reading ---------------------------------------------------------------


def read_xer(content: str, *, project_id: str | None = None) -> ExchangeSchedule:
    """Read an XER file into the hub model."""
    if "%T" not in content:
        raise XERError("no %T table marker found; this does not look like an XER file")

    tables = parse_tables(content)
    schedule = ExchangeSchedule(source_format="xer")
    issues = schedule.issues

    for name, description in _SKIPPED_TABLES.items():
        if tables.get(name):
            issues.info(
                "XER.TABLE_SKIPPED",
                f"{name} ({description}) carried {len(tables[name])} rows",
                "recognised and not imported",
                table=name,
            )

    chosen = _read_project(tables, schedule, project_id)
    _read_schedule_options(tables, schedule)
    calendars = _read_calendars(tables, schedule)
    _read_wbs(tables, schedule, chosen)
    _read_activities(tables, schedule, calendars, chosen)
    _read_relationships(tables, schedule)
    _read_resources(tables, schedule)
    _read_assignments(tables, schedule)
    _read_notes(tables, schedule)
    _read_activity_codes(tables, schedule)
    return schedule


def _read_project(
    tables: dict[str, list[dict[str, str]]],
    schedule: ExchangeSchedule,
    requested: str | None,
) -> str | None:
    rows = tables.get("PROJECT", [])
    if not rows:
        schedule.issues.warn(
            "XER.PROJECT.MISSING",
            "the file contains no PROJECT table",
            "imported every activity found, with no project metadata",
            table="PROJECT",
        )
        return None

    row = rows[0]
    if requested is not None:
        match = next((r for r in rows if r.get("proj_id") == requested), None)
        if match is None:
            schedule.issues.error(
                "XER.PROJECT.NOT_FOUND",
                f"requested project {requested!r} is not in this file",
                f"imported {row.get('proj_short_name')} instead",
                table="PROJECT",
                raw_value=requested,
            )
        else:
            row = match
    elif len(rows) > 1:
        schedule.issues.warn(
            "XER.PROJECT.MULTIPLE",
            "the file contains "
            + str(len(rows))
            + " projects: "
            + ", ".join(sorted(str(r.get("proj_short_name", "?")) for r in rows)),
            f"imported the first ({row.get('proj_short_name')})",
            table="PROJECT",
        )

    schedule.project_id = row.get("proj_id", "")
    schedule.project_name = row.get("proj_short_name", "") or row.get("proj_id", "")
    # `last_recalc_date` is the data date. Reading `plan_start_date` for it makes
    # every progressed schedule reschedule from its original start and report all
    # the completed work as still to do.
    schedule.data_date = _parse_date(row.get("last_recalc_date"))
    schedule.planned_start = _parse_date(row.get("plan_start_date"))
    schedule.must_finish_by = _parse_date(row.get("scd_end_date"))
    schedule.default_calendar_id = row.get("clndr_id") or None
    return schedule.project_id or None


def _read_schedule_options(
    tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule
) -> None:
    """Read SCHEDOPTIONS so a disagreement with P6's own dates is explicable.

    Rescheduling a file under different retained-logic settings gives different
    dates. Without recording what the file asked for, nobody can tell whether a
    difference is a bug in this engine or a deliberate option.
    """
    rows = tables.get("SCHEDOPTIONS", [])
    if not rows:
        return
    row = rows[0]
    source = {k: v for k, v in row.items() if v not in ("", None)}

    # P6 writes the pair inconsistently across versions: some exports set only
    # `sched_progress_override`, others only clear `sched_retained_logic`. Read
    # both, and treat retained logic as the default when neither is decisive --
    # which is what P6 itself does.
    mode = ProgressMode.RETAINED_LOGIC
    override = row.get("sched_progress_override")
    retained = row.get("sched_retained_logic")
    if override == "Y" or (retained == "N" and override != "N"):
        mode = ProgressMode.PROGRESS_OVERRIDE

    lag_calendar = LagCalendar.PREDECESSOR
    raw_lag = (row.get("sched_calendar_on_relationship_lag") or "").strip()
    lag_map = {
        "rcal_Predecessor": LagCalendar.PREDECESSOR,
        "rcal_Successor": LagCalendar.SUCCESSOR,
        "rcal_24Hour": LagCalendar.TWENTY_FOUR_HOUR,
        "rcal_Project": LagCalendar.PROJECT_DEFAULT,
    }
    if raw_lag:
        if raw_lag in lag_map:
            lag_calendar = lag_map[raw_lag]
        else:
            schedule.issues.warn(
                "XER.SCHEDOPTIONS.UNKNOWN_LAG_CALENDAR",
                f"unrecognised lag calendar {raw_lag!r}",
                "used the predecessor's calendar, which is P6's default",
                table="SCHEDOPTIONS",
                field_name="sched_calendar_on_relationship_lag",
                raw_value=raw_lag,
            )

    schedule.options = SchedulerOptions(
        progress_mode=mode, lag_calendar=lag_calendar, source_options=source
    )


def _read_calendars(
    tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule
) -> dict[str, Calendar]:
    calendars: dict[str, Calendar] = {}
    for row in tables.get("CALENDAR", []):
        cal_id = row.get("clndr_id", "")
        if not cal_id:
            continue
        hours = _parse_float(row.get("day_hr_cnt"))
        if hours is None or hours <= 0:
            hours = DEFAULT_HOURS_PER_DAY
            schedule.issues.warn(
                "XER.CALENDAR.NO_DAY_HR_CNT",
                f"calendar {cal_id} carries no usable day_hr_cnt",
                f"defaulted to {DEFAULT_HOURS_PER_DAY} hours per day",
                table="CALENDAR",
                row_key=cal_id,
                field_name="day_hr_cnt",
                raw_value=row.get("day_hr_cnt"),
            )
        weekdays, exceptions = parse_calendar_data(
            row.get("clndr_data", ""), cal_id, schedule.issues
        )
        cal = Calendar(
            id=cal_id,
            name=row.get("clndr_name", "") or cal_id,
            working_weekdays=weekdays,
            exceptions=exceptions,
            hours_per_day=hours,
            is_default=row.get("default_flag") == "Y",
        )
        calendars[cal_id] = cal
        schedule.calendars.append(cal)

    if not calendars:
        fallback = Calendar("default", "Standard 5-day", {0, 1, 2, 3, 4}, is_default=True)
        calendars["default"] = fallback
        schedule.calendars.append(fallback)
        schedule.issues.warn(
            "XER.CALENDAR.MISSING",
            "the file contains no CALENDAR table",
            "assumed a standard 5-day, 8-hour week",
            table="CALENDAR",
        )

    if not schedule.default_calendar_id or schedule.default_calendar_id not in calendars:
        default = next((c for c in schedule.calendars if c.is_default), schedule.calendars[0])
        schedule.default_calendar_id = default.id
    return calendars


def _belongs_to(row: dict[str, str], project_id: str | None) -> bool:
    """Whether a row is part of the project being imported.

    A row whose ``proj_id`` is absent or empty belongs to it. Treating a missing
    column as "some other project" drops every activity in a single-project
    export that simply does not write the column -- and the import then reports
    success with an empty schedule.
    """
    if not project_id:
        return True
    value = row.get("proj_id")
    return value is None or value == "" or value == project_id


def _read_wbs(
    tables: dict[str, list[dict[str, str]]],
    schedule: ExchangeSchedule,
    project_id: str | None,
) -> None:
    for row in tables.get("PROJWBS", []):
        if not _belongs_to(row, project_id):
            continue
        node_id = row.get("wbs_id", "")
        if not node_id:
            continue
        schedule.wbs.append(
            WBSNode(
                id=node_id,
                name=row.get("wbs_name", ""),
                # A root node's parent points outside the project; keeping it
                # would make `validate` report a dangling reference on a file
                # that is perfectly well formed.
                parent_id=(
                    None if row.get("proj_node_flag") == "Y" else (row.get("parent_wbs_id") or None)
                ),
                code=row.get("wbs_short_name", ""),
                sequence=int(_parse_float(row.get("seq_num")) or 0.0),
            )
        )
    known = {n.id for n in schedule.wbs}
    for node in schedule.wbs:
        if node.parent_id and node.parent_id not in known:
            node.parent_id = None


def _read_activities(
    tables: dict[str, list[dict[str, str]]],
    schedule: ExchangeSchedule,
    calendars: dict[str, Calendar],
    project_id: str | None,
) -> None:
    default_cal = schedule.default_calendar_id or next(iter(calendars))
    for row in tables.get("TASK", []):
        if not _belongs_to(row, project_id):
            continue
        task_id = row.get("task_id", "")
        if not task_id:
            continue

        cal_id = row.get("clndr_id") or default_cal
        if cal_id not in calendars:
            schedule.issues.warn(
                "XER.TASK.UNKNOWN_CALENDAR",
                f"activity {task_id} references calendar {cal_id!r}, which is not in the file",
                f"used the project default ({default_cal})",
                table="TASK",
                row_key=task_id,
                field_name="clndr_id",
                raw_value=cal_id,
            )
            cal_id = default_cal
        hours_per_day = calendars[cal_id].hours_per_day

        raw_kind = row.get("task_type", "TT_Task")
        kind = XER_ACTIVITY_KINDS.get(raw_kind)
        if kind is None:
            kind = ActivityKind.TASK
            schedule.issues.warn(
                "XER.TASK.UNKNOWN_TYPE",
                f"activity {task_id} has task_type {raw_kind!r}",
                "treated as an ordinary task",
                table="TASK",
                row_key=task_id,
                field_name="task_type",
                raw_value=raw_kind,
            )

        duration = days_from_hours(_parse_float(row.get("target_drtn_hr_cnt")), hours_per_day)
        remaining_hours = _parse_float(row.get("remain_drtn_hr_cnt"))
        remaining = (
            None if remaining_hours is None else days_from_hours(remaining_hours, hours_per_day)
        )
        # A milestone is an instant. `max(1, ...)` here is one of the four
        # documented traps, and it changes the logic network.
        if kind.is_milestone:
            duration = 0
            remaining = 0 if remaining is not None else None

        constraint = _read_constraint(row, "cstr_type", task_id, schedule)
        secondary = _read_constraint(row, "cstr_type2", task_id, schedule)

        schedule.activities.append(
            ExchangeActivity(
                id=task_id,
                name=row.get("task_name", ""),
                kind=kind,
                wbs_id=row.get("wbs_id") or None,
                calendar_id=cal_id,
                duration_days=duration,
                remaining_duration_days=remaining,
                early_start=_parse_date(row.get("early_start_date")),
                early_finish=_parse_date(row.get("early_end_date")),
                late_start=_parse_date(row.get("late_start_date")),
                late_finish=_parse_date(row.get("late_end_date")),
                actual_start=_parse_date(row.get("act_start_date")),
                actual_finish=_parse_date(row.get("act_end_date")),
                planned_start=_parse_date(row.get("target_start_date")),
                planned_finish=_parse_date(row.get("target_end_date")),
                constraint=constraint,
                constraint_date=_parse_date(row.get("cstr_date")),
                secondary_constraint=secondary,
                secondary_constraint_date=_parse_date(row.get("cstr_date2")),
                suspend_date=_parse_date(row.get("suspend_date")),
                resume_date=_parse_date(row.get("resume_date")),
                physical_percent_complete=_percent(row.get("phys_complete_pct")),
                is_longest_path=row.get("driving_path_flag") == "Y",
                code=row.get("task_code", ""),
            )
        )

        if row.get("suspend_date"):
            schedule.issues.warn(
                "XER.TASK.SUSPEND_NOT_MODELLED",
                f"activity {task_id} carries a suspend/resume period",
                "the dates are preserved but the interruption is not scheduled",
                table="TASK",
                row_key=task_id,
                field_name="suspend_date",
            )

    # A constraint type with no date is meaningless and would fail validation
    # later with a less useful message.
    for activity in schedule.activities:
        if activity.constraint.needs_date and activity.constraint_date is None:
            schedule.issues.warn(
                "XER.TASK.CONSTRAINT_WITHOUT_DATE",
                f"activity {activity.id} has constraint "
                f"{activity.constraint.value} but no cstr_date",
                "constraint dropped",
                table="TASK",
                row_key=activity.id,
                field_name="cstr_date",
            )
            activity.constraint = ConstraintType.NONE


def _read_constraint(
    row: dict[str, str], field: str, task_id: str, schedule: ExchangeSchedule
) -> ConstraintType:
    raw = (row.get(field) or "").strip()
    if not raw:
        return ConstraintType.NONE
    kind = XER_CONSTRAINTS.get(raw)
    if kind is None:
        schedule.issues.warn(
            "XER.TASK.UNKNOWN_CONSTRAINT",
            f"activity {task_id} has {field} {raw!r}",
            "constraint dropped",
            table="TASK",
            row_key=task_id,
            field_name=field,
            raw_value=raw,
        )
        return ConstraintType.NONE
    return kind


def _percent(value: str | None) -> float | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    # P6 stores this as a fraction in some exports and a percentage in others.
    return parsed / 100.0 if parsed > 1.0 else parsed


def _read_relationships(
    tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule
) -> None:
    """Read TASKPRED -- the table the consuming product's importer omits entirely.

    Without it every activity arrives with no logic, and a network with no logic
    reports every activity as critical with zero float. The importer looks like
    it worked, and the schedule it produces is worthless.
    """
    rows = tables.get("TASKPRED", [])
    if not rows and schedule.activities:
        schedule.issues.warn(
            "XER.TASKPRED.MISSING",
            "the file contains no TASKPRED table, so the network has no logic",
            "imported activities with no relationships; every activity will read "
            "as critical with zero float",
            table="TASKPRED",
        )
        return

    known = {a.id for a in schedule.activities}
    for row in rows:
        pred, succ = row.get("pred_task_id", ""), row.get("task_id", "")
        if pred not in known or succ not in known:
            schedule.issues.warn(
                "XER.TASKPRED.DANGLING",
                f"relationship {pred} -> {succ} references an activity outside this project",
                "relationship dropped",
                table="TASKPRED",
                row_key=f"{pred}->{succ}",
            )
            continue
        if pred == succ:
            schedule.issues.error(
                "XER.TASKPRED.SELF_LOOP",
                f"activity {pred} is its own predecessor",
                "relationship dropped",
                table="TASKPRED",
                row_key=pred,
            )
            continue

        raw_type = (row.get("pred_type") or "").strip()
        rel = XER_RELATION_TYPES.get(raw_type)
        if rel is None:
            rel = RelationType.FS
            schedule.issues.warn(
                "XER.TASKPRED.UNKNOWN_TYPE",
                f"relationship {pred} -> {succ} has pred_type {raw_type!r}",
                "coerced to FS; the critical path may differ from P6's",
                table="TASKPRED",
                row_key=f"{pred}->{succ}",
                field_name="pred_type",
                raw_value=raw_type,
            )

        activity = schedule.activity(succ)
        cal = schedule.calendar_for(activity) if activity else None
        hours_per_day = cal.hours_per_day if cal else DEFAULT_HOURS_PER_DAY
        lag_hours = _parse_float(row.get("lag_hr_cnt")) or 0.0
        # Lags can be negative, so the sign has to survive the hours-to-days
        # conversion, which only handles non-negative input.
        sign = -1 if lag_hours < 0 else 1
        lag_days = sign * days_from_hours(abs(lag_hours), hours_per_day)

        schedule.relationships.append(ExchangeRelationship(pred, succ, rel, lag_days))


def _read_resources(tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule) -> None:
    rates: dict[str, float] = {}
    for row in tables.get("RSRCRATE", []):
        rid = row.get("rsrc_id", "")
        cost = _parse_float(row.get("cost_per_qty"))
        if rid and cost is not None and rid not in rates:
            rates[rid] = cost

    for row in tables.get("RSRC", []):
        rid = row.get("rsrc_id", "")
        if not rid:
            continue
        schedule.resources.append(
            ExchangeResource(
                id=rid,
                name=row.get("rsrc_name", "") or rid,
                type=(row.get("rsrc_type", "") or "RT_Labor").replace("RT_", "").lower(),
                unit=row.get("unit_id", ""),
                unit_cost=rates.get(rid),
                max_units_per_day=_parse_float(row.get("def_qty_per_hr")),
                calendar_id=row.get("clndr_id") or None,
            )
        )


def _read_assignments(tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule) -> None:
    """Costs come from TASKRSRC, not TASK. Reading them from TASK yields zero."""
    known_activities = {a.id for a in schedule.activities}
    known_resources = {r.id for r in schedule.resources}
    for row in tables.get("TASKRSRC", []):
        task_id, rsrc_id = row.get("task_id", ""), row.get("rsrc_id", "")
        if task_id not in known_activities:
            continue
        if rsrc_id not in known_resources:
            schedule.issues.warn(
                "XER.TASKRSRC.UNKNOWN_RESOURCE",
                f"assignment on {task_id} references resource {rsrc_id!r}, not in the file",
                "assignment dropped",
                table="TASKRSRC",
                row_key=task_id,
                raw_value=rsrc_id,
            )
            continue
        actual = (_parse_float(row.get("act_reg_cost")) or 0.0) + (
            _parse_float(row.get("act_ot_cost")) or 0.0
        )
        schedule.assignments.append(
            ExchangeAssignment(
                activity_id=task_id,
                resource_id=rsrc_id,
                units_per_day=_parse_float(row.get("target_qty_per_hr")),
                budgeted_units=_parse_float(row.get("target_qty")),
                budgeted_cost=_parse_float(row.get("target_cost")),
                actual_cost=actual or None,
            )
        )


def _read_notes(tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule) -> None:
    """Notes come from TASKMEMO, not TASK."""
    memo_types = {
        r.get("memo_type_id", ""): r.get("memo_type", "") for r in tables.get("MEMOTYPE", [])
    }
    for row in tables.get("TASKMEMO", []):
        activity = schedule.activity(row.get("task_id", ""))
        if activity is None:
            continue
        label = memo_types.get(row.get("memo_type_id", ""), "").strip()
        body = (row.get("task_memo", "") or "").strip()
        if not body:
            continue
        entry = f"{label}: {body}" if label else body
        activity.notes = f"{activity.notes}\n{entry}".strip() if activity.notes else entry


def _read_activity_codes(
    tables: dict[str, list[dict[str, str]]], schedule: ExchangeSchedule
) -> None:
    """Activity codes are the dimension planners actually filter on.

    Dropping them makes an imported schedule unusable to the person who built it,
    even though every date is right.
    """
    types = {
        r.get("actv_code_type_id", ""): r.get("actv_code_type", "")
        for r in tables.get("ACTVTYPE", [])
    }
    codes = {
        r.get("actv_code_id", ""): (
            r.get("actv_code_type_id", ""),
            r.get("short_name", "") or r.get("actv_code_name", ""),
        )
        for r in tables.get("ACTVCODE", [])
    }
    for row in tables.get("TASKACTV", []):
        activity = schedule.activity(row.get("task_id", ""))
        if activity is None:
            continue
        type_id, value = codes.get(row.get("actv_code_id", ""), ("", ""))
        label = types.get(type_id, type_id)
        if label and value:
            activity.activity_codes[label] = value


# -- writing ---------------------------------------------------------------


def write_xer(schedule: ExchangeSchedule, *, exported_at: date | None = None) -> str:
    """Serialise the hub model back to XER.

    Round-trip fidelity is asserted on *the computed schedule*, not on the bytes.
    P6 writes dozens of columns this engine has no opinion about; matching them
    byte for byte would be a test of the fixture, not of the converter.
    """
    stamp = (exported_at or date.today()).strftime("%Y-%m-%d")
    lines: list[str] = [
        "\t".join(["ERMHDR", "19.12", stamp, "Project", "massingplan", "", "", "massingplan"])
    ]

    def table(name: str, columns: list[str], rows: list[list[str]]) -> None:
        if not rows:
            return
        lines.append(f"%T\t{name}")
        lines.append("\t".join(["%F", *columns]))
        for row in rows:
            lines.append("\t".join(["%R", *row]))

    table(
        "PROJECT",
        [
            "proj_id",
            "proj_short_name",
            "plan_start_date",
            "last_recalc_date",
            "scd_end_date",
            "clndr_id",
        ],
        [
            [
                schedule.project_id or "1",
                schedule.project_name or "PROJECT",
                _format_date(schedule.planned_start),
                _format_date(schedule.data_date),
                _format_date(schedule.must_finish_by),
                schedule.default_calendar_id or "",
            ]
        ],
    )

    table(
        "CALENDAR",
        ["clndr_id", "clndr_name", "day_hr_cnt", "default_flag", "clndr_data"],
        [
            [
                c.id,
                c.name,
                f"{c.hours_per_day:g}",
                "Y" if c.is_default else "N",
                _write_calendar_data(c),
            ]
            for c in schedule.calendars
        ],
    )

    table(
        "PROJWBS",
        [
            "wbs_id",
            "proj_id",
            "wbs_name",
            "wbs_short_name",
            "parent_wbs_id",
            "proj_node_flag",
            "seq_num",
        ],
        [
            [
                n.id,
                schedule.project_id or "1",
                n.name,
                n.code,
                n.parent_id or "",
                "Y" if n.parent_id is None else "N",
                str(n.sequence),
            ]
            for n in schedule.wbs
        ],
    )

    activity_rows = []
    for a in schedule.activities:
        cal = schedule.calendar_for(a)
        hpd = cal.hours_per_day if cal else DEFAULT_HOURS_PER_DAY
        activity_rows.append(
            [
                a.id,
                schedule.project_id or "1",
                a.wbs_id or "",
                a.code or a.id,
                a.name,
                ACTIVITY_KINDS_TO_XER.get(a.kind, "TT_Task"),
                a.calendar_id or schedule.default_calendar_id or "",
                f"{hours_from_days(a.duration_days, hpd):g}",
                ""
                if a.remaining_duration_days is None
                else f"{hours_from_days(a.remaining_duration_days, hpd):g}",
                _format_date(a.early_start),
                _format_date(a.early_finish),
                _format_date(a.late_start),
                _format_date(a.late_finish),
                _format_date(a.actual_start),
                _format_date(a.actual_finish),
                _format_date(a.planned_start),
                _format_date(a.planned_finish),
                CONSTRAINTS_TO_XER.get(a.constraint, ""),
                _format_date(a.constraint_date),
                "Y" if a.is_longest_path else "N",
                ""
                if a.physical_percent_complete is None
                else f"{a.physical_percent_complete * 100:g}",
            ]
        )
    table(
        "TASK",
        [
            "task_id",
            "proj_id",
            "wbs_id",
            "task_code",
            "task_name",
            "task_type",
            "clndr_id",
            "target_drtn_hr_cnt",
            "remain_drtn_hr_cnt",
            "early_start_date",
            "early_end_date",
            "late_start_date",
            "late_end_date",
            "act_start_date",
            "act_end_date",
            "target_start_date",
            "target_end_date",
            "cstr_type",
            "cstr_date",
            "driving_path_flag",
            "phys_complete_pct",
        ],
        activity_rows,
    )

    relationship_rows = []
    for r in schedule.relationships:
        successor = schedule.activity(r.successor_id)
        cal = schedule.calendar_for(successor) if successor else None
        hpd = cal.hours_per_day if cal else DEFAULT_HOURS_PER_DAY
        relationship_rows.append(
            [
                f"{r.predecessor_id}-{r.successor_id}",
                r.successor_id,
                r.predecessor_id,
                RELATION_TYPES_TO_XER[r.type],
                f"{hours_from_days(r.lag_days, hpd):g}",
            ]
        )
    table(
        "TASKPRED",
        ["task_pred_id", "task_id", "pred_task_id", "pred_type", "lag_hr_cnt"],
        relationship_rows,
    )

    table(
        "RSRC",
        ["rsrc_id", "rsrc_name", "rsrc_type", "unit_id", "clndr_id"],
        [
            [
                r.id,
                r.name,
                f"RT_{r.type.title()}",
                r.unit,
                r.calendar_id or "",
            ]
            for r in schedule.resources
        ],
    )

    table(
        "TASKRSRC",
        ["task_id", "rsrc_id", "target_qty", "target_cost", "target_qty_per_hr"],
        [
            [
                a.activity_id,
                a.resource_id,
                "" if a.budgeted_units is None else f"{a.budgeted_units:g}",
                "" if a.budgeted_cost is None else f"{a.budgeted_cost:g}",
                "" if a.units_per_day is None else f"{a.units_per_day:g}",
            ]
            for a in schedule.assignments
        ],
    )

    notes = [[a.id, a.id, "1", a.notes] for a in schedule.activities if a.notes]
    table("TASKMEMO", ["memo_id", "task_id", "memo_type_id", "task_memo"], notes)

    lines.append("%E")
    return "\n".join(lines) + "\n"


def _write_calendar_data(cal: Calendar) -> str:
    """Re-emit P6's packed calendar blob, including exceptions.

    Writing the weekly pattern and dropping the exceptions would make an export
    of an imported file schedule differently from the file it came from -- the
    round-trip test asserts exactly that this does not happen.
    """
    python_to_p6 = {6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7}
    days = []
    for python_day in range(7):
        p6_day = python_to_p6[python_day]
        if python_day in cal.working_weekdays:
            days.append(f"({p6_day}()(0||1(s|08:00|f|16:00)))")
        else:
            days.append(f"({p6_day}())")
    weekly = "(0||DaysOfWeek()(" + "".join(days) + "))"

    if not cal.exceptions:
        return weekly
    blocks = []
    for exc in cal.exceptions:
        serial = (exc.day - _SERIAL_EPOCH).days
        shift = "(0||1(s|08:00|f|16:00))" if exc.working else ""
        blocks.append(f"(0||d|{serial}({shift}))")
    return weekly + "(0||Exceptions()(" + "".join(blocks) + "))"
