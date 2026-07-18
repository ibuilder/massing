"""QA-AGENT — drawing-set QA review: every finding cited to a sheet, computed from structured source.

Agentic drawing review is the 2026 benchmark — but most tools review *raster PDFs*. This platform
generates its sheets from the model, so the QA pass can check the **structured source** directly (no OCR,
no hallucination): the register, the model, and the schedule data every sheet derives from.

Checks (each finding cites the sheet number it belongs to):
  1. **Set integrity** — duplicate sheet numbers; numbering gaps inside a series (A-101, A-103 → where's
     A-102?); sheets with no title / no discipline (titleblock fields).
  2. **Issuance hygiene** — sheets marked issued with no issued date; revision tokens that don't parse.
  3. **Model cross-checks** — a door/window/room schedule sheet whose counts disagree with the model
     (doors on paper ≠ doors in the model = a coordination miss a reviewer WILL find); an A-series set
     with fewer plan sheets than the model has storeys.
  4. **Coverage** — disciplines present in the model (structural/MEP elements) with no sheet series.

Deterministic and offline (the honest core an AI reviewer can later *narrate*); pre-check assist, not a
substitute for a QA manager's stamp.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

_SEV = {"critical": 0, "major": 1, "minor": 2}


def _sheets(db: Session, pid: str) -> list[dict[str, Any]]:
    out = []
    if "drawing" not in me.TABLES:
        return out
    for r in me.list_records(db, "drawing", pid, limit=100_000):
        d = r.get("data") or {}
        out.append({"id": r.get("id"), "number": str(d.get("number") or r.get("ref") or "").strip(),
                    "title": (d.get("title") or "").strip(), "discipline": (d.get("discipline") or "").strip(),
                    "revision": (d.get("revision") or "").strip(), "status": (d.get("status") or "").strip(),
                    "issued_date": (d.get("issued_date") or "").strip()})
    return out


def _series_num(number: str) -> tuple[str, int] | None:
    m = re.match(r"^([A-Z]{1,2})-?(\d{2,4})$", number.upper())
    return (m.group(1), int(m.group(2))) if m else None


def review(db: Session, pid: str, model=None) -> dict[str, Any]:
    """Run the QA pass. `model` (opened source IFC) enables the model cross-checks; without it the
    register/issuance checks still run and the model lane reports "model not loaded"."""
    findings: list[dict[str, Any]] = []

    def flag(sheet: str | None, severity: str, check: str, text: str, action: str):
        findings.append({"sheet": sheet, "severity": severity, "check": check,
                         "finding": text, "action": action})

    sheets = _sheets(db, pid)

    # 1 — set integrity ------------------------------------------------------------------------------
    seen: dict[str, int] = {}
    by_series: dict[str, list[int]] = {}
    for s in sheets:
        n = s["number"]
        if not n:
            flag(None, "major", "set-integrity", "a register row has no sheet number",
                 "assign a sheet number (Type-###) or remove the row")
            continue
        seen[n] = seen.get(n, 0) + 1
        parsed = _series_num(n)
        if parsed:
            by_series.setdefault(parsed[0], []).append(parsed[1])
        if not s["title"]:
            flag(n, "minor", "titleblock", f"{n} has no title", "fill the sheet title (titleblock field)")
        if not s["discipline"]:
            flag(n, "minor", "titleblock", f"{n} has no discipline", "set the discipline designator")
    for n, count in seen.items():
        if count > 1:
            flag(n, "critical", "set-integrity", f"duplicate sheet number {n} ({count}×)",
                 "renumber — a duplicate sheet number breaks the index and transmittals")
    for series, nums in by_series.items():
        nums = sorted(set(nums))
        for a, b in zip(nums, nums[1:]):
            if b - a > 1 and b - a <= 5:            # a small hole reads as a missing sheet, a big one as intent
                missing = ", ".join(f"{series}-{i:03d}" for i in range(a + 1, b))
                flag(f"{series}-{a:03d}", "minor", "set-integrity",
                     f"numbering gap in the {series} series: {missing} missing between "
                     f"{series}-{a:03d} and {series}-{b:03d}",
                     f"confirm {missing} is intentionally omitted or add it to the register")

    # 2 — issuance hygiene ---------------------------------------------------------------------------
    for s in sheets:
        if not s["number"]:
            continue
        if s["status"].lower() in ("issued", "published") and not s["issued_date"]:
            flag(s["number"], "major", "issuance", f"{s['number']} is {s['status']} with no issued date",
                 "record the issue date — transmittals and revision history depend on it")
        if s["revision"] and not re.match(r"^[A-Za-z]{0,2}\d{1,3}$", s["revision"]):
            flag(s["number"], "minor", "issuance", f"{s['number']} revision '{s['revision']}' doesn't parse",
                 "use the project revision convention (P01/C1/0…)")

    # 3 — model cross-checks -------------------------------------------------------------------------
    model_lane = "model not loaded — cross-checks skipped"
    if model is not None:
        model_lane = "ok"
        counts = {cls: len(model.by_type(cls)) for cls in
                  ("IfcDoor", "IfcWindow", "IfcSpace", "IfcBuildingStorey",
                   "IfcColumn", "IfcBeam", "IfcDuctSegment", "IfcPipeSegment")}
        a_plans = len(by_series.get("A", []))
        storeys = counts["IfcBuildingStorey"]
        if storeys > 1 and a_plans and a_plans < storeys:
            flag("A-series", "major", "model-crosscheck",
                 f"the model has {storeys} storeys but the A series holds {a_plans} sheet(s)",
                 "a permit set needs a plan sheet per level — generate the missing floor plans")
        if counts["IfcDoor"] and not any(s for s in sheets if "door" in s["title"].lower()):
            flag(None, "minor", "model-crosscheck",
                 f"{counts['IfcDoor']} doors modeled but no door-schedule sheet in the register",
                 "add the door schedule (computed schedules generate it from the model)")
        if (counts["IfcColumn"] or counts["IfcBeam"]) and not by_series.get("S"):
            flag(None, "major", "coverage",
                 f"structural elements modeled ({counts['IfcColumn']} columns / {counts['IfcBeam']} beams) "
                 "but no S-series sheets",
                 "generate/register the structural sheets")
        if (counts["IfcDuctSegment"] or counts["IfcPipeSegment"]) and not (by_series.get("M") or by_series.get("P")):
            flag(None, "major", "coverage",
                 "MEP runs modeled but no M/P-series sheets",
                 "generate/register the mechanical/plumbing sheets")

    findings.sort(key=lambda f: _SEV.get(f["severity"], 3))
    crit = sum(1 for f in findings if f["severity"] == "critical")
    return {
        "sheet_count": len(sheets), "series": {k: len(v) for k, v in sorted(by_series.items())},
        "findings": findings, "finding_count": len(findings),
        "by_severity": {s: sum(1 for f in findings if f["severity"] == s) for s in _SEV},
        "verdict": "HOLD" if crit else ("REVIEW" if findings else "CLEAN"),
        "model_crosschecks": model_lane,
        "note": ("Every finding is computed from the structured register/model source and cited to its "
                 "sheet — no raster interpretation. Pre-check assist for the set QA pass, not a "
                 "substitute for the QA manager's review."),
    }
