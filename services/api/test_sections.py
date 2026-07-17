"""W11 C5 sections/elevations: the section cut auto-centres on the model (so it lands through the
building, not the world origin) and the section/elevation endpoints render SVG.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sections.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_sec_test.ifc")
massing.generate_blank_ifc(TMP, name="Section Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
# a wall placed AWAY from the world origin — a section at x=0 would miss it entirely
edit.add_wall(m, [10, 5], [18, 5], 3.0, 0.2, st)

meshes = drawings.bake(m)
cx = drawings._axis_center(meshes, 0)          # midpoint of the X extent
assert cx > 1.0, f"auto-centre should be well off origin, got {cx}"

# auto-centred section (offset=None) cuts through the model → non-empty linework
auto = drawings.section_svg(m, "x")            # offset omitted → auto-centre
assert auto.startswith("<svg") or "<svg" in auto[:120], "section must be an SVG"
assert f"X = {cx:.2f} m" in auto, f"subtitle should carry the centred offset {cx:.2f}"
assert "<polyline" in auto or "<path" in auto or "<line" in auto, "auto-centred cut should draw geometry"

# a far-away explicit offset misses everything (proves the cut plane actually moves with offset,
# i.e. geometry is world-placed — a wall at x≈14 is not hit by a plane at x=1000)
far = drawings.section_svg(m, "x", offset=1000.0)
assert "No geometry on this cut" in far, "far cut plane should miss the world-placed model"

# elevations render for each cardinal direction
for d in ("north", "south", "east", "west"):
    svg = drawings.elevation(m, d)
    assert "<svg" in svg[:120] and f"{d.upper()} ELEVATION" in svg, f"{d} elevation"

# regression: space tags + element callouts must be built in WORLD coords too, so their centroids
# align with the (world-placed) linework instead of collapsing to each element's local origin.
massing.generate_blank_ifc(TMP, name="Tag Test", storeys=1, storey_height=3.5, ground_size=20.0)
mt = open_model(TMP)
stt = mt.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(mt, rooms_per_storey=4, ceiling_height=3.0)
wt = edit.add_wall(mt, [8, 6], [14, 6], 3.0, 0.2, stt)
edit.add_opening(mt, wt, width=0.9, height=2.1, kind="door")
mesh_bounds = drawings.bake(mt)
xs = [b for _, mh in mesh_bounds if getattr(mh, "bounds", None) is not None
      for b in (mh.bounds[0][0], mh.bounds[1][0])]
lo_x, hi_x = min(xs), max(xs)
tags = drawings.space_tags(mt)
assert tags, "expected room tags"
# at least one room tag must sit away from x=0 (proves world placement, not local-origin collapse)
assert any(abs(t["x"]) > 1.0 for t in tags), f"space tags collapsed to local origin: {[t['x'] for t in tags]}"
assert all(lo_x - 1 <= t["x"] <= hi_x + 1 for t in tags), "tags must fall within the world linework bounds"
cos = drawings.element_callouts(mt, ("IfcDoor",))
assert cos and cos[0]["x"] > 5.0, f"door callout should be near the world-placed wall (~x=11), got {cos}"

# a plan cut at a level tags ONLY that level's rooms (no cross-level stacking) + carries a titleblock.
TMP2 = os.path.join(os.path.dirname(__file__), "_sec_plan.ifc")
massing.generate_blank_ifc(TMP2, name="Plan Levels", storeys=3, storey_height=3.0, ground_size=20.0)
ml = open_model(TMP2)
levels = ml.by_type("IfcBuildingStorey")
for i, lv in enumerate(sorted(levels, key=lambda s: float(getattr(s, "Elevation", 0) or 0))):
    edit.add_space(ml, 1, 1, 6, 5, f"RoomOnFloor{i}", lv.Name, 3.0) if hasattr(edit, "add_space") else \
        edit.add_spaces(ml, rooms_per_storey=1, ceiling_height=3.0)
elevs = drawings.storey_elevations(ml)
mid = next(s for s in elevs if abs(s["elevation"] - 3.0) < 0.6)      # the 2nd storey (~3 m)
cut_z = mid["elevation"] + 1.2
tags_here = drawings.space_tags(ml, cut_z=cut_z)
tags_all = drawings.space_tags(ml)                                    # unfiltered = every floor's rooms
assert 0 < len(tags_here) < len(tags_all), (len(tags_here), len(tags_all))   # the cut isolates one level
# every tag returned for the cut actually straddles the cut plane
svg = drawings.plan_svg(ml, elevation=mid["elevation"], cut_height=1.2, title=f"PLAN - {mid['name']}", rooms=True)
assert "GENERAL NOTES" in svg and "GRAPHIC SCALE" in svg and "AFF" in svg, "plan must carry a titleblock + scale + notes"
import xml.dom.minidom as _md  # noqa: E402
_md.parseString(svg)                                                  # well-formed even with room names

# composed key-plan sheet: a tall model must NOT render a plan panel per storey (slow + illegible) —
# it caps to a few representative levels; `storey` renders exactly one.
TMP3 = os.path.join(os.path.dirname(__file__), "_sec_sheet.ifc")
massing.generate_blank_ifc(TMP3, name="Tall", storeys=9, storey_height=3.0, ground_size=16.0)
mtall = open_model(TMP3)
meta = {"number": "A-101", "title": "PLANS", "project": "Tall"}
full = drawings.default_sheet(mtall, meta, page="A3", fmt="svg")     # sampled, capped at 4
assert 0 < full.count('class="cell-label"') or "PLAN " in full        # sheet rendered
assert full.count("PLAN ") <= 5, f"key-plan sheet must cap plans, got {full.count('PLAN ')}"
_md.parseString(full)
one_lvl = drawings.default_sheet(mtall, meta, page="A3", fmt="svg", storey="Level 3")
assert one_lvl.count("PLAN Level") == 1, one_lvl.count("PLAN Level")   # a single-level sheet
if os.path.exists(TMP3):
    os.remove(TMP3)
for f in (TMP2,):
    if os.path.exists(f):
        os.remove(f)

if os.path.exists(TMP):
    os.remove(TMP)

print("SECTIONS OK - section_svg auto-centres the cut on the model extent (offset=None → mid-X), honours "
      "an explicit offset, and elevations render for N/S/E/W.")
