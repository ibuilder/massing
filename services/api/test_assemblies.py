"""Resource-based (assembly) estimating — build-up math, L/M/E split, crew-hours, model takeoff.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_assemblies.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_assemblies.db"
os.environ["STORAGE_DIR"] = "./test_storage_assemblies"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_assemblies.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import assemblies as asm  # noqa: E402

# --- price_assembly: a CIP wall built up from L/M/E ---
wall = asm.DEFAULT_ASSEMBLIES["cip_wall"]
p = asm.price_assembly(wall, 10.0)      # 10 m3 of wall
# hand-check a couple of components
conc = next(x for x in p["lines"] if x["resource"] == "mat_concrete")
assert conc["quantity"] == round(1.02 * 10, 2) and conc["amount"] == round(1.02 * 10 * 175.0, 2), conc
mason = next(x for x in p["lines"] if x["resource"] == "lab_cementmason")
assert mason["quantity"] == round(3.5 * 10, 2), mason
# by_kind split must sum to the total and all three kinds present + positive
assert set(p["by_kind"]) == {"labor", "material", "equipment"}, p["by_kind"]
assert all(v > 0 for v in p["by_kind"].values()), p["by_kind"]
assert round(sum(p["by_kind"].values()), 2) == p["total"], p
# labor-hours = only the hr-unit labor resources (cementmason 3.5 + laborer 2.5 + carpenter 2.0) * 10
assert p["labor_hours"] == round((3.5 + 2.5 + 2.0) * 10, 2), p["labor_hours"]
assert p["unit_cost"] == round(p["total"] / 10, 2)
print(f"cip_wall 10m3: total ${p['total']:,.0f}  L/M/E {p['by_kind']}  {p['labor_hours']} hr")

# --- resource override changes only the targeted resource ---
base = asm.price_assembly(wall, 1.0)["total"]
over = asm.price_assembly(wall, 1.0, resources={"mat_concrete": {"kind": "material", "unit": "m3", "rate": 275.0, "name": "x"}})["total"]
assert round(over - base, 2) == round((275.0 - 175.0) * 1.02, 2), (base, over)

# --- quantity 0 is safe (no divide-by-zero) ---
z = asm.price_assembly(wall, 0.0)
assert z["total"] == 0.0 and z["unit_cost"] == 0.0, z

# --- catalog: every assembly prices to a positive built-up unit cost ---
cat = asm.catalog()
assert cat["resources"] and cat["assemblies"] and cat["class_map"], cat.keys()
for a in cat["assemblies"]:
    assert a["unit_cost"] > 0, a
    assert round(sum(a["by_kind"].values()), 2) == a["unit_cost"], a   # 1-unit build-up == unit cost

# --- estimate_resource_based over a synthetic takeoff ---
rows = [
    {"ifc_class": "IfcSlab", "volume": 4.0}, {"ifc_class": "IfcSlab", "volume": 6.0},   # 10 m3 slab
    {"ifc_class": "IfcColumn", "volume": 2.0},                                          # 2 m3 column
    {"ifc_class": "IfcBeam", "volume": 0.5},                                            # steel by kg proxy
    {"ifc_class": "IfcWall", "area": 50.0},                                             # 50 m2 partition
    {"ifc_class": "IfcDoor"}, {"ifc_class": "IfcDoor"},                                 # 2 doors (count)
    {"ifc_class": "IfcSpace", "area": 999.0},                                           # unmapped
]
est = asm.estimate_resource_based(rows)
assert est["source"] == "resource" and est["total"] > 0, est
# unmapped surfaces the class with no assembly, not a silent drop
assert any(u["ifc_class"] == "IfcSpace" for u in est["unmapped"]), est["unmapped"]
# the slab line: 10 m3 priced via cip_slab
slab = next(x for x in est["lines"] if x["ifc_class"] == "IfcSlab")
assert slab["assembly"] == "cip_slab" and slab["quantity"] == 10.0, slab
# doors priced by count (2 ea)
door = next(x for x in est["lines"] if x["ifc_class"] == "IfcDoor")
assert door["quantity"] == 2.0 and door["count"] == 2, door
# steel beam converted volume->kg (0.5 m3 * 7850)
beam = next(x for x in est["lines"] if x["ifc_class"] == "IfcBeam")
assert beam["assembly"] == "steel_beam" and beam["quantity"] == round(0.5 * 7850.0, 2), beam
# project rollup: L/M/E sums to total, and crew-hours are aggregated + positive
assert round(sum(est["by_kind"].values()), 2) == est["total"], est
assert est["labor_hours"] > 0, est
# by_trade: labor rolled up per trade, sorted by hours, and hours reconcile to the total labor-hours
assert est["by_trade"] and est["by_trade"][0]["hours"] >= est["by_trade"][-1]["hours"], est["by_trade"]
assert round(sum(t["hours"] for t in est["by_trade"]), 0) == round(est["labor_hours"], 0), est["by_trade"]
# duration_weeks implies an average crew size per trade
dem = asm.labor_demand(est["lines"], duration_weeks=10.0)
assert all("avg_crew" in t and t["avg_crew"] >= 0 for t in dem), dem
_trades = ", ".join("{} {:.0f}hr".format(t["name"], t["hours"]) for t in est["by_trade"][:4])
print("labor demand: " + _trades)
print(f"model estimate: total ${est['total']:,.0f}  L/M/E {est['by_kind']}  {est['labor_hours']:,.0f} crew-hr  "
      f"{len(est['lines'])} lines, {len(est['unmapped'])} unmapped")

# --- endpoint smoke: catalog is reachable ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

c = TestClient(app)
rc = c.get("/estimate/resources/catalog")
assert rc.status_code == 200 and rc.json()["assemblies"], rc.status_code

print("test_assemblies OK")
