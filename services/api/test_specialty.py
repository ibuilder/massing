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
assert d["other_income_annual_add"] == s["annual_revenue"] + s["annual_energy_offset"]

# disabled assets contribute nothing
none = sp.summarize({"energy_enabled": False, "pfal_enabled": False})
assert none["capex_total"] == 0 and none["annual_revenue"] == 0, none

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
