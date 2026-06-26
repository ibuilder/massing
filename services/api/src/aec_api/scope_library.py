"""Scope-of-work clause library for contract exhibits — the procore-exhibit-generator concept.

A starter library of general / supplementary conditions + per-CSI-division scope sections, each with
`{{merge}}` tokens filled from the contract + project at render time. Editable. Exhibit A (Scope of
Work) is composed by picking clause ids; the agreement/CO documents pull the conditions clauses.
"""
from __future__ import annotations

import re
from typing import Any

CLAUSES: list[dict[str, Any]] = [
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

_BY_ID = {c["id"]: c for c in CLAUSES}


def library() -> list[dict[str, Any]]:
    """Catalog for the exhibit-composer UI (no bodies)."""
    return [{"id": c["id"], "category": c["category"], "title": c["title"], "trade": c.get("trade")} for c in CLAUSES]


def merge(text: str, ctx: dict[str, Any]) -> str:
    """Replace {{token}} with ctx[token]; leave unknown tokens as-is."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text)


def clauses_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    return [_BY_ID[i] for i in ids if i in _BY_ID]


def default_ids(trade: str | None) -> list[str]:
    """Sensible default Exhibit A: the matching trade scope (or all scopes) + the standard conditions."""
    scope = [c["id"] for c in CLAUSES if c["category"] == "Scope"
             and (not trade or (c.get("trade", "").lower() == (trade or "").lower()))]
    if not scope:
        scope = [c["id"] for c in CLAUSES if c["category"] == "Scope"]
    conditions = [c["id"] for c in CLAUSES if c["category"] != "Scope"]
    return scope + conditions
