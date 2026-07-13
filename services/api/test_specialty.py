"""Specialty assets — on-site energy + vertical-farm (PFAL) revenue engine + persistence.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_specialty.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_specialty.db"
os.environ["STORAGE_DIR"] = "./test_storage_specialty"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_specialty.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import specialty as sp  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- energy: solar capex + generation offset --------------------------------
e = sp.energy({"solar_sf": 500_000, "sf_per_panel": 20, "cost_per_panel": 330,
               "battery_units": 7, "rainwater_capex": 780_000})
assert e["solar_panels"] == 25_000, e["solar_panels"]
assert e["breakdown"]["solar"] == 25_000 * 330, e["breakdown"]
assert e["capex"] == 25_000 * 330 + 7 * 15_000 + 780_000, e["capex"]
assert e["generation_kwh_yr"] > 0 and e["annual_energy_offset"] > 0, e

# --- PFAL: towers from area, revenue, lighting opex --------------------------
f = sp.pfal({"pfal_sf": 40_000, "sf_per_tower": 1.7, "green_pct": 0.4})
assert f["towers"] == round(40_000 / 1.7), f["towers"]
assert f["annual_revenue"] > 0 and f["annual_opex"] > 0 and f["lighting_kwh_yr"] > 0, f

# --- summary + proforma deltas ----------------------------------------------
params = sp.starter()
s = sp.summarize(params)
assert s["capex_total"] == s["energy"]["capex"] + s["pfal"]["startup_capex"], s["capex_total"]
assert s["annual_net_contribution"] == s["annual_revenue"] + s["annual_energy_offset"] - s["annual_opex"]
d = sp.to_proforma_deltas(params)
assert d["cost_line"]["category"] == "hard" and d["cost_line"]["amount"] == s["capex_total"]
# deltas now use the risk-adjusted (underwritten) figures, not gross (U4)
assert d["other_income_annual_add"] == s["annual_revenue_underwritten"] + s["annual_offset_underwritten"]

# disabled assets contribute nothing
none = sp.summarize({"energy_enabled": False, "pfal_enabled": False})
assert none["capex_total"] == 0 and none["annual_revenue"] == 0, none

# --- U4: risk discount — underwritten revenue < gross; deltas use the haircut --------
sd = sp.summarize({**params, "risk_discount": 0.35})
assert sd["annual_revenue_underwritten"] == round(sd["annual_revenue"] * 0.65), sd
assert sd["annual_net_underwritten"] < sd["annual_net_contribution"], "risk-adjusted < gross"
dl = sp.to_proforma_deltas({**params, "risk_discount": 0.35})
assert dl["other_income_annual_add"] == sd["annual_revenue_underwritten"] + sd["annual_offset_underwritten"], dl
# a bigger discount underwrites less
assert sp.summarize({**params, "risk_discount": 0.6})["annual_revenue_underwritten"] < sd["annual_revenue_underwritten"]

# --- U4 depth: multi-year specialty P&L + production ramp --------------------
pf = sp.proforma(params, years=10, ramp_years=3, ramp_start=0.4)
assert len(pf["rows"]) == 10 and pf["rows"][0]["op_year"] == 1, pf["rows"][0]
# ramp: year-1 output is a fraction, reaching 100% by ramp_years
assert pf["rows"][0]["ramp"] == 0.4 and pf["rows"][2]["ramp"] == 1.0, [r["ramp"] for r in pf["rows"][:3]]
# early years earn less (revenue ramps, opex full from day 1) → net rises to a plateau
assert pf["rows"][0]["net"] < pf["rows"][2]["net"], "ramp lifts net toward stabilization"
assert all(pf["rows"][i]["net"] <= pf["rows"][i + 1]["net"] for i in range(2)), "net non-decreasing through ramp"
# last year is stabilized; terminal caps the stabilized net
assert pf["stabilized_net_annual"] == pf["rows"][-1]["net"], "last ramp year is stabilized"
assert pf["terminal_value"] == round(pf["stabilized_net_annual"] / 0.10), pf["terminal_value"]
assert pf["specialty_irr"] is not None and pf["payback_op_year"] and 1 <= pf["payback_op_year"] <= 10, pf
# cumulative net threads through the rows (last row's cumulative == reported cumulative_net)
assert pf["cumulative_net"] == pf["rows"][-1]["cumulative"], pf["cumulative_net"]
# a slower ramp (lower start, stretched over more years) lowers the specialty IRR
slow = sp.proforma(params, years=10, ramp_years=6, ramp_start=0.1)
assert slow["specialty_irr"] <= pf["specialty_irr"], "slower ramp -> lower specialty IRR"

# --- U4 depth: blended IRR — specialty folded into the RE equity stream ------
re_cf = [{"date": "2027-01-01", "amount": -10_000_000}, {"date": "2029-01-01", "amount": 1_500_000},
         {"date": "2032-01-01", "amount": 15_000_000}]
bl = sp.blended_irr(re_cf, params)
assert bl["re_only_irr"] is not None and bl["blended_irr"] is not None, bl
assert bl["blended_irr"] > bl["re_only_irr"], "a profitable specialty business lifts the blended IRR"
assert bl["irr_lift"] == round(bl["blended_irr"] - bl["re_only_irr"], 4), bl
assert bl["specialty"]["specialty_irr"] == sp.proforma(params, start_year=2028)["specialty_irr"], "reuses proforma"
# guarded when there are no equity cash flows
assert sp.blended_irr([], params)["blended_irr"] is None

# --- U4 depth: Monte-Carlo the specialty risk discount ----------------------
mc_vars = [{"path": "risk_discount", "dist": {"kind": "triangular", "low": 0.2, "mode": 0.35, "high": 0.6}},
           {"path": "pfal.green_price_lb", "dist": {"kind": "normal", "mean": 5.0, "std": 1.0, "min": 2.0}}]
mc = sp.monte_carlo(re_cf, params, mc_vars, iterations=200, seed=7)
assert mc["metrics"]["blended_irr"]["n"] == 200 and mc["metrics"]["specialty_irr"]["n"] > 0, mc
mcb = mc["metrics"]["blended_irr"]
assert mcb["p5"] <= mcb["p50"] <= mcb["p95"] and "histogram" in mcb, mcb   # ordered percentiles + histogram
# reproducible with a fixed seed
assert sp.monte_carlo(re_cf, params, mc_vars, iterations=200, seed=7)["metrics"]["blended_irr"]["p50"] == mcb["p50"]
# target-probability readout
mct = sp.monte_carlo(re_cf, params, mc_vars, iterations=200, seed=7, targets={"blended_irr": 0.15})
assert 0.0 <= mct["metrics"]["blended_irr"]["prob_at_least"] <= 1.0, mct
# a harsher risk-discount band underwrites less → a lower median blended IRR than a mild band
harsh = sp.monte_carlo(re_cf, params, [{"path": "risk_discount", "dist": {"kind": "uniform", "low": 0.6, "high": 0.9}}],
                       iterations=200, seed=7)
mild = sp.monte_carlo(re_cf, params, [{"path": "risk_discount", "dist": {"kind": "uniform", "low": 0.0, "high": 0.2}}],
                      iterations=200, seed=7)
assert harsh["metrics"]["blended_irr"]["p50"] <= mild["metrics"]["blended_irr"]["p50"], "harsher haircut -> lower IRR"

# --- U5: underwriting guardrails flag implausible returns ----------------------------
from aec_api import underwrite  # noqa: E402

hot = underwrite.guardrails({"returns": {"equity_irr": 0.71, "equity_multiple": 23.0, "dev_spread": 600}})
assert not hot["ok"] and any(f["metric"] == "equity_irr" and f["level"] == "high" for f in hot["flags"]), hot
sane = underwrite.guardrails({"returns": {"equity_irr": 0.16, "equity_multiple": 2.1, "dev_spread": 180}})
assert sane["ok"] and any(f["metric"] == "ok" for f in sane["flags"]), sane
thin = underwrite.guardrails({"returns": {"equity_irr": 0.10, "equity_multiple": 1.6, "dev_spread": -20}})
assert any(f["metric"] == "dev_spread" and f["level"] == "high" for f in thin["flags"]), thin

# --- U3: validate the exit cap against the deal's sale comps -------------------
_ok = {"returns": {"equity_irr": 0.16, "equity_multiple": 2.1, "dev_spread": 180, "exit_cap": 0.058}}
comps = [{"data": {"comp_type": "Sale", "cap_rate": 5.5}}, {"data": {"comp_type": "Sale", "cap_rate": 6.0}},
         {"data": {"comp_type": "Rent", "cap_rate": None}}]        # rent comp carries no cap → ignored
# an exit cap well under the comp band (0.058 stated but underwrite 0.045) → high flag
aggressive = underwrite.guardrails({"returns": {**_ok["returns"], "exit_cap": 0.045}}, comps=comps)
assert any(f["metric"] == "exit_cap" and f["level"] == "high" for f in aggressive["flags"]), aggressive
assert not aggressive["ok"], aggressive
# an exit cap inside the comp band but below the median (5.5–6.0%, median 5.75%) → info note, still ok
inband = underwrite.guardrails({"returns": {**_ok["returns"], "exit_cap": 0.056}}, comps=comps)
assert inband["ok"] and any(f["metric"] == "exit_cap" and f["level"] == "info" for f in inband["flags"]), inband
# an exit cap at/above the comp median is conservative → no exit-cap flag at all
soft = underwrite.guardrails({"returns": {**_ok["returns"], "exit_cap": 0.062}}, comps=comps)
assert not any(f["metric"] == "exit_cap" for f in soft["flags"]), soft
# no comps (or comps without cap rates) → no exit-cap flag (backward compatible)
nocomp = underwrite.guardrails(_ok, comps=[{"data": {"comp_type": "Rent"}}])
assert not any(f["metric"] == "exit_cap" for f in nocomp["flags"]), nocomp

# --- persistence round-trip --------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Vert Farm"}).json()["id"]
    g0 = c.get(f"/projects/{pid}/specialty").json()
    assert g0["summary"]["capex_total"] > 0 and "deltas" in g0, g0     # starter served
    r = c.put(f"/projects/{pid}/specialty", json=params)
    assert r.status_code == 200 and r.json()["summary"]["capex_total"] == s["capex_total"], r.text
    assert c.get(f"/projects/{pid}/specialty").json()["summary"]["capex_total"] == s["capex_total"]

    # U3 end-to-end: project-scoped solve validates the exit cap against the project's sale comps
    for cap in (5.5, 6.0):
        c.post(f"/projects/{pid}/modules/comparable", json={"data": {"address": f"comp-{cap}", "comp_type": "Sale", "cap_rate": cap}})
    deal = {
        "timing": {"construction_months": 18, "leaseup_months": 12, "hold_years": 5, "start_date": "2026-01-01"},
        "cost_lines": [{"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront", "start_month": 0, "end_month": 0},
                       {"category": "hard", "name": "Construction", "amount": 20_000_000, "curve": "scurve", "start_month": 1, "end_month": 17}],
        "debt": {"ltc": 0.65, "rate": 0.085, "points": 0.01, "funding": "equity_first"},
        "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
        "operations": {"potential_rent_annual": 3_600_000, "opex_annual": 1_300_000, "stabilized_occ": 0.94},
        "exit": {"exit_cap": 0.045, "selling_cost_pct": 0.02},   # 4.5% — well under the 5.5–6.0% comps
        "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                      "tiers": [{"hurdle": 0.12, "lp": 0.8, "gp": 0.2}, {"hurdle": None, "lp": 0.6, "gp": 0.4}]},
        "discount_rate": 0.10,
    }
    r = c.post(f"/projects/{pid}/proforma/solve", json=deal)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["returns"]["exit_cap"] == 0.045, body["returns"]
    assert any(f["metric"] == "exit_cap" for f in body["guardrails"]["flags"]), body["guardrails"]

    # U4 depth: specialty multi-year P&L endpoint (ramp + specialty IRR)
    pr = c.get(f"/projects/{pid}/specialty/proforma", params={"years": 8, "ramp_years": 3}).json()["proforma"]
    assert len(pr["rows"]) == 8 and pr["rows"][0]["op_year"] == 1 and pr["specialty_irr"] is not None, pr
    assert pr["rows"][0]["net"] < pr["stabilized_net_annual"], "ramp: year 1 below stabilized"
    # blended-IRR endpoint: solve the RE deal, fold in the saved specialty params, report the lift
    br = c.post(f"/projects/{pid}/specialty/blended", json=deal).json()["blended"]
    assert br["re_only_irr"] is not None and br["blended_irr"] is not None and br["irr_lift"] is not None, br

    # Monte-Carlo the specialty risk discount → distribution of blended IRR (endpoint)
    mcbody = {"assumptions": deal,
              "variables": [{"path": "risk_discount", "dist": {"kind": "triangular", "low": 0.2, "mode": 0.35, "high": 0.6}}],
              "iterations": 200, "targets": {"blended_irr": 0.15}}
    mr = c.post(f"/projects/{pid}/specialty/monte-carlo", json=mcbody).json()
    bm = mr["metrics"]["blended_irr"]
    assert bm["n"] == 200 and "prob_at_least" in bm and bm["p5"] <= bm["p95"], mr

print(f"SPECIALTY OK - energy {sp.starter()['energy']['solar_sf']:,} sf solar -> {e['solar_panels']:,} panels "
      f"${e['capex']:,} capex; PFAL {f['towers']:,} towers -> ${f['annual_revenue']:,}/yr; "
      f"net contribution ${s['annual_net_contribution']:,}/yr; deltas + persistence verified")
