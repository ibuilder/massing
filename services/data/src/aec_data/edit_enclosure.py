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


def add_roof_window(model: ifcopenshell.file, roof_guid: str, position, width: float = 0.9,
                    length: float = 1.2, storey: str | None = None) -> str:
    """DORMER slice (R17): a **roof window / skylight** — cut an opening through the host IfcRoof at an
    [E, N] plan position (IfcOpeningElement voiding it, full-depth) and fill it with an IfcWindow of
    PredefinedType SKYLIGHT (a thin glazed-panel proxy body). The flat-roof counterpart of the wall-hosted
    `add_opening`; the pitched-roof dormer assembly follows when pitched roofs land. GUID-stable."""
    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit
    import numpy as np

    host = next((e for e in model.by_type("IfcRoof") if e.GlobalId == roof_guid), None)
    if host is None:
        raise ValueError(f"host roof {roof_guid} not found (author a roof first)")
    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    wm = np.array(uplace.get_local_placement(host.ObjectPlacement), dtype=float)
    wm[0:3, 3] *= scale                                  # file units → metres
    # opening origin: the requested plan point at the roof's elevation, slightly below so the
    # vertical cut passes fully through the slab
    opm = np.eye(4)
    opm[0, 3], opm[1, 3], opm[2, 3] = float(position[0]), float(position[1]), wm[2, 3] - 0.1

    opening = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcOpeningElement",
                                   name="roof window opening")
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=opening, matrix=opm)
    cut = _rect_profile(model, float(width), float(length))
    crep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                profile=cut, depth=1.0)   # generous vertical cut through the roof build-up
    ifcopenshell.api.run("geometry.assign_representation", model, product=opening, representation=crep)
    ifcopenshell.api.run("feature.add_feature", model, feature=opening, element=host)

    win = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWindow", name="Roof window")
    try:
        win.PredefinedType = "SKYLIGHT"                   # IFC4 IfcWindowTypeEnum
    except Exception:                                     # noqa: BLE001 — enum absent on IFC2x3
        pass
    try:
        win.OverallWidth = float(width)
        win.OverallHeight = float(length)                 # the roof-plane dimensions
    except Exception:                                     # noqa: BLE001
        pass
    wpm = opm.copy()
    wpm[2, 3] = wm[2, 3]                                  # the glazing sits at the roof plane
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=win, matrix=wpm)
    panel = _rect_profile(model, float(width), float(length))
    prep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                profile=panel, depth=0.05)   # thin glazed panel proxy
    ifcopenshell.api.run("geometry.assign_representation", model, product=win, representation=prep)
    ifcopenshell.api.run("feature.add_filling", model, opening=opening, element=win)
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[win], relating_structure=st)
    return win.GlobalId


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


#: IBC-shaped straight-run limits, in metres. Maximum riser and minimum tread. They are DEFAULTS and
#: a REPORT, not a code check: `stair_geometry` says whether a run lands inside them, and `add_stair`
#: never silently reshapes a run to make the numbers fit.
MAX_RISER_M = 0.19
MIN_TREAD_M = 0.25
#: Maximum ramp slope, 1:12 — the accessible-route limit jurisdictions converge on.
MAX_RAMP_SLOPE = 1.0 / 12.0


