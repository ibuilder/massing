"""SPACE-UTIL (R16 Tier-2) — space **utilization + supply/demand** planning over the model's `IfcSpace`
inventory. Pure arithmetic (no sensors, no ML): each space's net floor area → an occupancy **capacity** at
a given area-per-person standard; rolled up by space type; and a headcount **program** compared against the
modelled inventory → the area **gap** (surplus / deficit) by type. The own-model analog to a sensor-fed
utilization dataset — because we hold the areas in the IFC, we compute them.

The computation is separated from IFC extraction (`utilization` / `demand` take a plain list of spaces) so
it is exhaustively testable without a model; `from_model` pulls the spaces off an opened IFC.
"""
from __future__ import annotations

import math
from typing import Any

_DEFAULT_APP = 10.0            # m² per person — a neutral office default the caller overrides
_MAX_SPACES = 20_000


def _space_type(name: str | None, long_name: str | None, object_type: str | None) -> str:
    """The space's program type — LongName / ObjectType carry it in practice; fall back to the name."""
    for v in (long_name, object_type, name):
        if v and str(v).strip():
            return str(v).strip()
    return "Unclassified"


def utilization(spaces: list[dict], area_per_person: float | None = None) -> dict[str, Any]:
    """Per-space occupancy capacity + by-type rollup. ``spaces`` = ``[{name, guid, type, area}]`` (area m²).
    Capacity = ``floor(area / area_per_person)``; a space with no/zero area contributes 0."""
    app = float(area_per_person or _DEFAULT_APP)
    if app <= 0:
        app = _DEFAULT_APP
    rows: list[dict] = []
    by_type: dict[str, dict] = {}
    for s in spaces[:_MAX_SPACES]:
        area = float(s.get("area") or 0.0)
        cap = int(math.floor(area / app)) if area > 0 else 0
        rows.append({"guid": s.get("guid"), "name": s.get("name") or s.get("type") or "Space",
                     "type": s.get("type") or "Unclassified", "area_m2": round(area, 2), "capacity": cap})
        t = by_type.setdefault(s.get("type") or "Unclassified", {"count": 0, "area": 0.0, "capacity": 0})
        t["count"] += 1
        t["area"] += area
        t["capacity"] += cap
    total_area = sum(r["area_m2"] for r in rows)
    rows.sort(key=lambda r: -r["area_m2"])
    by_type_rows = sorted(({"type": k, "count": v["count"], "area_m2": round(v["area"], 2),
                            "capacity": v["capacity"]} for k, v in by_type.items()),
                          key=lambda r: -r["area_m2"])
    return {"space_count": len(rows), "total_area_m2": round(total_area, 2),
            "area_per_person": app, "capacity_total": sum(r["capacity"] for r in rows),
            "by_type": by_type_rows, "spaces": rows[:_MAX_SPACES],
            "note": "Occupancy capacity per space at the given area-per-person standard, rolled up by type. "
                    "Pure arithmetic over the modelled net floor areas — no sensors."}


def demand(spaces: list[dict], program: dict[str, float], area_per_person: float | None = None) -> dict[str, Any]:
    """Compare a headcount ``program`` (``{space_type: headcount}``) against the modelled inventory →
    required vs. supplied area + the **gap** (supplied − required; negative = deficit) per type + totals."""
    app = float(area_per_person or _DEFAULT_APP)
    if app <= 0:
        app = _DEFAULT_APP
    supplied: dict[str, float] = {}
    for s in spaces[:_MAX_SPACES]:
        supplied[s.get("type") or "Unclassified"] = supplied.get(s.get("type") or "Unclassified", 0.0) + float(s.get("area") or 0.0)
    rows: list[dict] = []
    for ptype, headcount in (program or {}).items():
        req = float(headcount or 0) * app
        sup = supplied.get(ptype, 0.0)
        rows.append({"type": ptype, "headcount": float(headcount or 0), "required_m2": round(req, 2),
                     "supplied_m2": round(sup, 2), "gap_m2": round(sup - req, 2),
                     "status": "deficit" if sup + 0.5 < req else "ok"})
    rows.sort(key=lambda r: r["gap_m2"])            # worst deficit first
    total_req = sum(r["required_m2"] for r in rows)
    total_sup = sum(r["supplied_m2"] for r in rows)
    return {"area_per_person": app, "total_required_m2": round(total_req, 2),
            "total_supplied_m2": round(total_sup, 2), "total_gap_m2": round(total_sup - total_req, 2),
            "deficit_types": sum(1 for r in rows if r["status"] == "deficit"), "by_type": rows,
            "note": "Headcount program vs. modelled space inventory: required = headcount × area-per-person, "
                    "compared to the summed net floor area of that type. Negative gap = deficit to solve."}


def _spaces_from_model(model) -> list[dict]:
    """Extract ``[{guid, name, type, area}]`` from an opened IFC's IfcSpace inventory."""
    try:
        import ifcopenshell.util.element as ue
    except Exception:                                # noqa: BLE001 — no ifcopenshell
        return []
    out: list[dict] = []
    for sp in model.by_type("IfcSpace"):
        area = 0.0
        try:
            q = (ue.get_psets(sp, qtos_only=True) or {}).get("Qto_SpaceBaseQuantities") or {}
            area = float(q.get("NetFloorArea") or q.get("GrossFloorArea") or 0.0)
        except Exception:                            # noqa: BLE001 — opaque quantities: area 0
            area = 0.0
        out.append({"guid": getattr(sp, "GlobalId", None), "name": getattr(sp, "Name", None),
                    "type": _space_type(getattr(sp, "Name", None), getattr(sp, "LongName", None),
                                        getattr(sp, "ObjectType", None)), "area": area})
    return out


def from_model(model, area_per_person: float | None = None) -> dict[str, Any]:
    """Utilization directly from an opened IFC."""
    return utilization(_spaces_from_model(model), area_per_person)
