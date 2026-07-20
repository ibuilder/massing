"""REVISION-DELTA — conceptual cost impact of a model revision. Pure engine (added priced from the
current takeoff, removed counted by class, quantity-modified flagged) over synthetic inputs covering
every branch, plus the /versions/cost-delta route over two real snapshots.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_revision_delta.py"""
import os

from aec_api import revision_delta  # noqa: E402

# --- pure engine: all three branches, precise math --------------------------------------------------
diff_res = {
    "from": 1, "to": 2,
    "added": ["g_new_col", "g_new_wall"],
    "removed": ["g_old_beam", "g_old_col"],
    "modified": [
        {"guid": "g_mod", "name": "Slab 1", "ifc_class": "IfcSlab", "changes": ["quantities changed"]},
        {"guid": "g_ren", "name": "Wall 9", "ifc_class": "IfcWall", "changes": ["renamed"]},
    ],
}
current_rows = [
    {"guid": "g_new_col", "ifc_class": "IfcColumn", "volume": 2.0},      # 2.0 m³ × $650 = 1300
    {"guid": "g_new_wall", "ifc_class": "IfcWall", "area": 10.0},        # 10 m² × $160 = 1600
    {"guid": "other", "ifc_class": "IfcSlab", "volume": 5.0},            # not in `added` → ignored
]
prev_fp = {
    "g_old_beam": ["Beam 1", "IfcBeam", None, "L1", "p", "q"],
    "g_old_col": ["Col 9", "IfcColumn", None, "L1", "p", "q"],
}
r = revision_delta.delta(diff_res, current_rows, prev_fp)
assert r["added"]["count"] == 2 and r["added"]["priced_count"] == 2, r["added"]
assert r["added"]["cost"] == 2900.0, r["added"]["cost"]                 # 1300 + 1600
assert r["summary"]["added_cost"] == 2900.0, r["summary"]
# removed counted by class (not priced), from the prior fingerprints
assert r["removed"]["count"] == 2, r["removed"]
rc = {ln["ifc_class"]: ln["count"] for ln in r["removed"]["by_class"]}
assert rc == {"IfcBeam": 1, "IfcColumn": 1}, rc
assert all("discipline" in ln for ln in r["removed"]["by_class"])       # discipline enrichment
# only the quantity-changed modified element is flagged for re-estimate
assert r["requantified"]["count"] == 1, r["requantified"]
assert r["requantified"]["sample"][0]["guid"] == "g_mod", r["requantified"]

# added element absent from the current takeoff → counted but not priced (honest priced_count)
r2 = revision_delta.delta({"added": ["ghost"], "removed": [], "modified": []}, [], {})
assert r2["added"]["count"] == 1 and r2["added"]["priced_count"] == 0 and r2["added"]["cost"] == 0.0, r2["added"]

# --- route: two real snapshots + a current model to price the added elements ------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_revision_delta.db"
os.environ["STORAGE_DIR"] = "./test_storage_revdelta"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_revision_delta.db"):
    os.remove("./test_revision_delta.db")

TMP = os.path.join(os.path.dirname(__file__), "_revdelta.ifc")

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# current model = 3 columns + 1 wall (+ blank-model ground slab)
massing.generate_blank_ifc(TMP, name="RevDelta", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [12, 0], 4.0, 0.4, 0.4, st)
edit.add_wall(m, [0, 0], [12, 0], 3.0, 0.2, st)
m.write(TMP)
m = open_model(TMP)
cols = [c.GlobalId for c in m.by_type("IfcColumn")]
allg = [e.GlobalId for e in m.by_type("IfcElement")]
assert len(cols) == 3 and len(allg) >= 4, (len(cols), len(allg))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import versions  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402


def _idx(guids):
    return {"elements": [{"guid": g} for g in guids]}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RD"}).json()["id"]
    # v1 = the first 2 columns only; v2 = the whole current model
    versions.snapshot(pid, _idx(cols[:2]))
    versions.snapshot(pid, _idx(allg))
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    rr = c.get(f"/projects/{pid}/versions/cost-delta", params={"a": 1, "b": 2})
    assert rr.status_code == 200, (rr.status_code, rr.text[:200])
    j = rr.json()
    # added going v1→v2 = the 3rd column + the wall + the ground slab; priced from the real takeoff
    assert j["added"]["count"] == len(allg) - 2, j["summary"]
    assert j["added"]["cost"] > 0, j["added"]        # a column (volume) + a wall (area) carry a price
    assert j["removed"]["count"] == 0, j["removed"]

if os.path.exists(TMP):
    os.remove(TMP)

print("REVISION-DELTA OK - the pure engine prices ADDED elements from the current takeoff (a 2 m^3 column "
      "$1300 + a 10 m^2 wall $1600 = $2900), counts REMOVED by IFC class from the prior fingerprints "
      "(IfcBeam/IfcColumn, discipline-tagged, unpriced), and flags only the quantity-changed modified "
      "element for re-estimate; an added element missing from the current model is counted but not priced. "
      "The /versions/cost-delta route diffs two real snapshots and prices the elements added v1->v2 from the "
      "live model takeoff.")
