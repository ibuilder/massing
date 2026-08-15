"""Primavera P6 XML (PMXML): the format that can carry a series.

XER is what a planner exports for a routine transfer. **It does not carry
baselines.** P6 XML does -- as additional `<Project>` elements in the same
document -- along with the global calendars a restricted XER omits.

That distinction is why this module exists rather than being a nicety beside
`xer.py`. Baseline comparison needs two schedules and windows analysis needs a
*series* of them, so the format a claim actually arrives in is the one that can
hold more than one. Reading XER only means asking for eleven separate files and
hoping every data date survived being exported by hand eleven times.

Shapes verified against real exports
------------------------------------
Every element name and enumeration below was read out of genuine P6 exports,
not recalled. Three of them are traps:

* **`<Type>` is overloaded.** A `<Calendar>` has one (`Global`, `Project`,
  `Resource`), an `<Activity>` has one (`Task Dependent`, `Finish Milestone`),
  a `<Relationship>` has one (`Finish to Start`) and a user-defined field has
  one (`Total Float (In Days)`). They are only distinguishable by parent, so
  nothing here ever searches for `Type` across the document.
* **Durations and lags are hours, not days.** `<PlannedDuration>360.0` is
  forty-five days at eight hours. `<Lag>-32` is a four-day lead.
* **`<PercentComplete>` is a fraction.** A completed activity carries `1.0`,
  where MSPDI would carry `100`. Reading the P6 convention with the MSPDI rule
  turns every finished activity into one percent complete, and the schedule
  still computes -- it just reports a project that has barely started.

Namespaces
----------
Exports vary: some declare a default `xmlns` on `<APIBusinessObjects>`, some
carry only an `xsi:schemaLocation` and leave element names bare. Both are
valid and both are in the wild, so every lookup strips any namespace rather
than matching one. Matching a fixed namespace would read one vendor's export
and silently find no activities in the other's -- an empty schedule, not an
error.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from xml.etree import ElementTree

from .constraints import ConstraintType
from .issues import IssueLog
from .model import (
    Calendar,
    CalendarException,
    ExchangeActivity,
    ExchangeRelationship,
    ExchangeSchedule,
    WBSNode,
)
from .network import ActivityKind, LagCalendar, ProgressMode, RelationType, SchedulerOptions
from .units import days_from_hours
from .xmlsafe import parse as parse_xml
from .xmlsafe import text as xml_text

#: Microsoft and Oracle both spell these; Oracle spells them in English.
P6_RELATION_TYPES = {
    "Finish to Start": RelationType.FS,
    "Start to Start": RelationType.SS,
    "Finish to Finish": RelationType.FF,
    "Start to Finish": RelationType.SF,
}
RELATION_TYPES_TO_P6 = {v: k for k, v in P6_RELATION_TYPES.items()}

P6_ACTIVITY_KINDS = {
    "Task Dependent": ActivityKind.TASK,
    "Resource Dependent": ActivityKind.TASK,
    "Start Milestone": ActivityKind.START_MILESTONE,
    "Finish Milestone": ActivityKind.FINISH_MILESTONE,
    "Level of Effort": ActivityKind.LEVEL_OF_EFFORT,
    "WBS Summary": ActivityKind.WBS_SUMMARY,
}
#: `Resource Dependent` reads as a task and writes back as `Task Dependent`.
#: The distinction is which calendar P6 schedules against, and this engine
#: takes the activity's calendar either way -- so it is a real narrowing, and
#: the writer records it rather than letting it look lossless.
ACTIVITY_KINDS_TO_P6 = {
    ActivityKind.TASK: "Task Dependent",
    ActivityKind.START_MILESTONE: "Start Milestone",
    ActivityKind.FINISH_MILESTONE: "Finish Milestone",
    ActivityKind.LEVEL_OF_EFFORT: "Level of Effort",
    ActivityKind.WBS_SUMMARY: "WBS Summary",
}

P6_CONSTRAINTS = {
    "": ConstraintType.NONE,
    "Start On": ConstraintType.START_ON,
    "Start On or Before": ConstraintType.START_ON_OR_BEFORE,
    "Start On or After": ConstraintType.START_ON_OR_AFTER,
    "Finish On": ConstraintType.FINISH_ON,
    "Finish On or Before": ConstraintType.FINISH_ON_OR_BEFORE,
    "Finish On or After": ConstraintType.FINISH_ON_OR_AFTER,
    "As Late As Possible": ConstraintType.AS_LATE_AS_POSSIBLE,
    "Mandatory Start": ConstraintType.MANDATORY_START,
    "Mandatory Finish": ConstraintType.MANDATORY_FINISH,
}
CONSTRAINTS_TO_P6 = {v: k for k, v in P6_CONSTRAINTS.items() if k}

P6_PROGRESS_MODES = {
    "Retained Logic": ProgressMode.RETAINED_LOGIC,
    "Progress Override": ProgressMode.PROGRESS_OVERRIDE,
    "Actual Dates": ProgressMode.RETAINED_LOGIC,
}
PROGRESS_MODES_TO_P6 = {
    ProgressMode.RETAINED_LOGIC: "Retained Logic",
    ProgressMode.PROGRESS_OVERRIDE: "Progress Override",
}

P6_LAG_CALENDARS = {
    "Predecessor Activity Calendar": LagCalendar.PREDECESSOR,
    "Successor Activity Calendar": LagCalendar.SUCCESSOR,
    "Project Default Calendar": LagCalendar.PROJECT_DEFAULT,
    "24 Hour Calendar": LagCalendar.TWENTY_FOUR_HOUR,
}
LAG_CALENDARS_TO_P6 = {v: k for k, v in P6_LAG_CALENDARS.items()}

WEEKDAYS = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}
WEEKDAY_NAMES = {v: k for k, v in WEEKDAYS.items()}

DEFAULT_HOURS_PER_DAY = 8.0
NAMESPACE = "http://xmlns.oracle.com/Primavera/P6/V18.1/API/BusinessObjects"


class P6XMLError(ValueError):
    """The document is not a P6 XML file, or is too damaged to read."""


def _tag(element: ElementTree.Element) -> str:
    """The element's local name, with any namespace stripped."""
    return element.tag.rsplit("}", 1)[-1]


