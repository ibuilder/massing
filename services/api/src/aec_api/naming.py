"""Naming conventions (A3): validate document/container filenames and drawing sheet IDs against the
project's information standard, and audit the registers for compliance.

Two conventions, matching the ISO 19650 / US NCS practice the platform already speaks:
  - Container / document files: ``Type_Discipline_Description_Revision_Date`` — revision-controlled
    (P01 / C01 / 00 …), approved files never overwritten.
  - Drawing sheets: US National CAD Standard Sheet ID (discipline designator + sheet-type digit +
    sequence, e.g. ``A-101``) — reuses the D3 sheet-ID parser.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from . import classification, drawingset
from . import modules as me

_REV_RE = re.compile(r"^[A-Za-z]{0,2}\d{1,3}$")            # P01, C01, 00, 01, T1
_DATE_RE = re.compile(r"^\d{4}(-?\d{2}){0,2}$|^\d{6,8}$")  # 2026 | 2026-07 | 2026-07-05 | 260705
CONTAINER_PATTERN = "Type_Discipline_Description_Revision_Date"


def conventions() -> dict[str, Any]:
    """The documented naming conventions the validators enforce."""
    return {
        "container": {
            "pattern": CONTAINER_PATTERN, "separator": "_",
            "fields": ["Type", "Discipline", "Description", "Revision", "Date"],
            "note": "e.g. DR_A_GroundFloorPlan_P01_2026-07-05 — revision-controlled; approved files "
                    "are never overwritten.",
        },
        "sheet": {
            "pattern": "NCS Sheet ID: <discipline designator><sheet-type digit><sequence>",
            "note": "e.g. A-101 = Architectural / Plans / 01.",
        },
    }


def _d(r: dict) -> dict:
    return r.get("data") or r


def validate_container_name(name: str) -> dict[str, Any]:
    """Validate a document/container filename against ``Type_Discipline_Description_Revision_Date``."""
    stem = str(name or "").rsplit(".", 1)[0]
    parts = stem.split("_")
    issues: list[str] = []
    fields: dict[str, str] = {}
    if len(parts) < 5:
        issues.append(f"expected {CONTAINER_PATTERN} (>=5 '_'-separated fields), got {len(parts)}")
    else:
        fields = {"type": parts[0], "discipline": parts[1], "description": "_".join(parts[2:-2]),
                  "revision": parts[-2], "date": parts[-1]}
        if not classification.discipline_code(fields["discipline"]):
            issues.append(f"discipline '{fields['discipline']}' is not a known designator / name")
        if not _REV_RE.match(fields["revision"]):
            issues.append(f"revision '{fields['revision']}' not like P01 / C01 / 00")
        if not _DATE_RE.match(fields["date"]):
            issues.append(f"date '{fields['date']}' not a YYYY[-MM[-DD]] token")
    return {"name": name, "kind": "container", "valid": not issues, "fields": fields, "issues": issues}


def validate_sheet_id(sheet: str) -> dict[str, Any]:
    """Validate a drawing sheet number against the NCS Sheet ID grammar (reuses the D3 parser)."""
    parsed = drawingset.parse_sheet_id(sheet)
    issues = [] if parsed else ["not a valid NCS Sheet ID (e.g. A-101)"]
    return {"name": sheet, "kind": "sheet", "valid": bool(parsed), "fields": parsed or {}, "issues": issues}


def validate(name: str, kind: str = "container") -> dict[str, Any]:
    return validate_sheet_id(name) if kind == "sheet" else validate_container_name(name)


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def audit(db: Session, pid: str) -> dict[str, Any]:
    """Scan the CDE containers and the drawing register, validate each name/sheet-ID, and roll up
    compliance with a bounded violation list."""
    containers = me.list_records(db, "information_container", pid, limit=100000) \
        if "information_container" in me.TABLES else []
    drawings = me.list_records(db, "drawing", pid, limit=100000) if "drawing" in me.TABLES else []

    c_rows: list[dict] = []
    c_ok = 0
    for c in containers:
        d = _d(c)
        nm = d.get("container_id") or d.get("title") or c.get("id", "")
        v = validate_container_name(nm)
        c_ok += v["valid"]
        if not v["valid"]:
            c_rows.append({"name": nm, "issues": v["issues"]})

    s_rows: list[dict] = []
    s_ok = 0
    for dr in drawings:
        d = _d(dr)
        nm = d.get("sheet_number") or d.get("number") or ""
        v = validate_sheet_id(nm)
        s_ok += v["valid"]
        if not v["valid"]:
            s_rows.append({"name": nm or "(blank)", "issues": v["issues"]})

    return {
        "conventions": conventions(),
        "containers": {"total": len(containers), "compliant": c_ok,
                       "compliance_pct": _pct(c_ok, len(containers)), "violations": c_rows[:200]},
        "sheets": {"total": len(drawings), "compliant": s_ok,
                   "compliance_pct": _pct(s_ok, len(drawings)), "violations": s_rows[:200]},
    }
