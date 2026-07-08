"""MEP engineering depth (C1): first-pass sizing calculators + an equipment schedule / system rollup.

The calculators are deterministic engineering first-passes — duct + pipe sizing by the velocity method,
block cooling-load → tonnage, and hanger/support spacing per SMACNA (duct) / MSS SP-58 (pipe). They give
a designer a defensible starting size without a full load model; the equipment register (`mep_equipment`)
holds the selected schedule, which this rolls up per system. Extends the D5 parametric MEP generation
(which lays the ducts/pipes/terminals in geometry) with the numbers behind them.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

# Nominal pipe sizes (in) for rounding up a computed diameter.
_NPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]

# Max hanger/support spacing (ft). Duct: SMACNA rectangular ≈ 8–10 ft. Pipe: MSS SP-58, water service.
_HANGER_STEEL = [(1.0, 7), (1.5, 9), (2.0, 10), (3.0, 12), (4.0, 14), (6.0, 17), (8.0, 19), (12.0, 23)]
_HANGER_COPPER = [(1.0, 6), (1.5, 8), (2.0, 8), (2.5, 9), (4.0, 10), (12.0, 12)]


def size_duct(cfm: float, velocity_fpm: float = 1000.0) -> dict[str, Any]:
    """Round-duct sizing by the equal-velocity method: A = Q/V, d = sqrt(4A/pi)."""
    cfm = max(float(cfm), 0.0)
    velocity_fpm = max(float(velocity_fpm), 1.0)
    area_sf = cfm / velocity_fpm
    d_in = math.sqrt(4 * area_sf / math.pi) * 12 if area_sf > 0 else 0.0
    return {"cfm": cfm, "velocity_fpm": velocity_fpm, "area_sf": round(area_sf, 3),
            "diameter_in": round(d_in, 1), "round_diameter_in": int(math.ceil(d_in / 2) * 2),
            "method": "equal-velocity, rounded up to the next 2 in"}


def size_pipe(gpm: float, velocity_fps: float = 6.0) -> dict[str, Any]:
    """Pipe sizing by the velocity method: convert GPM→CFS, A = Q/V, round up to nominal pipe size."""
    gpm = max(float(gpm), 0.0)
    velocity_fps = max(float(velocity_fps), 0.1)
    q_cfs = gpm * 0.002228
    area_sf = q_cfs / velocity_fps
    d_in = math.sqrt(4 * area_sf / math.pi) * 12 if area_sf > 0 else 0.0
    nominal = next((n for n in _NPS if n >= d_in), _NPS[-1])
    return {"gpm": gpm, "velocity_fps": velocity_fps, "diameter_in": round(d_in, 2),
            "nominal_pipe_size_in": nominal, "method": "velocity method, rounded up to nominal pipe size"}


def size_cooling(load_btuh: float) -> dict[str, Any]:
    """Cooling load (BTU/h) → tons (1 ton = 12,000 BTU/h)."""
    load = max(float(load_btuh), 0.0)
    return {"load_btuh": load, "tons": round(load / 12000, 1)}


def block_cooling_load(gfa_sf: float, sf_per_ton: float = 350.0) -> dict[str, Any]:
    """Block cooling-load first pass: gross area ÷ a rule-of-thumb sf/ton (commercial ≈ 300–400)."""
    gfa = max(float(gfa_sf), 0.0)
    sf_per_ton = max(float(sf_per_ton), 1.0)
    tons = gfa / sf_per_ton
    return {"gfa_sf": gfa, "sf_per_ton": sf_per_ton, "tons": round(tons, 1),
            "load_btuh": round(tons * 12000)}


def hanger_spacing(kind: str, size_in: float) -> dict[str, Any]:
    """Max hanger/support spacing (ft) for a duct or pipe of the given size."""
    size_in = max(float(size_in), 0.0)
    if kind == "duct":
        return {"kind": "duct", "size_in": size_in, "max_spacing_ft": 8,
                "reference": "SMACNA rectangular duct (typ. 8–10 ft)"}
    table = _HANGER_COPPER if kind == "pipe_copper" else _HANGER_STEEL
    spacing = next((sp for lim, sp in table if size_in <= lim), table[-1][1])
    return {"kind": kind or "pipe_steel", "size_in": size_in, "max_spacing_ft": spacing,
            "reference": "MSS SP-58, water service"}


def _d(r: dict) -> dict:
    return r.get("data") or r


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# MEP IFC classes → a friendly label (for reading MEP off the model, complementing the register).
_MEP_CLASSES = {
    "IfcDuctSegment": "Duct", "IfcDuctFitting": "Duct fitting", "IfcAirTerminal": "Air terminal",
    "IfcAirTerminalBox": "Air terminal box", "IfcDamper": "Damper", "IfcFan": "Fan",
    "IfcPipeSegment": "Pipe", "IfcPipeFitting": "Pipe fitting", "IfcValve": "Valve",
    "IfcPump": "Pump", "IfcTank": "Tank", "IfcSanitaryTerminal": "Plumbing fixture",
    "IfcSpaceHeater": "Space heater", "IfcBoiler": "Boiler", "IfcChiller": "Chiller",
    "IfcCoolingTower": "Cooling tower", "IfcUnitaryEquipment": "AHU / RTU", "IfcCoil": "Coil",
    "IfcFlowTerminal": "Flow terminal", "IfcCableCarrierSegment": "Cable tray",
    "IfcCableSegment": "Cable", "IfcLightFixture": "Light fixture", "IfcOutlet": "Outlet",
    "IfcElectricAppliance": "Electrical appliance", "IfcElectricDistributionBoard": "Panel / board",
}


def extract_from_model(idx: dict[str, dict] | None) -> dict[str, Any]:
    """Read MEP elements off the loaded model (property index) by IFC class — the model-derived
    counterpart to the register-driven schedule. Complements, doesn't replace, the equipment register."""
    from . import classification
    if not idx:
        return {"model_scored": False, "mep_elements": 0, "by_class": [], "by_discipline": [],
                "note": "No model loaded — MEP extraction needs a published model."}
    by_class: dict[str, int] = {}
    by_disc: dict[str, int] = {}
    for e in idx.values():
        cl = e.get("ifc_class", "")
        if cl in _MEP_CLASSES:
            by_class[cl] = by_class.get(cl, 0) + 1
            disc = classification.discipline_name(classification.discipline_of_ifc_class(cl)) or "Mechanical"
            by_disc[disc] = by_disc.get(disc, 0) + 1
    return {
        "model_scored": True, "mep_elements": sum(by_class.values()),
        "by_class": [{"ifc_class": k, "label": _MEP_CLASSES[k], "count": v}
                     for k, v in sorted(by_class.items(), key=lambda kv: -kv[1])],
        "by_discipline": [{"discipline": k, "count": v} for k, v in sorted(by_disc.items())],
        "note": "MEP elements counted off the model by IFC class (ducts, pipes, terminals, equipment, "
                "electrical). Pair with the equipment register for the engineered schedule.",
    }


