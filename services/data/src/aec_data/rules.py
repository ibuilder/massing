"""W11 · Track D — the detail/spec rule engine (D3) + a seed rule library incl. the IBC window-flashing
case (D7).

The brain that turns model state into construction-document content. Rules are **IDS-shaped**:
an `applies` block (applicability facets — IFC entity, predefined type, a property on the element, or a
relationship-context facet like "fills an opening in an exterior wall") and an `attach` block (the content
bundle — classification codes + detail/instruction documents). When a rule matches an element, its bundle
is written through the Track-D carrier layer (`classify` + `attach_document`), IFC-natively and GUID-stable.

The *same* rule shape doubles as IDS QA validation ("every exterior window shall carry 08 51 00 + a
flashing detail") — author-time attach, QA-time check.

Licensing: pure ifcopenshell (LGPL). Code references below are the researched IBC 2021 / ASTM / AAMA
citations; they are facts, not copyrightable text.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell


def _host_wall(el):
    """The wall a door/window fills (via IfcRelFillsElement → opening → IfcRelVoidsElement → wall), or
    None. This is the relationship-context traversal an IDS `partOf` facet expresses."""
    for rel in (getattr(el, "FillsVoids", None) or []):
        op = getattr(rel, "RelatingOpeningElement", None)
        for vrel in (getattr(op, "VoidsElements", None) or []):
            host = getattr(vrel, "RelatingBuildingElement", None)
            if host is not None:
                return host
    return None


def _prop(el, pset: str, prop: str):
    import ifcopenshell.util.element as ue

    return (ue.get_pset(el, pset) or {}).get(prop)


def _is_truthy(v) -> bool:
    return v is True or str(v).strip().upper() in {"TRUE", "YES", "1", "T"}


def _matches(el, applies: dict) -> bool:
    """Evaluate a rule's applicability facets against one element (all facets AND-combined)."""
    if (ent := applies.get("entity")) and not el.is_a(ent):
        return False
    if (pd := applies.get("predefined")) and getattr(el, "PredefinedType", None) != pd:
        return False
    # relationship-context: the element fills an opening in an *external* wall
    if applies.get("host_external"):
        host = _host_wall(el)
        if host is None or not _is_truthy(_prop(host, "Pset_WallCommon", "IsExternal")):
            return False
    if applies.get("host_fire_rated"):
        host = _host_wall(el)
        if host is None or not (_prop(host, "Pset_WallCommon", "FireRating") or "").strip():
            return False
    # a property facet on the element itself: {pset, prop, value?}
    pf = applies.get("property")
    if pf:
        val = _prop(el, pf["pset"], pf["prop"])
        if val is None:
            return False
        if "value" in pf and str(val).strip().upper() != str(pf["value"]).strip().upper():
            return False
    return True


def _reworded_for_edition(rules: list[dict], ibc_edition: str | None) -> list[dict]:
    """CODE-3: reword the seed's `IBC 20xx` detail citations to the project's **resolved** adopted IBC
    edition, so an exterior window cites the *actually-adopted* section rather than the seed's 2021. Only
    the edition year in a document `description`/instruction changes — facts of law, not the seed content."""
    if not ibc_edition:
        return rules
    import re
    ed = str(ibc_edition).strip()
    out: list[dict] = []
    for r in rules:
        docs = (r.get("attach") or {}).get("document")
        if not docs:
            out.append(r)
            continue
        r2 = {**r, "attach": {**r["attach"], "document": [
            ({**d, "description": re.sub(r"IBC 20\d\d", f"IBC {ed}", d["description"])} if d.get("description")
             else d) for d in docs]}}
        out.append(r2)
    return out


def apply_rules(model: ifcopenshell.file, rules: list[dict] | None = None,
                ibc_edition: str | None = None) -> dict:
    """D3: evaluate the rule set over every element and write each matched rule's content bundle
    (classification codes + detail/instruction documents) via the Track-D carriers. Idempotent-ish —
    classify/attach_document dedupe, so re-running doesn't pile up. `ibc_edition` (CODE-3) rewords the
    citations to the project's resolved adopted IBC edition. Returns a summary of what fired."""
    from . import detailing

    rules = _reworded_for_edition(rules if rules is not None else SEED_RULES, ibc_edition)
    applied: list[dict] = []
    codes_written = docs_written = 0
    for el in model.by_type("IfcElement"):
        for rule in rules:
            if not _matches(el, rule.get("applies", {})):
                continue
            bundle = rule.get("attach", {})
            for c in bundle.get("classify", []):
                codes_written += detailing.classify(model, [el.GlobalId], c["system"], c["code"],
                                                    c.get("title"), c.get("edition"))
            for d in bundle.get("document", []):
                docs_written += detailing.attach_document(
                    model, [el.GlobalId], d["name"], d.get("location"), d.get("description"),
                    d.get("identification"), d.get("purpose"))
            applied.append({"rule": rule["name"], "guid": el.GlobalId,
                            "ifc_class": el.is_a(), "name": getattr(el, "Name", None) or el.is_a()})
    return {"rules_evaluated": len(rules), "matches": len(applied), "ibc_edition": ibc_edition,
            "codes_written": codes_written, "documents_written": docs_written, "applied": applied}


