"""REL-3 leaf: enclosure authoring recipes — coverings, railings, roofs, and hosted openings.

The enclosure/finish recipe group split off `edit.py`: ceiling/floor coverings, railings along a run,
footprint roofs, and the wall-hosted opening + parametric door/window fill (IfcRelVoidsElement +
IfcRelFillsElement, with the LOD-350 lining/panel generators falling back to a box proxy). Built on the
`edit_core` primitives; `edit.py` re-exports every name, so `edit.add_opening` / `edit.add_roof`
importers (RECIPES, routers, generators) are unchanged.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api

from .edit_core import (
    _body_context,
    _fill_representation,
    _first_storey,
    _rect_profile,
    _wall_thickness,
)


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
    pts = [model.create_entity("IfcCartesianPoint",                # profile coords in file units (÷ scale)
                               Coordinates=(float(p[0]) / scale, float(p[1]) / scale)) for p in points]
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
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-9:
        raise ValueError("start and end points must differ")
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
    pts = [model.create_entity("IfcCartesianPoint",                # profile coords in file units (÷ scale)
                               Coordinates=(float(p[0]) / scale, float(p[1]) / scale)) for p in points]
    pts.append(pts[0])
    poly = model.create_entity("IfcPolyline", Points=pts)
    profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=poly)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=profile, depth=float(thickness))
    ifcopenshell.api.run("geometry.assign_representation", model, product=roof, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[roof], relating_structure=st)
    return roof.GlobalId


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
