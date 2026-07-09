"""Structural depth (P4): AISC W-shape steel columns/beams (native IfcIShapeProfileDef), straight
rebar (IfcReinforcingBar), and pad footings (IfcFooting) — the edit recipes + the steel table.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_structural.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell                                    # noqa: E402
import ifcopenshell.api                                # noqa: E402
from aec_data import edit, steel                       # noqa: E402
from aec_data.ifc_loader import open_model             # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_struct.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_struct_out.ifc")


def _build() -> str:
    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")   # scale = 1 (as prod)
    ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    ifcopenshell.api.run("context.add_context", m, context_type="Model",
                         context_identifier="Body", target_view="MODEL_VIEW",
                         parent=m.by_type("IfcGeometricRepresentationContext")[0])
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name="L1")
    st.Elevation = 0.0
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=bldg)
    m.write(TMP)
    return TMP


# --- engine: the W-shape table + parametric profile ------------------------------------------
dims = steel.section_dims_m("W14x30")
assert abs(dims["d"] - 13.84 * 0.0254) < 1e-6, dims        # inches -> metres
cat = steel.catalog()
assert {s["section"] for s in cat["w_shapes"]} >= {"W12x26", "W24x76"}, cat["w_shapes"]
assert any(r["size"] == "#5" for r in cat["rebar_sizes"]), cat["rebar_sizes"]
assert abs(steel.rebar_diameter("#8") - 1.0 * 0.0254) < 1e-6, steel.rebar_diameter("#8")

path = _build()

# --- steel column: native IfcIShapeProfileDef named W14x30 -----------------------------------
edit.apply_recipe(path, "add_steel_column", {"point": [0, 0], "height": 3.6, "section": "W14x30"}, OUT)
m = open_model(OUT)
cols = m.by_type("IfcColumn")
assert len(cols) == 1, cols
iprofiles = m.by_type("IfcIShapeProfileDef")
assert iprofiles and iprofiles[0].ProfileName == "W14x30", iprofiles
assert abs(iprofiles[0].OverallDepth - 13.84 * 0.0254) < 1e-6, iprofiles[0].OverallDepth
# section stamped on the column's Pset_ColumnCommon.Reference
refs = [p.NominalValue.wrappedValue for ps in m.by_type("IfcPropertySet") if ps.Name == "Pset_ColumnCommon"
        for p in ps.HasProperties if p.Name == "Reference"]
assert "W14x30" in refs, refs

# --- steel beam ------------------------------------------------------------------------------
edit.apply_recipe(OUT, "add_steel_beam", {"start": [0, 0], "end": [6, 0], "section": "W16x40"}, OUT)
m = open_model(OUT)
assert len(m.by_type("IfcBeam")) == 1, m.by_type("IfcBeam")
assert any(p.ProfileName == "W16x40" for p in m.by_type("IfcIShapeProfileDef")), "W16x40 profile"

# --- rebar: IfcReinforcingBar, #5 nominal diameter, circular section -------------------------
edit.apply_recipe(OUT, "add_rebar", {"start": [0, 0], "end": [1, 0], "size": "#5"}, OUT)
m = open_model(OUT)
bars = m.by_type("IfcReinforcingBar")
assert len(bars) == 1, bars
assert abs(bars[0].NominalDiameter - 0.625 * 0.0254) < 1e-4, bars[0].NominalDiameter
assert m.by_type("IfcCircleProfileDef"), "rebar circular section"

# --- pad footing -----------------------------------------------------------------------------
edit.apply_recipe(OUT, "add_footing", {"point": [0, 0], "width": 1.8, "length": 1.8, "thickness": 0.5}, OUT)
m = open_model(OUT)
assert len(m.by_type("IfcFooting")) == 1, m.by_type("IfcFooting")

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("STRUCTURAL OK - W-shape table (inches->m); steel column authored as native IfcIShapeProfileDef "
      "W14x30 (depth 13.84in) + section stamped on Pset_ColumnCommon; steel beam W16x40; straight "
      "IfcReinforcingBar #5 (nominal dia 0.625in) circular section; IfcFooting pad.")
