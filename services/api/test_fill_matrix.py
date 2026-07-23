"""FILL-MATRIX — category × property fill-rate pivot over the property index; each property carries the
blank GUIDs (the selection for a bulk edit) + worst_gaps = the biggest partially-filled fields.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fill_matrix.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_fill_matrix.db"
os.environ["STORAGE_DIR"] = "./test_storage_fillmatrix"
os.environ.pop("AEC_RBAC", None)

from aec_api import fill_matrix as fm  # noqa: E402

idx = {
    "w1": {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"FireRating": "2HR", "LoadBearing": "true"}}},
    "w2": {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"FireRating": "1HR"}}},           # LoadBearing blank
    "w3": {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {}}},                               # both blank
    "w4": {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"LoadBearing": "false"}}},         # FireRating blank
    "s1": {"ifc_class": "IfcSlab", "psets": {"Pset_SlabCommon": {"IsExternal": "false"}}},          # fully filled
}
r = fm.matrix(idx)
assert r["element_count"] == 5 and r["class_count"] == 2, r
wall = next(c for c in r["classes"] if c["ifc_class"] == "IfcWall")
assert wall["count"] == 4, wall
props = {(p["pset"], p["prop"]): p for p in wall["properties"]}
fr = props[("Pset_WallCommon", "FireRating")]
assert fr["filled"] == 2 and fr["blank"] == 2 and fr["fill_rate"] == 0.5, fr
assert set(fr["blank_guids"]) == {"w3", "w4"}, fr["blank_guids"]              # the exact selection for a bulk fill
assert fr["selector"] == "class=IfcWall & Pset_WallCommon.FireRating", fr
lb = props[("Pset_WallCommon", "LoadBearing")]
assert lb["blank"] == 2 and set(lb["blank_guids"]) == {"w2", "w3"}, lb

slab = next(c for c in r["classes"] if c["ifc_class"] == "IfcSlab")
assert slab["properties"][0]["fill_rate"] == 1.0, slab                        # fully filled → not a gap

# worst_gaps = partially-filled fields (0 < rate < 1), most-blank first; the fully-filled slab prop excluded
gaps = {(g["ifc_class"], g["prop"]) for g in r["worst_gaps"]}
assert ("IfcWall", "FireRating") in gaps and ("IfcWall", "LoadBearing") in gaps, r["worst_gaps"]
assert ("IfcSlab", "IsExternal") not in gaps, r["worst_gaps"]

assert fm.matrix(None)["class_count"] == 0                                    # no model → empty, well-formed

# --- route: empty without a model; 200 -------------------------------------------------------------
if os.path.exists("./test_fill_matrix.db"):
    os.remove("./test_fill_matrix.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Fill"}).json()["id"]
    rr = c.get(f"/projects/{pid}/model/fill-matrix")
    assert rr.status_code == 200, rr.text
    assert rr.json()["class_count"] == 0, rr.json()                           # no model loaded yet

print("FILL-MATRIX OK - a category × property fill-rate pivot: of 4 IfcWall, Pset_WallCommon.FireRating is "
      "filled on 2 (0.5) with w3/w4 blank and LoadBearing filled on 2 with w2/w3 blank — each property hands "
      "back the exact blank GUIDs (the selection a bulk edit fills in one pass) + a query-DSL scope; the "
      "fully-filled IfcSlab.IsExternal is excluded from worst_gaps, which surfaces the partially-filled wall "
      "fields most-blank-first; the /model/fill-matrix route returns an empty pivot without a loaded model.")
