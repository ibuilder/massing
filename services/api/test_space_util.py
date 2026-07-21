"""SPACE-UTIL — occupancy capacity per IfcSpace at an area-per-person standard + a headcount supply/demand
gap. The computation is pure over a plain space list (tested directly); the routes pull spaces off the IFC.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_space_util.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_space_util.db"
os.environ["STORAGE_DIR"] = "./test_storage_su"
os.environ.pop("AEC_RBAC", None)

from aec_api import space_util as su  # noqa: E402

# --- utilization: capacity = floor(area / area_per_person), rolled up by type ----------------------
SPACES = [
    {"guid": "g1", "name": "Open office A", "type": "Office", "area": 200.0},
    {"guid": "g2", "name": "Open office B", "type": "Office", "area": 105.0},
    {"guid": "g3", "name": "Meeting 1", "type": "Meeting", "area": 30.0},
    {"guid": "g4", "name": "Closet", "type": "Storage", "area": 0.0},        # no area → 0 capacity
]
u = su.utilization(SPACES, area_per_person=10.0)
assert u["space_count"] == 4 and u["total_area_m2"] == 335.0, u
# 200/10 + 105/10(=10, floor) + 30/10 + 0 = 20 + 10 + 3 + 0 = 33
assert u["capacity_total"] == 33, u
by = {r["type"]: r for r in u["by_type"]}
assert by["Office"]["count"] == 2 and by["Office"]["capacity"] == 30 and by["Office"]["area_m2"] == 305.0, by
assert by["Storage"]["capacity"] == 0, by
# spaces sort by descending area; by_type sorts by descending area (Office first)
assert u["spaces"][0]["guid"] == "g1" and u["by_type"][0]["type"] == "Office", u
# a different standard changes capacity (15 m²/person → floor(200/15)=13 + floor(105/15)=7 + floor(30/15)=2 = 22)
assert su.utilization(SPACES, area_per_person=15.0)["capacity_total"] == 22, "app changes capacity"
# a zero/invalid standard falls back to the default (does not divide-by-zero)
assert su.utilization(SPACES, area_per_person=0)["area_per_person"] == 10.0, "bad app falls back"

# --- demand: headcount program vs modelled supply → gap per type -----------------------------------
d = su.demand(SPACES, {"Office": 40, "Meeting": 5}, area_per_person=10.0)
byt = {r["type"]: r for r in d["by_type"]}
# Office: need 40×10=400, have 305 → deficit −95; Meeting: need 50, have 30 → deficit −20
assert byt["Office"]["required_m2"] == 400.0 and byt["Office"]["gap_m2"] == -95.0 and byt["Office"]["status"] == "deficit", byt
assert byt["Meeting"]["gap_m2"] == -20.0, byt
assert d["deficit_types"] == 2 and d["total_gap_m2"] == -115.0, d
# worst deficit sorts first
assert d["by_type"][0]["type"] == "Office", d["by_type"]
# a program that fits shows no deficit
ok = su.demand(SPACES, {"Office": 10}, area_per_person=10.0)              # need 100, have 305 → surplus
assert ok["deficit_types"] == 0 and ok["by_type"][0]["gap_m2"] == 205.0, ok

# --- route: 409 without a model; 200 + valid structure with one -----------------------------------
import ifcopenshell  # noqa: E402

from aec_data import edit, massing  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_su.ifc")
massing.generate_blank_ifc(TMP, name="SU", storeys=1, storey_height=3.5, ground_size=20.0)
m = ifcopenshell.open(TMP)
edit.add_spaces(m, rooms_per_storey=3, ceiling_height=3.0)               # give it some IfcSpaces
m.write(TMP)

if os.path.exists("./test_space_util.db"):
    os.remove("./test_space_util.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Space"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/space-utilization").status_code == 409       # no model yet
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/model/space-utilization?area_per_person=12")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["area_per_person"] == 12.0 and j["space_count"] >= 3 and "by_type" in j, j
    # demand route: post a headcount program → a gap plan
    dr = c.post(f"/projects/{pid}/model/space-demand",
                json={"program": {"Room": 50}, "area_per_person": 12})
    assert dr.status_code == 200 and "total_gap_m2" in dr.json(), dr.text

if os.path.exists(TMP):
    os.remove(TMP)

print("SPACE-UTIL OK - occupancy capacity per IfcSpace at an area-per-person standard rolls up by type "
      "(200+105 m² Office → 30 seats at 10 m²/person; a 0-area space → 0; a different standard changes the "
      "count; a bad standard falls back to the default), and a headcount program compares against the "
      "modelled inventory into a required-vs-supplied gap per type worst-deficit-first (Office needs 400 has "
      "305 → −95 deficit); the /model/space-utilization route 409s without a model and the /space-demand "
      "route returns a gap plan.")
