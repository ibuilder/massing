"""W11 · Track D carrier layer — attach code/spec/detail content to elements, IFC-natively.

The join layer between the model and the construction documents. Two carriers (both GUID-stable,
attach to occurrences or types):

  • **Classification** (`IfcRelAssociatesClassification`) — the portable way to carry a **keynote /
    spec-section / element code**: UniFormat (element → keynote/drawing), MasterFormat (work result →
    spec section), OmniClass (product). One element can carry all three; each is the join key that a
    keynote, a schedule row and a spec section share. (Batch wrapper over `set_classification`.)
  • **Document** (`IfcRelAssociatesDocument`) — attach a **detail drawing + installation instruction**
    (an `IfcDocumentInformation` + `IfcDocumentReference`) so an element points at the flashing detail
    and the install sequence that explain it. This is what a rule engine writes when "exterior window →
    IBC §1404.4 flashing detail + ASTM E2112 instruction" fires.

`element_detailing` reads it all back for an inspector. The rule engine (D3) and the drawing/keynote/
spec generators (C/D6) consume exactly these carriers.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api


def classify(model: ifcopenshell.file, guids, system: str, code: str,
             name: str | None = None, edition: str | None = None) -> int:
    """Batch-classify elements with a code in a system (UniFormat / MasterFormat / OmniClass / Uniclass).
    Reuses one `IfcClassification` per system. GUID-stable; a bad GUID never aborts the batch."""
    from .edit import set_classification

    n = 0
    for g in guids or []:
        try:
            set_classification(model, g, system, code, name, edition)
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs
            pass
    return n


def _find_information(model: ifcopenshell.file, identification: str | None, name: str):
    """Reuse an existing IfcDocumentInformation by Identification (preferred) or Name, so re-attaching
    the same detail/instruction doesn't duplicate the record."""
    for info in model.by_type("IfcDocumentInformation"):
        if identification and (info.Identification or "") == identification:
            return info
        if not identification and (info.Name or "") == name:
            return info
    return None


def attach_document(model: ifcopenshell.file, guids, name: str, location: str | None = None,
                    description: str | None = None, identification: str | None = None,
                    purpose: str | None = None) -> int:
    """Associate a document (a detail drawing / installation instruction / cut sheet) with elements via
    `IfcRelAssociatesDocument`. Find-or-creates an `IfcDocumentInformation` (deduped by identification/
    name), adds an `IfcDocumentReference` to it, and assigns the reference to each element. `location`
    is the URI (SVG/PDF), `identification` a stable key (e.g. a detail number `A-541/3`). GUID-stable;
    returns the count attached."""
    name = (name or "Document").strip() or "Document"
    info = _find_information(model, identification, name)
    if info is None:
        info = ifcopenshell.api.run("document.add_information", model)
        attrs: dict = {"Name": name}
        if identification:
            attrs["Identification"] = identification
        if description:
            attrs["Description"] = description
        if location:
            attrs["Location"] = location
        if purpose:
            attrs["Purpose"] = purpose
        ifcopenshell.api.run("document.edit_information", model, information=info, attributes=attrs)

    ref = ifcopenshell.api.run("document.add_reference", model, information=info)
    ref_attrs: dict = {}
    if location:
        ref_attrs["Location"] = location
    if identification:
        ref_attrs["Identification"] = identification
    if name:
        ref_attrs["Name"] = name
    if ref_attrs:
        ifcopenshell.api.run("document.edit_reference", model, reference=ref, attributes=ref_attrs)

    n = 0
    for g in guids or []:
        try:
            el = model.by_guid(g)
            ifcopenshell.api.run("document.assign_document", model, products=[el], document=ref)
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs
            pass
    return n


def _ref_dict(ref) -> dict:
    """Flatten an IfcDocumentReference (+ its parent IfcDocumentInformation) for the inspector."""
    info = getattr(ref, "ReferencedDocument", None)
    return {
        "identification": getattr(ref, "Identification", None) or getattr(info, "Identification", None),
        "name": getattr(ref, "Name", None) or getattr(info, "Name", None),
        "location": getattr(ref, "Location", None) or getattr(info, "Location", None),
        "description": getattr(info, "Description", None),
    }


def element_detailing(model: ifcopenshell.file, guid: str) -> dict:
    """Read one element's carriers — classification codes (keynote/spec/element) and associated
    documents (details/instructions) — for a detailing inspector."""
    el = model.by_guid(guid)
    classifications: list[dict] = []
    documents: list[dict] = []
    for rel in (getattr(el, "HasAssociations", None) or []):
        if rel.is_a("IfcRelAssociatesClassification"):
            ref = rel.RelatingClassification
            src = getattr(ref, "ReferencedSource", None)
            # ReferencedSource may chain up through references to the IfcClassification
            while src is not None and src.is_a("IfcClassificationReference"):
                src = getattr(src, "ReferencedSource", None)
            classifications.append({
                "system": getattr(src, "Name", None) if src is not None else None,
                "code": getattr(ref, "Identification", None),
                "title": getattr(ref, "Name", None)})
        elif rel.is_a("IfcRelAssociatesDocument"):
            doc = rel.RelatingDocument
            if doc is not None and doc.is_a("IfcDocumentReference"):
                documents.append(_ref_dict(doc))
            elif doc is not None:  # a bare IfcDocumentInformation
                documents.append({"identification": getattr(doc, "Identification", None),
                                  "name": getattr(doc, "Name", None),
                                  "location": getattr(doc, "Location", None),
                                  "description": getattr(doc, "Description", None)})
    return {"guid": guid, "name": getattr(el, "Name", None) or el.is_a(), "ifc_class": el.is_a(),
            "classifications": classifications, "documents": documents}