def _run_placement(model, start, end, storey, target_storey, default_rise: float = 3.0):
    """Shared setup for a straight run: validated endpoints, midpoint matrix, base elevation and rise.

    An absent `target_storey` yields a STATED default rise rather than an inferred one — guessing the
    building's section from one drawn line would be a number nobody supplied."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    run = math.hypot(ex - sx, ey - sy)
    if run < 1e-9:
        raise ValueError("start and end points must differ")

    scale = uunit.calculate_unit_scale(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    tgt = _first_storey(model, target_storey) if target_storey else None
    if tgt is not None and tgt is not st:
        rise = (float(getattr(tgt, "Elevation", 0) or 0) * scale) - elev
    else:
        rise = float(default_rise)

    ang = math.atan2(ey - sy, ex - sx)
    c, s = math.cos(ang), math.sin(ang)
    matrix = np.array([[c, -s, 0, (sx + ex) / 2], [s, c, 0, (sy + ey) / 2],
                       [0, 0, 1, elev], [0, 0, 0, 1]], dtype=float)
    return st, matrix, run, rise


def _straight_run(model, start, end, width, storey, target_storey, ifc_class, flight_class, name):
    """Author an IfcStair/IfcRamp plus its aggregated flight. One body for both because the only
    difference is the class pair — duplicating it would let the two drift apart."""
    if float(width) <= 0:
        raise ValueError("width must be positive")
    st, matrix, run, rise = _run_placement(model, start, end, storey, target_storey)
    body = _body_context(model)

    parent = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    flight = ifcopenshell.api.run("root.create_entity", model, ifc_class=flight_class,
                                  name=name + " Flight")
    for prod in (parent, flight):
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=prod, matrix=matrix)
    # The flight's envelope along the run, not modelled treads: for a straight run the treads are
    # fully derivable from the reported riser/tread and add nothing a viewer or takeoff needs.
    profile = _rect_profile(model, run, float(width))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=max(0.05, abs(rise)))
    ifcopenshell.api.run("geometry.assign_representation", model, product=flight, representation=rep)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[flight], relating_object=parent)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[parent],
                             relating_structure=st)
    return parent.GlobalId


def add_stair(model: ifcopenshell.file, start, end, width: float = 1.2,
              storey: str | None = None, target_storey: str | None = None) -> str:
    """A straight-run IfcStair with its IfcStairFlight, from plan point `start` to `end`.

    Rises from `storey`'s elevation to `target_storey`'s, or by a stated 3.0 m when no target is given.

    **This does not certify a stair.** Riser and tread are derived from the rise and run actually
    drawn, and `stair_geometry()` reports whether they land inside `MAX_RISER_M` / `MIN_TREAD_M`.
    Silently lengthening a short run to satisfy the limits would move the top of the stair away from
    where the user put it — a change they cannot see and did not ask for. The run is placed as drawn
    and the consequence is reported."""
    return _straight_run(model, start, end, width, storey, target_storey,
                         "IfcStair", "IfcStairFlight", "Stair")


def add_ramp(model: ifcopenshell.file, start, end, width: float = 1.5,
             storey: str | None = None, target_storey: str | None = None) -> str:
    """A straight IfcRamp with its IfcRampFlight, from `start` to `end`.

    Same contract as `add_stair`: placed exactly where it was drawn, with `ramp_geometry()` reporting
    whether the resulting slope is within 1:12. A ramp quietly shortened to reach 1:12 no longer
    arrives where the user drew it, and nothing on screen would say so."""
    return _straight_run(model, start, end, width, storey, target_storey,
                         "IfcRamp", "IfcRampFlight", "Ramp")


def stair_geometry(rise: float, run: float) -> dict:
    """Riser/tread for a straight run, and whether it lands inside the shaped limits.

    Separate from `add_stair` so a draw tool can show the consequence BEFORE committing geometry, and
    so the arithmetic is testable without building a model. `within_limits` is a REPORT, never a gate."""
    import math

    if run <= 0 or rise <= 0:
        return {"riser_count": 0, "riser": None, "tread": None, "within_limits": None,
                "rise": None, "run": None, "max_riser": MAX_RISER_M, "min_tread": MIN_TREAD_M,
                "reason": "a stair needs a positive rise and a positive run; nothing was derived"}
    n = max(1, math.ceil(abs(rise) / MAX_RISER_M))
    riser = abs(rise) / n
    tread = abs(run) / n
    ok = riser <= MAX_RISER_M + 1e-9 and tread >= MIN_TREAD_M - 1e-9
    return {
        "riser_count": n, "riser": round(riser, 4), "tread": round(tread, 4),
        "rise": round(abs(rise), 4), "run": round(abs(run), 4),
        "within_limits": ok, "max_riser": MAX_RISER_M, "min_tread": MIN_TREAD_M,
        "reason": ("riser and tread are inside the shaped limits" if ok else
                   "the run is too short for this rise, so the tread falls below the minimum. The "
                   "stair is placed where it was drawn; lengthen the run rather than expecting it to "
                   "be adjusted silently"),
    }


def ramp_geometry(rise: float, run: float) -> dict:
    """Slope for a straight ramp and whether it is within the accessible limit. A report, not a gate."""
    if run <= 0:
        return {"slope": None, "slope_ratio": None, "within_limits": None,
                "rise": None, "run": None, "max_slope": MAX_RAMP_SLOPE, "max_slope_ratio": "1:12",
                "reason": "a ramp needs a positive run; nothing was derived"}
    slope = abs(rise) / abs(run)
    ok = slope <= MAX_RAMP_SLOPE + 1e-9
    return {
        "slope": round(slope, 5),
        "slope_ratio": ("1:" + str(round(1 / slope))) if slope > 0 else "level",
        "rise": round(abs(rise), 4), "run": round(abs(run), 4),
        "within_limits": ok, "max_slope": MAX_RAMP_SLOPE, "max_slope_ratio": "1:12",
        "reason": ("slope is within the 1:12 accessible limit" if ok else
                   "slope is steeper than 1:12. The ramp is placed where it was drawn; lengthen the "
                   "run rather than expecting it to be adjusted silently"),
    }
