"""IFC5 / IFCX / ifcJSON **data** read path.

IFC5 (and its ``.ifcx`` serialization, plus the older ``ifcJSON``) is a JSON-based schema that our
geometry stack (web-ifc / Fragments) cannot yet **render** — that lands upstream. But the *data* is
plain JSON, so the element/property layer is tractable **now**: this reader parses such a file into the
same element-index shape ``properties_index.build_index`` produces from a STEP model, so every data-layer
feature (analytics query, LOD/naming/envelope audits, the model query, CSV/JSON-LD/Parquet export) works
on an IFC5 file even before its geometry can be drawn.

The IFC5 spec is still moving, so the parser is deliberately **tolerant** — it recognises the shapes seen
in the wild and extracts what it can, rather than demanding one exact schema:

* **ifcJSON** — ``{"data": [ {"type": "IfcWall", "globalId": …, "name": …}, … ]}`` (or a bare list of
  such objects). The buildingSMART ifcJSON / ifc2json serialization.
* **IFCX / USD-layer** — a list of ``{"path"/"name": …, "attributes": {…}, "children": […]}`` component
  nodes (the OpenUSD-style composition IFC5 development uses); the IFC class is read from an
  ``ifc*:class`` / ``type`` attribute.

Geometry is intentionally out of scope here (returned counts reflect data elements, not tessellation).
"""
from __future__ import annotations

import json
from typing import Any

# Non-physical / spatial / relationship classes excluded from the element set (mirrors how the STEP
# path yields IfcBuildingElement/IfcElement, not projects, storeys, rels or property objects).
_NON_PHYSICAL_EXACT = {"IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace",
                       "IfcGrid", "IfcAnnotation", "IfcOwnerHistory"}
_NON_PHYSICAL_PREFIX = ("IfcRel", "IfcProperty", "IfcQuantity", "IfcElementQuantity", "IfcOwner",
                        "IfcUnit", "IfcSIUnit", "IfcGeometric", "IfcProfile", "IfcRepresentation",
                        "IfcShape", "IfcStyled", "IfcPresentation", "IfcMaterial", "IfcClassification")


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def _class_of(e: dict) -> str | None:
    cls = _first(e, "type", "Type", "class", "ifc_class", "ifcClass")
    if not cls and isinstance(e.get("attributes"), dict):          # IFCX: class lives in attributes
        a = e["attributes"]
        cls = _first(a, "ifc5:class", "ifc:class", "ifcClass", "class", "type")
    if isinstance(cls, str) and cls.startswith("Ifc"):
        return cls
    return None


def _is_physical(cls: str | None) -> bool:
    return bool(cls and cls not in _NON_PHYSICAL_EXACT
                and not any(cls.startswith(p) for p in _NON_PHYSICAL_PREFIX))


def _guid_of(e: dict, fallback: int) -> str:
    g = _first(e, "globalId", "GlobalId", "guid", "GUID", "id", "path", "name")
    return str(g) if g else f"ifcx-{fallback}"


def _psets_of(e: dict) -> dict[str, dict[str, Any]]:
    """Best-effort property groups: an explicit `psets`/`properties`/`attributes` dict of name->value."""
    for key in ("psets", "properties", "Properties"):
        v = e.get(key)
        if isinstance(v, dict) and v:
            return {k: (val if isinstance(val, dict) else {"value": val}) for k, val in v.items()}
    a = e.get("attributes")
    if isinstance(a, dict):
        flat = {k: v for k, v in a.items() if not isinstance(v, (dict, list))
                and not str(k).endswith("class")}
        if flat:
            return {"Attributes": flat}
    return {}


def _iter_entities(data: Any):
    """Yield entity dicts from any of the recognised container shapes, recursing IFCX `children`."""
    if isinstance(data, dict):
        for key in ("data", "objects", "elements", "entities"):
            if isinstance(data.get(key), list):
                yield from _iter_entities(data[key])
                return
        # a single entity dict
        yield data
        for child in (data.get("children") or []):
            yield from _iter_entities(child)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_entities(item)


def _detect_schema(data: Any) -> str:
    if isinstance(data, dict):
        s = _first(data, "schema", "schema_identifier") or _first(data.get("header", {}) or {}, "schema")
        if s:
            return str(s)
        if data.get("type") == "ifcJSON" or "data" in data:
            return "ifcJSON"
    return "IFC5"


def build_index_from_json(data: Any) -> dict[str, Any]:
    """Parse loaded IFC5/IFCX/ifcJSON `data` into the element-index shape (schema/project/counts/…)."""
    elements: list[dict[str, Any]] = []
    project_name = None
    for i, e in enumerate(_iter_entities(data)):
        if not isinstance(e, dict):
            continue
        cls = _class_of(e)
        if cls == "IfcProject":
            project_name = _first(e, "name", "Name")
        if not _is_physical(cls):
            continue
        elements.append({
            "guid": _guid_of(e, i),
            "ifc_class": cls,
            "name": _first(e, "name", "Name"),
            "type_name": _first(e, "objectType", "ObjectType", "typeName", "type_name"),
            "storey": _first(e, "storey", "Storey", "spatialContainer"),
            "psets": _psets_of(e),
            "qtos": {},
        })
    classes = sorted({el["ifc_class"] for el in elements})
    storeys = sorted({el["storey"] for el in elements if el["storey"]})
    return {
        "schema": _detect_schema(data),
        "project": {"guid": None, "name": project_name},
        "counts": {"elements": len(elements), "classes": len(classes), "storeys": len(storeys)},
        "facets": {"classes": classes, "storeys": storeys},
        "elements": elements,
        "geometry": {"readable": False,
                     "note": "IFC5/IFCX data is parsed; geometry rendering lands when web-ifc / "
                             "Fragments add IFC5 support upstream."},
    }


def index_json_file(path: str, out_path: str | None = None) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    index = build_index_from_json(data)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False)
    return index
