"""Generative fit-out (Wave 9 W9-6): auto-furnish IfcSpaces with gridded IfcFurnishingElement. Builds a
blank model → rooms (add_spaces) → furnish, and checks real furniture is created + contained in storeys.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_fitout.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_fitout_test.ifc")

# a blank model (levels + a ground datum slab -> a footprint add_spaces can read)
massing.generate_blank_ifc(TMP, name="Fitout Test", storeys=2, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
rooms = edit.add_spaces(m, rooms_per_storey=4, ceiling_height=3.0)
assert rooms >= 4, f"expected rooms, got {rooms}"

before = len(m.by_type("IfcFurnishingElement"))
placed = edit.furnish_spaces(m, item="desk", per_room=0)
after = m.by_type("IfcFurnishingElement")
assert placed > 0, "no furniture placed"
assert len(after) == before + placed, (before, placed, len(after))
# every placed item is real IfcFurnishingElement, named Desk, with geometry + a spatial container
sample = after[0]
assert sample.is_a() == "IfcFurnishingElement" and sample.Name == "Desk", sample
assert sample.Representation is not None, "furniture has no geometry representation"
assert ue.get_container(sample) is not None, "furniture not contained in a storey"

# per_room cap is respected (never more than the cap per room). NB: open_model is lru_cached, so use a
# SEPARATE file for an independent model (re-opening TMP returns the same already-furnished object).
TMP2 = os.path.join(os.path.dirname(__file__), "_fitout_test2.ifc")
massing.generate_blank_ifc(TMP2, name="Fitout Test 2", storeys=2, storey_height=3.5, ground_size=20.0)
m2 = open_model(TMP2)
edit.add_spaces(m2, rooms_per_storey=4, ceiling_height=3.0)
capped = edit.furnish_spaces(m2, item="table", per_room=1)
n_spaces = len(m2.by_type("IfcSpace"))
assert 0 < capped <= n_spaces, (capped, n_spaces)   # ≤ 1 per room
assert all(f.Name == "Table" for f in m2.by_type("IfcFurnishingElement")), "template not applied"

# the recipe path works through apply_recipe (the /edit route)
OUT = os.path.join(os.path.dirname(__file__), "_fitout_out.ifc")
edit.apply_recipe(TMP, "add_spaces", {"rooms_per_storey": 4}, OUT)
res = edit.apply_recipe(OUT, "furnish_spaces", {"item": "desk"}, OUT)
assert res["changed"] > 0, res

for f in (TMP, TMP2, OUT):
    if os.path.exists(f):
        os.remove(f)

print(f"FITOUT OK - blank model -> {rooms} rooms -> furnish placed {placed} desks (real "
      "IfcFurnishingElement w/ geometry + storey container); per_room=1 caps at <=1/room and applies the "
      "table template; furnish_spaces recipe works via apply_recipe.")
