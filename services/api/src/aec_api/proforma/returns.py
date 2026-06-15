"""Return metrics — XNPV, XIRR (robust), equity multiple, yield-on-cost, dev spread.

Pure functions over (date, amount) cash flows. XIRR uses Newton-Raphson with a bisection
fallback so it converges on development cash flows (long outflows then a big inflow)."""
from __future__ import annotations

from datetime import date

Cashflow = list[tuple[date, float]]


def xnpv(rate: float, cashflows: Cashflow) -> float:
    if not cashflows:
        return 0.0
    t0 = cashflows[0][0]
    return sum(cf / (1.0 + rate) ** ((d - t0).days / 365.0) for d, cf in cashflows)


def npv(rate: float, amounts: list[float], periods_per_year: int = 12) -> float:
    """NPV of evenly-spaced amounts (amounts[0] at t=0)."""
    return sum(a / (1.0 + rate) ** (i / periods_per_year) for i, a in enumerate(amounts))


def sign_changes(cashflows: Cashflow) -> int:
    vals = [cf for _, cf in cashflows if cf != 0]
    return sum(1 for a, b in zip(vals, vals[1:]) if (a < 0) != (b < 0))


def xirr(cashflows: Cashflow, guess: float = 0.10) -> float | None:
    """Annualized IRR for dated cash flows. Returns None if there's no sign change
    (no IRR) — caller should surface that rather than trust a garbage root."""
    if sign_changes(cashflows) == 0:
        return None
    # Newton-Raphson
    rate = guess
    for _ in range(100):
        f = xnpv(rate, cashflows)
        df = (xnpv(rate + 1e-6, cashflows) - f) / 1e-6
        if abs(df) < 1e-12:
            break
        nxt = rate - f / df
        if not (-0.9999 < nxt < 1e6):
            break
        if abs(nxt - rate) < 1e-7:
            return nxt
        rate = nxt
    # Bisection fallback (guaranteed if a sign change brackets a root)
    lo, hi = -0.9999, 100.0
    flo, fhi = xnpv(lo, cashflows), xnpv(hi, cashflows)
    if (flo < 0) == (fhi < 0):
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        fmid = xnpv(mid, cashflows)
        if abs(fmid) < 1e-7:
            return mid
        if (flo < 0) != (fmid < 0):
            hi = mid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2


def equity_multiple(contributions: float, distributions: float) -> float:
    return distributions / contributions if contributions else 0.0


def yield_on_cost(stabilized_noi: float, total_dev_cost: float) -> float:
    return stabilized_noi / total_dev_cost if total_dev_cost else 0.0


def dev_spread(yoc: float, exit_cap: float) -> float:
    return yoc - exit_cap
