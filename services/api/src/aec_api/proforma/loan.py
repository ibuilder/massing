"""Construction loan — interest-only, capitalized (negative amortization). Equity funds
first (or pari-passu / loan-first); interest accrues on the prior month-end balance."""
from __future__ import annotations

import numpy as np


def run_construction_loan(monthly_draws: np.ndarray, equity_available: float,
                          annual_rate: float, funding: str = "equity_first") -> dict:
    """Return ending balance, total accrued (capitalized) interest, and the balance
    schedule. `monthly_draws` is the monthly uses vector (cash needed each month)."""
    mrate = annual_rate / 12.0
    balance = 0.0
    accrued = 0.0
    equity_left = equity_available
    total_draws = float(monthly_draws.sum()) or 1.0
    balances, equity_drawn, loan_drawn = [], [], []
    for draw in monthly_draws:
        if funding == "loan_first":
            from_equity = 0.0
        elif funding == "pari_passu":
            from_equity = min(draw, equity_left, draw * (equity_available / total_draws))
        else:  # equity_first
            from_equity = min(draw, equity_left)
        equity_left -= from_equity
        from_loan = draw - from_equity
        interest = balance * mrate            # on prior balance (begin-of-period)
        accrued += interest
        balance += interest + from_loan        # capitalize interest + add new draw
        balances.append(balance)
        equity_drawn.append(from_equity)
        loan_drawn.append(from_loan)
    return {
        "ending_balance": balance,
        "accrued_interest": accrued,
        "balance_schedule": balances,
        "equity_draws": equity_drawn,
        "loan_draws": loan_drawn,
    }
