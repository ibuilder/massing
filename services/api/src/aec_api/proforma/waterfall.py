"""JV equity waterfall — distributes each period's cash through ordered tiers:
Return of Capital → compounding Preferred Return → IRR-hurdle promote splits.

Pref accrues/compounds on UNRETURNED capital. Promote-tier breakpoints are measured on the
LP's own cash flows (XIRR). European style withholds promote until the LP has its full
capital + pref back; American can pay promote as hurdles are met. Optional end-of-hold
clawback restores the LP's pref if the GP was over-promoted."""
from __future__ import annotations

from datetime import date

from .returns import xirr

TOL = 1e-6


def _period_fraction(d0: date, d1: date) -> float:
    return (d1 - d0).days / 365.0


def _lp_irr_with(lp_cf: list[float], lp_dates: list[date], d: date, extra: float) -> float | None:
    cf = list(zip(lp_dates + [d], lp_cf + [extra]))
    return xirr(cf)


def solve_cash_for_irr_hurdle(lp_cf, lp_dates, d, target_irr, lp_share, cap) -> float:
    """Max total distribution at date d (of which lp_share goes to LP) that keeps LP XIRR
    at/under target_irr. Bisection on the distribution amount (LP IRR rises with cash)."""
    if cap <= 0:
        return 0.0
    if (_lp_irr_with(lp_cf, lp_dates, d, 0.0) or -1.0) >= target_irr:
        return 0.0  # already at/above the hurdle — this tier gets nothing
    lo, hi = 0.0, cap
    if (_lp_irr_with(lp_cf, lp_dates, d, hi * lp_share) or -1.0) <= target_irr:
        return cap  # even the full cap doesn't reach the hurdle
    for _ in range(80):
        mid = (lo + hi) / 2
        irr = _lp_irr_with(lp_cf, lp_dates, d, mid * lp_share)
        if irr is None:
            lo = mid; continue
        if irr > target_irr:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1.0:
            break
    return (lo + hi) / 2


