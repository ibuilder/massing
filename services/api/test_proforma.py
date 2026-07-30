"""Proforma engine tests (Phase 1). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_proforma.py
Asserts the invariants the guide calls non-negotiable for a finance product."""
from datetime import date

from aec_api.proforma import returns as ret
from aec_api.proforma.schedule import monthly_uses, scurve_weights
from aec_api.proforma.solve import solve
from aec_api.proforma.sources_uses import solve_sources_uses
from aec_api.proforma.waterfall import run_waterfall

# --- XIRR / XNPV ------------------------------------------------------------
assert abs(ret.xirr([(date(2026, 1, 1), -100), (date(2027, 1, 1), 110)]) - 0.10) < 1e-3
assert ret.xirr([(date(2026, 1, 1), -100), (date(2027, 1, 1), -10)]) is None  # no sign change
# XNPV at the IRR is ~0
r = ret.xirr([(date(2026, 1, 1), -1000), (date(2027, 1, 1), 200), (date(2028, 1, 1), 1100)])
assert abs(ret.xnpv(r, [(date(2026, 1, 1), -1000), (date(2027, 1, 1), 200), (date(2028, 1, 1), 1100)])) < 1e-2

# --- S-curve sums to 1 ------------------------------------------------------
assert abs(scurve_weights(12).sum() - 1.0) < 1e-9
u = monthly_uses([{"amount": 1_000_000, "start_month": 0, "end_month": 11, "curve": "scurve"}], 12)
assert abs(u.sum() - 1_000_000) < 1e-3

# --- interest-reserve circularity converges to a fixed point ----------------
su = solve_sources_uses(u, ltc=0.65, annual_rate=0.09)
su2 = solve_sources_uses(u, ltc=0.65, annual_rate=0.09)
assert abs(su["interest_reserve"] - su2["interest_reserve"]) < 1.0  # deterministic
assert su["interest_reserve"] > 0
# Sources == Uses (the solved identity)
assert abs((su["loan_amount"] + su["equity"]) - su["total_uses"]) < 1.0

# --- waterfall: distributions reconcile to distributable cash ---------------
dates = [date(2026, 1, 1)] + [date(2027 + i, 1, 1) for i in range(4)]
dist = [50_000, 60_000, 70_000, 2_000_000]
wf = run_waterfall(dist, dates, lp_contrib=900_000, gp_contrib=100_000, pref_rate=0.08,
                   tiers=[{"hurdle": 0.12, "lp": 0.8, "gp": 0.2}, {"hurdle": None, "lp": 0.6, "gp": 0.4}])
assert abs((wf["lp_distributions"] + wf["gp_distributions"]) - sum(dist)) < 1.0  # all cash split
assert wf["lp_irr"] is not None and wf["lp_irr"] >= 0.08 - 1e-3                  # pref met
# higher pref/promote never increases GP share of a fixed pot beyond residual logic
wf_eu = run_waterfall(dist, dates, 900_000, 100_000, 0.08,
                      [{"hurdle": 0.12, "lp": 0.8, "gp": 0.2}, {"hurdle": None, "lp": 0.6, "gp": 0.4}],
                      style="european")
assert wf_eu["gp_distributions"] <= wf["gp_distributions"] + 1.0  # European withholds promote

