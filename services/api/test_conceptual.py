"""Conceptual estimating (parametric $/SF) + IFC reclassification suggestions.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_conceptual.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_conceptual.db"
os.environ["STORAGE_DIR"] = "./test_storage_conceptual"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_conceptual.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import conceptual_estimate as ce, ifc_classify   # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- conceptual estimate ---
r = ce.estimate({"building_type": "multifamily", "gfa_sf": 100000, "units": 100, "region": "us_average"})
assert r["hard_cost"] == 265 * 100000, r                 # base $/SF * GFA at US avg, base year
assert r["soft_cost"] == round(r["hard_cost"] * 0.25, 0), r
assert r["metrics"]["cost_per_unit"] == round(r["total_cost"] / 100, 0), r["metrics"]
assert r["range"]["low"] < r["total_cost"] < r["range"]["high"], r["range"]
# region + escalation raise the number
r_ny = ce.estimate({"building_type": "multifamily", "gfa_sf": 100000, "region": "new_york", "year": 2028})
assert r_ny["hard_cost"] > r["hard_cost"], (r_ny["hard_cost"], r["hard_cost"])
assert r_ny["region_index"] == 1.35 and r_ny["escalation_factor"] > 1, r_ny
# unknown type falls back to office (flagged), never errors; missing GFA -> error
assert "default" in ce.estimate({"building_type": "spaceship", "gfa_sf": 1000})["building_type"]
assert "error" in ce.estimate({"building_type": "office"})

# --- IFC classify ---
els = [
    {"guid": "g1", "name": "Basic Wall: Exterior", "ifc_class": "IfcBuildingElementProxy"},  # generic -> wall (high)
    {"guid": "g2", "name": "Concrete Slab on Grade", "ifc_class": "IfcBuildingElementProxy"},  # generic -> slab
    {"guid": "g3", "name": "M_Fixed Window", "ifc_class": "IfcWindow"},                        # already correct -> no suggestion
    {"guid": "g4", "name": "Steel Beam W12", "ifc_class": "IfcColumn"},                        # misclassified beam-as-column
]
cl = ifc_classify.classify(els)
sug = {s["guid"]: s for s in cl["suggestions"]}
assert sug["g1"]["suggested_class"] == "IfcWall" and sug["g1"]["confidence"] == "high", sug.get("g1")
assert sug["g2"]["suggested_class"] == "IfcSlab", sug.get("g2")
assert "g3" not in sug, "correctly-classified window needs no suggestion"
assert sug["g4"]["suggested_class"] == "IfcBeam" and sug["g4"]["confidence"] == "medium", sug.get("g4")
assert cl["generic_elements"] == 2, cl
assert cl["by_target_class"].get("IfcWall") == 1, cl["by_target_class"]

# --- endpoints ---
with TestClient(app) as c:
    assert c.get("/estimate/conceptual/catalog").json()["building_types"], "catalog"
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    e = c.post(f"/projects/{pid}/estimate/conceptual",
               json={"building_type": "hotel", "gfa_sf": 200000, "keys": 250, "region": "miami"})
    assert e.status_code == 200 and e.json()["metrics"]["cost_per_key"] > 0, e.text[:160]
    cc = c.post(f"/projects/{pid}/ifc/classify", json={"elements": els})
    assert cc.status_code == 200 and cc.json()["count"] == 3, cc.text[:160]

print("CONCEPTUAL OK - parametric $/SF estimate (multifamily base; NY+2028 escalated higher; unknown "
      "type->office; no-GFA->error; $/unit + $/key); IFC classify: proxy->Wall/Slab (high), beam-as-"
      "column->Beam (medium), correct window skipped; endpoints 200")
