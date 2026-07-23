"""PROGRESS-ROLLUP — % complete from as-built element presence, by IFC class / discipline / level / overall,
by count AND by value (which diverge when cheap elements are up but expensive ones are outstanding).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_progress_rollup.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_progress_rollup.db"
os.environ["STORAGE_DIR"] = "./test_storage_progress"
os.environ.pop("AEC_RBAC", None)

from aec_api import progress_rollup as pr  # noqa: E402


def _w(g):
    return {"guid": g, "ifc_class": "IfcWall", "discipline": "Architectural", "storey": "L1", "value": 1000}


def _s(g):
    return {"guid": g, "ifc_class": "IfcSlab", "discipline": "Structural", "storey": "L1", "value": 5000}


elements = [_w("w1"), _w("w2"), _w("w3"), _w("w4"), _s("s1"), _s("s2")]
r = pr.rollup(elements, ["w1", "w2", "w3", "w4"])          # all walls up, no slabs
assert r["element_count"] == 6 and r["installed_count"] == 4 and r["pct_complete"] == 0.667, r
# count vs value diverge: 4/6 by count (0.667) but only $4k/$14k by value (0.286)
assert r["value_total"] == 14000 and r["value_installed"] == 4000 and r["pct_complete_value"] == 0.286, r

cls = {c["ifc_class"]: c for c in r["by_class"]}
assert cls["IfcWall"]["pct_complete"] == 1.0 and cls["IfcWall"]["installed"] == 4, cls["IfcWall"]
assert cls["IfcSlab"]["pct_complete"] == 0.0 and cls["IfcSlab"]["pct_complete_value"] == 0.0, cls["IfcSlab"]
disc = {d["discipline"]: d for d in r["by_discipline"]}
assert disc["Architectural"]["pct_complete"] == 1.0 and disc["Structural"]["pct_complete"] == 0.0, disc
lvl = {x["level"]: x for x in r["by_level"]}
assert lvl["L1"]["pct_complete"] == 0.667 and lvl["L1"]["expected"] == 6, lvl

# discipline falls back to the classification map when not supplied
r2 = pr.rollup([{"guid": "x", "ifc_class": "IfcWall"}], [])
assert r2["by_discipline"][0]["discipline"], r2["by_discipline"]

assert pr.rollup([], [])["pct_complete"] == 0.0                          # empty is well-formed

# --- route: 404 missing project; 200 otherwise -----------------------------------------------------
if os.path.exists("./test_progress_rollup.db"):
    os.remove("./test_progress_rollup.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/progress/rollup", json={"elements": elements, "installed_guids": ["w1"]}).status_code == 404
    pid = c.post("/projects", json={"name": "Progress"}).json()["id"]
    rr = c.post(f"/projects/{pid}/progress/rollup", json={"elements": elements, "installed_guids": ["w1", "w2", "w3", "w4"]})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["pct_complete"] == 0.667 and j["pct_complete_value"] == 0.286, j

print("PROGRESS-ROLLUP OK - as-built presence (all 4 walls installed, 0 of 2 slabs) rolls up to 4/6 = 66.7% "
      "complete by count but only $4k/$14k = 28.6% by value (the divergence that matters — cheap elements up, "
      "expensive ones outstanding); by IFC class IfcWall is 100% and IfcSlab 0%, by discipline Architectural "
      "100% / Structural 0%, by level L1 66.7%; discipline falls back to the classification map when omitted; "
      "the /progress/rollup route 404s on a missing project.")