# --- full solve: a small multifamily deal -----------------------------------
deal = {
    "timing": {"construction_months": 18, "leaseup_months": 12, "hold_years": 5, "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront", "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Construction", "amount": 20_000_000, "curve": "scurve", "start_month": 1, "end_month": 17},
        {"category": "soft", "name": "Soft costs", "amount": 3_000_000, "curve": "linear", "start_month": 0, "end_month": 17},
        {"category": "contingency", "name": "Contingency", "amount": 1_000_000, "curve": "scurve", "start_month": 1, "end_month": 17},
    ],
    "debt": {"ltc": 0.65, "rate": 0.085, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 120_000,
                   "opex_annual": 1_300_000, "stabilized_occ": 0.94, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": 0.12, "lp": 0.8, "gp": 0.2},
                            {"hurdle": 0.18, "lp": 0.7, "gp": 0.3},
                            {"hurdle": None, "lp": 0.6, "gp": 0.4}]},
    "discount_rate": 0.10,
}
res = solve(deal)
su_r = res["sources_uses"]
assert abs((su_r["loan_amount"] + su_r["equity"]) - su_r["total_uses"]) < su_r["loan_fees"] + 2.0
assert su_r["interest_reserve"] > 0
assert res["returns"]["project_irr"] is not None and res["returns"]["equity_irr"] is not None
assert res["returns"]["equity_multiple"] > 1.0
wfr = res["waterfall"]
# distributions reconcile to POSITIVE distributable (negative = operating deficit, not a payout)
assert abs((wfr["lp_distributions"] + wfr["gp_distributions"])
           - sum(max(p["distributable"], 0) for p in wfr["periods"])) < 5.0

# --- U2: capital reserves are deducted above NOI → lower value + IRR --------
import copy  # noqa: E402

deal_res = copy.deepcopy(deal)
deal_res["operations"]["reserves_annual"] = 300_000
res_res = solve(deal_res)
assert res_res["returns"]["equity_irr"] < res["returns"]["equity_irr"], "reserves should lower IRR"
# reserves reduce the as-stabilized value (NOI ÷ cap) used for exit + debt sizing
assert res_res["sources_uses"]["total_uses"] <= res["sources_uses"]["total_uses"] + 1.0

# --- sensitivity: monotonic two-variable table ------------------------------
from aec_api.proforma.sensitivity import sensitivity  # noqa: E402

sens = sensitivity(deal, "exit.exit_cap", [0.05, 0.055, 0.06],
                   "cost_lines.1.amount", [18_000_000, 20_000_000, 22_000_000],
                   "returns.equity_irr")
m = sens["matrix"]
assert m[0][0] > m[0][-1]    # lower exit cap → higher IRR
assert m[0][0] > m[-1][0]    # cheaper hard cost → higher IRR

# --- draws bridge: a cost overrun re-forecasts a lower IRR -------------------
from aec_api.proforma.draws import reforecast  # noqa: E402

# at month 10, hard costs are 20% over budget-to-date; estimate cost-to-complete higher too
actuals = [
    {"actual_to_date": 4_000_000},                                    # land (on budget)
    {"actual_to_date": 9_000_000, "committed": 22_000_000, "cost_to_complete": 15_000_000},  # hard: 24M vs 20M budget
    {"actual_to_date": 1_800_000},                                    # soft
    {"actual_to_date": 600_000},                                      # contingency
]
fc = reforecast(deal, actuals, as_of_month=10)
assert fc["totals"]["forecast_at_completion"] > fc["totals"]["budget"]        # overrun
assert fc["totals"]["variance_to_budget"] > 0
assert fc["irr_delta"] is not None and fc["irr_delta"] < 0                    # overrun → lower IRR
hard = next(L for L in fc["lines"] if L["category"] == "hard")
assert hard["forecast_at_completion"] == 9_000_000 + 15_000_000              # actual + CTC

# --- debt sizing: lesser-of LTC / LTV / DSCR --------------------------------
# base deal is LTC-bound (no caps)
assert res["debt_sizing"]["binding_constraint"] == "ltc", res["debt_sizing"]
base_loan = res["sources_uses"]["loan_amount"]

# a tight DSCR must reduce the loan below the LTC amount and lift equity
deal_dscr = {**deal, "debt": {**deal["debt"], "min_dscr": 1.5}}
rd = solve(deal_dscr)
assert rd["debt_sizing"]["binding_constraint"] == "dscr", rd["debt_sizing"]
assert rd["sources_uses"]["loan_amount"] < base_loan
assert rd["sources_uses"]["equity"] > res["sources_uses"]["equity"]
assert abs(rd["debt_sizing"]["actual_dscr"] - 1.5) < 0.02          # sized right to the constraint
assert rd["sources_uses"]["effective_ltc"] < deal["debt"]["ltc"]

