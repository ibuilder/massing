"""REL-3 leaf: structural authoring recipes — walls, slabs, columns, beams, steel, rebar, footings.

The structural/enclosure recipe group split off `edit.py`: sloped walls, extruded walls/slabs, concrete
columns/beams, steel W-shapes (via the `steel` section catalog, imported lazily), rebar runs and spread
footings. Built entirely on the `edit_core` primitives (body context, rect profiles, storey lookup) —
never on another recipe. `edit.py` re-exports every name, so `edit.add_wall` / `edit.add_column` importers
(routers, RECIPES, tests, generators) are unchanged.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api

from .edit_core import _body_context, _first_storey, _rect_profile


def set_wall_slope(model: ifcopenshell.file, guid: str, start_height: float, end_height: float) -> dict:
    """B3: give a wall a **sloped top** — the top goes from `start_height` (at the wall's start end) to
    `end_height` (at the end), for parapet slopes / shed / gable walls. Rebuilds the wall's Body as a
    **trapezoidal side profile extruded across the thickness** (a plain IfcExtrudedAreaSolid — no boolean,
    so every geometry engine renders it). GUID-stable. The wall must be a standard rectangular-extruded
    wall (as authored by add_wall); returns {guid, start_height, end_height, length, thickness}."""
    import ifcopenshell.util.unit as uunit

    try:
        el = model.by_guid(guid)
    except (RuntimeError, Exception):  # noqa: BLE001 — by_guid raises for an unknown GUID
        el = None
    if el is None or not el.is_a("IfcWall"):
        raise ValueError(f"{guid} is not an IfcWall")
    sh, eh = float(start_height), float(end_height)
    if sh <= 0 or eh <= 0:
        raise ValueError("start_height and end_height must be > 0")
    scale = uunit.calculate_unit_scale(model)
    rep = next((r for r in (getattr(getattr(el, "Representation", None), "Representations", None) or [])
                if getattr(r, "RepresentationIdentifier", None) == "Body"), None)
    solid = rep.Items[0] if (rep and rep.Items) else None
    if solid is None or not solid.is_a("IfcExtrudedAreaSolid"):
        raise ValueError("wall geometry isn't a standard extrusion — can't slope it")
    prof = solid.SweptArea
    if prof.is_a("IfcRectangleProfileDef"):                  # a fresh add_wall: length×thickness, extruded up
        xdim, ydim = float(prof.XDim), float(prof.YDim)      # length, thickness in FILE units
    elif prof.is_a("IfcArbitraryClosedProfileDef") and prof.OuterCurve.is_a("IfcPolyline"):
        # a wall we already sloped: length = the profile's X-extent, thickness = the extrusion depth
        pxs = [float(p.Coordinates[0]) for p in prof.OuterCurve.Points]
        xdim, ydim = (max(pxs) - min(pxs)), float(solid.Depth)
    else:
        raise ValueError("wall geometry isn't a standard rectangular/sloped extrusion — can't slope it")
    hx = xdim / 2.0
    # trapezoid side profile (file units): along-length X, height Y; top edge start_h → end_h
    pts = [(-hx, 0.0), (hx, 0.0), (hx, eh / scale), (-hx, sh / scale)]
    poly = model.create_entity("IfcPolyline", Points=[
        model.create_entity("IfcCartesianPoint", (float(x), float(y))) for x, y in pts]
        + [model.create_entity("IfcCartesianPoint", (float(pts[0][0]), float(pts[0][1])))])
    new_prof = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=poly)
    # place the profile plane in the wall's local X–Z, extrude across thickness (local -Y, centred)
    place = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", (0.0, ydim / 2.0, 0.0)),
        Axis=model.create_entity("IfcDirection", (0.0, -1.0, 0.0)),
        RefDirection=model.create_entity("IfcDirection", (1.0, 0.0, 0.0)))
    new_solid = model.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=new_prof, Position=place,
        ExtrudedDirection=model.create_entity("IfcDirection", (0.0, 0.0, 1.0)), Depth=ydim)
    rep.Items = [new_solid]
    try:                                                    # tidy the now-orphaned rectangular solid
        model.remove(solid)
    except Exception:  # noqa: BLE001
        pass
    return {"guid": guid, "start_height": sh, "end_height": eh,
            "length": round(xdim * scale, 4), "thickness": round(ydim * scale, 4)}


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
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-9:
        raise ValueError("start and end points must differ")
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
    pts = [model.create_entity("IfcCartesianPoint",                # profile coords in file units (÷ scale)
                               Coordinates=(float(p[0]) / scale, float(p[1]) / scale)) for p in points]
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
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-9:
        raise ValueError("start and end points must differ")
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
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-9:
        raise ValueError("start and end points must differ")
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
    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=pos,
                                  Radius=dia / 2.0 / scale)          # file units (metres ÷ scale)
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
# MEP-FP: a discipline word (or a raw IfcDistributionSystemEnum value) → the system PredefinedType, so a
# distribution system carries its discipline and **fire protection is a first-class system** beside
# HVAC / plumbing / electrical (not just an unlabelled "MEP" group).
