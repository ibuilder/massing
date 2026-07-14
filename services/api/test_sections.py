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

if os.path.exists(TMP):
    os.remove(TMP)

print("SECTIONS OK - section_svg auto-centres the cut on the model extent (offset=None → mid-X), honours "
      "an explicit offset, and elevations render for N/S/E/W.")
