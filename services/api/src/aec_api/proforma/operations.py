"""Operating proforma (lease-up → stabilized NOI) and reversion (sale at exit cap)."""
from __future__ import annotations

import numpy as np


def leaseup_occupancy(months: int, leaseup_months: int, stabilized_occ: float) -> np.ndarray:
    """Linear lease-up from 0 to stabilized over leaseup_months, then flat."""
    occ = np.full(months, stabilized_occ)
    n = min(leaseup_months, months)
    if n > 0:
        occ[:n] = np.linspace(stabilized_occ / n, stabilized_occ, n)
    return occ


def operating_noi(months: int, potential_rent_monthly: float, other_income_monthly: float,
                  opex_monthly: float, leaseup_months: int, stabilized_occ: float,
                  credit_loss_pct: float = 0.0) -> np.ndarray:
    """Monthly NOI vector over the operating period."""
    occ = leaseup_occupancy(months, leaseup_months, stabilized_occ)
    egi = potential_rent_monthly * occ * (1 - credit_loss_pct) + other_income_monthly * occ
    return egi - opex_monthly


def reversion(stabilized_noi_annual: float, exit_cap: float, selling_cost_pct: float,
              loan_payoff: float) -> dict:
    gross = stabilized_noi_annual / exit_cap if exit_cap else 0.0
    selling = gross * selling_cost_pct
    net = gross - selling - loan_payoff
    return {"gross_sale": gross, "selling_costs": selling, "loan_payoff": loan_payoff,
            "net_proceeds": net}
