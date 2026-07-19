"""Phase 5 — 4D schedule.

Two inputs supported (guide §8):
  1. IFC-native IfcTask / IfcWorkSchedule, when present.
  2. An external activity↔element mapping (CSV/P6/MSP export) applied to the model.

Output is an ordered list of activities each carrying the element GUIDs it drives, so the
viewer can scrub a timeline and color/hide by date."""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from typing import Any

import defusedxml.ElementTree as _DET  # XXE-safe parser for untrusted P6 XML uploads
import ifcopenshell
import ifcopenshell.util.element as ue
import ifcopenshell.util.sequence as seq
from defusedxml.common import DefusedXmlException

from .ifc_loader import open_model, physical_elements, storey_name


def from_ifc(model: ifcopenshell.file) -> list[dict[str, Any]]:
    """Read IfcTask activities and the products each one outputs/operates on."""
    activities: list[dict[str, Any]] = []
    for task in model.by_type("IfcTask"):
        time = task.TaskTime
        outputs = []
        try:
            outputs = [p.GlobalId for p in seq.get_task_outputs(task) or []]
        except Exception:
            outputs = []
        activities.append({
            "id": task.Identification or task.GlobalId,
            "name": task.Name,
            "start": getattr(time, "ScheduleStart", None) if time else None,
            "finish": getattr(time, "ScheduleFinish", None) if time else None,
            "guids": outputs,
        })
    return activities


def _matches(el, rule: dict[str, str]) -> bool:
    if "ifc_class" in rule and el.is_a() != rule["ifc_class"]:
        return False
    if "storey" in rule and storey_name(el) != rule["storey"]:
        return False
    if "type" in rule:
        t = ue.get_type(el)
        if not t or getattr(t, "Name", None) != rule["type"]:
            return False
    return True


