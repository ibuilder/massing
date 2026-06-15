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
                  style: str = "american", clawback: bool = False) -> dict:
    """distributable: cash available each operating period; dates[0] = contribution date,
    dates[1:] aligns with distributable. tiers: ordered, each
    {"hurdle": 0.08|None, "lp": 0.8, "gp": 0.2} (hurdle None = residual)."""
    lp_cf = [-lp_contrib]
    gp_cf = [-gp_contrib]
    lp_dates = [dates[0]]
    lp_unreturned = lp_contrib
    accrued_pref = 0.0
    periods = []
    prev = dates[0]

    for d, cash in zip(dates[1:], distributable):
        remaining = max(cash, 0.0)
        lp_take = gp_take = 0.0
        accrued_pref += lp_unreturned * pref_rate * _period_fraction(prev, d)

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
                        "lp": round(lp_take, 2), "gp": round(gp_take, 2)})
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
            lp_cf = [-lp_contrib] + [p["lp"] for p in periods]
            gp_cf = [-gp_contrib] + [p["gp"] for p in periods]

    lp_dist = sum(p["lp"] for p in periods)
    gp_dist = sum(p["gp"] for p in periods)
    return {
        "periods": periods, "style": style,
        "lp_distributions": round(lp_dist, 2), "gp_distributions": round(gp_dist, 2),
        "lp_irr": xirr(list(zip(lp_dates, lp_cf))),
        "gp_irr": xirr(list(zip(lp_dates, gp_cf))),
        "lp_equity_multiple": round(lp_dist / lp_contrib, 3) if lp_contrib else 0,
        "gp_equity_multiple": round(gp_dist / gp_contrib, 3) if gp_contrib else 0,
        "lp_unreturned": round(lp_unreturned, 2),
    }
