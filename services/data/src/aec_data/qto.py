"""Phase 5 — Quantity takeoff (QTO) → estimating (5D).

Pull base quantities from IfcElementQuantity/Psets; fall back to geometry-derived
length/area/volume when quantities are missing. Map elements to cost codes (CSI
MasterFormat / UniFormat) via a user-editable table; multiply by unit cost → 5D."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name

try:
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.shape as _shape
    _GEOM_OK = True
except Exception:  # pragma: no cover - geom backend optional
    _GEOM_OK = False

# common base-quantity keys across IFC qto psets
_QTY_KEYS = {
    "length": ("Length", "NetLength", "GrossLength"),
    "area": ("NetArea", "GrossArea", "Area", "NetSideArea", "GrossSideArea"),
    "volume": ("NetVolume", "GrossVolume", "Volume"),
    "weight": ("NetWeight", "GrossWeight", "Weight"),
}


@dataclass
class CostCodeRow:
    """One line of the editable mapping table (CSV-backed in production)."""
    match_class: str            # IFC class, e.g. "IfcBeam"
    cost_code: str              # e.g. "03 30 00"
    description: str
    unit: str                   # the quantity to bill on: length|area|volume|weight|count
    unit_cost: float


def _quantities(el) -> dict[str, float]:
    qtos = ue.get_psets(el, qtos_only=True)
    out: dict[str, float] = {}
    for qset in qtos.values():
        for canonical, keys in _QTY_KEYS.items():
            if canonical in out:
                continue
            for k in keys:
                if k in qset and isinstance(qset[k], (int, float)):
                    out[canonical] = float(qset[k])
                    break
    return out


def _geom_quantities(element, settings) -> dict[str, float]:
    """Geometry-derived fallback when IfcElementQuantity is missing (guide §8)."""
    if not _GEOM_OK:
        return {}
    try:
        shape = _geom.create_shape(settings, element)
        geo = shape.geometry
        return {
            "volume": float(_shape.get_volume(geo)),
            "area": float(_shape.get_area(geo)),
        }
    except Exception:
        return {}


def load_cost_map(path: str | None) -> dict[str, CostCodeRow]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {r["match_class"]: CostCodeRow(**r) for r in data}


def takeoff(
    model: ifcopenshell.file,
    cost_map: dict[str, CostCodeRow] | None = None,
    geometry_fallback: bool = True,
    force_geometry: bool = False,
) -> list[dict[str, Any]]:
    """`force_geometry`: compute area+volume from geometry for EVERY element that lacks them
    (independent of a cost map), so a model-based estimate prices real quantities even without
    Qto psets or a cost-code mapping. Slightly slower; meant for on-demand estimating."""
    cost_map = cost_map or {}
    settings = None
    if (geometry_fallback or force_geometry) and _GEOM_OK:
        settings = _geom.settings()  # meters, triangulated

    rows: list[dict[str, Any]] = []
    for el in physical_elements(model):
        if el.is_a("IfcOpeningElement"):
            continue
        q = _quantities(el)
        el_type = ue.get_type(el)
        cc = cost_map.get(el.is_a())

        if force_geometry and settings is not None and ("area" not in q or "volume" not in q):
            for k, v in _geom_quantities(el, settings).items():
                q.setdefault(k, v)

        amount = None
        if cc and cc.unit == "count":
            amount = cc.unit_cost
        else:
            # only compute geometry for elements we'll actually bill and that lack the quantity
            if cc and settings is not None and cc.unit not in q and cc.unit in ("area", "volume"):
                for k, v in _geom_quantities(el, settings).items():
                    q.setdefault(k, v)
            if cc and cc.unit in q:
                amount = round(q[cc.unit] * cc.unit_cost, 2)
        rows.append({
            "guid": el.GlobalId,
            "ifc_class": el.is_a(),
            "name": getattr(el, "Name", None),
            "type": getattr(el_type, "Name", None) if el_type else None,
            "storey": storey_name(el),
            "length": q.get("length"),
            "area": q.get("area"),
            "volume": q.get("volume"),
            "weight": q.get("weight"),
            "cost_code": cc.cost_code if cc else None,
            "cost_description": cc.description if cc else None,
            "unit": cc.unit if cc else None,
            "amount": amount,
        })
    return rows


def takeoff_file(ifc_path: str, cost_map_path: str | None = None,
                 force_geometry: bool = False) -> list[dict[str, Any]]:
    return takeoff(open_model(ifc_path), load_cost_map(cost_map_path), force_geometry=force_geometry)
