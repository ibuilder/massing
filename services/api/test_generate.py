"""Generative massing + family library endpoints (API gate).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_generate.py"""
import os
import sys
import tempfile

# IFC_DIR is read at import time by the authoring router; point it at a temp dir before importing.
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="gen_ifc_")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

import ifcopenshell.util.element as ue  # noqa: E402
import ifcopenshell.util.unit as uunit  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

with TestClient(app) as c:  # context manager triggers startup -> create tables
    # --- family catalog (static, no project) --------------------------------
    r = c.get("/families/catalog")
    assert r.status_code == 200, r.text
    cat = r.json()
    assert cat["count"] >= 12, cat["count"]
    assert {"Furniture", "Sanitary", "Appliance", "Plant"} <= set(cat["categories"]), cat["categories"]

    # --- stateless massing preview (pure math + proforma, no model written) --
    r = c.post("/generate/massing/preview", json={"lot_width": 50, "lot_depth": 40, "far": 3.0,
                                                  "use_type": "residential", "height_limit": 24})
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["metrics"]["floors"] >= 1 and prev["metrics"]["units"] > 0, prev["metrics"]
    assert prev["metrics"]["building_height_m"] <= 24, "height limit must bind"
    assert "proforma" in prev
    assert c.post("/generate/massing/preview", json={"far": 3.0}).status_code == 422  # bad input

    # --- generate a model on a project, then furnish it ----------------------
    pid = c.post("/projects", json={"name": "Gen Test"}).json()["id"]
    r = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 40, "lot_depth": 30, "far": 2.5, "use_type": "residential", "land_cost": 5_000_000})
    assert r.status_code == 200, r.text
    g = r.json()
    floors = g["metrics"]["floors"]
    assert g["source_ifc"] and floors >= 1, g
    # generate seeds a dev_budget so Sources & Uses isn't $0 right after generating (was a gap)
    su = c.get(f"/projects/{pid}/sources-uses").json()
    assert su["total_uses"] > 5_000_000, su   # at least the land + hard costs flowed through

    # generate also completes the GC pillar: cost codes + budget + GMP + cost-loaded schedule
    assert g["gc_seed"]["seeded"] and g["gc_seed"]["activities"] == floors, g["gc_seed"]
    assert len(c.get(f"/projects/{pid}/modules/cost_code").json()) == 6, "CSI cost codes seeded"
    assert len(c.get(f"/projects/{pid}/modules/schedule_activity").json()) == floors, "one structure activity per floor"
    gmp = c.get(f"/projects/{pid}/budget/gmp").json()
    assert gmp["gmp"]["computed"] > 0 and gmp["gmp"]["contract_value"] > 0, gmp["gmp"]
    # the GMP is relational to the developer's hard cost (reconciliation surfaces the delta to sync)
    recon = c.get(f"/projects/{pid}/dev-budget/gmp-reconciliation").json()
    assert recon["gc_gmp"] > 0 and recon["dev_hard_cost"] > 0, recon
    cf = c.get(f"/projects/{pid}/budget/cashflow").json()
    assert cf["loaded_activities"] == floors and cf["total"] > 0, cf   # the schedule is cost-loaded

    # the generated IFC is real: storeys + renderable slabs at metre scale
    src = c.get(f"/projects/{pid}").json()["source_ifc"]
    m = open_model(src)
    assert len(m.by_type("IfcBuildingStorey")) == floors, m.by_type("IfcBuildingStorey")
    assert len(m.by_type("IfcSlab")) == floors, "renderable floor plate per level"
    assert len(m.by_type("IfcSpace")) == floors
    assert abs(uunit.calculate_unit_scale(m) - 1.0) < 1e-9, "model must be in metres (mm regression)"

    # place a family via the add_family recipe (publish off; node not required in the gate)
    r = c.post(f"/projects/{pid}/edit",
               json={"recipe": "add_family", "params": {"family": "sofa", "position": [5.0, 5.0]},
                     "publish": False})
    assert r.status_code == 200, r.text
    src2 = c.get(f"/projects/{pid}").json()["source_ifc"]
    m2 = open_model(src2)
    furn = m2.by_type("IfcFurniture")
    assert len(furn) == 1 and m2.by_type("IfcFurnitureType"), m2.by_type("IfcFurniture")
    assert ue.get_type(furn[0]) is not None, "placed family has no type"

print(f"GENERATE OK - catalog {cat['count']} families; preview (height-bound {prev['metrics']['floors']}fl); "
      f"generated {floors}-floor metre-scale model (storeys+slabs+spaces); add_family -> IfcFurniture placed")
