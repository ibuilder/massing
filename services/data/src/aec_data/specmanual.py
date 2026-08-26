"""D6 — the 3-part MasterFormat **project manual** (the spec book that accompanies the drawings).

Groups the model's elements by their MasterFormat **work-result** classification (attached via Track-D
`classify`), rolls them up into CSI **divisions → sections**, and frames each section in the CSI
**SectionFormat** 3-part shape: Part 1 General, Part 2 Products (the element types + materials actually
in that section), Part 3 Execution (the installation instructions attached to those elements via
`IfcRelAssociatesDocument`, or a manufacturer-instructions fallback). This closes the loop from
"classify an element + attach its detail" to "a spec section writes itself."

Output is structured data (divisions/sections/parts) plus a plain-text rendering for a downloadable manual.
Pre-check assist — a real project manual is authored by the spec writer; this seeds it from the model.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell.util.element as ue

# CSI MasterFormat division numbers → titles — the one canonical table (shared with aec_api via the
# low-level discipline data), the 2-digit prefix of a work-result code.
from .disciplines import MF_DIVISIONS as _DIVISIONS  # noqa: E402

#: Uniclass 2015 TABLE codes — the alpha prefix a Uniclass code starts with. Not a code dictionary:
#: it names the twelve tables so a Uniclass manual groups under "Products" rather than under
#: "Unassigned", which is what `MF_DIVISIONS` returns for every non-numeric prefix.
#:
#: Added 2026-08-26 with the auto-detection below. Grouping Uniclass codes through a CSI division
#: table is not merely unhelpful, it MISDESCRIBES: `MF_DIVISIONS.get("Pr")` misses and the section
#: is filed under a division title that asserts something the code never said.
UNICLASS_TABLES: dict[str, str] = {
    "Co": "Complexes", "En": "Entities", "Ac": "Activities", "SL": "Spaces / Locations",
    "EF": "Elements / Functions", "Ss": "Systems", "Pr": "Products", "TE": "Tools & Equipment",
    "PM": "Project Management", "FI": "Form of Information", "RO": "Roles", "Zz": "CAD",
}

#: Systems whose codes are CSI-numeric and therefore roll up through `MF_DIVISIONS`.
_NUMERIC_CODE_SYSTEMS = ("MasterFormat", "OmniClass")


def _division(code: str, system: str = "MasterFormat") -> str:
    """The grouping key for one code, in the vocabulary of ITS OWN system.

    MasterFormat and OmniClass are numeric, so the first two digits are the division. Uniclass codes
    are `Pr_20_76_51` — the table is the alpha prefix, and taking `[:2]` of a code like `SL_25`
    happens to work while taking it of `Pr_20_76_51` also does, but only by coincidence of length.
    Splitting on the separator says what is meant.
    """
    c = (code or "").strip()
    if system in _NUMERIC_CODE_SYSTEMS or c[:2].isdigit():
        return c[:2]
    return c.split("_", 1)[0] or c[:2]


def _division_title(div: str, system: str) -> str:
    """The division/table title, or an honest blank rather than a borrowed one."""
    if system in _NUMERIC_CODE_SYSTEMS or div[:2].isdigit():
        return _DIVISIONS.get(div, "Unassigned")
    return UNICLASS_TABLES.get(div) or f"Table {div}" if div else "Unassigned"


def _rel_system(ref) -> str | None:
    """The classification SYSTEM a reference belongs to, walking the `ReferencedSource` chain.

    Factored out so `classification_systems`, `project_manual` and `element_codes` cannot drift into
    three answers to "which system is this in" — the same rule `_resolve_field` follows elsewhere in
    the codebase for "what is a field".
    """
    src = getattr(ref, "ReferencedSource", None)
    while src is not None and src.is_a("IfcClassificationReference"):
        src = getattr(src, "ReferencedSource", None)
    if src is not None and getattr(src, "Name", None):
        return str(src.Name)
    # A bare IfcClassification attached directly (a whole-project statement) names itself.
    if ref is not None and ref.is_a("IfcClassification") and getattr(ref, "Name", None):
        return str(ref.Name)
    return None


def element_codes(model, system: str | None = None) -> dict[str, str]:
    """`{GlobalId: classification code}` for every element the model classifies, in one system.

    R36-VIEWER-SUBAPP — the keynote → spec section link. A keynote on a section says what an assembly
    IS (`200mm CONCRETE WALL`, built from class + material + measured thickness); the spec section
    says what governs it. Nothing joined the two, so a reader had to know the mapping by heart.

    Keyed by **GlobalId**, which is the only identity that survives a re-tessellation or a reload —
    the same rule the markup keys follow. Both an element and its TYPE may be classified, and a type
    classification covers every occurrence of it, so occurrences inherit from their type unless
    classified directly. A direct classification wins: it is the more specific statement.
    """
    system = resolve_system(model, system)
    direct: dict[str, str] = {}
    by_type: dict[int, str] = {}
    for rel in model.by_type("IfcRelAssociatesClassification"):
        ref = rel.RelatingClassification
        if _rel_system(ref) != system:
            continue
        code = (getattr(ref, "Identification", None) or "").strip()
        if not code:
            continue
        for obj in (getattr(rel, "RelatedObjects", None) or []):
            guid = getattr(obj, "GlobalId", None)
            if obj.is_a("IfcTypeObject") or obj.is_a("IfcTypeProduct"):
                by_type[obj.id()] = code
            elif guid:
                direct[str(guid)] = code
    if not by_type:
        return direct
    # Occurrences inherit their type's code. Done second so a direct classification is never
    # overwritten by the broader statement its type makes.
    out: dict[str, str] = {}
    for el in model.by_type("IfcProduct"):
        guid = getattr(el, "GlobalId", None)
        if not guid:
            continue
        t = ue.get_type(el)
        if t is not None and t.id() in by_type:
            out[str(guid)] = by_type[t.id()]
    out.update(direct)
    return out


def classification_systems(model) -> dict[str, int]:
    """Every classification system the model actually uses, and how many references each has.

    **This exists because nothing could see that the answer was empty for the right reason.**
    `project_manual` defaulted to MasterFormat and its only caller passed nothing, so a model
    classified under any other system produced zero sections that looked exactly like a model with no
    classifications at all. Measured 2026-08-26 across this repository's 58 tracked IFC files: 57
    declare **Uniclass**, one **OmniClass**, and **none declare MasterFormat** — so the spec surface
    answered nothing for every model the project ships, while reporting no error.
    """
    out: dict[str, int] = {}
    for rel in model.by_type("IfcRelAssociatesClassification"):
        ref = rel.RelatingClassification
        name = _rel_system(ref)
        if not name:
            continue
        # Only count references that carry a code — a system declared with nothing classified under
        # it would otherwise win the auto-pick below and produce an empty manual.
        if ref.is_a("IfcClassificationReference") and not (getattr(ref, "Identification", None) or "").strip():
            continue
        if ref.is_a("IfcClassification"):
            continue
        out[str(name)] = out.get(str(name), 0) + 1
    return out


def resolve_system(model, system: str | None = None) -> str:
    """The system to build the manual for: the caller's choice, else the one the MODEL uses.

    MasterFormat wins when present because it is the North American spec convention this module was
    written around and its division titles are the ones `MF_DIVISIONS` holds. Otherwise the most-used
    system present wins, ties broken by name so the answer is stable across runs. Falls back to
    MasterFormat when the model carries no classifications at all — an empty manual for a model with
    nothing classified is the honest answer, and it keeps the old default for that case.
    """
    if system:
        return system
    present = classification_systems(model)
    if not present:
        return "MasterFormat"
    for preferred in _NUMERIC_CODE_SYSTEMS:
        if preferred in present:
            return preferred
    return sorted(present, key=lambda n: (-present[n], n))[0]


def _element_materials(el) -> list[str]:
    """All distinct material names on an element. Handles a plain IfcMaterial, an IfcMaterialList, and the
    layer/profile/constituent **sets** (and their *usages*, which is what a real wall/beam actually carries —
    an IfcMaterialLayerSetUsage → IfcMaterialLayerSet → layers). Empty when there's no material."""
    try:
        m = ue.get_material(el)
    except Exception:  # noqa: BLE001
        return []
    if m is None:
        return []
    out: list[str] = []
    n = getattr(m, "Name", None)                 # a plain IfcMaterial has .Name; usages/sets don't
    if n:
        out.append(str(n))
    s = getattr(m, "ForLayerSet", None) or getattr(m, "ForProfileSet", None) or m   # usage → its set
    for coll in ("MaterialLayers", "MaterialProfiles", "MaterialConstituents"):
        for item in (getattr(s, coll, None) or []):
            nm = getattr(getattr(item, "Material", None), "Name", None)
            if nm:
                out.append(str(nm))
    for item in (getattr(s, "Materials", None) or []):        # IfcMaterialList holds IfcMaterial directly
        nm = getattr(item, "Name", None)
        if nm:
            out.append(str(nm))
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def project_manual(model, system: str | None = None) -> dict[str, Any]:
    """Assemble the 3-part project manual from the model's classifications + attached docs.

    `system` defaults to **what the model actually uses** (`resolve_system`) rather than to
    MasterFormat. The old default was a filter on the very thing being looked for: ask a Uniclass
    model for its MasterFormat sections and the honest answer is "none", which is indistinguishable
    from "this model is unclassified" and was reported the same way.
    """
    system = resolve_system(model, system)
    sections: dict[str, dict[str, Any]] = {}
    for rel in model.by_type("IfcRelAssociatesClassification"):
        ref = rel.RelatingClassification
        src = getattr(ref, "ReferencedSource", None)
        while src is not None and src.is_a("IfcClassificationReference"):
            src = getattr(src, "ReferencedSource", None)
        if (getattr(src, "Name", None) if src is not None else None) != system:
            continue
        code = (getattr(ref, "Identification", None) or "").strip()
        if not code:
            continue
        title = getattr(ref, "Name", None) or ""
        sec = sections.setdefault(code, {"code": code, "title": title, "division": _division(code, system),
                                         "elements": [], "products": set(), "execution": set()})
        for obj in (getattr(rel, "RelatedObjects", None) or []):
            el = obj
            name = getattr(el, "Name", None) or el.is_a()
            sec["elements"].append({"guid": getattr(el, "GlobalId", None), "name": name, "ifc_class": el.is_a()})
            # Part 2 — products: the element's type name + material
            t = ue.get_type(el)
            if t is not None and getattr(t, "Name", None):
                sec["products"].add(str(t.Name))
            for mat in _element_materials(el):
                sec["products"].add(mat)
            # Part 3 — execution: installation instructions attached as documents
            for a in (getattr(el, "HasAssociations", None) or []):
                if a.is_a("IfcRelAssociatesDocument"):
                    doc = a.RelatingDocument
                    dn = getattr(doc, "Name", None) or getattr(doc, "Identification", None)
                    if dn:
                        sec["execution"].add(str(dn))

    # roll sections up into divisions, CSI-ordered
    divs: dict[str, dict[str, Any]] = {}
    for code in sorted(sections):
        s = sections[code]
        dn = s["division"]
        div = divs.setdefault(dn, {"division": dn, "title": _division_title(dn, system), "sections": []})
        div["sections"].append({
            "code": code, "title": s["title"], "element_count": len(s["elements"]),
            "part1_general": f"Summary: work of this Section — {s['title'] or code}. Related requirements, "
                             "references, submittals, and quality assurance per Division 01.",
            "part2_products": sorted(s["products"]) or ["(specify products / materials / manufacturers)"],
            "part3_execution": sorted(s["execution"]) or ["Install in accordance with the manufacturer's "
                                                          "printed instructions and the Contract Documents."],
            "elements": s["elements"][:50],
        })
    divisions = [divs[d] for d in sorted(divs)]
    return {
        "system": system,
        "divisions": divisions,
        "section_count": len(sections),
        "division_count": len(divisions),
        # Names the system actually used. This string said "MasterFormat" unconditionally, so a
        # Uniclass manual described itself as a MasterFormat one — a payload misdescribing its own
        # contents, which is worse than an empty one because nothing looks wrong.
        "note": f"Seeded from the model's {system} classifications + attached documents. A pre-check "
                "starting point — the project manual is authored/edited by the spec writer.",
        #: What else this model carries, so a caller can offer the choice instead of guessing.
        "available_systems": classification_systems(model),
    }


def manual_text(model, project: str = "Project", system: str | None = None) -> str:
    """Render the project manual as a plain-text spec outline (a downloadable starting document)."""
    m = project_manual(model, system)
    system = m["system"]
    lines = [f"PROJECT MANUAL — {project}", "=" * 60,
             f"{m['division_count']} divisions · {m['section_count']} sections "
             f"(seeded from {system} classifications).", ""]
    if not m["divisions"]:
        lines.append(f"No {system}-classified elements found. Classify elements (Track-D) to seed the manual.")
    for div in m["divisions"]:
        lines.append(f"DIVISION {div['division']} — {div['title'].upper()}")
        for s in div["sections"]:
            lines.append(f"  SECTION {s['code']} — {s['title'] or ''}  [{s['element_count']} element(s)]")
            lines.append(f"    PART 1 - GENERAL: {s['part1_general']}")
            lines.append(f"    PART 2 - PRODUCTS: {', '.join(s['part2_products'])}")
            lines.append(f"    PART 3 - EXECUTION: {'; '.join(s['part3_execution'])}")
        lines.append("")
    lines.append(m["note"])
    return "\n".join(lines)
