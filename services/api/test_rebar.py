"""W11 B6 reinforcement detailing: a concrete column gets a rebar CAGE — 4 longitudinal corner bars +
stirrups at a spacing, as swept-disk IfcReinforcingBars, assembled with the column. LOD 400 rebar.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_rebar.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing, rebar  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_rebar_test.ifc")
massing.generate_blank_ifc(TMP, name="Rebar Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a rectangular (concrete) column, 0.5×0.5 × 3.5 m
col = edit.add_column(m, [3, 3], 3.5, 0.5, 0.5, st)
assert col

# --- rebar cage: 4 longitudinal bars + stirrups, assembled with the column -----------------------
n_bar0 = len(m.by_type("IfcReinforcingBar"))
r = rebar.add_rebar_cage(m, col, bar_size="#8", tie_size="#3", cover=0.04, tie_spacing=0.3)
assert r["bars"] == 4, r
assert r["ties"] >= 2, r
made = len(m.by_type("IfcReinforcingBar")) - n_bar0
assert made == r["bars"] + r["ties"], (made, r)

# geometry is swept-disk (IfcSweptDiskSolid) — real rebar, not boxes
bars = m.by_type("IfcReinforcingBar")
solids = [it for b in bars for rep in (b.Representation.Representations if b.Representation else [])
          for it in (rep.Items or [])]
assert solids and all(s.is_a() == "IfcSweptDiskSolid" for s in solids), "rebar not swept-disk"
# longitudinal bars are straight (2-pt directrix); stirrups are closed rectangles (5-pt directrix)
longit = [b for b in bars if b.Name == "Rebar"]
stirrups = [b for b in bars if b.Name == "Stirrup"]
assert len(longit) == 4 and len(stirrups) == r["ties"], (len(longit), len(stirrups))
lp = longit[0].Representation.Representations[0].Items[0].Directrix.Points
assert len(lp) == 2, "longitudinal bar should be a straight 2-point directrix"
sp = stirrups[0].Representation.Representations[0].Items[0].Directrix.Points
assert len(sp) == 5, "stirrup should be a closed 5-point (rectangle) directrix"

# assembled into an IfcElementAssembly with the column
asm = m.by_guid(r["assembly"])
assert asm.is_a() == "IfcElementAssembly"
parts = [o for rel in (asm.IsDecomposedBy or []) for o in rel.RelatedObjects]
assert col in {p.GlobalId for p in parts} and len(parts) == 1 + r["bars"] + r["ties"], len(parts)

# --- non-column rejected + cover-too-large rejected ----------------------------------------------
w = edit.add_wall(m, [0, 0], [4, 0], 3.0, 0.2, st)
for bad, exc in ((lambda: rebar.add_rebar_cage(m, w), "wall"),
                 (lambda: rebar.add_rebar_cage(m, col, cover=0.5), "cover")):
    try:
        bad(); raised = False
    except ValueError:
        raised = True
    assert raised, f"{exc} should raise"

# --- recipe path (the /edit route) ---------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_rebar_out.ifc")
rc = edit.apply_recipe(TMP, "add_rebar_cage", {"column_guid": col, "tie_spacing": 0.25}, OUT)
assert rc["changed"]["bars"] == 4 and rc["changed"]["ties"] >= 2, rc
mo = open_model(OUT)
assert mo.by_guid(rc["changed"]["assembly"]).is_a() == "IfcElementAssembly"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("REBAR OK - add_rebar_cage builds a reinforcement cage in a concrete column: 4 longitudinal corner "
      "bars (straight swept-disk IfcReinforcingBar) + stirrups (closed-rectangle swept-disk) at spacing, "
      "assembled with the column into an IfcElementAssembly (LOD 400); non-column + oversized-cover rejected; "
      "add_rebar_cage recipe works via apply_recipe.")
