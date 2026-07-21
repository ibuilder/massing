"""ASSET-REG — derive the maintainable-asset register from the IFC (serviceable equipment / terminals /
controls / transport; ducts/pipes/fittings excluded), the tallies, and the asset_register seed route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_model_assets.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_assets.ifc")

import ifcopenshell  # noqa: E402

from aec_api import model_assets as ma  # noqa: E402
from aec_data import edit_mep, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a blank model + two maintainable terminals + a duct (must be EXCLUDED) + a pump + an elevator
massing.generate_blank_ifc(TMP, name="Assets", storeys=1, storey_height=3.5, ground_size=20.0)
m = ifcopenshell.open(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit_mep.add_mep_terminal(m, "IfcAirTerminal", [1, 1], storey=st)              # terminal → maintainable
edit_mep.add_mep_terminal(m, "IfcFireSuppressionTerminal", [2, 2], storey=st)  # terminal → maintainable
edit_mep.add_mep_run(m, "IfcDuctSegment", [0, 0], [5, 0], "round", 0.3, st)    # IfcFlowSegment → EXCLUDED
m.create_entity("IfcPump", GlobalId=ifcopenshell.guid.new(), Name="CHW Pump 1")            # equipment
m.create_entity("IfcTransportElement", GlobalId=ifcopenshell.guid.new(), Name="Elevator 1")  # transport
m.write(TMP)

res = ma.assets(open_model(TMP))
by_class = {r["ifc_class"]: r["count"] for r in res["by_class"]}
assert res["count"] == 4, (res["count"], by_class)                            # 2 terminals + pump + elevator
assert "IfcDuctSegment" not in by_class, by_class                             # the duct is excluded (not an asset)
assert by_class.get("IfcAirTerminal") == 1 and by_class.get("IfcPump") == 1, by_class
assert by_class.get("IfcTransportElement") == 1, by_class
cats = {r["category"]: r["count"] for r in res["by_category"]}
assert cats.get("terminal") == 2 and cats.get("equipment") == 1 and cats.get("transport") == 1, cats
# every asset is GUID-keyed + carries a discipline; the air terminal picked up its storey
assert all(a["guid"] and a["discipline"] for a in res["assets"]), res["assets"][:2]
at = next(a for a in res["assets"] if a["ifc_class"] == "IfcAirTerminal")
assert at["storey"] == st, at

# --- routes: GET the register + seed the asset_register module (idempotent) ------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_model_assets.db"
os.environ["STORAGE_DIR"] = "./test_storage_assets"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_model_assets.db"):
    os.remove("./test_model_assets.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "FM"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/assets").status_code == 409          # no source IFC yet
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/model/assets")
    assert r.status_code == 200 and r.json()["count"] == 4, r.json()
    # seed the asset_register from the model, then re-seed adds nothing (idempotent by tag)
    s1 = c.post(f"/projects/{pid}/model/assets/seed").json()
    assert s1["created"] == 4 and s1["skipped"] == 0, s1
    assert len(c.get(f"/projects/{pid}/modules/asset_register").json()) == 4, "register populated"
    s2 = c.post(f"/projects/{pid}/model/assets/seed").json()
    assert s2["created"] == 0 and s2["skipped"] == 4, s2
    assert len(c.get(f"/projects/{pid}/modules/asset_register").json()) == 4, "no duplicate assets"

if os.path.exists(TMP):
    os.remove(TMP)

print("ASSET-REG OK - the maintainable-asset register derives straight from the IFC: 2 terminals (air + "
      "fire-suppression), a pump (equipment) and an elevator (transport) are picked up GUID-keyed with "
      "discipline + storey + category, while the duct segment is correctly EXCLUDED (you maintain the unit, "
      "not the duct); the /model/assets route 409s without a model and the /seed route populates the "
      "asset_register module (4 created) idempotently by tag (re-seed adds 0, no duplicates).")
