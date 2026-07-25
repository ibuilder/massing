"""W10-5 + C6 — a section that can be issued, not just one that is geometrically correct.

`section_svg` produced bare linework: every edge the same weight, no levels, no grid, no dimensions.
That drawing is *correct* and *unusable* — a section exists to communicate vertical relationships,
and a reader had no way to get a floor-to-floor height out of it except by measuring the screen.

This covers the annotation layer: poché that separates cut material from what is merely visible
beyond it, C6 reference-line datums, grid bubbles, and the dimension chain.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_section_annotation.py
"""
import os
import re

os.environ["DATABASE_URL"] = "sqlite:///./test_section_annotation.db"
os.environ["STORAGE_DIR"] = "./test_storage_section_annotation"
if os.path.exists("./test_section_annotation.db"):
    os.remove("./test_section_annotation.db")

import sys  # noqa: E402

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a 3-storey shell with walls the cut passes through, at known 3.5 m storey heights
PATH = os.path.join(os.path.dirname(__file__), "_section_annot.ifc")
massing.generate_blank_ifc(PATH, name="Section Annotation", storeys=3, storey_height=3.5,
                           ground_size=24.0)
model = open_model(PATH)
for _st in model.by_type("IfcBuildingStorey"):
    # spanning the origin: the auto-centred cut lands at mid-X, so a wall off to one side is missed
    edit.add_wall(model, [-9, 0], [9, 0], 3.2, 0.25, _st.Name)
    edit.add_wall(model, [0, -9], [0, 9], 3.2, 0.25, _st.Name)
levels = drawings.storey_elevations(model)
assert len(levels) >= 3, levels
meshes = drawings.bake(model)
grid = drawings.grid_from_meshes(meshes)
offset = drawings._axis_center(meshes, 0)

# ---- poché: the cut is FILLED, and grouped by what the material is -----------------------------
svg = drawings.section_drawing_svg(meshes, "x", offset, levels, "SECTION A", grid=grid, lod="coarse")
assert svg.startswith("<?xml") and svg.rstrip().endswith("</svg>")
polys = re.findall(r'<polygon [^>]*fill="(#[0-9a-f]{3,6})"', svg)
assert polys, "coarse poché must fill the cut loops"
# structure reads heavier than enclosure — that ordering IS the information poché carries
assert drawings._poche_fill("IfcSlab", "coarse") == "#4a4a4a"
assert drawings._poche_fill("IfcWall", "coarse") == "#8a8a8a"
assert drawings._poche_fill("IfcDoor", "coarse") == "#d8d8d8"
# an unfamiliar class is drawn faintly, never as though it were structure
assert drawings._poche_fill("IfcSomethingNew", "coarse") == drawings._POCHE_LIGHT
assert drawings._poche_fill("", "coarse") == drawings._POCHE_LIGHT

# ---- LOD drives how much tone survives ----------------------------------------------------------
fine = drawings.section_drawing_svg(meshes, "x", offset, levels, "SECTION A", grid=grid, lod="fine")
line = drawings.section_drawing_svg(meshes, "x", offset, levels, "SECTION A", grid=grid, lod="line")
assert 'fill-opacity="1.00"' in svg and 'fill-opacity="0.45"' in fine, "fine must step the tone back"
assert 'fill-opacity=' not in line and 'fill="none"' in line, "line LOD carries no poché at all"
assert drawings._poche_fill("IfcSlab", "line") == "none"
# the linework is identical across LODs — only the fill changes
assert svg.count("<polygon") == fine.count("<polygon") == line.count("<polygon")

# a misspelled LOD is refused, not silently defaulted to a plausible-looking weight
for bad in ("COARSE", "medium", "", None):
    try:
        drawings.section_drawing_svg(meshes, "x", offset, levels, "S", lod=bad)
        raise AssertionError(f"expected refusal for lod={bad!r}")
    except ValueError as e:
        assert "lod must be one of" in str(e), str(e)
assert drawings.SECTION_LODS == {"coarse", "fine", "line"}, drawings.SECTION_LODS

# ---- C6 datums: every in-range level gets a reference line, named and tagged ---------------------
for lv in levels:
    assert f'+{lv["elevation"]*1000:.0f}' in svg, f'no datum tag for {lv["name"]}'
    assert str(lv["name"]) in svg, lv["name"]
assert svg.count('stroke="#0a6" stroke-width="0.6" stroke-dasharray="8 4"') == len(levels), \
    "one datum line per storey"

# ---- THE POINT: the floor-to-floor chain is on the drawing ---------------------------------------
# 3.5 m storeys → 3500 between consecutive levels, and an overall from lowest to highest.
rises = [round((b["elevation"] - a["elevation"]) * 1000) for a, b in zip(levels, levels[1:])]
assert rises and all(r == 3500 for r in rises), rises
assert svg.count(">3500<") == len(rises), f"expected {len(rises)} floor-to-floor dims"
overall = round((levels[-1]["elevation"] - levels[0]["elevation"]) * 1000)
assert f"{overall} OVERALL" in svg, overall
assert overall == 3500 * len(rises), (overall, rises)

# ---- grid bubbles come from the in-plane axis, not the cut axis ----------------------------------
# a section on X draws world Y, so it must carry the Y grid's labels
if grid.get("y"):
    labels = {str(lbl) for _, lbl in grid["y"]}
    assert any(f">{lbl}<" in svg for lbl in labels), (labels, "no Y-grid bubble on an X section")
sec_y = drawings.section_drawing_svg(meshes, "y", drawings._axis_center(meshes, 1), levels,
                                     "SECTION B", grid=grid, lod="coarse")
assert "SECTION B" in sec_y and sec_y.count("<polygon") > 0

# ---- the wrapper: annotated by default, bare linework on request ---------------------------------
auto = drawings.section_svg(model, "x")
assert "OVERALL" in auto and "poché" in auto, "section_svg must annotate by default"
bare = drawings.section_svg(model, "x", annotate=False)
assert "<polyline" in bare and "OVERALL" not in bare and "<polygon" not in bare, \
    "annotate=False must return the historical bare linework"

# a cut that misses the model says so instead of emitting an empty drawing that looks finished
miss = drawings.section_svg(model, "x", offset=9999.0)
assert "no geometry" in miss.lower(), miss[:200]

# titles and grid labels are escaped — a model-derived string reaches this SVG
evil = drawings.section_drawing_svg(meshes, "x", offset, levels, 'A & B <script>', grid=grid)
assert "<script>" not in evil and "&amp;" in evil and "&lt;script&gt;" in evil

os.remove(PATH)
print("SECTION-ANNOTATION OK - a section is now issuable rather than merely correct. Cut material is "
      "poché'd and grouped by what it IS (structure heavier than enclosure heavier than openings), "
      "which is the one distinction a pure-linework section cannot make: every edge looks equally "
      "solid. The tone follows LOD — solid while the drawing is about mass, stepped back as the "
      "linework sharpens, absent at 'line' — and the linework is identical across all three, so the "
      "LOD changes weight and never content. C6 reference-line datums run the full width past the "
      "drawing, because a datum references the whole section rather than labelling one element. And "
      "the floor-to-floor chain plus an overall height are on the sheet: those are the numbers a "
      "reader opens a section for, and until now the only way to get one was to measure the screen. "
      "A misspelled LOD is refused rather than defaulted, since a silently-wrong weight produces a "
      "plausible drawing nothing downstream would flag.")
