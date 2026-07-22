"""SUBSET-EXPORT — prune the model to a QUERY-DSL slice as a standalone IFC. Engine (keep-set prune
via remove_deep2, spatial skeleton preserved) + the /export/subset.ifc route (gate, 422 on empty
match, valid contained IFC out).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_subset_export.py"""
import os
import tempfile as _tempfile

TMP = os.path.join(os.path.dirname(__file__), "_subset_src.ifc")

# PERF-B6 cleanup test: route the subset FileResponse's mkstemp into an isolated dir so we can assert
# the throwaway .ifc is deleted by the response's BackgroundTask (no /tmp leak).
_SUBSET_TMPDIR = os.path.join(os.path.dirname(__file__), "_subset_tmp")
os.makedirs(_SUBSET_TMPDIR, exist_ok=True)
_tempfile.tempdir = _SUBSET_TMPDIR

import glob as _glob  # noqa: E402
import shutil as _shutil  # noqa: E402

import ifcopenshell  # noqa: E402

from aec_data import edit, ifcpatch_lib, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# each mutating extract_subset needs an INDEPENDENT copy — open_model() is LRU-cached by (path,mtime,
# size), so reuse would hand back the same already-pruned instance. ifcopenshell.open bypasses it.
fresh = ifcopenshell.open

# a mixed 1-storey model: 2 columns (structural) + 1 wall (architectural)
massing.generate_blank_ifc(TMP, name="Subset", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
m.write(TMP)

m = fresh(TMP)
cols = m.by_type("IfcColumn")
walls = m.by_type("IfcWall")
assert len(cols) == 2 and len(walls) == 1, (len(cols), len(walls))
total_elems = len(m.by_type("IfcElement"))       # 2 col + 1 wall + a ground slab (blank-model default)
keep = {c.GlobalId for c in cols}

res = ifcpatch_lib.extract_subset(m, keep)
assert res["available"] is True, res
assert res["kept"] == 2 and res["removed"] == total_elems - 2, (res, total_elems)  # everything else pruned
# the columns survive with GUIDs unchanged; the wall is gone; the spatial skeleton stays
assert {c.GlobalId for c in m.by_type("IfcColumn")} == keep, "kept columns changed"
assert not m.by_type("IfcWall"), "wall should be pruned"
assert m.by_type("IfcProject") and m.by_type("IfcBuildingStorey"), "spatial skeleton must survive"
# the pruned model is a valid, writable IFC (re-open round-trips)
OUT = os.path.join(os.path.dirname(__file__), "_subset_out.ifc")
m.write(OUT)
assert open_model(OUT).by_type("IfcColumn"), "pruned file did not round-trip"
os.remove(OUT)

# empty keep-set → every element pruned; a model with no IfcElement → not available
res2 = ifcpatch_lib.extract_subset(fresh(TMP), set())
assert res2["kept"] == 0 and res2["removed"] == total_elems, res2
# a model with NO IfcElement (prune everything, then subset again) → not available
bare = fresh(TMP)
ifcpatch_lib.extract_subset(bare, set())          # removes every element
assert ifcpatch_lib.extract_subset(bare, set())["available"] is False

# --- route: gate + select + stream; 422 on empty match --------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_subset_export.db"
os.environ["STORAGE_DIR"] = "./test_storage_subset"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_subset_export.db"):
    os.remove("./test_subset_export.db")

# rebuild the mixed model as the project source, capturing the real GUIDs for the property index
import json as _json  # noqa: E402

massing.generate_blank_ifc(TMP, name="Subset Route", storeys=1, storey_height=4.0, ground_size=20.0)
mr = fresh(TMP)
str2 = mr.by_type("IfcBuildingStorey")[0].Name
c1 = edit.add_column(mr, [0, 0], 4.0, 0.4, 0.4, str2)
c2 = edit.add_column(mr, [6, 0], 4.0, 0.4, 0.4, str2)
w1 = edit.add_wall(mr, [0, 0], [6, 0], 3.0, 0.2, str2)
mr.write(TMP)

# the DSL selects over the uploaded property index — its `guid`s must be the real IFC GlobalIds
props = _json.dumps({"elements": [
    {"guid": c1, "ifc_class": "IfcColumn", "name": "Col 1", "storey": str2},
    {"guid": c2, "ifc_class": "IfcColumn", "name": "Col 2", "storey": str2},
    {"guid": w1, "ifc_class": "IfcWall", "name": "Wall 1", "storey": str2},
]}).encode()

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Subset"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    up = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", props, "application/json")})
    assert up.status_code == 200 and up.json()["loaded"] == 3, up.text[:160]
    # a class that matches nothing → 422
    assert c.get(f"/projects/{pid}/export/subset.ifc", params={"query": "IfcDuctSegment"}).status_code == 422
    # columns only → a streamed IFC containing IfcColumn but not IfcWall
    r = c.get(f"/projects/{pid}/export/subset.ifc", params={"query": "IfcColumn"})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    body = r.content.decode("utf-8", "ignore")
    assert "IFCCOLUMN" in body.upper() and "IFCWALL" not in body.upper(), "subset content wrong"
    assert "subset" in r.headers.get("content-disposition", "")
    # PERF-B6: the FileResponse's BackgroundTask (TestClient runs it after the response) must delete
    # the server-chosen temp file — no subset-*.ifc left behind in the temp dir.
    leftovers = _glob.glob(os.path.join(_SUBSET_TMPDIR, "subset-*.ifc"))
    assert not leftovers, f"subset temp file leaked: {leftovers}"

if os.path.exists(TMP):
    os.remove(TMP)
_shutil.rmtree(_SUBSET_TMPDIR, ignore_errors=True)

print("SUBSET-EXPORT OK - the keep-set prune drops the wall and keeps both columns (GUIDs unchanged) with the "
      "spatial skeleton intact; the pruned model round-trips as a valid IFC; empty keep-set prunes all, a bare "
      "model is not-available; the /export/subset.ifc route 422s on an empty match and streams a columns-only "
      "IFC (IFCCOLUMN present, IFCWALL gone) for the IfcColumn selector.")
