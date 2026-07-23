"""WALL-ASSEMBLY thermal — R/U computed from the IfcMaterialLayerSet layers (thickness ÷ design k +
surface films) + per-layer material takeoff.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_assembly_thermal.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_asmth.ifc")

from aec_data import assembly_thermal as at  # noqa: E402

# --- pure analyze(): a brick-cavity wall, hand-checked -------------------------------------------
layers = [
    {"name": "Brick veneer", "category": "masonry", "thickness_m": 0.090},      # 0.090/0.77 = 0.1169
    {"name": "Air cavity", "category": "air", "thickness_m": 0.025},            # fixed 0.17
    {"name": "Rigid insulation", "category": "insulation", "thickness_m": 0.050},  # 0.050/0.030 = 1.6667
    {"name": "Gypsum board", "category": "gypsum", "thickness_m": 0.016},       # 0.016/0.16 = 0.1
]
r = at.analyze(layers)
# R = films 0.17 + 0.1169 + 0.17 + 1.6667 + 0.1 = 2.2236 → U = 0.450
assert r["r_value"] == 2.224 and r["u_value"] == 0.45, r
assert r["thickness_m"] == 0.181 and r["r_value_imperial"] == 12.6, r
assert r["layers"][2]["r_value"] == 1.667, r["layers"][2]                      # insulation dominates
assert r["layers"][1]["r_value"] == 0.17, r["layers"][1]                       # air cavity = fixed R

# an explicit k overrides the category
o = at.analyze([{"category": "insulation", "thickness_m": 0.05, "k": 0.025}])
assert o["layers"][0]["r_value"] == 2.0, o

assert at.analyze([])["u_value"] == round(1 / 0.17, 3)                          # films only

# --- from_model over an authored model with applied layer sets -------------------------------------
from aec_data import massing, material_layers  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="Asm", storeys=1, storey_height=3.0, ground_size=12.0)
m = open_model(TMP)
from aec_data import edit  # noqa: E402

st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.add_wall(m, [0, 3], [6, 3], 3.0, 0.2, st)
applied = material_layers.apply_layer_sets(m)
assert applied["assigned"] >= 2, applied

f = at.from_model(m)
assert f["assembly_count"] >= 1, f
a0 = f["assemblies"][0]
assert a0["element_count"] >= 2 and a0["u_value"] and a0["u_value"] > 0, a0
assert a0["layers"] and all(ly["r_value"] >= 0 for ly in a0["layers"]), a0
assert a0["takeoff"] and a0["takeoff"][0]["thickness_m"] > 0, a0["takeoff"]

# --- route: 409 without a model; 200 with one ------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_assembly_thermal.db"
os.environ["STORAGE_DIR"] = "./test_storage_asmth"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_assembly_thermal.db"):
    os.remove("./test_assembly_thermal.db")
m.write(TMP)
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Asm"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/assembly-thermal").status_code == 409
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    rr = c.get(f"/projects/{pid}/model/assembly-thermal")
    assert rr.status_code == 200, rr.text
    assert rr.json()["assembly_count"] >= 1, rr.json()

if os.path.exists(TMP):
    os.remove(TMP)

print("WALL-ASSEMBLY THERMAL OK - a brick/cavity/insulation/gypsum wall computes R 2.224 (R-12.6 imperial) "
      "→ U 0.45 from the layers themselves (insulation contributes 1.667, the air cavity its fixed 0.17, "
      "films 0.17; an explicit k overrides the category); over an authored model with applied layer sets the "
      "engine finds the assembly, its 2+ walls, positive U, per-layer R and a thickness-based takeoff; the "
      "/model/assembly-thermal route 409s without a source IFC.")
