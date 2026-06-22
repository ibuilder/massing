"""Property & tax assumptions — the acquisition/operating facts a deal underwrites against:
address, parcel, areas, purchase price, and the tax table (school/county/town/fire → total) that
feeds OPEX. Pure summary over a plain dict so it's testable without a DB."""
from __future__ import annotations

from typing import Any

M2_TO_SF = 10.7639


def summarize(prop: dict[str, Any]) -> dict[str, Any]:
    """prop: {address, block_lot, appraisal, purchase_price, land_sf, building_sf, parking_sf,
    taxes:{school,county,town,fire,other}}. Returns totals + per-SF ratios + a proforma delta."""
    taxes = prop.get("taxes") or {}
    total_taxes = round(sum(float(v or 0) for v in taxes.values()), 2)
    bsf = float(prop.get("building_sf", 0) or 0)
    lsf = float(prop.get("land_sf", 0) or 0)
    price = float(prop.get("purchase_price", 0) or 0)
    return {
        "total_taxes": total_taxes,
        "purchase_price": round(price),
        "building_sf": round(bsf), "land_sf": round(lsf),
        "parking_sf": round(float(prop.get("parking_sf", 0) or 0)),
        "price_per_building_sf": round(price / bsf, 2) if bsf else 0.0,
        "price_per_land_sf": round(price / lsf, 2) if lsf else 0.0,
        "tax_per_building_sf": round(total_taxes / bsf, 2) if bsf else 0.0,
        "far_existing": round(bsf / lsf, 2) if lsf else 0.0,
        # how it adjusts a proforma: taxes → opex; price → acquisition cost line
        "deltas": {"opex_annual_add": total_taxes, "acquisition_amount": round(price)},
    }


def starter() -> dict[str, Any]:
    """Thesis-grounded starter (2000 Hempstead Tpke), editable."""
    return {
        "address": "", "block_lot": "", "appraisal": 0, "purchase_price": 0,
        "land_sf": 0, "building_sf": 0, "parking_sf": 0,
        "taxes": {"school": 0, "county": 0, "town": 0, "fire": 0, "other": 0},
    }
