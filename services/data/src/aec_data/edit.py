"""IFC authoring recipes + round-trip (Phase 6).

These run on `ifcopenshell.api` — the SAME engine Bonsai drives in Blender, and what
Bonsai-MCP executes over its socket. So the platform can author/edit IFC headlessly here,
or through the desktop GUI; both stay GUID-stable so pins/RFIs/clashes survive a re-publish.

Round-trip: edit IFC -> save -> reconvert to .frag (converter) -> reindex props -> reload.
"""
from __future__ import annotations

import contextlib
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


def list_types(model: ifcopenshell.file) -> list[dict]:
    """Catalog of placeable types ("families") in the model — IfcTypeProduct, deduped by
    (class, name) so the picker shows distinct families rather than one per instance."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for t in model.by_type("IfcTypeProduct"):
        name = getattr(t, "Name", None) or t.is_a()
        key = (t.is_a(), name)
        if key in seen:
            continue
        seen.add(key)
        occ = sum(len(rel.RelatedObjects) for rel in (getattr(t, "Types", None) or []))
        out.append({"guid": t.GlobalId, "name": name, "ifc_class": t.is_a(),
                    "predefined": getattr(t, "PredefinedType", None),
                    "has_geometry": bool(getattr(t, "RepresentationMaps", None)),
                    "occurrence_count": occ})
    out.sort(key=lambda x: (x["ifc_class"], x["name"]))
    return out


def query_elements(model: ifcopenshell.file, query: str, limit: int = 2000) -> dict:
    """Run an IfcOpenShell **selector query** (the `.IfcWall`, `IfcWall, IfcDoor`,
    `IfcWall, material=concrete`, `IfcSpace, Pset_SpaceCommon.IsExternal=TRUE` DSL) over the model and
    return the matched elements. This is the power-selection primitive behind bulk edits, schedule
    scoping, and rule-driven detail/spec attachment. Returns {query, count, truncated, elements:[{guid,
    name, ifc_class, storey}]}. Invalid syntax raises ValueError with the parser message."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.selector as sel

    q = (query or "").strip()
    if not q:
        raise ValueError("empty query")
    try:
        matched = sel.filter_elements(model, q)
    except Exception as e:  # noqa: BLE001 — surface the selector parser error as a clean 400
        raise ValueError(f"invalid selector query: {str(e)[:200]}") from e
    out: list[dict] = []
    for el in matched:
        if len(out) >= limit:
            break
        st = ue.get_container(el)
        out.append({"guid": el.GlobalId, "name": getattr(el, "Name", None) or el.is_a(),
                    "ifc_class": el.is_a(), "storey": getattr(st, "Name", None) if st else None})
    return {"query": q, "count": len(matched), "truncated": len(matched) > len(out), "elements": out}


def place_type(model: ifcopenshell.file, type_guid: str, storey_name: str,
               position=None) -> str | None:
    """Instantiate an occurrence of an IFC type ("family") on a storey, optionally positioned
    at an [E, N] point (meters). assign_type maps the type's geometry to the occurrence when the
    type carries RepresentationMaps. Returns the new element's GUID."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    el_type = next((t for t in model.by_type("IfcTypeProduct") if t.GlobalId == type_guid), None)
    if el_type is None:
        return None
    st = _first_storey(model, storey_name)
    occ_class = el_type.is_a().replace("Type", "")
    element = ifcopenshell.api.run("root.create_entity", model, ifc_class=occ_class)
    ifcopenshell.api.run("type.assign_type", model, related_objects=[element], relating_type=el_type)
    if position is not None:
        scale = uunit.calculate_unit_scale(model)
        elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale  # file units -> m
        matrix = np.array([[1, 0, 0, float(position[0])], [0, 1, 0, float(position[1])],
                           [0, 0, 1, elev], [0, 0, 0, 1]], dtype=float)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model,
                             products=[element], relating_structure=st)
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


def _body_context(model):
    return next((c for c in model.by_type("IfcGeometricRepresentationSubContext")
                 if c.ContextIdentifier == "Body"), None) or \
        (model.by_type("IfcGeometricRepresentationContext") or [None])[0]


def _rect_profile(model, xdim: float, ydim: float):
    """An IfcRectangleProfileDef WITH a Position. web-ifc requires the profile placement to be set
    (ifcopenshell tolerates a null Position, but web-ifc silently skips the element → it renders
    invisible in the viewer). Always give parametric profiles an origin placement."""
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    return model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                               XDim=float(xdim), YDim=float(ydim))


def _first_storey(model, name=None):
    sts = sorted(model.by_type("IfcBuildingStorey"),
                 key=lambda s: float(getattr(s, "Elevation", 0) or 0))
    if name:
        return next((s for s in sts if s.Name == name), sts[0] if sts else None)
    return sts[0] if sts else None


def add_storey(model: ifcopenshell.file, name: str, elevation: float = 0.0) -> str:
    """Author a new IfcBuildingStorey (level) at `elevation` metres, aggregated under the building."""
    import ifcopenshell.util.unit as uunit
    scale = uunit.calculate_unit_scale(model)         # file units -> metres
    building = (model.by_type("IfcBuilding") or [None])[0]
    st = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                              name=name or "Level")
    st.Elevation = float(elevation) / scale           # metres -> file units
    if building is not None:
        ifcopenshell.api.run("aggregate.assign_object", model, products=[st], relating_object=building)
    return st.GlobalId


def rename_storey(model: ifcopenshell.file, guid: str, name: str) -> str:
    """Rename an existing storey/level (by GUID)."""
    st = model.by_guid(guid)
    st.Name = name
    return guid


def set_storey_elevation(model: ifcopenshell.file, guid: str, elevation: float = 0.0) -> str:
    """Move a storey/level to a new elevation (metres)."""
    import ifcopenshell.util.unit as uunit
    scale = uunit.calculate_unit_scale(model)
    st = model.by_guid(guid)
    st.Elevation = float(elevation) / scale
    return guid


def add_wall(model: ifcopenshell.file, start, end, height: float = 3.0,
             thickness: float = 0.2, storey: str | None = None) -> str:
    """Author an IfcWall from two XY points (meters): a rectangular profile (length ×
    thickness) extruded to `height`, placed + rotated along the start→end axis. Mirrors
    add_spaces' unit handling (geometry in meters, placement translation / unit scale).
    Returns the new wall's GUID."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy) or 1.0
    ang = math.atan2(ey - sy, ex - sx)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale   # file units -> m
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    mx, my = (sx + ex) / 2, (sy + ey) / 2
    c, s = math.cos(ang), math.sin(ang)
    # placement in metres; edit_object_placement(is_si=True) converts to file units
    matrix = np.array([[c, -s, 0, mx], [s, c, 0, my],
                       [0, 0, 1, elev], [0, 0, 0, 1]], dtype=float)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=wall, matrix=matrix)
    profile = _rect_profile(model, length, float(thickness))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model,
                               context=body, profile=profile, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[wall], relating_structure=st)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps,
                         properties={"LoadBearing": False, "IsExternal": True})
    return wall.GlobalId


