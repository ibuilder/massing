"""AUTH-CONSTRAINTS ① — the broken-host / illegal-placement checker over IFC's own constraint graph:
healthy models are clean; deleted hosts, dangling fills, out-of-extent inserts, uncontained elements
and level/elevation disagreements each surface with the right kind + severity.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_constraints.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_constraints.db"
os.environ["STORAGE_DIR"] = "./test_storage_constraints"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_constraints.db"):
    os.remove("./test_constraints.db")

import ifcopenshell.api  # noqa: E402

from aec_data import constraints, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "constraints_test.ifc"
massing.generate_blank_ifc(str(_ifc), name="Constraints", storeys=2, storey_height=3.5, ground_size=20.0)
m = open_model(str(_ifc))
L1 = "Level 1"

# --- healthy: a hosted, filled, contained door in a wall → no errors, no warnings ------------------
wall_a = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, L1)
edit.add_opening(m, wall_a, width=0.9, height=2.1, kind="door")
r0 = constraints.check(m)
assert r0["errors"] == 0 and r0["warnings"] == 0, r0["issues"]
assert r0["checked"]["openings"] == 1 and r0["checked"]["storeys"] == 2, r0["checked"]

# --- insert_outside_host: an opening projected past the wall's end -------------------------------
wall_b = edit.add_wall(m, [0, 5], [4, 5], 3.0, 0.2, L1)
edit.add_opening(m, wall_b, width=0.9, height=2.1, kind="window", sill=1.0, position=[9.0, 5.0])
r1 = constraints.check(m)
outside = [i for i in r1["issues"] if i["kind"] == "insert_outside_host"]
assert len(outside) == 1 and outside[0]["severity"] == "error", r1["issues"]
assert "outside its extent" in outside[0]["detail"], outside[0]

# --- uncontained_element: a column stripped of its storey containment ------------------------------
col = edit.add_column(m, [2, 2], 3.0, 0.4, 0.4, L1)
col_el = next(e for e in m.by_type("IfcColumn") if e.GlobalId == col)
for rel in list(col_el.ContainedInStructure or []):
    if len(rel.RelatedElements) == 1:
        m.remove(rel)
    else:
        rel.RelatedElements = [e for e in rel.RelatedElements if e.GlobalId != col]
r2 = constraints.check(m)
unc = [i for i in r2["issues"] if i["kind"] == "uncontained_element"]
assert len(unc) == 1 and unc[0]["guid"] == col and unc[0]["severity"] == "warning", r2["issues"]

# --- level_mismatch: a wall built at z=0 but re-contained on Level 2 (elev 3.5) --------------------
wall_d = edit.add_wall(m, [0, 10], [6, 10], 3.0, 0.2, L1)
wall_d_el = next(e for e in m.by_type("IfcWall") if e.GlobalId == wall_d)
lvl2 = next(s for s in m.by_type("IfcBuildingStorey") if s.Name == "Level 2")
ifcopenshell.api.run("spatial.assign_container", m, products=[wall_d_el], relating_structure=lvl2)
r3 = constraints.check(m)
mism = [i for i in r3["issues"] if i["kind"] == "level_mismatch"]
assert len(mism) == 1 and mism[0]["guid"] == wall_d, r3["issues"]
assert "Level 2" in mism[0]["detail"] and mism[0]["severity"] == "warning", mism[0]

# --- orphan_opening + orphan_fill: delete a host wall, then delete another door's opening ----------
wall_e = edit.add_wall(m, [10, 0], [16, 0], 3.0, 0.2, L1)
edit.add_opening(m, wall_e, width=0.9, height=2.1, kind="door")
wall_e_el = next(e for e in m.by_type("IfcWall") if e.GlobalId == wall_e)
m.remove(wall_e_el)                                        # refs to it unset → the opening dangles
door_a_el = next(e for e in m.by_type("IfcDoor")
                 if (e.FillsVoids or []) and e.FillsVoids[0].RelatingOpeningElement is not None
                 and (e.FillsVoids[0].RelatingOpeningElement.VoidsElements or [])
                 and e.FillsVoids[0].RelatingOpeningElement.VoidsElements[0].RelatingBuildingElement is not None)
m.remove(door_a_el.FillsVoids[0].RelatingOpeningElement)   # now THAT door's opening is gone
r4 = constraints.check(m)
kinds = r4["counts"]
assert kinds.get("orphan_opening", 0) >= 1, r4["counts"]
assert kinds.get("orphan_fill", 0) >= 1, r4["counts"]
assert r4["errors"] >= 3, r4["errors"]                     # outside-host + orphan opening + orphan fill
# errors sort before warnings before info
sev = [i["severity"] for i in r4["issues"]]
assert sev == sorted(sev, key=lambda s: {"error": 0, "warning": 1, "info": 2}[s]), sev

# --- route: 409 without a model; 200 with one ------------------------------------------------------
m.write(str(_ifc))
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Constraints"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/constraints").status_code == 409
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    rr = c.get(f"/projects/{pid}/model/constraints")
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["issue_count"] == r4["issue_count"] and j["errors"] == r4["errors"], j["counts"]

if _ifc.exists():
    _ifc.unlink()

print("AUTH-CONSTRAINTS OK - IFC's own constraint graph validated: a healthy hosted/filled/contained "
      "door raises nothing; an opening projected past its wall's end is an insert_outside_host error; "
      "a column stripped of containment is an uncontained_element warning; a z=0 wall re-contained on "
      "Level 2 (elev 3.5) is a level_mismatch warning; deleting a host wall orphans its opening and "
      "deleting an opening dangles its door fill (both errors); issues sort errors > warnings > info "
      "and the /model/constraints route 409s without a model.")
