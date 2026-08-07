"""Scope-of-work clause library for contract exhibits.

A library of general / supplementary conditions plus per-CSI-division scope sections, each with
`{{merge}}` tokens filled from the contract + project at render time. Editable. Exhibit A (Scope of
Work) is composed by picking clause ids; the agreement/CO documents pull the conditions clauses.

TWO SOURCES, ON PURPOSE.

  * `_CURATED` below — 14 hand-written clauses carrying `{{merge}}` tokens and a `trade`. These are
    the ones the agreement documents lean on, and their wording has been tuned against the AIA-shaped
    output in `contracts.py`. Hand-edited freely.
  * `scope_clauses.CLAUSES` — 236 clauses imported from the ScopeMaker seed library, division-scoped
    and split into inclusions / exclusions / clarifications. Generated; regenerate rather than bulk-edit.

The imported half is what makes a scope of work actually negotiable. A subcontract argument is almost
never about the general conditions — it is about what *is* and what *is not* in the subcontractor's
number, and the curated 14 had no exclusions at all. 69 of the imported clauses are exclusions.

DIVISIONS COME FROM THE SPINE. `division` is a CSI MasterFormat division key, and the only authority
for those is `aec_data.disciplines.MF_DIVISIONS` (DISC-SSOT). Nothing here re-declares them; the
import below is the assertion, and `test_scope_library.py` fails if a clause names a division the
spine does not have.
"""
from __future__ import annotations

import re
from typing import Any

from aec_data.disciplines import MF_DIVISIONS

from . import scope_clauses

#: Categories that belong to Exhibit A (the scope document) rather than to the agreement body.
#: `contracts.py` uses this to decide what NOT to print into the agreement — before the import there
#: was only "Scope" to exclude, and an exclusion clause leaking into the agreement body would read as
#: the Contractor's own carve-out rather than the Subcontractor's.
EXHIBIT_CATEGORIES = frozenset({"Scope", "Exclusions", "Clarifications"})

#: Trade label -> MasterFormat division. The curated clauses are keyed by trade and the imported ones
#: by division, so one of the two has to be translatable into the other. Explicit rather than derived
#: from `MF_DIVISIONS` names: only "Concrete" happens to match a division title exactly, and guessing
#: the rest from string similarity would silently mis-scope an exhibit.
TRADE_DIVISION: dict[str, str] = {
    "concrete": "03", "masonry": "04", "steel": "05", "metals": "05",
    "carpentry": "06", "roofing": "07", "doors": "08", "glazing": "08",
    "finishes": "09", "drywall": "09", "fire protection": "21",
    "plumbing": "22", "hvac": "23", "mechanical": "23",
    "electrical": "26", "communications": "27", "earthwork": "31", "sitework": "31",
}