def _children(parent: ElementTree.Element, name: str) -> Iterator[ElementTree.Element]:
    """Direct children with this local name.

    Direct, never a descendant search: `<Type>` means four different things in
    this format and only its parent says which.
    """
    for child in parent:
        if _tag(child) == name:
            yield child


def _text(parent: ElementTree.Element, name: str) -> str | None:
    for child in _children(parent, name):
        return (child.text or "").strip() or None
    return None


def _number(parent: ElementTree.Element, name: str) -> float | None:
    raw = _text(parent, name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _date(parent: ElementTree.Element, name: str) -> date | None:
    """A P6 timestamp as a date.

    P6 writes `2021-05-17T22:00:00`. The time is the shift boundary, not a fact
    about which day the work happened on, so it is dropped -- this engine's
    axis is whole days and keeping the time would invite a comparison between a
    date and a datetime that raises much later, somewhere else.
    """
    raw = _text(parent, name)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _percent(value: float | None) -> float | None:
    """P6 percent complete, as a percentage.

    The file holds a **fraction**: a completed activity is `1.0`, not `100`.
    This engine stores percentages, so it is scaled here -- once, at the edge.
    """
    if value is None:
        return None
    return max(0.0, min(100.0, value * 100.0))


def _hours_per_day(root: ElementTree.Element) -> float:
    for calendar in _iter_calendars(root):
        hours = _number(calendar, "HoursPerDay")
        if hours and hours > 0:
            return hours
    return DEFAULT_HOURS_PER_DAY


def _iter_calendars(root: ElementTree.Element) -> Iterator[ElementTree.Element]:
    """Calendars, wherever the export put them.

    Global calendars sit at the document root; project calendars sit inside
    their `<Project>`. An export may use either or both, so both are read.
    """
    yield from _children(root, "Calendar")
    for project in _children(root, "Project"):
        yield from _children(project, "Calendar")


def _read_calendar(element: ElementTree.Element, issues: IssueLog) -> Calendar:
    cal_id = _text(element, "ObjectId") or _text(element, "Name") or "CAL"
    name = _text(element, "Name") or cal_id
    hours = _number(element, "HoursPerDay") or DEFAULT_HOURS_PER_DAY

    working: set[int] = set()
    for week in _children(element, "StandardWorkWeek"):
        for day in _children(week, "StandardWorkHours"):
            label = _text(day, "DayOfWeek")
            if label is None:
                continue
            index = WEEKDAYS.get(label)
            if index is None:
                issues.warn(
                    "P6XML.CALENDAR.UNKNOWN_DAY",
                    f"calendar {name}: unrecognised day {label!r}",
                    "the day is dropped from the working week",
                    row_key=cal_id,
                    field_name="DayOfWeek",
                    raw_value=label,
                )
                continue
            # A day with no `<WorkTime>` is a non-working day. That is how P6
            # writes a weekend -- the element is present and empty, not absent
            # -- so presence alone cannot be the test.
            if any(True for _ in _children(day, "WorkTime")):
                working.add(index)

    if not working:
        issues.warn(
            "P6XML.CALENDAR.NO_WORKING_DAYS",
            f"calendar {name} declares no working day",
            "defaulted to Monday-Friday; every date computed against it would "
            "otherwise be unreachable",
            row_key=cal_id,
        )
        working = {0, 1, 2, 3, 4}

    calendar = Calendar(
        id=cal_id,
        name=name,
        working_weekdays=set(working),
        hours_per_day=hours,
    )
    for holder in _children(element, "HolidayOrExceptions"):
        for exception in _children(holder, "HolidayOrException"):
            when = _date(exception, "Date")
            if when is None:
                continue
            # Same rule as the working week: an exception with work time on it
            # is an added working day, one without is a holiday.
            works = any(True for _ in _children(exception, "WorkTime"))
            calendar.exceptions.append(
                CalendarException(day=when, working=works, name="P6 exception")
            )
    return calendar


def _read_activity(
    element: ElementTree.Element,
    hours_per_day: float,
    issues: IssueLog,
) -> ExchangeActivity:
    object_id = _text(element, "ObjectId") or ""
    code = _text(element, "Id") or object_id
    name = _text(element, "Name") or code

    raw_kind = _text(element, "Type") or "Task Dependent"
    kind = P6_ACTIVITY_KINDS.get(raw_kind)
    if kind is None:
        kind = ActivityKind.TASK
        issues.warn(
            "P6XML.ACTIVITY.UNKNOWN_TYPE",
            f"activity {code}: unrecognised type {raw_kind!r}",
            "imported as a task, which schedules against its own calendar",
            row_key=code,
            field_name="Type",
            raw_value=raw_kind,
        )

    raw_constraint = _text(element, "PrimaryConstraintType") or ""
    constraint = P6_CONSTRAINTS.get(raw_constraint)
    if constraint is None:
        constraint = ConstraintType.NONE
        issues.warn(
            "P6XML.ACTIVITY.UNKNOWN_CONSTRAINT",
            f"activity {code}: unrecognised constraint {raw_constraint!r}",
            "constraint dropped; the activity floats on its logic alone",
            row_key=code,
            field_name="PrimaryConstraintType",
            raw_value=raw_constraint,
        )
    constraint_date = _date(element, "PrimaryConstraintDate")
    if constraint.needs_date and constraint_date is None:
        issues.warn(
            "P6XML.ACTIVITY.CONSTRAINT_WITHOUT_DATE",
            f"activity {code}: {raw_constraint} with no date",
            "constraint dropped rather than applied against a guessed date",
            row_key=code,
            field_name="PrimaryConstraintDate",
        )
        constraint = ConstraintType.NONE

    planned = _number(element, "PlannedDuration")
    remaining = _number(element, "RemainingDuration")
    duration = days_from_hours(planned, hours_per_day) if planned is not None else 0
    if kind.is_milestone:
        # A milestone with a duration is rejected by the model, and P6 files do
        # carry a nonzero PlannedDuration on one often enough to matter. The
        # kind is the stronger statement: a Finish Milestone is a point in time
        # whatever hours got written beside it.
        duration = 0

    return ExchangeActivity(
        id=code,
        code=code,
        name=name,
        kind=kind,
        calendar_id=_text(element, "CalendarObjectId"),
        duration_days=duration,
        remaining_duration_days=(
            None if remaining is None else days_from_hours(remaining, hours_per_day)
        ),
        actual_start=_date(element, "ActualStartDate"),
        actual_finish=_date(element, "ActualFinishDate"),
        # All three, because the model prefers physical and falls back to
        # duration, and squashing them here would make that choice unavailable.
        duration_percent_complete=_percent(
            _number(element, "DurationPercentComplete")
            if _number(element, "DurationPercentComplete") is not None
            else _number(element, "PercentComplete")
        ),
        physical_percent_complete=_percent(_number(element, "PhysicalPercentComplete")),
        constraint=constraint,
        constraint_date=constraint_date,
        wbs_id=_text(element, "WBSObjectId"),
    )


def _read_options(project: ElementTree.Element, issues: IssueLog) -> SchedulerOptions:
    """P6's own scheduling options, which this engine has equivalents for.

    Taking the defaults instead would compute a different schedule from the one
    the file's author saw, without saying so -- retained logic and progress
    override give genuinely different finishes on a project with out-of-sequence
    progress.
    """
    options = SchedulerOptions()
    raw_mode = _text(project, "OutOfSequenceScheduleType")
    if raw_mode:
        mode = P6_PROGRESS_MODES.get(raw_mode)
        if mode is None:
            issues.warn(
                "P6XML.PROJECT.UNKNOWN_PROGRESS_MODE",
                f"unrecognised out-of-sequence type {raw_mode!r}",
                f"defaulted to {options.progress_mode.value}",
                field_name="OutOfSequenceScheduleType",
                raw_value=raw_mode,
            )
        else:
            options = SchedulerOptions(
                progress_mode=mode,
                lag_calendar=options.lag_calendar,
                open_ends_are_critical=options.open_ends_are_critical,
            )

    raw_lag = _text(project, "RelationshipLagCalendar")
    if raw_lag:
        lag = P6_LAG_CALENDARS.get(raw_lag)
        if lag is None:
            issues.warn(
                "P6XML.PROJECT.UNKNOWN_LAG_CALENDAR",
                f"unrecognised lag calendar {raw_lag!r}",
                f"defaulted to {options.lag_calendar.value}; a lag is n working "
                "days in *some* calendar and the choice moves dates",
                field_name="RelationshipLagCalendar",
                raw_value=raw_lag,
            )
        else:
            options = SchedulerOptions(
                progress_mode=options.progress_mode,
                lag_calendar=lag,
                open_ends_are_critical=options.open_ends_are_critical,
            )

    open_ends = _text(project, "MakeOpenEndedActivitiesCritical")
    if open_ends is not None:
        options = SchedulerOptions(
            progress_mode=options.progress_mode,
            lag_calendar=options.lag_calendar,
            open_ends_are_critical=open_ends in ("1", "true", "True"),
        )
    return options


def _read_project(
    project: ElementTree.Element,
    calendars: list[Calendar],
    hours_per_day: float,
) -> ExchangeSchedule:
    issues = IssueLog()
    schedule = ExchangeSchedule(
        project_id=_text(project, "Id") or _text(project, "ObjectId") or "",
        project_name=_text(project, "Name") or "",
        data_date=_date(project, "DataDate"),
        planned_start=_date(project, "PlannedStartDate") or _date(project, "StartDate"),
        must_finish_by=_date(project, "MustFinishByDate"),
        calendars=list(calendars),
        source_format="p6xml",
    )
    schedule.options = _read_options(project, issues)

    for node in _children(project, "WBS"):
        schedule.wbs.append(
            WBSNode(
                id=_text(node, "ObjectId") or "",
                code=_text(node, "Code") or "",
                name=_text(node, "Name") or "",
                parent_id=_text(node, "ParentObjectId"),
            )
        )

    # ObjectId to activity code: relationships reference the numeric ObjectId,
    # and every id this engine reports is the code a planner recognises.
    by_object_id: dict[str, str] = {}
    for element in _children(project, "Activity"):
        activity = _read_activity(element, hours_per_day, issues)
        object_id = _text(element, "ObjectId")
        if object_id:
            by_object_id[object_id] = activity.id
        schedule.activities.append(activity)

    known = {a.id for a in schedule.activities}
    for element in _children(project, "Relationship"):
        raw_type = _text(element, "Type") or "Finish to Start"
        relation = P6_RELATION_TYPES.get(raw_type)
        if relation is None:
            relation = RelationType.FS
            issues.warn(
                "P6XML.RELATIONSHIP.UNKNOWN_TYPE",
                f"unrecognised relationship type {raw_type!r}",
                "imported as Finish-to-Start, which is the safe reading: it "
                "constrains more than the alternatives, so no date moves earlier",
                field_name="Type",
                raw_value=raw_type,
            )
        pred_object = _text(element, "PredecessorActivityObjectId") or ""
        succ_object = _text(element, "SuccessorActivityObjectId") or ""
        predecessor = by_object_id.get(pred_object)
        successor = by_object_id.get(succ_object)
        if predecessor is None or successor is None:
            # External relationships are real: P6 links across projects and the
            # other end is simply not in this file. Dropping it silently would
            # remove a constraint and pull dates earlier with nothing to show
            # for it.
            issues.warn(
                "P6XML.RELATIONSHIP.EXTERNAL",
                f"relationship {pred_object} -> {succ_object} points outside this project",
                "dropped; export the other project too, or the link's constraint "
                "is missing and the dates may compute early",
                field_name="PredecessorActivityObjectId",
                raw_value=f"{pred_object}->{succ_object}",
            )
            continue
        if predecessor not in known or successor not in known:  # pragma: no cover - defensive
            continue
        lag_hours = _number(element, "Lag") or 0.0
        schedule.relationships.append(
            ExchangeRelationship(
                predecessor_id=predecessor,
                successor_id=successor,
                type=relation,
                lag_days=days_from_hours(abs(lag_hours), hours_per_day)
                * (-1 if lag_hours < 0 else 1),
            )
        )

    if calendars and not schedule.default_calendar_id:
        default = _text(project, "ActivityDefaultCalendarObjectId")
        schedule.default_calendar_id = default or calendars[0].id

    schedule.issues.extend(issues)
    return schedule


def read_p6xml_all(content: str) -> list[ExchangeSchedule]:
    """Every project in the document, in file order.

    **This is the entry point that makes P6 XML worth having.** An export with
    baselines carries them as additional `<Project>` elements, so a file that
    XER would have needed four separate exports for arrives as one list -- and
    a windows analysis can be run on it without anybody hand-collating four
    files and their data dates.
    """
    try:
        root = parse_xml(content)
    except ElementTree.ParseError as exc:
        raise P6XMLError(f"not well-formed XML: {exc}") from exc
    except ValueError as exc:
        raise P6XMLError(str(exc)) from exc

    if _tag(root) != "APIBusinessObjects":
        raise P6XMLError(
            f"expected an <APIBusinessObjects> document, got <{_tag(root)}>. "
            "P6 XML is not the same format as MS Project XML"
        )

    shared = IssueLog()
    hours_per_day = _hours_per_day(root)
    calendars = [_read_calendar(element, shared) for element in _iter_calendars(root)]

    schedules: list[ExchangeSchedule] = []
    for project in _children(root, "Project"):
        # Two different empties, guarded two different ways, and it is worth
        # being precise about which does what:
        #
        # This guard covers both empties: a `<ProjectList>` stub -- an id and a
        # name, no activities, an index of the file rather than a schedule --
        # and a top-level `<Project>` that genuinely has nothing in it. The
        # stub is also out of reach because `_children` never descends, but
        # that is belt to this braces; the activity check does the work.
        #
        # Either way an empty schedule imports without an error and analyses to
        # nothing, which is the failure this codebase treats as the expensive one.
        if not any(True for _ in _children(project, "Activity")):
            continue
        schedule = _read_project(project, calendars, hours_per_day)
        schedule.issues.extend(shared)
        schedules.append(schedule)

    if not schedules:
        raise P6XMLError(
            "the document contains no project with activities. A <ProjectList> "
            "entry is an index of the file, not a schedule"
        )
    return schedules


def read_p6xml(content: str, *, project_id: str | None = None) -> ExchangeSchedule:
    """One project from a P6 XML document.

    With no `project_id`, the first project carrying activities. When the file
    holds more than one -- a project and its baselines -- that is recorded as
    an issue rather than passed over, because silently reading one of four is
    how somebody analyses the wrong schedule.
    """
    schedules = read_p6xml_all(content)
    if project_id is not None:
        for schedule in schedules:
            if schedule.project_id == project_id:
                return schedule
        raise P6XMLError(
            f"no project {project_id!r} in this document; it holds "
            f"{[s.project_id for s in schedules]}"
        )

    chosen = schedules[0]
    if len(schedules) > 1:
        others = [s.project_id for s in schedules[1:]]
        chosen.issues.warn(
            "P6XML.MULTIPLE_PROJECTS",
            f"the document holds {len(schedules)} projects; read {chosen.project_id!r}",
            f"the others ({others}) are most likely baselines. Use read_p6xml_all "
            "to get every one, which is what a windows analysis needs",
        )
    return chosen


def _iso(value: date | None, *, end_of_day: bool = False) -> str:
    if value is None:
        return ""
    return f"{value.isoformat()}T{'17:00:00' if end_of_day else '08:00:00'}"


def write_p6xml(schedule: ExchangeSchedule, *, exported_at: date | None = None) -> str:
    """A P6 XML document carrying this schedule.

    Written with the default namespace declared, which is the more common of
    the two forms in the wild and the one P6 itself emits.
    """
    from xml.sax.saxutils import escape as _escape

    def escape(value: str) -> str:
        """Escape what changes meaning, and remove what XML cannot carry.

        `saxutils.escape` handles `&`, `<` and `>`. It says nothing about the
        C0 controls XML 1.0 forbids outright, and a name containing one
        produced an export no parser would open -- P6's included.
        """
        return _escape(xml_text(value))

    hours_per_day = DEFAULT_HOURS_PER_DAY
    default_calendar = schedule.default_calendar()
    if default_calendar and default_calendar.hours_per_day:
        hours_per_day = default_calendar.hours_per_day

    out: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append(f'<APIBusinessObjects xmlns="{NAMESPACE}">')

    for calendar in schedule.calendars:
        out.append("  <Calendar>")
        out.append(f"    <ObjectId>{escape(calendar.id)}</ObjectId>")
        out.append(f"    <Name>{escape(calendar.name or calendar.id)}</Name>")
        out.append("    <Type>Global</Type>")
        out.append(f"    <HoursPerDay>{calendar.hours_per_day or hours_per_day}</HoursPerDay>")
        out.append("    <StandardWorkWeek>")
        for index in range(7):
            out.append("      <StandardWorkHours>")
            out.append(f"        <DayOfWeek>{WEEKDAY_NAMES[index]}</DayOfWeek>")
            # A working day carries a `<WorkTime>`; a non-working day carries
            # the element with nothing in it. Omitting the day entirely is not
            # the same statement and P6 does not do it.
            if index in calendar.working_weekdays:
                out.append("        <WorkTime>")
                out.append("          <Start>08:00:00</Start>")
                out.append("          <Finish>17:00:00</Finish>")
                out.append("        </WorkTime>")
            out.append("      </StandardWorkHours>")
        out.append("    </StandardWorkWeek>")
        out.append("    <HolidayOrExceptions>")
        for exception in calendar.exceptions:
            out.append("      <HolidayOrException>")
            out.append(f"        <Date>{_iso(exception.day)}</Date>")
            if exception.working:
                out.append("        <WorkTime>")
                out.append("          <Start>08:00:00</Start>")
                out.append("          <Finish>17:00:00</Finish>")
                out.append("        </WorkTime>")
            out.append("      </HolidayOrException>")
        out.append("    </HolidayOrExceptions>")
        out.append("  </Calendar>")

    out.append("  <Project>")
    out.append(f"    <ObjectId>{escape(schedule.project_id or 'PROJ')}</ObjectId>")
    out.append(f"    <Id>{escape(schedule.project_id or 'PROJ')}</Id>")
    out.append(f"    <Name>{escape(schedule.project_name or schedule.project_id)}</Name>")
    if schedule.data_date:
        out.append(f"    <DataDate>{_iso(schedule.data_date)}</DataDate>")
    if schedule.planned_start:
        out.append(f"    <PlannedStartDate>{_iso(schedule.planned_start)}</PlannedStartDate>")
    if schedule.must_finish_by:
        out.append(f"    <MustFinishByDate>{_iso(schedule.must_finish_by)}</MustFinishByDate>")
    if schedule.default_calendar_id:
        out.append(
            "    <ActivityDefaultCalendarObjectId>"
            f"{escape(schedule.default_calendar_id)}"
            "</ActivityDefaultCalendarObjectId>"
        )
    mode = PROGRESS_MODES_TO_P6.get(schedule.options.progress_mode, "Retained Logic")
    out.append(f"    <OutOfSequenceScheduleType>{mode}</OutOfSequenceScheduleType>")
    lag = LAG_CALENDARS_TO_P6.get(schedule.options.lag_calendar, "Predecessor Activity Calendar")
    out.append(f"    <RelationshipLagCalendar>{lag}</RelationshipLagCalendar>")
    out.append(
        "    <MakeOpenEndedActivitiesCritical>"
        f"{'1' if schedule.options.open_ends_are_critical else '0'}"
        "</MakeOpenEndedActivitiesCritical>"
    )

    for node in schedule.wbs:
        out.append("    <WBS>")
        out.append(f"      <ObjectId>{escape(node.id)}</ObjectId>")
        out.append(f"      <Code>{escape(node.code)}</Code>")
        out.append(f"      <Name>{escape(node.name)}</Name>")
        if node.parent_id:
            out.append(f"      <ParentObjectId>{escape(node.parent_id)}</ParentObjectId>")
        out.append("    </WBS>")

    for activity in schedule.activities:
        out.append("    <Activity>")
        # The activity code is written as the ObjectId as well, so a relationship
        # can reference it without a second identity to keep consistent. P6's
        # own numeric ObjectIds are meaningless outside their database.
        out.append(f"      <ObjectId>{escape(activity.id)}</ObjectId>")
        out.append(f"      <Id>{escape(activity.id)}</Id>")
        out.append(f"      <Name>{escape(activity.name or activity.id)}</Name>")
        out.append(f"      <Type>{ACTIVITY_KINDS_TO_P6[activity.kind]}</Type>")
        if activity.calendar_id:
            out.append(f"      <CalendarObjectId>{escape(activity.calendar_id)}</CalendarObjectId>")
        out.append(
            f"      <PlannedDuration>{activity.duration_days * hours_per_day:.1f}</PlannedDuration>"
        )
        if activity.remaining_duration_days is not None:
            out.append(
                f"      <RemainingDuration>"
                f"{activity.remaining_duration_days * hours_per_day:.1f}"
                "</RemainingDuration>"
            )
        if activity.actual_start:
            out.append(f"      <ActualStartDate>{_iso(activity.actual_start)}</ActualStartDate>")
        if activity.actual_finish:
            out.append(
                f"      <ActualFinishDate>{_iso(activity.actual_finish, end_of_day=True)}"
                "</ActualFinishDate>"
            )
        if activity.percent_complete is not None:
            # Back to a fraction, which is what the format holds.
            out.append(
                f"      <PercentComplete>{activity.percent_complete / 100.0:.4f}</PercentComplete>"
            )
        constraint = CONSTRAINTS_TO_P6.get(activity.constraint)
        if constraint:
            out.append(f"      <PrimaryConstraintType>{constraint}</PrimaryConstraintType>")
            if activity.constraint_date:
                out.append(
                    f"      <PrimaryConstraintDate>{_iso(activity.constraint_date)}"
                    "</PrimaryConstraintDate>"
                )
        else:
            out.append("      <PrimaryConstraintType/>")
        if activity.wbs_id:
            out.append(f"      <WBSObjectId>{escape(activity.wbs_id)}</WBSObjectId>")
        out.append("    </Activity>")

    for relationship in schedule.relationships:
        out.append("    <Relationship>")
        out.append(
            f"      <PredecessorActivityObjectId>{escape(relationship.predecessor_id)}"
            "</PredecessorActivityObjectId>"
        )
        out.append(
            f"      <SuccessorActivityObjectId>{escape(relationship.successor_id)}"
            "</SuccessorActivityObjectId>"
        )
        out.append(f"      <Type>{RELATION_TYPES_TO_P6[relationship.type]}</Type>")
        out.append(f"      <Lag>{relationship.lag_days * hours_per_day:.1f}</Lag>")
        out.append("    </Relationship>")

    out.append("  </Project>")
    out.append("</APIBusinessObjects>")
    return "\n".join(out) + "\n"


__all__ = [
    "P6XMLError",
    "read_p6xml",
    "read_p6xml_all",
    "write_p6xml",
]
