"""Sources & Uses — solves the construction-loan interest-reserve circularity by iteration.

The interest reserve is a *use* (it's borrowed), but the interest depends on the loan
balance, which depends on draws, which include the reserve. Iterate to a fixed point."""
from __future__ import annotations

import numpy as np

from .loan import run_construction_loan


def solve_sources_uses(uses_ex_interest: np.ndarray, ltc: float, annual_rate: float,
                       funding: str = "equity_first", tol: float = 1.0,
                       max_iter: int = 100, max_loan: float | None = None) -> dict:
    """uses_ex_interest: monthly vector of all uses EXCEPT loan interest.
    `max_loan` is an optional absolute cap (from an LTV / DSCR / debt-yield constraint); the
    loan is sized to the lesser of the LTC amount and the cap, with equity filling the rest.
    Returns loan amount, equity, converged interest reserve, and the loan schedule."""
    interest_reserve = 0.0
    loan = {}
    loan_amount = equity = 0.0
    for _ in range(max_iter):
        total_uses = float(uses_ex_interest.sum()) + interest_reserve
        loan_amount = total_uses * ltc
        if max_loan is not None:
            loan_amount = min(loan_amount, max_loan)
        equity = total_uses - loan_amount
        # Pass the sized loan as the COMMITMENT, so `loan_first` funds from the loan only up to what
        # was actually sized and then turns to equity. The fixed-point iteration re-sizes it each pass,
        # so handing over this pass's figure converges the same way the interest reserve does.
        loan = run_construction_loan(uses_ex_interest, equity, annual_rate, funding,
                                     loan_available=loan_amount)
        new_reserve = loan["accrued_interest"]
        if abs(new_reserve - interest_reserve) < tol:
            interest_reserve = new_reserve
            break
        interest_reserve = new_reserve
    total_uses = float(uses_ex_interest.sum()) + interest_reserve
    return {
        "total_uses": total_uses,
        "uses_ex_interest": float(uses_ex_interest.sum()),
        "interest_reserve": interest_reserve,
        "loan_amount": loan_amount,
        "equity": equity,
        "ltc": ltc,
        "effective_ltc": round(loan_amount / total_uses, 4) if total_uses else 0.0,
        "loan": loan,
    }
