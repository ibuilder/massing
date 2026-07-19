"""SMART-VIEWS — user-authored saved view presets (name + QUERY-DSL selector + isolate/color/hide),
persisted per project, resolved to GUIDs for the viewer. Engine tested over an injected property
index; route contract validated (save/list/run + 422 on a bad selector + 404 on an unknown id).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_smart_views.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_smart_views.db"
os.environ["STORAGE_DIR"] = "./test_storage_smart_views"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_smart_views.db"):
    os.remove("./test_smart_views.db")

from aec_api import smart_views  # noqa: E402
from aec_api.query_dsl import QueryError  # noqa: E402

# --- engine: colour validation + normalization ----------------------------------------------------
v = smart_views._norm({"name": "L3 ducts", "selector": "IfcDuctSegment & storey=L3", "mode": "color",
                       "color": "#FF8800"})
assert v["mode"] == "color" and v["color"] == "#ff8800" and v["id"], v          # hex lowercased, id minted
assert smart_views._norm({"selector": "IfcWall", "mode": "color", "color": "nope"})["color"] is None
assert smart_views._norm({"selector": "IfcWall"})["mode"] == "isolate", "default mode"
assert smart_views._norm({"selector": "IfcWall", "mode": "isolate", "color": "#fff000"})["color"] is None  # color only on color mode
for bad in ({"selector": ""}, {"selector": "IfcWall", "mode": "explode"}, {"selector": "x" * 501}):
    try:
        smart_views._norm(bad); raise AssertionError(f"expected QueryError for {bad}")
    except QueryError:
        pass

# --- engine: run resolves the selector over the property index ------------------------------------
IDX = {
    "g1": {"ifc_class": "IfcDuctSegment", "storey": "L3", "name": "D1"},
    "g2": {"ifc_class": "IfcDuctSegment", "storey": "L2", "name": "D2"},
    "g3": {"ifc_class": "IfcWall", "storey": "L3", "name": "W1"},
}
r = smart_views.run(IDX, v)
assert r["matched"] == 1 and r["guids"] == ["g1"] and r["mode"] == "color", r     # only L3 duct
r_all = smart_views.run(IDX, smart_views._norm({"selector": "storey=L3", "name": "all L3"}))
assert set(r_all["guids"]) == {"g1", "g3"}, r_all
assert smart_views.run(None, v)["guids"] == [], "no model → empty, no crash"

# --- route contract: save → list → run; 422 bad selector; 404 unknown id --------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.routers.properties import _INDEX  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "SmartViews"}).json()["id"]
    assert c.get(f"/projects/{pid}/smart-views").json() == {"views": [], "count": 0}

    payload = [{"name": "L3 ducts", "selector": "IfcDuctSegment & storey=L3", "mode": "color", "color": "#ff8800"},
               {"name": "All L3", "selector": "storey=L3", "mode": "isolate"}]
    put = c.put(f"/projects/{pid}/smart-views", json={"views": payload})
    assert put.status_code == 200 and put.json()["saved"] == 2, put.text
    vid = put.json()["views"][0]["id"]

    got = c.get(f"/projects/{pid}/smart-views").json()
    assert got["count"] == 2 and got["views"][0]["name"] == "L3 ducts", got

    # a bad selector rejects the WHOLE save (atomic) with 422 — nothing overwrites the saved set
    bad = c.put(f"/projects/{pid}/smart-views", json={"views": [{"name": "x", "selector": ""}]})
    assert bad.status_code == 422, bad.text
    assert c.get(f"/projects/{pid}/smart-views").json()["count"] == 2, "422 must not clobber the saved views"

    # run resolves against the loaded index (injected here); unknown id → 404
    _INDEX[pid] = IDX
    run = c.get(f"/projects/{pid}/smart-views/{vid}/run").json()
    assert run["matched"] == 1 and run["guids"] == ["g1"] and run["color"] == "#ff8800", run
    _INDEX.pop(pid, None)
    assert c.get(f"/projects/{pid}/smart-views/nope/run").status_code == 404

print("SMART-VIEWS OK - saved view presets (name + QUERY-DSL selector + isolate/color/hide) validate + "
      "persist atomically (bad selector → 422, no clobber); colour only kept in color mode + hex-checked; "
      "run() resolves the selector to GUIDs over the property index (L3 duct → [g1]; storey=L3 → g1,g3; "
      "no model → empty); routes list/save/run with 404 on an unknown id.")
