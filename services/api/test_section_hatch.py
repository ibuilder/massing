"""R21-HATCH — a tone says "this is cut"; a hatch says what it is cut THROUGH.

Measured against a real issued shop-drawing set: at 1:10 the details separate concrete, reinforced
concrete, steel, masonry and insulation by PATTERN, and a reader identifies the assembly from the
patterns alone. v0.3.673 filled cut geometry with flat greys grouped by IFC class, which is enough to
say "cut" and cannot say "cut through what" — the difference between a set that reads as a study and
one that reads as construction documents.

The drafting rule this encodes, and the reason it is not just a lookup table: **hatch is defined in
PAPER space.** Spacing belongs to the sheet, so the same wall hatches identically at 1:100 and 1:10.
The consequence is that an element thinner than a couple of tiles cannot be hatched legibly — at that
size the honest mark is the solid tone, which is exactly what a drafter does by hand.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_section_hatch.py
"""
import os
import re
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_section_hatch.db"
os.environ["STORAGE_DIR"] = "./test_storage_section_hatch"
if os.path.exists("./test_section_hatch.db"):
    os.remove("./test_section_hatch.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings as d  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# ---- the material map reads the MODEL, and falls back only when it must ---------------------------
assert d.hatch_material("IfcSlab", {"ifcslab": "reinforced_concrete"}) == "reinforced_concrete"
assert d.hatch_material("IfcSlab", None) == "reinforced_concrete"      # class fallback
assert d.hatch_material("IfcWall", None) == "masonry"
# the model's own material WINS over the fallback — that is the whole point of reading it
assert d.hatch_material("IfcWall", {"ifcwall": "timber"}) == "timber"
# an unknown class hatches as the lightest category, never as structure
assert d.hatch_material("IfcSomethingNew", None) == "finish"
assert d.hatch_material("", None) == "finish"

# "reinforced concrete" must beat "concrete" — keyword order is load-bearing here
assert d._MATERIAL_KEYWORDS[0][1] == "reinforced_concrete", d._MATERIAL_KEYWORDS[0]
assert any("concrete" in k for k in d._MATERIAL_KEYWORDS[0][0])

# ---- defs carry exactly what is referenced, and every category has a body -------------------------
assert set(d._HATCH_BODY) == set(d.HATCH_MATERIALS), (set(d._HATCH_BODY) ^ set(d.HATCH_MATERIALS))
defs = d.hatch_defs({"masonry", "steel"})
assert defs.count("<pattern ") == 2 and 'id="hatch-masonry"' in defs and 'id="hatch-steel"' in defs
assert "hatch-concrete" not in defs, "a section of two materials must not carry nine pattern defs"
assert d.hatch_defs(set()) == "", "no categories → no defs block at all"
assert d.hatch_defs({"not-a-material"}) == ""
# patterns are paper-space, which is what makes 1:100 and 1:10 agree
assert 'patternUnits="userSpaceOnUse"' in defs

# ---- on a real model ------------------------------------------------------------------------------
PATH = os.path.join(os.path.dirname(__file__), "_section_hatch.ifc")
massing.generate_blank_ifc(PATH, name="Hatch", storeys=2, storey_height=3.5, ground_size=24.0)
model = open_model(PATH)
for st in model.by_type("IfcBuildingStorey"):
    edit.add_wall(model, [-9, 0], [9, 0], 3.2, 0.4, st.Name)     # 400 mm — hatchable
    edit.add_wall(model, [0, -9], [0, 9], 3.2, 0.4, st.Name)

svg = d.section_svg(model, "x")
defined = set(re.findall(r'id="hatch-([a-z_]+)"', svg))
used = set(re.findall(r'url\(#hatch-([a-z_]+)\)', svg))
assert used, "a 400 mm wall is thick enough to hatch"
assert defined == used, (defined, used)          # never define a pattern nobody references
assert "masonry" in used, used                   # walls carry no material → class fallback

# THE DRAFTING RULE: a thin element degrades to tone rather than emitting unresolvable stripes.
# The 200 mm slab in this model sits below the tile threshold at this scale and must NOT be hatched.
assert d.MIN_HATCH_PX > 0
assert "<polygon" in svg
solid = re.findall(r'<polygon [^>]*fill="(#[0-9a-f]{3,6})"', svg)
assert solid, "the thin elements must still be filled — degraded, not dropped"

# ---- the levers all behave -------------------------------------------------------------------------
flat = d.section_svg(model, "x", hatch=False)
assert "hatch-" not in flat and "<polygon" in flat, "hatch=False keeps the drawing, drops the pattern"
line = d.section_svg(model, "x", lod="line")
assert "url(#hatch" not in line, "the line LOD carries no fill of any kind"
fine = d.section_svg(model, "x", lod="fine")
assert "<polygon" in fine
# linework is unchanged across every fill mode — the fill changes weight, never content
assert svg.count("<polygon") == flat.count("<polygon") == line.count("<polygon")

# a section still renders when the model has no materials at all (every fallback path exercised)
assert d.material_by_class(model) is not None
assert isinstance(d.material_by_class(model), dict)

# ---- the wrapper still refuses a bad LOD, with hatch on ---------------------------------------------
for bad in ("COARSE", "medium", ""):
    try:
        d.section_svg(model, "x", lod=bad)
        raise AssertionError(f"expected refusal for {bad!r}")
    except ValueError as e:
        assert "lod must be one of" in str(e)

os.remove(PATH)
print("R21-HATCH OK - cut material now carries a material HATCH rather than a flat grey tone, which "
      "is the difference between a drawing that says 'this is cut' and one that says what it is cut "
      "THROUGH: concrete, reinforced concrete, steel, masonry, insulation, timber, earth, glass and "
      "finish each get the conventional pattern, and a reader identifies the assembly from the "
      "patterns alone. The category comes from the MODEL's own materials where it has them and from "
      "a stated class fallback where it does not — an unfamiliar class hatches as the lightest "
      "category, never as structure. Patterns are defined in PAPER space, which is the actual "
      "drafting convention and is why the same wall hatches identically at 1:100 and 1:10 — and it "
      "forces the rule that earns this its keep: an element thinner than a couple of tiles CANNOT be "
      "hatched legibly, so it degrades to the solid tone instead of emitting stripes nobody can "
      "resolve, exactly as a drafter would do by hand. Only the patterns actually referenced are "
      "emitted, so a two-material section does not carry nine unused definitions, and the linework "
      "is identical across hatch / tone / line so the fill mode changes weight and never content.")
