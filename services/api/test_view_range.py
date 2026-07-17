"""VIEW-RANGE: a plan cut at `elevation + cut_height` can additionally show, as dashed hidden lines, the
footprint of elements BELOW the cut but within a given view depth (foundations/footings) — the Revit
Top/Cut/Bottom/View-Depth model rather than a single cut_z.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_view_range.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_view_range_test.ifc")
massing.generate_blank_ifc(TMP, name="View Range", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a column rising through the cut plane (so the plan has cut linework) + a footing pad below the floor
edit.add_column(m, [5, 5], 3.0, 0.4, 0.4, st)          # z 0..3 — intersected by a 1.2 m cut
edit.add_footing(m, [5, 5], width=1.5, length=1.5, thickness=0.4, storey=st)  # z -0.4..0, below the floor

meshes = drawings.bake(m)
assert meshes, "model must bake to meshes"

# --- the view-depth band controls what 'below' returns ------------------------------------------------
# cut plane at z=1.2; a deep view depth (down to z=-2.0) catches the footing (top at z≈0); a shallow one
# (only to z=1.0, i.e. 0.2 m below the cut) catches nothing below.
deep = drawings.below_footprint_baked(meshes, 1.2, -2.0)
shallow = drawings.below_footprint_baked(meshes, 1.2, 1.0)
assert len(deep) >= 1, f"a deep view depth must surface the footing below the cut: {len(deep)}"
assert len(shallow) == 0, f"a shallow view depth (0.2 m) surfaces nothing below: {len(shallow)}"

# a class filter scopes the 'below' set (footings only still returns the footing; walls-only returns none)
only_ftg = drawings.below_footprint_baked(meshes, 1.2, -2.0, classes=["IfcFooting"])
only_wall = drawings.below_footprint_baked(meshes, 1.2, -2.0, classes=["IfcWall"])
assert len(only_ftg) >= 1 and len(only_wall) == 0, (len(only_ftg), len(only_wall))

# --- plan_svg wires view_depth: dashed 'below' linework + a legend appear only when requested ----------
svg_vd = drawings.plan_svg(m, elevation=0.0, cut_height=1.2, title="PLAN", grid=False, rooms=False,
                           view_depth=2.0)
svg_no = drawings.plan_svg(m, elevation=0.0, cut_height=1.2, title="PLAN", grid=False, rooms=False)
assert "below cut (view depth)" in svg_vd, "view-depth plan must carry the legend"
assert 'stroke="#999"' in svg_vd and 'stroke-dasharray="5 3"' in svg_vd, "below linework is dashed + light"
assert "below cut (view depth)" not in svg_no, "a plain plan must NOT show the below legend"
# both are valid SVGs of the same cut
assert svg_vd.startswith("<?xml") and svg_no.startswith("<?xml"), "valid SVG documents"
assert "1.20 m AFF" in svg_vd, "titleblock still reports the cut plane AFF"

# a zero / negative view depth is a no-op (same as omitting it)
svg_zero = drawings.plan_svg(m, elevation=0.0, cut_height=1.2, title="PLAN", grid=False, rooms=False,
                             view_depth=0.0)
assert "below cut (view depth)" not in svg_zero, "view_depth=0 draws no below linework"

if os.path.exists(TMP):
    os.remove(TMP)

print("VIEW-RANGE OK - plan_svg accepts a view_depth (metres below the cut): below_footprint_baked returns "
      "the plan footprint of elements under the cut but within that depth (a deep depth surfaces the "
      "footing, a shallow one nothing; class-filterable), sectioned through each element's mid-height; "
      "plan_svg draws them as dashed light hidden lines with a 'below cut (view depth)' legend only when "
      "view_depth>0, while the cut linework + titleblock AFF are unchanged — the Top/Cut/Bottom/View-Depth "
      "model, not a single cut_z.")
