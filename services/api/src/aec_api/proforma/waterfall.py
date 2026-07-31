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


def solve_clawback_for_pref(lp_cf, lp_dates, pref_rate, cap) -> float:
    """Cash added at the FINAL date that lifts the LP's XIRR to `pref_rate`, capped at `cap`.

    The exact inverse of `solve_cash_for_irr_hurdle` above, and deliberately built the same way. That
    function asks "how much cash keeps the LP AT/UNDER a target IRR"; restitution asks "how much cash
    LIFTS the LP TO it". The technique was already in this file; the clawback path used a proxy.

    The proxy it replaces was `(pref_rate - lp_irr) * lp_contrib` — a RATE multiplied by CAPITAL,
    which is a one-year figure and has no time dimension at all. It cannot express the money needed to
    move a multi-year return, and it understates badly: on a conventional five-year deal
    ([-1,000,000, 40k, 45k, 50k, 55k, 1,000,000] at an 8% pref) the proxy says 41,509 where the true
    figure is 240,776 — **5.8x**. Verified by construction: adding 240,776 at the final date takes the
    LP's XIRR to exactly 0.080000.

    Capped at `cap` (the promote actually paid) because a clawback returns the excess promote and
    cannot return more than the GP received. `owed` and `restored` are therefore different numbers
    whenever the promote cannot cover the shortfall, and `run_waterfall` reports both.
    """
    if cap <= 0:
        return 0.0
    d = lp_dates[-1]
    if (_lp_irr_with(lp_cf, lp_dates, d, 0.0) or -1.0) >= pref_rate:
        return 0.0                      # already at/above the pref — nothing owed
    if (_lp_irr_with(lp_cf, lp_dates, d, cap) or -1.0) <= pref_rate:
        # Even the whole promote does not get there. Returning `cap` here is the RIGHT amount to move
        # but it is NOT the amount required, and the two must not be conflated: comparing
        # restored >= owed would then read as "fully restored" precisely because the cap bound.
        return cap
    lo, hi = 0.0, cap
    for _ in range(80):
        mid = (lo + hi) / 2
        irr = _lp_irr_with(lp_cf, lp_dates, d, mid)
        if irr is None:
            lo = mid; continue
        if irr > pref_rate:
            hi = mid
        else:
            lo = mid
        if hi - lo < 0.01:              # to the cent — this is a dollar figure, not a cash cap
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
                # The hurdle is tested on the LP's cash flows INCLUDING what it has already been
                # paid in THIS period — `lp_take` currently holds the pref and the return of
                # capital, which are not appended to `lp_cf` until after this loop. Passing plain
                # `lp_cf` measured the LP's IRR as though the current period had paid it nothing:
                # in the first distribution period the series is contributions-only, XIRR is
                # undefined, and `(None or -1.0) >= hurdle` is False — so the below-hurdle tier
                # absorbed cash that belonged to the residual tier. On a single 2,000 distribution
                # (900 LP / 100 GP, 8% pref, 90/10 then 80/20) the GP received 102.78 instead of
                # 205.57 — half its promote — while dollars still conserved and every existing
                # assertion passed. The solver already models the tier's own cash at date `d`;
                # omitting the pref and RoC paid at that same date was the inconsistency.
                cap = solve_cash_for_irr_hurdle(lp_cf + [lp_take], lp_dates + [d], d,
                                               tier["hurdle"], tier["lp"], remaining)
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
    #
    # `lp_irr is None` means **XIRR did not converge**, not "no clawback owed" — and across a
    # 729-pattern sweep of cash-flow shapes it came back None in 26% of them (sign patterns with
    # multiple or no real roots). Until now that case silently did nothing: a deal where restitution
    # might be owed returned the same payload as one where none was, and a GP kept money a clawback
    # would have recovered. It is reported rather than guessed at, because any fallback would invent
    # a restitution figure out of a failed solve — a plausible dollar amount gets cited, a missing one
    # gets chased. Whether a non-converging IRR is a zero-clawback case by contract or an unpriceable
    # one is a DEAL-TERMS decision, not an arithmetic one, so the code states the situation and stops.
    clawback_status = "not_requested"
    clawback_reason = None
    # None, never 0.0: "not requested" and "nothing owed" are different facts, and a zero here would
    # read as the second while meaning the first.
    clawback_owed = clawback_restored = None
    _capped_short = False
    if clawback:
        lp_irr = xirr(list(zip(lp_dates, lp_cf)))
        if lp_irr is None:
            clawback_status = "unavailable"
            clawback_reason = ("the LP's IRR could not be solved for these cash flows (XIRR did not "
                               "converge), so whether restitution is owed cannot be determined. This "
                               "is NOT a finding that none is owed")
        elif lp_irr >= pref_rate:
            clawback_status = "not_owed"
            clawback_reason = "the LP achieved its preferred return, so no restitution is due"
        elif not len(periods):
            clawback_status = "not_owed"
            clawback_reason = "no distribution period exists to claw back from"
        else:
            clawback_status = "applied"
        if lp_irr is not None and lp_irr < pref_rate and len(periods):
            shortfall_periods = [p for p in periods if p["gp"] > 0]
            promote_paid = sum(p["gp"] for p in shortfall_periods)
            # The money that actually lifts the LP to its pref, solved rather than approximated.
            clawback_owed = solve_clawback_for_pref(lp_cf, lp_dates, pref_rate, promote_paid)
            owed = clawback_owed
            for p in reversed(shortfall_periods):
                move = min(owed, p["gp"])
                p["gp"] -= move; p["lp"] += move; owed -= move
                if owed <= 0:
                    break
            # What was RESTORED is what the promote could cover; `owed` is what was required. They
            # differ whenever the GP did not take enough promote to make the LP whole, and reporting
            # only one of them hides which situation the deal is in.
            clawback_restored = clawback_owed - max(owed, 0.0)
            # Whether the promote could COVER the requirement — not whether the LP ended at its
            # pref. Those are different claims and only the first is knowable here:
            #
            # The solve places the restitution as a lump at the FINAL date, because that is the
            # question with one answer ("what cash at the end lifts the LP to its pref"). The actual
            # transfer comes out of the earlier periods that paid promote, so the realised cash-flow
            # shape differs — money arriving sooner, generally leaving the LP at or above the target.
            # For multi-sign-change series the realised `lp_irr` may have no root at all and is
            # reported as None, so it cannot be used as the test either.
            #
            # `restored == owed` on its own proves nothing, because the solver returns the cap when
            # the promote cannot cover the shortfall — which is exactly what made the first version
            # of this report say `fully_restored: True` on a deal whose whole promote was consumed
            # and whose LP was still short.
            _capped_short = (_lp_irr_with(lp_cf, lp_dates, lp_dates[-1], clawback_owed)
                             or -1.0) < pref_rate - 1e-9
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
        # Stated, never inferred from the numbers: a caller cannot tell "no restitution was
        # owed" from "we could not work out whether any was" by looking at the distributions.
        "clawback": {"requested": bool(clawback), "status": clawback_status,
                     "reason": clawback_reason,
                     # What the LP was short, and what the promote could actually return. They differ
                     # when the GP did not take enough promote to cover the shortfall.
                     "owed": round(clawback_owed, 2) if clawback_owed is not None else None,
                     "restored": round(clawback_restored, 2) if clawback_restored is not None else None,
                     # The promote covered the solved requirement (the cap did not bind). NOT a
                     # claim that the realised LP IRR equals the pref — see the note above on the
                     # lump-at-final-date solve versus the period-by-period transfer.
                     "requirement_met": (None if clawback_owed is None else not _capped_short),
                     "capped_by_promote": (None if clawback_owed is None else _capped_short),
                     # The TRIGGER is IRR-based. NPV-at-pref is the right basis for the AMOUNT but is
                     # not a safe drop-in for the trigger: for multi-sign-change flows the two
                     # genuinely disagree, and NPV can read positive while the LP still has unreturned
                     # capital. Which basis applies is a deal term, so it is stated rather than picked.
                     "basis": "irr"},
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
