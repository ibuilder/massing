"""W11 B6 structural steel connections: a bare steel column/beam (LOD 300) gets a base plate + anchor
bolts / shear tab + bolts (LOD 350/400), assembled into an IfcElementAssembly. Verifies the plate,
fasteners, geometry, and the fabrication assembly.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_steel_connections.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import connections, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_steelconn_test.ifc")
massing.generate_blank_ifc(TMP, name="Conn Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# native steel column + beam (AISC W-shapes)
col = edit.add_steel_column(m, [2, 2], 3.5, "W12x26", st)
beam = edit.add_steel_beam(m, [2, 2], [8, 2], "W16x40", st)
assert col and beam

# --- base plate + 4 anchor bolts, assembled with the column ------------------------------------------
n_plate0, n_bolt0 = len(m.by_type("IfcPlate")), len(m.by_type("IfcMechanicalFastener"))
r = connections.add_base_plate(m, col, width=0.45, depth=0.45, thickness=0.03, bolts=4)
assert len(m.by_type("IfcPlate")) == n_plate0 + 1, "no base plate"
assert len(m.by_type("IfcMechanicalFastener")) == n_bolt0 + 4, "expected 4 anchor bolts"
plate = m.by_guid(r["plate"])
assert plate.is_a() == "IfcPlate" and plate.Representation is not None, "plate has no geometry"
bolts = [b for b in m.by_type("IfcMechanicalFastener") if b.Name == "Anchor bolt"]
assert len(bolts) == 4 and all(b.Representation is not None for b in bolts)
assert getattr(bolts[0], "PredefinedType", None) == "ANCHORBOLT", bolts[0].PredefinedType
# the connection is an IfcElementAssembly aggregating the column + plate + bolts (>=6 parts)
asm = m.by_guid(r["assembly"])
assert asm.is_a() == "IfcElementAssembly", asm
parts = [o for rel in (asm.IsDecomposedBy or []) for o in rel.RelatedObjects]
assert col in {p.GlobalId for p in parts} and r["plate"] in {p.GlobalId for p in parts}, "column/plate not in assembly"
assert len(parts) >= 6, f"assembly should hold column+plate+4 bolts, got {len(parts)}"

# --- shear tab + bolts on the beam -------------------------------------------------------------------
r2 = connections.add_shear_tab(m, beam, bolts=3)
assert r2["bolts"] == 3, r2
tab = m.by_guid(r2["plate"])
assert tab.is_a() == "IfcPlate" and tab.Name == "Shear tab"
assert m.by_guid(r2["assembly"]).is_a() == "IfcElementAssembly"

# --- wrong element class is rejected -----------------------------------------------------------------
w = edit.add_wall(m, [0, 0], [4, 0], 3.0, 0.2, st)
try:
    connections.add_base_plate(m, w)          # a wall is not a column
    raised = False
except ValueError:
    raised = True
assert raised, "base plate on a non-column should raise"

# --- recipe path (the /edit route) -------------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_steelconn_out.ifc")
rc = edit.apply_recipe(TMP, "add_base_plate", {"column_guid": col, "bolts": 4}, OUT)
assert rc["changed"]["bolts"] == 4, rc
mo = open_model(OUT)
assert mo.by_guid(rc["changed"]["assembly"]).is_a() == "IfcElementAssembly"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("STEEL CONNECTIONS OK - base plate (IfcPlate) + 4 anchor bolts (IfcMechanicalFastener ANCHORBOLT) "
      "under a steel column, grouped into an IfcElementAssembly (>=6 parts, fabrication LOD 350/400); "
      "shear tab + 3 bolts on a beam; non-column rejected; add_base_plate recipe works via apply_recipe.")