_CURATED: list[dict[str, Any]] = [
    # --- general & supplementary conditions (attach to every agreement) ---
    {"id": "gc-coordination", "category": "General Conditions", "title": "Coordination",
     "body": "The Subcontractor shall coordinate its {{trade}} work with the General Contractor and all "
             "other trades on {{project}}, attend weekly coordination meetings, and sequence the work in "
             "accordance with the current project schedule."},
    {"id": "gc-cleanup", "category": "General Conditions", "title": "Cleanup",
     "body": "The Subcontractor shall keep its work areas broom-clean on a daily basis and remove all "
             "{{trade}} debris to the designated container, leaving the work ready for following trades."},
    {"id": "gc-safety", "category": "General Conditions", "title": "Safety",
     "body": "The Subcontractor shall comply with the project safety program and all applicable OSHA "
             "requirements, and shall submit a site-specific safety plan and material SDS prior to mobilization."},
    {"id": "sc-insurance", "category": "Supplementary Conditions", "title": "Insurance & Indemnity",
     "body": "The Subcontractor shall maintain commercial general liability, workers' compensation, and "
             "umbrella coverage in the amounts required by the Contract Documents, naming {{owner}} and the "
             "General Contractor as additional insureds, and shall indemnify them to the fullest extent "
             "permitted by law for claims arising out of the {{trade}} work."},
    {"id": "sc-payment", "category": "Supplementary Conditions", "title": "Payment & Retainage",
     "body": "Progress payments shall be subject to {{retainage}} retainage and conditioned upon receipt of "
             "a conforming pay application, current lien waivers, and an updated schedule. Final payment "
             "follows acceptance of the work and submission of all closeout documents."},
    {"id": "sc-warranty", "category": "Supplementary Conditions", "title": "Warranty",
     "body": "The Subcontractor warrants all {{trade}} work and materials against defects for one (1) year "
             "from the date of Substantial Completion of the project."},
    {"id": "sc-changes", "category": "Supplementary Conditions", "title": "Changes in the Work",
     "body": "No change to the scope, price, or schedule of the {{trade}} work shall be valid unless "
             "authorized in writing by a fully executed change order. Work performed without such "
             "authorization is at the Subcontractor's risk."},
    # --- per-CSI-division scope sections (compose Exhibit A) ---
    {"id": "div03-concrete", "category": "Scope", "trade": "Concrete", "title": "Division 03 — Concrete",
     "body": "Furnish all labor, materials, equipment, formwork, reinforcing, placement, finishing, and "
             "curing for cast-in-place concrete for {{project}}, including footings, foundation walls, "
             "slabs-on-grade, and elevated slabs as shown on the Contract Documents."},
    {"id": "div05-steel", "category": "Scope", "trade": "Steel", "title": "Division 05 — Structural Steel",
     "body": "Furnish and erect structural steel framing, connections, metal decking, and miscellaneous "
             "metals for {{project}}, including shop drawings, fabrication, delivery, and field "
             "bolting/welding in accordance with AISC standards."},
    {"id": "div09-finishes", "category": "Scope", "trade": "Finishes", "title": "Division 09 — Finishes",
     "body": "Furnish all labor and materials for gypsum board assemblies, taping and finishing, painting, "
             "and floor finishes for {{project}} in accordance with the finish schedule."},
    {"id": "div22-plumbing", "category": "Scope", "trade": "Plumbing", "title": "Division 22 — Plumbing",
     "body": "Furnish and install domestic water, sanitary, vent, and storm piping, fixtures, and equipment "
             "for {{project}} in accordance with the plumbing drawings and specifications."},
    {"id": "div23-hvac", "category": "Scope", "trade": "HVAC", "title": "Division 23 — HVAC",
     "body": "Furnish and install HVAC equipment, ductwork, piping, controls, and testing & balancing for "
             "{{project}} in accordance with the mechanical drawings and specifications."},
    {"id": "div26-electrical", "category": "Scope", "trade": "Electrical", "title": "Division 26 — Electrical",
     "body": "Furnish and install electrical service, distribution, branch wiring, lighting, fire-alarm "
             "rough-in, and devices for {{project}} in accordance with the electrical drawings."},
]

#: The curated clauses first so a hand-tuned wording wins ordering ties, then the imported library.
CLAUSES: list[dict[str, Any]] = [*_CURATED, *scope_clauses.CLAUSES]

_BY_ID = {c["id"]: c for c in CLAUSES}


def division_for_trade(trade: str | None) -> str | None:
    """Trade label -> MasterFormat division, or None when we cannot say.

    Returns None rather than guessing. A wrong division silently produces a plausible-looking exhibit
    full of the wrong trade's inclusions, which is worse than an exhibit that falls back to the
    whole library and is obviously in need of editing.
    """
    if not trade:
        return None
    return TRADE_DIVISION.get(trade.strip().lower())


def division_name(division: str | None) -> str | None:
    """`"22"` -> `"Plumbing"`, straight from the spine. None for a universal clause.

    Reads `MF_DIVISIONS` rather than carrying its own titles: a second copy of the division names is
    exactly the duplication DISC-SSOT exists to prevent, and it would drift the first time a title
    was corrected in one place.
    """
    return MF_DIVISIONS.get(division) if division else None


