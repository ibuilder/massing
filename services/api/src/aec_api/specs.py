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


#: Spec-section states where the section is WITHDRAWN from the manual. A void section specifies
#: nothing: it requires no submittals, and it is not a hole in the spec-to-budget chain.
#:
#: This is a CONSTANT rather than an inline check because `spec_section` has two independent readers
#: — `specs.submittal_log` here and `spine.traceability`, which imports it — and a rule with two
#: places to rot is a rule that will disagree with itself. `under_revision` is deliberately NOT
#: here: a section being revised is still the section in force.
SPEC_SECTION_WITHDRAWN = ("void",)


def submittal_log(db, pid: str) -> dict[str, Any]:
    """The spec-driven submittal log: required submittals derived per spec section vs the submittals
    actually logged (matched by section number), with missing-submittal gaps.

    A VOID section still appears as a row — deleting it from the log would read as a section nobody
    wrote rather than as one somebody withdrew — but it requires nothing and can be missing nothing.
    Measured before the fix on a manual holding one live section requiring 2 submittals and one
    VOID section requiring 3: `required_total: 5`, `missing_total: 5`, and `by_division` advertised
    "09 - Finishes": 3 for a section that had been deleted. Three of those five missing-submittal
    gaps were work orders against a section nobody has to build.
    """
    from . import modules as me
    specs = me.list_records(db, "spec_section", pid, limit=100000) if "spec_section" in me.TABLES else []
    subs = me.list_records(db, "submittal", pid, limit=100000) if "submittal" in me.TABLES else []

    # index logged submittals by normalized spec section number
    logged_by_section: dict[str, int] = {}
    for s in subs:
        sec = parse_section_number(_d(s).get("spec_section") or "") or (_d(s).get("spec_section") or "").strip()
        if sec:
            logged_by_section[sec] = logged_by_section.get(sec, 0) + 1

    rows, by_division = [], {}
    required_total = missing_total = 0
    by_type: dict[str, int] = {}
    withdrawn_refs = []
    enforced = 0
    # Section keys claimed by withdrawn vs enforced rows. Kept separately because `logged_total` is
    # summed over `logged_by_section` (submittal-side), not over the rows, so it needs its own
    # exclusion — see the note at the return.
    withdrawn_keys: set[str] = set()
    enforced_keys: set[str] = set()
    for sp in specs:
        d = _d(sp)
        st = sp.get("workflow_state")
        sec = (d.get("section_number") or "").strip()
        div = (d.get("division") or (sec.split()[0] + " - Division" if sec else "(unassigned)")).strip()
        req = parse_required_submittals(d.get("submittals_required") or "")
        withdrawn = st in SPEC_SECTION_WITHDRAWN
        logged = logged_by_section.get(parse_section_number(sec) or sec, 0)
        key = parse_section_number(sec) or sec
        if withdrawn:
            # Listed, with what it USED to ask for visible in `required`, but contributing to no
            # total: a withdrawn section demands nothing and can therefore be missing nothing.
            withdrawn_refs.append({"ref": sp.get("ref"), "section_number": sec,
                                   "title": d.get("title"), "would_require": len(req)})
            withdrawn_keys.add(key)
            missing = 0
        else:
            enforced += 1
            enforced_keys.add(key)
            for item in req:
                by_type[item["type"]] = by_type.get(item["type"], 0) + 1
            required_total += len(req)
            by_division[div] = by_division.get(div, 0) + len(req)
            missing = max(0, len(req) - logged)
            missing_total += missing
        rows.append({
            "ref": sp.get("ref"), "section_number": sec, "title": d.get("title"), "division": div,
            "state": st, "withdrawn": withdrawn,
            "required_count": 0 if withdrawn else len(req), "logged_count": logged,
            "missing_count": missing,
            "responsible": d.get("responsible"),
            "required": req,
        })
    return {
        # `enforced_spec_count + len(withdrawn_excluded) == spec_count`; every total below is taken
        # over the enforced sections only, so the response reconciles with its own row list.
        "spec_count": len(specs), "enforced_spec_count": enforced,
        "withdrawn_excluded": withdrawn_refs,
        "required_total": required_total,
        # `logged_total` is summed submittal-side, so filtering the ROWS did not move it: a
        # submittal logged against a WITHDRAWN section still counted as logged while that section's
        # `required` did not — the fourth time in this class that a count derived from a filtered
        # set failed to move with it, and the second found by review rather than by us.
        #
        # Excluded by section KEY, and only for keys no enforced row also claims: two rows can carry
        # the same section number (one withdrawn, one reissued), and dropping the key outright would
        # silently discard the live row's logged submittals too.
        #
        # ORPHANS ARE DELIBERATELY KEPT. Accumulating `logged` per enforced row instead — the
        # smaller patch — would also drop submittals logged against a section number that matches no
        # spec row at all. Those are still submittals somebody logged; they belong in `logged_total`
        # even though they appear in no row. That is why this sums the dict rather than the rows.
        "logged_total": sum(v for k, v in logged_by_section.items()
                            if k not in (withdrawn_keys - enforced_keys)),
        "missing_total": missing_total,
        "coverage_pct": round(100 * (required_total - missing_total) / required_total, 1) if required_total else None,
        "by_type": by_type,
        "by_division": dict(sorted(by_division.items())),
        "rows": sorted(rows, key=lambda r: (r.get("section_number") or "")),
    }