# a generous LTV/DSCR leaves LTC binding (loan unchanged)
deal_loose = {**deal, "debt": {**deal["debt"], "max_ltv": 0.95, "min_dscr": 1.0}}
rl = solve(deal_loose)
assert rl["debt_sizing"]["binding_constraint"] == "ltc", rl["debt_sizing"]
assert abs(rl["sources_uses"]["loan_amount"] - base_loan) < 1.0

# --- Monte Carlo: probabilistic risk distribution ---------------------------
from aec_api.proforma.monte_carlo import monte_carlo  # noqa: E402

mc_vars = [
    {"path": "exit.exit_cap", "dist": {"kind": "triangular", "low": 0.05, "mode": 0.055, "high": 0.065}},
    {"path": "cost_lines.1.amount", "dist": {"kind": "triangular", "low": 18_000_000, "mode": 20_000_000, "high": 24_000_000}},
    {"path": "operations.potential_rent_annual", "dist": {"kind": "normal", "mean": 3_600_000, "std": 200_000, "min": 3_000_000}},
]
mc = monte_carlo(deal, mc_vars, iterations=600, seed=7, targets={"returns.equity_irr": 0.15})
assert mc["solved"] + mc["failures"] == 600 and mc["failures"] == 0, mc["failures"]
eq = mc["metrics"]["returns.equity_irr"]
assert eq["p10"] < eq["p50"] < eq["p90"], eq                       # ordered percentiles
assert 0.0 <= eq["prob_at_least"] <= 1.0                            # P[IRR ≥ 15%] is a probability
assert sum(eq["histogram"]["counts"]) == eq["n"]                   # histogram covers every sample
assert eq["p5"] <= res["returns"]["equity_irr"] <= eq["p95"]       # base case sits inside the spread
# reproducible: same seed → identical distribution; clamp respected (rent never < 3.0M is implicit)
mc_again = monte_carlo(deal, mc_vars, iterations=600, seed=7, targets={"returns.equity_irr": 0.15})
assert mc_again["metrics"]["returns.equity_irr"]["p50"] == eq["p50"], "seeded run must reproduce"

print("PROFORMA OK")
print(f"  monte-carlo (600 draws): equity IRR P10 {eq['p10']*100:.1f}% | P50 {eq['p50']*100:.1f}%"
      f" | P90 {eq['p90']*100:.1f}% | P[IRR>=15%] {eq['prob_at_least']*100:.0f}%")
print(f"  S&U: uses ${su_r['total_uses']:,.0f} = loan ${su_r['loan_amount']:,.0f} + equity ${su_r['equity']:,.0f}"
      f" (int reserve ${su_r['interest_reserve']:,.0f})")
print(f"  returns: project IRR {res['returns']['project_irr']*100:.1f}% | equity IRR {res['returns']['equity_irr']*100:.1f}%"
      f" | EM {res['returns']['equity_multiple']} | YoC {res['returns']['yield_on_cost']*100:.2f}%"
      f" | spread {res['returns']['dev_spread']*1e4:.0f} bps")
import numpy as np  # noqa: E402

# ---- REVIEW FIX: P[metric >= target] counts EVERY solved draw ----------------------------------------
# `_summary` stripped NaNs and then took the probability over what was left, which silently answers
# "P[metric >= target | metric is defined]". An undefined equity IRR is a draw where the deal never
# returned capital -- the worst outcome, not a missing one -- so dropping those flattered a deal
# exactly when it was riskiest. The tests only ever range-checked this value, so nothing caught it.
from aec_api.proforma.monte_carlo import _summary as _mc_summary  # noqa: E402

