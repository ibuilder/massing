"""Safe, high-value edit *recipes* for the desktop editor (guide §9).

These are small, reviewable IfcOpenShell operations that Bonsai-MCP can run against the live
IFC in Blender — preferred over free-form `execute_blender_code`. Each recipe is a pure
function over an `ifcopenshell.file`; the MCP layer is responsible for saving first and
chunking large selections (see bonsai-mcp.config.json).

These are reference implementations: they use the same ifcopenshell API available inside
Bonsai, so they can be pasted into an MCP `execute` call or imported by a thin add-on.
"""
from __future__ import annotations

from collections.abc import Iterable

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element as ue


def place_type(model: ifcopenshell.file, type_guid: str, storey_name: str,
               location: tuple[float, float, float]) -> ifcopenshell.entity_instance:
    """Instantiate an occurrence of an IFC type ("family") at a point on a storey."""
    el_type = next((t for t in model.by_type("IfcTypeProduct") if t.GlobalId == type_guid), None)
    if el_type is None:
        raise ValueError(f"type {type_guid} not found")
    storey = next((s for s in model.by_type("IfcBuildingStorey") if s.Name == storey_name), None)
    if storey is None:
        raise ValueError(f"storey {storey_name!r} not found")

    occurrence_class = el_type.is_a().replace("Type", "")  # IfcWallType -> IfcWall
    element = ifcopenshell.api.run("root.create_entity", model, ifc_class=occurrence_class)
    ifcopenshell.api.run("type.assign_type", model, related_objects=[element], relating_type=el_type)
    ifcopenshell.api.run("spatial.assign_container", model,
                         products=[element], relating_structure=storey)
    # caller sets placement geometry; location recorded for the MCP to position the object
    element.Description = f"placed@{location}"
    return element


def set_pset_value(model: ifcopenshell.file, elements: Iterable, pset_name: str,
                   prop_name: str, value) -> int:
    """Set a single Pset property on many elements (e.g. fire rating on all L3 walls)."""
    count = 0
    for el in elements:
        pset = ue.get_pset(el, pset_name, prop="id")
        pset = ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset_name) \
            if pset is None else model.by_id(pset)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={prop_name: value})
        count += 1
    return count


def batch_tag(model: ifcopenshell.file, elements: Iterable, tag: str) -> int:
    """Add a label/classification tag to elements (drives layers/filters in the viewer)."""
    return set_pset_value(model, elements, "AEC_Tags", "Label", tag)


def elements_on_storey(model: ifcopenshell.file, storey_name: str, ifc_class: str = "IfcWall"):
    """Selection helper: all elements of a class on a named storey."""
    storey = next((s for s in model.by_type("IfcBuildingStorey") if s.Name == storey_name), None)
    if storey is None:
        return []
    return [el for el in model.by_type(ifc_class) if ue.get_container(el) is storey]
