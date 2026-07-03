"""Conceptual / parametric estimating — a $/SF cost off building parameters at the massing stage.

Ediphi's wedge is estimating from geometry before there's a detailed takeoff; it's on-brand for a
product called Massing (we generate the building from a zoning envelope). This turns building type +
GFA + unit count into a conceptual cost with a low/base/high range, escalated for region and year, plus
derived $/SF, $/unit and $/key metrics — the number a developer needs for the proforma before design.
Deterministic; the $/SF table is a sane national-average default a deployment overrides. A directional
signal, not a detailed estimate."""
from __future__ import annotations

from datetime import datetime, timezone

# building type -> base hard cost $/SF (national average, new construction, mid-range).
COST_PER_SF: dict[str, float] = {
    "office": 310.0, "office_highrise": 420.0, "multifamily": 265.0, "multifamily_highrise": 360.0,
    "retail": 220.0, "industrial": 145.0, "warehouse": 120.0, "hotel": 350.0, "hospital": 620.0,
    "school": 340.0, "parking_structure": 95.0, "mixed_use": 300.0, "data_center": 900.0,
    "senior_living": 320.0, "lab": 700.0,
}
# regional cost index (1.0 = US average). Overridable; representative city multipliers.
REGION_INDEX: dict[str, float] = {
    "us_average": 1.0, "new_york": 1.35, "san_francisco": 1.38, "boston": 1.22, "chicago": 1.12,
    "seattle": 1.18, "los_angeles": 1.24, "denver": 1.02, "austin": 0.98, "atlanta": 0.92,
    "dallas": 0.94, "phoenix": 0.95, "miami": 1.03,
}
_BASE_YEAR = 2025
_ESCALATION = 0.045                                      # ~4.5%/yr construction cost escalation


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def estimate(params: dict) -> dict:
    """params: {building_type, gfa_sf, units?, keys?, stories?, region?, year?, soft_cost_pct?}.
    Returns hard/soft/total conceptual cost with a low/base/high range + per-unit metrics."""
    btype = (params.get("building_type") or "office").lower().replace(" ", "_")
    gfa = _num(params.get("gfa_sf"))
    if gfa <= 0:
        return {"error": "gfa_sf required (gross floor area, sf)"}
    base_psf = COST_PER_SF.get(btype)
    matched = btype
    if base_psf is None:
        base_psf, matched = COST_PER_SF["office"], "office (default — unknown type)"

    region = (params.get("region") or "us_average").lower().replace(" ", "_")
    region_idx = REGION_INDEX.get(region, 1.0)
    year = int(params.get("year") or _BASE_YEAR)
    esc = (1 + _ESCALATION) ** (year - _BASE_YEAR)
    stories = int(params.get("stories") or 0)
    # gentle height premium (cranes, structure, MEP risers) above ~12 stories
    height_factor = 1.0 + max(0, stories - 12) * 0.008

    adj_psf = base_psf * region_idx * esc * height_factor
    hard = round(adj_psf * gfa, 0)
    soft_pct = _num(params.get("soft_cost_pct")) or 25.0
    soft = round(hard * soft_pct / 100.0, 0)
    total = hard + soft

    units = int(params.get("units") or 0)
    keys = int(params.get("keys") or units)
    metrics = {"cost_per_sf": round(adj_psf, 2), "hard_per_sf": round(adj_psf, 2),
               "total_per_sf": round(total / gfa, 2) if gfa else 0}
    if units:
        metrics["cost_per_unit"] = round(total / units, 0)
    if keys:
        metrics["cost_per_key"] = round(total / keys, 0)

    return {
        "building_type": matched, "gfa_sf": gfa, "region": region, "region_index": region_idx,
        "year": year, "escalation_factor": round(esc, 3), "height_factor": round(height_factor, 3),
        "hard_cost": hard, "soft_cost": soft, "soft_cost_pct": soft_pct, "total_cost": total,
        "range": {"low": round(total * 0.85, 0), "base": total, "high": round(total * 1.20, 0)},
        "metrics": metrics,
        "note": "Conceptual (Class 5) estimate from parametric $/SF benchmarks — a directional signal "
                "for the proforma, not a detailed takeoff. Refine as the design develops.",
    }


def catalog() -> dict:
    """The building-type + region reference tables (for the UI picker)."""
    return {"building_types": sorted(COST_PER_SF.keys()),
            "regions": sorted(REGION_INDEX.keys()),
            "base_year": _BASE_YEAR, "annual_escalation": _ESCALATION,
            "current_year": datetime.now(timezone.utc).year}
