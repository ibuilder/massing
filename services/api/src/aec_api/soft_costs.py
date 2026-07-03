"""Itemized, phase-aware soft costs.

The proforma/dev-budget seed used to carry a single flat "Soft costs = hard × 25%" line. Real
underwriting itemizes soft costs (a 2024/25 development budget breaks them out by category), and the
A/E **design fee** is drawn down across the design phases (SD → DD → CD → Bid → CA), not paid up front.
This turns the flat % into a transparent line-item schedule that still totals the same default (so it's
backward-compatible), with the architecture/engineering fee allocated by phase per standard AIA splits.

Component fractions are *of hard cost* and sum to 0.25 by default; a caller-supplied `soft_cost_pct`
scales them proportionally so the total stays `hard × soft_cost_pct / 100`. Deployments override the
table. Directional defaults, not a substitute for a real development budget."""
from __future__ import annotations

# Soft-cost components as a fraction of HARD cost. Default sum = 0.25 (matches the prior flat 25%).
# Sources: typical US real-estate development soft-cost breakdowns (A/E fees, permits, legal, financing,
# insurance/bonds, developer fee, FF&E, marketing, soft contingency).
COMPONENTS: dict[str, float] = {
    "architecture_engineering": 0.070,   # A/E design fee — phase-allocated (see AE_PHASE_SPLIT)
    "permits_entitlements": 0.020,
    "legal": 0.010,
    "financing_interest": 0.050,
    "insurance_bonds": 0.015,
    "developer_fee": 0.040,
    "ff_e": 0.020,
    "marketing_leasing": 0.010,
    "soft_contingency": 0.015,
}
_DEFAULT_SUM = sum(COMPONENTS.values())   # 0.25

_LABELS: dict[str, str] = {
    "architecture_engineering": "Architecture & engineering (design fee)",
    "permits_entitlements": "Permits & entitlements",
    "legal": "Legal & closing",
    "financing_interest": "Financing & construction-period interest",
    "insurance_bonds": "Insurance & bonds",
    "developer_fee": "Developer fee",
    "ff_e": "FF&E",
    "marketing_leasing": "Marketing & lease-up",
    "soft_contingency": "Soft-cost contingency",
}

# A/E design fee drawn down across the design phases (AIA-standard split; sums to 1.0).
AE_PHASE_SPLIT: dict[str, float] = {
    "SD": 0.15,   # Schematic Design
    "DD": 0.25,   # Design Development
    "CD": 0.35,   # Construction Documents
    "Bid": 0.05,  # Bidding / Negotiation
    "CA": 0.20,   # Construction Administration
}


def itemize(hard: float, soft_cost_pct: float = 25.0) -> dict:
    """Break a hard cost into itemized soft-cost lines totalling `hard × soft_cost_pct / 100`.

    Returns {total, soft_cost_pct, lines:[{key,label,pct_of_hard,amount}], ae_fee, ae_schedule:[{phase,
    pct,amount}]}. The architecture/engineering line is additionally scheduled by design phase."""
    hard = max(0.0, float(hard or 0))
    scale = (float(soft_cost_pct) / 100.0) / _DEFAULT_SUM if _DEFAULT_SUM else 0.0
    lines = []
    for key, frac in COMPONENTS.items():
        amt = round(hard * frac * scale, 0)
        lines.append({"key": key, "label": _LABELS.get(key, key),
                      "pct_of_hard": round(frac * scale * 100, 2), "amount": amt})
    total = round(sum(x["amount"] for x in lines), 0)
    ae_fee = next((x["amount"] for x in lines if x["key"] == "architecture_engineering"), 0.0)
    ae_schedule = [{"phase": ph, "pct": round(f * 100, 1), "amount": round(ae_fee * f, 0)}
                   for ph, f in AE_PHASE_SPLIT.items()]
    return {"total": total, "soft_cost_pct": float(soft_cost_pct), "lines": lines,
            "ae_fee": ae_fee, "ae_schedule": ae_schedule}


def budget_lines(hard: float, soft_cost_pct: float = 25.0) -> list[dict]:
    """Itemized soft costs as dev-budget lines (category='soft'), for _seed_dev_budget."""
    return [{"category": "soft", "description": x["label"], "unit_cost": x["amount"],
             "quantity": 1, "cost_code": ""} for x in itemize(hard, soft_cost_pct)["lines"]]


def proforma_cost_lines(hard: float, soft_cost_pct: float = 25.0) -> list[dict]:
    """Itemized soft costs as proforma cost_lines (category='soft', linear curve), for _proforma_seed."""
    return [{"category": "soft", "name": x["label"], "amount": x["amount"], "curve": "linear"}
            for x in itemize(hard, soft_cost_pct)["lines"]]
