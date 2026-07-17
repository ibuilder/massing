"""Phase 1 — lightweight properties index.

Extracts per-element GUID, IFC class, name, storey, and Psets to a queryable JSON so the
API and the viewer's spatial tree never re-parse geometry. Geometry streams as .frag;
data comes from here (CLAUDE.md: keep geometry and metadata separate)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name


@dataclass
class ElementRecord:
    guid: str
    ifc_class: str
    name: str | None
    type_name: str | None
    storey: str | None
    host: str | None = None   # IFC class of the aggregating parent (e.g. an IfcMember's IfcCurtainWall)
    psets: dict[str, dict[str, Any]] = field(default_factory=dict)
    qtos: dict[str, dict[str, Any]] = field(default_factory=dict)


def _element_record(el) -> ElementRecord:
    el_type = ue.get_type(el)
    parent = ue.get_aggregate(el)     # the decomposing parent (IfcRelAggregates), not the spatial container
    return ElementRecord(
        guid=el.GlobalId,
        ifc_class=el.is_a(),
        name=getattr(el, "Name", None),
        type_name=getattr(el_type, "Name", None) if el_type else None,
        storey=storey_name(el),
        host=parent.is_a() if parent is not None else None,
        psets=ue.get_psets(el, psets_only=True),
        qtos=ue.get_psets(el, qtos_only=True),
    )


def build_index(model: ifcopenshell.file) -> dict[str, Any]:
    project = (model.by_type("IfcProject") or [None])[0]
    elements = [asdict(_element_record(el)) for el in physical_elements(model)]
    # collect distinct facets used by layers/classification filters (guide §3/§6)
    classes = sorted({e["ifc_class"] for e in elements})
    storeys = sorted({e["storey"] for e in elements if e["storey"]})
    return {
        "schema": model.schema,
        "project": {
            "guid": project.GlobalId if project else None,
            "name": getattr(project, "Name", None) if project else None,
        },
        "counts": {"elements": len(elements), "classes": len(classes), "storeys": len(storeys)},
        "facets": {"classes": classes, "storeys": storeys},
        "elements": elements,
    }


def _is_json_model(path: str) -> bool:
    """IFC5 / IFCX / ifcJSON are JSON documents (first non-space byte is { or [); STEP starts ISO-10303."""
    try:
        with open(path, "rb") as fh:
            return fh.read(4096).lstrip()[:1] in (b"{", b"[")
    except OSError:
        return False


def index_file(ifc_path: str, out_path: str | None = None) -> dict[str, Any]:
    if _is_json_model(ifc_path):
        # IFC5/IFCX/ifcJSON: geometry can't render yet, but the data layer reads now (real read path).
        from .ifc5_reader import index_json_file
        return index_json_file(ifc_path, out_path)
    model = open_model(ifc_path)
    index = build_index(model)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False)
    return index
