"""Incremental element preview (draft perf): build_preview_ifc authors just the recipe's element into
a minimal metre model at the target level's elevation (for a one-element preview fragment).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_preview.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell                                    # noqa: E402
import ifcopenshell.api                                # noqa: E402
from aec_data import preview                           # noqa: E402
from aec_data.ifc_loader import open_model             # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "_pv_src.ifc")
TMP = os.path.join(os.path.dirname(__file__), "_pv_tmp.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_pv_out.ifc")


def _source() -> str:
    """A source model with two storeys L1@0 and L2@4 (metres)."""
    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
    for name, elev in [("L1", 0.0), ("L2", 4.0)]:
        st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name=name)
        st.Elevation = elev
        ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=bldg)
    m.write(SRC)
    return SRC


src = _source()

# preview a steel column on L2 → a minimal model with just that column, storey at 4 m
guid = preview.build_preview_ifc(
    src, "add_steel_column", {"point": [1, 1], "height": 3.0, "section": "W12x26", "storey": "L2"}, OUT, TMP)
assert guid, "preview returned a GUID"

pv = open_model(OUT)
assert len(pv.by_type("IfcColumn")) == 1, pv.by_type("IfcColumn")     # exactly one element
assert len(pv.by_type("IfcBuildingStorey")) == 1, "single storey in the preview model"
st = pv.by_type("IfcBuildingStorey")[0]
assert st.Name == "L2" and abs(st.Elevation - 4.0) < 1e-6, (st.Name, st.Elevation)
assert pv.by_type("IfcIShapeProfileDef"), "steel profile carried into the preview"
assert pv.by_guid(guid).is_a("IfcColumn"), "returned GUID is the authored column"

for f in (SRC, TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("PREVIEW OK - build_preview_ifc authors a one-element metre model (single IfcColumn) at the "
      "target level L2 (4 m) carrying the steel IfcIShapeProfileDef; returns the element GUID. This "
      "is what converts to the fast one-element preview fragment shown while the full model republishes.")
