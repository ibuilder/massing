"""FAMILY-DEPTH ④ — shared parameters: the validated registry, values through the normal edit
recipes, registered params surfacing as schedule columns, and SCHED-CALC formulas over them.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_shared_params.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_shared_params.db"
os.environ["STORAGE_DIR"] = "./test_storage_shparams"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_shared_params.db"):
    os.remove("./test_shared_params.db")

from aec_api import shared_params as sp  # noqa: E402

# --- registry validation rails ---------------------------------------------------------------------
good = [{"name": "FireRating", "ptype": "text", "applies_to": ["IfcDoor", "IfcWindow"]},
        {"name": "AcousticClass", "pset": "Pset_Acoustic", "ptype": "text",
         "applies_to": ["IfcDoor"], "label": "STC"}]
clean = sp.validate(good)
assert clean[0]["pset"] == "Pset_Shared" and clean[1]["label"] == "STC"
for bad, why in ((
        [{"name": "FireRating", "applies_to": ["IfcDoor"]},
         {"name": "firerating", "applies_to": ["IfcDoor"]}], "duplicate"),
        ([{"name": "9bad", "applies_to": ["IfcDoor"]}], "letter-first"),
        ([{"name": "X", "ptype": "date", "applies_to": ["IfcDoor"]}], "ptype"),
        ([{"name": "X", "applies_to": []}], "applies_to"),
        ([{"name": "X", "applies_to": ["NotAClass"]}], "IFC class")):
    try:
        sp.validate(bad)
        raise AssertionError(f"expected rejection: {why}")
    except ValueError:
        pass
assert sp.schedule_columns(clean, "IfcDoor") == [
    {"label": "FireRating", "pset": "Pset_Shared", "prop": "FireRating"},
    {"label": "STC", "pset": "Pset_Acoustic", "prop": "AcousticClass"}]
assert sp.schedule_columns(clean, "IfcSpace") == []

# --- end to end: registry → value via the normal edit recipe → schedule column → formula -----------
import ifcopenshell.api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "shared_params.ifc"
massing.generate_blank_ifc(str(_ifc), name="SP", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, "Level 1")
edit.add_opening(m, w, width=0.9, height=2.1, kind="door")
door = m.by_type("IfcDoor")[0]
# the value is written through the SAME pset machinery the set_element_pset recipe uses
ps = ifcopenshell.api.run("pset.add_pset", m, product=door, name="Pset_Shared")
ifcopenshell.api.run("pset.edit_pset", m, pset=ps, properties={"FireRating": "2HR"})
m.write(str(_ifc))

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "SP"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()

    # registry CRUD (validated atomically; a bad registry never half-saves)
    r = c.put(f"/projects/{pid}/shared-params", json={"params": good})
    assert r.status_code == 200 and len(r.json()["params"]) == 2, r.text
    assert c.get(f"/projects/{pid}/shared-params").json()["params"][0]["name"] == "FireRating"
    assert c.put(f"/projects/{pid}/shared-params",
                 json={"params": [{"name": "9bad", "applies_to": ["IfcDoor"]}]}).status_code == 422
    assert c.get(f"/projects/{pid}/shared-params").json()["params"][0]["name"] == "FireRating"

    # the registered params ARE schedule columns now (value present; unset param = blank cell)
    sched = c.get(f"/projects/{pid}/drawings/schedules").json()
    assert sched["doors"]["columns"][-2:] == ["FireRating", "STC"], sched["doors"]["columns"]
    row = sched["doors"]["rows"][0]
    assert row[-2] == "2HR" and row[-1] == "", row
    assert "FireRating" not in sched["rooms"]["columns"]           # scoped by applies_to

    # …and therefore reachable by SCHED-CALC formulas (normalized column name)
    r = c.post(f"/projects/{pid}/drawings/schedules/calc",
               json={"doors": [{"name": "Rated", "expr": '"yes" if firerating == "2HR" else "no"'}]})
    assert r.status_code == 200, r.text
    doors = r.json()["doors"]
    rated_col = doors["columns"].index("Rated")
    assert doors["rows"][0][rated_col] == "yes", doors["rows"]

if _ifc.exists():
    _ifc.unlink()

print("SHARED-PARAMS OK - the registry validates atomically (duplicate/letter-first/ptype/"
      "applies_to/IFC-class rails; defaults Pset_Shared; a bad PUT 422s and leaves the old registry "
      "intact); registered parameters surface as door-schedule columns scoped by applies_to "
      "(FireRating '2HR' from the pset, unset STC blank, rooms untouched) and SCHED-CALC formulas "
      "reference them by normalized name (firerating == \"2HR\" -> 'yes').")
