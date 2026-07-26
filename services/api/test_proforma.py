"""Proforma engine tests (Phase 1). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_proforma.py
Asserts the invariants the guide calls non-negotiable for a finance product."""
from datetime import date

from aec_api.proforma import returns as ret
from aec_api.proforma.sources_uses import solve_sources_uses
from aec_api.proforma.schedule import monthly_uses, scurve_weights
from aec_api.proforma.waterfall import run_waterfall
from aec_api.proforma.solve import solve

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

print(f"  waterfall: LP IRR {wfr['lp_irr']*100:.1f}% EM {wfr['lp_equity_multiple']} | GP IRR {wfr['gp_irr']*100:.1f}% EM {wfr['gp_equity_multiple']}")
