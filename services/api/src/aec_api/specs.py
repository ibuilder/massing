"""Specifications → submittals. Builds the **spec-driven submittal log** from the project's
`spec_section` records (CSI SectionFormat Part 1 "Submittals" article → required submittal items,
typed), and reconciles it against the submittals actually logged to surface **missing submittals**
per spec section. Pure helpers + a deterministic submittal-type classifier (also used by the AI
extractor's offline fallback). No writes."""
from __future__ import annotations

import re
from typing import Any

# canonical submittal types (match the `submittal` module's `type` options) + detection keywords
SUBMITTAL_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("Shop Drawing", ("shop drawing", "shop dwg", "fabrication drawing", "erection drawing")),
    ("Product Data", ("product data", "manufacturer's data", "manufacturer data", "catalog", "cut sheet", "data sheet")),
    ("Sample", ("sample", "physical sample", "color sample")),
    ("Mock-up", ("mock-up", "mockup", "mock up")),
    ("Certificate", ("certificate", "certification", "certificate of compliance", "mill certificate")),
    ("Test Report", ("test report", "test result", "testing report", "lab report")),
    ("Calculations", ("calculation", "design calc", "structural calc", "engineering calc")),
    ("O&M Manual", ("o&m", "operation and maintenance", "operations and maintenance", "maintenance manual")),
    ("Warranty", ("warranty", "guarantee")),
]
_DEFAULT_TYPE = "Product Data"
_SECTION_RE = re.compile(r"\b(\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?)\b")   # MasterFormat e.g. 03 30 00


def _has_type_keyword(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for _, kws in SUBMITTAL_TYPES for k in kws)


def classify_type(text: str) -> str:
    t = (text or "").lower()
    for name, kws in SUBMITTAL_TYPES:
        if any(k in t for k in kws):
            return name
    return _DEFAULT_TYPE


def parse_section_number(text: str) -> str | None:
    m = _SECTION_RE.search(text or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def parse_required_submittals(text: str) -> list[dict[str, str]]:
    """Split a Part 1 'Submittals' article into individual required items, each typed by keyword.
    Handles bullet/numbered/semicolon/newline-delimited lists from a pasted spec."""
    if not text:
        return []
    # normalize list delimiters: numbered (1., A., 1.2.A), bullets, semicolons -> newlines
    norm = re.sub(r"(?m)^\s*(?:[-*•]|\(?[0-9A-Za-z]\)|[0-9A-Za-z]\.)\s+", "\n", text)
    norm = norm.replace(";", "\n")
    items = []
    for raw in norm.splitlines():
        line = raw.strip(" \t.-")
        if len(line) < 4:
            continue
        # keep only real submittal items: a "Type: description" line or one naming a submittal type.
        # this excludes the SECTION header and the "SUBMITTALS" article header (no colon, no type word).
        if ":" not in line and not _has_type_keyword(line):
            continue
        if re.match(r"(?i)^section\s+\d", line):                  # "SECTION 03 30 00 - …" header
            continue
        items.append({"title": line[:160], "type": classify_type(line)})
    return items


def _d(r: dict) -> dict:
    return r.get("data") or r


def submittal_log(db, pid: str) -> dict[str, Any]:
    """The spec-driven submittal log: required submittals derived per spec section vs the submittals
    actually logged (matched by section number), with missing-submittal gaps."""
    from . import modules as me
    specs = me.list_records(db, "spec_section", pid, limit=100000) if "spec_section" in me.TABLES else []
    subs = me.list_records(db, "submittal", pid, limit=100000) if "submittal" in me.TABLES else []

    # index logged submittals by normalized spec section number
    logged_by_section: dict[str, int] = {}
    for s in subs:
        sec = parse_section_number((_d(s).get("spec_section") or "")) or (_d(s).get("spec_section") or "").strip()
        if sec:
            logged_by_section[sec] = logged_by_section.get(sec, 0) + 1

    rows, by_division = [], {}
    required_total = missing_total = 0
    by_type: dict[str, int] = {}
    for sp in specs:
        d = _d(sp)
        sec = (d.get("section_number") or "").strip()
        div = (d.get("division") or (sec.split()[0] + " - Division" if sec else "(unassigned)")).strip()
        req = parse_required_submittals(d.get("submittals_required") or "")
        for item in req:
            by_type[item["type"]] = by_type.get(item["type"], 0) + 1
        required_total += len(req)
        by_division[div] = by_division.get(div, 0) + len(req)
        logged = logged_by_section.get(parse_section_number(sec) or sec, 0)
        missing = max(0, len(req) - logged)
        missing_total += missing
        rows.append({
            "ref": sp.get("ref"), "section_number": sec, "title": d.get("title"), "division": div,
            "required_count": len(req), "logged_count": logged, "missing_count": missing,
            "responsible": d.get("responsible"),
            "required": req,
        })
    return {
        "spec_count": len(specs), "required_total": required_total,
        "logged_total": sum(logged_by_section.values()), "missing_total": missing_total,
        "coverage_pct": round(100 * (required_total - missing_total) / required_total, 1) if required_total else None,
        "by_type": by_type,
        "by_division": dict(sorted(by_division.items())),
        "rows": sorted(rows, key=lambda r: (r.get("section_number") or "")),
    }
