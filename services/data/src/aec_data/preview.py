"""Incremental element preview (draft performance).

Authoring an element normally reconverts the *whole* model to a fragment — fine for correctness, slow
for live drafting. This builds a **minimal one-element IFC**: a metre model with a single storey at the
target level's elevation, with just the new element authored into it via the same recipe. Converting
that (one element) is fast, so the viewer can show real geometry immediately while the full model
republishes in the background. World coordinates match the full model (same XY + level elevation).
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api

from . import edit
from .drawings import storey_elevations


def build_preview_ifc(source_ifc_path: str, recipe: str, params: dict,
                      out_ifc: str, tmp_ifc: str) -> str:
    """Author the recipe's element into a minimal metre model (single storey at the target level's
    elevation) and write it to `out_ifc`. Returns the new element's GUID."""
    src = ifcopenshell.open(source_ifc_path)
    levels = storey_elevations(src)                   # metres
    sname = params.get("storey")
    elev = 0.0
    if sname:
        lv = next((x for x in levels if x["name"] == sname), None)
        if lv:
            elev = float(lv["elevation"])
    elif levels:
        elev = float(levels[0]["elevation"])

    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="Preview")
    metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    ifcopenshell.api.run("context.add_context", m, context_type="Model", context_identifier="Body",
                         target_view="MODEL_VIEW",
                         parent=m.by_type("IfcGeometricRepresentationContext")[0])
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name=sname or "Level")
    st.Elevation = float(elev)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=bldg)
    m.write(tmp_ifc)

    pv = {k: v for k, v in params.items() if k != "storey"}   # one storey in the preview model
    return edit.apply_recipe(tmp_ifc, recipe, pv, out_ifc)["changed"]
