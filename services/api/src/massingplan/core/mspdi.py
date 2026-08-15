"""Reading and writing Microsoft Project XML (MSPDI).

MSPDI is the documented interchange format for MS Project. Binary ``.mpp`` is
proprietary and undocumented; this engine does not attempt to write it, and says
so rather than producing something that almost opens.

Three traps, each of which produces a plausible wrong answer rather than an
error:

* **Durations are ISO-8601.** ``PT40H0M0S`` is forty hours, which is five days
  at eight hours or four at ten. Parsing the leading digits gives 40 days.
* **Link ``Type`` is an integer, and the ordering is not alphabetical.**
  ``0=FF, 1=FS, 2=SF, 3=SS``. Guessing alphabetically maps every SS to FF and
  every FF to SS -- a schedule that computes cleanly and is wrong.
* **``UID`` is not ``ID``.** ``ID`` is the visible outline row number and is
  reassigned when tasks move; ``UID`` is stable and is what relationships
  reference. Keying on ``ID`` silently re-points relationships after any reorder.

Ported from ibuilder/AIHackScheduler ``core/mspdi.py`` (MIT), extended with
calendar exceptions, remaining duration, actuals and the status date.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from xml.etree import ElementTree

from .constraints import ConstraintType
from .model import (
    Calendar,
    CalendarException,
    ExchangeActivity,
    ExchangeRelationship,
    ExchangeSchedule,
)
from .network import ActivityKind, RelationType
from .units import days_from_hours, hours_from_days
from .xmlsafe import parse as parse_xml
from .xmlsafe import text as xml_text

MSPDI_NS = "http://schemas.microsoft.com/project"

# Deliberately not alphabetical. This is Microsoft's ordering, and writing it
# out as a literal table is the only way to keep it from being "tidied".
MSPDI_LINK_TYPES = {
    0: RelationType.FF,
    1: RelationType.FS,
    2: RelationType.SF,
    3: RelationType.SS,
}
LINK_TYPES_TO_MSPDI = {v: k for k, v in MSPDI_LINK_TYPES.items()}

# Microsoft's ConstraintType codes, in Microsoft's order. 2 and 3 are the
# two-sided "Must Start On" / "Must Finish On"; 4-7 are the one-sided
# no-earlier/no-later pairs. Reading 2 as a one-sided floor -- which this table
# did -- is not a rounding of the semantics, it is a different constraint: a
# two-sided pin fixes the late date as well, so dropping the late half leaves
# the early dates identical and silently *invents float*. Nothing moves, no
# violation is raised, and the activity reports slack it does not have.
#
# The same slip made 3 and 6 both mean FINISH_ON_OR_AFTER, so no MSPDI file
# could ever produce a FINISH_ON however it was written.
MSPDI_CONSTRAINTS = {
    0: ConstraintType.NONE,  # As Soon As Possible
    1: ConstraintType.AS_LATE_AS_POSSIBLE,
    2: ConstraintType.START_ON,  # Must Start On
    3: ConstraintType.FINISH_ON,  # Must Finish On
    4: ConstraintType.START_ON_OR_AFTER,  # Start No Earlier Than
    5: ConstraintType.START_ON_OR_BEFORE,  # Start No Later Than
    6: ConstraintType.FINISH_ON_OR_AFTER,  # Finish No Earlier Than
    7: ConstraintType.FINISH_ON_OR_BEFORE,  # Finish No Later Than
}
# MS Project has no constraint that overrides network logic, so P6's two
# mandatory types cannot survive the trip. They are written as the two-sided
# pin -- the closest thing the format has -- rather than as a one-sided floor,
# and the writer records the downgrade as an issue.
#
# The choice of *which* way to degrade matters. As START_ON the date stays
# pinned and a conflict with the logic shows up where this engine always puts
# it: negative float and a violation record. As START_ON_OR_AFTER the late
# half is gone and the conflict shows up nowhere at all.
CONSTRAINTS_TO_MSPDI = {
    ConstraintType.NONE: 0,
    ConstraintType.AS_LATE_AS_POSSIBLE: 1,
    ConstraintType.START_ON: 2,
    ConstraintType.FINISH_ON: 3,
    ConstraintType.START_ON_OR_AFTER: 4,
    ConstraintType.START_ON_OR_BEFORE: 5,
    ConstraintType.FINISH_ON_OR_AFTER: 6,
    ConstraintType.FINISH_ON_OR_BEFORE: 7,
    ConstraintType.MANDATORY_START: 2,
    ConstraintType.MANDATORY_FINISH: 3,
}
#: Written as something weaker than they are, and said so on the way out.
_MANDATORY = {ConstraintType.MANDATORY_START, ConstraintType.MANDATORY_FINISH}

_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>[\d.]+)S)?)?$"
)

DEFAULT_HOURS_PER_DAY = 8.0


class MSPDIError(ValueError):
    """The document could not be read as MSPDI."""


# -- namespace-tolerant helpers -------------------------------------------
# MS Project writes the namespace; hand-edited and third-party files often do
# not. Refusing the bare form would reject half the files people actually have.


def _tag(name: str) -> str:
    return f"{{{MSPDI_NS}}}{name}"


def _find(parent: ElementTree.Element, name: str) -> ElementTree.Element | None:
    found = parent.find(_tag(name))
    return found if found is not None else parent.find(name)


def _children(parent: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    found = parent.findall(_tag(name))
    return found if found else parent.findall(name)


def _text(parent: ElementTree.Element, name: str) -> str | None:
    node = _find(parent, name)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _int(parent: ElementTree.Element, name: str) -> int | None:
    raw = _text(parent, name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _bool(parent: ElementTree.Element, name: str) -> bool:
    return (_text(parent, name) or "").strip() in ("1", "true", "True")


def _date(parent: ElementTree.Element, name: str) -> date | None:
    raw = _text(parent, name)
    if not raw:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    return None


def parse_duration_hours(value: str | None) -> float | None:
    """``PT40H0M0S`` -> 40.0. Returns ``None`` when the text is not a duration."""
    if not value:
        return None
    match = _DURATION_PATTERN.match(value.strip())
    if not match:
        return None
    parts = match.groupdict()
    # A leading `nD` in MSPDI means n *elapsed* days, which MS Project writes as
    # 24-hour periods. It is rare, and treating it as working days would silently
    # triple a duration on an 8-hour calendar.
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = float(parts["seconds"] or 0)
    return days * 24 + hours + minutes / 60 + seconds / 3600


def format_duration_hours(hours: float) -> str:
    whole = int(hours)
    minutes = round((hours - whole) * 60)
    return f"PT{whole}H{minutes}M0S"


# -- reading ---------------------------------------------------------------


def read_mspdi(content: str) -> ExchangeSchedule:
    """Read an MSPDI document into the hub model."""
    # This used to call `ElementTree.fromstring` directly, under a note saying
    # the application layer hardened untrusted uploads. It does not: the only
    # control there is a byte limit, and a billion-laughs payload is a few
    # hundred bytes. See `xmlsafe` for the measurement.
    try:
        root = parse_xml(content)
    except ElementTree.ParseError as exc:
        raise MSPDIError(f"not well-formed XML: {exc}") from exc
    except ValueError as exc:
        raise MSPDIError(str(exc)) from exc

    schedule = ExchangeSchedule(source_format="mspdi")
    issues = schedule.issues

    schedule.project_id = _text(root, "UID") or ""
    schedule.project_name = _text(root, "Name") or _text(root, "Title") or ""
    schedule.planned_start = _date(root, "StartDate")
    # StatusDate is MS Project's data date. Without it a progressed schedule
    # reschedules from its planned start and reports completed work as pending.
    schedule.data_date = _date(root, "StatusDate") or schedule.planned_start
    schedule.must_finish_by = _date(root, "FinishDate")

    hours_per_day = DEFAULT_HOURS_PER_DAY
    minutes = _int(root, "MinutesPerDay")
    if minutes:
        hours_per_day = minutes / 60

    _read_calendars(root, schedule, hours_per_day)
    _read_tasks(root, schedule, hours_per_day)
    _read_links(root, schedule, hours_per_day)

    if not schedule.relationships and len(schedule.activities) > 1:
        issues.warn(
            "MSPDI.LINKS.MISSING",
            "no PredecessorLink elements were found",
            "imported activities with no logic; every activity will read as "
            "critical with zero float",
        )
    return schedule


def _read_calendars(
    root: ElementTree.Element, schedule: ExchangeSchedule, hours_per_day: float
) -> None:
    container = _find(root, "Calendars")
    if container is None:
        schedule.calendars.append(
            Calendar("1", "Standard", {0, 1, 2, 3, 4}, hours_per_day=hours_per_day, is_default=True)
        )
        schedule.default_calendar_id = "1"
        schedule.issues.warn(
            "MSPDI.CALENDAR.MISSING",
            "the document contains no Calendars element",
            "assumed a standard 5-day week",
        )
        return

    default_uid = _text(root, "CalendarUID")
    for node in _children(container, "Calendar"):
        uid = _text(node, "UID") or ""
        if not uid:
            continue
        working: set[int] = set()
        exceptions: list[CalendarException] = []

        weekdays = _find(node, "WeekDays")
        if weekdays is not None:
            for day in _children(weekdays, "WeekDay"):
                day_type = _int(day, "DayType")
                is_working = _bool(day, "DayWorking")
                if day_type is not None and 1 <= day_type <= 7:
                    # MS Project numbers Sunday=1..Saturday=7.
                    python_day = (day_type + 5) % 7
                    if is_working:
                        working.add(python_day)
                    continue
                # DayType 0 means "this is an exception, see TimePeriod".
                period = _find(day, "TimePeriod")
                if period is None:
                    continue
                from_date = _date(period, "FromDate")
                to_date = _date(period, "ToDate") or from_date
                if from_date is None or to_date is None:
                    continue
                if (to_date - from_date).days > 366:
                    schedule.issues.warn(
                        "MSPDI.CALENDAR.EXCEPTION_TOO_LONG",
                        f"calendar {uid}: exception spans {(to_date - from_date).days} days",
                        "exception dropped",
                        row_key=uid,
                    )
                    continue
                import datetime as _dt

                cursor = from_date
                while cursor <= to_date:
                    exceptions.append(CalendarException(cursor, working=is_working))
                    cursor += _dt.timedelta(days=1)

        if not working:
            working = {0, 1, 2, 3, 4}

        cal = Calendar(
            id=uid,
            name=_text(node, "Name") or uid,
            working_weekdays=working,
            exceptions=exceptions,
            hours_per_day=hours_per_day,
            is_default=(uid == default_uid),
        )
        schedule.calendars.append(cal)

    if not schedule.calendars:
        schedule.calendars.append(
            Calendar("1", "Standard", {0, 1, 2, 3, 4}, hours_per_day=hours_per_day, is_default=True)
        )
    default = next((c for c in schedule.calendars if c.is_default), schedule.calendars[0])
    schedule.default_calendar_id = default.id


def _read_tasks(
    root: ElementTree.Element, schedule: ExchangeSchedule, hours_per_day: float
) -> None:
    container = _find(root, "Tasks")
    if container is None:
        schedule.issues.warn(
            "MSPDI.TASKS.MISSING", "the document contains no Tasks element", "nothing imported"
        )
        return

    for node in _children(container, "Task"):
        # UID, not ID. ID is the visible outline row and is reassigned on any
        # reorder; UID is what PredecessorLink references.
        uid = _text(node, "UID")
        if uid is None or uid == "0":
            # UID 0 is the project summary row, not an activity.
            continue

        cal_id = _text(node, "CalendarUID") or schedule.default_calendar_id
        cal = schedule.calendar(cal_id)
        hpd = cal.hours_per_day if cal else hours_per_day

        is_milestone = _bool(node, "Milestone")
        is_summary = _bool(node, "Summary")
        duration_hours = parse_duration_hours(_text(node, "Duration"))
        if duration_hours is None and _text(node, "Duration"):
            schedule.issues.warn(
                "MSPDI.TASK.BAD_DURATION",
                f"task {uid}: could not parse duration {_text(node, 'Duration')!r}",
                "treated as zero",
                row_key=uid,
                field_name="Duration",
                raw_value=_text(node, "Duration"),
            )
        duration = days_from_hours(duration_hours, hpd)

        if is_summary:
            kind = ActivityKind.WBS_SUMMARY
        elif is_milestone or duration == 0:
            # START_MILESTONE, not FINISH_MILESTONE, and the difference is a
            # day on every milestone in the file.
            #
            # MSPDI has one boolean, `<Milestone>`. It cannot say which of
            # P6's `TT_Mile` and `TT_FinMile` it means, and MS Project has no
            # such distinction to express: a milestone there simply *is* its
            # date. `_present` shows a start milestone at its own date and
            # snaps a *finish* milestone back to the previous working day --
            # deliberately, because a P6 finish milestone marks the work
            # before the boundary it sits on.
            #
            # Reading every MSPDI milestone as a finish milestone therefore
            # displayed genuine MS Project files a day early, and made a start
            # milestone drift one day earlier on every export-and-reimport.
            # XER carries the distinction in both directions; MSPDI cannot,
            # so it reads as the kind whose presentation matches what the file
            # actually says.
            kind = ActivityKind.START_MILESTONE if is_milestone else ActivityKind.TASK
        else:
            kind = ActivityKind.TASK
        if kind.is_milestone:
            duration = 0

        remaining_hours = parse_duration_hours(_text(node, "RemainingDuration"))
        remaining = None if remaining_hours is None else days_from_hours(remaining_hours, hpd)
        if kind.is_milestone and remaining is not None:
            remaining = 0

        raw_constraint = _int(node, "ConstraintType")
        constraint = MSPDI_CONSTRAINTS.get(raw_constraint or 0, ConstraintType.NONE)
        if raw_constraint is not None and raw_constraint not in MSPDI_CONSTRAINTS:
            schedule.issues.warn(
                "MSPDI.TASK.UNKNOWN_CONSTRAINT",
                f"task {uid}: ConstraintType {raw_constraint}",
                "constraint dropped",
                row_key=uid,
                field_name="ConstraintType",
                raw_value=raw_constraint,
            )
        constraint_date = _date(node, "ConstraintDate")
        if constraint.needs_date and constraint_date is None:
            constraint = ConstraintType.NONE

        percent = _int(node, "PhysicalPercentComplete")
        duration_percent = _int(node, "PercentComplete")

        schedule.activities.append(
            ExchangeActivity(
                id=uid,
                name=_text(node, "Name") or "",
                kind=kind,
                calendar_id=cal_id,
                duration_days=duration,
                remaining_duration_days=remaining,
                early_start=_date(node, "EarlyStart"),
                early_finish=_date(node, "EarlyFinish"),
                late_start=_date(node, "LateStart"),
                late_finish=_date(node, "LateFinish"),
                actual_start=_date(node, "ActualStart"),
                actual_finish=_date(node, "ActualFinish"),
                planned_start=_date(node, "Start"),
                planned_finish=_date(node, "Finish"),
                constraint=constraint,
                constraint_date=constraint_date,
                duration_percent_complete=None
                if duration_percent is None
                else duration_percent / 100,
                physical_percent_complete=None if percent is None else percent / 100,
                is_longest_path=_bool(node, "Critical"),
                code=_text(node, "WBS") or "",
                notes=_text(node, "Notes") or "",
            )
        )


def _read_links(
    root: ElementTree.Element, schedule: ExchangeSchedule, hours_per_day: float
) -> None:
    container = _find(root, "Tasks")
    if container is None:
        return
    known = {a.id for a in schedule.activities}

    for node in _children(container, "Task"):
        successor = _text(node, "UID")
        if successor is None or successor not in known:
            continue
        activity = schedule.activity(successor)
        cal = schedule.calendar(activity.calendar_id if activity else None)
        hpd = cal.hours_per_day if cal else hours_per_day

        for link in _children(node, "PredecessorLink"):
            predecessor = _text(link, "PredecessorUID")
            if predecessor is None:
                continue
            if predecessor not in known:
                schedule.issues.warn(
                    "MSPDI.LINK.DANGLING",
                    f"link {predecessor} -> {successor} references an unknown task",
                    "link dropped",
                    row_key=f"{predecessor}->{successor}",
                )
                continue

            raw_type = _int(link, "Type")
            rel = MSPDI_LINK_TYPES.get(raw_type if raw_type is not None else 1)
            if rel is None:
                rel = RelationType.FS
                schedule.issues.warn(
                    "MSPDI.LINK.UNKNOWN_TYPE",
                    f"link {predecessor} -> {successor} has Type {raw_type}",
                    "coerced to FS; the critical path may differ from MS Project's",
                    row_key=f"{predecessor}->{successor}",
                    field_name="Type",
                    raw_value=raw_type,
                )

            lag_raw = _text(link, "LinkLag")
            lag_days = 0
            if lag_raw:
                try:
                    # LinkLag is in tenths of a minute, signed.
                    lag_minutes = int(lag_raw) / 10
                except ValueError:
                    lag_minutes = 0.0
                sign = -1 if lag_minutes < 0 else 1
                lag_days = sign * days_from_hours(abs(lag_minutes) / 60, hpd)

            schedule.relationships.append(
                ExchangeRelationship(predecessor, successor, rel, lag_days)
            )


# -- writing ---------------------------------------------------------------


def write_mspdi(schedule: ExchangeSchedule, *, exported_at: date | None = None) -> str:
    """Serialise the hub model to MSPDI XML."""
    default_cal = schedule.default_calendar() or Calendar("1", "Standard")
    hours_per_day = default_cal.hours_per_day
    stamp = exported_at or date.today()

    def esc(value: str) -> str:
        """Escape the characters that change meaning; remove the illegal ones.

        Two different problems and both have to be handled here. Escaping `&`,
        `<` and `>` stops a name closing an element and opening another.
        `xmlsafe.text` removes the C0 controls XML 1.0 forbids outright -- a
        vertical tab is not expressible even as `&#x0B;`, so a name carrying
        one produced a file that no parser would open, MS Project's included.
        """
        return (
            xml_text(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def iso(value: date | None) -> str:
        return "" if value is None else f"{value.isoformat()}T08:00:00"

    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Project xmlns="{MSPDI_NS}">',
        f"  <UID>{esc(schedule.project_id or '1')}</UID>",
        f"  <Name>{esc(schedule.project_name or 'Project')}</Name>",
        f"  <Title>{esc(schedule.project_name or 'Project')}</Title>",
        f"  <CreationDate>{iso(stamp)}</CreationDate>",
        f"  <StartDate>{iso(schedule.planned_start)}</StartDate>",
        f"  <StatusDate>{iso(schedule.data_date)}</StatusDate>",
        f"  <MinutesPerDay>{int(hours_per_day * 60)}</MinutesPerDay>",
        f"  <CalendarUID>{esc(default_cal.id)}</CalendarUID>",
        "  <Calendars>",
    ]

    for cal in schedule.calendars or [default_cal]:
        out.append("    <Calendar>")
        out.append(f"      <UID>{esc(cal.id)}</UID>")
        out.append(f"      <Name>{esc(cal.name or cal.id)}</Name>")
        out.append("      <IsBaseCalendar>1</IsBaseCalendar>")
        out.append("      <WeekDays>")
        for python_day in range(7):
            msp_day = (python_day + 1) % 7 + 1
            working = "1" if python_day in cal.working_weekdays else "0"
            out.append("        <WeekDay>")
            out.append(f"          <DayType>{msp_day}</DayType>")
            out.append(f"          <DayWorking>{working}</DayWorking>")
            out.append("        </WeekDay>")
        for exc in cal.exceptions:
            out.append("        <WeekDay>")
            out.append("          <DayType>0</DayType>")
            out.append(f"          <DayWorking>{'1' if exc.working else '0'}</DayWorking>")
            out.append("          <TimePeriod>")
            out.append(f"            <FromDate>{iso(exc.day)}</FromDate>")
            out.append(f"            <ToDate>{iso(exc.day)}</ToDate>")
            out.append("          </TimePeriod>")
            out.append("        </WeekDay>")
        out.append("      </WeekDays>")
        out.append("    </Calendar>")
    out.append("  </Calendars>")

    incoming: dict[str, list[ExchangeRelationship]] = {}
    for rel in schedule.relationships:
        incoming.setdefault(rel.successor_id, []).append(rel)

    out.append("  <Tasks>")
    for index, activity in enumerate(schedule.activities, start=1):
        cal = schedule.calendar_for(activity) or default_cal
        hpd = cal.hours_per_day
        out.append("    <Task>")
        out.append(f"      <UID>{esc(activity.id)}</UID>")
        # ID is the visible row number; UID is the stable key. Emitting the
        # index as ID and the real identifier as UID is what keeps a reorder in
        # MS Project from re-pointing every relationship.
        out.append(f"      <ID>{index}</ID>")
        out.append(f"      <Name>{esc(activity.name)}</Name>")
        out.append(f"      <WBS>{esc(activity.code or str(index))}</WBS>")
        planned_hours = hours_from_days(activity.duration_days, hpd)
        out.append(f"      <Duration>{format_duration_hours(planned_hours)}</Duration>")
        out.append("      <DurationFormat>7</DurationFormat>")
        if activity.remaining_duration_days is not None:
            out.append(
                "      <RemainingDuration>"
                f"{format_duration_hours(hours_from_days(activity.remaining_duration_days, hpd))}"
                "</RemainingDuration>"
            )
        # One boolean for both milestone kinds, because that is all the format
        # has. A `FINISH_MILESTONE` written here reads back as a start
        # milestone -- MSPDI cannot carry the distinction and MS Project has no
        # concept to carry it into. Use XER where that matters; it has
        # `TT_Mile` and `TT_FinMile` and round-trips both.
        out.append(f"      <Milestone>{'1' if activity.kind.is_milestone else '0'}</Milestone>")
        summary = "1" if activity.kind is ActivityKind.WBS_SUMMARY else "0"
        out.append(f"      <Summary>{summary}</Summary>")
        cal_uid = esc(activity.calendar_id or default_cal.id)
        out.append(f"      <CalendarUID>{cal_uid}</CalendarUID>")
        for tag, value in (
            ("Start", activity.early_start or activity.planned_start),
            ("Finish", activity.early_finish or activity.planned_finish),
            ("EarlyStart", activity.early_start),
            ("EarlyFinish", activity.early_finish),
            ("LateStart", activity.late_start),
            ("LateFinish", activity.late_finish),
            ("ActualStart", activity.actual_start),
            ("ActualFinish", activity.actual_finish),
            ("ConstraintDate", activity.constraint_date),
        ):
            if value is not None:
                out.append(f"      <{tag}>{iso(value)}</{tag}>")
        ctype = CONSTRAINTS_TO_MSPDI.get(activity.constraint, 0)
        if activity.constraint in _MANDATORY:
            schedule.issues.warn(
                "MSPDI.TASK.MANDATORY_DOWNGRADED",
                f"activity {activity.id}: {activity.constraint.value} written as "
                f"ConstraintType {ctype}",
                "MS Project has no constraint that overrides logic; the date is "
                "preserved but it will no longer override the network. Use XER "
                "where the mandatory behaviour matters.",
                field_name="ConstraintType",
                raw_value=activity.constraint.value,
            )
        out.append(f"      <ConstraintType>{ctype}</ConstraintType>")
        if activity.notes:
            out.append(f"      <Notes>{esc(activity.notes)}</Notes>")
        for rel in incoming.get(activity.id, []):
            lag_tenths = round(hours_from_days(rel.lag_days, hpd) * 600)
            out.append("      <PredecessorLink>")
            out.append(f"        <PredecessorUID>{esc(rel.predecessor_id)}</PredecessorUID>")
            out.append(f"        <Type>{LINK_TYPES_TO_MSPDI[rel.type]}</Type>")
            out.append(f"        <LinkLag>{lag_tenths}</LinkLag>")
            out.append("        <LagFormat>7</LagFormat>")
            out.append("      </PredecessorLink>")
        out.append("    </Task>")
    out.append("  </Tasks>")
    out.append("</Project>")
    return "\n".join(out) + "\n"


def mpp_unavailable_reason() -> str:
    """Why there is no ``.mpp`` writer, in one sentence a user can act on.

    Stated as a function rather than left unmentioned, so the application can
    show it at the point where somebody asks for the format.
    """
    return (
        "Binary .mpp is a proprietary, undocumented format; export as XML "
        "(MSPDI) from Microsoft Project instead, which round-trips losslessly."
    )
