"""W11 D6 project manual: elements grouped by MasterFormat classification into CSI divisions → sections,
each framed as SectionFormat Part 1/2/3 (Products from types+materials, Execution from attached docs).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_specmanual.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import detailing, edit, massing, specmanual  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_specmanual_test.ifc")
massing.generate_blank_ifc(TMP, name="Spec Manual Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

w1 = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
w2 = edit.add_wall(m, [6, 0], [6, 4], 3.0, 0.2, st)
col = edit.add_column(m, [3, 2], 3.0, 0.4, 0.4, st)

# Track-D: classify into two MasterFormat sections (04 Masonry, 05 Metals) + attach an install doc
detailing.classify(m, [w1, w2], "MasterFormat", "04 20 00", "Unit Masonry")
detailing.classify(m, [col], "MasterFormat", "05 12 00", "Structural Steel Framing")
detailing.attach_document(m, [col], "Steel erection procedure", location="details/steel-erection.pdf")

man = specmanual.project_manual(m)
assert man["section_count"] == 2 and man["division_count"] == 2, man
divs = {d["division"]: d for d in man["divisions"]}
assert "04" in divs and divs["04"]["title"] == "Masonry", divs["04"]
assert "05" in divs and divs["05"]["title"] == "Metals", divs["05"]

# the masonry section carries both walls; each section has the 3 parts
masonry = divs["04"]["sections"][0]
assert masonry["code"] == "04 20 00" and masonry["element_count"] == 2, masonry
assert masonry["part1_general"] and masonry["part2_products"] and masonry["part3_execution"], masonry
# masonry has no attached doc → the manufacturer-instructions fallback
assert any("manufacturer" in e.lower() for e in masonry["part3_execution"]), masonry["part3_execution"]

# the metals section's Part 3 Execution pulls the attached install document
metals = divs["05"]["sections"][0]
assert any("erection" in e.lower() for e in metals["part3_execution"]), metals["part3_execution"]

# divisions come out CSI-ordered (04 before 05)
assert [d["division"] for d in man["divisions"]] == ["04", "05"], man["divisions"]

# regression: a wall carrying a material LAYER SET (via a type) must surface its layer materials in
# Part 2 Products (the IfcMaterialLayerSetUsage case previously yielded nothing).
from aec_data import families  # noqa: E402

tg = families.create_type(m, "IfcWallType", "CMU-8")
families.assign_material_set(m, tg, [{"material": "Concrete Masonry Unit", "thickness": 0.19},
                                     {"material": "Rigid Insulation", "thickness": 0.05}])
wt = edit.place_type(m, tg, st, position=[0, 8])
detailing.classify(m, [wt], "MasterFormat", "04 22 00", "Concrete Unit Masonry")
man2 = specmanual.project_manual(m)
sec_0422 = next(s for d in man2["divisions"] for s in d["sections"] if s["code"] == "04 22 00")
prods = " ".join(sec_0422["part2_products"])
assert "Concrete Masonry Unit" in prods and "Rigid Insulation" in prods, sec_0422["part2_products"]

# text rendering
txt = specmanual.manual_text(m, project="Spec Manual Test")
assert "PROJECT MANUAL" in txt and "DIVISION 04 — MASONRY" in txt and "SECTION 05 12 00" in txt, txt
assert "PART 1 - GENERAL" in txt and "PART 3 - EXECUTION" in txt, txt

# empty model → a valid, empty manual (no crash)
empty = specmanual.project_manual(open_model(TMP))  # freshly reopened, unclassified copy is fine
assert "divisions" in empty and "note" in empty

if os.path.exists(TMP):
    os.remove(TMP)

print("SPEC MANUAL OK - project_manual groups elements by MasterFormat into CSI divisions (04 Masonry / "
      "05 Metals) → sections with SectionFormat Part 1/2/3; Part 3 Execution pulls attached install docs "
      "(steel erection) or falls back to manufacturer instructions; CSI-ordered; manual_text renders the outline.")