def add_slab(model: ifcopenshell.file, points, thickness: float = 0.2,
             storey: str | None = None) -> str:
    """Author an IfcSlab from a polygon of XY points (meters) extruded by `thickness`.
    Returns the new slab's GUID."""
    import ifcopenshell.util.unit as uunit
    import numpy as np
    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name="Slab")
    matrix = np.eye(4); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=slab, matrix=matrix)
    pts = [model.create_entity("IfcCartesianPoint", Coordinates=(float(p[0]), float(p[1]))) for p in points]
    pts.append(pts[0])  # close the loop
    poly = model.create_entity("IfcPolyline", Points=pts)
    profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=poly)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model,
                               context=body, profile=profile, depth=float(thickness))
    ifcopenshell.api.run("geometry.assign_representation", model, product=slab, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[slab], relating_structure=st)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=slab, name="Pset_SlabCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"LoadBearing": True})
    return slab.GlobalId


def add_column(model: ifcopenshell.file, point, height: float = 3.0, width: float = 0.4,
               depth: float = 0.4, storey: str | None = None, profile=None) -> str:
    """Author an IfcColumn at an XY point (meters): a rectangular profile (or a supplied parametric
    `profile`, e.g. a steel I-shape) extruded to `height`."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    col = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name="Column")
    matrix = np.eye(4)
    matrix[0, 3] = float(point[0]); matrix[1, 3] = float(point[1]); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=col, matrix=matrix)
    profile = profile or _rect_profile(model, float(width), float(depth))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=profile, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=col, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[col], relating_structure=st)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=col, name="Pset_ColumnCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"LoadBearing": True})
    return col.GlobalId


def add_beam(model: ifcopenshell.file, start, end, width: float = 0.3, depth: float = 0.5,
             storey: str | None = None, profile=None) -> str:
    """Author an IfcBeam between two XY points (meters): a rectangular cross-section (or a supplied
    parametric `profile`, e.g. a steel I-shape) swept horizontally along the start→end axis."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy) or 1.0
    dx, dy = (ex - sx) / length, (ey - sy) / length
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    beam = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name="Beam")
    # local Z = beam axis (horizontal), local Y = up, local X = Y×Z; extrude along local Z
    matrix = np.array([[-dy, 0, dx, sx], [dx, 0, dy, sy],
                       [0, 1, 0, elev], [0, 0, 0, 1]], dtype=float)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=beam, matrix=matrix)
    profile = _rect_profile(model, float(width), float(depth))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=profile, depth=length)
    ifcopenshell.api.run("geometry.assign_representation", model, product=beam, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[beam], relating_structure=st)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=beam, name="Pset_BeamCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"LoadBearing": True})
    return beam.GlobalId


# --- structural steel + rebar + footing (P4) --------------------------------------------------
def add_steel_column(model: ifcopenshell.file, point, height: float = 3.0,
                     section: str = "W12x26", storey: str | None = None) -> str:
    """An IfcColumn with a native parametric AISC W-shape (IfcIShapeProfileDef) extruded to `height`."""
    from . import steel
    guid = add_column(model, point, height=height, storey=storey, profile=steel.i_profile(model, section))
    _tag_section(model, guid, section)
    return guid


def add_steel_beam(model: ifcopenshell.file, start, end, section: str = "W12x26",
                   storey: str | None = None) -> str:
    """An IfcBeam with a native parametric AISC W-shape swept along the start→end axis."""
    from . import steel
    guid = add_beam(model, start, end, storey=storey, profile=steel.i_profile(model, section))
    _tag_section(model, guid, section)
    return guid


