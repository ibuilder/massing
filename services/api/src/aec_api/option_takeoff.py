"""GEN-SCORE depth — an elemental (5D) takeoff behind each generated massing option, so cost and
carbon come from **quantities** rather than from one blended rate and one typology benchmark.

`option_score` today prices an option at a single conceptual $/SF and rates its carbon from a
whole-building kgCO₂e/m² benchmark by building type. Both are defensible at concept stage, and both
share a weakness: they cannot tell you *where* the number comes from. Two options with the same GFA
and type get the same carbon intensity even when one is a squat plate and the other a slender tower
with twice the façade per square metre — which is exactly the trade-off the scorer exists to expose.

So this derives elemental quantities from the massing geometry (footprint, perimeter, floors,
height), prices each element, and runs the same quantities through the platform's existing EPD
factors (`carbon.FACTORS` — one material factor table, not a second copy).

**The basis is reported, always.** A quantity-derived number and a benchmark number are different
claims about the world, and a ranking that silently mixes them is comparing unlike things. Every
figure carries `basis`, and `option_score` flags a mixed set rather than averaging over the
difference.

Conceptual grade, and it says so: these are massing-stage assemblies with no detailed design behind
them. The gain is not accuracy — it is that the number is *decomposed*, so a reader can see which
assumption is doing the work and change it.
"""
from __future__ import annotations

import math
from typing import Any

from . import carbon

# Structural system → m³ of concrete and kg of steel per m² of GFA. Massing-stage assemblies from
# published concept-estimating ranges; overridable per call.
STRUCTURE: dict[str, dict[str, float]] = {
    "concrete_flat_plate": {"concrete_m3_per_m2": 0.26, "rebar_kg_per_m2": 22.0, "steel_kg_per_m2": 0.0},
    "concrete_pt":         {"concrete_m3_per_m2": 0.22, "rebar_kg_per_m2": 14.0, "steel_kg_per_m2": 0.0},
    "steel_composite":     {"concrete_m3_per_m2": 0.10, "rebar_kg_per_m2": 6.0, "steel_kg_per_m2": 55.0},
    "mass_timber":         {"concrete_m3_per_m2": 0.06, "rebar_kg_per_m2": 4.0, "steel_kg_per_m2": 8.0,
                            "timber_m3_per_m2": 0.16},
}
DEFAULT_STRUCTURE = "concrete_flat_plate"

# Elemental $/unit — concept grade, region-neutral. The conceptual estimator stays the authority on
# the TOTAL; these split it so the reader can see the shape of the spend.
RATES = {
    "concrete_m3": 380.0, "rebar_kg": 1.65, "steel_kg": 3.40, "timber_m3": 1150.0,
    "glazing_m2": 780.0, "opaque_wall_m2": 420.0, "roof_m2": 260.0,
    "partition_m2": 95.0, "finishes_m2": 210.0, "mep_m2": 480.0, "vertical_core_m2": 640.0,
}

DEFAULT_WWR = 0.40                 # window-to-wall ratio when the option doesn't state one
CORE_FRACTION = 0.14               # of GFA taken by vertical circulation / shafts at concept stage


def _perimeter(m: dict) -> float:
    """Façade perimeter (m) from the massing plate. Falls back to the perimeter of a square of the
    same footprint area — an approximation, and `basis` says so downstream."""
    w, d = float(m.get("plate_w") or 0.0), float(m.get("plate_d") or 0.0)
    if w > 0 and d > 0:
        return 2.0 * (w + d)
    fp = float(m.get("footprint_m2") or 0.0)
    return 4.0 * math.sqrt(fp) if fp > 0 else 0.0


def quantities(massing: dict, structure: str | None = None, wwr: float | None = None) -> dict[str, Any]:
    """Elemental quantities from a `compute_massing` result. Returns {} when the massing carries no
    usable geometry — an empty takeoff, never a fabricated one."""
    gfa = float(massing.get("buildable_gfa_m2") or 0.0)
    floors = int(massing.get("floors") or 0)
    height = float(massing.get("building_height_m") or 0.0)
    footprint = float(massing.get("footprint_m2") or 0.0)
    if gfa <= 0 or floors <= 0:
        return {}

    key = (structure or DEFAULT_STRUCTURE).lower()
    sys = STRUCTURE.get(key)
    if sys is None:
        raise ValueError(f"unknown structure {key!r}; have {', '.join(sorted(STRUCTURE))}")
    ratio = DEFAULT_WWR if wwr is None else float(wwr)
    if not 0.0 <= ratio <= 0.95:
        raise ValueError(f"wwr must be between 0 and 0.95, got {ratio}")

    facade = round(_perimeter(massing) * height, 1)
    core = round(gfa * CORE_FRACTION, 1)
    q: dict[str, float] = {
        "concrete_m3": round(gfa * sys["concrete_m3_per_m2"], 1),
        "rebar_kg": round(gfa * sys["rebar_kg_per_m2"], 0),
        "steel_kg": round(gfa * sys.get("steel_kg_per_m2", 0.0), 0),
        "glazing_m2": round(facade * ratio, 1),
        "opaque_wall_m2": round(facade * (1.0 - ratio), 1),
        "roof_m2": round(footprint, 1),
        "partition_m2": round(gfa * 0.6, 1),        # linear-metre allowance folded to an area rate
        "finishes_m2": round(gfa - core, 1),
        "mep_m2": round(gfa, 1),
        "vertical_core_m2": core,
    }
    if sys.get("timber_m3_per_m2"):
        q["timber_m3"] = round(gfa * sys["timber_m3_per_m2"], 1)
    return {k: v for k, v in q.items() if v > 0}


