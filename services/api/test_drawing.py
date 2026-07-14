"""W11 C1 plan SVG generator: derive a schematic plan drawing from element footprints (walls/columns/
slabs) — the first slice of the construction-document set, no geometry kernel needed.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_drawing.py"""
import os
import re
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawing, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_drawing_test.ifc")
massing.generate_blank_ifc(TMP, name="Drawing Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a rectangular room of 4 walls + a column
edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.add_wall(m, [6, 0], [6, 4], 3.0, 0.2, st)
edit.add_wall(m, [6, 4], [0, 4], 3.0, 0.2, st)
edit.add_wall(m, [0, 4], [0, 0], 3.0, 0.2, st)
edit.add_column(m, [3, 2], 3.0, 0.4, 0.4, st)

r = drawing.plan_svg(m, scale=100)
svg = r["svg"]
# drawn elements: 4 walls + 1 column + the blank model's ground slab = 6, each a polygon
assert r["elements"] == 6, r
assert svg.count("<polygon") == 6, svg.count("<polygon")
# valid SVG root + class-styled linework (walls, column, and the slab all present)
assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), svg[:60]
assert svg.count('class="el IfcWall"') == 4 and 'class="el IfcColumn"' in svg and 'class="el IfcSlab"' in svg
assert "PLAN 1:100" in svg
# has real paper dimensions (mm) and a viewBox
assert re.search(r'width="[\d.]+mm"', svg) and 'viewBox="0 0 ' in svg, svg[:200]
# bounds cover the 6×4 m room
assert r["bounds"]["max"][0] - r["bounds"]["min"][0] >= 6.0, r["bounds"]

# storey filter: a bogus storey name → no elements → empty-but-valid SVG
empty = drawing.plan_svg(m, storey="Nonexistent Level")
assert empty["elements"] == 0 and empty["svg"].startswith("<svg"), empty

# scale changes the paper size (1:50 is twice the mm of 1:100)
r50 = drawing.plan_svg(m, scale=50)
w100 = float(re.search(r'width="([\d.]+)mm"', svg).group(1))
w50 = float(re.search(r'width="([\d.]+)mm"', r50["svg"]).group(1))
assert w50 > w100, (w50, w100)

if os.path.exists(TMP):
    os.remove(TMP)

print("DRAWING OK - plan_svg derives a schematic plan from footprints: 4 walls + 1 column -> 5 class-styled "
      "polygons in a valid, paper-dimensioned SVG (PLAN 1:100); storey filter yields an empty-but-valid "
      "sheet; scale drives paper size (1:50 larger than 1:100). No geometry kernel required.")
