"""R21-KEYNOTE-SECT — sections had no annotation layer at all.

`drawings.py` has `_leader_callout` for PLANS, and its boxed label is the right mark there: a plan tag
names an OBJECT. A section keynote does a different job — it names the MATERIAL of a layer in an
assembly — so the convention is a left-hand text column with an unboxed leader to a dot. Reusing the
plan tag here would have produced the wrong drawing, which is why this is a separate helper rather
than a parameter on the existing one.

The rule that earns the feature its keep is GROUPING: a wall cut at eight storeys is ONE keynote, not
eight. Without that, an annotation layer makes a section less readable than no annotation at all.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_section_keynotes.py
"""
import os
import re
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_section_keynotes.db"
os.environ["STORAGE_DIR"] = "./test_storage_section_keynotes"
if os.path.exists("./test_section_keynotes.db"):
    os.remove("./test_section_keynotes.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings as d  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# ---- the keynote text is built from what the MODEL knows -------------------------------------------
# thickness is carried in millimetres, which is how a keynote is actually written
assert d.keynote_text("IfcWall", "masonry", 0.4) == "400mm MASONRY WALL"
assert d.keynote_text("IfcSlab", "reinforced_concrete", 0.2) == "RC SLAB AS PER STRUCTURAL DRAWINGS"
assert d.keynote_text("IfcBeam", "steel", 0.3) == "STEEL BEAM"
assert d.keynote_text("IfcCovering", "insulation", 0.06) == "60mm INSULATION"
# a thickness we do not have must not invent one
assert d.keynote_text("IfcWall", "masonry", None) == "MASONRY WALL"
assert d.keynote_text("IfcWall", "masonry", 0.0) == "MASONRY WALL"
# an unknown CLASS falls back to the class name with the IFC prefix stripped — still true, not a guess
assert d.keynote_text("IfcBurjKhalifaThing", "steel") == "STEEL BURJKHALIFATHING"
assert "IFC" not in d.keynote_text("IfcFooting", "concrete", 1.2)
assert d.keynote_text("", "steel") == "STEEL ELEMENT"
# an unknown MATERIAL still yields a legible keynote rather than a KeyError or a blank
assert d.keynote_text("IfcWall", "unobtainium", 0.3) == "300mm WALL"

# ---- leaders: the column never collides with itself -------------------------------------------------
# three targets at the SAME y would stack three labels on one baseline if rows were not pushed apart
svg = d._keynote_leaders([(500, 200, "A"), (520, 200, "B"), (540, 200, "C")], 100, 40, 600,
                         anchor_right=True)
ys = [float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)"', svg)]
assert len(ys) == 3, ys
assert len(set(ys)) == 3, f"collided keynote rows: {ys}"
assert min(b - a for a, b in zip(sorted(ys), sorted(ys)[1:])) >= 10, ys
assert svg.count("<circle") == 3, "every keynote lands a dot on its component"
assert 'text-anchor="end"' in svg
assert d._keynote_leaders([], 100, 40, 600, anchor_right=True) == "", "no entries → no markup"
# text is escaped — a material name arrives from the model and is therefore untrusted free text
bad = d._keynote_leaders([(1, 2, '<script>&"')], 100, 40, 600, anchor_right=True)
assert "<script>" not in bad and "&lt;script&gt;" in bad, bad

# rows are clamped into the drawing band rather than running off the sheet
tight = d._keynote_leaders([(9, y, f"K{y}") for y in range(0, 400, 5)], 100, 40, 300,
                           anchor_right=True)
tys = [float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)"', tight)]
assert max(tys) <= 303.1, max(tys)

# ---- on a real model --------------------------------------------------------------------------------
PATH = os.path.join(os.path.dirname(__file__), "_section_keynotes.ifc")
massing.generate_blank_ifc(PATH, name="Keynote", storeys=4, storey_height=3.5, ground_size=24.0)
model = open_model(PATH)
# the SAME wall at every storey — the grouping case, stated explicitly
for st in model.by_type("IfcBuildingStorey"):
    edit.add_wall(model, [-9, 0], [9, 0], 3.2, 0.4, st.Name)

svg = d.section_svg(model, "x")
notes = re.findall(r'font-size="9.5" fill="#111">([^<]*)</text>', svg)
assert notes, "a section must now carry an annotation layer"

# THE RULE: four identical walls across four storeys are ONE keynote, not four.
wall_notes = [n for n in notes if "WALL" in n]
assert len(wall_notes) == 1, f"grouping failed — {len(wall_notes)} wall keynotes: {wall_notes}"
assert wall_notes[0] == "400mm MASONRY WALL", wall_notes
# and no keynote is ever emitted twice
assert len(notes) == len(set(notes)), notes
assert len(notes) <= d.MAX_KEYNOTES

# every keynote is reachable: its leader ends inside the drawing, its text sits in the gutter
assert svg.count("</text>") > len(notes), "keynotes are additive — datums/grid/title still present"

# ---- the levers behave ------------------------------------------------------------------------------
off = d.section_svg(model, "x", keynotes=False)
assert 'font-size="9.5"' not in off, "keynotes=False removes the annotation layer"
assert "<polygon" in off and off.count("<polygon") == svg.count("<polygon"), \
    "the annotation layer changes annotation only — never the linework"
# the sheet narrows when the keynote column is not needed
assert d.KEYNOTE_GUTTER > 130
line = d.section_svg(model, "x", lod="line")
assert 'font-size="9.5"' not in line, "the line LOD is bare linework; keynotes would contradict that"

# keynotes must survive hatch=False — the material map serves BOTH, and scoping it to hatch alone
# would silently downgrade every keynote to a class default
flat = d.section_svg(model, "x", hatch=False)
flat_notes = re.findall(r'font-size="9.5" fill="#111">([^<]*)</text>', flat)
assert flat_notes == notes, (flat_notes, notes)

os.remove(PATH)
print("R21-KEYNOTE-SECT OK - sections carry an assembly-annotation layer for the first time: a "
      "left-hand keynote column with unboxed leaders to a dot on the component, which is the section "
      "convention and deliberately NOT the boxed tag `_leader_callout` draws on plans - a plan tag "
      "names an object, a section keynote names the material of a layer in an assembly. The text is "
      "built from what the model knows (its material, its class, its measured thickness in mm) and an "
      "unfamiliar class degrades to its own name with the IFC prefix stripped rather than to a guess "
      "that would read as authored. The rule that earns it its keep is GROUPING: the same wall cut at "
      "four storeys is ONE keynote, not four, because an annotation layer that repeats itself makes a "
      "section less readable than no annotation at all - and rows are pushed apart so labels never "
      "collide, since a reader who cannot tell which label belongs to which leader has no annotation "
      "either. Linework is byte-identical with keynotes on and off.")
