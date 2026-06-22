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

# --- U5: underwriting guardrails flag implausible returns ----------------------------
from aec_api import underwrite  # noqa: E402
hot = underwrite.guardrails({"returns": {"equity_irr": 0.71, "equity_multiple": 23.0, "dev_spread": 600}})
assert not hot["ok"] and any(f["metric"] == "equity_irr" and f["level"] == "high" for f in hot["flags"]), hot
sane = underwrite.guardrails({"returns": {"equity_irr": 0.16, "equity_multiple": 2.1, "dev_spread": 180}})
assert sane["ok"] and any(f["metric"] == "ok" for f in sane["flags"]), sane
thin = underwrite.guardrails({"returns": {"equity_irr": 0.10, "equity_multiple": 1.6, "dev_spread": -20}})
assert any(f["metric"] == "dev_spread" and f["level"] == "high" for f in thin["flags"]), thin

# --- persistence round-trip --------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Vert Farm"}).json()["id"]
    g0 = c.get(f"/projects/{pid}/specialty").json()
    assert g0["summary"]["capex_total"] > 0 and "deltas" in g0, g0     # starter served
    r = c.put(f"/projects/{pid}/specialty", json=params)
    assert r.status_code == 200 and r.json()["summary"]["capex_total"] == s["capex_total"], r.text
    assert c.get(f"/projects/{pid}/specialty").json()["summary"]["capex_total"] == s["capex_total"]

print(f"SPECIALTY OK - energy {sp.starter()['energy']['solar_sf']:,} sf solar -> {e['solar_panels']:,} panels "
      f"${e['capex']:,} capex; PFAL {f['towers']:,} towers -> ${f['annual_revenue']:,}/yr; "
      f"net contribution ${s['annual_net_contribution']:,}/yr; deltas + persistence verified")
