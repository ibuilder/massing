"""Tri-approach valuation — the three classic appraisal approaches, fused from data Massing
already owns:

- **Cost approach** — replacement cost new (hard + soft from the proforma / model estimate) less
  depreciation, plus land. The defensible "what would it cost to rebuild" number.
- **Income approach** — direct capitalization: stabilized NOI / cap rate (from the proforma solve).
  Primary method for stabilized income property.
- **Sales-comparison approach** — adjusted $/SF (or $/unit) from recorded `comparable` sales.

Each function is pure (numbers in, numbers out) so it's testable without a DB/IFC; the router wires
in the project's proforma, estimate and comparables. `reconcile()` produces a single opinion of value
from weighted approaches. No external services; conceptual-grade (not a USPAP-certified appraisal).
"""
from __future__ import annotations

from statistics import median
from typing import Any


def _r(v: float | None) -> float:
    return round(float(v or 0.0), 2)


def cost_approach(replacement_cost_new: float, land_value: float = 0.0,
                  depreciation_pct: float = 0.0) -> dict[str, Any]:
    """Value = replacement cost new × (1 − depreciation) + land. For new construction depreciation
    is ~0; for older assets pass an accrued-depreciation fraction (physical + functional + external)."""
    dep = max(0.0, min(1.0, float(depreciation_pct or 0.0)))
    depreciated = float(replacement_cost_new or 0.0) * (1.0 - dep)
    value = depreciated + float(land_value or 0.0)
    return {
        "approach": "cost",
        "replacement_cost_new": _r(replacement_cost_new),
        "depreciation_pct": round(dep, 4),
        "depreciation_amount": _r(float(replacement_cost_new or 0.0) * dep),
        "depreciated_improvements": _r(depreciated),
        "land_value": _r(land_value),
        "value": _r(value),
    }


def income_approach(stabilized_noi: float, cap_rate: float) -> dict[str, Any]:
    """Direct capitalization: value = NOI / cap rate. `cap_rate` is a fraction (0.06 = 6%)."""
    cap = float(cap_rate or 0.0)
    value = (float(stabilized_noi or 0.0) / cap) if cap > 0 else 0.0
    return {
        "approach": "income",
        "stabilized_noi": _r(stabilized_noi),
        "cap_rate": round(cap, 4),
        "value": _r(value),
        "method": "direct_capitalization",
    }


def sales_comparison(subject_sqft: float, comps: list[dict],
                     subject_units: float | None = None) -> dict[str, Any]:
    """Value the subject from recorded comparable sales. Prefers $/SF × subject SF (median across
    comps with a usable $/SF); falls back to $/unit × units, then to the median raw sale price.
    `comps`: the `comparable` module records' `data` dicts (price, price_psf, cap_rate, rent_psf...)."""
    psfs, ppus, prices, caps = [], [], [], []
    for c in comps or []:
        price = _num(c.get("price"))
        psf = _num(c.get("price_psf"))
        if psf is None and price and subject_sqft:        # derive $/SF from price if not given
            psf = price / subject_sqft if subject_sqft else None
        if psf:
            psfs.append(psf)
        if price:
            prices.append(price)
            if subject_units and c.get("num_units"):
                u = _num(c.get("num_units"))
                if u:
                    ppus.append(price / u)
        cap = _num(c.get("cap_rate"))
        if cap:
            caps.append(cap / 100.0 if cap > 1 else cap)   # accept 6 or 0.06

    basis, value, unit_psf, unit_ppu = "none", 0.0, None, None
    if psfs and subject_sqft:
        unit_psf = median(psfs)
        value = unit_psf * float(subject_sqft)
        basis = "$/SF"
    elif ppus and subject_units:
        unit_ppu = median(ppus)
        value = unit_ppu * float(subject_units)
        basis = "$/unit"
    elif prices:
        value = median(prices)
        basis = "median price"
    return {
        "approach": "sales_comparison",
        "comp_count": len([c for c in (comps or []) if _num(c.get("price")) or _num(c.get("price_psf"))]),
        "basis": basis,
        "median_price_psf": _r(unit_psf) if unit_psf is not None else None,
        "median_price_per_unit": _r(unit_ppu) if unit_ppu is not None else None,
        "implied_cap_rate": round(median(caps), 4) if caps else None,
        "value": _r(value),
    }


def reconcile(approaches: dict[str, dict], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Weighted reconciliation into a single opinion of value. `approaches` maps name → result dict
    (each with a `value`). Default weighting favors the income approach for stabilized property; any
    approach with a zero/absent value is dropped and the remaining weights are renormalized."""
    default_w = {"income": 0.5, "sales_comparison": 0.3, "cost": 0.2}
    w = {**default_w, **(weights or {})}
    usable = {k: a for k, a in approaches.items() if a and (a.get("value") or 0) > 0}
    wsum = sum(w.get(k, 0.0) for k in usable) or 0.0
    if wsum <= 0:                                          # no weights → equal-weight the usable ones
        wsum = float(len(usable)) or 1.0
        w = {k: 1.0 for k in usable}
    value = sum((usable[k]["value"]) * (w.get(k, 0.0)) for k in usable) / wsum if usable else 0.0
    contributions = [
        {"approach": k, "value": _r(usable[k]["value"]),
         "weight": round(w.get(k, 0.0) / wsum, 4)}
        for k in usable
    ]
    vals = [a["value"] for a in usable.values()]
    spread = (max(vals) - min(vals)) if len(vals) > 1 else 0.0
    return {
        "value": _r(value),
        "contributions": contributions,
        "approaches_used": list(usable.keys()),
        "range": {"low": _r(min(vals)) if vals else 0.0, "high": _r(max(vals)) if vals else 0.0,
                  "spread_pct": round(spread / value, 4) if value else 0.0},
    }


def _num(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f else None
    except (TypeError, ValueError):
        return None