def _tag_section(model, guid: str, section: str) -> None:
    """Stamp the standard section name onto the member's common Pset (Reference)."""
    el = model.by_guid(guid)
    pset_name = "Pset_ColumnCommon" if el.is_a("IfcColumn") else "Pset_BeamCommon"
    existing = next((r.RelatingPropertyDefinition for r in getattr(el, "IsDefinedBy", [])
                     if r.is_a("IfcRelDefinesByProperties")
                     and r.RelatingPropertyDefinition.is_a("IfcPropertySet")
                     and r.RelatingPropertyDefinition.Name == pset_name), None)
    ps = existing or ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset_name)
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"Reference": section})


def add_rebar(model: ifcopenshell.file, start, end, size: str = "#5",
              storey: str | None = None) -> str:
    """A straight IfcReinforcingBar between two XY points — a circular section (bar diameter for
    `size`, e.g. '#5') swept along the axis. NominalDiameter + BarLength are stamped."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    from . import steel
    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy) or 1.0
    dx, dy = (ex - sx) / length, (ey - sy) / length
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    bar = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcReinforcingBar", name="Rebar")
    matrix = np.array([[-dy, 0, dx, sx], [dx, 0, dy, sy], [0, 1, 0, elev], [0, 0, 0, 1]], dtype=float)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=bar, matrix=matrix)
    dia = steel.rebar_diameter(size)
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=pos, Radius=dia / 2.0)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=length)
    ifcopenshell.api.run("geometry.assign_representation", model, product=bar, representation=rep)
    try:
        bar.NominalDiameter = dia / scale
        bar.BarLength = length / scale
    except Exception:                                 # noqa: BLE001 — optional attrs, best-effort
        pass
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[bar], relating_structure=st)
    return bar.GlobalId


def add_footing(model: ifcopenshell.file, point, width: float = 1.5, length: float = 1.5,
                thickness: float = 0.4, storey: str | None = None) -> str:
    """An IfcFooting (pad) at an XY point — a rectangular pad extruded by `thickness`, below the level."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale - float(thickness)
    ft = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFooting", name="Footing")
    try:
        ft.PredefinedType = "PAD_FOOTING"
    except Exception:                                 # noqa: BLE001 — schema without the enum
        pass
    matrix = np.eye(4)
    matrix[0, 3] = float(point[0]); matrix[1, 3] = float(point[1]); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=ft, matrix=matrix)
    profile = _rect_profile(model, float(width), float(length))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=float(thickness))
    ifcopenshell.api.run("geometry.assign_representation", model, product=ft, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[ft], relating_structure=st)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=ft, name="Pset_FootingCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"LoadBearing": True})
    return ft.GlobalId


# --- MEP: distribution runs (duct/pipe/cable) + point equipment (P5) --------------------------
def add_mep_run(model: ifcopenshell.file, ifc_class: str, start, end, shape: str = "round",
                size: float = 0.3, storey: str | None = None, system: str = "MEP") -> str:
    """A straight MEP segment (IfcDuctSegment / IfcPipeSegment / IfcCableCarrierSegment /
    IfcCableSegment) swept along start→end: a round (size=diameter) or rectangular (tray) section.
    Adds two connection ports and assigns it to a named IfcDistributionSystem."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy) or 1.0
    dx, dy = (ex - sx) / length, (ey - sy) / length
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    seg = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class,
                               name=ifc_class.replace("Ifc", "").replace("Segment", ""))
    matrix = np.array([[-dy, 0, dx, sx], [dx, 0, dy, sy], [0, 1, 0, elev], [0, 0, 0, 1]], dtype=float)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=seg, matrix=matrix)
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    if shape == "rect":
        profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                                      XDim=float(size), YDim=float(size) * 0.4)
    else:
        profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=pos,
                                      Radius=float(size) / 2.0)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=length)
    ifcopenshell.api.run("geometry.assign_representation", model, product=seg, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[seg], relating_structure=st)
    try:                                              # ports — a bare segment is flagged invalid
        ifcopenshell.api.run("system.add_port", model, element=seg)
        ifcopenshell.api.run("system.add_port", model, element=seg)
    except Exception:                                 # noqa: BLE001 — older ifcopenshell w/o system.add_port
        pass
    try:
        name = system or "MEP"
        sysobj = next((s for s in model.by_type("IfcDistributionSystem") if s.Name == name), None) \
            or ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDistributionSystem", name=name)
        ifcopenshell.api.run("system.assign_system", model, products=[seg], system=sysobj)
    except Exception:                                 # noqa: BLE001 — system assignment best-effort
        pass
    return seg.GlobalId


def add_mep_terminal(model: ifcopenshell.file, ifc_class: str, point, width: float = 0.4,
                     depth: float = 0.4, height: float = 0.4, predefined: str | None = None,
                     storey: str | None = None) -> str:
    """Point MEP equipment (electrical panel, outlet, light, air terminal, sanitary/waste terminal,
    fire alarm, sensor, comms appliance) as a sized box of `ifc_class` at an XY point."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    el = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class,
                              name=ifc_class.replace("Ifc", ""))
    if predefined:
        try:
            el.PredefinedType = predefined
        except Exception:                             # noqa: BLE001 — enum not in this schema
            pass
    matrix = np.eye(4)
    matrix[0, 3] = float(point[0]); matrix[1, 3] = float(point[1]); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=matrix)
    profile = _rect_profile(model, float(width), float(depth))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=st)
    return el.GlobalId


