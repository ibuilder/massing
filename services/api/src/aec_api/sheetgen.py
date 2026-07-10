"""Discipline sheet-set generator — turns the model's storeys + the disciplines present into a
standard, correctly-numbered drawing set. One **sheet series per discipline**, each with its own NCS
designator and its own sequence:

    G- General · C- Civil · L- Landscape · S- Structural · A- Architectural · FP- Fire Protection ·
    FA- Fire Alarm · P- Plumbing · M- Mechanical · E- Electrical · T- Telecommunications

Each series gets a cover/notes sheet, one plan per building level, and the usual elevations / sections
/ details / schedules — numbered per the US National CAD Standard (``<designator><sheet-type digit>
<2-digit sequence>``, e.g. ``M-101`` = Mechanical / Plans / 01, ``FA-101`` = Fire Alarm / Plans / 01).
Creates one ``drawing`` record per sheet so the set flows straight into the drawing-set register,
transmittal, and naming validation. Idempotent: a sheet number that already exists is skipped."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import modules as me

# NCS sheet-type digit → name (mirrors drawingset._SHEET_TYPE).
_TYPE_NAME = {"0": "General", "1": "Plans", "2": "Elevations", "3": "Sections",
              "4": "Large-scale views", "5": "Details", "6": "Schedules & Diagrams"}

# Per-series sheet program. `general`/`end` are fixed (type_digit, title); `per_level` emits one sheet
# per building level (type_digit, "{level} …" title). Sequence runs per (series, type). Order here is
# NCS binding order (the order a set is assembled). `parent` is the NCS level-1 discipline a 2-letter
# designator refines (FA/FP), used for detection + colour; `name` is what goes in the drawing record.
SERIES: list[dict[str, Any]] = [
    {"code": "G", "name": "General", "parent": "G",
     "general": [("0", "Cover Sheet & Drawing Index"), ("0", "General Notes & Abbreviations"),
                 ("0", "Code & Zoning Analysis"), ("0", "Life Safety Plan")],
     "per_level": [], "end": []},
    {"code": "C", "name": "Civil", "parent": "C",
     "general": [("0", "Civil General Notes")],
     "per_level": [], "end": [("1", "Site Plan"), ("1", "Grading & Drainage Plan"),
                              ("1", "Utility Plan"), ("5", "Civil Details")]},
    {"code": "L", "name": "Landscape", "parent": "L",
     "general": [], "per_level": [], "end": [("1", "Landscape Plan"), ("1", "Planting Plan"),
                                             ("5", "Landscape Details")]},
    {"code": "S", "name": "Structural", "parent": "S",
     "general": [("0", "Structural General Notes")],
     "per_level": [("1", "{level} Framing Plan")],
     "end": [("1", "Foundation Plan"), ("3", "Building Sections"), ("5", "Structural Details"),
             ("6", "Column & Beam Schedules")]},
    {"code": "A", "name": "Architectural", "parent": "A",
     "general": [("0", "Architectural General Notes")],
     "per_level": [("1", "{level} Floor Plan"), ("1", "{level} Reflected Ceiling Plan")],
     "end": [("2", "Building Elevations"), ("3", "Building Sections"), ("4", "Enlarged Plans"),
             ("5", "Wall Sections & Details"), ("6", "Door, Window & Finish Schedules")]},
    {"code": "FP", "name": "Fire Protection", "parent": "F",
     "general": [("0", "Fire Protection Notes & Legend")],
     "per_level": [("1", "{level} Sprinkler Plan")],
     "end": [("6", "Fire Protection Riser Diagram")]},
    {"code": "FA", "name": "Fire Alarm", "parent": "E",
     "general": [("0", "Fire Alarm Notes & Legend")],
     "per_level": [("1", "{level} Fire Alarm Device Plan")],
     "end": [("6", "Fire Alarm Riser Diagram"), ("6", "Device Matrix & Sequence of Operations")]},
    {"code": "P", "name": "Plumbing", "parent": "P",
     "general": [("0", "Plumbing Notes & Legend")],
     "per_level": [("1", "{level} Plumbing Plan")],
     "end": [("6", "Plumbing Riser Diagram"), ("6", "Fixture & Equipment Schedules")]},
    {"code": "M", "name": "Mechanical", "parent": "M",
     "general": [("0", "Mechanical Notes & Legend")],
     "per_level": [("1", "{level} HVAC Plan")],
     "end": [("5", "Mechanical Details"), ("6", "Equipment Schedules"),
             ("6", "Control & Flow Diagrams")]},
    {"code": "E", "name": "Electrical", "parent": "E",
     "general": [("0", "Electrical Notes & Legend")],
     "per_level": [("1", "{level} Power Plan"), ("1", "{level} Lighting Plan")],
     "end": [("6", "Panel Schedules"), ("6", "Electrical Riser & One-Line Diagram")]},
    {"code": "T", "name": "Telecommunications", "parent": "T",
     "general": [("0", "Telecom Notes & Legend")],
     "per_level": [("1", "{level} Telecom/Data Plan")],
     "end": [("6", "Telecom Riser Diagram")]},
]
_BY_CODE = {s["code"]: s for s in SERIES}
# Default set for a standard occupied building when none is specified / detected.
DEFAULT_CODES = ["G", "S", "A", "FP", "FA", "P", "M", "E", "T"]

# IFC classes → which discipline series their presence implies (drives auto-detection). Structural
# and architectural are assumed for any building; MEP/FA/FP series only appear when the model carries
# the corresponding elements (so a shell model doesn't get empty mechanical sheets unless asked).
_CLASS_SERIES = {
    "IfcDuctSegment": "M", "IfcDuctFitting": "M", "IfcAirTerminal": "M", "IfcUnitaryEquipment": "M",
    "IfcPipeSegment": "P", "IfcPipeFitting": "P", "IfcSanitaryTerminal": "P",
    "IfcCableSegment": "E", "IfcCableCarrierSegment": "E", "IfcElectricAppliance": "E",
    "IfcOutlet": "E", "IfcLightFixture": "E", "IfcElectricDistributionBoard": "E",
    "IfcFireSuppressionTerminal": "FP", "IfcAlarm": "FA", "IfcSensor": "FA",
    "IfcCommunicationsAppliance": "T",
}


_NAME_TO_CODE = {s["name"].lower(): s["code"] for s in SERIES}


def normalize_codes(items: list[str] | None) -> list[str]:
    """Turn a mix of designators / discipline names ('M', 'Mechanical', 'FA', 'Fire Alarm') into the
    canonical series codes, deduped and in NCS binding order. Unknown entries are dropped."""
    want = set()
    for it in items or []:
        v = str(it).strip()
        code = v.upper() if v.upper() in _BY_CODE else _NAME_TO_CODE.get(v.lower())
        if code:
            want.add(code)
    return [s["code"] for s in SERIES if s["code"] in want]


def detect_series(ifc_classes: set[str]) -> list[str]:
    """Which sheet series a model warrants: always G/S/A, plus any discipline whose elements are
    present. Preserves NCS binding order."""
    codes = {"G", "S", "A"}
    for c in ifc_classes:
        s = _CLASS_SERIES.get(c)
        if s:
            codes.add(s)
    return [s["code"] for s in SERIES if s["code"] in codes]


def _sheet(s: dict[str, Any], seq: dict[str, int], typ: str, title: str) -> dict[str, Any]:
    """One sheet record; `seq` (per series, mutated) carries the running sequence for each type."""
    seq[typ] += 1
    number = f"{s['code']}-{typ}{seq[typ]:02d}"
    return {"number": number, "sheet_number": number,
            "discipline": s["name"], "discipline_code": s["code"],
            "sheet_type": _TYPE_NAME.get(typ, "User-defined"),
            "title": f"{s['name']} — {title}".upper()}


def plan_set(level_names: list[str], series_codes: list[str] | None = None) -> list[dict[str, Any]]:
    """The sheet index (no DB) for the given levels + series. Deterministic + pure — used by the
    preview endpoint and the generator. Sequence is per (series, sheet-type)."""
    codes = series_codes or DEFAULT_CODES
    levels = level_names or ["Level 1"]
    sheets: list[dict[str, Any]] = []
    for code in codes:
        s = _BY_CODE.get(code)
        if not s:
            continue
        seq: dict[str, int] = defaultdict(int)
        for typ, title in s["general"]:
            sheets.append(_sheet(s, seq, typ, title))
        for typ, tmpl in s["per_level"]:
            for lvl in levels:
                sheets.append(_sheet(s, seq, typ, tmpl.format(level=lvl)))
        for typ, title in s["end"]:
            sheets.append(_sheet(s, seq, typ, title))
    return sheets


def generate(db: Session, pid: str, level_names: list[str],
             series_codes: list[str] | None = None) -> dict[str, Any]:
    """Create a `drawing` record per generated sheet (skipping any sheet number that already exists),
    then return the resulting drawing-set register. Bulk-inserts in a single transaction — a full
    50-storey, all-discipline set is ~500–2500 sheets, so the per-record create/commit path is far too
    slow (measured ~48 rec/s); this does it in one round-trip."""
    import uuid
    from datetime import datetime, timezone

    from . import drawingset
    mod = me.get_module("drawing")
    t = me.TABLES["drawing"]
    planned = plan_set(level_names, series_codes)
    existing = set()
    start_n = db.execute(select(func.count()).select_from(t).where(t.c.project_id == pid)).scalar() or 0
    for r in me.list_records(db, "drawing", pid, limit=100000):
        d = r.get("data") or {}
        existing.add((d.get("sheet_number") or d.get("number") or "").strip())
    prefix = mod.get("ref_prefix", "DWG")
    initial = mod.get("workflow", {}).get("initial", "open")
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    by_discipline: dict[str, int] = defaultdict(int)
    n = start_n
    for sh in planned:
        if sh["number"] in existing:
            continue
        n += 1
        rows.append({
            "id": str(uuid.uuid4()), "project_id": pid, "ref": f"{prefix}-{n:03d}",
            "title": sh["number"], "workflow_state": initial, "party_owner": "GC",
            "assignee": None, "created_by": "sheetgen", "created_at": now, "modified_at": now,
            "anchor": None, "element_guids": None, "links": [],
            "data": {"number": sh["number"], "sheet_number": sh["number"], "title": sh["title"],
                     "discipline": sh["discipline"], "status": "For Review", "revision": "",
                     "purpose": "Issued for Review"},
        })
        by_discipline[sh["discipline"]] += 1
    if rows:
        db.execute(t.insert(), rows)
        db.commit()
    reg = drawingset.drawing_set(db, pid)
    return {
        "levels": len(level_names), "series": series_codes or DEFAULT_CODES,
        "planned": len(planned), "created": len(rows),
        "skipped_existing": len(planned) - len(rows),
        "by_discipline": dict(by_discipline),
        "sheet_count": reg["sheet_count"], "register": reg,
    }
