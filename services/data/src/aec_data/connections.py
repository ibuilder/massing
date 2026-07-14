"""W11 · B6 — structural steel connections (fabrication-level LOD 350/400).

Bare members (columns/beams) are LOD 300 — "the ability to construct." A **connection** is what takes
them to LOD 350/400: the base plate + anchor bolts under a column, the shear tab + bolts joining a beam to
a column. Each is authored as small IFC elements (`IfcPlate`, `IfcMechanicalFastener`) grouped with the
member into an `IfcElementAssembly` — a fabrication/shop assembly. GUID-stable; pure ifcopenshell.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import numpy as np


def _member(model: ifcopenshell.file, guid: str, classes: tuple[str, ...]):
    el = next((e for e in model.by_type("IfcElement") if e.GlobalId == guid and e.is_a() in classes), None)
    if el is None:
        raise ValueError(f"{guid} is not a {' / '.join(classes)} (select one first)")
    return el


def _base_xyz(model, el) -> tuple[float, float, float]:
    """Element origin in metres (its ObjectPlacement translation)."""
    import ifcopenshell.util.placement as up
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(model)
    m = np.array(up.get_local_placement(el.ObjectPlacement), dtype=float)
    return float(m[0, 3]) * scale, float(m[1, 3]) * scale, float(m[2, 3]) * scale


def _set_predefined(el, value: str) -> None:
    if value and hasattr(el, "PredefinedType"):
        try:
            el.PredefinedType = value
        except Exception:  # noqa: BLE001 — invalid enum for the schema, skip
            pass


def _place(model, el, x: float, y: float, z: float) -> None:
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=m)


def _circle(model, radius: float):
    return model.create_entity(
        "IfcCircleProfileDef", ProfileType="AREA", Radius=radius,
        Position=model.create_entity("IfcAxis2Placement2D",
                                     Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0))))


def add_base_plate(model: ifcopenshell.file, column_guid: str, width: float = 0.4, depth: float = 0.4,
                   thickness: float = 0.025, bolts: int = 4, bolt_dia: float = 0.024,
                   storey: str | None = None) -> dict:
    """B6: author a **base plate + anchor bolts** under a column and group them with the column into an
    `IfcElementAssembly` (a fabrication assembly). The plate (`IfcPlate`) sits just below the column base;
    up to 4 anchor bolts (`IfcMechanicalFastener`, ANCHORBOLT) at the plate corners. Returns
    {assembly, plate, bolts, column}. GUID-stable."""
    from .edit import _body_context, _first_storey, _rect_profile

    col = _member(model, column_guid, ("IfcColumn",))
    body = _body_context(model)
    cx, cy, cz = _base_xyz(model, col)

    made: list[str] = []
    # base plate — rectangle width×depth extruded by `thickness`, its top face at the column base (cz)
    plate = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcPlate", name="Base plate")
    _set_predefined(plate, "SHEET")
    _place(model, plate, cx, cy, cz - thickness)
    prof = _rect_profile(model, float(width), float(depth))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=prof, depth=float(thickness))
    ifcopenshell.api.run("geometry.assign_representation", model, product=plate, representation=rep)
    made.append(plate.GlobalId)

    # anchor bolts at the corners (inset by an edge distance), extending below and through the plate
    inset = min(width, depth) * 0.16
    hx, hy = width / 2 - inset, depth / 2 - inset
    corners = [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)]
    embed = 0.20
    for i in range(max(0, min(int(bolts), 4))):
        dx, dy = corners[i]
        bolt = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcMechanicalFastener",
                                    name="Anchor bolt")
        _set_predefined(bolt, "ANCHORBOLT")
        _place(model, bolt, cx + dx, cy + dy, cz - thickness - embed)
        brep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                    profile=_circle(model, float(bolt_dia) / 2), depth=embed + thickness + 0.03)
        ifcopenshell.api.run("geometry.assign_representation", model, product=bolt, representation=brep)
        made.append(bolt.GlobalId)

    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model,
                             products=[model.by_guid(g) for g in made], relating_structure=st)

    from . import groups
    asm = groups.create_assembly(model, f"Base connection {col.Name or ''}".strip(),
                                 [column_guid, *made], predefined="RIGID_FRAME")
    return {"assembly": asm["guid"], "plate": made[0], "bolts": len(made) - 1, "column": column_guid}


def add_shear_tab(model: ifcopenshell.file, beam_guid: str, thickness: float = 0.01, depth: float = 0.2,
                  width: float = 0.1, bolts: int = 2, bolt_dia: float = 0.02,
                  storey: str | None = None) -> dict:
    """B6: author a **shear-tab plate + bolts** at a beam end (a simple beam-to-column shear connection)
    and assemble it with the beam. The tab (`IfcPlate`) sits at the beam's start; bolts run vertically
    through it. Returns {assembly, plate, bolts, beam}. GUID-stable."""
    from .edit import _body_context, _first_storey, _rect_profile

    beam = _member(model, beam_guid, ("IfcBeam",))
    body = _body_context(model)
    bx, by, bz = _base_xyz(model, beam)

    made: list[str] = []
    tab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcPlate", name="Shear tab")
    _set_predefined(tab, "SHEET")
    _place(model, tab, bx, by, bz - depth / 2)
    prof = _rect_profile(model, float(thickness), float(width))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=prof, depth=float(depth))
    ifcopenshell.api.run("geometry.assign_representation", model, product=tab, representation=rep)
    made.append(tab.GlobalId)

    for i in range(max(0, min(int(bolts), 4))):
        dz = depth * (0.3 + 0.4 * i / max(1, int(bolts) - 1)) if int(bolts) > 1 else depth / 2
        bolt = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcMechanicalFastener",
                                    name="Bolt")
        _set_predefined(bolt, "BOLT")
        _place(model, bolt, bx - 0.05, by, bz - depth / 2 + dz)
        # horizontal bolt through the tab (extruded along +X via a rotated placement is overkill;
        # a short vertical stud reads fine at LOD 350)
        brep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                    profile=_circle(model, float(bolt_dia) / 2), depth=0.12)
        ifcopenshell.api.run("geometry.assign_representation", model, product=bolt, representation=brep)
        made.append(bolt.GlobalId)

    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model,
                             products=[model.by_guid(g) for g in made], relating_structure=st)

    from . import groups
    asm = groups.create_assembly(model, f"Shear connection {beam.Name or ''}".strip(),
                                 [beam_guid, *made], predefined="RIGID_FRAME")
    return {"assembly": asm["guid"], "plate": made[0], "bolts": len(made) - 1, "beam": beam_guid}
