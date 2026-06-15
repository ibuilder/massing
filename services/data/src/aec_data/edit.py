"""IFC authoring recipes + round-trip (Phase 6).

These run on `ifcopenshell.api` — the SAME engine Bonsai drives in Blender, and what
Bonsai-MCP executes over its socket. So the platform can author/edit IFC headlessly here,
or through the desktop GUI; both stay GUID-stable so pins/RFIs/clashes survive a re-publish.

Round-trip: edit IFC -> save -> reconvert to .frag (converter) -> reindex props -> reload.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element as ue

from .ifc_loader import open_model

_DTYPE = {"bool": "IfcBoolean", "str": "IfcLabel", "float": "IfcReal", "int": "IfcInteger"}


def set_pset_on_class(model: ifcopenshell.file, ifc_class: str, pset: str,
                      prop: str, value: Any) -> int:
    """Add/edit a Pset property on every element of an IFC class (e.g. fix LoadBearing on
    all slabs). Returns the number of elements changed."""
    count = 0
    for el in model.by_type(ifc_class):
        existing = ue.get_pset(el, pset, prop="id")
        ps = model.by_id(existing) if existing else \
            ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset)
        ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={prop: value})
        count += 1
    return count


def batch_tag(model: ifcopenshell.file, ifc_class: str, label: str) -> int:
    """Tag all elements of a class with a custom label (drives viewer layers/filters)."""
    return set_pset_on_class(model, ifc_class, "AEC_Tags", "Label", label)


def place_type(model: ifcopenshell.file, type_guid: str, storey_name: str) -> str | None:
    """Instantiate an occurrence of an IFC type ("family") and put it on a storey.
    Returns the new element's GUID (geometry/placement is set by the caller / Bonsai)."""
    el_type = next((t for t in model.by_type("IfcTypeProduct") if t.GlobalId == type_guid), None)
    if el_type is None:
        return None
    storey = next((s for s in model.by_type("IfcBuildingStorey") if s.Name == storey_name), None)
    occ_class = el_type.is_a().replace("Type", "")
    element = ifcopenshell.api.run("root.create_entity", model, ifc_class=occ_class)
    ifcopenshell.api.run("type.assign_type", model, related_objects=[element], relating_type=el_type)
    if storey:
        ifcopenshell.api.run("spatial.assign_container", model,
                             products=[element], relating_structure=storey)
    return element.GlobalId


def add_spaces(model: ifcopenshell.file, rooms_per_storey: int = 4,
               ceiling_height: float = 3.0) -> int:
    """Author IfcSpace rooms per storey as a grid over the real building footprint, with
    extruded geometry, base quantities and Pset_SpaceCommon — so the model gains a usable
    space/room schedule. Returns the number of spaces created."""
    import math
    import multiprocessing

    import ifcopenshell.geom as geom
    import numpy as np

    # building XY footprint from envelope elements only (exclude site/terrain)
    building = {"ifcwall", "ifcwallstandardcase", "ifcslab", "ifcroof", "ifcwindow",
                "ifcdoor", "ifccolumn", "ifcbeam", "ifcstair", "ifccovering"}
    settings = geom.settings()
    it = geom.iterator(settings, model, max(1, multiprocessing.cpu_count() - 1))
    mn = np.array([1e18, 1e18, 1e18]); mx = -mn
    if it.initialize():
        while True:
            sh = it.get()
            el = model.by_guid(sh.guid)
            if el and el.is_a().lower() in building:
                v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
                if v.size:
                    mn = np.minimum(mn, v.min(axis=0)); mx = np.maximum(mx, v.max(axis=0))
            if not it.next():
                break
    if not np.isfinite(mn).all():
        return 0

    # body context for the representations
    body = next((c for c in model.by_type("IfcGeometricRepresentationSubContext")
                 if c.ContextIdentifier == "Body"), None) or \
        (model.by_type("IfcGeometricRepresentationContext") or [None])[0]

    storeys = sorted(model.by_type("IfcBuildingStorey"),
                     key=lambda s: float(getattr(s, "Elevation", 0) or 0))
    cols = int(math.ceil(math.sqrt(rooms_per_storey)))
    rows = int(math.ceil(rooms_per_storey / cols))
    w = (mx[0] - mn[0]) / cols
    d = (mx[1] - mn[1]) / rows
    import ifcopenshell.util.unit as uunit
    scale = uunit.calculate_unit_scale(model)  # meters -> file units for placement
    count = 0
    for storey in storeys:
        elev = float(getattr(storey, "Elevation", 0) or 0)  # file units
        n = 0
        for r in range(rows):
            for c in range(cols):
                if n >= rooms_per_storey:
                    break
                n += 1
                space = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace",
                                             name=f"{storey.Name} - Room {n:02d}")
                space.LongName = f"Room {n:02d}"
                # placement (file units): geometry is meters → divide by scale
                ox = (mn[0] + c * w) / scale
                oy = (mn[1] + r * d) / scale
                matrix = np.eye(4); matrix[0, 3] = ox; matrix[1, 3] = oy; matrix[2, 3] = elev
                ifcopenshell.api.run("geometry.edit_object_placement", model, product=space, matrix=matrix)
                # extruded rectangle (meters)
                profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                                              XDim=w, YDim=d)
                rep = ifcopenshell.api.run("geometry.add_profile_representation", model,
                                           context=body, profile=profile, depth=ceiling_height)
                ifcopenshell.api.run("geometry.assign_representation", model, product=space, representation=rep)
                ifcopenshell.api.run("aggregate.assign_object", model, products=[space], relating_object=storey)
                # base quantities + common pset
                qto = ifcopenshell.api.run("pset.add_qto", model, product=space, name="Qto_SpaceBaseQuantities")
                ifcopenshell.api.run("pset.edit_qto", model, qto=qto,
                                     properties={"NetFloorArea": round(w * d, 2),
                                                 "GrossFloorArea": round(w * d, 2),
                                                 "NetVolume": round(w * d * ceiling_height, 2),
                                                 "Height": ceiling_height})
                ps = ifcopenshell.api.run("pset.add_pset", model, product=space, name="Pset_SpaceCommon")
                ifcopenshell.api.run("pset.edit_pset", model, pset=ps,
                                     properties={"Reference": "ROOM", "Category": "Habitable"})
                count += 1
    return count


# recipe registry — what an API endpoint / Bonsai-MCP can invoke by name
RECIPES = {
    "set_pset": lambda m, p: set_pset_on_class(
        m, p["ifc_class"], p["pset"], p["prop"],
        _coerce(p.get("value"), p.get("dtype", "str"))),
    "batch_tag": lambda m, p: batch_tag(m, p["ifc_class"], p["label"]),
    "place_type": lambda m, p: place_type(m, p["type_guid"], p["storey"]),
    "add_spaces": lambda m, p: add_spaces(m, int(p.get("rooms_per_storey", 4)),
                                          float(p.get("ceiling_height", 3.0))),
}


def _coerce(v, dtype):
    if dtype == "bool":
        return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
    if dtype == "float":
        return float(v)
    if dtype == "int":
        return int(v)
    return v


def apply_recipe(ifc_path: str, recipe: str, params: dict, out_path: str) -> dict:
    """Apply a recipe to the IFC and save a new file. GUIDs of existing elements are
    preserved, so downstream pins/RFIs/clashes (keyed by GUID) survive."""
    if recipe not in RECIPES:
        raise ValueError(f"unknown recipe {recipe!r}; have {list(RECIPES)}")
    model = open_model(ifc_path)
    changed = RECIPES[recipe](model, params)
    model.write(out_path)
    return {"recipe": recipe, "changed": changed, "out": out_path}