def validate_rules(model: ifcopenshell.file, rules: list[dict] | None = None) -> dict:
    """The same rules as IDS-style QA: for every element a rule *applies* to, check its content bundle
    is actually present (the classification codes are carried). Returns non-compliant elements — the
    'components missing a keynote/spec' pre-flight the approvability check builds on."""
    from . import detailing

    rules = rules if rules is not None else SEED_RULES
    gaps: list[dict] = []
    for el in model.by_type("IfcElement"):
        for rule in rules:
            if not _matches(el, rule.get("applies", {})):
                continue
            det = detailing.element_detailing(model, el.GlobalId)
            have_codes = {(c["system"], c["code"]) for c in det["classifications"]}
            for c in rule.get("attach", {}).get("classify", []):
                if (c["system"], c["code"]) not in have_codes:
                    gaps.append({"rule": rule["name"], "guid": el.GlobalId,
                                 "name": getattr(el, "Name", None) or el.is_a(),
                                 "missing": f"{c['system']} {c['code']}"})
    return {"rules_evaluated": len(rules), "gaps": len(gaps), "elements": gaps}


# ── Seed rule library ────────────────────────────────────────────────────────────────────────────
# Content researched from IBC 2021 / ASTM / AAMA / ICC A117.1 (citations are facts). Each rule attaches
# UniFormat (keynote/element) + MasterFormat (spec) codes and the governing detail + install instruction.

_WIN_FLASHING_INSTRUCTION = (
    "Window flashing per IBC 2021 §1404.4 & ASTM E2112. Install sill pan with end dams sloped to "
    "exterior; shingle-lap jamb & head flashing over the WRB per §1403. Self-adhered flashing to comply "
    "with AAMA 711. WRB to lap over head flashing; leave sill flange unsealed for drainage."
)

SEED_RULES: list[dict[str, Any]] = [
    {
        "name": "exterior-window-flashing",
        "applies": {"entity": "IfcWindow", "host_external": True},
        "attach": {
            "classify": [
                {"system": "UniFormat", "code": "B2020", "title": "Exterior Windows"},
                {"system": "MasterFormat", "code": "08 51 00", "title": "Metal Windows", "edition": "2020"},
            ],
            "document": [
                {"name": "Window Flashing @ Punched Opening (sill pan / jamb / head)",
                 "identification": "A-541/3", "location": "details/window_flashing.svg",
                 "description": "IBC 2021 §1404.4 / ASTM E2112 / AAMA 711"},
                {"name": "Window Flashing Installation Sequence", "identification": "INST-0851-01",
                 "location": "docs/window_flashing_install.md", "purpose": "INSTRUCTION",
                 "description": _WIN_FLASHING_INSTRUCTION},
            ],
        },
    },
    {
        "name": "exterior-door-flashing",
        "applies": {"entity": "IfcDoor", "host_external": True},
        "attach": {
            "classify": [
                {"system": "UniFormat", "code": "B2010", "title": "Exterior Doors"},
                {"system": "MasterFormat", "code": "08 11 00", "title": "Metal Doors and Frames", "edition": "2020"},
            ],
            "document": [
                {"name": "Exterior Door Sill Pan & Jamb Flashing", "identification": "A-542/1",
                 "location": "details/door_flashing.svg",
                 "description": "IBC 2021 §1404.4 / ASTM E2112; sill pan with end dams, sloped to exterior"},
            ],
        },
    },
    {
        "name": "fire-rated-wall-keynote",
        "applies": {"entity": "IfcWall", "property": {"pset": "Pset_WallCommon", "prop": "FireRating"}},
        "attach": {
            "classify": [
                {"system": "MasterFormat", "code": "09 21 16", "title": "Gypsum Board Assemblies", "edition": "2020"},
            ],
            "document": [
                {"name": "Rated Partition Assembly (cite UL/GA design no.)", "identification": "A-551/1",
                 "location": "details/rated_partition.svg",
                 "description": "Fire-resistance-rated assembly per IBC 2021 Table 601/602; tag with UL design "
                                "or GA file no. (e.g. UL U419 / GA WP 1731) per tested build-up."},
            ],
        },
    },
]
