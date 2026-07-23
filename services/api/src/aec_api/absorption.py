"""ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX (R17 Sprint E) — the **revenue-side** underwriting levers.

Our escalation/market work is cost-side; the biggest missing lever is *how fast the product sells*.

- **sell-out schedule** — an absorption rate (sales / month) deterministically phases revenue over time and
  sets the **sell-out duration**, which drives the carry the pro-forma must underwrite. Given units, an
  absorption rate, and an average price, this returns the monthly revenue curve, the months-to-sell-out, and
  the carry cost over that window.
- **Lot Supply Index** — the public months-of-supply signal: ``months_of_supply = VDL / monthly_absorption``,
  expressed as an index vs a balanced-market target (100 = equilibrium; > 125 oversupplied, < 75
  undersupplied) so land screening carries a defensible supply/demand read.

Deterministic arithmetic; the *comparable* absorption rate is an INTEGRATE market feed — here the caller
supplies it (default to a user assumption offline).
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def sellout(units: float, absorption_per_month: float, avg_price: float,
            monthly_carry: float = 0.0, start_month: int = 1, max_months: int = 1200) -> dict[str, Any]:
    """Phase revenue by absorption → the monthly sell-out curve + duration + carry over the window."""
    units, absorption, price = _num(units), _num(absorption_per_month), _num(avg_price)
    if units <= 0 or absorption <= 0:
        return {"units": units, "absorption_per_month": absorption, "months_to_sellout": None,
                "total_revenue": round(units * price, 2), "schedule": [],
                "note": "Need positive units and a positive absorption rate to phase a sell-out."}
    remaining = units
    month = int(start_month)
    schedule = []
    cum_units = cum_rev = 0.0
    while remaining > 1e-9 and len(schedule) < max_months:
        sold = min(absorption, remaining)
        rev = sold * price
        remaining -= sold
        cum_units += sold
        cum_rev += rev
        schedule.append({"month": month, "units_sold": round(sold, 2), "revenue": round(rev, 2),
                         "cumulative_units": round(cum_units, 2), "cumulative_revenue": round(cum_rev, 2),
                         "remaining_units": round(max(0.0, remaining), 2)})
        month += 1
    months = len(schedule)
    return {
        "units": round(units, 2), "absorption_per_month": absorption, "avg_price": round(price, 2),
        "months_to_sellout": months, "years_to_sellout": round(months / 12.0, 2),
        "total_revenue": round(units * price, 2),
        "avg_monthly_revenue": round(units * price / months, 2) if months else 0.0,
        "total_carry": round(monthly_carry * months, 2) if monthly_carry else 0.0,
        "monthly_carry": round(_num(monthly_carry), 2) or None,
        "schedule": schedule,
        "note": "Absorption-phased sell-out: revenue recognized as units sell at the absorption rate; "
                "months_to_sellout drives the carry the pro-forma underwrites. Absorption rate is an input "
                "(comparable rate = an optional market feed).",
    }


def lot_supply_index(vdl: float, monthly_absorption: float, equilibrium_months: float = 6.0) -> dict[str, Any]:
    """Months of supply = VDL / monthly absorption, as an index vs a balanced-market target (100 =
    equilibrium; > 125 oversupplied, < 75 undersupplied)."""
    vdl, absorption, eq = _num(vdl), _num(monthly_absorption), _num(equilibrium_months) or 6.0
    if absorption <= 0:
        return {"vdl": vdl, "monthly_absorption": absorption, "months_of_supply": None, "lsi": None,
                "band": "unknown", "note": "Need a positive absorption rate to compute months of supply."}
    mos = vdl / absorption
    lsi = round(mos / eq * 100.0)
    band = "oversupplied" if lsi > 125 else "undersupplied" if lsi < 75 else "balanced"
    return {
        "vdl": round(vdl, 1), "monthly_absorption": absorption, "equilibrium_months": eq,
        "months_of_supply": round(mos, 1), "lsi": lsi, "band": band,
        "note": "Lot Supply Index: months_of_supply = VDL ÷ monthly absorption, indexed to a balanced-market "
                f"target of {eq:g} months (100 = equilibrium · > 125 oversupplied · < 75 undersupplied). "
                "VDL = vacant developed lots; absorption = sales/community/month.",
    }
