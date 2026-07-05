"""Disposition / marketing — turn a built (or designed) project into a sellable listing.

Massing owns the BIM model + proforma, so a listing can be **auto-filled from the project** (areas,
NOI, cap rate) instead of typed from scratch — the off-plan advantage. This module also holds the
`RESO_MAP` seam: our listing fields → RESO Data Dictionary names, so a later bridge can push listings
to WPRealWise / an MLS as a serialization, not a rewrite. And it orchestrates the tri-approach
appraisal (`appraisal.py`) from the project's proforma, estimate inputs and recorded comparables.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import appraisal
from .models import Project, Scenario

# our listing field -> RESO Data Dictionary field (the bridge seam to WPRealWise / MLS)
RESO_MAP: dict[str, str] = {
    "status": "StandardStatus",
    "list_price": "ListPrice",
    "asset_type": "PropertyType",
    "address": "UnparsedAddress",
    "city": "City",
    "state": "StateOrProvince",
    "zip_code": "PostalCode",
    "beds": "BedroomsTotal",
    "baths": "BathroomsTotalInteger",
    "sqft": "LivingArea",
    "lot_sqft": "LotSizeSquareFeet",
    "year_built": "YearBuilt",
    "num_units": "NumberOfUnitsTotal",
    "public_description": "PublicRemarks",
    "virtual_tour_url": "VirtualTourURLUnbranded",
}

# StandardStatus mapping for our workflow states (RESO uses a controlled vocabulary)
_RESO_STATUS = {
    "draft": "Incomplete", "coming_soon": "ComingSoon", "active": "Active",
    "under_contract": "ActiveUnderContract", "sold": "Closed", "leased": "Closed",
    "withdrawn": "Withdrawn",
}


def to_reso(record: dict) -> dict[str, Any]:
    """Serialize a listing record (module row) to a flat RESO-shaped dict — the payload a bridge
    would POST to WPRealWise / an MLS. Pure; takes the record's `data` + workflow_state."""
    data = record.get("data") or {}
    out: dict[str, Any] = {}
    for ours, reso in RESO_MAP.items():
        if ours == "status":
            continue
        v = data.get(ours)
        if v not in (None, ""):
            out[reso] = v
    out["StandardStatus"] = _RESO_STATUS.get(record.get("workflow_state", ""), "Active")
    out["Latitude"] = (record.get("anchor") or {}).get("lat")
    out["Longitude"] = (record.get("anchor") or {}).get("lon")
    return {k: v for k, v in out.items() if v not in (None, "")}


def _latest_scenario(db: Session, pid: str) -> Scenario | None:
    return (db.query(Scenario).filter(Scenario.project_id == pid)
            .order_by(Scenario.created_at.desc()).first())


def _solved(db: Session, pid: str) -> tuple[dict | None, dict | None]:
    """(result, assumptions) of the project's latest proforma scenario, solving on demand."""
    s = _latest_scenario(db, pid)
    if not s:
        return None, None
    from .proforma.solve import solve
    result = s.result or (solve(s.assumptions) if s.assumptions else None)
    return result, s.assumptions


def _cost_lines_by_category(assumptions: dict | None) -> dict[str, float]:
    """Sum proforma cost_lines by category (land/hard/soft/contingency/fee)."""
    out: dict[str, float] = {}
    for ln in (assumptions or {}).get("cost_lines", []) or []:
        cat = ln.get("category", "other")
        try:
            out[cat] = out.get(cat, 0.0) + float(ln.get("amount") or 0.0)
        except (TypeError, ValueError):
            pass
    return out


def autofill_listing(db: Session, pid: str) -> dict[str, Any]:
    """Pre-populate listing fields from the project's proforma — the off-plan advantage: the listing
    fills itself from the model + underwriting instead of being typed. Returns a `data` dict the
    listing form can apply; safe (empty-ish) when there's no saved scenario yet."""
    p = db.get(Project, pid)
    result, a = _solved(db, pid)
    data: dict[str, Any] = {}
    if p:
        data["address"] = p.name
        prop = p.dev_property or {}
        for k in ("city", "state", "zip_code", "sqft", "num_units", "year_built"):
            if prop.get(k) not in (None, ""):
                data[k] = prop[k]
    if result and a:
        noi = (result.get("operations") or {}).get("stabilized_noi_annual")
        exit_cap = float((a.get("exit") or {}).get("exit_cap") or 0.0)
        if noi:
            data["noi"] = round(float(noi), 2)
        if exit_cap > 0:
            data["cap_rate"] = round(exit_cap * 100, 2)               # field label is "Cap rate %"
            if noi:
                data["list_price"] = round(float(noi) / exit_cap, 2)  # income-approach value ~ asking
        sqft = data.get("sqft")
        if sqft and data.get("list_price"):
            data["price_psf"] = round(float(data["list_price"]) / float(sqft), 2)
    data["_source"] = "proforma" if result else "project"
    return data


def appraisal_inputs(db: Session, pid: str, overrides: dict | None = None) -> dict[str, Any]:
    """Gather the raw inputs for the three approaches from the project (overridable). Each input
    notes its source so the report is defensible."""
    ov = overrides or {}
    result, a = _solved(db, pid)
    by_cat = _cost_lines_by_category(a)
    rcn = ov.get("replacement_cost_new")
    if rcn is None:
        rcn = sum(v for k, v in by_cat.items() if k != "land")        # hard+soft+contingency+fee
    land = ov.get("land_value")
    if land is None:
        land = by_cat.get("land", 0.0)
    noi = ov.get("stabilized_noi")
    if noi is None and result:
        noi = (result.get("operations") or {}).get("stabilized_noi_annual")
    cap = ov.get("cap_rate")
    if cap is None and a:
        cap = float((a.get("exit") or {}).get("exit_cap") or 0.0)
    elif cap is not None and float(cap) > 1:                           # accept 6 (%) or 0.06
        cap = float(cap) / 100.0
    sqft = ov.get("subject_sqft")
    if sqft is None:
        sqft = ((db.get(Project, pid).dev_property or {}).get("sqft")
                if db.get(Project, pid) else None) or 0.0
    return {
        "replacement_cost_new": float(rcn or 0.0),
        "land_value": float(land or 0.0),
        "depreciation_pct": float(ov.get("depreciation_pct") or 0.0),
        "stabilized_noi": float(noi or 0.0),
        "cap_rate": float(cap or 0.0),
        "subject_sqft": float(sqft or 0.0),
        "subject_units": ov.get("subject_units"),
        "has_proforma": result is not None,
    }


def compute_appraisal(db: Session, pid: str, overrides: dict | None = None) -> dict[str, Any]:
    """Full tri-approach valuation for a project: cost + income + sales-comparison + reconciliation.
    Sales comps come from the project's `comparable` module records."""
    from . import modules as me
    inp = appraisal_inputs(db, pid, overrides)
    comps = [r.get("data") or {} for r in (me.list_records(db, "comparable", pid, limit=1000)
                                           if "comparable" in me.TABLES else [])]
    cost = appraisal.cost_approach(inp["replacement_cost_new"], inp["land_value"], inp["depreciation_pct"])
    income = appraisal.income_approach(inp["stabilized_noi"], inp["cap_rate"])
    sales = appraisal.sales_comparison(inp["subject_sqft"], comps, inp.get("subject_units"))
    weights = (overrides or {}).get("weights")
    rec = appraisal.reconcile({"cost": cost, "income": income, "sales_comparison": sales}, weights)
    return {"inputs": inp, "cost": cost, "income": income, "sales_comparison": sales,
            "reconciliation": rec, "comp_count": len(comps)}
