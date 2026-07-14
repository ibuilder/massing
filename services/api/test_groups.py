"""W10-3 groups / assemblies / arrays: build a blank model, place a few family occurrences, then group
them (IfcGroup), aggregate a subset into an IfcElementAssembly (part-of whole), and rectangular-array an
element. Verifies the IFC relationships + the list/detail inspectors + the recipe path.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_groups.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, families, groups, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_groups_test.ifc")
massing.generate_blank_ifc(TMP, name="Groups Test", storeys=1, storey_height=3.5, ground_size=30.0)
m = open_model(TMP)
storey = m.by_type("IfcBuildingStorey")[0].Name

# place four column occurrences to organise
tg = families.create_type(m, "IfcColumnType", "COL 400", dims=[0.4, 0.4, 3.5])
cols = [edit.place_type(m, tg, storey, [float(x), 0.0]) for x in (0, 3, 6, 9)]
assert all(cols), cols

# --- group: a named set (IfcGroup + IfcRelAssignsToGroup) -----------------------------------------
g = groups.create_group(m, "West grid line", cols)
assert g["members"] == 4, g
grp = m.by_guid(g["guid"])
assert grp.is_a("IfcGroup") and not grp.is_a("IfcSystem"), grp
# members carry the assignment inverse
assert ue.get_container(m.by_guid(cols[0])) is not None, "grouping must not remove spatial containment"

# re-using the name adds to the same group, not a new one
g2 = groups.create_group(m, "West grid line", [])
assert g2["guid"] == g["guid"], (g2, g)
assert sum(1 for x in m.by_type("IfcGroup") if x.Name == "West grid line") == 1

# --- assembly: a real part-of whole (IfcElementAssembly + IfcRelAggregates) -----------------------
asm = groups.create_assembly(m, "Braced frame A", cols[:2], predefined="RIGID_FRAME")
assert asm["parts"] == 2, asm
a = m.by_guid(asm["guid"])
assert a.is_a("IfcElementAssembly"), a
kids = [o for rel in (a.IsDecomposedBy or []) for o in rel.RelatedObjects]
assert {k.GlobalId for k in kids} == set(cols[:2]), kids
# the assembly itself is placed in the spatial tree
assert ue.get_container(a) is not None, "assembly not contained in a storey"

# --- array: rectangular parametric duplication ---------------------------------------------------
before = len(m.by_type("IfcColumn"))
arr = groups.array_element(m, cols[3], nx=3, ny=2, dx=1.5, dy=1.5)
assert arr["count"] == 3 * 2 - 1 == 5, arr                 # nx*ny minus the original cell (0,0)
assert len(m.by_type("IfcColumn")) == before + 5, (before, len(m.by_type("IfcColumn")))

# --- inspectors ----------------------------------------------------------------------------------
lst = groups.list_groups(m)
assert any(x["name"] == "West grid line" and x["members"] == 4 for x in lst["groups"]), lst["groups"]
assert any(x["name"] == "Braced frame A" and x["parts"] == 2 for x in lst["assemblies"]), lst["assemblies"]
det = groups.group_detail(m, g["guid"])
assert det["kind"] == "group" and det["member_count"] == 4, det
detA = groups.group_detail(m, asm["guid"])
assert detA["kind"] == "assembly" and detA["member_count"] == 2, detA

# --- ungroup dissolves the set (members untouched) -----------------------------------------------
n_cols_before = len(m.by_type("IfcColumn"))
r = groups.ungroup(m, g["guid"])
assert r["removed"] == 1 and not [x for x in m.by_type("IfcGroup") if x.GlobalId == g["guid"]]
assert len(m.by_type("IfcColumn")) == n_cols_before, "ungroup must not delete members"

# --- recipe path (the /edit route) ---------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_groups_out.ifc")
tg2 = families.create_type(m, "IfcFurnitureType", "Chair X", dims=[0.5, 0.5, 0.9])
seat = edit.place_type(m, tg2, storey, [20.0, 20.0])
m.write(TMP)                                               # persist the seat so the recipe file has it
rg = edit.apply_recipe(TMP, "create_group", {"name": "Seating", "guids": [seat]}, OUT)
assert isinstance(rg["changed"], dict) and rg["changed"]["members"] == 1, rg
ra = edit.apply_recipe(OUT, "array_element", {"guid": seat, "nx": 4, "ny": 1, "dx": 0.6}, OUT)
assert ra["changed"]["count"] == 3, ra

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("GROUPS OK - create_group (IfcGroup named set, re-name adds, members keep containment) -> "
      "create_assembly (IfcElementAssembly aggregating parts, spatially contained) -> array_element "
      "(3x2 rectangular array = 5 copies) -> list/detail inspectors -> ungroup (dissolves set, keeps "
      "members); create_group + array_element recipes work through apply_recipe.")
