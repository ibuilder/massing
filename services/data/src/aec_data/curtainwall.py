"""W11 · B6 — curtain-wall systems.

A real curtain wall is not one panel — it's an `IfcCurtainWall` that **aggregates** a grid of framing
(`IfcMember`, vertical mullions + horizontal transoms) and glazing (`IfcPlate`, CURTAIN_PANEL) on a
cols×rows layout. This authors that assembly along a start→end line at a height, oriented to the wall
axis, GUID-stable. Profile dims go through the unit-scale-correct `_rect_profile`; part placements carry
the axis rotation in world coordinates (metres — the SI-converting placement API handles the unit).
"""
from __future__ import annotations

import math

import ifcopenshell
import ifcopenshell.api
import numpy as np


def _set_pd(el, value: str) -> None:
    if hasattr(el, "PredefinedType"):
        try:
            el.PredefinedType = value
        except Exception:  # noqa: BLE001 — enum not in this schema
            pass


def add_curtain_wall(model: ifcopenshell.file, start, end, height: float = 3.5, cols: int = 3,
                     rows: int = 2, mullion: float = 0.06, panel_thickness: float = 0.03,
                     storey: str | None = None) -> dict:
    """Author an `IfcCurtainWall` from `start`→`end` (XY metres) at `height` m: `cols`×`rows` glazing
    panels bounded by vertical **mullions** (cols+1) and horizontal **transoms** (rows+1) — all
    `IfcMember`/`IfcPlate`, aggregated under the curtain wall and contained in the storey. Returns
    {curtain_wall, mullions, transoms, panels}. GUID-stable."""
    import ifcopenshell.util.unit as uunit

    from .edit import _body_context, _first_storey, _rect_profile

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy) or 1.0
    dx, dy = (ex - sx) / length, (ey - sy) / length          # unit axis (X of the wall frame)
    cols = max(1, int(cols))
    rows = max(1, int(rows))
    cw_h = float(height)
    cell_w, cell_h = length / cols, cw_h / rows

    def _mat(x_axis, y_axis, z_axis, lx, lz):
        """World placement (metres) for a part at local (lx along wall, 0 out-of-plane, lz up)."""
        wx, wy, wz = sx + lx * dx, sy + lx * dy, elev + lz
        m = np.eye(4)
        m[0:3, 0], m[0:3, 1], m[0:3, 2] = x_axis, y_axis, z_axis
        m[0:3, 3] = (wx, wy, wz)
        return m

    axis = np.array([dx, dy, 0.0])                           # along the wall
    out = np.array([-dy, dx, 0.0])                           # out of plane (thickness dir)
    up = np.array([0.0, 0.0, 1.0])

    def _extrude(el, prof_x, prof_y, depth):
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=_rect_profile(model, prof_x, prof_y), depth=float(depth))
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)

    cw = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCurtainWall", name="Curtain wall")
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=cw, matrix=_mat(axis, out, up, 0, 0))

    parts: list = []
    # vertical mullions (extruded up Z): cross-section mullion×mullion, at each column boundary
    n_mull = 0
    for i in range(cols + 1):
        mem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcMember", name="Mullion")
        _set_pd(mem, "MULLION")
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=mem,
                             matrix=_mat(axis, out, up, i * cell_w, 0))
        _extrude(mem, mullion, mullion, cw_h)
        parts.append(mem); n_mull += 1
    # horizontal transoms (extruded along the wall axis): local Z = wall axis, at each row boundary
    n_tran = 0
    for j in range(rows + 1):
        mem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcMember", name="Transom")
        _set_pd(mem, "MULLION")                              # IfcMemberTypeEnum has no TRANSOM; MULLION is used
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=mem,
                             matrix=_mat(up, out, axis, 0, j * cell_h))
        _extrude(mem, mullion, mullion, length)
        parts.append(mem); n_tran += 1
    # glazing panels (thin plate per cell): profile = cell_w × panel_thickness, extruded up cell_h
    n_pan = 0
    for i in range(cols):
        for j in range(rows):
            pan = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcPlate", name="Glazing")
            _set_pd(pan, "CURTAIN_PANEL")
            ifcopenshell.api.run("geometry.edit_object_placement", model, product=pan,
                                 matrix=_mat(axis, out, up, i * cell_w + cell_w / 2, j * cell_h))
            _extrude(pan, cell_w, panel_thickness, cell_h)
            parts.append(pan); n_pan += 1

    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[cw], relating_structure=st)
    ifcopenshell.api.run("aggregate.assign_object", model, products=parts, relating_object=cw)
    return {"curtain_wall": cw.GlobalId, "mullions": n_mull, "transoms": n_tran, "panels": n_pan}