_nan = float("nan")
_mixed = np.array([_nan] * 400 + [0.18] * 600, dtype=float)
_s = _mc_summary(_mixed, target=0.15)
assert _s["n"] == 600 and _s["undefined"] == 400, _s
# 600 of 1000 draws clear 15% -- not 600 of 600
assert abs(_s["prob_at_least"] - 0.60) < 1e-9, _s["prob_at_least"]
# the conditional figure is still reported, so the gap between the two is visible rather than lost
assert abs(_s["prob_at_least_of_defined"] - 1.00) < 1e-9, _s
# with nothing undefined the number is unchanged and the extra key stays away
_all_def = _mc_summary(np.array([0.10, 0.20, 0.30]), target=0.15)
assert abs(_all_def["prob_at_least"] - 2 / 3) < 1e-4, _all_def   # reported at 4dp
assert _all_def["undefined"] == 0 and "prob_at_least_of_defined" not in _all_def, _all_def
# every draw undefined: no stats to invent, and the count is still stated
assert _mc_summary(np.array([_nan, _nan]), target=0.15) == {"n": 0, "undefined": 2}

# ---- REVIEW FIX: `loan_first` actually deploys the equity it sizes -----------------------------------
# `loan_first` set from_equity = 0.0 on EVERY draw and never switched, so the loan funded 100% of the
# job forever: equity was sized and never used, and the balance ran past its own sizing by exactly the
# undeployed equity ($26.2M drawn against an $18.3M loan on a $24M project) while `effective_ltc` still
# reported the requested 0.70. It is a public schema value (proforma_schemas.Debt.funding) and had no
# test at all. The loan now funds only up to its commitment, then equity.
from aec_api.proforma.sources_uses import solve_sources_uses as _ssu  # noqa: E402

_uses = np.array([1_000_000.0] * 24)
_modes = {f: _ssu(_uses, ltc=0.70, annual_rate=0.09, funding=f)
          for f in ("equity_first", "pari_passu", "loan_first")}

# every mode must fund every draw -- a schedule that funds less describes a project that stopped
for _f, _r in _modes.items():
    _funded = sum(_r["loan"]["equity_draws"]) + sum(_r["loan"]["loan_draws"])
    assert abs(_funded - float(_uses.sum())) < 1.0, (_f, _funded)

# THE REGRESSION: loan_first must put the sized equity to work rather than leaving it on the table
_lf = _modes["loan_first"]
assert _lf["loan"]["equity_deployed"] > 0.0, "loan_first deployed no equity at all"
assert _lf["loan"]["equity_deployed"] > 0.8 * _lf["equity"], (
    _lf["loan"]["equity_deployed"], _lf["equity"])
# and the balance must no longer overrun by the whole undeployed equity (was +7.86M on this fixture)
assert _lf["loan"]["ending_balance"] - _lf["loan_amount"] < 0.10 * _lf["loan_amount"], _lf
# NOTE: a residual overrun remains under loan_first -- interest capitalizing after the commitment is
# reached. Whether that interest may capitalize or must be paid in cash is a loan-terms question, so it
# is deliberately NOT asserted here as correct. See the review notes.

# the two modes that were already right are UNCHANGED -- the loop was restructured to capitalize
# interest before apportioning a draw, which must be arithmetically identical for these
for _f in ("equity_first", "pari_passu"):
    _r = _modes[_f]
    assert abs(_r["loan"]["ending_balance"] - _r["loan_amount"]) < 1000.0, (_f, _r["loan_amount"])
    assert abs(_r["loan"]["equity_deployed"] - _r["equity"]) < 1.0, (_f, _r["equity"])
assert abs(_modes["equity_first"]["interest_reserve"] - 995_933) < 500, _modes["equity_first"]
assert abs(_modes["pari_passu"]["interest_reserve"] - 1_491_138) < 500, _modes["pari_passu"]

# ---- REVIEW FIX: loan fees are charged to the equity CASH FLOW, not just to the S&U table ------------
# `equity_total = su["equity"] + loan_fees` and lp/gp_contribution both carried the fee, and
# `total_dev_cost` counted it -- but the equity cash flow never did, so `returns.equity_irr` ignored a
# cost this model explicitly says the equity funds. The invariant that catches it: the construction
# leg of the equity cash flow must reconcile to `sources_uses.equity` to the cent.
_fee_deal = copy.deepcopy(deal)
_fee_deal["debt"]["points"] = 0.01
_fr = solve(_fee_deal)
_C = int(_fee_deal["timing"]["construction_months"])
_constr_leg = -sum(x for x in _fr["cash_flow"]["equity"][:_C] if x < 0)
assert _fr["sources_uses"]["loan_fees"] > 0, _fr["sources_uses"]
assert abs(_constr_leg - _fr["sources_uses"]["equity"]) < 0.02, (
    _constr_leg, _fr["sources_uses"]["equity"], "construction equity leg must include the loan fee")

