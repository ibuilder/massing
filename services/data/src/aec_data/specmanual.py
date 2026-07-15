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

# CSI MasterFormat division numbers → titles (the 2-digit prefix of a work-result code).
_DIVISIONS = {
    "00": "Procurement and Contracting Requirements", "01": "General Requirements",
    "02": "Existing Conditions", "03": "Concrete", "04": "Masonry", "05": "Metals",
    "06": "Wood, Plastics, and Composites", "07": "Thermal and Moisture Protection", "08": "Openings",
    "09": "Finishes", "10": "Specialties", "11": "Equipment", "12": "Furnishings",
    "13": "Special Construction", "14": "Conveying Equipment", "21": "Fire Suppression",
    "22": "Plumbing", "23": "Heating, Ventilating, and Air Conditioning (HVAC)",
    "25": "Integrated Automation", "26": "Electrical", "27": "Communications",
    "28": "Electronic Safety and Security", "31": "Earthwork", "32": "Exterior Improvements",
    "33": "Utilities",
}


def _division(code: str) -> str:
    return (code or "").strip()[:2]


def _element_material(el) -> str | None:
    try:
        m = ue.get_material(el)
    except Exception:  # noqa: BLE001
        return None
    if m is None:
        return None
    for attr in ("Name",):                       # IfcMaterial / IfcMaterialLayerSet(Usage) / profile
        n = getattr(m, attr, None)
        if n:
            return str(n)
    for layered in ("ForLayerSet", "MaterialLayers", "Materials"):
        sub = getattr(m, layered, None)
        if sub:
            first = sub[0] if isinstance(sub, (list, tuple)) else sub
            n = getattr(getattr(first, "Material", first), "Name", None)
            if n:
                return str(n)
    return None


def project_manual(model, system: str = "MasterFormat") -> dict[str, Any]:
    """Assemble the 3-part project manual from the model's MasterFormat classifications + attached docs."""
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
        sec = sections.setdefault(code, {"code": code, "title": title, "division": _division(code),
                                         "elements": [], "products": set(), "execution": set()})
        for obj in (getattr(rel, "RelatedObjects", None) or []):
            el = obj
            name = getattr(el, "Name", None) or el.is_a()
            sec["elements"].append({"guid": getattr(el, "GlobalId", None), "name": name, "ifc_class": el.is_a()})
            # Part 2 — products: the element's type name + material
            t = ue.get_type(el)
            if t is not None and getattr(t, "Name", None):
                sec["products"].add(str(t.Name))
            mat = _element_material(el)
            if mat:
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
        div = divs.setdefault(dn, {"division": dn, "title": _DIVISIONS.get(dn, "Unassigned"), "sections": []})
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
        "note": "Seeded from the model's MasterFormat classifications + attached documents. A pre-check "
                "starting point — the project manual is authored/edited by the spec writer.",
    }


def manual_text(model, project: str = "Project", system: str = "MasterFormat") -> str:
    """Render the project manual as a plain-text spec outline (a downloadable starting document)."""
    m = project_manual(model, system)
    lines = [f"PROJECT MANUAL — {project}", "=" * 60,
             f"{m['division_count']} divisions · {m['section_count']} sections "
             f"(seeded from {system} classifications).", ""]
    if not m["divisions"]:
        lines.append("No MasterFormat-classified elements found. Classify elements (Track-D) to seed the manual.")
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
