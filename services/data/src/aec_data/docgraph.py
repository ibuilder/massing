"""W9-4 (harder half) · the document / specification graph — the *cited-source* layer over the model.

`graph.py` links the model to itself (containment, bounds, openings). This adds the other half W9-4 left
open: linking each element to the **documents and specification sections that govern it**, so a question
like "what governs this wall?" or "why is this element the way it is?" answers with real citations —
a MasterFormat spec section, an attached detail/cut-sheet with its sheet number, the level it sits on.

Two node kinds are folded onto the model graph:

  spec_section   an element's classification code (MasterFormat / UniFormat / …) → the governing spec
                 section. Edge  element ──specified_by──▶ section.
  document       an attached `IfcRelAssociatesDocument` (detail drawing, cut sheet, instruction) with its
                 sheet reference. Edge  element ──documented_by──▶ document.

`element_sources(model, guid)` returns the full cited provenance for one element — the substrate the
RFI-0 NL-QA layer answers from. No geometry kernel, no external docs required (the citations come from the
classifications + documents already carried on the IFC).
"""
from __future__ import annotations

from typing import Any

import ifcopenshell

# classification systems in citation priority — a reference keynote points at a spec section
_SPEC_SYSTEMS = ("MasterFormat", "UniFormat", "OmniClass", "Uniclass")


def _codes(el) -> list[dict]:
    """(system, code, title) from an element's IfcRelAssociatesClassification — its spec-section refs."""
    out: list[dict] = []
    for rel in (getattr(el, "HasAssociations", None) or []):
        if not rel.is_a("IfcRelAssociatesClassification"):
            continue
        ref = rel.RelatingClassification
        src = getattr(ref, "ReferencedSource", None)
        while src is not None and src.is_a("IfcClassificationReference"):
            src = getattr(src, "ReferencedSource", None)
        system = getattr(src, "Name", None) if src is not None else None
        code = getattr(ref, "Identification", None)
        if code:
            out.append({"system": system, "code": str(code), "title": getattr(ref, "Name", None) or ""})
    return out


def _sheet_ref(doc) -> str:
    """The NCS sheet reference for a document: its Identification, else the sheet number from the Location
    basename (`details/S-501.pdf` → `S-501`), else ''."""
    ident = getattr(doc, "Identification", None)
    if ident and str(ident).strip():
        return str(ident).strip()
    loc = getattr(doc, "Location", None)
    if loc and str(loc).strip():
        base = str(loc).strip().replace("\\", "/").rsplit("/", 1)[-1]
        return (base.rsplit(".", 1)[0] if "." in base else base)[:16]
    return ""


def _docs(el) -> list[dict]:
    """Attached documents (name + sheet ref) from an element's IfcRelAssociatesDocument."""
    out: list[dict] = []
    for rel in (getattr(el, "HasAssociations", None) or []):
        if not rel.is_a("IfcRelAssociatesDocument"):
            continue
        doc = rel.RelatingDocument
        name = getattr(doc, "Name", None) or getattr(doc, "Identification", None)
        if name:
            out.append({"name": str(name), "sheet": _sheet_ref(doc)})
    return out


def _container(el) -> dict | None:
    """The element's spatial container (level) — a citation for 'where'."""
    import ifcopenshell.util.element as ue

    st = ue.get_container(el) or ue.get_aggregate(el)
    if st is None:
        return None
    return {"guid": getattr(st, "GlobalId", None), "name": getattr(st, "Name", None), "class": st.is_a()}


def build(model: ifcopenshell.file) -> dict[str, Any]:
    """Fold spec-section + document nodes onto the model graph. Returns counts + the distinct nodes:
    {spec_sections:[{code,system,title,elements}], documents:[{name,sheet,elements}], edges, by_rel}."""
    sections: dict[tuple, dict] = {}     # (system, code) -> {..., elements:[guid]}
    documents: dict[tuple, dict] = {}    # (name, sheet) -> {..., elements:[guid]}
    edges = 0

    for el in model.by_type("IfcElement"):
        g = el.GlobalId
        for c in _codes(el):
            key = (c["system"], c["code"])
            sec = sections.setdefault(key, {"system": c["system"], "code": c["code"],
                                            "title": c["title"], "elements": []})
            sec["elements"].append(g)
            edges += 1
        for d in _docs(el):
            key = (d["name"], d["sheet"])
            doc = documents.setdefault(key, {"name": d["name"], "sheet": d["sheet"], "elements": []})
            doc["elements"].append(g)
            edges += 1

    spec_list = sorted(sections.values(), key=lambda s: (s["system"] or "", s["code"]))
    doc_list = sorted(documents.values(), key=lambda d: d["name"])
    return {
        "spec_sections": spec_list,
        "documents": doc_list,
        "counts": {"spec_sections": len(spec_list), "documents": len(doc_list), "edges": edges},
        "by_rel": {"specified_by": sum(len(s["elements"]) for s in spec_list),
                   "documented_by": sum(len(d["elements"]) for d in doc_list)},
    }


def element_sources(model: ifcopenshell.file, guid: str) -> dict[str, Any]:
    """The cited provenance of one element: its spec sections (classification codes), attached documents
    (with sheet refs), and its spatial container — every fact tagged with its source so an NL-QA answer
    can cite it. `found=False` for an unknown GUID."""
    try:
        el = model.by_guid(guid)
    except (RuntimeError, KeyError):
        el = None
    if el is None:
        return {"guid": guid, "found": False, "citations": []}

    specs = _codes(el)
    docs = _docs(el)
    container = _container(el)
    citations: list[dict] = []
    for s in specs:
        citations.append({"kind": "spec", "ref": f"{s['system']} {s['code']}".strip(),
                          "title": s["title"], "source": "classification"})
    for d in docs:
        ref = f"{d['name']}" + (f" ({d['sheet']})" if d["sheet"] else "")
        citations.append({"kind": "document", "ref": ref, "sheet": d["sheet"], "source": "document"})
    if container:
        citations.append({"kind": "location", "ref": container["name"] or container["class"],
                          "source": "spatial-structure"})
    return {
        "guid": guid, "found": True, "name": getattr(el, "Name", None), "class": el.is_a(),
        "spec_sections": specs, "documents": docs, "container": container,
        "citations": citations,
    }
