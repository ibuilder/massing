"""Financial statements for a real-estate deal — the three core statements plus tax, built on top of
the proforma `solve()` output (NOI, debt, reversion, cash flows).

- **Income statement** — a stabilized operating P&L (Potential Gross Rent → vacancy/credit loss →
  Effective Gross Income → operating expenses → **NOI**; then interest, **depreciation**, income tax →
  **net income**), plus a year-by-year summary across the hold.
- **Balance sheet** — Assets (land + depreciable improvements net of accumulated depreciation +
  capitalized financing + cash) = Liabilities (loan) + Equity (paid-in + retained). It **balances**
  every year (exposes a `balanced` flag).
- **Cash-flow statement** — GAAP three-section (Operating / Investing / Financing), indirect method
  (net income + depreciation add-back).
- **Tax** — straight-line depreciation (27.5-yr residential / 39-yr commercial; land non-depreciable),
  annual income tax on taxable income, and at sale: **depreciation recapture** (≤25%) stacked on
  **capital-gains** tax (+ NIIT). Drives an **after-tax** IRR / equity multiple.
- **Two-sided budget** — the development budget as **Uses** (left) vs **Sources** (right); both tie.

Pure functions over plain dicts (the solve result + assumptions) so the math is unit-testable.
Institutional defaults are explicit and overridable via the `tax` assumption block; everything is an
estimate, not tax advice.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .proforma import returns as _ret

TAX_DEFAULTS = {
    "income_tax_rate": 0.25,      # blended ordinary rate on operating taxable income
    "depreciation_years": 27.5,   # 27.5 residential · 39 commercial; land is never depreciated
    "capital_gains_rate": 0.20,   # long-term federal capital gains
    "niit_rate": 0.038,           # net investment income tax, stacked on cap gains
    "recapture_rate": 0.25,       # unrecaptured §1250 depreciation recapture (max 25%)
}


def _r(x: float) -> float:
    return round(float(x), 2)


def _land_amount(assumptions: dict) -> float:
    return round(sum(float(l.get("amount", 0)) for l in assumptions.get("cost_lines", [])
                     if l.get("category") == "land"), 2)


def depreciation_schedule(building_basis: float, life_years: float, hold_years: int) -> list[float]:
    """Straight-line depreciation per operating year, capped so it never exceeds the basis."""
    annual = building_basis / life_years if life_years else 0.0
    out, taken = [], 0.0
    for _ in range(hold_years):
        d = min(annual, max(0.0, building_basis - taken))
        out.append(round(d, 2))
        taken += d
    return out


def sale_tax(sale_price: float, selling_costs: float, land: float, building_basis: float,
             accumulated_depreciation: float, tax: dict, suspended_loss: float = 0.0) -> dict[str, Any]:
    """Tax due at disposition: §1250 depreciation recapture (≤25%) plus long-term capital gains (+NIIT)
    on the remaining gain. Recapture and capital gains are separate calcs that stack on the same sale.
    Any `suspended_loss` (passive losses released on full disposition) first reduces the gain."""
    total_basis = land + building_basis
    adjusted_basis = total_basis - accumulated_depreciation
    net_sale = sale_price - selling_costs
    total_gain = max(0.0, net_sale - adjusted_basis)
    loss_used = min(suspended_loss, total_gain)                  # freed passive losses offset the gain
    gain = total_gain - loss_used
    recaptured = min(accumulated_depreciation, gain)            # taxed at the recapture rate
    cap_gain = max(0.0, gain - recaptured)                      # the rest is long-term capital gain
    recapture_tax = recaptured * float(tax["recapture_rate"])
    cap_gains_tax = cap_gain * (float(tax["capital_gains_rate"]) + float(tax["niit_rate"]))
    return {
        "sale_price": _r(sale_price), "selling_costs": _r(selling_costs), "net_sale": _r(net_sale),
        "adjusted_basis": _r(adjusted_basis), "total_gain": _r(total_gain),
        "suspended_loss_used": _r(loss_used), "taxable_gain": _r(gain),
        "depreciation_recaptured": _r(recaptured), "recapture_tax": _r(recapture_tax),
        "capital_gain": _r(cap_gain), "capital_gains_tax": _r(cap_gains_tax),
        "total_sale_tax": _r(recapture_tax + cap_gains_tax),
    }


def statements(solve: dict, assumptions: dict) -> dict[str, Any]:
    """Assemble the three statements + tax + two-sided budget from a solved proforma."""
    tax = {**TAX_DEFAULTS, **(assumptions.get("tax") or {})}
    su = solve["sources_uses"]
    ops_in = assumptions["operations"]
    timing = assumptions["timing"]
    rate = float(assumptions["debt"]["rate"])
    hold_years = max(1, int(round(float(timing["hold_years"]))))

    land = _land_amount(assumptions)
    other_capitalized = float(su.get("loan_fees", 0)) + float(su.get("interest_reserve", 0))
    total_uses = float(su["total_uses"])
    building_basis = max(0.0, total_uses - land - other_capitalized)   # depreciable improvements
    loan = float(su["loan_amount"])
    paid_in = float(su["equity"])

    # --- annual NOI across the hold (from the monthly operating cash flow) -----
    noi_monthly = solve["cash_flow"]["noi_monthly"]
    noi_by_year = [round(sum(noi_monthly[y * 12:(y + 1) * 12]), 2) for y in range(hold_years)]
    interest_annual = round(loan * rate, 2)                  # interest-only during operations
    depr = depreciation_schedule(building_basis, float(tax["depreciation_years"]), hold_years)
    rate_inc = float(tax["income_tax_rate"])

    # --- year-by-year operating rows -----------------------------------------
    # Passive activity losses (real estate is passive): a loss year yields no current tax benefit —
    # it's suspended and carried forward to offset later passive income, with the remainder released
    # against the gain at sale (§469). So income tax is never negative; the shield is deferred.
    years, accum_depr, carryforward = [], 0.0, 0.0
    for y in range(hold_years):
        noi = noi_by_year[y]
        d = depr[y]
        taxable = round(noi - interest_annual - d, 2)
        if taxable >= 0:
            used = round(min(taxable, carryforward), 2)        # prior suspended losses offset income
            carryforward = round(carryforward - used, 2)
            income_tax = round((taxable - used) * rate_inc, 2)
        else:
            used = 0.0
            carryforward = round(carryforward - taxable, 2)    # taxable < 0 → grows the suspended loss
            income_tax = 0.0
        net_income = round(taxable - income_tax, 2)
        after_tax_cash = round(noi - interest_annual - income_tax, 2)   # depreciation is non-cash
        accum_depr = round(accum_depr + d, 2)
        years.append({"year": y + 1, "noi": noi, "interest": interest_annual, "depreciation": d,
                      "taxable_income": taxable, "loss_carryforward_used": used,
                      "loss_carryforward_end": carryforward, "income_tax": income_tax,
                      "net_income": net_income, "after_tax_cash_flow": after_tax_cash,
                      "accumulated_depreciation": accum_depr})
    suspended_loss = carryforward                              # released against the gain at sale

    # --- stabilized operating P&L (detailed income statement) -----------------
    occ = float(ops_in["stabilized_occ"])
    pgr = float(ops_in["potential_rent_annual"])
    credit = float(ops_in.get("credit_loss_pct", 0))
    other_income = float(ops_in.get("other_income_annual", 0)) * occ
    vacancy_credit = round(pgr - pgr * occ * (1 - credit), 2)         # lost rent (vacancy + credit)
    egi = round(pgr - vacancy_credit + other_income, 2)
    opex = float(ops_in["opex_annual"])
    reserves = float(ops_in.get("reserves_annual", 0))
    noi_stab = round(egi - opex - reserves, 2)
    last = years[-1]                                            # the fully-stabilized operating year
    income_statement = {
        "lines": [
            {"label": "Potential gross rent", "amount": _r(pgr)},
            {"label": "Vacancy & credit loss", "amount": _r(-vacancy_credit)},
            {"label": "Other income", "amount": _r(other_income)},
            {"label": "Effective gross income", "amount": _r(egi), "subtotal": True},
            {"label": "Operating expenses", "amount": _r(-opex)},
            {"label": "Capital reserves", "amount": _r(-reserves)},
            {"label": "Net operating income (NOI)", "amount": _r(noi_stab), "subtotal": True},
            {"label": "Interest expense", "amount": _r(-last["interest"])},
            {"label": "Depreciation", "amount": _r(-last["depreciation"])},
            {"label": "Pre-tax income", "amount": _r(last["taxable_income"]), "subtotal": True},
            {"label": "Income tax", "amount": _r(-last["income_tax"])},
            {"label": "Net income", "amount": _r(last["net_income"]), "total": True},
        ],
        "by_year": years,
        "note": "Stabilized year shown. Real estate is passive: loss years are suspended (no current "
                "benefit) and carried forward, releasing against the gain at sale. Estimate, not tax advice.",
    }

    # --- balance sheet per year-end (full distribution → cash held flat) ------
    # distributions each year = after-tax cash flow, so retained earnings fall by accumulated
    # depreciation exactly as net book value does → Assets always equal Liabilities + Equity.
    balance_sheets = []
    accum = 0.0
    for y in range(hold_years):
        accum = round(accum + depr[y], 2)
        net_improvements = round(building_basis - accum, 2)
        assets = round(land + net_improvements + other_capitalized, 2)
        retained = round(-accum, 2)                          # NI − distributions, cumulative
        equity = round(paid_in + retained, 2)
        balance_sheets.append({
            "year": y + 1,
            "assets": {"land": _r(land), "improvements_net": _r(net_improvements),
                       "accumulated_depreciation": _r(accum), "capitalized_financing": _r(other_capitalized),
                       "cash": 0.0, "total": _r(assets)},
            "liabilities": {"loan": _r(loan), "total": _r(loan)},
            "equity": {"paid_in_capital": _r(paid_in), "retained_earnings": _r(retained), "total": _r(equity)},
            "balanced": abs(assets - (loan + equity)) < 1.0,
        })

    # --- cash-flow statement (GAAP three-section, indirect) -------------------
    rev = solve["operations"]["reversion"]
    gross_sale = float(rev.get("gross_sale", 0))
    selling_costs = float(rev.get("selling_costs", 0))
    loan_payoff = float(rev.get("loan_payoff", loan))
    stax = sale_tax(gross_sale, selling_costs, land, building_basis, accum, tax, suspended_loss)
    cfo = round(sum(r["after_tax_cash_flow"] for r in years), 2)
    cfi = round(-total_uses + (gross_sale - selling_costs) - stax["total_sale_tax"], 2)
    distributions = round(cfo + (gross_sale - selling_costs) - stax["total_sale_tax"] - loan_payoff, 2)
    cff = round(loan + paid_in - loan_payoff - distributions, 2)
    # per-year three-section cash flow (full distribution → cash flat; the sale lands in the final year)
    cfs_by_year = []
    for i, r in enumerate(years):
        last_y = i == hold_years - 1
        op = r["after_tax_cash_flow"]
        inv = round((gross_sale - selling_costs) - stax["total_sale_tax"], 2) if last_y else 0.0
        repay = -loan_payoff if last_y else 0.0
        dist = round(op + inv + repay, 2)              # distribute all available cash each year
        cfs_by_year.append({"year": r["year"], "operating": op, "investing": inv,
                            "loan_repayment": _r(repay), "distributions": _r(-dist),
                            "net_change_in_cash": _r(op + inv + repay - dist)})
    cash_flow_statement = {
        "operating": {"after_tax_operating_cash_flow": cfo,
                      "note": "NOI − interest − income tax (net income + depreciation add-back)"},
        "investing": {"development_cost": _r(-total_uses), "net_sale_proceeds": _r(gross_sale - selling_costs),
                      "sale_tax": _r(-stax["total_sale_tax"]), "total": cfi},
        "financing": {"loan_proceeds": _r(loan), "equity_contributions": _r(paid_in),
                      "loan_repayment": _r(-loan_payoff), "distributions": _r(-distributions), "total": cff},
        "net_change_in_cash": _r(cfo + cfi + cff),
        "by_year": cfs_by_year,
    }

    # --- after-tax returns (levered equity, net of income + sale tax) ---------
    iso_dates = solve["cash_flow"]["dates"]
    annual_tax = [r["income_tax"] for r in years]
    # subtract each year's income tax in its last operating month, and the sale tax in the final
    # month — a pragmatic after-tax equity stream for an after-tax IRR / equity multiple
    at_equity = list(solve["cash_flow"]["equity"])
    construction_m = int(timing["construction_months"])
    for y in range(hold_years):
        idx = construction_m + (y + 1) * 12 - 1
        if 0 <= idx < len(at_equity):
            at_equity[idx] -= annual_tax[y]
    at_equity[-1] -= stax["total_sale_tax"]
    at_cf = list(zip([date.fromisoformat(s) for s in iso_dates], at_equity))
    contrib = sum(-c for _, c in at_cf if c < 0)
    distrib = sum(c for _, c in at_cf if c > 0)
    after_tax = {
        "equity_irr": _ret.xirr(at_cf),
        "equity_multiple": round(_ret.equity_multiple(contrib, distrib), 3) if contrib else None,
        "total_income_tax": _r(sum(annual_tax)),
        "total_sale_tax": stax["total_sale_tax"],
        "suspended_loss_at_sale": _r(suspended_loss),
    }

    return {
        "assumptions": {"income_tax_rate": rate_inc, "depreciation_years": float(tax["depreciation_years"]),
                        "capital_gains_rate": float(tax["capital_gains_rate"]),
                        "niit_rate": float(tax["niit_rate"]), "recapture_rate": float(tax["recapture_rate"]),
                        "land": _r(land), "depreciable_basis": _r(building_basis)},
        "income_statement": income_statement,
        "balance_sheet": {
            "by_year": balance_sheets,
            # EMPTY-IS-CLEAN: `balance_sheets` cannot be empty. `hold_years` is
            # `max(1, int(round(float(timing["hold_years"]))))` above, and the loop that builds this
            # list runs `for y in range(hold_years)` — so it always appends at least one year-end.
            # QUANT-VACUOUS: declared rather than guarded because `bool(balance_sheets) and ...`
            # would read as a possibility the arithmetic above has already excluded.
            "balanced": all(b["balanced"] for b in balance_sheets)},
        "cash_flow_statement": cash_flow_statement,
        "tax": {"depreciation_by_year": depr, "annual": years, "sale": stax,
                "suspended_loss_at_sale": _r(suspended_loss)},
        "after_tax_returns": after_tax,
        "two_sided_budget": two_sided_budget(solve, assumptions),
    }


def two_sided_budget(solve: dict, assumptions: dict) -> dict[str, Any]:
    """The development budget as Uses (left) vs Sources (right) — both tie to the total project cost."""
    su = solve["sources_uses"]
    land = _land_amount(assumptions)
    # uses: land + improvements + financing (loan fees + interest reserve); both sides equal total_uses
    financing = round(float(su.get("loan_fees", 0)) + float(su.get("interest_reserve", 0)), 2)
    improvements = round(float(su["total_uses"]) - land - financing, 2)
    uses = [u for u in (
        {"label": "Land / acquisition", "amount": _r(land)},
        {"label": "Improvements (hard + soft)", "amount": _r(improvements)},
        {"label": "Financing (fees + interest reserve)", "amount": _r(financing)},
    ) if u["amount"]]
    sources = [s for s in (
        {"label": "Senior debt", "amount": _r(su["loan_amount"])},
        {"label": "LP equity", "amount": _r(su.get("lp_contribution", 0))},
        {"label": "GP equity", "amount": _r(su.get("gp_contribution", 0))},
    ) if s["amount"]]
    total_uses = round(sum(u["amount"] for u in uses), 2)
    total_sources = round(sum(s["amount"] for s in sources), 2)
    return {
        "uses": uses, "sources": sources,
        "total_uses": total_uses, "total_sources": total_sources,
        "balanced": abs(total_uses - total_sources) < 1.0,
    }
