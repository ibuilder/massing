"""Model integrity / hygiene checks — build an IFC in memory with each defect and verify the scan.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_qa.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_qa.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_qa"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_qa.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ifcopenshell  # noqa: E402
import ifcopenshell.guid  # noqa: E402

from aec_api import model_qa  # noqa: E402

f = ifcopenshell.file(schema="IFC4")


def _place(x, y, z):
    pt = f.create_entity("IfcCartesianPoint", Coordinates=(float(x), float(y), float(z)))
    ax = f.create_entity("IfcAxis2Placement3D", Location=pt)
    return f.create_entity("IfcLocalPlacement", RelativePlacement=ax)


storey = f.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="Level 1")
# w1: clean, contained in the storey
w1 = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W-1", ObjectPlacement=_place(0, 0, 0))
# w2: same class + same placement as w1 -> overlapping duplicate; also not contained -> orphan
w2 = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W-2", ObjectPlacement=_place(0, 0, 0))
# w3: blank name + duplicate GlobalId (shares w1's) + not contained -> orphan
w3 = f.create_entity("IfcWall", GlobalId=w1.GlobalId, Name="", ObjectPlacement=_place(5, 0, 0))
# contain only w1 in the storey
f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                RelatingStructure=storey, RelatedElements=[w1])
# an unenclosed space (no IfcRelSpaceBoundary)
f.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 1", ObjectPlacement=_place(10, 0, 0))

q = model_qa.model_qa(f)
c = q["checks"]
assert q["element_count"] == 3, q["element_count"]                        # w1, w2, w3
assert c["duplicate_guids"]["count"] == 1, c["duplicate_guids"]           # w1 & w3 share a GUID
assert c["overlapping_duplicates"]["count"] == 1, c["overlapping_duplicates"]   # w1 & w2 stacked
assert c["orphaned_elements"]["count"] == 2, c["orphaned_elements"]       # w2, w3 not in a storey
assert c["unenclosed_spaces"]["count"] == 1 and c["unenclosed_spaces"]["total_spaces"] == 1, c["unenclosed_spaces"]
assert c["blank_names"]["count"] == 1, c["blank_names"]                   # w3
assert q["total_issues"] == 1 + 1 + 2 + 1 + 1 and not q["clean"], q["total_issues"]
print(f"model_qa: {q['total_issues']} issues across {q['element_count']} elements — "
      f"{ {k: v['count'] for k, v in c.items()} }")

# a clean model has no issues
g = ifcopenshell.file(schema="IFC4")
st = g.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L1")
gw = g.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W-1",
                     ObjectPlacement=g.create_entity("IfcLocalPlacement",
                     RelativePlacement=g.create_entity("IfcAxis2Placement3D",
                     Location=g.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)))))
g.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                RelatingStructure=st, RelatedElements=[gw])
q2 = model_qa.model_qa(g)
assert q2["clean"] and q2["total_issues"] == 0, q2

# wrong-storey: a wall assigned to L1 (elev 0) but placed at z=3, right at L2 (elev 3) -> flagged
h = ifcopenshell.file(schema="IFC4")


def _hplace(z):
    return h.create_entity("IfcLocalPlacement", RelativePlacement=h.create_entity(
        "IfcAxis2Placement3D", Location=h.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, float(z)))))


l1 = h.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L1", Elevation=0.0)
h.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L2", Elevation=3.0)
ok = h.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="ok", ObjectPlacement=_hplace(0))    # at L1
bad = h.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="bad", ObjectPlacement=_hplace(3))   # near L2
h.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                RelatingStructure=l1, RelatedElements=[ok, bad])   # both assigned to L1
q3 = model_qa.model_qa(h)
ws = q3["checks"]["wrong_storey"]
assert ws["count"] == 1 and ws["sample"][0]["guid"] == bad.GlobalId, ws
assert ws["sample"][0]["nearest_storey"] == "L2" and ws["sample"][0]["placed_z"] == 3.0, ws
print(f"wrong_storey: flagged '{ws['sample'][0]['name']}' assigned L1 but placed at L2 elevation")

# endpoint: no source IFC -> 409
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "P"}).json()["id"]
    r = tc.get(f"/projects/{pid}/models/qa")
    assert r.status_code == 409, (r.status_code, r.text[:160])

print("test_model_qa OK")
