"""Embodied-carbon (A1-A3) estimator from material quantities.

Embodied carbon is moving from optional to mandatory on public work and now affects a developer's access
to capital — and we have the material quantities (`production_quantity`, and ultimately the IFC model) to
compute it, which pure PM tools don't. This multiplies quantities by a built-in EPD factor table
(representative ICE/industry A1-A3 averages, kgCO2e per canonical unit) with unit conversion, and rolls
up by material + cost code. Deterministic, offline, and transparent — factors are defaults a deployment
can refine per its own EPDs. Not a certified LCA; a design-stage carbon signal that ties to the model
and to the developer proforma."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import modules as me

# material keyword -> (kgCO2e per canonical unit, canonical unit). A1-A3 "cradle-to-gate" averages.
FACTORS: dict[str, tuple[float, str]] = {
    "concrete": (300.0, "m3"), "rebar": (1.99, "kg"), "reinforc": (1.99, "kg"),
    "structural steel": (1.55, "kg"), "steel": (1.55, "kg"), "metal deck": (2.5, "kg"),
    "timber": (250.0, "m3"), "lumber": (250.0, "m3"), "wood": (250.0, "m3"), "clt": (210.0, "m3"),
    "cmu": (90.0, "m2"), "block": (90.0, "m2"), "masonry": (95.0, "m2"), "brick": (100.0, "m2"),
    "glass": (45.0, "m2"), "glazing": (45.0, "m2"), "curtain wall": (90.0, "m2"),
    "aluminum": (8.24, "kg"), "copper": (3.8, "kg"),
    "gypsum": (3.5, "m2"), "drywall": (3.5, "m2"), "insulation": (5.0, "m2"),
    "asphalt": (0.06, "kg"), "carpet": (5.0, "m2"),   # asphalt: 60 kgCO2e/tonne = 0.06/kg
}

# Every factor is expressed per BASE unit (m3 volume / kg mass / m2 area). This table converts an
# item's unit into that base; canonical factor units above are always one of {m3, kg, m2}.
_UNITS: dict[str, tuple[str, float]] = {
    "m3": ("m3", 1.0), "cy": ("m3", 0.764555), "cf": ("m3", 0.0283168), "l": ("m3", 0.001),
    "kg": ("kg", 1.0), "lb": ("kg", 0.453592), "lbs": ("kg", 0.453592), "ton": ("kg", 907.185),
    "tons": ("kg", 907.185), "tonne": ("kg", 1000.0), "t": ("kg", 1000.0),
    "m2": ("m2", 1.0), "sf": ("m2", 0.092903), "sqft": ("m2", 0.092903), "sy": ("m2", 0.836127),
}


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _match_factor(text: str) -> tuple[str, float, str] | None:
    low = (text or "").lower()
    for kw, (factor, unit) in FACTORS.items():
        if kw in low:
            return kw, factor, unit
    return None


def compute_item(material: str, quantity: float, unit: str) -> dict:
    """kgCO2e for one line, converting the item's unit into the factor's canonical unit family."""
    m = _match_factor(material)
    if not m:
        return {"material": material, "quantity": quantity, "unit": unit,
                "matched": None, "kgco2e": None, "note": "no EPD factor matched"}
    kw, factor, canon = m                                    # canon is a base unit: m3 / kg / m2
    u = (unit or "").lower().strip().rstrip(".")
    conv = _UNITS.get(u)                                      # -> (base_unit, multiply-to-base)
    if not conv or conv[0] != canon:
        # can't safely convert (unit's base family differs from the factor's) — report, don't guess
        return {"material": material, "quantity": quantity, "unit": unit, "matched": kw,
                "kgco2e": None, "note": f"unit '{unit}' not convertible to {canon}"}
    kg = round(quantity * conv[1] * factor, 1)
    return {"material": material, "quantity": quantity, "unit": unit, "matched": kw,
            "factor": factor, "factor_unit": canon, "kgco2e": kg, "note": None}


def compute(items: list[dict]) -> dict:
    """items: [{material|description, quantity, unit, cost_code?}] -> per-line + rollups."""
    lines, by_material, by_code = [], {}, {}
    total = 0.0
    unmatched = 0
    for it in items:
        mat = it.get("material") or it.get("description") or ""
        r = compute_item(mat, _num(it.get("quantity")), it.get("unit") or "")
        r["cost_code"] = it.get("cost_code") or ""
        lines.append(r)
        if r["kgco2e"] is None:
            unmatched += 1
            continue
        total += r["kgco2e"]
        by_material[r["matched"]] = round(by_material.get(r["matched"], 0.0) + r["kgco2e"], 1)
        if r["cost_code"]:
            by_code[r["cost_code"]] = round(by_code.get(r["cost_code"], 0.0) + r["kgco2e"], 1)
    total = round(total, 1)
    return {"lines": lines, "total_kgco2e": total, "total_tco2e": round(total / 1000.0, 2),
            "by_material": dict(sorted(by_material.items(), key=lambda x: -x[1])),
            "by_cost_code": dict(sorted(by_code.items(), key=lambda x: -x[1])),
            "line_count": len(lines), "unmatched": unmatched,
            "message": (None if lines else "No material quantities to assess — add production quantities "
                        "with a material and unit.")}


def project_carbon(db: Session, project_id: str) -> dict:
    """Embodied carbon from the project's production_quantity records."""
    recs = me.list_records(db, "production_quantity", project_id, limit=100_000) if "production_quantity" in me.TABLES else []
    items = [{"description": (r.get("data") or {}).get("description"),
              "quantity": (r.get("data") or {}).get("quantity"),
              "unit": (r.get("data") or {}).get("unit"),
              "cost_code": (r.get("data") or {}).get("cost_code")} for r in recs]
    return compute(items)
