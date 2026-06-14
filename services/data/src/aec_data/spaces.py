"""Phase 5 — Space & functional performance.

Extract IfcSpace data (area, volume, occupancy, department/function) → room/space
schedules; compute net vs gross area and area per occupant (guide §8)."""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, storey_name


def _num(pset_val) -> float | None:
    return float(pset_val) if isinstance(pset_val, (int, float)) else None


def space_schedule(model: ifcopenshell.file) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sp in model.by_type("IfcSpace"):
        psets = ue.get_psets(sp)
        qtos = ue.get_psets(sp, qtos_only=True)
        common = psets.get("Pset_SpaceCommon", {})
        occupancy = psets.get("Pset_SpaceOccupancyRequirements", {})

        area = None
        volume = None
        for q in qtos.values():
            area = area or _num(q.get("NetFloorArea")) or _num(q.get("GrossFloorArea"))
            volume = volume or _num(q.get("NetVolume")) or _num(q.get("GrossVolume"))

        occ = _num(occupancy.get("OccupancyNumber"))
        rows.append({
            "guid": sp.GlobalId,
            "number": getattr(sp, "LongName", None) or getattr(sp, "Name", None),
            "name": getattr(sp, "Name", None),
            "storey": storey_name(sp),
            "function": common.get("Category") or common.get("Reference"),
            "department": common.get("Department"),
            "net_area": area,
            "volume": volume,
            "occupancy": occ,
            "area_per_occupant": round(area / occ, 2) if area and occ else None,
        })
    return rows


def space_schedule_file(ifc_path: str) -> list[dict[str, Any]]:
    return space_schedule(open_model(ifc_path))
