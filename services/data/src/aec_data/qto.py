"""Phase 5 — Quantity takeoff (QTO) → estimating (5D).

Pull base quantities from IfcElementQuantity/Psets; fall back to geometry-derived
length/area/volume when quantities are missing. Map elements to cost codes (CSI
MasterFormat / UniFormat) via a user-editable table; multiply by unit cost → 5D."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name

try:
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.shape as _shape
    import numpy as _np
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


def _bbox_longest(geo) -> float | None:
    """Longest bounding-box dimension of a meshed geometry — a robust length proxy for
    linear elements (a swept solid's run is its dominant extent). Works whether the run is
    the extrusion depth (vertical pipe/cable riser) or lies in the profile plane (a railing
    extruded to its rail height). Returns None if the mesh has no vertices.

    NOTE: `geo.verts` is only valid while the owning shape is alive, so callers must keep the
    shape referenced until this returns (see `_geom_quantities`)."""
    try:
        verts = _np.asarray(geo.verts, dtype=float).reshape(-1, 3)
        if verts.size == 0:
            return None
        extents = verts.max(axis=0) - verts.min(axis=0)
        return float(extents.max())
    except Exception:
        return None


def _geom_quantities(element, settings) -> dict[str, float]:
    """Geometry-derived fallback when IfcElementQuantity is missing (guide §8).

    Also derives a `length` from the meshed solid's longest bounding-box dimension. Linear
    elements (IfcPipeSegment / IfcDuctSegment / IfcCableCarrierSegment / IfcRailing) are modelled
    as swept solids with no Qto length, so without this they price at $0 on a per-length rate."""
    if not _GEOM_OK:
        return {}
    try:
        shape = _geom.create_shape(settings, element)
        geo = shape.geometry  # keep `shape` alive: geo.verts is a view into it
        out = {
            "volume": float(_shape.get_volume(geo)),
            "area": float(_shape.get_area(geo)),
        }
        length = _bbox_longest(geo)
        if length is not None:
            out["length"] = length
        return out
    except Exception:
        return {}


_STEEL_DENSITY = 7850.0   # kg/m3 — rebar weight fallback when NetWeight is absent


def discipline_summary(model: ifcopenshell.file, settings=None) -> dict[str, Any]:
    """Discipline quantity roll-up (Koh rebar viz / WithRebar-style MEP takeoff): reinforcement
    tonnage, MEP linear runs (duct / pipe / cable), and structural element volume — from Qto psets
    with a geometry fallback. Honest: weights fall back to volume × steel density when not modelled."""
    if settings is None and _GEOM_OK:
        settings = _geom.settings()

    def _q(el) -> dict[str, float]:
        q = _quantities(el)
        if ("volume" not in q or "length" not in q) and settings:
            q = {**_geom_quantities(el, settings), **q}   # psets win; geometry fills gaps
        return q

    def _len(el) -> float:
        return _q(el).get("length", 0.0) or 0.0

    def _weight(el) -> float:
        q = _q(el)
        return q["weight"] if q.get("weight") else (q.get("volume", 0.0) or 0.0) * _STEEL_DENSITY

    def _count(*classes) -> int:
        return sum(len(model.by_type(c)) for c in classes)

    rebar_els = [e for c in ("IfcReinforcingBar", "IfcReinforcingMesh", "IfcTendon") for e in model.by_type(c)]
    rebar_kg = sum(_weight(e) for e in rebar_els)
    duct_m = sum(_len(e) for e in model.by_type("IfcDuctSegment"))
    pipe_m = sum(_len(e) for e in model.by_type("IfcPipeSegment"))
    cable_m = sum(_len(e) for c in ("IfcCableSegment", "IfcCableCarrierSegment") for e in model.by_type(c))
    struct_vol = 0.0
    for c in ("IfcBeam", "IfcColumn", "IfcSlab", "IfcWall", "IfcWallStandardCase", "IfcFooting", "IfcPile"):
        for e in model.by_type(c):
            struct_vol += _q(e).get("volume", 0.0) or 0.0
    return {
        "rebar": {"count": len(rebar_els), "weight_kg": round(rebar_kg, 1),
                  "tonnes": round(rebar_kg / 1000.0, 3),
                  "estimated": not any(_quantities(e).get("weight") for e in rebar_els) and bool(rebar_els)},
        "mep": {"duct_m": round(duct_m, 1), "pipe_m": round(pipe_m, 1), "cable_m": round(cable_m, 1),
                "counts": {"duct": _count("IfcDuctSegment"), "pipe": _count("IfcPipeSegment"),
                           "cable": _count("IfcCableSegment", "IfcCableCarrierSegment"),
                           "fittings": _count("IfcDuctFitting", "IfcPipeFitting", "IfcCableCarrierFitting")}},
        "structure": {"element_volume_m3": round(struct_vol, 2)},
    }


_DISC_CACHE: dict[tuple, dict[str, Any]] = {}
_DISC_CACHE_MAX = 24


def discipline_summary_file(ifc_path: str) -> dict[str, Any]:
    # PERF-3: cache the discipline roll-up keyed on (path, mtime) — discipline_summary falls back to
    # per-element create_shape for volume/length, which re-runs on every /quantities/disciplines GET
    key = (ifc_path, _mtime(ifc_path))
    cached = _DISC_CACHE.get(key)
    if cached is not None:
        return cached
    out = discipline_summary(open_model(ifc_path))
    if len(_DISC_CACHE) >= _DISC_CACHE_MAX:
        _DISC_CACHE.pop(next(iter(_DISC_CACHE)))
    _DISC_CACHE[key] = out
    return out


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


# Takeoff is expensive (geometry meshing with force_geometry) and the same published model is hit
# repeatedly (estimate + QTO export + closeout package). Cache by (path, mtime, …) — a new published
# version writes a new file path, and any in-place change bumps mtime, so the cache is content-safe.
_TAKEOFF_CACHE: dict[tuple, list[dict[str, Any]]] = {}
_TAKEOFF_CACHE_MAX = 24


def _mtime(path: str | None) -> float:
    try:
        return os.path.getmtime(path) if path else 0.0
    except OSError:
        return 0.0


def takeoff_file(ifc_path: str, cost_map_path: str | None = None,
                 force_geometry: bool = False) -> list[dict[str, Any]]:
    key = (ifc_path, _mtime(ifc_path), bool(force_geometry), cost_map_path or "", _mtime(cost_map_path))
    cached = _TAKEOFF_CACHE.get(key)
    if cached is not None:
        return cached
    rows = takeoff(open_model(ifc_path), load_cost_map(cost_map_path), force_geometry=force_geometry)
    if len(_TAKEOFF_CACHE) >= _TAKEOFF_CACHE_MAX:
        _TAKEOFF_CACHE.pop(next(iter(_TAKEOFF_CACHE)))   # evict oldest (dict preserves insert order)
    _TAKEOFF_CACHE[key] = rows
    return rows
