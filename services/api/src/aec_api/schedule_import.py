"""Full-fidelity schedule import, routed through the vendored massingplan readers.

The previous import path wrote exactly five fields per activity --
`{name, wbs, start, finish, activity_type}` -- because that is all
`aec_data.schedule.parse_schedule` returns. It never read `TASKPRED`.

That is not a cosmetic gap. An activity network with no relationships has no
critical path: **every activity comes back with zero float and reads as
critical**, and the import reports success. Every downstream analysis -- EVM,
Monte Carlo, the extension-of-time methods, resource levelling within float --
then computes correctly from an input that is wrong.

This module reads the same files through `massingplan.xer` / `massingplan.mspdi`
(see `services/api/src/massingplan/VENDOR.md`), which carry relationships,
relationship types, lags, calendars with their exceptions, constraints, actual
dates and remaining duration. It emits the record `data` blob the module engine
stores, so the rest of the import endpoint is unchanged.

PMXML (P6's XML flavour) still goes through the old parser, which handles it and
the vendored engine does not. That is stated rather than hidden: a PMXML import
still arrives without logic, and this module says so in the returned issues.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.issues import IssueLog, Severity
from massingplan.core.model import ExchangeSchedule
from massingplan.core.mspdi import MSPDIError, read_mspdi
from massingplan.core.network import RelationType
from massingplan.core.xer import XERError, read_xer

#: How a relationship reads in the `predecessors` field the module engine stores
#: and `schedule_engine.parse_predecessor_tokens` reads back.
_TYPE_SUFFIX = {
    RelationType.FS: "FS",
    RelationType.SS: "SS",
    RelationType.FF: "FF",
    RelationType.SF: "SF",
}

_KIND_LABEL = {
    "task": "Task",
    "start_milestone": "Milestone",
    "finish_milestone": "Milestone",
    "level_of_effort": "Level of Effort",
    "wbs_summary": "Summary",
}


def detect_format(text: str) -> str:
    """``"xer"``, ``"mspdi"``, ``"pmxml"`` or ``"unknown"``."""
    stripped = text.lstrip()
    if stripped.startswith("<"):
        if "<Activity" in text or "APIBusinessObjects" in text:
            return "pmxml"
        if "<Task" in text or "schemas.microsoft.com/project" in text:
            return "mspdi"
        return "unknown"
    if "%T" in text and "ERMHDR" in text:
        return "xer"
    return "unknown"


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _predecessor_field(schedule: ExchangeSchedule, activity_id: str) -> str:
    """``"A1010FS+3, A1020SS"`` -- the notation planners type and the adapter parses.

    Written against the activity **code**, not the internal id, so the field
    stays readable and survives a re-import that renumbers the records.
    """
    codes = {a.id: (a.code or a.id) for a in schedule.activities}
    parts: list[str] = []
    for rel in schedule.relationships:
        if rel.successor_id != activity_id:
            continue
        token = codes.get(rel.predecessor_id, rel.predecessor_id)
        suffix = _TYPE_SUFFIX[rel.type]
        if rel.type is not RelationType.FS or rel.lag_days:
            token += suffix
        if rel.lag_days:
            token += f"{rel.lag_days:+d}"
        parts.append(token)
    return ", ".join(parts)


def to_records(schedule: ExchangeSchedule) -> list[dict[str, Any]]:
    """Map an imported schedule to `schedule_activity` `data` blobs."""
    calendars = {c.id: c for c in schedule.calendars}
    default_calendar = schedule.default_calendar()
    rows: list[dict[str, Any]] = []

    for activity in schedule.activities:
        cal = calendars.get(activity.calendar_id or "") or default_calendar
        # The module engine's calendar vocabulary is a small named set; map the
        # file's weekly pattern onto it rather than inventing a calendar record.
        working = len(cal.working_weekdays) if cal else 5
        calendar_key = {5: "5D", 6: "6D", 7: "7D"}.get(working, "5D")

        rows.append(
            {
                "activity_id": activity.code or activity.id,
                "data": {
                    "name": activity.name or activity.code or activity.id,
                    "wbs": activity.code or "",
                    "start": _iso(activity.early_start or activity.planned_start),
                    "finish": _iso(activity.early_finish or activity.planned_finish),
                    "activity_type": _KIND_LABEL.get(activity.kind.value, "Task"),
                    # -- everything the previous importer dropped ---------------
                    "duration": activity.duration_days,
                    "remaining_duration": activity.remaining_duration_days,
                    "predecessors": _predecessor_field(schedule, activity.id),
                    "calendar": calendar_key,
                    "constraint": activity.constraint.value,
                    "constraint_date": _iso(activity.constraint_date),
                    "actual_start": _iso(activity.actual_start),
                    "actual_finish": _iso(activity.actual_finish),
                    "percent": (
                        None
                        if activity.percent_complete is None
                        else round(activity.percent_complete * 100, 2)
                    ),
                },
            }
        )
    return rows


def parse_full(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse an upload and return ``(records, report)``.

    ``report`` carries the detected format, counts, and the issue log -- every
    coercion, drop and default the reader took, each with a stable code. An
    import that quietly loses a table is the failure this whole path exists to
    prevent, so the report is returned rather than logged.
    """
    detected = detect_format(text)
    issues = IssueLog()

    if detected == "xer":
        schedule = read_xer(text)
    elif detected == "mspdi":
        schedule = read_mspdi(text)
    elif detected == "pmxml":
        # Handled by the data service's parser, which does not read logic.
        # Named, not hidden.
        issues.warn(
            "IMPORT.PMXML_NO_LOGIC",
            "PMXML is parsed by the legacy reader, which does not carry relationships",
            "activities imported without logic; export as .xer for a full import",
        )
        return [], {
            "format": "pmxml",
            "fell_back": True,
            "activities": 0,
            "relationships": 0,
            "issues": issues.to_list(),
        }
    else:
        raise ValueError(
            "unrecognised schedule format -- expected a Primavera .xer, a "
            "Primavera PMXML export, or an MS Project .xml (MSPDI)"
        )

    issues.extend(schedule.issues)
    records = to_records(schedule)
    problems = schedule.validate()

    return records, {
        "format": detected,
        "fell_back": False,
        "project": schedule.project_name,
        "data_date": _iso(schedule.data_date),
        "activities": len(schedule.activities),
        "relationships": len(schedule.relationships),
        "calendars": len(schedule.calendars),
        "resources": len(schedule.resources),
        # The headline: how much logic came across. Zero here means the
        # resulting critical path is meaningless, and the caller should say so
        # rather than showing a green tick.
        "has_logic": bool(schedule.relationships),
        "validation_problems": problems,
        "issues": issues.to_list(),
        "error_count": issues.count(Severity.ERROR),
        "warning_count": issues.count(Severity.WARNING),
    }


__all__ = ["MSPDIError", "XERError", "detect_format", "parse_full", "to_records"]
