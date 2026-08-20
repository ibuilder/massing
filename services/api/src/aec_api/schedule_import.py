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

# CRIT-2 (Aikido, 2026-08-13). `massingplan/core/mspdi.py` parses with stdlib
# `ElementTree.fromstring`, which is open to XXE and billion-laughs. The scanner's instruction was to
# swap defusedxml INTO that file. **That would be wrong here**: it is VENDORED verbatim from
# MassingCloud/massingplan, its `core` is stdlib-only *by contract*, and editing a vendored copy turns
# it into a fork every future re-sync has to merge.
#
# Upstream already made the right call and wrote it down in that function: "`core` is pure stdlib by
# contract so the application layer is where an untrusted upload gets hardened." They did their half.
# **This module IS that application layer and had not done its half** — it fed uploaded text straight
# into `read_mspdi`. That gap is the real finding, and it is ours, not theirs.
#
# defusedxml is already declared in requirements.in (for citygml) and already used by bcf_io,
# citygml, clash_import and routers/bim, so this applies an existing standard to a path that missed
# it rather than adding a dependency.
import defusedxml.ElementTree as _defused_et
from defusedxml.common import DefusedXmlException

from massingplan.core.issues import IssueLog, Severity
from massingplan.core.model import ExchangeSchedule
from massingplan.core.mspdi import MSPDIError, read_mspdi
from massingplan.core.network import RelationType
from massingplan.core.p6xml import P6XMLError, read_p6xml, read_p6xml_all
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


def parse_full(text: str, project_id: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse an upload and return ``(records, report)``.

    ``report`` carries the detected format, counts, and the issue log -- every
    coercion, drop and default the reader took, each with a stable code. An
    import that quietly loses a table is the failure this whole path exists to
    prevent, so the report is returned rather than logged.
    """
    detected = detect_format(text)
    issues = IssueLog()
    projects: list[dict[str, str]] = []      # PMXML can hold several; other formats, one


    if detected == "xer":
        schedule = read_xer(text)
    elif detected == "mspdi":
        # Parse once with the hardened parser purely to REJECT. defusedxml raises on external
        # entities, DTD retrieval and entity expansion; if it returns, the document contains none of
        # them and the vendored stdlib reader can be handed the same text safely.
        #
        # The cost is one extra parse of an upload, which is the right trade for a path that accepts
        # a file from a user. Note this rejects rather than sanitises: a document that needs an
        # external entity to be meaningful is not one we want to import silently degraded.
        try:
            _defused_et.fromstring(text)
        except DefusedXmlException as exc:
            raise MSPDIError(
                "MSPDI refused: the document uses XML entity or DTD features that are disabled for "
                f"uploaded files ({type(exc).__name__})."
            ) from exc
        except _defused_et.ParseError:
            pass  # not well-formed — let read_mspdi raise its own, better-worded MSPDIError
        schedule = read_mspdi(text)
    elif detected == "pmxml":
        # R46 — PMXML is now READ, not counted. This branch used to warn and return zero activities,
        # so a planner who exported the format that carries baselines got an import of nothing and a
        # note telling them to re-export as XER. `p6xml.read_p6xml` returns the same
        # `ExchangeSchedule` the XER reader does, so everything downstream is unchanged.
        #
        # Same defused pre-parse as MSPDI, for the same reason and on the same argument: this path
        # takes a file from a user, so it REJECTS a document using entity or DTD features rather
        # than sanitising one. `xmlsafe` in the vendored engine hardens the reader itself; this
        # rejects before the reader is reached at all, and the two are not redundant — one is a
        # property of the parser, the other of this upload path.
        try:
            _defused_et.fromstring(text)
        except DefusedXmlException as exc:
            raise P6XMLError(
                "PMXML refused: the document uses XML entity or DTD features that are disabled for "
                f"uploaded files ({type(exc).__name__})."
            ) from exc
        except _defused_et.ParseError:
            pass  # not well-formed — let read_p6xml raise its own, better-worded P6XMLError
        # R46 ④ — a PMXML export carries its BASELINES as additional <Project> elements, which is
        # the whole reason this format is worth having over XER (XER cannot carry them at all).
        # `read_p6xml` returns ONE project, so a file holding a live schedule plus three baselines
        # imported the first and dropped the rest **without saying so** — measured: a two-project
        # document reported `activities: 2` and no mention of the baseline anywhere in the report.
        #
        # This module's own docstring calls that out as the failure it exists to prevent: "an import
        # that quietly loses a table". A dropped project is a lost table, so it is logged as one, at
        # ERROR — data was dropped — and the projects are named so the caller can ask for a specific
        # one by id rather than guessing which the first was.
        every = read_p6xml_all(text)
        projects = [{"id": sch.project_id, "name": sch.project_name} for sch in every]
        if project_id is not None:
            schedule = read_p6xml(text, project_id=project_id)
        else:
            schedule = every[0] if every else read_p6xml(text)
        if len(every) > 1 and project_id is None:
            dropped = ", ".join(f"{p['name']!r} ({p['id']})" for p in projects[1:])
            issues.error(
                "PMXML_MULTI_PROJECT",
                f"the document holds {len(every)} projects and only one can be imported at a time; "
                f"imported {projects[0]['name']!r} ({projects[0]['id']}), not imported: {dropped}",
                "re-import with project_id set to the one you want — in a P6 export the extra "
                "projects are usually the baselines, which XER could not have carried at all",
                table="Project",
            )
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
        # Present for every format; a PMXML with baselines lists them all, so a caller can see what
        # it did NOT import. One entry means there was nothing to choose between.
        "projects": projects,
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
