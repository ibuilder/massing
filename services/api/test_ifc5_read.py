"""IFC5 / IFCX / ifcJSON data read path: parse JSON models into the element-index shape so the data
layer (analytics, audits, exports) works on IFC5 before geometry can be rendered.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ifc5_read.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

from aec_data import ifc5_reader  # noqa: E402
from aec_data.properties_index import _is_json_model, index_file  # noqa: E402

# --- ifcJSON shape: {"data": [ {type, globalId, name}, … ]} ---------------------------------------
ifcjson = {"type": "ifcJSON", "schema": "IFC5", "data": [
    {"type": "IfcProject", "globalId": "P0", "name": "Sample5"},
    {"type": "IfcBuildingStorey", "globalId": "S1", "name": "L1"},         # spatial -> excluded
    {"type": "IfcWall", "globalId": "W1", "name": "Wall-1",
     "properties": {"Pset_WallCommon": {"IsExternal": True}}},
    {"type": "IfcWall", "globalId": "W2", "name": "Wall-2"},
    {"type": "IfcDoor", "globalId": "D1", "name": "Door-1"},
    {"type": "IfcRelContainedInSpatialStructure", "globalId": "R1"},       # relationship -> excluded
]}
idx = ifc5_reader.build_index_from_json(ifcjson)
assert idx["counts"]["elements"] == 3, idx["counts"]                        # 2 walls + 1 door
assert set(idx["facets"]["classes"]) == {"IfcWall", "IfcDoor"}, idx["facets"]
assert idx["project"]["name"] == "Sample5", idx["project"]
w1 = next(e for e in idx["elements"] if e["guid"] == "W1")
assert w1["ifc_class"] == "IfcWall" and w1["psets"]["Pset_WallCommon"]["IsExternal"] is True, w1
assert idx["geometry"]["readable"] is False, idx["geometry"]

# --- IFCX / USD-layer shape: list of {name, attributes{class}, children} --------------------------
ifcx = [
    {"name": "Beam-01", "attributes": {"ifc5:class": "IfcBeam", "Reference": "B12"}},
    {"name": "Space", "attributes": {"ifc5:class": "IfcSpace"},                # spatial -> excluded
     "children": [{"name": "Col-01", "attributes": {"ifc5:class": "IfcColumn"}}]},
]
idx2 = ifc5_reader.build_index_from_json(ifcx)
assert idx2["counts"]["elements"] == 2, idx2["counts"]                       # beam + nested column
classes = set(idx2["facets"]["classes"])
assert classes == {"IfcBeam", "IfcColumn"}, classes
beam = next(e for e in idx2["elements"] if e["ifc_class"] == "IfcBeam")
assert beam["psets"]["Attributes"]["Reference"] == "B12", beam

# --- index_file dispatches JSON models to the IFC5 reader (STEP still goes to ifcopenshell) --------
with tempfile.TemporaryDirectory() as d:
    j = os.path.join(d, "m.ifcx")
    with open(j, "w", encoding="utf-8") as f:
        json.dump(ifcjson, f)
    assert _is_json_model(j) is True
    built = index_file(j)
    assert built["counts"]["elements"] == 3 and built["schema"] == "IFC5", built["counts"]

    spf = os.path.join(d, "m.ifc")
    with open(spf, "w") as f:
        f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\n")
    assert _is_json_model(spf) is False

print("IFC5 READ OK - ifcJSON {data:[…]} parses 3 physical elements (spatial + rels excluded, psets + "
      "project name kept); IFCX/USD-layer {attributes:{ifc5:class}} parses 2 (incl. nested child); "
      "index_file dispatches JSON->IFC5 reader and STEP->ifcopenshell; geometry flagged not-readable")
