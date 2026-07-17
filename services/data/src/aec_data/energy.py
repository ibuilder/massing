"""Energy & MEP analysis (open, IFC-native).

A simplified building-envelope energy model (steady-state UA + degree-day method, the
CIBSE/ASHRAE rule-of-thumb) computed from the *actual* IFC geometry — exterior wall, window,
door, roof and ground-floor areas, plus an infiltration term — giving design heating/cooling
loads, annual energy, and EUI. Also a lightweight MEP systems inventory.

This is an engineering estimate (not a full dynamic simulation like EnergyPlus), but it runs
fully offline on the model with no proprietary tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import ifcopenshell
import ifcopenshell.geom as geom
import numpy as np

from .geomconf import geom_workers
from .ifc_loader import open_model

# default constructions (SI, W/m²K) + climate — all overridable
DEFAULTS = {
    "u_wall": 0.30, "u_window": 1.80, "u_door": 2.00, "u_roof": 0.20, "u_floor": 0.25,
    "ach": 0.5,          # air changes / hour (infiltration)
    "delta_t": 25.0,     # design indoor-outdoor temp difference (K)
    "hdd": 2500.0,       # heating degree-days (K·day)
    "cdd": 500.0,        # cooling degree-days (K·day)
    "ceiling_height": 3.0,
}
_AIR = 0.33  # volumetric heat capacity of air, W·h/(m³·K)


@dataclass
class _Areas:
    wall: float = 0.0
    window: float = 0.0
    door: float = 0.0
    roof: float = 0.0
    floor: float = 0.0
    footprint: float = 0.0  # ground-floor footprint (largest horizontal slab)
    counts: dict = field(default_factory=dict)


def _bbox_dims(verts: np.ndarray) -> tuple[float, float, float]:
    mn, mx = verts.min(axis=0), verts.max(axis=0)
    d = mx - mn
    return float(d[0]), float(d[1]), float(d[2])


def envelope_areas(model: ifcopenshell.file) -> _Areas:
    """Sum envelope areas from real geometry. Planar elements use their largest face;
    horizontal elements (roof/slab) use the footprint."""
    a = _Areas()
    counts: dict[str, int] = {}
    settings = geom.settings()
    it = geom.iterator(settings, model, geom_workers())
    if not it.initialize():
        return a
    while True:
        shape = it.get()
        el = model.by_guid(shape.guid)
        cls = el.is_a() if el else shape.type
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        if verts.size:
            dx, dy, dz = _bbox_dims(verts)
            dims = sorted([dx, dy, dz], reverse=True)
            face = dims[0] * dims[1]        # largest face (vertical for walls/windows)
            foot = dx * dy                  # horizontal footprint
            counts[cls] = counts.get(cls, 0) + 1
            if cls in ("IfcWall", "IfcWallStandardCase"):
                a.wall += face
            elif cls == "IfcWindow":
                a.window += face
            elif cls == "IfcDoor":
                a.door += face
            elif cls in ("IfcRoof", "IfcSlab") and dz < min(dx, dy):  # flat-ish → roof/floor
                a.roof += foot  # provisionally roof; ground floor handled below
                a.footprint = max(a.footprint, foot)
        if not it.next():
            break
    a.counts = counts
    # split the largest horizontal area off as ground floor (heat loss to ground)
    if a.footprint:
        a.floor = a.footprint
        a.roof = max(a.roof - a.footprint, a.footprint)  # remaining horizontal ≈ roof
    return a


def analyze(model: ifcopenshell.file, params: dict | None = None) -> dict[str, Any]:
    p = {**DEFAULTS, **(params or {})}
    a = envelope_areas(model)

    storeys = max(len(model.by_type("IfcBuildingStorey")), 1)
    cond_floor_area = a.footprint * storeys if a.footprint else a.floor
    volume = cond_floor_area * p["ceiling_height"]

    net_wall = max(a.wall - a.window - a.door, 0.0)
    ua = {
        "wall": round(net_wall * p["u_wall"], 1),
        "window": round(a.window * p["u_window"], 1),
        "door": round(a.door * p["u_door"], 1),
        "roof": round(a.roof * p["u_roof"], 1),
        "floor": round(a.floor * p["u_floor"], 1),
        "infiltration": round(_AIR * p["ach"] * volume, 1),
    }
    ua_total = round(sum(ua.values()), 1)

    design_heat_w = round(ua_total * p["delta_t"], 0)
    design_cool_w = round(ua_total * (p["delta_t"] * 0.6), 0)  # cooling ΔT smaller
    annual_heat = round(ua_total * p["hdd"] * 24 / 1000, 0)    # kWh
    annual_cool = round(ua_total * p["cdd"] * 24 / 1000, 0)
    total_annual = annual_heat + annual_cool
    eui = round(total_annual / cond_floor_area, 1) if cond_floor_area else 0.0

    return {
        "inputs": p,
        "areas_m2": {"exterior_wall_net": round(net_wall, 1), "window": round(a.window, 1),
                     "door": round(a.door, 1), "roof": round(a.roof, 1),
                     "ground_floor": round(a.floor, 1),
                     "conditioned_floor_area": round(cond_floor_area, 1),
                     "window_wall_ratio": round(a.window / a.wall, 2) if a.wall else 0.0},
        "ua_w_per_k": {**ua, "total": ua_total},
        "loads": {"design_heating_w": design_heat_w, "design_cooling_w": design_cool_w,
                  "design_heating_kw": round(design_heat_w / 1000, 1),
                  "design_cooling_kw": round(design_cool_w / 1000, 1)},
        "annual_kwh": {"heating": annual_heat, "cooling": annual_cool, "total": total_annual},
        "eui_kwh_m2_yr": eui,
        "element_counts": a.counts,
    }


def mep_inventory(model: ifcopenshell.file) -> dict[str, Any]:
    """Lightweight MEP systems inventory: distribution elements/terminals/segments by class
    and by system, plus total run length of any linear segments."""
    # leaf classes for the breakdown; the total is deduplicated by element id since these
    # overlap (e.g. IfcFlowTerminal IS-A IfcDistributionElement)
    classes = ["IfcFlowTerminal", "IfcFlowSegment", "IfcDuctSegment", "IfcPipeSegment",
               "IfcFlowController", "IfcFlowFitting", "IfcEnergyConversionDevice",
               "IfcSpaceHeater", "IfcAirTerminal"]
    by_class = {}
    for cls in classes:
        try:
            n = len(model.by_type(cls))
        except RuntimeError:
            n = 0
        if n:
            by_class[cls] = n
    ids = set()
    for cls in ("IfcDistributionElement",) + tuple(classes):
        try:
            ids.update(e.id() for e in model.by_type(cls))
        except RuntimeError:
            pass
    systems = {}
    for sys_cls in ("IfcDistributionSystem", "IfcSystem"):
        try:
            for s in model.by_type(sys_cls):
                systems[s.Name or s.GlobalId] = getattr(s, "PredefinedType", None)
        except RuntimeError:
            pass
    return {"by_class": by_class, "systems": systems, "total_distribution_elements": len(ids)}


def analyze_file(ifc_path: str, params: dict | None = None) -> dict[str, Any]:
    return analyze(open_model(ifc_path), params)
