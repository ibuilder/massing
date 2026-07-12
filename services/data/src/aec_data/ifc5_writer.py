"""IFC5 / IFCX / ifcJSON **data** write path — the inverse of ``ifc5_reader.build_index_from_json``.

Geometry authoring for IFC5 lands upstream (web-ifc / Fragments), but the *data* layer is plain JSON, so
we can already **emit** an IFC5 file from our element/property index. This closes the read/write loop:
``properties_index`` (STEP *or* IFC5) → the element index → this writer → a standards-compliant IFC5 JSON
that round-trips back through ``ifc5_reader``.

Two serializations, both recognised by the reader:

* **ifcJSON** (``flavor="ifcjson"``, default) — the buildingSMART ``{"type":"ifcJSON","data":[…]}`` form.
  Full-fidelity: guid / class / name / type / storey / property groups all round-trip exactly.
* **IFCX** (``flavor="ifcx"``) — the OpenUSD-style layer of ``{"name","globalId","attributes","children"}``
  component nodes, class carried on ``attributes["ifc5:class"]``. USD attributes are flat, so property
  *groups* collapse into a single attribute set (values preserved), matching the reader's IFCX handling.
"""
from __future__ import annotations

import json
from typing import Any

SCHEMA = "IFC5"


def _scalars(psets: dict[str, Any]) -> dict[str, Any]:
    """Flatten property groups to a single {prop: value} map (USD attributes are flat)."""
    flat: dict[str, Any] = {}
    for _grp, props in (psets or {}).items():
        if isinstance(props, dict):
            for k, v in props.items():
                if not isinstance(v, (dict, list)):
                    flat[str(k)] = v
    return flat


def to_ifcjson(index: dict[str, Any]) -> dict[str, Any]:
    """Serialize the element index to buildingSMART ifcJSON. Property groups are kept under a
    ``properties`` map so they round-trip through the reader's ``_psets_of``."""
    data: list[dict[str, Any]] = []
    proj = (index.get("project") or {}).get("name")
    if proj:
        data.append({"type": "IfcProject", "name": proj})
    for el in index.get("elements", []):
        obj: dict[str, Any] = {"type": el.get("ifc_class"), "globalId": el.get("guid")}
        if el.get("name") is not None:
            obj["name"] = el["name"]
        if el.get("type_name"):
            obj["objectType"] = el["type_name"]
        if el.get("storey"):
            obj["storey"] = el["storey"]
        psets = el.get("psets") or {}
        if psets:
            obj["properties"] = {grp: dict(props) for grp, props in psets.items()
                                 if isinstance(props, dict)}
        data.append(obj)
    return {"type": "ifcJSON", "schema": SCHEMA, "data": data}


def to_ifcx(index: dict[str, Any]) -> list[dict[str, Any]]:
    """Serialize the element index to the IFCX / USD-layer node list. Class on ``ifc5:class``; scalar
    properties folded into ``attributes`` (USD attributes are flat)."""
    nodes: list[dict[str, Any]] = []
    proj = (index.get("project") or {}).get("name")
    if proj:
        nodes.append({"name": proj, "attributes": {"ifc5:class": "IfcProject", "name": proj},
                      "children": []})
    for el in index.get("elements", []):
        attrs: dict[str, Any] = {"ifc5:class": el.get("ifc_class")}
        if el.get("name") is not None:
            attrs["name"] = el["name"]
        if el.get("type_name"):
            attrs["objectType"] = el["type_name"]
        if el.get("storey"):
            attrs["storey"] = el["storey"]
        attrs.update(_scalars(el.get("psets") or {}))
        nodes.append({"name": el.get("name") or el.get("guid"), "globalId": el.get("guid"),
                      "attributes": attrs, "children": []})
    return nodes


def to_bytes(index: dict[str, Any], flavor: str = "ifcjson", *, indent: int | None = None) -> bytes:
    """Serialize `index` to IFC5 JSON bytes. flavor: 'ifcjson' (default) | 'ifcx'."""
    doc: Any = to_ifcx(index) if flavor == "ifcx" else to_ifcjson(index)
    return json.dumps(doc, ensure_ascii=False, indent=indent).encode("utf-8")


def write_file(index: dict[str, Any], out_path: str, flavor: str = "ifcjson") -> str:
    with open(out_path, "wb") as fh:
        fh.write(to_bytes(index, flavor, indent=2))
    return out_path