# --- architectural finishes: coverings (ceiling/tile/cladding) + railings (P3) ----------------
def add_covering(model: ifcopenshell.file, points, predefined: str = "CEILING",
                 thickness: float = 0.02, material: str | None = None,
                 storey: str | None = None) -> str:
    """A thin IfcCovering over a polygon of XY points: a CEILING (hung near the top of the storey),
    FLOORING (tile/wood at floor level), or CLADDING. Optional finish material."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    base = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    elev = base + (2.7 if predefined == "CEILING" else 0.0)   # ceilings hang near the storey top
    cov = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCovering", name="Covering")
    try:
        cov.PredefinedType = predefined
    except Exception:                                 # noqa: BLE001 — enum not in this schema
        pass
    matrix = np.eye(4); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=cov, matrix=matrix)
    pts = [model.create_entity("IfcCartesianPoint", Coordinates=(float(p[0]), float(p[1]))) for p in points]
    pts.append(pts[0])
    poly = model.create_entity("IfcPolyline", Points=pts)
    profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=poly)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=float(thickness))
    ifcopenshell.api.run("geometry.assign_representation", model, product=cov, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[cov], relating_structure=st)
    if material:
        try:
            mat = ifcopenshell.api.run("material.add_material", model, name=material)
            ifcopenshell.api.run("material.assign_material", model, products=[cov], material=mat)
        except Exception:                             # noqa: BLE001 — material assignment best-effort
            pass
    ifcopenshell.api.run("pset.add_pset", model, product=cov, name="Pset_CoveringCommon")
    return cov.GlobalId


def add_railing(model: ifcopenshell.file, start, end, height: float = 1.1,
                storey: str | None = None) -> str:
    """A straight IfcRailing between two XY points — a thin panel of `height` along the axis."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy) or 1.0
    ang = math.atan2(ey - sy, ex - sx)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    rail = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcRailing", name="Railing")
    mx, my = (sx + ex) / 2, (sy + ey) / 2
    c, s = math.cos(ang), math.sin(ang)
    matrix = np.array([[c, -s, 0, mx], [s, c, 0, my], [0, 0, 1, elev], [0, 0, 0, 1]], dtype=float)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=rail, matrix=matrix)
    profile = _rect_profile(model, length, 0.05)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=rail, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[rail], relating_structure=st)
    return rail.GlobalId


def add_roof(model: ifcopenshell.file, points, thickness: float = 0.3,
             storey: str | None = None) -> str:
    """Author a flat IfcRoof from a polygon of XY points (meters) extruded by `thickness`
    at the storey elevation. (Pitched roofs are a future enhancement.)"""
    import ifcopenshell.util.unit as uunit
    import numpy as np
    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    roof = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcRoof", name="Roof")
    matrix = np.eye(4); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=roof, matrix=matrix)
    pts = [model.create_entity("IfcCartesianPoint", Coordinates=(float(p[0]), float(p[1]))) for p in points]
    pts.append(pts[0])
    poly = model.create_entity("IfcPolyline", Points=pts)
    profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=poly)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=profile, depth=float(thickness))
    ifcopenshell.api.run("geometry.assign_representation", model, product=roof, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[roof], relating_structure=st)
    return roof.GlobalId


def _wall_thickness(host, default: float = 0.2) -> float:
    """The host wall's thickness (m) for sizing a door/window lining — from Qto_WallBaseQuantities if
    present, else a sensible default."""
    import ifcopenshell.util.element as ue

    q = ue.get_pset(host, "Qto_WallBaseQuantities") or {}
    w = q.get("Width")
    try:
        return float(w) if w else default
    except (TypeError, ValueError):
        return default


def _fill_representation(model, body, kind: str, width: float, height: float,
                        operation: str | None, scale: float, lining_depth: float):
    """B2 — parametric door/window geometry via IfcOpenShell's built-in generators (real lining, frame
    and panels — a LOD 300→350 jump over the old single box proxy). Returns a shape representation, or
    None so the caller falls back to the box proxy if the generator rejects the parameters."""
    try:
        if kind == "window":
            return ifcopenshell.api.run(
                "geometry.add_window_representation", model, context=body,
                overall_height=float(height), overall_width=float(width),
                partition_type=(operation or "SINGLE_PANEL"),
                lining_properties={"LiningDepth": lining_depth, "LiningThickness": 0.05,
                                   "MullionThickness": 0.0, "TransomThickness": 0.0},
                panel_properties=[{"FrameDepth": 0.04, "FrameThickness": 0.05}],
                unit_scale=scale)
        return ifcopenshell.api.run(
            "geometry.add_door_representation", model, context=body,
            overall_height=float(height), overall_width=float(width),
            operation_type=(operation or "SINGLE_SWING_LEFT"),
            lining_properties={"LiningDepth": lining_depth, "LiningThickness": 0.05,
                               "TransomThickness": 0.0},
            panel_properties={"PanelDepth": 0.04, "PanelWidth": 1.0,
                              "FrameDepth": 0.0, "FrameThickness": 0.0},
            unit_scale=scale)
    except Exception:  # noqa: BLE001 — bad enum / generator failure → caller uses the box proxy
        return None