# charging a real cost can only LOWER the levered return
_nofee = copy.deepcopy(_fee_deal)
_nofee["debt"]["points"] = 0.0
_nr = solve(_nofee)
assert _fr["returns"]["equity_irr"] < _nr["returns"]["equity_irr"], (
    _fr["returns"]["equity_irr"], _nr["returns"]["equity_irr"])
assert _fr["returns"]["equity_multiple"] < _nr["returns"]["equity_multiple"]

# ...and must NOT move the unlevered return: a financing cost is not a project cost, so the fee
# belongs in eq_cf and never in proj_cf.
assert abs(_fr["returns"]["project_irr"] - _nr["returns"]["project_irr"]) < 1e-9, (
    _fr["returns"]["project_irr"], _nr["returns"]["project_irr"])

# NOTE: `returns.equity_irr` and `waterfall.lp_irr` still rest on DIFFERENT capital bases -- the
# equity cash flow carries lease-up operating deficits as capital calls, while run_waterfall discards
# negative distributable via max(cash, 0.0), so the waterfall never sees them. Whether those deficits
# are additional LP/GP contributions that accrue pref is a JV-terms question and is deliberately NOT
# asserted here. See the review notes.

# ---- REVIEW FIX: a cost line's money is never silently dropped ---------------------------------------
# TWO defaults answered one question and disagreed: the Pydantic schema had end_month=0 while the
# engine's own dict default was total_months-1 ("runs to the end of construction"). The schema's won
# for every API caller, so a line posted with start_month>0 and no end_month got end_month=0,
# spread_line saw e < s, returned zeros, and the WHOLE line vanished -- from the uses vector, from
# total_uses, from the loan sizing and from every return metric, with nothing reporting it.
from aec_api.proforma.schedule import monthly_uses, unscheduled  # noqa: E402
from aec_api.routers.proforma_schemas import CostLine  # noqa: E402

_cl = CostLine(category="hard", name="Structure", amount=8_000_000, curve="scurve", start_month=3)
assert _cl.end_month is None, "absent end_month must mean 'to the end of construction', not month 0"
assert abs(monthly_uses([_cl.model_dump()], 18).sum() - 8_000_000) < 1.0, "line was silently zeroed"
assert unscheduled([_cl.model_dump()], 18) == [], "a schedulable line is not 'unscheduled'"

# money that genuinely cannot be scheduled (window wholly outside construction) is REPORTED, not
# dropped -- the same refusal fived makes for an element no rule prices.
_outside = [{"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront",
             "start_month": 0, "end_month": 0},
            {"category": "soft", "name": "FF&E", "amount": 2_500_000, "curve": "linear",
             "start_month": 20, "end_month": 24}]
_un = unscheduled(_outside, 18)
assert len(_un) == 1 and _un[0]["name"] == "FF&E", _un
assert _un[0]["amount"] == 2_500_000, _un
assert abs(monthly_uses(_outside, 18).sum() - 4_000_000) < 1.0   # it really is excluded
# ...and solve() surfaces it rather than underwriting a cheaper project in silence
_deal_out = copy.deepcopy(deal)
_deal_out["cost_lines"] = _deal_out["cost_lines"] + [
    {"category": "soft", "name": "Post-completion FF&E", "amount": 2_500_000, "curve": "linear",
     "start_month": 40, "end_month": 44}]
_ro = solve(_deal_out)
assert _ro["sources_uses"]["unscheduled_amount"] == 2_500_000, _ro["sources_uses"]
assert len(_ro["sources_uses"]["unscheduled_lines"]) == 1, _ro["sources_uses"]
# a well-formed deal stays quiet -- the signal is only worth having if it is not always on
assert solve(deal)["sources_uses"]["unscheduled_amount"] == 0
assert solve(deal)["sources_uses"]["unscheduled_lines"] == []

