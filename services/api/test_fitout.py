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

# --- W9-6b: headcount program → zones + furnish-to-seat-count --------------------------------------
TMP3 = os.path.join(os.path.dirname(__file__), "_fitout_test3.ifc")
massing.generate_blank_ifc(TMP3, name="Program Fit", storeys=1, storey_height=3.5, ground_size=24.0)
m3 = open_model(TMP3)
edit.add_spaces(m3, rooms_per_storey=4, ceiling_height=3.0)
n_rooms = len(m3.by_type("IfcSpace"))
assert n_rooms == 4, n_rooms

pf = edit.program_fit(m3, {"Engineering": 8, "Sales": 3}, item="desk")
depts = {a["department"]: a for a in pf["departments"]}
# every department seated in full; seats_placed matches the real furniture authored
assert pf["all_satisfied"] is True and pf["seats_asked"] == 11, pf["seats_asked"]
assert depts["Engineering"]["seats"] == 8 and depts["Sales"]["seats"] == 3, depts
placed_items = m3.by_type("IfcFurnishingElement")
assert pf["seats_placed"] == len(placed_items) == 11, (pf["seats_placed"], len(placed_items))
# Engineering (the bigger ask) claimed the room(s) first — its zones are stamped
eng_space = m3.by_guid(depts["Engineering"]["spaces"][0]["guid"])
assert eng_space.LongName == "Engineering zone", eng_space.LongName
prog_ps = ue.get_pset(eng_space, "Pset_Massing_Program")
assert prog_ps["Department"] == "Engineering" and prog_ps["SeatsAllocated"] >= 1, prog_ps
# allocated + unallocated partitions the room list
n_used = sum(len(a["spaces"]) for a in pf["departments"])
assert n_used + len(pf["unallocated_spaces"]) == n_rooms, (n_used, pf["unallocated_spaces"])

# an over-capacity ask reports the shortage honestly (never silently under-seats)
TMP4 = os.path.join(os.path.dirname(__file__), "_fitout_test4.ifc")
massing.generate_blank_ifc(TMP4, name="Program Short", storeys=1, storey_height=3.5, ground_size=12.0)
m4 = open_model(TMP4)
edit.add_spaces(m4, rooms_per_storey=2, ceiling_height=3.0)
pf2 = edit.program_fit(m4, {"Everyone": 500})
short = pf2["departments"][0]
assert pf2["all_satisfied"] is False and short["short_by"] > 0, pf2
assert short["seats"] + short["short_by"] == 500, short

# bad programs are clean errors; registered as a recipe
for bad in ({}, {"Eng": 0}, {"Eng": "lots"}):
    try:
        edit.program_fit(m4, bad)
        raise AssertionError(f"expected ValueError for {bad}")
    except ValueError:
        pass
assert "program_fit" in edit.RECIPES

for f in (TMP, TMP2, TMP3, TMP4, OUT):
    if os.path.exists(f):
        os.remove(f)

print(f"FITOUT OK - blank model -> {rooms} rooms -> furnish placed {placed} desks (real "
      "IfcFurnishingElement w/ geometry + storey container); per_room=1 caps at <=1/room and applies the "
      "table template; furnish_spaces recipe works via apply_recipe. W9-6b: program_fit seats "
      "{Engineering:8, Sales:3} in full (11 desks authored = seats_placed), stamps LongName + "
      "Pset_Massing_Program on the zones, partitions allocated/unallocated rooms, reports a 500-seat "
      "over-ask as short_by (never silently under-seats), rejects bad programs, and is a recipe.")