def add_opening(model: ifcopenshell.file, host_guid: str, width: float = 0.9, height: float = 2.1,
                sill: float = 0.0, kind: str = "door", storey: str | None = None,
                position=None, operation: str | None = None, parametric: bool = True) -> str:
    """Cut an opening in the host wall (IfcOpeningElement voiding it) and fill it with an
    IfcDoor/IfcWindow. `kind` ∈ door|window; `sill` is the bottom height (m). `position` is an
    optional [E,N] plan point — projected onto the wall axis to place the opening there;
    omit it to center on the wall. When `parametric` (default), the fill gets real lining/frame/panel
    geometry from IfcOpenShell's door/window generators (`operation` = the swing/partition type);
    a generator failure falls back to a simple panel proxy so authoring never breaks."""
    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit
    import numpy as np

    host = next((e for e in model.by_type("IfcWall") if e.GlobalId == host_guid), None)
    if host is None:
        raise ValueError(f"host wall {host_guid} not found (select a wall first)")
    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    # opening placement = wall world placement (in metres), raised by the sill (local +Z up),
    # and (if a position is given) offset along the wall axis to the projected click point
    wm = np.array(uplace.get_local_placement(host.ObjectPlacement), dtype=float)
    wm[0:3, 3] *= scale   # file units -> metres
    off = np.eye(4); off[2, 3] = float(sill)
    if position is not None:
        origin, xaxis = wm[0:3, 3], wm[0:3, 0].copy()
        n = float(np.linalg.norm(xaxis)) or 1.0
        xaxis /= n
        p = np.array([float(position[0]), float(position[1]), origin[2]])
        off[0, 3] = float(np.dot(p - origin, xaxis))   # signed distance along the wall axis
    opm = wm @ off

    opening = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name=f"{kind} opening")
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=opening, matrix=opm)
    # generous Y so the box cuts fully through the wall thickness
    cut = _rect_profile(model, float(width), 1.0)
    crep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=cut, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=opening, representation=crep)
    ifcopenshell.api.run("feature.add_feature", model, feature=opening, element=host)

    cls = "IfcWindow" if kind == "window" else "IfcDoor"
    el = ifcopenshell.api.run("root.create_entity", model, ifc_class=cls, name=kind.capitalize())
    try:
        el.OverallWidth = float(width); el.OverallHeight = float(height)
    except Exception:
        pass
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=opm)
    prep = _fill_representation(model, body, kind, width, height, operation, scale,
                               _wall_thickness(host)) if parametric else None
    if prep is None:                                   # fallback: simple panel proxy (never breaks)
        panel = _rect_profile(model, float(width), 0.06)
        prep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                    profile=panel, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=prep)
    ifcopenshell.api.run("feature.add_filling", model, opening=opening, element=el)
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=st)
    return el.GlobalId


def delete_element(model: ifcopenshell.file, guid: str) -> int:
    """Remove an element (and its placement/representation/voids) by GlobalId. Returns 1/0."""
    el = next((e for e in model.by_type("IfcElement") if e.GlobalId == guid), None)
    if el is None:
        return 0
    ifcopenshell.api.run("root.remove_product", model, product=el)
    return 1


def _element(model: ifcopenshell.file, guid: str):
    el = next((e for e in model.by_type("IfcElement") if e.GlobalId == guid), None)
    if el is None:
        raise ValueError(f"element {guid} not found")
    return el


def copy_element(model: ifcopenshell.file, guid: str, dx: float = 0.0, dy: float = 0.0,
                 dz: float = 0.0) -> str:
    """Duplicate an element (new GUID, deep-copied representation, contained in a storey) and
    offset it by (dx,dy,dz) metres. copy_class alone drops the representation, so deep-copy it."""
    import ifcopenshell.util.element as ue

    el = _element(model, guid)
    new = ifcopenshell.api.run("root.copy_class", model, product=el)
    if el.Representation:
        new.Representation = ue.copy_deep(model, el.Representation)
    st = _first_storey(model)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[new], relating_structure=st)
    if dx or dy or dz:
        move_element(model, new.GlobalId, dx, dy, dz)
    return new.GlobalId


def set_element_pset(model: ifcopenshell.file, guid: str, pset: str, prop: str,
                     value, dtype: str = "str") -> str:
    """Set a single property in a Pset on one element (by GUID). GUID-stable."""
    import ifcopenshell.util.element as ue

    el = _element(model, guid)
    existing = ue.get_pset(el, pset, prop="id")
    ps = model.by_id(existing) if existing else \
        ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset)
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={prop: _coerce(value, dtype)})
    return guid


_PHASE_CODES = {"new": "NEW", "existing": "EXISTING", "demolish": "DEMOLISH", "temporary": "TEMPORARY"}


def set_phase(model: ifcopenshell.file, guids, phase: str = "new") -> int:
    """W10-8: tag elements with a construction **phase / status** (new · existing · demolish ·
    temporary) — the renovation/sequencing dimension needed for LOD-500 as-built + demolition models.
    Stamps `Massing_Phasing.Status` (the widely-used NEW/EXISTING/DEMOLISH/TEMPORARY status coding, so
    it colours/filters and round-trips) on each element. GUID-stable; a bad GUID never aborts the batch.
    Returns the count tagged."""
    code = _PHASE_CODES.get((phase or "new").strip().lower(), (phase or "NEW").strip().upper())
    n = 0
    for g in guids or []:
        try:
            set_element_pset(model, g, "Massing_Phasing", "Status", code, "str")
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs, keep tagging the rest
            pass
    return n


def phase_summary(model: ifcopenshell.file) -> dict:
    """Count physical elements per phase/status (unset = not yet phased). Feeds a phasing overview and
    the colour-by-status view."""
    import ifcopenshell.util.element as ue

    counts: dict[str, int] = {"NEW": 0, "EXISTING": 0, "DEMOLISH": 0, "TEMPORARY": 0, "UNSET": 0}
    total = 0
    for el in model.by_type("IfcElement"):
        total += 1
        ps = ue.get_pset(el, "Massing_Phasing") or {}
        status = str(ps.get("Status") or "").upper()
        counts[status if status in counts else "UNSET"] += 1
    return {"total": total, "counts": counts,
            "phased": total - counts["UNSET"], "prop": "Massing_Phasing.Status"}


