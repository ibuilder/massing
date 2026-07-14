"""Semantic model graph (Wave 9 W9-4): build a typed graph from IFC relationships (contained_in /
aggregates) and traverse a node's neighborhood with cited GUID paths. Pure data-service engine test.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_graph.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402

from aec_data import graph  # noqa: E402

# project ▸ building ▸ storey (aggregates); a wall + a column contained in the storey (contained_in)
m = ifcopenshell.api.run("project.create_file")
proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="Graph Test")
bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="Building A")
storey = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name="Level 1")
wall = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcWall", name="W1")
col = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcColumn", name="C1")
ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=proj)
ifcopenshell.api.run("aggregate.assign_object", m, products=[storey], relating_object=bldg)
ifcopenshell.api.run("spatial.assign_container", m, products=[wall, col], relating_structure=storey)

g = graph.build(m)
assert g["nodes"] == 5, g                                  # proj, bldg, storey, wall, col
assert g["by_rel"].get("aggregates") == 2, g               # proj→bldg, bldg→storey
assert g["by_rel"].get("contained_in") == 2, g             # wall→storey, col→storey
assert g["edges"] == 4, g

# neighbors of the wall at depth 1 -> reaches the storey via contained_in
n1 = graph.neighbors(m, wall.GlobalId, depth=1)
assert n1["found"] and n1["neighbor_count"] == 1, n1
reached = n1["paths"][0]
assert reached["name"] == "Level 1" and reached["class"] == "IfcBuildingStorey", reached
assert reached["path"][-1]["rel"] == "contained_in", reached["path"]

# depth 2 from the wall -> storey (contained_in) then building (aggregates) + the sibling column
n2 = graph.neighbors(m, wall.GlobalId, depth=2)
names = {p["name"] for p in n2["paths"]}
assert "Building A" in names and "C1" in names, names        # multi-hop: reaches building + sibling
bldg_path = next(p for p in n2["paths"] if p["name"] == "Building A")
assert [s["rel"] for s in bldg_path["path"]] == ["contained_in", "aggregates"], bldg_path["path"]

# an unknown guid returns a clean not-found
assert graph.neighbors(m, "does-not-exist", 1)["found"] is False

print("GRAPH OK - built 5 nodes / 4 edges from IfcRelAggregates (2) + IfcRelContainedInSpatialStructure "
      "(2); wall->storey at depth 1 (cited contained_in); depth-2 reaches Building A via "
      "[contained_in, aggregates] + the sibling column; unknown guid -> not found.")
