"""EST-ASSEMBLIES — cost-item assemblies: unit-rate build-up from component resources (labour /
material / equipment), waste %, overrides, take-off extension, the starter library + endpoints.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_assemblies_cost.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_asm_cost.db"
os.environ["STORAGE_DIR"] = "./test_storage_asm_cost"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_asm_cost.db"):
    os.remove("./test_asm_cost.db")

from aec_api import assemblies_cost as ac  # noqa: E402

# --- build-up math: extended = qty × unit_cost × (1 + waste/100); rate = Σ; by-kind subtotals -------
comps = [
    {"resource": "Mason", "kind": "labour", "qty": 0.1, "unit": "hr", "unit_cost": 70.0},          # 7.00
    {"resource": "Block", "kind": "material", "qty": 1.0, "unit": "ea", "unit_cost": 2.0, "waste_pct": 10},  # 2.20
    {"resource": "Pump", "kind": "equipment", "qty": 0.5, "unit": "hr", "unit_cost": 4.0},          # 2.00
]
b = ac.build_up(comps)
assert b["by_kind"]["labour"] == 7.0 and b["by_kind"]["material"] == 2.2 and b["by_kind"]["equipment"] == 2.0, b
assert b["unit_rate"] == 11.2 and b["component_count"] == 3, b
assert b["lines"][1]["extended"] == 2.2, b["lines"][1]                     # waste applied

# an unknown kind buckets as material; a non-numeric qty is 0
odd = ac.build_up([{"resource": "X", "kind": "weird", "qty": "n/a", "unit_cost": 5}])
assert odd["by_kind"]["material"] == 0.0 and odd["unit_rate"] == 0.0, odd

# --- overrides re-cost by resource name (wage/price move) ------------------------------------------
o = ac.build_up(comps, overrides={"Mason": 80.0})                          # 0.1×80 = 8.00
assert o["by_kind"]["labour"] == 8.0 and o["unit_rate"] == 12.2, o

# --- price() extends the unit rate over a take-off quantity ----------------------------------------
p = ac.price(comps, 250)
assert p["unit_rate"] == 11.2 and p["quantity"] == 250.0 and p["total"] == 2800.0, p

# --- the starter library pre-computes each rate ---------------------------------------------------
lib = ac.library()
assert len(lib) >= 3 and all(a["unit_rate"] > 0 and a["unit"] for a in lib), lib
cmu = next(a for a in lib if a["id"] == "cmu-8-wall")
assert cmu["unit"] == "SF" and cmu["unit_rate"] == ac.build_up(ac.get("cmu-8-wall")["components"])["unit_rate"]

# --- endpoints ------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    la = c.get("/estimate/assemblies").json()
    assert any(a["id"] == "cip-slab-6" for a in la["assemblies"]), la

    # price a known assembly over a quantity
    r = c.post("/estimate/assembly/price", json={"assembly_id": "cmu-8-wall", "quantity": 100}).json()
    assert r["unit_rate"] == cmu["unit_rate"] and r["total"] == round(cmu["unit_rate"] * 100, 2), r
    assert r["by_kind"]["labour"] > 0, r

    # a custom component list + an override
    rc = c.post("/estimate/assembly/price", json={
        "components": comps, "quantity": 10, "overrides": {"Mason": 80.0}}).json()
    assert rc["unit_rate"] == 12.2 and rc["total"] == 122.0, rc

    # build-up only (no quantity) omits total
    bo = c.post("/estimate/assembly/price", json={"assembly_id": "cmu-8-wall"}).json()
    assert "total" not in bo and bo["unit_rate"] == cmu["unit_rate"], bo

    # errors: unknown id → 404; neither components nor id → 422
    assert c.post("/estimate/assembly/price", json={"assembly_id": "nope"}).status_code == 404
    assert c.post("/estimate/assembly/price", json={}).status_code == 422

print("EST-ASSEMBLIES OK - unit-rate build-up from labour/material/equipment components (extended = "
      "qty×cost×(1+waste); rate=Σ=11.20, by-kind subtotals; unknown kind→material, bad qty→0); "
      "overrides re-cost by resource name (Mason→80 ⇒ 12.20); price() extends over a take-off qty "
      "(250 SF ⇒ 2800); the starter library pre-computes each rate; endpoints list/price with "
      "assembly_id or a custom component list, build-up-only omits total, 404/422 on bad input.")
