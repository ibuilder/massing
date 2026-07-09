"""Grid + levels drafting refs (P1): the grid reader (derived from IfcColumn centres) + the
editable-storey recipes (add / rename / move). Pure data-service engine test — no converter.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_grid.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell                                    # noqa: E402
import ifcopenshell.api                                # noqa: E402
import numpy as np                                     # noqa: E402
from aec_data import edit, grid                        # noqa: E402
from aec_data.ifc_loader import open_model             # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_grid_test.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_grid_test_out.ifc")


def _run(model, fn, **kw):
    return ifcopenshell.api.run(fn, model, **kw)


def _build_model() -> str:
    """A minimal metric model: project → site → building → 1 storey + 4 columns on a 6 m × 6 m grid."""
    m = _run(None, "project.create_file") if False else ifcopenshell.api.run("project.create_file")
    proj = _run(m, "root.create_entity", ifc_class="IfcProject", name="P")
    _run(m, "unit.assign_unit")                        # metric (metres) by default
    _run(m, "context.add_context", context_type="Model")
    site = _run(m, "root.create_entity", ifc_class="IfcSite", name="Site")
    bldg = _run(m, "root.create_entity", ifc_class="IfcBuilding", name="Building")
    storey = _run(m, "root.create_entity", ifc_class="IfcBuildingStorey", name="Level 1")
    storey.Elevation = 0.0
    _run(m, "aggregate.assign_object", products=[site], relating_object=proj)
    _run(m, "aggregate.assign_object", products=[bldg], relating_object=site)
    _run(m, "aggregate.assign_object", products=[storey], relating_object=bldg)
    for x, y in [(0.0, 0.0), (6.0, 0.0), (0.0, 6.0), (6.0, 6.0)]:
        col = _run(m, "root.create_entity", ifc_class="IfcColumn", name=f"C{x}-{y}")
        mat = np.array([[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        _run(m, "geometry.edit_object_placement", product=col, matrix=mat)
        _run(m, "spatial.assign_container", products=[col], relating_structure=storey)
    m.write(TMP)
    return TMP


path = _build_model()
model = open_model(path)

# --- grid derived from the 4 columns: 2 X-lines (1,2) + 2 Y-lines (A,B) + 4 intersections ---
gl = grid.grid_and_levels(model)
g = gl["grid"]
assert g["source"] == "derived", g["source"]
tags = sorted(a["tag"] for a in g["axes"])
assert tags == ["1", "2", "A", "B"], tags
assert len(g["intersections"]) == 4, g["intersections"]
labels = sorted(i["label"] for i in g["intersections"])
assert labels == ["A-1", "A-2", "B-1", "B-2"], labels
# a snap point sits on a real column (0,0) and (6,6)
pts = {(round(i["x"], 2), round(i["y"], 2)) for i in g["intersections"]}
assert (0.0, 0.0) in pts and (6.0, 6.0) in pts, pts
# levels present
assert [lv["name"] for lv in gl["levels"]] == ["Level 1"], gl["levels"]

# --- editable storeys: add / rename / move (metres) -----------------------------------------
r = edit.apply_recipe(path, "add_storey", {"name": "Level 2", "elevation": 4.0}, OUT)
m2 = open_model(OUT)
lv2 = grid.grid_and_levels(m2)["levels"]
assert [lv["name"] for lv in lv2] == ["Level 1", "Level 2"], lv2
assert abs(lv2[1]["elevation"] - 4.0) < 1e-6, lv2[1]     # metres

new_guid = r["changed"]
edit.apply_recipe(OUT, "set_storey_elevation", {"guid": new_guid, "elevation": 7.5}, OUT)
edit.apply_recipe(OUT, "rename_storey", {"guid": new_guid, "name": "Roof"}, OUT)
m3 = open_model(OUT)
roof = [lv for lv in grid.grid_and_levels(m3)["levels"] if lv["name"] == "Roof"]
assert roof and abs(roof[0]["elevation"] - 7.5) < 1e-6, grid.grid_and_levels(m3)["levels"]

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("GRID OK - derived grid from 4 columns -> axes 1/2/A/B + 4 intersections (A-1..B-2) snapping "
      "to column centres; levels read from IfcBuildingStorey; add_storey (Level 2 @ 4 m) + "
      "set_storey_elevation (7.5 m) + rename_storey (Roof) recipes author real IFC.")
