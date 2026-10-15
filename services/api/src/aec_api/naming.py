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


MAX_VIOLATIONS = 200


def _ident(rec: dict, d: dict) -> tuple[str, str]:
    """The register reference and human title, so a violation row can be FOUND. A list of bad names
    with no ref is a list a reader has to search the register for, one name at a time."""
    return str(rec.get("ref") or ""), str(d.get("title") or rec.get("title") or "")


def audit(db: Session, pid: str) -> dict[str, Any]:
    """Scan the CDE containers and the drawing register, validate each name/sheet-ID, and roll up
    compliance with a bounded violation list.

    **The compliance percentage is over the rows that HAVE a name to rule on, not over the
    register.** ``container_id`` — the ISO 19650 name — is an OPTIONAL field on
    ``information_container``; only ``title`` is required. So registering a container before its
    name is settled is the normal order of work, and this audit used to fall back to the title,
    validate *that* against ``Type_Discipline_Description_Revision_Date``, and report the result as
    a naming violation. Measured on a five-row register with one genuinely misnamed file:

    | | shipped before | here |
    |---|---|---|
    | compliance | **20.0%** of 5 | 50.0% of the 2 named, 3 unnamed |
    | violations | 4 rows, all carrying the same issue string | 1 row |

    Three of those four "violations" read ``expected Type_Discipline_Description_Revision_Date
    (>=5 '_'-separated fields), got 1`` against the titles *Ground floor plan*, *Structural calcs*
    and *Fire strategy* — **character-for-character the issue reported for ``New file (2).pdf``**,
    which is the one file that is actually misnamed. *The audit printed the same sentence for two
    different pieces of work*: one needs a container ID recorded, the other needs the file renamed.
    So `unnamed` is a third state and is never folded into either percentage, the same split
    ``envelope.audit`` makes between ``total`` and ``checked``.

    The drawing side carries the same shape and its ``unnamed`` list is **structurally empty**:
    ``number`` is a REQUIRED field on the ``drawing`` module (a POST without it is a 422), and the
    subject falls back from ``sheet_number`` to it — both are drawing numbers, so the fallback stays
    inside the naming family rather than crossing out of it the way the container one did. The
    branch is kept, and `services/api/test_naming.py` pins the guarantee to the module field it
    depends on: make ``number`` optional and un-numbered drawings start reporting as un-named
    instead of as misnamed.

    Violations are returned in register order and NOT ranked. Every row is one fix of the same size,
    and a stable order is what lets a reader work down the list across two calls — unlike a
    worst-first table, where a cap applied before the ranking is its own defect.
    """
    containers = me.list_records(db, "information_container", pid, limit=100000) \
        if "information_container" in me.TABLES else []
    drawings = me.list_records(db, "drawing", pid, limit=100000) if "drawing" in me.TABLES else []

    c_rows: list[dict] = []
    c_un: list[dict] = []
    c_ok = 0
    for c in containers:
        d = _d(c)
        ref, title = _ident(c, d)
        nm = str(d.get("container_id") or "").strip()
        if not nm:
            c_un.append({"ref": ref, "title": title})
            continue
        v = validate_container_name(nm)
        c_ok += v["valid"]
        if not v["valid"]:
            c_rows.append({"ref": ref, "title": title, "name": nm, "issues": v["issues"]})

    s_rows: list[dict] = []
    s_un: list[dict] = []
    s_ok = 0
    for dr in drawings:
        d = _d(dr)
        ref, title = _ident(dr, d)
        nm = str(d.get("sheet_number") or d.get("number") or "").strip()
        if not nm:
            s_un.append({"ref": ref, "title": title})
            continue
        v = validate_sheet_id(nm)
        s_ok += v["valid"]
        if not v["valid"]:
            s_rows.append({"ref": ref, "title": title, "name": nm, "issues": v["issues"]})

    def block(total: int, ok: int, rows: list[dict], un: list[dict]) -> dict[str, Any]:
        named = total - len(un)
        return {
            # `compliance_pct` is over `named`, never over `total`: `unnamed_count` is the gap
            # between them and the only honest way to read the percentage.
            "total": total, "named": named, "compliant": ok, "compliance_pct": _pct(ok, named),
            "violations": rows[:MAX_VIOLATIONS],
            "violations_count": len(rows),
            "violations_truncated": len(rows) > MAX_VIOLATIONS,
            "unnamed": un[:MAX_VIOLATIONS],
            "unnamed_count": len(un),
            "unnamed_truncated": len(un) > MAX_VIOLATIONS,
        }

    return {
        "conventions": conventions(),
        "containers": block(len(containers), c_ok, c_rows, c_un),
        "sheets": block(len(drawings), s_ok, s_rows, s_un),
        "max_violations": MAX_VIOLATIONS,
    }
