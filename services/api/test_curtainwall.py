"""W11 B6 curtain-wall systems: author an IfcCurtainWall composed of mullions + transoms (IfcMember) +
glazing panels (IfcPlate) on a cols×rows grid, aggregated under the curtain wall. Verified on both a
metre and a millimetre model (unit-scale correctness).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_curtainwall.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402
import ifcopenshell.util.unit as uu  # noqa: E402

from aec_data import curtainwall, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_cw_test.ifc")
massing.generate_blank_ifc(TMP, name="CW Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a 6 m × 3.5 m curtain wall, 3 columns × 2 rows
r = curtainwall.add_curtain_wall(m, [0, 0], [6, 0], height=3.5, cols=3, rows=2)
assert r["mullions"] == 4 and r["transoms"] == 3 and r["panels"] == 6, r      # cols+1, rows+1, cols*rows
cw = m.by_guid(r["curtain_wall"])
assert cw.is_a() == "IfcCurtainWall", cw

# the parts are aggregated under the curtain wall
parts = [o for rel in (cw.IsDecomposedBy or []) for o in rel.RelatedObjects]
assert len(parts) == 4 + 3 + 6, len(parts)
members = [p for p in parts if p.is_a("IfcMember")]
plates = [p for p in parts if p.is_a("IfcPlate")]
assert len(members) == 7 and len(plates) == 6, (len(members), len(plates))
assert all(p.PredefinedType == "CURTAIN_PANEL" for p in plates), "panels not CURTAIN_PANEL"
assert all(mm.PredefinedType == "MULLION" for mm in members), "members not MULLION"
assert all(p.Representation is not None for p in parts), "a part has no geometry"
# curtain wall itself is contained in the storey
assert ue.get_container(cw) is not None, "curtain wall not contained in a storey"

# --- unit-scale correctness: a glazing panel's real width ≈ cell width (6/3 = 2 m) on BOTH units -----
def _panel_width(model, plate):
    scale = uu.calculate_unit_scale(model)
    solid = [it for rr in plate.Representation.Representations for it in rr.Items
             if it.is_a("IfcExtrudedAreaSolid")][0]
    return float(solid.SweptArea.XDim) * scale

assert abs(_panel_width(m, plates[0]) - 2.0) < 1e-3, f"panel width {_panel_width(m, plates[0])} (want 2.0)"

# millimetre model: same real sizes
MM = os.path.join(os.path.dirname(__file__), "_cw_mm.ifc")
massing.generate_blank_ifc(MM, name="CW mm", storeys=1, storey_height=3.5, ground_size=20.0)
mm = open_model(MM)
for u in mm.by_type("IfcSIUnit"):
    if u.UnitType == "LENGTHUNIT":
        u.Prefix = "MILLI"
rmm = curtainwall.add_curtain_wall(mm, [0, 0], [6, 0], height=3.5, cols=3, rows=2)
pmm = [o for rel in (mm.by_guid(rmm["curtain_wall"]).IsDecomposedBy or []) for o in rel.RelatedObjects if o.is_a("IfcPlate")][0]
assert abs(_panel_width(mm, pmm) - 2.0) < 1e-3, f"mm panel width {_panel_width(mm, pmm)} (want 2.0)"

# --- recipe path (the /edit route) ---------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_cw_out.ifc")
rc = edit.apply_recipe(TMP, "add_curtain_wall", {"start": [0, 5], "end": [4, 5], "cols": 2, "rows": 1}, OUT)
assert rc["changed"]["panels"] == 2, rc
mo = open_model(OUT)
assert mo.by_guid(rc["changed"]["curtain_wall"]).is_a() == "IfcCurtainWall"

# --- coincident start/end raises a clear error (not an opaque placement crash) --------------------
try:
    curtainwall.add_curtain_wall(m, [1, 1], [1, 1])
    raised = False
except ValueError as e:
    raised = "differ" in str(e)
assert raised, "zero-length curtain wall should raise a clear ValueError"

for f in (TMP, MM, OUT):
    if os.path.exists(f):
        os.remove(f)

print("CURTAIN WALL OK - IfcCurtainWall aggregates 4 mullions + 3 transoms (IfcMember MULLION) + 6 glazing "
      "panels (IfcPlate CURTAIN_PANEL) on a 3×2 grid, contained in the storey; panel real width = 2.0 m on "
      "BOTH metre and millimetre models (unit-scale correct); add_curtain_wall recipe works via apply_recipe.")
