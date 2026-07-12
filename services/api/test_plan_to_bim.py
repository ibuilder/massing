"""2D -> BIM raise: build a synthetic DXF floor plan, raise it to IFC, and verify the walls/spaces
round-trip. Plus endpoint preview + raise + a 404 smoke.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_plan_to_bim.py"""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_plan_to_bim.db"
os.environ["STORAGE_DIR"] = "./test_storage_plan_to_bim"
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="p2b_ifc_")
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_plan_to_bim.db",):
    if os.path.exists(_f):
        os.remove(_f)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

import ezdxf  # noqa: E402
import ifcopenshell  # noqa: E402

from aec_data import plan_to_bim  # noqa: E402


def _make_dxf(path):
    """A 6x4 m room: 4 wall lines on WALL + a closed room polygon on ROOM (drawn in metres)."""
    doc = ezdxf.new(); doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    doc.layers.add("WALL"); doc.layers.add("ROOM")
    pts = [(0, 0), (6, 0), (6, 4), (0, 4)]
    for i in range(4):
        a = pts[i]; b = pts[(i + 1) % 4]
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "ROOM"})
    doc.saveas(path)


d = tempfile.mkdtemp()
dxf = os.path.join(d, "plan.dxf")
_make_dxf(dxf)

# --- pure parse ---
plan = plan_to_bim.parse_plan(dxf)
assert plan["wall_count"] == 4, plan["wall_count"]
assert plan["room_count"] == 1, plan["room_count"]
assert plan["total_wall_length_m"] == 20.0, plan["total_wall_length_m"]   # 6+4+6+4
assert plan["total_floor_area_m2"] == 24.0, plan["total_floor_area_m2"]   # 6*4
assert plan["units"] == "m", plan["units"]
print(f"parse_plan: {plan['wall_count']} walls, {plan['room_count']} room, "
      f"{plan['total_wall_length_m']} m, {plan['total_floor_area_m2']} m2")

# --- raise to IFC and reopen ---
out = os.path.join(d, "raised.ifc")
res = plan_to_bim.raise_plan(dxf, out, wall_height=3.0, wall_thickness=0.2)
assert res["wall_count"] == 4 and res["space_count"] == 1, res
m = ifcopenshell.open(out)
assert len(m.by_type("IfcWall")) == 4, len(m.by_type("IfcWall"))
assert len(m.by_type("IfcSpace")) == 1, len(m.by_type("IfcSpace"))
assert len(m.by_type("IfcBuildingStorey")) == 1
# every element has a GUID; the space carries its floor area in the Qto
guids = [w.GlobalId for w in m.by_type("IfcWall")]
assert all(guids) and len(set(guids)) == 4, "walls need unique GlobalIds"
sp = m.by_type("IfcSpace")[0]
area = None
for rel in getattr(sp, "IsDefinedBy", []) or []:
    pd = getattr(rel, "RelatingPropertyDefinition", None)
    if pd and pd.is_a("IfcElementQuantity"):
        for q in pd.Quantities:
            if q.Name == "NetFloorArea":
                area = q.AreaValue
assert area == 24.0, area
print(f"raise_plan: {res['wall_count']} IfcWall + {res['space_count']} IfcSpace "
      f"(NetFloorArea={area} m2), {os.path.getsize(out)} bytes")

# --- empty DXF raises cleanly ---
empty = os.path.join(d, "empty.dxf")
ezdxf.new().saveas(empty)
try:
    plan_to_bim.raise_plan(empty, os.path.join(d, "x.ifc"))
    raise AssertionError("expected RuntimeError on an empty DXF")
except RuntimeError:
    pass

# --- endpoints (preview + raise + 404) ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "P"}).json()["id"]
    with open(dxf, "rb") as fh:
        r = tc.post(f"/projects/{pid}/raise-plan", data={"preview": "true"},
                    files={"file": ("plan.dxf", fh.read(), "application/dxf")})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.json()["wall_count"] == 4 and r.json()["room_count"] == 1, r.json()

    with open(dxf, "rb") as fh:
        r = tc.post(f"/projects/{pid}/raise-plan",
                    data={"wall_height": "2.7", "wall_thickness": "0.15"},
                    files={"file": ("plan.dxf", fh.read(), "application/dxf")})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    body = r.json()
    assert body["discipline"] == "2D Raise" and body["wall_count"] == 4 and body["space_count"] == 1, body
    # it registered a discipline model
    models = tc.get(f"/projects/{pid}/models").json()
    assert any(mm["id"] == body["id"] for mm in models), models

    # unknown project -> 404
    with open(dxf, "rb") as fh:
        r = tc.post("/projects/nope/raise-plan", files={"file": ("plan.dxf", fh.read(), "application/dxf")})
    assert r.status_code == 404, r.status_code

print("test_plan_to_bim OK")