def library(division: str | None = None) -> list[dict[str, Any]]:
    """Catalog for the exhibit-composer UI (no bodies). Optionally narrowed to one division."""
    return [{"id": c["id"], "category": c["category"], "title": c["title"],
             "trade": c.get("trade"), "division": c.get("division"),
             "default": bool(c.get("default", False))}
            for c in CLAUSES
            if division is None or c.get("division") in (division, None)]


def merge(text: str, ctx: dict[str, Any]) -> str:
    """Replace {{token}} with ctx[token]; leave unknown tokens as-is."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text)


def clauses_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    return [_BY_ID[i] for i in ids if i in _BY_ID]


def exhibit_clauses(clause_ids: list[str] | None, trade: str | None) -> list[dict[str, Any]]:
    """The clauses that belong in Exhibit A. **The** authority — every renderer reads this one.

    Extracted when the third caller appeared, which was the agreed trigger: the PDF and the preview
    route each applied this filter inline, and the DOCX export would have been a third copy. Two
    copies is how the original defect happened — the route filtered, `_exhibit_flowables` did not, and
    a plumbing subcontract printed 31 clauses into a signed PDF against 11 in the preview, with 20 of
    them duplicated from Article 3.

    The filter is unconditional, including over an explicitly supplied `clause_ids`: a caller chooses
    *which* clauses, never which document a category belongs in. Exhibit A owns Scope, Exclusions and
    Clarifications; the agreement body owns the conditions; neither owns both.

    Order is `default_ids`' order, or the caller's if they supplied one — this selects, it does not
    sort, because a renumbered exhibit invalidates clause references already cited in negotiation.
    """
    ids = clause_ids or default_ids(trade)
    return [c for c in clauses_by_ids(ids) if c["category"] in EXHIBIT_CATEGORIES]


def numbered(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a stable `number` (`1.`, `1.1`, `1.2`, `2.`, ...) grouped by category.

    A subcontract exhibit is argued clause by clause, so "we agreed to 3.2" has to point at exactly
    one sentence. Renderer-side list numbering cannot give that — it restarts per list and is lost on
    export — so the label is computed once here and printed as literal text, which is what makes the
    PDF, the JSON and the UI agree. Order in equals order out; this does not sort.
    """
    out: list[dict[str, Any]] = []
    seen: list[str] = []
    n = 0
    for c in clauses:
        cat = c["category"]
        if cat not in seen:
            seen.append(cat)
            n = 0
        n += 1
        out.append({**c, "number": f"{seen.index(cat) + 1}.{n}", "section": f"{seen.index(cat) + 1}."})
    return out


def default_ids(trade: str | None) -> list[str]:
    """Sensible default Exhibit A: the trade's division scope + the standard conditions.

    Kept backwards-compatible with the curated-only behaviour: an unrecognised or absent trade still
    falls back to every Scope clause plus the conditions. What changed is that a RECOGNISED trade now
    narrows to that MasterFormat division, because returning all 147 imported inclusions for a
    plumbing subcontract would produce an exhibit nobody reads — and an exhibit nobody reads is how a
    scope gap reaches a jobsite.
    """
    div = division_for_trade(trade)
    if div:
        scope = [c["id"] for c in CLAUSES
                 if c["category"] in EXHIBIT_CATEGORIES
                 and (c.get("division") == div
                      or (c.get("trade", "") or "").lower() == (trade or "").lower())]
    else:
        scope = [c["id"] for c in CLAUSES if c["category"] in EXHIBIT_CATEGORIES
                 and (not trade or (c.get("trade", "") or "").lower() == (trade or "").lower())]
        if not scope:
            scope = [c["id"] for c in CLAUSES if c["category"] in EXHIBIT_CATEGORIES]
    conditions = [c["id"] for c in CLAUSES if c["category"] not in EXHIBIT_CATEGORIES]
    return scope + conditions
