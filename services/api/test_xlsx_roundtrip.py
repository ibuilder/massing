"""XLSX-ROUNDTRIP — GUID-keyed property export → edit → dry-run diff → batch apply.
Engine half: the set_props_by_guid recipe applies a mixed batch in one pass (bad rows skipped).
Endpoint half: roundtrip.csv export (formula-injection guarded) + /roundtrip/diff (dtype inferred
from the OLD value so numerics don't flip to strings; unknown GUIDs reported; blanks ignored).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_xlsx_roundtrip.py"""
import json
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_xlsx_roundtrip.db"
os.environ["STORAGE_DIR"] = "./test_storage_xlsx_roundtrip"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_xlsx_roundtrip.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.api  # noqa: E402
import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_xlsxrt.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_xlsxrt_out.ifc")

# --- engine: the batch recipe -------------------------------------------------
m = ifcopenshell.api.run("project.create_file")
proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
ifcopenshell.api.run("context.add_context", m, context_type="Model")
c1 = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcColumn", name="C1")
c2 = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcColumn", name="C2")
m.write(TMP)

applied = edit.apply_recipe(TMP, "set_props_by_guid", {"changes": [
    {"guid": c1.GlobalId, "pset": "Pset_Custom", "prop": "FireRating", "new": "2HR"},
    {"guid": c2.GlobalId, "pset": "Pset_Custom", "prop": "LoadRating", "new": "1500", "dtype": "float"},
    {"guid": "0badGuid0000000000000x", "pset": "P", "prop": "X", "new": "y"},   # skipped, never aborts
]}, OUT)
m2 = open_model(OUT)
assert ue.get_pset(m2.by_guid(c1.GlobalId), "Pset_Custom", "FireRating") == "2HR"
assert ue.get_pset(m2.by_guid(c2.GlobalId), "Pset_Custom", "LoadRating") == 1500.0, "dtype float honored"

# --- endpoints: export + dry-run diff ----------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

IDX = {"elements": [
    {"guid": "GUID000000000000000001", "ifc_class": "IfcWall", "name": "Wall A",
     "psets": {"Pset_WallCommon": {"FireRating": "1HR", "Width": 0.2}}},
    {"guid": "GUID000000000000000002", "ifc_class": "IfcWall", "name": "=SUM(A1)",   # injection bait
     "psets": {"Pset_WallCommon": {"FireRating": "2HR"}}},
]}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RT"}).json()["id"]
    up = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", json.dumps(IDX), "application/json")})
    assert up.status_code == 200 and up.json()["loaded"] == 2, up.text

    # export: guid + requested prop columns; the formula-lead name is guarded with a quote
    csv_out = c.get(f"/projects/{pid}/model/roundtrip.csv?props=Pset_WallCommon.FireRating,Pset_WallCommon.Width")
    assert csv_out.status_code == 200, csv_out.text
    assert "guid,ifc_class,name,Pset_WallCommon.FireRating,Pset_WallCommon.Width" in csv_out.text
    assert "'=SUM(A1)" in csv_out.text, "CSV formula-injection guard"
    assert c.get(f"/projects/{pid}/model/roundtrip.csv?props=").status_code == 422

    # edit the CSV: change one rating, change the numeric width, add an unknown guid, leave one blank
    edited = ("guid,ifc_class,name,Pset_WallCommon.FireRating,Pset_WallCommon.Width\n"
              "GUID000000000000000001,IfcWall,Wall A,2HR,0.25\n"
              "GUID000000000000000002,IfcWall,'=SUM(A1),2HR,\n"          # unchanged (guard stripped)
              "GUIDunknown00000000000,IfcWall,X,1HR,\n")
    d = c.post(f"/projects/{pid}/model/roundtrip/diff",
               files={"file": ("edited.csv", edited, "text/csv")}).json()
    assert d["checked"] == 3 and d["unknown_guids"] == ["GUIDunknown00000000000"], d
    assert len(d["changes"]) == 2, d["changes"]
    fr = next(x for x in d["changes"] if x["prop"] == "FireRating")
    assert fr == {"guid": "GUID000000000000000001", "pset": "Pset_WallCommon", "prop": "FireRating",
                  "old": "1HR", "new": "2HR", "dtype": "str"}, fr
    wd = next(x for x in d["changes"] if x["prop"] == "Width")
    assert wd["dtype"] == "float" and wd["new"] == "0.25", "dtype inferred from the OLD value's type"
    assert d["unchanged"] >= 1, d                       # the guarded name row's rating didn't change

    # header without a guid column → 422
    bad = c.post(f"/projects/{pid}/model/roundtrip/diff",
                 files={"file": ("x.csv", "a,b\n1,2\n", "text/csv")})
    assert bad.status_code == 422, bad.text

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("XLSX-ROUNDTRIP OK - set_props_by_guid batch (str + float dtype, bad row skipped) verified in "
      "the IFC; roundtrip.csv exports guarded GUID-keyed columns; dry-run diff finds 2 changes with "
      "dtype inferred from old values, reports unknown GUIDs, ignores blanks; 422 on bad header")
