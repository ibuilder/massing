"""Shared IFC-authoring scaffold — the boilerplate every generator repeats.

Before this module, the project/site/building bootstrap was cloned in four places
(`massing.generate_ifc`, `massing.generate_blank_ifc`, `massing.generate_dome_ifc`,
`plan_to_bim.raise_plan`) and the Position-carrying rectangle profile in three. A clone of
load-bearing setup is how unit-scale and web-ifc regressions sneak in one call site at a time —
fix it here once and every generator inherits it.
"""
from __future__ import annotations

from typing import Any


def rect_profile(model: Any, w: float, d: float) -> Any:
    """An ``IfcRectangleProfileDef`` **with a Position**. web-ifc REQUIRES ``IfcProfileDef.Position``
    (ifcopenshell tolerates None, web-ifc skips the element silently → empty .frag), so always set
    an origin placement. Dimensions are clamped to ≥ 1 mm so a degenerate input can't emit a
    zero-area profile."""
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    return model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                               XDim=max(float(w), 1e-3), YDim=max(float(d), 1e-3))


def new_project(name: str) -> tuple[Any, Any, Any, Any]:
    """A minimal valid IFC4 authoring spine: project + Model/Body contexts + site + building,
    aggregated project → site → building. Returns ``(model, body, site, building)``.

    The METRE length unit is load-bearing: all generator geometry/placements are written in metres,
    and the ifcopenshell default (MILLIMETRE) silently shrinks a model 1000× (renders empty)."""
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=name)
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model",
                                context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    return model, body, site, building
