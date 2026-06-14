"""Phase 5 — 4D schedule.

Two inputs supported (guide §8):
  1. IFC-native IfcTask / IfcWorkSchedule, when present.
  2. An external activity↔element mapping (CSV/P6/MSP export) applied to the model.

Output is an ordered list of activities each carrying the element GUIDs it drives, so the
viewer can scrub a timeline and color/hide by date."""
from __future__ import annotations

import csv
from typing import Any, Iterable

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


def schedule_file(ifc_path: str, mapping_csv: str | None = None) -> list[dict[str, Any]]:
    model = open_model(ifc_path)
    if mapping_csv:
        return from_mapping_csv(model, mapping_csv)
    return from_ifc(model)
