"""Test fitting (TestFit-style) — fit a unit mix to a floor plate and optimize yield.

`layout()` tiles a unit mix along a double-loaded corridor on a rectangular floor plate (units on
both sides of a central corridor) and returns placed unit rectangles + yield metrics. `parking()`
sizes parking to a stalls/unit ratio. `compare()` evaluates several schemes side-by-side so the
team can find the one that pencils. Pure — no IFC needed (the geometry rects feed massing).

IFC-native is the differentiator: the same placed rectangles become real IfcSpaces in the model."""
from __future__ import annotations

import math
from typing import Any

M2_TO_SF = 10.7639
DEFAULT_MIX = [
    {"name": "Studio", "target_sf": 500, "mix_pct": 0.2},
    {"name": "1BR", "target_sf": 750, "mix_pct": 0.5},
    {"name": "2BR", "target_sf": 1050, "mix_pct": 0.3},
]


def layout(plate_w: float, plate_d: float, floors: int = 1, unit_types: list[dict] | None = None,
           corridor_w: float = 1.8, efficiency_target: float = 0.85) -> dict[str, Any]:
    """Double-loaded corridor fit on a plate_w × plate_d (m) plate. Returns placed units (metres,
    centred at plate origin), corridor, and yield metrics (units, NSF/GSF, efficiency, mix)."""
    types = unit_types or DEFAULT_MIX
    total_pct = sum(t.get("mix_pct", 0) for t in types) or 1.0
    bay_d = max(2.5, (plate_d - corridor_w) / 2)          # unit depth per side (m)
    bay_d_sf = bay_d / 1  # depth in m; unit width derived from target area below
    units: list[dict] = []
    by_type: dict[str, int] = {t["name"]: 0 for t in types}

    # build a repeating sequence of unit *widths* weighted by mix; tile each side along X
    seq: list[tuple[str, float]] = []
    for t in types:
        w_m = max(2.5, (float(t["target_sf"]) / M2_TO_SF) / bay_d)   # width so width×depth = target SF
        n = max(1, round((t.get("mix_pct", 0) / total_pct) * 12))    # weight in a 12-slot cycle
        seq += [(t["name"], w_m)] * n
    if not seq:
        seq = [("Unit", 8.0)]

    for side, y_sign in (("N", 1), ("S", -1)):
        x = -plate_w / 2
        i = 0
        cy = y_sign * (corridor_w / 2 + bay_d / 2)
        while True:
            name, w_m = seq[i % len(seq)]
            if x + w_m > plate_w / 2 + 0.01:
                break
            units.append({"name": name, "cx": round(x + w_m / 2, 2), "cy": round(cy, 2),
                          "w": round(w_m, 2), "d": round(bay_d, 2)})
            by_type[name] = by_type.get(name, 0) + 1
            x += w_m
            i += 1

    units_per_floor = len(units)
    total_units = units_per_floor * max(1, floors)
    nsf_floor = sum(u["w"] * u["d"] for u in units) * M2_TO_SF
    gsf_floor = plate_w * plate_d * M2_TO_SF
    by_type_total = {k: v * max(1, floors) for k, v in by_type.items()}
    return {
        "units": units,                                  # one floor's placed rects (metres)
        "corridor": {"w": corridor_w, "length": round(plate_w, 2)},
        "bay_depth": round(bay_d, 2),
        "metrics": {
            "units_per_floor": units_per_floor,
            "total_units": total_units,
            "nsf_per_floor": round(nsf_floor),
            "gsf_per_floor": round(gsf_floor),
            "total_nsf": round(nsf_floor * max(1, floors)),
            "total_gsf": round(gsf_floor * max(1, floors)),
            "efficiency": round(nsf_floor / gsf_floor, 3) if gsf_floor else 0.0,
            "avg_unit_sf": round(nsf_floor / units_per_floor) if units_per_floor else 0,
            "mix": by_type_total,
        },
    }


def parking(units: int, ratio: float = 1.2, kind: str = "surface") -> dict[str, Any]:
    """Size parking to a stalls/unit ratio. SF/stall by type: surface ~320, structured ~350 (incl.
    drive aisles/ramps). Returns stall count + footprint + a rough cost."""
    stalls = math.ceil(units * ratio)
    sf_per = {"surface": 320, "podium": 360, "structured": 350}.get(kind, 320)
    cost_per = {"surface": 5_000, "podium": 28_000, "structured": 32_000}.get(kind, 5_000)
    return {"stalls": stalls, "ratio": ratio, "kind": kind,
            "area_sf": stalls * sf_per, "cost": stalls * cost_per}