def run_waterfall(distributable: list[float], dates: list[date], lp_contrib: float,
                  gp_contrib: float, pref_rate: float, tiers: list[dict],
                  style: str = "american", clawback: bool = False,
                  pref_accrual: str = "compounding") -> dict:
    """distributable: cash available each operating period; dates[0] = contribution date,
    dates[1:] aligns with distributable. tiers: ordered, each
    {"hurdle": 0.08|None, "lp": 0.8, "gp": 0.2} (hurdle None = residual).

    `pref_accrual` — `"compounding"` (unpaid pref itself earns pref) or `"simple"` (pref accrues on
    unreturned capital only). Both are real deal terms and the difference is money: over three unpaid
    periods on $1,000 at 10% it is $331 against $300, ~10% more owed to the LP. This used to be
    unstated and unselectable — the module documented "compounding" twice and implemented simple — so
    it is now an explicit input, defaulted to the documented behaviour and echoed in the result.

    A period with NEGATIVE distributable is an operating shortfall, and it is treated as a **capital
    call** split in the partners' contribution ratio: it increases LP unreturned capital (so pref
    accrues on it) and lands in the partner cash flows. Previously `max(cash, 0.0)` discarded it, so
    the waterfall's LP IRR rested on a smaller capital base than the deal-level equity IRR computed
    from the same deal — two headline returns that could not be reconciled.
    """
    if pref_accrual not in ("compounding", "simple"):
        raise ValueError("pref_accrual must be 'compounding' or 'simple'")
    lp_cf = [-lp_contrib]
    gp_cf = [-gp_contrib]
    lp_dates = [dates[0]]
    lp_unreturned = lp_contrib
    accrued_pref = 0.0
    periods = []
    prev = dates[0]
    total_equity = lp_contrib + gp_contrib
    lp_share = (lp_contrib / total_equity) if total_equity else 1.0
    lp_calls = gp_calls = 0.0

    for d, cash in zip(dates[1:], distributable):
        # Unpaid pref compounds when the terms say so: the balance it accrues on is unreturned
        # capital PLUS pref already earned and not yet paid.
        base = lp_unreturned + (accrued_pref if pref_accrual == "compounding" else 0.0)
        accrued_pref += base * pref_rate * _period_fraction(prev, d)

        if cash < 0:
            # An operating shortfall is funded by the partners, not absorbed by nobody. LP capital
            # called this way is unreturned capital like any other, so it earns pref from here on.
            call = -float(cash)
            lp_call = call * lp_share
            gp_call = call - lp_call
            lp_unreturned += lp_call
            lp_calls += lp_call
            gp_calls += gp_call
            lp_cf.append(-lp_call); gp_cf.append(-gp_call); lp_dates.append(d)
            periods.append({"date": d.isoformat(), "distributable": round(cash, 2),
                            "lp": 0.0, "gp": 0.0,
                            "lp_call": round(lp_call, 2), "gp_call": round(gp_call, 2)})
            prev = d
            continue

        remaining = cash
        lp_take = gp_take = 0.0

        # Tier 1: preferred return, then return of capital (LP)
        pay = min(remaining, accrued_pref)
        lp_take += pay; remaining -= pay; accrued_pref -= pay
        roc = min(remaining, lp_unreturned)
        lp_take += roc; remaining -= roc; lp_unreturned -= roc

        # Promote tiers — European withholds until LP fully returned + pref paid
        gate = not (style == "european" and (lp_unreturned > TOL or accrued_pref > TOL))
        if gate:
            for tier in tiers:
                if remaining <= TOL:
                    break
                if tier.get("hurdle") is None:           # residual
                    lp_take += remaining * tier["lp"]
                    gp_take += remaining * tier["gp"]
                    remaining = 0.0
                    break
                cap = solve_cash_for_irr_hurdle(lp_cf, lp_dates, d, tier["hurdle"], tier["lp"], remaining)
                split = min(remaining, cap)
                lp_take += split * tier["lp"]
                gp_take += split * tier["gp"]
                remaining -= split

        lp_cf.append(lp_take); gp_cf.append(gp_take); lp_dates.append(d)
        periods.append({"date": d.isoformat(), "distributable": round(cash, 2),
                        "lp": round(lp_take, 2), "gp": round(gp_take, 2),
                        "lp_call": 0.0, "gp_call": 0.0})
        prev = d

    # clawback: if LP didn't reach its pref over the hold, claw GP promote back to LP
    if clawback:
        lp_irr = xirr(list(zip(lp_dates, lp_cf)))
        if lp_irr is not None and lp_irr < pref_rate and len(periods):
            shortfall_periods = [p for p in periods if p["gp"] > 0]
            owed = (pref_rate - lp_irr) * lp_contrib  # rough restitution proxy
            for p in reversed(shortfall_periods):
                move = min(owed, p["gp"])
                p["gp"] -= move; p["lp"] += move; owed -= move
                if owed <= 0:
                    break
            # Rebuild NET of capital calls — a period can carry a call instead of a distribution, and
            # dropping it here would quietly restore the old too-small capital base.
            lp_cf = [-lp_contrib] + [p["lp"] - p["lp_call"] for p in periods]
            gp_cf = [-gp_contrib] + [p["gp"] - p["gp_call"] for p in periods]

    lp_dist = sum(p["lp"] for p in periods)
    gp_dist = sum(p["gp"] for p in periods)
    # Multiples are measured against ALL capital the partner put in, initial plus called. Dividing by
    # the initial contribution alone reports a multiple on money that was not the whole investment.
    lp_invested = lp_contrib + lp_calls
    gp_invested = gp_contrib + gp_calls
    return {
        "periods": periods, "style": style, "pref_accrual": pref_accrual,
        "lp_distributions": round(lp_dist, 2), "gp_distributions": round(gp_dist, 2),
        # Additional capital the partners had to fund for operating shortfalls. Reported separately
        # from `*_distributions` so the existing "distributions reconcile to positive distributable"
        # invariant still holds and the calls are not netted away into invisibility.
        "lp_capital_calls": round(lp_calls, 2), "gp_capital_calls": round(gp_calls, 2),
        "lp_invested": round(lp_invested, 2), "gp_invested": round(gp_invested, 2),
        "lp_irr": xirr(list(zip(lp_dates, lp_cf))),
        "gp_irr": xirr(list(zip(lp_dates, gp_cf))),
        "lp_equity_multiple": round(lp_dist / lp_invested, 3) if lp_invested else 0,
        "gp_equity_multiple": round(gp_dist / gp_invested, 3) if gp_invested else 0,
        "lp_unreturned": round(lp_unreturned, 2),
    }
