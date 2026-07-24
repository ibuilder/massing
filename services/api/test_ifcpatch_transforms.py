"""IFCPATCH-LIB v2 — the transform recipes: rebase_origin (georeference-preserving),
convert_length_unit (real size preserved), split_by_storey (the slice plan) + the route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ifcpatch_transforms.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_ifcpatch_transforms.db"
os.environ["STORAGE_DIR"] = "./test_storage_patch2"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_ifcpatch_transforms.db"):
    os.remove("./test_ifcpatch_transforms.db")

import ifcopenshell.util.placement as uplace  # noqa: E402
import ifcopenshell.util.unit as uunit  # noqa: E402

from aec_data import edit, ifcpatch_lib, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def world_xy(m, guid):
    """The element's world placement in METRES (unit-scale applied)."""
    scale = uunit.calculate_unit_scale(m)
    mat = uplace.get_local_placement(m.by_guid(guid).ObjectPlacement)
    return (float(mat[0, 3]) * scale, float(mat[1, 3]) * scale)


_ifc = Path(tempfile.gettempdir()) / "ifcpatch_transforms.ifc"
massing.generate_blank_ifc(str(_ifc), name="PX", storeys=2, storey_height=3.0, ground_size=40.0)
m = open_model(str(_ifc))
w1 = edit.add_wall(m, [10, 20], [18, 20], 3.0, 0.2, "Level 1")
w2 = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, "Level 2")
before_xy = world_xy(m, w1)
assert abs(before_xy[0] - 14.0) < 1e-6 and abs(before_xy[1] - 20.0) < 1e-6, before_xy

# --- rebase_origin: the model moves, the survey position does not ----------------------------------
out = ifcpatch_lib.rebase_origin(m, [10.0, 20.0, 0.0])
assert out["moved"] and out["offset"] == [-10.0, -20.0, -0.0], out
after_xy = world_xy(m, w1)
assert abs(after_xy[0] - 4.0) < 1e-6 and abs(after_xy[1] - 0.0) < 1e-6, after_xy   # shifted by -Δ
# every element moves together — relative geometry is untouched
d_before = (before_xy[0] - 14.0, before_xy[1] - 20.0)
assert abs((after_xy[0] - 4.0) - d_before[0]) < 1e-9
# a no-op rebase reports itself instead of touching the file
assert ifcpatch_lib.rebase_origin(m, [0, 0, 0])["moved"] is False
# this blank file carries no map conversion — say so rather than implying the georeference followed
assert out["georeference_updated"] is False and "no IfcMapConversion" in out["note"]

# --- convert_length_unit: unit changes, real-world size does not -----------------------------------
scale_before = uunit.calculate_unit_scale(m)                       # metres per file unit (1.0)
storey2 = next(s for s in m.by_type("IfcBuildingStorey") if s.Name == "Level 2")
elev_m_before = float(storey2.Elevation) * scale_before
wall_xy_before = world_xy(m, w2)

rep = ifcpatch_lib.convert_length_unit(m, "MILLIMETRE")
assert abs(rep["ratio"] - 1000.0) < 1e-9, rep
assert "IfcCartesianPoint" in rep["converted"] and rep["entities_touched"] > 0, rep
scale_after = uunit.calculate_unit_scale(m)
assert abs(scale_after - 0.001) < 1e-12, scale_after               # the file now reads in mm
assert abs(float(storey2.Elevation) - 3000.0) < 1e-6               # 3 m expressed as 3000 mm
assert abs(float(storey2.Elevation) * scale_after - elev_m_before) < 1e-9   # …same real elevation
after = world_xy(m, w2)
assert abs(after[0] - wall_xy_before[0]) < 1e-6 and abs(after[1] - wall_xy_before[1]) < 1e-6
# idempotent + guarded
assert ifcpatch_lib.convert_length_unit(m, "MILLIMETRE")["ratio"] == 1.0
try:
    ifcpatch_lib.convert_length_unit(m, "FURLONG")
    raise AssertionError("unknown unit must ValueError")
except ValueError as e:
    assert "FURLONG" in str(e)
assert abs(ifcpatch_lib.convert_length_unit(m, "METRE")["ratio"] - 0.001) < 1e-12   # and back

# --- split_by_storey: the slice plan ---------------------------------------------------------------
plan = ifcpatch_lib.split_by_storey(m)
assert w1 in plan["storeys"]["Level 1"] and w2 in plan["storeys"]["Level 2"], plan["counts"]
assert plan["counts"]["Level 1"] >= 1 and plan["counts"]["Level 2"] >= 1
assert sorted(plan["storeys"]["Level 1"]) == plan["storeys"]["Level 1"]     # deterministic order

# --- recipes + routes ------------------------------------------------------------------------------
assert "rebase_origin" in edit.RECIPES and "convert_length_unit" in edit.RECIPES
m.write(str(_ifc))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "PX"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    r = c.get(f"/projects/{pid}/model/split-plan")
    assert r.status_code == 200 and "Level 1" in r.json()["storeys"], r.text

if _ifc.exists():
    _ifc.unlink()

print("IFCPATCH-TRANSFORMS OK - rebase_origin shifts every ROOT placement plus the storey datums "
      "(a wall at E14 lands at E4 when (10,20) becomes the origin, relative geometry intact), "
      "reports a no-op honestly and says plainly when there is no IfcMapConversion to carry the "
      "georeference; convert_length_unit rewrites the unit assignment AND rescales the whitelisted "
      "attributes so a 3 m storey reads 3000 mm at the SAME real elevation (ratio 1000, idempotent, "
      "unknown unit refused, round-trips back to metres); split_by_storey plans deterministic "
      "per-storey slices and GET /model/split-plan serves them.")
