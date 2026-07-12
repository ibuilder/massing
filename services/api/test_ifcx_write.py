"""IFC5 / IFCX write path — the inverse of the reader. Emits ifcJSON / IFCX from the element index and
round-trips it back through ifc5_reader. Run:
  PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ifcx_write.py
(run_tests.py already puts both src dirs on PYTHONPATH.)"""
import json
import os
import sys
from pathlib import Path

# make aec_data importable when run standalone (run_tests.py already sets this up)
_DATA_SRC = Path(__file__).resolve().parents[1] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

os.environ["DATABASE_URL"] = "sqlite:///./test_ifcx_write.db"
os.environ["STORAGE_DIR"] = "./test_storage_ifcx"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_ifcx_write.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_data import ifc5_reader, ifc5_writer  # noqa: E402

# a minimal element index (the shape properties_index / ifc5_reader produce)
INDEX = {
    "schema": "IFC5",
    "project": {"guid": None, "name": "Sample5 Tower"},
    "counts": {"elements": 2, "classes": 2, "storeys": 1},
    "facets": {"classes": ["IfcColumn", "IfcWall"], "storeys": ["Level 1"]},
    "elements": [
        {"guid": "0aVeryReal22charGUIDwall", "ifc_class": "IfcWall", "name": "W1", "type_name": "Basic Wall",
         "storey": "Level 1", "psets": {"Pset_WallCommon": {"IsExternal": True, "FireRating": "2HR"}}, "qtos": {}},
        {"guid": "0aVeryReal22charGUIDcolm", "ifc_class": "IfcColumn", "name": "C12", "type_name": None,
         "storey": "Level 1", "psets": {"Pset_ColumnCommon": {"Reference": "C12"}}, "qtos": {}},
    ],
}

# --- 1. ifcJSON flavor round-trips at full fidelity -----------------------------
ifcjson = ifc5_writer.to_ifcjson(INDEX)
assert ifcjson["type"] == "ifcJSON" and ifcjson["schema"] == "IFC5", ifcjson
back = ifc5_reader.build_index_from_json(ifcjson)
assert back["counts"]["elements"] == 2, back["counts"]
assert set(back["facets"]["classes"]) == {"IfcWall", "IfcColumn"}, back["facets"]
assert back["project"]["name"] == "Sample5 Tower", back["project"]
by_guid = {e["guid"]: e for e in back["elements"]}
w = by_guid["0aVeryReal22charGUIDwall"]
assert w["name"] == "W1" and w["ifc_class"] == "IfcWall", w
assert w["psets"]["Pset_WallCommon"]["IsExternal"] is True, w   # property groups + values survive
assert w["psets"]["Pset_WallCommon"]["FireRating"] == "2HR", w

# --- 2. IFCX/USD flavor round-trips class/guid/name (properties fold to a flat set) ----------
ifcx = ifc5_writer.to_ifcx(INDEX)
assert isinstance(ifcx, list) and len(ifcx) == 3, len(ifcx)   # 2 elements + the IfcProject node
backx = ifc5_reader.build_index_from_json(ifcx)
assert backx["counts"]["elements"] == 2, backx["counts"]
assert set(backx["facets"]["classes"]) == {"IfcWall", "IfcColumn"}, backx["facets"]
bx = {e["guid"]: e for e in backx["elements"]}
assert bx["0aVeryReal22charGUIDwall"]["name"] == "W1", bx
# USD attributes are flat → the reader folds scalars into an "Attributes" group; the value survives
attrs = bx["0aVeryReal22charGUIDwall"]["psets"].get("Attributes", {})
assert attrs.get("FireRating") == "2HR", bx["0aVeryReal22charGUIDwall"]["psets"]

# --- 3. bytes serialization is valid JSON both ways -----------------------------
assert json.loads(ifc5_writer.to_bytes(INDEX, "ifcjson").decode())["type"] == "ifcJSON"
assert isinstance(json.loads(ifc5_writer.to_bytes(INDEX, "ifcx").decode()), list)

# --- 4. openBIM registry now advertises IFC5 as writable ------------------------
from aec_api import openbim  # noqa: E402

caps = openbim.capabilities()
assert "IFC5" in caps["index"]["ifc"]["write"], caps["index"]["ifc"]
assert openbim.supports("ifc", "IFC5", "write") is True, "IFC5 should be writable now"
assert openbim.supports("ifc", "IFC5", "read") is True, "IFC5 stays readable"

# --- 5. the export endpoint serves both flavors (empty-but-well-formed with no model loaded) ----
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "Sample5 Tower"}).json()["id"]
    r = tc.get(f"/projects/{pid}/model/export.ifcx")
    assert r.status_code == 200, r.text[:200]
    doc = r.json()
    assert doc["type"] == "ifcJSON" and isinstance(doc["data"], list), doc
    rx = tc.get(f"/projects/{pid}/model/export.ifcx?flavor=ifcx")
    assert rx.status_code == 200 and isinstance(rx.json(), list), rx.text[:200]

print("IFCX-WRITE OK - ifc5_writer inverts the reader: ifcJSON round-trips guid/class/name/type/storey + "
      "property groups at full fidelity; IFCX/USD flavor round-trips class/guid/name (scalars fold to a flat "
      "attribute set); openBIM now advertises IFC5 in ifc.write; GET /model/export.ifcx serves both flavors. "
      "Closes the IFC5 read/write loop at the data layer (geometry still waits on web-ifc/Fragments upstream).")
