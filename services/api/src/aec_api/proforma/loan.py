"""Construction loan — interest-only, capitalized (negative amortization). Equity funds
first (or pari-passu / loan-first); interest accrues on the prior month-end balance."""
from __future__ import annotations

import numpy as np


def run_construction_loan(monthly_draws: np.ndarray, equity_available: float,
                          annual_rate: float, funding: str = "equity_first",
                          loan_available: float | None = None) -> dict:
    """Return ending balance, total accrued (capitalized) interest, and the balance
    schedule. `monthly_draws` is the monthly uses vector (cash needed each month).

    `loan_available` is the loan COMMITMENT, and it is what makes `loan_first` mean anything.
    Without it that mode set `from_equity = 0.0` on every draw and never switched — the loan funded
    100% of the project forever, equity was sized but never deployed, and the balance ran past its own
    sizing by exactly the undeployed equity ($26.2M drawn against an $18.3M loan on a $24M job) while
    `effective_ltc` still reported the requested 0.70. Capitalized interest consumes the commitment
    too, so headroom is measured against the balance *after* interest, not before.
    """
    mrate = annual_rate / 12.0
    balance = 0.0
    accrued = 0.0
    equity_left = equity_available
    cap = float("inf") if loan_available is None else float(loan_available)
    total_draws = float(monthly_draws.sum()) or 1.0
    balances, equity_drawn, loan_drawn = [], [], []
    for draw in monthly_draws:
        # Interest is capitalized BEFORE this month's draw is apportioned: it accrues on the prior
        # month-end balance, and it consumes loan headroom just as a draw does. Splitting it out of
        # the old `balance += interest + from_loan` leaves equity_first/pari_passu bit-identical.
        interest = balance * mrate            # on prior balance (begin-of-period)
        accrued += interest
        balance += interest
        if funding == "loan_first":
            from_loan = min(draw, max(0.0, cap - balance))
            from_equity = min(draw - from_loan, equity_left)
            # The loan remains funder of last resort once equity is exhausted, exactly as it is under
            # equity_first — every draw must still be funded, or the schedule would silently describe
            # a project that stopped being built.
            from_loan += draw - from_loan - from_equity
        elif funding == "pari_passu":
            from_equity = min(draw, equity_left, draw * (equity_available / total_draws))
            from_loan = draw - from_equity
        else:  # equity_first
            from_equity = min(draw, equity_left)
            from_loan = draw - from_equity
        equity_left -= from_equity
        balance += from_loan
        balances.append(balance)
        equity_drawn.append(from_equity)
        loan_drawn.append(from_loan)
    return {
        "ending_balance": balance,
        "accrued_interest": accrued,
        "balance_schedule": balances,
        "equity_draws": equity_drawn,
        "loan_draws": loan_drawn,
        "equity_deployed": float(sum(equity_drawn)),
    }
