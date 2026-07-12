"""Orchestrates the development-finance pipeline:
cost schedule → sources&uses (interest reserve) → construction loan → operating proforma →
reversion → project/equity cash flows → returns → waterfall.

The engine is pure: it takes an assumptions dict and returns a result dict (no DB/HTTP),
so it can be tested against reference models and reused by the draws module later."""
from __future__ import annotations

from datetime import date

from . import operations as ops
from . import returns as ret
from .schedule import monthly_uses
from .sources_uses import solve_sources_uses
from .waterfall import run_waterfall


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def solve(a: dict) -> dict:
    timing = a["timing"]
    C = int(timing["construction_months"])
    ops_m = int(timing["hold_years"] * 12)
    leaseup = int(timing.get("leaseup_months", 0))
    start = date.fromisoformat(timing["start_date"]) if timing.get("start_date") else date.today()

    debt, eq = a["debt"], a["equity"]
    o, ex, wf = a["operations"], a["exit"], a["waterfall"]

    # stabilized NOI is needed up front to size debt by value/coverage (LTV / DSCR / debt yield).
    # Capital reserves are deducted "above NOI" (institutional convention) so value/coverage and the
    # exit are underwritten on a reserve-funded NOI (U2).
    reserves_annual = float(o.get("reserves_annual", 0))
    stabilized_noi_annual = (float(o["potential_rent_annual"]) * float(o["stabilized_occ"])
                             * (1 - float(o.get("credit_loss_pct", 0)))
                             + float(o.get("other_income_annual", 0)) * float(o["stabilized_occ"])
                             - float(o["opex_annual"]) - reserves_annual)

    # debt sizing: loan = lesser of LTC and any value/coverage cap supplied (all optional).
    # LTV uses the as-stabilized value (NOI / exit cap); DSCR/debt-yield assume interest-only debt.
    rate = float(debt["rate"])
    stabilized_value = stabilized_noi_annual / float(ex["exit_cap"])
    caps: dict[str, float] = {}
    if debt.get("max_ltv") is not None:
        caps["ltv"] = float(debt["max_ltv"]) * stabilized_value
    if debt.get("min_dscr") is not None and rate > 0:
        caps["dscr"] = stabilized_noi_annual / (float(debt["min_dscr"]) * rate)
    if debt.get("min_debt_yield") is not None:
        caps["debt_yield"] = stabilized_noi_annual / float(debt["min_debt_yield"])
    max_loan = min(caps.values()) if caps else None

    # 1-2-3. cost schedule + sources & uses (resolves interest-reserve circularity)
    uses_ex_int = monthly_uses(a["cost_lines"], C)
    su = solve_sources_uses(uses_ex_int, float(debt["ltc"]), rate,
                            debt.get("funding", "equity_first"), max_loan=max_loan)
    # which constraint actually bound the loan (LTC if no cap undercut it)
    ltc_loan = su["total_uses"] * float(debt["ltc"])
    binding = "ltc"
    if caps and max_loan is not None and max_loan < ltc_loan - 1.0:
        binding = min(caps, key=lambda k: caps[k])
    loan_fees = su["loan_amount"] * float(debt.get("points", 0.0))
    total_dev_cost = su["total_uses"] + loan_fees
    equity_total = su["equity"] + loan_fees  # fees funded by equity for simplicity
    lp_contrib = equity_total * float(eq["lp_pct"])
    gp_contrib = equity_total * float(eq["gp_pct"])

    # 4. operating proforma (monthly NOI over the hold)
    pr_m = float(o["potential_rent_annual"]) / 12.0
    oi_m = float(o.get("other_income_annual", 0)) / 12.0
    opex_m = (float(o["opex_annual"]) + reserves_annual) / 12.0   # reserves above NOI (U2)
    noi_monthly = ops.operating_noi(ops_m, pr_m, oi_m, opex_m, leaseup,
                                    float(o["stabilized_occ"]), float(o.get("credit_loss_pct", 0)))
    # (stabilized_noi_annual computed up front for debt sizing)

    # 5. reversion (sale at exit cap, less selling + loan payoff)
    loan_payoff = su["loan"]["ending_balance"]
    rev = ops.reversion(stabilized_noi_annual, float(ex["exit_cap"]),
                        float(ex["selling_cost_pct"]), loan_payoff)

    # 6. cash flows (monthly). Project = unlevered; equity = levered.
    io_interest_m = loan_payoff * float(debt["rate"]) / 12.0  # IO during ops
    proj_cf: list[tuple[date, float]] = []
    eq_cf: list[tuple[date, float]] = []
    distributable: list[float] = []
    op_dates: list[date] = []
    for t in range(C):
        d = _add_months(start, t)
        proj_cf.append((d, -float(uses_ex_int[t])))
        eq_cf.append((d, -float(su["loan"]["equity_draws"][t])))
    for t in range(ops_m):
        d = _add_months(start, C + t)
        noi = float(noi_monthly[t])
        dist = noi - io_interest_m
        if t == ops_m - 1:                       # exit month
            proj_cf.append((d, noi + rev["gross_sale"] - rev["selling_costs"]))
            dist += rev["net_proceeds"]
        else:
            proj_cf.append((d, noi))
        eq_cf.append((d, dist))
        distributable.append(dist)
        op_dates.append(d)

    # 7. returns
    contributions = sum(-cf for _, cf in eq_cf if cf < 0)
    distributions = sum(cf for _, cf in eq_cf if cf > 0)
    project_irr = ret.xirr(proj_cf)
    equity_irr = ret.xirr(eq_cf)
    yoc = ret.yield_on_cost(stabilized_noi_annual, total_dev_cost)

    # 8. waterfall (LP/GP split of distributable cash; contributions lump at t0)
    wf_dates = [start] + op_dates
    waterfall = run_waterfall(distributable, wf_dates, lp_contrib, gp_contrib,
                              float(wf["pref_rate"]), wf["tiers"],
                              wf.get("style", "american"), bool(wf.get("clawback", False)))

    return {
        "sources_uses": {
            "total_uses": round(total_dev_cost, 2),
            "loan_amount": round(su["loan_amount"], 2),
            "loan_fees": round(loan_fees, 2),
            "interest_reserve": round(su["interest_reserve"], 2),
            "equity": round(equity_total, 2),
            "ltc": su["ltc"],
            "effective_ltc": su["effective_ltc"],
            "lp_contribution": round(lp_contrib, 2),
            "gp_contribution": round(gp_contrib, 2),
        },
        "debt_sizing": {
            # which constraint set the loan, plus the dollar cap each one implies
            "binding_constraint": binding,
            "stabilized_value": round(stabilized_value, 2),
            "actual_dscr": round(stabilized_noi_annual / (su["loan_amount"] * rate), 3) if su["loan_amount"] and rate else None,
            "actual_debt_yield": round(stabilized_noi_annual / su["loan_amount"], 4) if su["loan_amount"] else None,
            "actual_ltv": round(su["loan_amount"] / stabilized_value, 4) if stabilized_value else None,
            "caps": {k: round(v, 2) for k, v in caps.items()},
        },
        "operations": {
            "stabilized_noi_annual": round(stabilized_noi_annual, 2),
            "reversion": {k: round(v, 2) for k, v in rev.items()},
        },
        "returns": {
            "project_irr": project_irr, "equity_irr": equity_irr,
            "equity_multiple": round(ret.equity_multiple(contributions, distributions), 3),
            "npv": round(ret.npv(float(a.get("discount_rate", 0.1)),
                                 [cf for _, cf in eq_cf]), 2),
            "yield_on_cost": round(yoc, 4),
            "exit_cap": round(float(ex["exit_cap"]), 4),
            "dev_spread": round(ret.dev_spread(yoc, float(ex["exit_cap"])), 4),
            "total_contributions": round(contributions, 2),
            "total_distributions": round(distributions, 2),
        },
        "waterfall": waterfall,
        "cash_flow": {
            "dates": [d.isoformat() for d, _ in eq_cf],
            "equity": [round(cf, 2) for _, cf in eq_cf],
            "project": [round(cf, 2) for _, cf in proj_cf],
            "noi_monthly": [round(float(x), 2) for x in noi_monthly],
        },
    }
