"""MEP-EQUIP — the procurement equipment schedule derived from the IFC: procurable MEP units grouped by
(class, type) into RFQ line-items with a quantity + representative spec, ducts/pipes/fittings excluded.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_equipment.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_equip.ifc")

import ifcopenshell  # noqa: E402

from aec_api import equipment as eq  # noqa: E402
from aec_data import edit_mep, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a blank model + two air terminals (same class → one RFQ line, qty 2) + a pump + a duct (EXCLUDED)
massing.generate_blank_ifc(TMP, name="Equip", storeys=1, storey_height=3.5, ground_size=20.0)
m = ifcopenshell.open(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit_mep.add_mep_terminal(m, "IfcAirTerminal", [1, 1], storey=st)
edit_mep.add_mep_terminal(m, "IfcAirTerminal", [2, 2], storey=st)
edit_mep.add_mep_run(m, "IfcDuctSegment", [0, 0], [5, 0], "round", 0.3, st)     # IfcFlowSegment → EXCLUDED
m.create_entity("IfcPump", GlobalId=ifcopenshell.guid.new(), Name="CHW Pump 1")   # equipment
m.write(TMP)

# --- SPEC-CONFLICT: pure comparison over fabricated schedule lines (no model needed) ----------------
_lines = [
    {"ifc_class": "IfcChiller", "type": "CH-1", "count": 2, "spec": {"CondenserType": "AirCooled"}},
    {"ifc_class": "IfcPump", "type": "P-1", "count": 1, "spec": {"Model": "CHW-2000"}},
    {"ifc_class": "IfcAirTerminal", "type": "AT-1", "count": 4, "spec": {}},          # no spec value
]
sc = eq.spec_conflicts(_lines, {
    "IfcChiller": {"CondenserType": "WaterCooled"},       # spec says water-cooled, model says air → CONFLICT
    "IfcPump": {"Model": "chw-2000"},                      # matches case-insensitively → NO conflict
    "IfcAirTerminal": {"FlowRate": 250},                   # specified but not modelled → MISSING
})
assert sc["conflict_count"] == 1 and sc["conflicts"][0]["ifc_class"] == "IfcChiller", sc
assert sc["conflicts"][0]["expected"] == "WaterCooled" and sc["conflicts"][0]["actual"] == "AirCooled", sc
assert sc["units_in_conflict"] == 2, sc                    # the conflicting chiller line has 2 units
assert sc["missing_count"] == 1 and sc["missing"][0]["ifc_class"] == "IfcAirTerminal", sc
# a class with no requirement is never flagged
assert eq.spec_conflicts(_lines, {})["conflict_count"] == 0

res = eq.schedule(open_model(TMP))
by_class = {r["ifc_class"]: r for r in res["lines"]}
# two air terminals of the same (class, type) collapse into ONE line with count 2
assert "IfcAirTerminal" in by_class and by_class["IfcAirTerminal"]["count"] == 2, res["lines"]
# the pump is its own line; the duct is NOT scheduled (installed material, not a unit)
assert "IfcPump" in by_class and by_class["IfcPump"]["count"] == 1, res["lines"]
assert "IfcDuctSegment" not in by_class, by_class
assert res["unit_count"] == 3 and res["line_count"] == 2, res          # 2 terminals + 1 pump; 2 lines
# each line carries a discipline + the guids of its units; lines sort by descending count
assert all(r["discipline"] and r["guids"] for r in res["lines"]), res["lines"]
assert [r["count"] for r in res["lines"]] == sorted([r["count"] for r in res["lines"]], reverse=True), res["lines"]

# --- route: GET the schedule; 409 without a model ---------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_equipment.db"
os.environ["STORAGE_DIR"] = "./test_storage_equip"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_equipment.db"):
    os.remove("./test_equipment.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RFQ"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/equipment").status_code == 409       # no source IFC yet
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/model/equipment")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["unit_count"] == 3 and j["line_count"] == 2, j
    # SPEC-CONFLICT route: require the pump to be a model the schedule doesn't carry → reported missing;
    # an empty requirement set yields zero conflicts
    sr = c.post(f"/projects/{pid}/model/equipment/spec-check",
                json={"requirements": {"IfcPump": {"Model": "P-9999"}}})
    assert sr.status_code == 200, sr.text
    sj = sr.json()
    assert sj["conflict_count"] + sj["missing_count"] >= 1 and sj["line_count"] == 2, sj
    assert c.post(f"/projects/{pid}/model/equipment/spec-check", json={"requirements": {}}).json()["conflict_count"] == 0

if os.path.exists(TMP):
    os.remove(TMP)

print("MEP-EQUIP OK - the procurement equipment schedule derives from the IFC: two air terminals of the "
      "same class+type collapse into ONE RFQ line-item (qty 2) and a pump forms its own line, each carrying "
      "a discipline + the unit GUIDs + a representative spec, while the duct segment is correctly EXCLUDED "
      "(installed material, not a scheduled unit); lines sort by descending quantity; the /model/equipment "
      "route 409s without a model and returns 3 units across 2 lines with one.")