def set_classification(model: ifcopenshell.file, guid: str, system: str, code: str,
                       name: str | None = None, edition: str | None = None) -> str:
    """Tag one element (by GUID) with a classification reference — Uniclass 2015, OmniClass,
    Uniformat II, MasterFormat, etc. Reuses an existing IfcClassification for `system` if present,
    so repeated tags don't duplicate the source. GUID-stable; the standard BIM way to carry
    Uniclass/OmniClass codes into downstream takeoff, cost and asset systems.
    """
    import ifcopenshell.api.classification as cls

    el = _element(model, guid)
    src = next((s for s in model.by_type("IfcClassification")
                if (s.Name or "").strip().lower() == system.strip().lower()), None)
    if src is None:
        src = cls.add_classification(model, classification=system)
        if edition:
            with contextlib.suppress(Exception):
                cls.edit_classification(model, classification=src, attributes={"Edition": edition})
    cls.add_reference(model, products=[el], classification=src,
                      identification=code, name=name or code)
    return guid


def move_element(model: ifcopenshell.file, guid: str, dx: float = 0.0, dy: float = 0.0,
                 dz: float = 0.0) -> str:
    """Translate an element by (dx,dy,dz) metres in IFC E/N/Z. GUID-stable."""
    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit
    import numpy as np

    el = _element(model, guid)
    scale = uunit.calculate_unit_scale(model)
    m = np.array(uplace.get_local_placement(el.ObjectPlacement), dtype=float)
    m[0:3, 3] *= scale                     # world translation -> metres
    m[0, 3] += float(dx); m[1, 3] += float(dy); m[2, 3] += float(dz)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=m)  # is_si
    return guid


def rotate_element(model: ifcopenshell.file, guid: str, angle_deg: float = 0.0) -> str:
    """Rotate an element about its own vertical (Z) axis by `angle_deg`. GUID-stable."""
    import math

    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit
    import numpy as np
    el = _element(model, guid)
    scale = uunit.calculate_unit_scale(model)
    a = math.radians(float(angle_deg))
    c, s = math.cos(a), math.sin(a)
    rz = np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    m = np.array(uplace.get_local_placement(el.ObjectPlacement), dtype=float)
    m[0:3, 3] *= scale                     # world translation -> metres (is_si placement)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=m @ rz)
    return guid


def _recipe_add_family(model, p):
    """Place a starter-library family (furniture/sanitary/appliance/lighting/MEP/structural/plant) by
    catalog key. Optional `dims` ([w, d, h] m) places a parametrically-sized type variant."""
    from . import families  # lazy — families lazily imports edit, so this avoids an import cycle
    return families.add_family(model, p["family"], p.get("storey"), p.get("position"), p.get("dims"))


