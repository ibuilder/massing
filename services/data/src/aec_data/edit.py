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
        out.append({"guid": t.GlobalId, "name": name, "ifc_class": t.is_a(),
                    "has_geometry": bool(getattr(t, "RepresentationMaps", None))})
    out.sort(key=lambda x: (x["ifc_class"], x["name"]))
    return out


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
    import numpy as np

    import ifcopenshell.util.unit as uunit
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
               depth: float = 0.4, storey: str | None = None) -> str:
    """Author an IfcColumn at an XY point (meters): a rectangular profile extruded to `height`."""
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
    profile = _rect_profile(model, float(width), float(depth))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=profile, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=col, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[col], relating_structure=st)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=col, name="Pset_ColumnCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"LoadBearing": True})
    return col.GlobalId


def add_beam(model: ifcopenshell.file, start, end, width: float = 0.3, depth: float = 0.5,
             storey: str | None = None) -> str:
    """Author an IfcBeam between two XY points (meters): a rectangular cross-section swept
    horizontally along the start→end axis at the storey elevation."""
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


def add_roof(model: ifcopenshell.file, points, thickness: float = 0.3,
             storey: str | None = None) -> str:
    """Author a flat IfcRoof from a polygon of XY points (meters) extruded by `thickness`
    at the storey elevation. (Pitched roofs are a future enhancement.)"""
    import numpy as np

    import ifcopenshell.util.unit as uunit
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


def add_opening(model: ifcopenshell.file, host_guid: str, width: float = 0.9, height: float = 2.1,
                sill: float = 0.0, kind: str = "door", storey: str | None = None,
                position=None) -> str:
    """Cut an opening in the host wall (IfcOpeningElement voiding it) and fill it with an
    IfcDoor/IfcWindow. `kind` ∈ door|window; `sill` is the bottom height (m). `position` is an
    optional [E,N] plan point — projected onto the wall axis to place the opening there;
    omit it to center on the wall."""
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
    panel = _rect_profile(model, float(width), 0.06)
    prep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=panel, depth=float(height))
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
    import numpy as np

    import ifcopenshell.util.unit as uunit
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
    """Place a starter-library family (furniture/sanitary/appliance/plant) by catalog key."""
    from . import families  # lazy — families lazily imports edit, so this avoids an import cycle
    return families.add_family(model, p["family"], p.get("storey"), p.get("position"))


# recipe registry — what an API endpoint / Bonsai-MCP can invoke by name
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
                                         p.get("storey"), p.get("position")),
    "add_window": lambda m, p: add_opening(m, p["host_guid"], float(p.get("width", 1.2)),
                                           float(p.get("height", 1.2)), float(p.get("sill", 0.9)), "window",
                                           p.get("storey"), p.get("position")),
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
