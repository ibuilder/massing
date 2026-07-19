"""RULE-LIB-2 geometric checks — AABB-level clearance / escape-distance / clear-width over
synthetic boxes (no IFC needed; bake_boxes is the same iterator the clash broad phase already
covers), plus the /rules/geometry/run route contract (defaults, 422s).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_geometric_rules.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_georules.db"
os.environ["STORAGE_DIR"] = "./test_storage_georules"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_georules.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_data import geometric_rules as gr  # noqa: E402


def box(guid, x0, x1, y0, y1, z0, z1, cls="IfcWall", name=None):
    return {"guid": guid, "ifc_class": cls, "name": name, "min": (x0, y0, z0), "max": (x1, y1, z1)}


# --- clear_width: opening width = larger horizontal dim --------------------------------------------
DOOR_OK = box("d-ok", 0, 0.9, 0, 0.1, 0, 2.1, "IfcDoor", "D1")     # 900 mm wide
DOOR_NARROW = box("d-nar", 0, 0.7, 5, 5.1, 0, 2.1, "IfcDoor", "D2")  # 700 mm — fails ADA proxy
r = gr.check_clear_width([DOOR_OK, DOOR_NARROW], {"d-ok", "d-nar"}, 0.815)
assert r["checked"] == 2 and len(r["violations"]) == 1, r
assert r["violations"][0]["guid"] == "d-nar" and r["violations"][0]["width_m"] == 0.7, r

# --- escape_distance: straight-line to the nearest exit --------------------------------------------
EXIT = box("exit", 0, 1, 0, 0.1, 0, 2.1, "IfcDoor")
NEAR = box("room-a", 5, 8, 2, 6, 0, 3, "IfcSpace")            # centre (6.5, 4) → ~7.6 m
FAR = box("room-b", 80, 84, 2, 6, 0, 3, "IfcSpace")           # centre (82, 4) → ~81.6 m
r = gr.check_escape_distance([EXIT, NEAR, FAR], {"room-a", "room-b"}, {"exit"}, 60.0)
assert r["checked"] == 2 and len(r["violations"]) == 1, r
assert r["violations"][0]["guid"] == "room-b" and r["violations"][0]["distance_m"] > 60, r
r = gr.check_escape_distance([NEAR], {"room-a"}, set(), 60.0)   # no exits → note, no violations
assert r["violations"] == [] and "no exit" in r["note"], r

# --- clearance: approach slab along the thin axis; host + floor are not obstructions ---------------
DOOR = box("door", 0, 1, 0, 0.1, 0, 2.1, "IfcDoor", "Entry")   # thin axis = y
HOST = box("host", -2, 3, -0.05, 0.15, 0, 3)                   # overlaps the door itself → ignored
FLOOR = box("floor", -10, 10, -10, 10, -0.2, 0.02)             # under the z-trim → ignored
r = gr.check_clearance([DOOR, HOST, FLOOR], {"door"}, 0.9)
assert r["checked"] == 1 and r["violations"] == [], r          # both sides clear

FRONT = box("cab-f", 0.2, 0.8, 0.3, 0.6, 0.5, 1.5)             # blocks +y side only
r = gr.check_clearance([DOOR, HOST, FLOOR, FRONT], {"door"}, 0.9)
assert r["violations"] == [], r                                # one side still clear → passes

BACK = box("cab-b", 0.2, 0.8, -0.6, -0.3, 0.5, 1.5)            # now −y blocked too
r = gr.check_clearance([DOOR, HOST, FLOOR, FRONT, BACK], {"door"}, 0.9)
assert len(r["violations"]) == 1, r
assert set(r["violations"][0]["blocking"]) == {"cab-b", "cab-f"}, r

# an obstruction just beyond the probe distance doesn't block
FAR_OB = box("far", 0.2, 0.8, 1.2, 1.5, 0.5, 1.5)              # 1.1 m in front > 0.9 m probe
r = gr.check_clearance([DOOR, HOST, FAR_OB, BACK], {"door"}, 0.9)
assert r["violations"] == [], r

# restricting the obstruction set excludes the blocker
r = gr.check_clearance([DOOR, FRONT, BACK], {"door"}, 0.9, obstructions={"cab-f"})
assert r["violations"] == [], r                                # BACK not in the obstruction set

# --- run(): rollup shape mirrors the property library ----------------------------------------------
out = gr.run([DOOR, HOST, FRONT, BACK, DOOR_NARROW, EXIT, NEAR, FAR], [
    {"id": "c1", "kind": "clearance", "scope": ["door"], "distance_m": 0.9, "severity": "high"},
    {"kind": "clear_width", "scope": ["d-nar"], "min_m": 0.815},
    {"kind": "escape_distance", "scope": ["room-a", "room-b"], "exits": ["exit"], "max_m": 60.0},
])
assert out["violation_total"] == 3 and out["by_severity"] == {"high": 1, "medium": 2}, out
assert [x["passed"] for x in out["results"]] == [False, False, False], out
try:
    gr.run([], [{"kind": "nope", "scope": []}])
    raise AssertionError("unknown kind must raise")
except ValueError:
    pass

# --- bake_boxes over a real generated IFC (same iterator as the clash broad phase) -----------------
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from aec_data import massing  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "georules_test_model.ifc"
massing.generate_ifc(massing.compute_massing({"lot_width": 30, "lot_depth": 20, "far": 2.0,
                                              "floor_to_floor": 3.5, "height_limit": 14}),
                     str(_ifc), name="GeoRules Test")
baked = gr.bake_boxes(str(_ifc))
assert baked and all(b["guid"] and len(b["min"]) == 3 and len(b["max"]) == 3 for b in baked), \
    f"bake_boxes returned {len(baked)} boxes"
assert all(b["max"][i] >= b["min"][i] for b in baked for i in range(3)), "degenerate AABB"
allg = {b["guid"] for b in baked}
wide = gr.check_clear_width(baked, allg, 0.001)     # every real element is wider than 1 mm
assert wide["checked"] == len(baked) and wide["violations"] == [], wide

# --- route contract: registered, starter defaults, 422 on garbage ----------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "GeoRules"}).json()["id"]
    assert "/projects/{pid}/rules/geometry/run" in app.openapi()["paths"]
    bad = c.post(f"/projects/{pid}/rules/geometry/run",
                 json={"checks": [{"kind": "teleport", "scope": "IfcDoor"}]})
    assert bad.status_code == 422 and "kind" in bad.json()["detail"], bad.text
    bad2 = c.post(f"/projects/{pid}/rules/geometry/run",
                  json={"checks": [{"kind": "clearance", "scope": "IfcDoor", "distance_m": -3}]})
    assert bad2.status_code == 422 and "distance_m" in bad2.json()["detail"], bad2.text
    bad3 = c.post(f"/projects/{pid}/rules/geometry/run",
                  json={"checks": [{"kind": "clearance"}]})     # no scope → empty selector → 422
    assert bad3.status_code == 422 and "bad selector" in bad3.json()["detail"], bad3.text
    # a valid request on a model-less project fails cleanly at source-IFC resolution, not a 500
    nosrc = c.post(f"/projects/{pid}/rules/geometry/run", json={})
    assert 400 <= nosrc.status_code < 500 and "source" in nosrc.json()["detail"].lower(), nosrc.text

print("GEOMETRIC RULES OK - clear_width flags the 700mm door (ADA 815mm proxy); escape_distance "
      "flags the 81m room at a 60m straight-line max (no-exit gives a note, not violations); "
      "clearance needs ONE clear approach side along the thin axis (host wall + floor excluded, "
      "both-sides-blocked flags with the blocking GUIDs, beyond-probe obstructions and out-of-set "
      "obstructions ignored); run() rolls up by severity; the route 422s on bad kind/param/selector.")