# recipe registry — what an API endpoint / Bonsai-MCP can invoke by name
def furnish_spaces(model: ifcopenshell.file, item: str = "desk", per_room: int = 0) -> int:
    """Generative fit-out (Wave 9 · W9-6): auto-furnish every IfcSpace by gridding furniture
    (IfcFurnishingElement) inside each room's real footprint with aisle clearance. Templates by `item`
    (metres, w×d×h). `per_room=0` fits as many as the footprint allows; otherwise caps per room.
    Returns the number of furniture items placed. Mirrors add_spaces' geometry/placement handling."""
    import multiprocessing

    import ifcopenshell.geom as geom
    import ifcopenshell.util.element as ue
    import numpy as np

    templates = {"desk": (1.5, 0.75, 0.75), "table": (2.0, 1.0, 0.75),
                 "bed": (2.0, 1.5, 0.5), "sofa": (2.0, 0.9, 0.8)}
    w, d, h = templates.get(item, templates["desk"])
    body = _body_context(model)

    # per-space footprint bbox from the baked geometry (SI metres, as add_spaces reads it)
    settings = geom.settings()
    it = geom.iterator(settings, model, max(1, multiprocessing.cpu_count() - 1))
    boxes: dict[str, tuple] = {}
    if it.initialize():
        while True:
            sh = it.get()
            el = model.by_guid(sh.guid)
            if el and el.is_a() == "IfcSpace":
                v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
                if v.size:
                    boxes[sh.guid] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max(), v[:, 2].min())
            if not it.next():
                break

    aisle = 0.8   # clear space around each item (m)
    cw, cd = w + aisle, d + aisle
    placed = 0
    for guid, (x0, y0, x1, y1, z0) in boxes.items():
        space = model.by_guid(guid)
        # spaces may be CONTAINED in or (more commonly) AGGREGATED under the storey — resolve either
        st = ue.get_container(space) or ue.get_aggregate(space)
        cols = max(0, int((x1 - x0 - aisle) // cw))
        rows = max(0, int((y1 - y0 - aisle) // cd))
        target = cols * rows if not per_room else min(per_room, cols * rows)
        k = 0
        for r in range(rows):
            for c in range(cols):
                if k >= target:
                    break
                cx = x0 + aisle / 2 + cw / 2 + c * cw
                cy = y0 + aisle / 2 + cd / 2 + r * cd
                f = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFurnishingElement",
                                         name=item.title())
                matrix = np.eye(4)
                matrix[0, 3] = cx
                matrix[1, 3] = cy
                matrix[2, 3] = z0
                ifcopenshell.api.run("geometry.edit_object_placement", model, product=f, matrix=matrix)
                rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                           profile=_rect_profile(model, w, d), depth=h)
                ifcopenshell.api.run("geometry.assign_representation", model, product=f, representation=rep)
                if st is not None:
                    ifcopenshell.api.run("spatial.assign_container", model, products=[f], relating_structure=st)
                placed += 1
                k += 1
    return placed


RECIPES = {
    "add_wall": lambda m, p: add_wall(m, p["start"], p["end"], float(p.get("height", 3.0)),
                                      float(p.get("thickness", 0.2)), p.get("storey")),
    "add_slab": lambda m, p: add_slab(m, p["points"], float(p.get("thickness", 0.2)), p.get("storey")),
    "add_column": lambda m, p: add_column(m, p["point"], float(p.get("height", 3.0)),
                                          float(p.get("width", 0.4)), float(p.get("depth", 0.4)), p.get("storey")),
    "add_beam": lambda m, p: add_beam(m, p["start"], p["end"], float(p.get("width", 0.3)),
                                      float(p.get("depth", 0.5)), p.get("storey")),
    "add_roof": lambda m, p: add_roof(m, p["points"], float(p.get("thickness", 0.3)), p.get("storey")),
    "add_door": lambda m, p: add_opening(m, p["host_guid"], float(p.get("width", 0.9)),
                                         float(p.get("height", 2.1)), float(p.get("sill", 0.0)), "door",
                                         p.get("storey"), p.get("position"), p.get("operation")),
    "add_window": lambda m, p: add_opening(m, p["host_guid"], float(p.get("width", 1.2)),
                                           float(p.get("height", 1.2)), float(p.get("sill", 0.9)), "window",
                                           p.get("storey"), p.get("position"), p.get("operation")),
    "delete_element": lambda m, p: delete_element(m, p["guid"]),
    "move_element": lambda m, p: move_element(m, p["guid"], float(p.get("dx", 0)),
                                              float(p.get("dy", 0)), float(p.get("dz", 0))),
    "rotate_element": lambda m, p: rotate_element(m, p["guid"], float(p.get("angle", 0))),
    "set_element_pset": lambda m, p: set_element_pset(m, p["guid"], p["pset"], p["prop"],
                                                      p.get("value"), p.get("dtype", "str")),
    "copy_element": lambda m, p: copy_element(m, p["guid"], float(p.get("dx", 1)),
                                              float(p.get("dy", 0)), float(p.get("dz", 0))),
    "set_pset": lambda m, p: set_pset_on_class(
        m, p["ifc_class"], p["pset"], p["prop"],
        _coerce(p.get("value"), p.get("dtype", "str"))),
    "batch_tag": lambda m, p: batch_tag(m, p["ifc_class"], p["label"]),
    "place_type": lambda m, p: place_type(m, p["type_guid"], p.get("storey"), p.get("position")),
    "add_family": lambda m, p: _recipe_add_family(m, p),
    "add_spaces": lambda m, p: add_spaces(m, int(p.get("rooms_per_storey", 4)),
                                          float(p.get("ceiling_height", 3.0))),
    # W9-6 generative fit-out: grid furniture into each space's footprint
    "furnish_spaces": lambda m, p: furnish_spaces(m, p.get("item", "desk"), int(p.get("per_room", 0))),
    "add_storey": lambda m, p: add_storey(m, p["name"], float(p.get("elevation", 0.0))),
    "rename_storey": lambda m, p: rename_storey(m, p["guid"], p["name"]),
    "set_storey_elevation": lambda m, p: set_storey_elevation(m, p["guid"], float(p.get("elevation", 0.0))),
    "add_steel_column": lambda m, p: add_steel_column(m, p["point"], float(p.get("height", 3.0)),
                                                       p.get("section", "W12x26"), p.get("storey")),
    "add_steel_beam": lambda m, p: add_steel_beam(m, p["start"], p["end"],
                                                  p.get("section", "W12x26"), p.get("storey")),
    "add_rebar": lambda m, p: add_rebar(m, p["start"], p["end"], p.get("size", "#5"), p.get("storey")),
    "add_footing": lambda m, p: add_footing(m, p["point"], float(p.get("width", 1.5)),
                                            float(p.get("length", 1.5)), float(p.get("thickness", 0.4)),
                                            p.get("storey")),
    "add_duct": lambda m, p: add_mep_run(m, "IfcDuctSegment", p["start"], p["end"], "round",
                                         float(p.get("size", 0.3)), p.get("storey"), p.get("system", "HVAC Supply")),
    "add_pipe": lambda m, p: add_mep_run(m, "IfcPipeSegment", p["start"], p["end"], "round",
                                         float(p.get("size", 0.05)), p.get("storey"), p.get("system", "Domestic Water")),
    "add_cable_tray": lambda m, p: add_mep_run(m, "IfcCableCarrierSegment", p["start"], p["end"], "rect",
                                               float(p.get("size", 0.3)), p.get("storey"), p.get("system", "Power")),
    "add_wire": lambda m, p: add_mep_run(m, "IfcCableSegment", p["start"], p["end"], "round",
                                         float(p.get("size", 0.02)), p.get("storey"), p.get("system", "Power")),
    "add_mep_terminal": lambda m, p: add_mep_terminal(m, p["ifc_class"], p["point"],
                                                      float(p.get("width", 0.4)), float(p.get("depth", 0.4)),
                                                      float(p.get("height", 0.4)), p.get("predefined"),
                                                      p.get("storey")),
    "add_covering": lambda m, p: add_covering(m, p["points"], p.get("predefined", "CEILING"),
                                              float(p.get("thickness", 0.02)), p.get("material"), p.get("storey")),
    "add_railing": lambda m, p: add_railing(m, p["start"], p["end"], float(p.get("height", 1.1)),
                                            p.get("storey")),
    "set_classification": lambda m, p: set_classification(m, p["guid"], p["system"], p["code"],
                                                          p.get("name"), p.get("edition")),
    # W9-1 property normalization: remap source psets/props onto a target (IDS/employer) structure
    "map_properties": lambda m, p: _map_properties(m, p["rules"]),
    # W9-3 bake resolved IFC5-style override layers into the model (each override -> set_element_pset)
    "apply_layers": lambda m, p: _apply_layers(m, p["overrides"]),
    # W10-1 first-class type/family system — create/edit types, assign material sets
    "create_type": lambda m, p: _fam(m).create_type(m, p["ifc_class"], p["name"], p.get("dims"),
                                                     p.get("predefined"), p.get("psets")),
    "edit_type_params": lambda m, p: _fam(m).edit_type_params(m, p["type_guid"], p.get("name"),
                                                              p.get("dims"), p.get("predefined"),
                                                              p.get("psets")),
    "assign_material_set": lambda m, p: _fam(m).assign_material_set(m, p["type_guid"], p["layers"]),
    # W10-3 groups / assemblies / arrays — compose placed elements
    "create_group": lambda m, p: _grp().create_group(m, p.get("name", "Group"), p["guids"]),
    "create_assembly": lambda m, p: _grp().create_assembly(m, p.get("name", "Assembly"), p["guids"],
                                                           p.get("predefined")),
    "array_element": lambda m, p: _grp().array_element(m, p["guid"], int(p.get("nx", 2)),
                                                       int(p.get("ny", 1)), float(p.get("dx", 1.0)),
                                                       float(p.get("dy", 0.0)), float(p.get("dz", 0.0))),
    "ungroup": lambda m, p: _grp().ungroup(m, p["guid"]),
    # W10-8 element phasing — tag new/existing/demolish/temporary status
    "set_phase": lambda m, p: set_phase(m, p["guids"], p.get("phase", "new")),
    # W11 F0 — the representation/context spine + LOD stage
    "ensure_contexts": lambda m, p: _rep().ensure_contexts(m),
    "set_lod": lambda m, p: _rep().set_lod(m, p["guids"], p.get("stage", "300")),
    # W11 Track D carrier layer — classification (keynote/spec code) + document (detail/instruction)
    "classify": lambda m, p: _det().classify(m, p["guids"], p["system"], p["code"],
                                             p.get("name"), p.get("edition")),
    "attach_document": lambda m, p: _det().attach_document(m, p["guids"], p["name"], p.get("location"),
                                                          p.get("description"), p.get("identification"),
                                                          p.get("purpose")),
    # W11 D3 — auto-detail: evaluate the condition→content rule set, write matched code/detail bundles
    "apply_detailing_rules": lambda m, p: _rules().apply_rules(m, p.get("rules")),
    # W11 B6 — structural steel connections (fabrication LOD 350/400)
    "add_base_plate": lambda m, p: _conn().add_base_plate(m, p["column_guid"], float(p.get("width", 0.4)),
                                                          float(p.get("depth", 0.4)), float(p.get("thickness", 0.025)),
                                                          int(p.get("bolts", 4)), storey=p.get("storey")),
    "add_shear_tab": lambda m, p: _conn().add_shear_tab(m, p["beam_guid"], float(p.get("thickness", 0.01)),
                                                        float(p.get("depth", 0.2)), float(p.get("width", 0.1)),
                                                        int(p.get("bolts", 2)), storey=p.get("storey")),
}


def _conn():
    """Lazy handle to the connections module (it imports edit helpers → avoid a cycle)."""
    from . import connections
    return connections


def _rules():
    """Lazy handle to the detailing rule engine."""
    from . import rules
    return rules


def _rep():
    """Lazy handle to the representations module (it imports edit.set_element_pset → avoid a cycle)."""
    from . import representations
    return representations


def _det():
    """Lazy handle to the detailing module (it imports edit.set_classification → avoid a cycle)."""
    from . import detailing
    return detailing


def _fam(model):
    """Lazy handle to the families module (avoids an import cycle: families imports edit for helpers)."""
    from . import families
    return families


def _grp():
    """Lazy handle to the groups module (it imports edit.copy_element → avoid an import cycle)."""
    from . import groups
    return groups


def _map_properties(model: ifcopenshell.file, rules) -> int:
    """Bulk property remap (Wave 9 W9-1) — delegate to the propmap engine; returns values changed."""
    from . import propmap
    return propmap.apply(model, rules)


def _apply_layers(model: ifcopenshell.file, overrides) -> int:
    """Bake resolved override layers (Wave 9 W9-3): write each effective {guid,pset,prop,value} into
    the IFC via set_element_pset. GUID-stable; a bad element never aborts the batch."""
    n = 0
    for o in overrides:
        try:
            set_element_pset(model, o["guid"], o["pset"], o["prop"], o.get("value"), o.get("dtype", "str"))
            n += 1
        except Exception:  # noqa: BLE001, S112
            continue
    return n


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
