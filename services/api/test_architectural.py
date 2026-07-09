"""Architectural depth (P3): IfcCovering (ceiling / flooring / cladding, optional finish material)
and IfcRailing recipes.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_architectural.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell                                    # noqa: E402
import ifcopenshell.api                                # noqa: E402
from aec_data import edit                              # noqa: E402
from aec_data.ifc_loader import open_model             # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_arch.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_arch_out.ifc")


def _build() -> str:
    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    ifcopenshell.api.run("context.add_context", m, context_type="Model", context_identifier="Body",
                         target_view="MODEL_VIEW", parent=m.by_type("IfcGeometricRepresentationContext")[0])
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name="L1")
    st.Elevation = 0.0
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=bldg)
    m.write(TMP)
    return TMP


SQUARE = [[0, 0], [4, 0], [4, 4], [0, 4]]
path = _build()

# --- ceiling: hung near the top of the storey (base 0 + 2.7 m) --------------------------------
edit.apply_recipe(path, "add_covering", {"points": SQUARE, "predefined": "CEILING", "thickness": 0.02}, OUT)
m = open_model(OUT)
covs = m.by_type("IfcCovering")
assert len(covs) == 1 and covs[0].PredefinedType == "CEILING", covs
z = covs[0].ObjectPlacement.RelativePlacement.Location.Coordinates[2]
assert abs(z - 2.7) < 1e-6, z                         # ceiling hangs at ~2.7 m

# --- wood flooring: FLOORING with a Wood material --------------------------------------------
edit.apply_recipe(OUT, "add_covering",
                  {"points": SQUARE, "predefined": "FLOORING", "material": "Wood", "thickness": 0.02}, OUT)
m = open_model(OUT)
floors = [c for c in m.by_type("IfcCovering") if c.PredefinedType == "FLOORING"]
assert floors, "flooring covering"
assert any(mat.Name == "Wood" for mat in m.by_type("IfcMaterial")), [x.Name for x in m.by_type("IfcMaterial")]

# --- cladding + railing ----------------------------------------------------------------------
edit.apply_recipe(OUT, "add_covering", {"points": SQUARE, "predefined": "CLADDING"}, OUT)
edit.apply_recipe(OUT, "add_railing", {"start": [0, 0], "end": [4, 0], "height": 1.1}, OUT)
m = open_model(OUT)
assert any(c.PredefinedType == "CLADDING" for c in m.by_type("IfcCovering")), "cladding"
assert len(m.by_type("IfcRailing")) == 1, m.by_type("IfcRailing")

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("ARCHITECTURAL OK - IfcCovering ceiling (hung at 2.7 m) / flooring w/ Wood material / cladding "
      "by PredefinedType; IfcRailing authored between two points.")
