"""TESTFIT-ADJ — space adjacency graph + program-relation score + dimensional-compliance rule pack.
Built over a 2×2 grid of authored IfcSpaces relabelled to program types.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_adjacency.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_adj.ifc")

from aec_data import adjacency as adj  # noqa: E402
from aec_data import edit, massing
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="Adj", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
assert edit.add_spaces(m, rooms_per_storey=4, ceiling_height=3.0) == 4, "expected a 2x2 grid of 4 rooms"
# relabel the grid rooms (01..04 → 2x2: 01=(r0,c0) 02=(r0,c1) 03=(r1,c0) 04=(r1,c1)) to program types
labels = {"01": "Kitchen", "02": "Dining", "03": "Bedroom", "04": "Mechanical"}
for sp in m.by_type("IfcSpace"):
    sp.LongName = labels[str(sp.LongName).split()[-1]]

program = {
    "required_adjacent": [["Kitchen", "Dining"], ["Kitchen", "Mechanical"]],  # one met, one diagonal (unmet)
    "forbidden": [["Bedroom", "Mechanical"]],                                 # these ARE adjacent → a violation
    "dimensional": {"min_room_dim": 2.0, "min_area": 5.0, "min_ceiling_height": 2.5},  # all pass
}
r = adj.evaluate(m, program)
assert r["space_count"] == 4, r
# 2x2 grid: 4 shared edges (2 horizontal + 2 vertical); the 2 diagonals touch only at a corner → excluded
assert r["adjacency"]["edge_count"] == 4, r["adjacency"]
# Kitchen touches Dining (edge) + Bedroom (edge) but NOT Mechanical (diagonal)
kitchen = next(s for s in r["adjacency"]["spaces"] if s["type"] == "Kitchen")
assert set(kitchen["neighbors"]) == {"Dining", "Bedroom"}, kitchen

prog = r["program"]
assert prog["required_total"] == 2 and prog["required_satisfied"] == 1, prog   # Kitchen-Dining yes, Kitchen-Mech no
assert prog["required_pct"] == 0.5, prog
assert len(prog["forbidden_violations"]) == 1, prog                            # Bedroom adjacent to Mechanical
assert prog["forbidden_ok"] is False, prog
assert not r["dimensional"]["violations"], r["dimensional"]                     # generous thresholds → all pass
assert r["dimensional"]["checked"] == 4, r["dimensional"]

# a huge min-area makes every space fail the dimensional pack
r2 = adj.evaluate(m, {"dimensional": {"min_area": 1e9}})
assert len(r2["dimensional"]["violations"]) == 4 and r2["dimensional"]["passed"] == 0, r2["dimensional"]

# --- needs-daylight + needs-wet-wall program terms -------------------------------------------------
# 2x2: every room sits on the envelope → daylight satisfied; Dining shares a wall with the (wet)
# Kitchen → wet-wall met; Mechanical touches only Dining+Bedroom (no wet type) → a violation
r4 = adj.evaluate(m, {"needs_daylight": ["Kitchen"], "needs_wet_wall": ["Dining", "Mechanical"]})
p4 = r4["program"]
assert p4["daylight_results"] == [{"type": "kitchen", "spaces": 1, "exterior": 1, "satisfied": True}], p4
ww = {x["type"]: x for x in p4["wet_wall_results"]}
assert ww["dining"]["satisfied"] is True, ww
assert ww["mechanical"]["satisfied"] is False, ww
assert len(p4["wet_wall_violations"]) == 1 and p4["wet_wall_violations"][0]["type"] == "Mechanical", p4

# 3x3 grid of Offices: the CENTER room has no envelope face → exactly one daylight violation
TMP9 = os.path.join(os.path.dirname(__file__), "_adj9.ifc")
massing.generate_blank_ifc(TMP9, name="Adj9", storeys=1, storey_height=3.5, ground_size=30.0)
m9 = open_model(TMP9)
assert edit.add_spaces(m9, rooms_per_storey=9, ceiling_height=3.0) == 9
for sp in m9.by_type("IfcSpace"):
    sp.LongName = "Office"
r9 = adj.evaluate(m9, {"needs_daylight": ["Office"]})
d9 = r9["program"]["daylight_results"][0]
assert d9["spaces"] == 9 and d9["exterior"] == 8 and d9["satisfied"] is False, d9
assert len(r9["program"]["daylight_violations"]) == 1, r9["program"]["daylight_violations"]
os.remove(TMP9)

# empty program → adjacency graph still computed, no program/dimensional findings
r3 = adj.evaluate(m, {})
assert r3["adjacency"]["edge_count"] == 4 and r3["program"]["required_total"] == 0, r3
assert r3["dimensional"]["checked"] == 0, r3

# --- route: 409 without a model; 200 + evaluation with one -----------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_adjacency.db"
os.environ["STORAGE_DIR"] = "./test_storage_adj"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_adjacency.db"):
    os.remove("./test_adjacency.db")
m.write(TMP)
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Adj"}).json()["id"]
    assert c.post(f"/projects/{pid}/model/adjacency", json={}).status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    rr = c.post(f"/projects/{pid}/model/adjacency", json=program)
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["adjacency"]["edge_count"] == 4 and j["program"]["required_satisfied"] == 1, j

if os.path.exists(TMP):
    os.remove(TMP)

print("TESTFIT-ADJ OK - a 2x2 grid of authored spaces relabelled Kitchen/Dining/Bedroom/Mechanical yields "
      "4 adjacency edges (shared walls; the 2 diagonals touch only at a corner and are excluded); the "
      "program score reports Kitchen-Dining met but Kitchen-Mechanical (diagonal) unmet (1/2, 50%) and flags "
      "the Bedroom-Mechanical forbidden adjacency; the dimensional rule pack passes generous thresholds and "
      "fails every space against a 1e9 m² min-area; the /model/adjacency route 409s without a model.")