# candidate unit-mix presets the optimizer sweeps
_PRESETS: dict[str, list[dict]] = {
    "Studio-heavy": [{"name": "Studio", "target_sf": 480, "mix_pct": 0.6}, {"name": "1BR", "target_sf": 720, "mix_pct": 0.4}],
    "1BR-heavy": [{"name": "Studio", "target_sf": 480, "mix_pct": 0.2}, {"name": "1BR", "target_sf": 720, "mix_pct": 0.6}, {"name": "2BR", "target_sf": 1000, "mix_pct": 0.2}],
    "Balanced": DEFAULT_MIX,
    "2BR-heavy": [{"name": "1BR", "target_sf": 750, "mix_pct": 0.3}, {"name": "2BR", "target_sf": 1050, "mix_pct": 0.5}, {"name": "3BR", "target_sf": 1350, "mix_pct": 0.2}],
    "Family": [{"name": "2BR", "target_sf": 1100, "mix_pct": 0.6}, {"name": "3BR", "target_sf": 1400, "mix_pct": 0.4}],
}


def optimize(plate_w: float, plate_d: float, floors: int, targets: dict | None = None,
             econ: dict | None = None) -> dict[str, Any]:
    """Generative design — sweep unit-mix presets × parking ratios, score each on a yield-on-cost
    proxy, filter by `targets` (min_units, min_efficiency, max_parking_ratio, min_yoc), and rank.
    `econ`: rent_psf_yr, hard_psf, stall_cost, opex_ratio, land. "Find the deal that pencils.\""""
    t = targets or {}
    e = {"rent_psf_yr": 34.0, "hard_psf": 220.0, "stall_cost": 12_000.0, "opex_ratio": 0.35, "land": 0.0,
         **(econ or {})}
    candidates = []
    for mix_name, mix in _PRESETS.items():
        for pr in (0.5, 1.0, 1.5):
            lay = layout(plate_w, plate_d, floors, mix)
            m = lay["metrics"]
            pk = parking(m["total_units"], pr)
            nsf, gsf = m["total_nsf"], m["total_gsf"]
            revenue = nsf * e["rent_psf_yr"]
            noi = revenue * (1 - e["opex_ratio"])
            cost = gsf * e["hard_psf"] + pk["cost"] + e["land"]
            yoc = round(noi / cost, 4) if cost else 0.0
            candidates.append({
                "name": f"{mix_name} · {pr:g}/unit pkg", "mix_preset": mix_name, "parking_ratio": pr,
                "total_units": m["total_units"], "efficiency": m["efficiency"],
                "total_nsf": nsf, "parking_stalls": pk["stalls"], "yield_on_cost": yoc,
            })
    # filter by targets
    def passes(c: dict) -> bool:
        return (c["total_units"] >= t.get("min_units", 0)
                and c["efficiency"] >= t.get("min_efficiency", 0)
                and c["parking_ratio"] <= t.get("max_parking_ratio", 99)
                and c["yield_on_cost"] >= t.get("min_yoc", 0))
    feasible = [c for c in candidates if passes(c)]
    objective = t.get("objective", "yield_on_cost")
    feasible.sort(key=lambda c: c.get(objective, 0), reverse=True)
    return {"considered": len(candidates), "feasible": len(feasible),
            "ranked": feasible[:8], "best": feasible[0] if feasible else None,
            "objective": objective}


def compare(plate_w: float, plate_d: float, floors: int, schemes: list[dict]) -> dict[str, Any]:
    """Evaluate several schemes side-by-side. Each scheme: {name, unit_types?, parking_ratio?,
    parking_kind?}. Returns per-scheme yield metrics + parking, ranked by total units."""
    out = []
    for sc in schemes:
        lay = layout(plate_w, plate_d, floors, sc.get("unit_types"),
                     corridor_w=float(sc.get("corridor_w", 1.8)))
        m = lay["metrics"]
        pk = parking(m["total_units"], float(sc.get("parking_ratio", 1.2)), sc.get("parking_kind", "surface"))
        out.append({
            "name": sc.get("name", "Scheme"),
            "total_units": m["total_units"], "efficiency": m["efficiency"],
            "total_nsf": m["total_nsf"], "total_gsf": m["total_gsf"],
            "avg_unit_sf": m["avg_unit_sf"], "mix": m["mix"],
            "parking_stalls": pk["stalls"], "parking_area_sf": pk["area_sf"],
        })
    out.sort(key=lambda s: s["total_units"], reverse=True)
    return {"schemes": out, "best": out[0]["name"] if out else None,
            "plate": {"w": plate_w, "d": plate_d, "floors": floors}}
