"""CBS-1 (R14) — a **Cost Breakdown Structure** over a construction estimate.

The estimator's layering (distinct from the developer proforma's land/hard/soft in ``dev_budget``):
a base **direct cost** built up through **indirect / general conditions**, **contingency** (known
risks), a **management reserve** (unknown-unknowns, a PMBOK layer held separately from contingency),
**overhead & profit**, then **taxes & fees**, with each layer's amount, rate, and share of the total.

Pure function over a supplied direct cost (the model takeoff estimate feeds it at the route) — every
rate is overridable; conceptual-grade.
"""
from __future__ import annotations

from typing import Any

_DEFAULTS = {
    "indirect_pct": 0.12,             # general conditions / field indirects
    "contingency_pct": 0.05,          # known risks (design/estimate maturity)
    "management_reserve_pct": 0.03,   # unknown-unknowns, held above the line (PMBOK)
    "fee_pct": 0.06,                  # overhead & profit
    "tax_pct": 0.0,                   # sales/use tax on the applicable base (jurisdictional)
}


def build(direct: float, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Layer a direct cost into a full CBS. ``params`` overrides any of the default rates."""
    p = {**_DEFAULTS, **{k: float(v) for k, v in (params or {}).items() if v is not None}}
    direct = round(float(direct or 0.0), 2)
    indirect = round(direct * p["indirect_pct"], 2)
    subtotal = round(direct + indirect, 2)                      # direct + indirect
    contingency = round(subtotal * p["contingency_pct"], 2)
    reserve = round(subtotal * p["management_reserve_pct"], 2)
    base_with_risk = round(subtotal + contingency + reserve, 2)
    fee = round(base_with_risk * p["fee_pct"], 2)
    pre_tax = round(base_with_risk + fee, 2)
    tax = round(pre_tax * p["tax_pct"], 2)
    total = round(pre_tax + tax, 2)

    def _pct(x: float) -> float:
        return round(100.0 * x / total, 2) if total else 0.0

    layers = [
        {"level": "Direct cost", "amount": direct, "rate": None, "pct_of_total": _pct(direct)},
        {"level": "Indirect / general conditions", "amount": indirect,
         "rate": p["indirect_pct"], "pct_of_total": _pct(indirect)},
        {"level": "Contingency (known risks)", "amount": contingency,
         "rate": p["contingency_pct"], "pct_of_total": _pct(contingency)},
        {"level": "Management reserve (unknown risks)", "amount": reserve,
         "rate": p["management_reserve_pct"], "pct_of_total": _pct(reserve)},
        {"level": "Overhead & profit", "amount": fee, "rate": p["fee_pct"], "pct_of_total": _pct(fee)},
        {"level": "Taxes & fees", "amount": tax, "rate": p["tax_pct"], "pct_of_total": _pct(tax)},
    ]
    return {
        "direct": direct, "indirect": indirect, "subtotal": subtotal,
        "contingency": contingency, "management_reserve": reserve,
        "base_with_risk": base_with_risk, "overhead_profit": fee, "taxes": tax, "total": total,
        "rates": p, "layers": layers,
        "note": "Cost breakdown structure over the direct construction cost: indirect (general "
                "conditions) → contingency (known risks) → management reserve (unknown-unknowns, PMBOK, "
                "held separately) → overhead & profit → taxes. Rates overridable; conceptual-grade.",
    }
