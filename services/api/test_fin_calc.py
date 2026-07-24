"""FIN-CALC — calculation trust: golden hand-computed references for the core return metrics,
and the residual-land-value inverse solver (bisection over the forward solve).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fin_calc.py"""
import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///./test_fin_calc.db"
os.environ["STORAGE_DIR"] = "./test_storage_fincalc"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_fin_calc.db"):
    os.remove("./test_fin_calc.db")

from aec_api.proforma import returns as ret  # noqa: E402
from aec_api.proforma.residual import residual_land_value  # noqa: E402
from aec_api.proforma.solve import solve  # noqa: E402
from aec_api.proforma.waterfall import run_waterfall  # noqa: E402

# --- golden references (hand-computed, exact closed forms) -----------------------------------------
# XIRR: -1000 today, +1210 in exactly 2 years → (1210/1000)^(1/2) - 1 = 10%
g = ret.xirr([(date(2026, 1, 1), -1000.0), (date(2028, 1, 1), 1210.0)])
assert abs(g - 0.10) < 1e-4, g
# XIRR: -1000, +500 @1y, +600 @2y → r solves 500/(1+r) + 600/(1+r)^2 = 1000 → r = 6.394% (quadratic)
g = ret.xirr([(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), 500.0), (date(2028, 1, 1), 600.0)])
assert abs(g - 0.063941) < 5e-4, g
# NPV @10% annual of monthly stream [-1200, +100 × 24 months]: closed-form annuity check
monthly = [-1200.0] + [100.0] * 24
r_m = (1 + 0.10) ** (1 / 12) - 1
golden_npv = -1200 + sum(100.0 / (1 + r_m) ** t for t in range(1, 25))
assert abs(ret.npv(0.10, monthly) - golden_npv) < 0.01
# equity multiple & yield-on-cost are pure ratios
assert ret.equity_multiple(1_000_000, 1_850_000) == 1.85
assert abs(ret.yield_on_cost(650_000, 10_000_000) - 0.065) < 1e-12
# Waterfall golden: LP 900 / GP 100 in, 8% pref, single 100/0 residual tier after exactly 1 year.
# Distributable 1100: pref LP 72, GP 8 → RoC LP 900, GP 100 → residual 20 split 80/20 → LP 988, GP 112.
wf = run_waterfall([1100.0], [date(2026, 1, 1), date(2027, 1, 1)], lp_contrib=900.0,
                   gp_contrib=100.0, pref_rate=0.08,
                   tiers=[{"hurdle": None, "lp": 0.8, "gp": 0.2}])
assert abs((wf["lp_distributions"] + wf["gp_distributions"]) - 1100.0) < 1e-6  # every dollar lands
assert wf["lp_distributions"] > wf["gp_distributions"]                          # pref + RoC ordering

# --- the residual-land inverse solver --------------------------------------------------------------
DEAL = {
    "timing": {"construction_months": 12, "leaseup_months": 6, "hold_years": 3,
               "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 2_000_000, "curve": "upfront",
         "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Build", "amount": 8_000_000, "curve": "scurve",
         "start_month": 1, "end_month": 11},
        {"category": "soft", "name": "Soft", "amount": 1_000_000, "curve": "linear",
         "start_month": 0, "end_month": 11},
    ],
    "debt": {"ltc": 0.6, "rate": 0.08, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 1_500_000, "other_income_annual": 0,
                   "opex_annual": 500_000, "stabilized_occ": 0.95, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.06, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
}

base_irr = solve(DEAL)["returns"]["equity_irr"]
assert base_irr is not None and base_irr > 0
# ask for exactly the base IRR → the solver should hand back ~the base land price
res = residual_land_value(DEAL, target="equity_irr", target_value=base_irr)
assert res["converged"], res
assert abs(res["land_value"] - 2_000_000) / 2_000_000 < 0.02, res["land_value"]
# consistency: forward-solving at the answer reproduces the target metric
check = solve({**DEAL, "cost_lines": [
    {**DEAL["cost_lines"][0], "amount": res["land_value"]}, *DEAL["cost_lines"][1:]]})
assert abs(check["returns"]["equity_irr"] - base_irr) < 5e-3
# a HIGHER return target → the developer can pay LESS for the land (monotonicity)
res_hi = residual_land_value(DEAL, target="equity_irr", target_value=base_irr + 0.03)
assert res_hi["converged"] and res_hi["land_value"] < res["land_value"], res_hi
# an impossible target reports honestly instead of inventing a number
impossible = residual_land_value(DEAL, target="equity_irr", target_value=9.99)
assert impossible["land_value"] is None and not impossible["converged"]
assert "not achievable" in impossible["note"]
# profit-margin target works and yield-on-cost rejects unknown targets loudly
pm = residual_land_value(DEAL, target="profit_margin", target_value=0.10)
assert pm["converged"] or pm["land_value"] is None
try:
    residual_land_value(DEAL, target="cap_rate", target_value=0.05)
    raise AssertionError("unknown target must ValueError")
except ValueError:
    pass

# --- route -----------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    r = c.post("/proforma/residual-land",
               json={"assumptions": DEAL, "target": "equity_irr", "target_value": round(base_irr, 4)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["converged"] and abs(body["land_value"] - 2_000_000) / 2_000_000 < 0.03, body
    assert c.post("/proforma/residual-land",
                  json={"assumptions": DEAL, "target": "nope", "target_value": 0.1}).status_code == 400

print("FIN-CALC OK - golden references hold: 2-year XIRR closed-form 10.00%, the quadratic "
      "two-flow XIRR 6.394%, monthly NPV vs the hand-built annuity sum, EM 1.85x, YoC 6.5%, the "
      "1100-on-1000 waterfall reconciles to the dollar; residual land value inverts the forward "
      "solve (asking for the base IRR returns the base land within 2%, forward-solving the answer "
      "reproduces the target, +300bp target -> lower land), an impossible target says 'not "
      "achievable' instead of inventing a number, and POST /proforma/residual-land serves it "
      "(unknown target 400).")
