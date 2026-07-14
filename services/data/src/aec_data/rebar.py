"""W11 · B6 — reinforcement detailing (rebar cages): the LOD-400 rebar for a concrete column.

A bare `add_rebar` is a single straight bar. A **cage** is the real detailing: longitudinal (vertical)
corner bars + transverse stirrups/ties at a spacing, sized with concrete cover, as `IfcReinforcingBar`
elements with proper **swept-disk** geometry (a disk of the bar radius swept along the bar's centreline —
the research-recommended way to model reinforcement). The bars are grouped with the host column into an
`IfcElementAssembly` (a reinforcement cage). GUID-stable; pure ifcopenshell.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import numpy as np


def _column(model: ifcopenshell.file, guid: str):
    el = next((e for e in model.by_type("IfcColumn") if e.GlobalId == guid), None)
    if el is None:
        raise ValueError(f"{guid} is not a column (select a concrete column)")
    return el


def _column_box(model, col):
    """(cx, cy, cz, w, d, h) in metres from a rectangular column's placement + extruded rect profile."""
    import ifcopenshell.util.placement as up
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(model)
    m = np.array(up.get_local_placement(col.ObjectPlacement), dtype=float)
    cx, cy, cz = float(m[0, 3]) * scale, float(m[1, 3]) * scale, float(m[2, 3]) * scale
    solid = None
    for r in (col.Representation.Representations if col.Representation else []):
        for it in (r.Items or []):
            if it.is_a("IfcExtrudedAreaSolid") and it.SweptArea and it.SweptArea.is_a("IfcRectangleProfileDef"):
                solid = it
                break
        if solid:
            break
    if solid is None:
        raise ValueError("column has no rectangular extruded body (need a rectangular concrete column)")
    w = float(solid.SweptArea.XDim) * scale
    d = float(solid.SweptArea.YDim) * scale
    h = float(solid.Depth) * scale
    return cx, cy, cz, w, d, h


def _swept_bar(model, body, name, directrix_pts, radius, closed=False):
    """An IfcReinforcingBar whose geometry is a disk of `radius` swept along `directrix_pts` (world XYZ,
    metres) — straight for a longitudinal bar, a closed rectangle for a stirrup. Identity placement, so
    the directrix carries absolute coordinates."""
    bar = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcReinforcingBar", name=name)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=bar, matrix=np.eye(4))
    pts = [model.create_entity("IfcCartesianPoint", (float(x), float(y), float(z))) for x, y, z in directrix_pts]
    if closed:
        pts.append(pts[0])
    poly = model.create_entity("IfcPolyline", Points=pts)
    solid = model.create_entity("IfcSweptDiskSolid", Directrix=poly, Radius=float(radius))
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body,
                              RepresentationIdentifier="Body", RepresentationType="AdvancedSweptSolid",
                              Items=[solid])
    ifcopenshell.api.run("geometry.assign_representation", model, product=bar, representation=rep)
    return bar


def add_rebar_cage(model: ifcopenshell.file, column_guid: str, bar_size: str = "#8",
                   tie_size: str = "#3", cover: float = 0.04, tie_spacing: float = 0.25,
                   storey: str | None = None) -> dict:
    """B6: author a **reinforcement cage** in a rectangular concrete column — 4 longitudinal corner bars +
    stirrups at `tie_spacing`, offset by `cover`, as swept-disk `IfcReinforcingBar`s, grouped with the
    column into an `IfcElementAssembly`. Returns {assembly, bars, ties, column}. GUID-stable."""
    from . import steel
    from .edit import _body_context, _first_storey

    col = _column(model, column_guid)
    cx, cy, cz, w, d, h = _column_box(model, col)
    body = _body_context(model)
    bar_r = steel.rebar_diameter(bar_size) / 2.0
    tie_r = steel.rebar_diameter(tie_size) / 2.0
    hx, hy = w / 2 - cover, d / 2 - cover
    if hx <= 0 or hy <= 0:
        raise ValueError("cover too large for the column size")

    made: list[str] = []
    # 4 longitudinal corner bars (bottom cover → top cover)
    z0, z1 = cz + cover, cz + h - cover
    for dx, dy in [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)]:
        bar = _swept_bar(model, body, "Rebar", [(cx + dx, cy + dy, z0), (cx + dx, cy + dy, z1)], bar_r)
        made.append(bar.GlobalId)
    n_bars = len(made)

    # transverse stirrups/ties along the height
    n_ties = max(2, int(round((h - 2 * cover) / max(tie_spacing, 0.05))) + 1)
    corners = [(cx + hx, cy + hy), (cx - hx, cy + hy), (cx - hx, cy - hy), (cx + hx, cy - hy)]
    for i in range(n_ties):
        z = z0 + i * (z1 - z0) / (n_ties - 1)
        tie = _swept_bar(model, body, "Stirrup", [(x, y, z) for x, y in corners], tie_r, closed=True)
        made.append(tie.GlobalId)
    n_ties_made = len(made) - n_bars

    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model,
                             products=[model.by_guid(g) for g in made], relating_structure=st)

    from . import groups
    asm = groups.create_assembly(model, f"Rebar cage {col.Name or ''}".strip(),
                                 [column_guid, *made])
    return {"assembly": asm["guid"], "bars": n_bars, "ties": n_ties_made, "column": column_guid}