# ---- RESOLVED #1: preferred return accrual is STATED, not assumed --------------------------------
# The module documented "compounding" twice and implemented simple accrual on unreturned capital.
# Both are real deal terms, so it is now an explicit input echoed in the result, defaulted to the
# documented behaviour. Three unpaid periods on $1,000 @ 10%: simple 300, compounding 331.
from datetime import date as _d  # noqa: E402

from aec_api.proforma.waterfall import run_waterfall as _rw  # noqa: E402

_pd = [_d(2021, 1, 1), _d(2022, 1, 1), _d(2023, 1, 1), _d(2024, 1, 1)]


def _pref_paid(mode):
    r = _rw([0.0, 0.0, 3000.0], _pd, 1000.0, 0.0, 0.10,
            [{"hurdle": None, "lp": 0.5, "gp": 0.5}], "american", False, mode)
    assert r["pref_accrual"] == mode, r["pref_accrual"]
    return 2 * (r["lp_distributions"] - 2000)        # back out the pref actually paid


assert abs(_pref_paid("simple") - 300.0) < 0.01, _pref_paid("simple")
assert abs(_pref_paid("compounding") - 331.0) < 0.01, _pref_paid("compounding")
assert _pref_paid("compounding") > _pref_paid("simple"), "compounding must owe the LP more"
try:
    _rw([0.0], _pd[:2], 1000.0, 0.0, 0.10, [{"hurdle": None, "lp": 1.0, "gp": 0.0}],
        "american", False, "nonsense")
    raise AssertionError("an unknown pref_accrual must be refused, not silently defaulted")
except ValueError:
    pass

# ---- RESOLVED #4: an operating shortfall is a CAPITAL CALL that earns pref -----------------------
# run_waterfall did `remaining = max(cash, 0.0)`, so a negative period vanished: the LP's extra
# capital never entered the waterfall, pref never accrued on it, and waterfall.lp_irr rested on a
# smaller base than the deal-level equity IRR computed from the very same deal.
_call = _rw([-500.0, 0.0, 4000.0], _pd, 900.0, 100.0, 0.08,
            [{"hurdle": None, "lp": 0.8, "gp": 0.2}], "american", False, "compounding")
assert abs(_call["lp_capital_calls"] - 450.0) < 0.01, _call["lp_capital_calls"]   # 500 split 90/10
assert abs(_call["gp_capital_calls"] - 50.0) < 0.01, _call["gp_capital_calls"]
assert abs(_call["lp_invested"] - 1350.0) < 0.01, _call["lp_invested"]            # 900 + 450
# the pre-existing invariant must still hold: distributions reconcile to POSITIVE distributable
assert abs((_call["lp_distributions"] + _call["gp_distributions"])
           - sum(max(p["distributable"], 0) for p in _call["periods"])) < 5.0, _call
# a deal with no shortfall reports no calls, so the signal stays meaningful
_nocall = _rw([100.0, 100.0, 4000.0], _pd, 900.0, 100.0, 0.08,
              [{"hurdle": None, "lp": 0.8, "gp": 0.2}], "american", False, "compounding")
assert _nocall["lp_capital_calls"] == 0 and _nocall["gp_capital_calls"] == 0, _nocall

# ---- RESOLVED #2: capitalized interest may not exceed the loan COMMITMENT ------------------------
# Interest kept capitalizing after the loan was fully drawn, so the balance ran past its own sizing
# on compounding alone. It is now cash-paid once headroom is gone, and — the part that actually made
# it converge — the sources & uses fixed point sizes on TOTAL interest, since cash interest is a use
# that must be funded too.
from aec_api.proforma.sources_uses import solve_sources_uses as _ssu2  # noqa: E402

