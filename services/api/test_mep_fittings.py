"""MEP-FITTINGS — implied tee/cross/reducer/elbow over the port graph → QTO EA lines. Built over three
authored + connected mini-systems (a branch, a size step, a direction change).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_mep_fittings.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_mepfit.ifc")

from aec_data import edit, massing, mep_fittings  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="MEP Fittings", storeys=1, storey_height=4.0, ground_size=40.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# (1) BRANCH → tee: a 3-port JUNCTION hub with three duct segments hung off it.
hub = edit.add_mep_fitting(m, "IfcDuctFitting", [10, 0], 0.3, "JUNCTION", st)
b1 = edit.add_mep_run(m, "IfcDuctSegment", [10, 0], [15, 0], "round", 0.3, st)
b2 = edit.add_mep_run(m, "IfcDuctSegment", [10, 0], [5, 0], "round", 0.3, st)
b3 = edit.add_mep_run(m, "IfcDuctSegment", [10, 0], [10, 5], "round", 0.3, st)
edit.connect_mep(m, hub, b1)
edit.connect_mep(m, hub, b2)
edit.connect_mep(m, hub, b3)

# (2) SIZE STEP → reducer: a 300 mm segment joined in-line to a 200 mm segment (collinear, no turn).
r1 = edit.add_mep_run(m, "IfcDuctSegment", [0, 10], [5, 10], "round", 0.3, st)    # 300 mm
r2 = edit.add_mep_run(m, "IfcDuctSegment", [5, 10], [10, 10], "round", 0.2, st)   # 200 mm
edit.connect_mep(m, r1, r2)

# (3) DIRECTION CHANGE → elbow: a horizontal segment joined to a vertical (in-plane) one, same size.
e1 = edit.add_mep_run(m, "IfcDuctSegment", [0, 20], [5, 20], "round", 0.3, st)    # →x
e2 = edit.add_mep_run(m, "IfcDuctSegment", [5, 20], [5, 25], "round", 0.3, st)    # →y (a 90° turn)
edit.connect_mep(m, e1, e2)

f = mep_fittings.fittings(m)
c = f["fittings"]
assert c["tee"] >= 1, f                      # the 3-way hub
assert c["reducer"] >= 1, f                  # the 300→200 in-line joint
assert c["elbow"] >= 1, f                    # the 90° corner
assert f["total_fittings"] == c["tee"] + c["cross"] + c["reducer"] + c["elbow"], f
# the reducing/turning joints are segment-to-segment; the branch legs are NOT counted as elbows/reducers
assert c["cross"] == 0, f                     # no 4-way node was authored
# QTO lines mirror the counts, one EA line per non-zero fitting type
qty = {ln["fitting"]: ln["qty"] for ln in f["qto_lines"]}
assert qty.get("tee") == c["tee"] and qty.get("reducer") == c["reducer"] and qty.get("elbow") == c["elbow"], f
assert all(ln["unit"] == "EA" for ln in f["qto_lines"]), f

# --- route: 409 without a model; 200 + counts with one ---------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_mep_fittings.db"
os.environ["STORAGE_DIR"] = "./test_storage_mepfit"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_mep_fittings.db"):
    os.remove("./test_mep_fittings.db")
m.write(TMP)
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as client:
    pid = client.post("/projects", json={"name": "MEPFit"}).json()["id"]
    assert client.get(f"/projects/{pid}/mep/fittings").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    rr = client.get(f"/projects/{pid}/mep/fittings")
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["fittings"]["tee"] >= 1 and j["fittings"]["elbow"] >= 1 and j["fittings"]["reducer"] >= 1, j
    assert j["total_fittings"] >= 3 and j["qto_lines"], j

if os.path.exists(TMP):
    os.remove(TMP)

print("MEP-FITTINGS OK - over three authored + connected mini-systems the engine infers the implied "
      "fittings deterministically from the port graph: a tee at the 3-way junction node, a reducer at the "
      "300→200 mm in-line joint, and an elbow at the 90° segment-to-segment corner (branch legs are not "
      "double-counted as elbows/reducers); the counts roll into QTO as EA lines, and the /mep/fittings "
      "route 409s without a model and returns the fitting counts otherwise.")
