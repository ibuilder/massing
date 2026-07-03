"""Embodied-carbon estimator — EPD factors x quantities with unit conversion + rollups.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_carbon.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_carbon.db"
os.environ["STORAGE_DIR"] = "./test_storage_carbon"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_carbon.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import carbon                            # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- engine ---
# 100 m3 concrete @ 300 = 30,000 kg
r = carbon.compute_item("Cast-in-place concrete", 100, "m3")
assert r["kgco2e"] == 30000.0 and r["matched"] == "concrete", r
# 10 CY concrete -> 10*0.764555*300 = 2293.7 kg (unit conversion CY->m3)
r2 = carbon.compute_item("concrete footing", 10, "CY")
assert abs(r2["kgco2e"] - 2293.7) < 0.5, r2
# steel by tons -> kg conversion: 5 tons * 907.185 * 1.55
r3 = carbon.compute_item("structural steel", 5, "tons")
assert abs(r3["kgco2e"] - 5 * 907.185 * 1.55) < 1, r3
# unmatched material -> no factor, no guess
assert carbon.compute_item("unobtainium widget", 5, "ea")["kgco2e"] is None
# wrong unit family for the factor (concrete is volume) -> flagged, not computed
assert carbon.compute_item("concrete", 100, "kg")["kgco2e"] is None

agg = carbon.compute([
    {"description": "concrete slab", "quantity": 100, "unit": "m3", "cost_code": "03-3000"},
    {"description": "rebar", "quantity": 5000, "unit": "kg", "cost_code": "03-2000"},
    {"description": "mystery", "quantity": 1, "unit": "ea"},
])
assert agg["unmatched"] == 1, agg
assert agg["by_material"]["concrete"] == 30000.0, agg["by_material"]
assert agg["by_cost_code"]["03-3000"] == 30000.0, agg["by_cost_code"]
assert agg["total_kgco2e"] == 30000.0 + 5000 * 1.99, agg
assert agg["total_tco2e"] == round(agg["total_kgco2e"] / 1000, 2)

# --- endpoint from production_quantity records ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    c.post(f"/projects/{pid}/modules/production_quantity",
           json={"data": {"description": "Concrete slab on grade", "quantity": 200, "unit": "m3", "cost_code": "03-3000"}})
    j = c.get(f"/projects/{pid}/carbon").json()
    assert j["total_kgco2e"] == 60000.0 and j["by_material"]["concrete"] == 60000.0, j
    assert j["total_tco2e"] == 60.0, j

print("CARBON OK - EPD factors x quantities with CY/ton unit conversion; unmatched + wrong-unit-family "
      "flagged (no guessing); rollups by material + cost code; endpoint from production_quantity = 60 tCO2e")
