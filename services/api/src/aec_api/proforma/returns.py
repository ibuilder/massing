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


#: Range the discount factor `(1 + rate) ** years` must stay inside. Both ends sit comfortably within
#: float64's normal range (~2.2e-308 … 1.8e308), so `xnpv` neither divides by an underflowed zero nor
#: overflows the exponentiation itself.
_MIN_FACTOR = 1e-290
_MAX_FACTOR = 1e290


def _bracket(cashflows: Cashflow) -> tuple[float, float]:
    """Rate bounds it is SAFE to evaluate `xnpv` at for these flows.

    The fixed bounds this used to carry — (-0.9999, 100.0) for bisection and 1e6 for Newton — both
    break on long-dated flows, in opposite directions. `(1e-4) ** 82` is exactly 0.0 in float64, after
    which `xnpv` divides by zero; `101 ** 155` overflows the power outright. Neither is hypothetical:
    a 99-year ground lease is a two-point cash flow spanning a century, and nothing in the platform
    caps a horizon. So the bracket is derived from the span.

    Narrowing the bracket cannot hide a real IRR — the rates excluded are beyond ±2,700% on a
    two-century flow — and a bracket that no longer straddles a root already returns None rather than
    guessing. Refusing to evaluate outside float64's range is the only correct option available.
    """
    if not cashflows:
        return -0.9999, 100.0
    t0 = cashflows[0][0]
    span = max(abs((d - t0).days) for d, _ in cashflows) / 365.0
    if span < 1.0:
        return -0.9999, 100.0
    return (max(-0.9999, _MIN_FACTOR ** (1.0 / span) - 1.0),
            min(100.0, _MAX_FACTOR ** (1.0 / span) - 1.0))


def xirr(cashflows: Cashflow, guess: float = 0.10) -> float | None:
    """Annualized IRR for dated cash flows. Returns None if there's no sign change
    (no IRR) — caller should surface that rather than trust a garbage root."""
    if sign_changes(cashflows) == 0:
        return None
    lo, hi = _bracket(cashflows)
    # Newton-Raphson
    rate = guess
    for _ in range(100):
        f = xnpv(rate, cashflows)
        df = (xnpv(rate + 1e-6, cashflows) - f) / 1e-6
        if abs(df) < 1e-12:
            break
        nxt = rate - f / df
        # The span-derived bracket, not (-0.9999, 1e6): accepting a rate outside it would blow up the
        # discount factor on the NEXT iteration's xnpv call, which is where it actually raised.
        if not (lo < nxt < hi):
            break
        if abs(nxt - rate) < 1e-7:
            return nxt
        rate = nxt
    # Bisection fallback (guaranteed if a sign change brackets a root)
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