def schedule(db: Session, pid: str) -> dict[str, Any]:
    """The equipment schedule from the register + a per-system rollup (count + total capacity by unit)."""
    rows = me.list_records(db, "mep_equipment", pid, limit=100000) if "mep_equipment" in me.TABLES else []
    items = []
    by_system: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = _d(r)
        cap, unit = _num(d.get("capacity")), d.get("capacity_unit") or ""
        item = {"tag": d.get("tag", ""), "type": d.get("equipment_type", ""),
                "system": d.get("system", ""), "capacity": cap, "capacity_unit": unit,
                "flow": _num(d.get("flow")), "size": d.get("size", ""), "state": r.get("workflow_state", "")}
        items.append(item)
        sysrow = by_system.setdefault(item["system"] or "(unassigned)", {"count": 0, "capacity_by_unit": {}})
        sysrow["count"] += 1
        if cap is not None and unit:
            sysrow["capacity_by_unit"][unit] = round(sysrow["capacity_by_unit"].get(unit, 0.0) + cap, 2)
    return {"count": len(items), "items": items,
            "by_system": [{"system": s, **v} for s, v in sorted(by_system.items())],
            "note": "Equipment schedule from the register, rolled up per system. Pair with the sizing "
                    "calculators (duct/pipe/cooling/hanger) for a first-pass design."}