def from_mapping(model: ifcopenshell.file, rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """rows: activity_id,name,start,finish,ifc_class?,storey?,type? — each row a selection rule."""
    els = list(physical_elements(model))
    activities: list[dict[str, Any]] = []
    for r in rows:
        rule = {k: v for k, v in r.items() if k in ("ifc_class", "storey", "type") and v}
        guids = [el.GlobalId for el in els if _matches(el, rule)]
        activities.append({
            "id": r.get("activity_id"),
            "name": r.get("name"),
            "start": r.get("start"),
            "finish": r.get("finish"),
            "guids": guids,
        })
    return activities


def from_mapping_csv(model: ifcopenshell.file, csv_path: str) -> list[dict[str, Any]]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return from_mapping(model, list(csv.DictReader(fh)))


def parse_xer(text: str) -> list[dict[str, str]]:
    """Parse a Primavera P6 **.xer** export (tab-delimited; %T table / %F field-header / %R rows)
    into activity rows {activity_id, name, start, finish} from its TASK table — the same shape
    `from_mapping` consumes. Prefers planned (target) dates, falls back to actual/early dates.
    Pure string→rows; .mpp is intentionally unsupported (proprietary binary — export to XER/CSV)."""
    rows: list[dict[str, str]] = []
    table: str | None = None
    fields: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        tag, _, rest = line.partition("\t")
        if tag == "%T":
            table = rest.strip()
            fields = []
        elif tag == "%F":
            fields = rest.split("\t")
        elif tag == "%R" and table == "TASK" and fields:
            vals = rest.split("\t")
            rec = dict(zip(fields, vals))
            start = rec.get("target_start_date") or rec.get("act_start_date") or rec.get("early_start_date") or ""
            finish = rec.get("target_end_date") or rec.get("act_end_date") or rec.get("early_end_date") or ""
            rows.append({
                "activity_id": rec.get("task_code") or rec.get("task_id") or "",
                "name": rec.get("task_name") or "",
                "start": start[:10], "finish": finish[:10],
            })
    return rows


def _local(tag: str) -> str:
    """Local element name without its XML namespace (`{ns}Activity` → `Activity`)."""
    return tag.rsplit("}", 1)[-1]


def parse_pmxml(text: str) -> list[dict[str, str]]:
    """Parse a Primavera P6 **XML (PMXML)** export into the same activity rows
    {activity_id, name, start, finish} as `parse_xer`. Namespace-agnostic (the P6 namespace varies
    by version, so we match on local tag names). Prefers planned dates, falls back to actual dates.
    Returns [] for non-XML or XML without <Activity> elements."""
    try:
        root = _DET.fromstring(text)                # defused: blocks XXE / entity-expansion attacks
    except (ET.ParseError, DefusedXmlException):
        return []
    rows: list[dict[str, str]] = []
    for act in (e for e in root.iter() if _local(e.tag) == "Activity"):
        vals: dict[str, str] = {}
        for child in act:
            name = _local(child.tag)
            if name not in vals and child.text and child.text.strip():
                vals[name] = child.text.strip()
        start = vals.get("PlannedStartDate") or vals.get("StartDate") or vals.get("ActualStartDate") or ""
        finish = vals.get("PlannedFinishDate") or vals.get("FinishDate") or vals.get("ActualFinishDate") or ""
        rows.append({
            "activity_id": vals.get("Id") or vals.get("ObjectId") or "",
            "name": vals.get("Name") or "",
            "start": start[:10], "finish": finish[:10],
        })
    return rows


def parse_mspdi(text: str) -> list[dict[str, str]]:
    """Parse a **Microsoft Project XML (MSPDI)** export into the same activity rows
    {activity_id, name, start, finish} as the P6 parsers. MSPDI uses `<Task>` under `<Tasks>` (P6's
    PMXML uses `<Activity>`), so the two are distinguished by tag. The activity code round-trips via
    the `<WBS>` field (that's where `to_mspdi` writes it); falls back to `<UID>`. The project-summary
    task (blank name, no dates) is skipped. Namespace-agnostic. Returns [] for XML without `<Task>`."""
    try:
        root = _DET.fromstring(text)                # defused: blocks XXE / entity-expansion attacks
    except (ET.ParseError, DefusedXmlException):
        return []
    rows: list[dict[str, str]] = []
    for task in (e for e in root.iter() if _local(e.tag) == "Task"):
        vals: dict[str, str] = {}
        for child in task:
            name = _local(child.tag)
            if name not in vals and child.text and child.text.strip():
                vals[name] = child.text.strip()
        start = vals.get("Start") or vals.get("ActualStart") or ""
        finish = vals.get("Finish") or vals.get("ActualFinish") or ""
        act_name = vals.get("Name") or ""
        if not act_name and not start:               # empty placeholder task
            continue
        # HARDEN-2 (B3): real MS Project exports carry the project-summary task (UID 0) and one
        # summary task per WBS header — named AND dated, so the old blank-guard let them through as
        # phantom activities inflating CPM/4D/EV. Summary containers are rollups, not work — skip.
        if vals.get("Summary") == "1" or vals.get("OutlineLevel") == "0":
            continue
        rows.append({
            "activity_id": vals.get("WBS") or vals.get("UID") or "",
            "name": act_name, "start": start[:10], "finish": finish[:10],
        })
    return rows


def parse_schedule(text: str) -> list[dict[str, str]]:
    """Parse a schedule export in any supported format — Primavera **XER** (tab-delimited), Primavera
    **PMXML** (XML with `<Activity>`), or **MS-Project MSPDI** (XML with `<Task>`) — auto-detected from
    the content, into the activity rows the schedule import consumes."""
    stripped = text.lstrip()
    if stripped.startswith("<"):
        rows = parse_pmxml(text)                      # P6 XML first (…<Activity>…)
        if not rows:
            rows = parse_mspdi(text)                  # …then MS-Project XML (…<Task>…)
        return rows
    return parse_xer(text)


def _is_milestone(a: dict[str, Any]) -> bool:
    return bool(a.get("activity_type") == "Milestone"
               or (a.get("start") and a.get("start") == a.get("finish")))


def _xer_cell(v: Any) -> str:
    """XER is tab/newline-delimited, so a value can contain neither — flatten to spaces."""
    return str(v if v is not None else "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def to_xer(activities: list[dict[str, Any]], project_name: str = "Schedule",
           export_date: str = "2024-01-01") -> str:
    """Serialize activities → a minimal but valid Primavera P6 **.xer** (tab-delimited). Emits the
    ERMHDR header and a TASK table carrying task_code / task_name / task_type / target dates /
    percent — the exact fields `parse_xer` reads back, so export→re-import round-trips by activity
    code. Each activity dict: {activity_id, name, start 'YYYY-MM-DD', finish, activity_type?, percent?}.
    Dates are written 'YYYY-MM-DD 00:00' (P6's format); `parse_xer` truncates back to the date."""
    lines = ["\t".join(["ERMHDR", "8.0", export_date, _xer_cell(project_name) or "Project", "", "",
                        "dbxDatabaseNoName", "Project Management", "USD"])]
    fields = ["task_id", "task_code", "task_name", "task_type", "status_code",
              "target_start_date", "target_end_date", "phys_complete_pct"]
    lines.append("%T\tTASK")
    lines.append("%F\t" + "\t".join(fields))
    for i, a in enumerate(activities, 1):
        code = a.get("activity_id") or f"A{i:04d}"
        ttype = "TT_Mile" if _is_milestone(a) else "TT_Task"
        start = a.get("start") or ""
        finish = a.get("finish") or ""
        row = [i, code, a.get("name") or code, ttype, "TK_NotStart",
               (start + " 00:00") if start else "", (finish + " 00:00") if finish else "",
               int(a.get("percent") or 0)]
        lines.append("%R\t" + "\t".join(_xer_cell(c) for c in row))
    lines.append("%E")
    return "\n".join(lines) + "\n"


def _msp_dt(d: str | None, end: bool) -> str:
    """A 'YYYY-MM-DD' date → an MSPDI datetime; work-day 08:00 start / 17:00 finish. '' when no date."""
    if not d:
        return ""
    return f"{d[:10]}T{'17:00:00' if end else '08:00:00'}"


def _xesc(v: Any) -> str:
    from xml.sax.saxutils import escape
    return escape(str(v if v is not None else ""))


def to_mspdi(activities: list[dict[str, Any]], project_name: str = "Schedule") -> str:
    """Serialize activities → a **Microsoft Project XML (MSPDI)** document that MS Project can open.
    The activity code is written to each task's `<WBS>` so the export round-trips through
    `parse_mspdi` by code. Milestones get `<Milestone>1</Milestone>` and equal start/finish."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<Project xmlns="http://schemas.microsoft.com/project">',
             f'<Name>{_xesc(project_name)}</Name>', '<Tasks>']
    for i, a in enumerate(activities, 1):
        code = a.get("activity_id") or f"A{i:04d}"
        start = _msp_dt(a.get("start"), False)
        finish = _msp_dt(a.get("finish"), True)
        parts += [
            '<Task>', f'<UID>{i}</UID>', f'<ID>{i}</ID>',
            f'<Name>{_xesc(a.get("name") or code)}</Name>',
            f'<WBS>{_xesc(code)}</WBS>',
            f'<OutlineNumber>{i}</OutlineNumber>', '<OutlineLevel>1</OutlineLevel>',
            f'<Milestone>{1 if _is_milestone(a) else 0}</Milestone>',
        ]
        if start:
            parts.append(f'<Start>{start}</Start>')
        if finish:
            parts.append(f'<Finish>{finish}</Finish>')
        parts.append(f'<PercentComplete>{int(a.get("percent") or 0)}</PercentComplete>')
        parts.append('</Task>')
    parts += ['</Tasks>', '</Project>']
    return "\n".join(parts) + "\n"


def from_xer(model: ifcopenshell.file, xer_path: str) -> list[dict[str, Any]]:
    """Import P6 .xer activities and match them to model elements by the same name/class/storey
    rules as the CSV path (so a P6 schedule drives the 4D scrub). Element-matching columns
    (ifc_class/storey/type) may be added per-row by a companion mapping; bare .xer yields dated
    activities you can then map."""
    with open(xer_path, encoding="utf-8", errors="ignore") as fh:
        return from_mapping(model, parse_xer(fh.read()))


def schedule_file(ifc_path: str, mapping_csv: str | None = None) -> list[dict[str, Any]]:
    model = open_model(ifc_path)
    if mapping_csv:
        return from_mapping_csv(model, mapping_csv)
    return from_ifc(model)
