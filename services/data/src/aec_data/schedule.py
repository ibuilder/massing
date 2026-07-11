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

import ifcopenshell
import ifcopenshell.util.element as ue
import ifcopenshell.util.sequence as seq

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
            table = rest.strip(); fields = []
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
        root = ET.fromstring(text)
    except ET.ParseError:
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


def parse_schedule(text: str) -> list[dict[str, str]]:
    """Parse a Primavera P6 export in either format — **XER** (tab-delimited) or **PMXML** (XML) —
    auto-detected from the content, into activity rows the schedule import consumes."""
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return parse_pmxml(text)
    return parse_xer(text)


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