_u = np.array([1_000_000.0] * 24)
for _f in ("equity_first", "pari_passu", "loan_first"):
    _r = _ssu2(_u, ltc=0.70, annual_rate=0.09, funding=_f)
    assert _r["loan"]["ending_balance"] <= _r["loan_amount"] + 1000.0, (
        _f, _r["loan"]["ending_balance"], _r["loan_amount"])
    # sources must equal uses to the dollar
    assert abs((_r["loan_amount"] + _r["equity"]) - _r["total_uses"]) < 2.0, (_f, _r["total_uses"])
    assert abs(_r["interest_reserve"] + _r["cash_interest"] - _r["total_interest"]) < 1.0, _f
# only the front-loaded profile needs cash-pay interest; the other two fund it from the reserve
assert _ssu2(_u, ltc=0.70, annual_rate=0.09, funding="equity_first")["cash_interest"] == 0
assert _ssu2(_u, ltc=0.70, annual_rate=0.09, funding="loan_first")["cash_interest"] > 0

# ---- RESOLVED #3: the re-forecast actually re-forecasts ------------------------------------------
# `max(budget, actual)` returned the ORIGINAL budget for any line not yet over it, so a line 20% over
# at the halfway point forecast no overrun at all -- in the module whose stated purpose is to surface
# exactly that.
_fc_deal = copy.deepcopy(deal)
_fc_deal["cost_lines"] = [
    {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront",
     "start_month": 0, "end_month": 0},
    {"category": "hard", "name": "Construction", "amount": 20_000_000, "curve": "scurve",
     "start_month": 1, "end_month": 17}]
_hot = reforecast(_fc_deal, [{"actual_to_date": 4_000_000}, {"actual_to_date": 9_000_000}],
                  as_of_month=6)
_h = next(L for L in _hot["lines"] if L["category"] == "hard")
assert _h["actual_to_date"] > _h["budget_to_date"], "fixture must actually be running hot"
assert _h["variance_to_budget"] > 5_000_000, _h        # old code reported exactly 0 here
assert _h["forecast_basis"] == "remaining_budget", _h
assert _hot["irr_delta"] < 0, "a forecast overrun must lower the IRR"

# CPI is available but refuses to speak too early: dividing by a near-zero percent-complete turned a
# $9M spend against a $1.9M plan into a $96M forecast.
_cpi = reforecast(_fc_deal, [{"actual_to_date": 4_000_000}, {"actual_to_date": 9_000_000}],
                  as_of_month=6, method="cpi")
_hc = next(L for L in _cpi["lines"] if L["category"] == "hard")
assert _hc["forecast_basis"] == "remaining_budget", "too early for CPI — must fall back"
assert _hc["forecast_at_completion"] < 40_000_000, _hc["forecast_at_completion"]
# The fallback's ARITHMETIC, not just which branch it took. Found by mutation testing: the branch was
# exercised and only its `forecast_basis` label was asserted, so flipping its
# `actual + max(0.0, budget - budget_to_date)` to `min` survived — the forecast collapsed from
# 27,133,231.54 to 9,000,000 (spend-to-date, i.e. claiming the job is finished) and the `< 40,000,000`
# bound above passed just as happily. Checking a label proves which code ran, never what it computed.
assert abs(_hc["forecast_at_completion"]
           - (_hc["actual_to_date"] + max(0.0, _hc["budget"] - _hc["budget_to_date"]))) < 0.01, _hc
assert _hc["forecast_at_completion"] > _hc["actual_to_date"], (
    "a forecast at completion equal to spend-to-date says the job is done — it is month 6 of 17")
# late enough in the curve, CPI is used and is stated per line
_late = reforecast(_fc_deal, [{"actual_to_date": 4_000_000}, {"actual_to_date": 22_000_000}],
                   as_of_month=14, method="cpi")
_hl = next(L for L in _late["lines"] if L["category"] == "hard")
assert _hl["forecast_basis"] == "cpi", _hl

print(f"  waterfall: LP IRR {wfr['lp_irr']*100:.1f}% EM {wfr['lp_equity_multiple']} | GP IRR {wfr['gp_irr']*100:.1f}% EM {wfr['gp_equity_multiple']}")