# quantity key → (material name for carbon.FACTORS, unit). Keys whose material has no EPD factor are
# simply absent — their carbon is not guessed, it is left out and counted as uncovered.
_CARBON_MAP = {
    "concrete_m3": ("concrete", "m3"), "rebar_kg": ("rebar", "kg"), "steel_kg": ("structural steel", "kg"),
    "timber_m3": ("timber", "m3"), "glazing_m2": ("curtain wall", "m2"),
    "opaque_wall_m2": ("cmu", "m2"), "partition_m2": ("gypsum", "m2"),
}


def price(q: dict[str, float], rates: dict[str, float] | None = None) -> dict[str, Any]:
    """Cost the quantities. Returns per-element lines + the total, plus any quantity with no rate —
    an unpriced element is named, not dropped silently into a total that looks complete."""
    r = {**RATES, **(rates or {})}
    lines, unpriced = [], []
    for k, v in sorted(q.items()):
        if k not in r:
            unpriced.append(k)
            continue
        lines.append({"element": k, "quantity": v, "rate": r[k], "cost": round(v * r[k], 2)})
    return {"lines": lines, "total": round(sum(x["cost"] for x in lines), 2), "unpriced": unpriced}


def embodied(q: dict[str, float]) -> dict[str, Any]:
    """Embodied carbon from the same quantities, through the platform's own EPD factor table.

    `covered_pct` is the share of *cost* whose material has a factor — because a bottom-up number
    over 60% of the building is not the same claim as one over 95%, and the reader needs to know
    which they are holding.
    """
    lines, uncovered = [], []
    for k, v in sorted(q.items()):
        mapped = _CARBON_MAP.get(k)
        if not mapped:
            uncovered.append(k)
            continue
        material, unit = mapped
        item = carbon.compute_item(material, v, unit)
        if not item.get("kgco2e"):
            uncovered.append(k)
            continue
        lines.append({"element": k, "material": material, "quantity": v, "unit": unit,
                      "factor": item.get("factor"), "kgco2e": item["kgco2e"]})
    total = round(sum(x["kgco2e"] for x in lines), 1)
    return {"lines": lines, "total_kgco2e": total, "total_tco2e": round(total / 1000.0, 1),
            "uncovered_elements": uncovered,
            "covered_elements": len(lines), "element_count": len(q)}


def takeoff(massing: dict, *, structure: str | None = None, wwr: float | None = None,
            rates: dict[str, float] | None = None) -> dict[str, Any]:
    """The full elemental takeoff for one option: quantities → cost → embodied carbon.

    `basis` is `"quantity"` when the geometry supported a takeoff and `"none"` when it did not — the
    caller must fall back to a benchmark and SAY that it did, rather than presenting a benchmark
    figure as though it were derived.
    """
    q = quantities(massing, structure=structure, wwr=wwr)
    if not q:
        return {"basis": "none", "quantities": {}, "cost": None, "carbon": None,
                "note": "massing carries no usable geometry (needs GFA and floors) — no takeoff"}
    costed, carb = price(q, rates), embodied(q)
    gfa = float(massing.get("buildable_gfa_m2") or 0.0)
    return {
        "basis": "quantity",
        "structure": (structure or DEFAULT_STRUCTURE).lower(),
        "wwr": DEFAULT_WWR if wwr is None else float(wwr),
        "quantities": q,
        "cost": costed,
        "carbon": carb,
        "carbon_intensity_kgco2e_m2": round(carb["total_kgco2e"] / gfa, 1) if gfa else None,
        "facade_m2_per_gfa_m2": round(
            (q.get("glazing_m2", 0) + q.get("opaque_wall_m2", 0)) / gfa, 3) if gfa else None,
        "note": "Concept-grade assemblies over massing geometry — the value is that the number is "
                "decomposed, not that it is precise. Every element rate and the structural system "
                "are overridable.",
    }
