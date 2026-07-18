"""EST-1 productivity-rate library: man-hours/unit → labour hours + crew-days + cost, with loading factors;
plus a rough model-driven takeoff from element dimensions.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_productivity.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing, productivity  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- the catalog groups activities by trade + carries loading factors ------------------------------
cat = productivity.catalog()
assert "Concrete" in cat["groups"] and "MEP" in cat["groups"] and "Finishes" in cat["groups"], cat["groups"].keys()
assert cat["loading_factors"]["standard"] == 1.0 and cat["loading_factors"]["highrise"] > 1.0

# --- labor_estimate: hours = qty × mh × loading; cost = hours × rate -------------------------------
items = [{"activity": "block_masonry", "quantity": 100},   # 100 m² × 1.3 mh = 130 mh (standard)
         {"activity": "rc_casting", "quantity": 10}]        # 10 m³ × 10 mh = 100 mh
e = productivity.labor_estimate(items, hourly_rate=30.0, loading="standard")
assert e["loading_factor"] == 1.0 and e["line_count"] == 2, e
masonry = next(x for x in e["lines"] if x["activity"] == "block_masonry")
assert abs(masonry["man_hours"] - 130.0) < 0.1, masonry
assert abs(masonry["labor_cost"] - 130.0 * 30.0) < 0.1, masonry
assert masonry["crew_days"] > 0, masonry
assert abs(e["total_man_hours"] - 230.0) < 0.1 and abs(e["total_labor_cost"] - 230.0 * 30.0) < 0.1, e

# --- EST-1 schedule: crew-days roll up by trade → working/calendar days -----------------------------
sch = e["schedule"]
assert sch["by_group"] and sch["duration_working_days"] > 0, sch
# groups sequential → total working days == sum of per-group durations
assert abs(sch["duration_working_days"] - sum(g["duration_days"] for g in sch["by_group"])) < 0.1, sch
assert sch["duration_calendar_days"] >= sch["duration_working_days"], sch          # 7/5 calendar stretch
# 2 crews per trade halve each trade's duration → shorter overall
e2 = productivity.labor_estimate(items, hourly_rate=30.0, loading="standard", crews_parallel=2)
assert e2["schedule"]["duration_working_days"] < sch["duration_working_days"], (e2["schedule"], sch)
# highrise loading inflates the hours
eh = productivity.labor_estimate(items, hourly_rate=30.0, loading="highrise")
assert eh["total_man_hours"] > e["total_man_hours"], (eh["total_man_hours"], e["total_man_hours"])
# unknown activity + zero qty are skipped
assert productivity.labor_estimate([{"activity": "teleport", "quantity": 5},
                                    {"activity": "painting", "quantity": 0}])["line_count"] == 0

# --- full_estimate: labour + material + equipment ---------------------------------------------------
fe = productivity.full_estimate(items, hourly_rate=30.0, loading="standard")
assert fe["has_material_equipment"] is True, fe
# labour total is unchanged from labor_estimate; material + equipment are added on top
assert abs(fe["total_labor_cost"] - e["total_labor_cost"]) < 0.1, (fe["total_labor_cost"], e["total_labor_cost"])
# rc_casting: 10 m³ × $130/m³ material = $1,300; × $15/m³ equipment = $150
cast = next(x for x in fe["lines"] if x["activity"] == "rc_casting")
assert abs(cast["material_cost"] - 1300.0) < 0.1, cast
assert abs(cast["equipment_cost"] - 150.0) < 0.1, cast
assert abs(cast["line_total"] - (cast["labor_cost"] + 1300.0 + 150.0)) < 0.1, cast
# block_masonry: 100 m² × $30/m² material = $3,000; no equipment key → $0
mas2 = next(x for x in fe["lines"] if x["activity"] == "block_masonry")
assert abs(mas2["material_cost"] - 3000.0) < 0.1 and mas2["equipment_cost"] == 0.0, mas2
assert abs(fe["total_material_cost"] - (1300.0 + 3000.0)) < 0.1, fe["total_material_cost"]
assert abs(fe["total_equipment_cost"] - 150.0) < 0.1, fe["total_equipment_cost"]
assert abs(fe["total_cost"] - (fe["total_labor_cost"] + fe["total_material_cost"] + fe["total_equipment_cost"])) < 0.1, fe
# the catalog now carries material/equipment $/unit
conc = next(a for a in cat["groups"]["Concrete"] if a["activity"] == "rc_casting")
assert conc["material_cost_per_unit"] == 130.0 and conc["equipment_cost_per_unit"] == 15.0, conc

# --- model-driven takeoff: walls → masonry area, slab → concrete -----------------------------------
TMP = os.path.join(os.path.dirname(__file__), "_prod_test.ifc")
massing.generate_blank_ifc(TMP, name="Prod Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [0, 0], [10, 0], 3.0, 0.2, st)            # 10 m × 3 m = 30 m² masonry
edit.add_wall(m, [10, 0], [10, 5], 3.0, 0.2, st)           # 5 m × 3 m = 15 m² masonry
edit.add_slab(m, [[0, 0], [10, 0], [10, 5], [0, 5]], thickness=0.2, storey=st)

fm = productivity.from_model(m, hourly_rate=25.0, loading="commercial")
assert fm["derived_from_model"] and fm["total_man_hours"] > 0, fm
mas = next((x for x in fm["lines"] if x["activity"] == "block_masonry"), None)
assert mas is not None and mas["quantity"] > 40, mas   # ~45 m² of wall face, × commercial loading
assert any(x["activity"] == "rc_casting" for x in fm["lines"]), "slab → concrete casting"
# the model-driven estimate carries the schedule duration too
assert fm["schedule"]["duration_working_days"] > 0 and fm["schedule"]["by_group"], fm["schedule"]
# full model estimate adds material + equipment on top of the same labour
fmf = productivity.from_model(m, hourly_rate=25.0, loading="commercial", full=True)
assert fmf["has_material_equipment"] and fmf["total_cost"] > fmf["total_labor_cost"], fmf
assert fmf["total_material_cost"] > 0 and abs(fmf["total_labor_cost"] - fm["total_labor_cost"]) < 0.1, fmf

# --- EST-1: from_takeoff — the estimate driven by REAL measured QTO rows ---------------------------
QTO_ROWS = [
    {"ifc_class": "IfcWall", "area": 30.0, "volume": 6.0},           # wall face → masonry m²
    {"ifc_class": "IfcWallStandardCase", "area": 15.0},
    {"ifc_class": "IfcSlab", "area": 50.0, "volume": 10.0},          # slab → casting m³ + finish m²
    {"ifc_class": "IfcColumn", "volume": 1.2},                       # concrete column → casting
    {"ifc_class": "IfcBeam", "weight": 500.0},                       # steel beam (kg) → erection tons
    {"ifc_class": "IfcCovering", "name": "Ceiling ACT", "area": 20.0},
    {"ifc_class": "IfcCovering", "name": "Floor Tile", "area": 25.0},
    {"ifc_class": "IfcPipeSegment", "length": 12.0},
    {"ifc_class": "IfcDuctSegment", "length": 8.0},
    {"ifc_class": "IfcDoor", "area": 2.0},                           # unmapped class → skipped
]
ft = productivity.from_takeoff(QTO_ROWS, hourly_rate=30.0, loading="standard")
assert ft["derived_from_takeoff"] is True and ft["elements_counted"] == 9, ft["elements_counted"]
by_act = {x["activity"]: x for x in ft["lines"]}
assert abs(by_act["block_masonry"]["quantity"] - 45.0) < 0.1, by_act["block_masonry"]   # 30 + 15 m²
assert abs(by_act["rc_casting"]["quantity"] - 11.2) < 0.1, by_act["rc_casting"]         # 10 + 1.2 m³
assert abs(by_act["concrete_finish"]["quantity"] - 50.0) < 0.1, by_act
assert abs(by_act["steel_erection"]["quantity"] - 0.5) < 0.01, by_act["steel_erection"] # 500 kg → 0.5 t
assert abs(by_act["false_ceiling"]["quantity"] - 20.0) < 0.1 and abs(by_act["floor_tile"]["quantity"] - 25.0) < 0.1
assert abs(by_act["pipe_install"]["quantity"] - 12.0) < 0.1 and abs(by_act["duct_install"]["quantity"] - 8.0) < 0.1
assert ft["schedule"]["duration_working_days"] > 0 and ft["schedule"]["by_group"], ft["schedule"]

# --- EST-1 CPM half: POST /schedule/from-estimate writes crew-day durations as EST activities -------
m.write(TMP)                       # persist the walls+slab so the uploaded source IFC carries them
os.environ["DATABASE_URL"] = "sqlite:///./test_productivity.db"
os.environ["STORAGE_DIR"] = "./test_storage_prod"
os.environ["IFC_DIR"] = "./_ifc_prod"     # writable; the default /app/ifc is read-only in CI
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_productivity.db"):
    os.remove("./test_productivity.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

HDR = {"X-User": "scheduler"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "EST-1"}, headers=HDR).json()["id"]
    # no source IFC yet → 409
    assert c.post(f"/projects/{pid}/schedule/from-estimate", json={}, headers=HDR).status_code == 409
    with open(TMP, "rb") as fh:
        up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                    files={"file": ("est.ifc", fh, "application/octet-stream")}, headers=HDR)
    assert up.status_code == 200, up.text[:200]
    r = c.post(f"/projects/{pid}/schedule/from-estimate", json={"loading": "standard"}, headers=HDR)
    assert r.status_code == 200, r.text[:300]
    b = r.json()
    assert b["activities"] >= 2 and b["cpm_project_duration"] > 0, b            # Masonry + Concrete
    assert all(w["duration_days"] >= 1 for w in b["written"]), b["written"]
    # sequential chain: every activity after the first carries a predecessor
    refs = [w["ref"] for w in b["written"]]
    # re-run → UPSERT: same activity count, all rows marked updated (no duplicates)
    r2 = c.post(f"/projects/{pid}/schedule/from-estimate", json={"loading": "standard"}, headers=HDR).json()
    assert r2["activities"] == b["activities"] and all(w["updated"] for w in r2["written"]), r2
    assert [w["ref"] for w in r2["written"]] == refs, "refs stable across re-runs"
    # CPM sees the chain: project duration ≈ sum of the EST durations (sequential FS)
    cpm = c.get(f"/projects/{pid}/schedule/cpm", headers=HDR).json()
    assert cpm["project_duration"] >= sum(w["duration_days"] for w in b["written"]), cpm["project_duration"]
    # the QTO-driven GET estimate works too
    le = c.get(f"/projects/{pid}/estimate/labor?loading=standard", headers=HDR).json()
    assert le.get("derived_from_takeoff") is True and le["total_labor_cost"] > 0, le.get("note")
    # PROFORMA-LIVE: the model's takeoff-priced cost + slab GFA, refreshed per version
    pl = c.get(f"/projects/{pid}/proforma/live", headers=HDR)
    assert pl.status_code == 200, pl.text[:200]
    plb = pl.json()
    assert plb["est_construction_cost"] > 0 and plb["gfa_m2"] > 0, plb
    assert plb["cost_per_m2"] and plb["model_version"], plb

if os.path.exists(TMP):
    os.remove(TMP)

print("PRODUCTIVITY OK - the rate catalog groups activities by trade w/ loading factors; labor_estimate "
      "computes man-hours (qty×mh×loading) + crew-days + cost (100 m² masonry → 130 mh → $3,900 at $30/hr), "
      "highrise loading inflates hours, unknown/zero lines skipped; from_model derives a rough takeoff "
      "(2 walls → ~45 m² masonry, slab → concrete casting) straight from element dimensions.")
