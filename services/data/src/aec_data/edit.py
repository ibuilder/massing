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

from .edit_annotate import (  # noqa: F401 — re-exported: RECIPES/routers reach these via edit
    add_annotation,
    add_dimension,
    add_revision_cloud,
    add_tag,
)
from .edit_asbuilt import (  # noqa: F401 — re-exported: scene/ebc/detailing + RECIPES reach these via edit
    _coerce,
    asbuilt_summary,
    phase_summary,
    record_asbuilt_dimension,
    set_classification,
    set_element_pset,
    set_manufacturer_info,
    set_phase,
    set_spec_link,
    spec_link_summary,
    verify_asbuilt,
)
from .edit_core import (  # noqa: F401 — re-exported: connections/curtainwall/families import these via edit
    _annotation_context,
    _body_context,
    _box_mesh,
    _element,
    _element_mark,
    _fill_representation,
    _first_storey,
    _rect_profile,
    _wall_thickness,
)
from .edit_enclosure import (  # noqa: F401 — re-exported: RECIPES/routers/generators reach these via edit
    add_covering,
    add_opening,
    add_railing,
    add_roof,
)
from .edit_mep import (  # noqa: F401 — re-exported: routers/RECIPES/nodegraph reach these via edit
    add_comms_device,
    add_fa_device,
    add_fire_equipment,
    add_mep_fitting,
    add_mep_run,
    add_mep_terminal,
    add_riser,
    auto_connect,
    connect_elements,
    connect_mep,
    element_connections,
    set_system_predefined,
)
from .edit_struct import (  # noqa: F401 — re-exported: routers/RECIPES/generators reach these via edit
    _tag_section,
    add_beam,
    add_column,
    add_footing,
    add_rebar,
    add_slab,
    add_steel_beam,
    add_steel_column,
    add_wall,
    extrude_profile,
    set_extrusion_depth,
    set_wall_slope,
)
from .geomconf import geom_workers
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

    import ifcopenshell.geom as geom
    import numpy as np

    # building XY footprint from envelope elements only (exclude site/terrain)
    building = {"ifcwall", "ifcwallstandardcase", "ifcslab", "ifcroof", "ifcwindow",
                "ifcdoor", "ifccolumn", "ifcbeam", "ifcstair", "ifccovering"}
    settings = geom.settings()
    it = geom.iterator(settings, model, geom_workers())
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
        elev_m = float(getattr(storey, "Elevation", 0) or 0) * scale  # file units → metres
        n = 0
        for r in range(rows):
            for c in range(cols):
                if n >= rooms_per_storey:
                    break
                n += 1
                space = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace",
                                             name=f"{storey.Name} - Room {n:02d}")
                space.LongName = f"Room {n:02d}"
                # placement is in METRES (edit_object_placement SI-converts it); w/d are metres
                matrix = np.eye(4)
                matrix[0, 3] = mn[0] + c * w; matrix[1, 3] = mn[1] + r * d; matrix[2, 3] = elev_m
                ifcopenshell.api.run("geometry.edit_object_placement", model, product=space, matrix=matrix)
                # profile dims must be file units (metres ÷ scale) — the API converts only the depth
                profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                                              XDim=w / scale, YDim=d / scale)
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


def place_content(model: ifcopenshell.file, category: str, point, verts=None, faces=None,
                  name: str | None = None, storey: str | None = None) -> dict:
    """CONTENT-1: place a catalogued content item — a crane, porta-john, tree, desk… — as the **right IFC**
    (class + phase + classification), from a supplied detailed mesh (`verts`/`faces`, an imported/vetted
    asset) or a category-sized placeholder box at `point` [E,N] metres. GUID-stable. Returns the placement
    metadata. Unknown categories raise; unsupported IFC classes fall back to a proxy."""
    from . import content

    spec = content.spec(category)
    if spec is None:
        raise ValueError(f"unknown content category {category!r}; see the content catalog")
    px, py = float(point[0]), float(point[1])
    if verts and faces:
        v, f = verts, faces
    else:
        w, d, h = spec["dims"]
        v, f = _box_mesh(px, py, float(w), float(d), float(h))
    nm = name or category.replace("_", " ").title()
    try:
        guid = add_mesh_representation(model, v, f, nm, spec["ifc_class"], storey)
    except Exception:  # noqa: BLE001 — class absent from the schema (e.g. IFC2x3) → proxy
        guid = add_mesh_representation(model, v, f, nm, "IfcBuildingElementProxy", storey)
    if spec["phase"]:
        try:
            set_phase(model, [guid], spec["phase"])
        except Exception:  # noqa: BLE001
            pass
    csys, ccode, ctitle = spec["classification"]
    try:
        set_classification(model, guid, csys, ccode, ctitle)
    except Exception:  # noqa: BLE001 — classification is best-effort
        pass
    return {"guid": guid, "category": category, "ifc_class": model.by_guid(guid).is_a(),
            "phase": spec["phase"], "group": spec["group"], "classification": f"{ccode} {ctitle}"}


def add_mesh_representation(model: ifcopenshell.file, verts, faces, name: str = "Mesh",
                            ifc_class: str = "IfcBuildingElementProxy", storey: str | None = None) -> str:
    """B4: the **procedural-mesh escape hatch** — author an element from a raw triangle mesh
    (`IfcTriangulatedFaceSet`) for geometry the parametric recipes can't express. `verts` is a list of
    [x, y, z] points in metres; `faces` is a list of [i, j, k] **0-based** vertex indices. Placed on the
    storey. GUID-stable. Returns the new element's GUID."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    pts = [[float(c) for c in v[:3]] for v in (verts or [])]
    tris = [[int(i) for i in f[:3]] for f in (faces or [])]
    if len(pts) < 3 or not tris:
        raise ValueError("a mesh needs at least 3 vertices and 1 triangle")
    n = len(pts)
    for t in tris:
        if any(i < 0 or i >= n for i in t):
            raise ValueError("a face index is out of range for the vertex list")
    scale = uunit.calculate_unit_scale(model)                # metres -> file units
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    el = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    matrix = np.eye(4); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=matrix)
    coord_list = model.create_entity(
        "IfcCartesianPointList3D", CoordList=[[c / scale for c in p] for p in pts])
    face_set = model.create_entity(
        "IfcTriangulatedFaceSet", Coordinates=coord_list, Closed=False,
        CoordIndex=[[i + 1 for i in t] for t in tris])       # IFC CoordIndex is 1-based
    rep = model.create_entity(
        "IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body",
        RepresentationType="Tessellation", Items=[face_set])
    ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
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


def copy_element(model: ifcopenshell.file, guid: str, dx: float = 0.0, dy: float = 0.0,
                 dz: float = 0.0) -> str:
    """Duplicate an element (new GUID, deep-copied representation, contained in a storey) and
    offset it by (dx,dy,dz) metres. copy_class alone drops the representation, so deep-copy it."""
    import ifcopenshell.util.element as ue

    el = _element(model, guid)
    new = ifcopenshell.api.run("root.copy_class", model, product=el)
    if el.Representation:
        new.Representation = ue.copy_deep(model, el.Representation)
    st = ue.get_container(el) or _first_storey(model)     # keep the source's storey, not the lowest one
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[new], relating_structure=st)
    if dx or dy or dz:
        move_element(model, new.GlobalId, dx, dy, dz)
    return new.GlobalId


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

    import ifcopenshell.geom as geom
    import ifcopenshell.util.element as ue
    import numpy as np

    templates = {"desk": (1.5, 0.75, 0.75), "table": (2.0, 1.0, 0.75),
                 "bed": (2.0, 1.5, 0.5), "sofa": (2.0, 0.9, 0.8)}
    w, d, h = templates.get(item, templates["desk"])
    body = _body_context(model)

    # per-space footprint bbox from the baked geometry (SI metres, as add_spaces reads it)
    settings = geom.settings()
    it = geom.iterator(settings, model, geom_workers())
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


def program_fit(model: ifcopenshell.file, program: dict, item: str = "desk") -> dict:
    """W9-6b — **headcount program → zones + auto-furnish**: given `{department: headcount}`, allocate
    the model's IfcSpaces to departments (largest rooms to the largest remaining headcounts), stamp
    each allocated space as that department's zone (`LongName` + `Pset_Massing_Program`
    Department/SeatsAllocated), and furnish it with exactly the allocated seats (via the W9-6
    gridder). Returns the allocation report — per department: spaces, seats provided vs asked,
    satisfied/short — plus unallocated spaces. Deterministic; capacity = how many `item`s the
    footprint grids with aisle clearance (the same math the furnisher uses)."""

    import ifcopenshell.geom as geom
    import numpy as np

    if not isinstance(program, dict) or not program:
        raise ValueError("program must be a non-empty {department: headcount} map")
    asks: list[tuple[str, int]] = []
    for dept, n in program.items():
        try:
            count = int(n)
        except (TypeError, ValueError):
            raise ValueError(f"headcount for {dept!r} must be a whole number") from None
        if count < 1:
            raise ValueError(f"headcount for {dept!r} must be at least 1")
        asks.append((str(dept), count))
    asks.sort(key=lambda a: -a[1])                     # biggest department first

    templates = {"desk": (1.5, 0.75, 0.75), "table": (2.0, 1.0, 0.75),
                 "bed": (2.0, 1.5, 0.5), "sofa": (2.0, 0.9, 0.8)}
    w, d, _h = templates.get(item, templates["desk"])
    aisle = 0.8
    cw, cd = w + aisle, d + aisle

    # capacity per space from the baked footprint (same math as furnish_spaces)
    settings = geom.settings()
    it = geom.iterator(settings, model, geom_workers())
    rooms: list[dict] = []
    if it.initialize():
        while True:
            sh = it.get()
            el = model.by_guid(sh.guid)
            if el and el.is_a() == "IfcSpace":
                v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
                if v.size:
                    cols = max(0, int((v[:, 0].max() - v[:, 0].min() - aisle) // cw))
                    rows = max(0, int((v[:, 1].max() - v[:, 1].min() - aisle) // cd))
                    rooms.append({"guid": sh.guid, "name": getattr(el, "Name", None),
                                  "capacity": cols * rows})
            if not it.next():
                break
    rooms.sort(key=lambda r: -r["capacity"])           # biggest room first

    allocation: dict[str, dict] = {dept: {"department": dept, "headcount": n, "seats": 0,
                                          "spaces": []} for dept, n in asks}
    free = list(rooms)
    for dept, n in asks:
        a = allocation[dept]
        while a["seats"] < n and free:
            room = free.pop(0)
            take = min(room["capacity"], n - a["seats"])
            if take <= 0:
                continue
            a["seats"] += take
            a["spaces"].append({**room, "seats": take})
    for a in allocation.values():
        a["satisfied"] = a["seats"] >= a["headcount"]
        a["short_by"] = max(0, a["headcount"] - a["seats"])

    placed_total = 0
    for a in allocation.values():
        for s in a["spaces"]:
            space = model.by_guid(s["guid"])
            space.LongName = f"{a['department']} zone"
            ps = ifcopenshell.api.run("pset.add_pset", model, product=space,
                                      name="Pset_Massing_Program")
            ifcopenshell.api.run("pset.edit_pset", model, pset=ps,
                                 properties={"Department": a["department"],
                                             "SeatsAllocated": int(s["seats"])})
    # furnish each allocated room to its seat count: temporarily grid via furnish_spaces would hit
    # EVERY space — instead reuse its per-room cap by furnishing one room at a time is heavier than
    # needed; the gridder already caps per room, so run it once per distinct cap group
    # (in practice: run per room via the same placement math)
    placed_total = _furnish_allocated(model, allocation, item)

    used = {s["guid"] for a in allocation.values() for s in a["spaces"]}
    return {"item": item,
            "departments": sorted(allocation.values(), key=lambda a: -a["headcount"]),
            "seats_placed": placed_total,
            "seats_asked": sum(n for _, n in asks),
            "all_satisfied": all(a["satisfied"] for a in allocation.values()),
            "unallocated_spaces": [{"guid": r["guid"], "name": r["name"],
                                    "capacity": r["capacity"]}
                                   for r in rooms if r["guid"] not in used],
            "note": "largest-first greedy fit; capacity from the footprint grid with "
                    f"{aisle} m aisle clearance around each {item}"}


def _furnish_allocated(model: ifcopenshell.file, allocation: dict, item: str) -> int:
    """Grid `seats` items into each allocated space (the furnish_spaces placement math, scoped to
    the allocation instead of every space)."""
    import ifcopenshell.geom as geom
    import ifcopenshell.util.element as ue
    import numpy as np

    templates = {"desk": (1.5, 0.75, 0.75), "table": (2.0, 1.0, 0.75),
                 "bed": (2.0, 1.5, 0.5), "sofa": (2.0, 0.9, 0.8)}
    w, d, h = templates.get(item, templates["desk"])
    aisle = 0.8
    cw, cd = w + aisle, d + aisle
    body = _body_context(model)
    targets = {s["guid"]: s["seats"] for a in allocation.values() for s in a["spaces"]}

    settings = geom.settings()
    it = geom.iterator(settings, model, geom_workers())
    boxes: dict[str, tuple] = {}
    if it.initialize():
        while True:
            sh = it.get()
            if sh.guid in targets:
                v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
                if v.size:
                    boxes[sh.guid] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max(),
                                      v[:, 2].min())
            if not it.next():
                break
    placed = 0
    for guid, (x0, y0, x1, y1, z0) in boxes.items():
        space = model.by_guid(guid)
        st = ue.get_container(space) or ue.get_aggregate(space)
        cols = max(0, int((x1 - x0 - aisle) // cw))
        rows = max(0, int((y1 - y0 - aisle) // cd))
        k = 0
        for r in range(rows):
            for c in range(cols):
                if k >= targets[guid]:
                    break
                cx = x0 + aisle / 2 + cw / 2 + c * cw
                cy = y0 + aisle / 2 + cd / 2 + r * cd
                f = ifcopenshell.api.run("root.create_entity", model,
                                         ifc_class="IfcFurnishingElement", name=item.title())
                matrix = np.eye(4)
                matrix[0, 3] = cx
                matrix[1, 3] = cy
                matrix[2, 3] = z0
                ifcopenshell.api.run("geometry.edit_object_placement", model, product=f, matrix=matrix)
                rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                           profile=_rect_profile(model, w, d), depth=h)
                ifcopenshell.api.run("geometry.assign_representation", model, product=f,
                                     representation=rep)
                if st is not None:
                    ifcopenshell.api.run("spatial.assign_container", model, products=[f],
                                         relating_structure=st)
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
    # W9-6b — headcount program → department zones + furnish-to-seat-count
    "program_fit": lambda m, p: program_fit(m, p["program"], p.get("item", "desk")),
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
                                         float(p.get("size", 0.3)), p.get("storey"), p.get("system", "HVAC Supply"),
                                         p.get("discipline", "hvac"), p.get("flow"), p.get("flow_unit")),
    "add_pipe": lambda m, p: add_mep_run(m, "IfcPipeSegment", p["start"], p["end"], "round",
                                         float(p.get("size", 0.05)), p.get("storey"), p.get("system", "Domestic Water"),
                                         p.get("discipline", "plumbing"), p.get("flow"), p.get("flow_unit")),
    "add_cable_tray": lambda m, p: add_mep_run(m, "IfcCableCarrierSegment", p["start"], p["end"], "rect",
                                               float(p.get("size", 0.3)), p.get("storey"), p.get("system", "Power"),
                                               p.get("discipline", "electrical"), p.get("flow"), p.get("flow_unit")),
    "add_wire": lambda m, p: add_mep_run(m, "IfcCableSegment", p["start"], p["end"], "round",
                                         float(p.get("size", 0.02)), p.get("storey"), p.get("system", "Power"),
                                         p.get("discipline", "electrical"), p.get("flow"), p.get("flow_unit")),
    "add_mep_fitting": lambda m, p: add_mep_fitting(m, p["ifc_class"], p["point"], float(p.get("size", 0.3)),
                                                    p.get("predefined", "BEND"), p.get("storey"),
                                                    p.get("system", "MEP"), p.get("discipline")),
    "add_mep_terminal": lambda m, p: add_mep_terminal(m, p["ifc_class"], p["point"],
                                                      float(p.get("width", 0.4)), float(p.get("depth", 0.4)),
                                                      float(p.get("height", 0.4)), p.get("predefined"),
                                                      p.get("storey"), p.get("system"), p.get("discipline")),
    # MEP-FP — fire protection as a first-class distribution system
    "add_sprinkler": lambda m, p: add_mep_terminal(m, "IfcFireSuppressionTerminal", p["point"],
                                                    float(p.get("width", 0.15)), float(p.get("depth", 0.15)),
                                                    float(p.get("height", 0.1)), p.get("predefined", "SPRINKLER"),
                                                    p.get("storey"), p.get("system", "Fire Protection"), "fire"),
    "add_fire_equipment": lambda m, p: add_fire_equipment(m, p.get("kind", "sprinkler"), p["point"],
                                                          p.get("storey"), p.get("system", "Fire Protection")),
    "add_fa_device": lambda m, p: add_fa_device(m, p.get("kind", "smoke_detector"), p["point"],
                                                p.get("storey"), p.get("system", "Fire Alarm")),
    "add_comms_device": lambda m, p: add_comms_device(m, p.get("kind", "idf"), p["point"],
                                                      p.get("storey"), p.get("system", "Telecommunications")),
    "add_riser": lambda m, p: add_riser(m, p["point"], float(p.get("bottom_z", 0.0)), float(p.get("top_z", 3.0)),
                                        float(p.get("size", 0.1)), p.get("ifc_class", "IfcPipeSegment"),
                                        p.get("storey"), p.get("system", "Fire Protection"), p.get("discipline", "fire"),
                                        p.get("flow"), p.get("flow_unit")),
    "set_system_predefined": lambda m, p: set_system_predefined(m, p["system"], p["discipline"]),
    "connect_mep": lambda m, p: connect_mep(m, p["guid_a"], p["guid_b"]),
    # W10-4 — one-pass coincident-port auto-connect over every unconnected MEP element
    "auto_connect_mep": lambda m, p: auto_connect(m, float(p.get("tolerance", 0.05))),
    # B5 — generic element-to-element connection (IfcRelConnectsElements, LOD-350 coordination)
    "connect_elements": lambda m, p: connect_elements(m, p["guid_a"], p["guid_b"], p.get("description")),
    # A1 — sandboxed ifcopenshell escape hatch (gated by AEC_ALLOW_IFC_CODE; AST-whitelisted)
    "execute_ifc_code": lambda m, p: _sandbox().execute_ifc_code(m, p["code"]),
    # B3 — sloped-top wall (parapet slope / shed / gable)
    "set_wall_slope": lambda m, p: set_wall_slope(m, p["guid"], p["start_height"], p["end_height"]),
    # E3 — sketch-to-BIM: closed profile → extruded element; pull an existing extrusion's depth
    "extrude_profile": lambda m, p: extrude_profile(
        m, p["points"], float(p.get("height", 3.0)), p.get("ifc_class", "IfcBuildingElementProxy"),
        p.get("name"), p.get("storey"), float(p.get("z", 0.0))),
    "set_extrusion_depth": lambda m, p: set_extrusion_depth(m, p["guid"], float(p["depth"])),
    # B4 — procedural-mesh escape hatch (IfcTriangulatedFaceSet)
    "add_mesh_representation": lambda m, p: add_mesh_representation(
        m, p["verts"], p["faces"], p.get("name", "Mesh"),
        p.get("ifc_class", "IfcBuildingElementProxy"), p.get("storey")),
    # UX-2 — 2D text annotation as an IfcAnnotation (note / tag / callout)
    "add_annotation": lambda m, p: add_annotation(m, p["point"], p["text"], p.get("kind", "note"),
                                                  p.get("storey"), float(p.get("z", 0.0))),
    # UX-2 — dimension annotation between two points (start/end guarded for finiteness + distinctness)
    "add_dimension": lambda m, p: add_dimension(m, p["start"], p["end"], p.get("text"),
                                                p.get("storey"), float(p.get("z", 0.0))),
    # UX-2 — revision cloud around a region (>=3 points, or 2 opposite corners) + optional delta/number tag
    "add_revision_cloud": lambda m, p: add_revision_cloud(m, p["points"], p.get("tag"),
                                                          p.get("storey"), float(p.get("z", 0.0))),
    # UX-2 — element-aware tag: label auto-read from the host element (Name / mark / type), assigned to it
    "add_tag": lambda m, p: add_tag(m, p["host_guid"], p.get("text"), p.get("storey"),
                                    None if p.get("z") is None else float(p["z"])),
    # CONTENT-1 — place a catalogued content item (logistics / furniture / landscaping) as the right IFC
    "place_content": lambda m, p: place_content(
        m, p["category"], p["point"], p.get("verts"), p.get("faces"), p.get("name"), p.get("storey")),
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
    # W11 G1 — LOD-500 field-verified as-built stamp
    "verify_asbuilt": lambda m, p: verify_asbuilt(m, p["guids"], p.get("verified_by", ""),
                                                  p.get("method", "field-measure"), p.get("note", ""),
                                                  p.get("date")),
    # W11 G3 — manufacturer / serial info for the LOD-500 / O&M / turnover layer
    "set_manufacturer_info": lambda m, p: set_manufacturer_info(
        m, p["guids"], p.get("manufacturer", ""), p.get("model_label", ""),
        p.get("production_year", ""), p.get("serial", ""), p.get("barcode", "")),
    # W11 G2 — field-verified as-built dimension + variance
    "record_asbuilt_dimension": lambda m, p: record_asbuilt_dimension(
        m, p["guids"], p.get("dimension", "Length"), p["measured"], p.get("design"),
        float(p.get("tolerance", 0.01))),
    # W11 F0 — the representation/context spine + LOD stage
    "ensure_contexts": lambda m, p: _rep().ensure_contexts(m),
    "set_lod": lambda m, p: _rep().set_lod(m, p["guids"], p.get("stage", "300")),
    # W11 F0b — derive coarse Box/Axis/FootPrint views from Body geometry (bounds-based)
    "derive_representations": lambda m, p: _rep().derive_representations(
        m, p.get("guids"), tuple(p.get("kinds") or ("Box", "Axis", "FootPrint"))),
    # W11 SpecLink — the per-element spec-section breadcrumb (Pset_Massing_SpecLink)
    "set_spec_link": lambda m, p: set_spec_link(m, p["guids"], p["section"],
                                                p.get("title"), p.get("url")),
    # W11 Track D carrier layer — classification (keynote/spec code) + document (detail/instruction)
    "classify": lambda m, p: _det().classify(m, p["guids"], p["system"], p["code"],
                                             p.get("name"), p.get("edition")),
    "attach_document": lambda m, p: _det().attach_document(m, p["guids"], p["name"], p.get("location"),
                                                          p.get("description"), p.get("identification"),
                                                          p.get("purpose")),
    # G3: O&M / warranty document reference (a purpose-tagged attach_document) — turnover paperwork bound
    # to the physical asset; surfaced in asbuilt_summary.with_om_docs
    "attach_om_document": lambda m, p: _det().attach_document(
        m, p["guids"], p["name"], p.get("location"), p.get("description"), p.get("identification"),
        "WARRANTY" if str(p.get("kind", "om")).strip().lower().startswith("warr") else "OPERATION_MAINTENANCE"),
    # W11 D3 — auto-detail: evaluate the condition→content rule set, write matched code/detail bundles
    "apply_detailing_rules": lambda m, p: _rules().apply_rules(m, p.get("rules"), p.get("ibc_edition")),
    # W11 B6 — structural steel connections (fabrication LOD 350/400)
    "add_base_plate": lambda m, p: _conn().add_base_plate(m, p["column_guid"], float(p.get("width", 0.4)),
                                                          float(p.get("depth", 0.4)), float(p.get("thickness", 0.025)),
                                                          int(p.get("bolts", 4)), storey=p.get("storey")),
    "add_shear_tab": lambda m, p: _conn().add_shear_tab(m, p["beam_guid"], float(p.get("thickness", 0.01)),
                                                        float(p.get("depth", 0.2)), float(p.get("width", 0.1)),
                                                        int(p.get("bolts", 2)), storey=p.get("storey")),
    # B5 — generic fastener/connection assembly with IfcRelConnectsWithRealizingElements semantics
    "add_connection_assembly": lambda m, p: _conn().add_connection_assembly(
        m, p["guid_a"], p["guid_b"], p.get("kind", "bolted"), int(p.get("bolts", 4)),
        float(p.get("bolt_dia", 0.02)), float(p.get("plate_size", 0.25)),
        float(p.get("plate_thickness", 0.012)), p.get("storey")),
    "add_rebar_cage": lambda m, p: _rebar().add_rebar_cage(m, p["column_guid"], p.get("bar_size", "#8"),
                                                          p.get("tie_size", "#3"), float(p.get("cover", 0.04)),
                                                          float(p.get("tie_spacing", 0.25)), p.get("storey")),
    "derive_analytical": lambda m, p: _analytical().derive_analytical(m, p.get("name", "Analytical model")),
    "apply_structural_loads": lambda m, p: _analytical().apply_member_loads(
        m, float(p.get("dead_klf", 1.0)), float(p.get("live_klf", 0.5))),
    "apply_structural_supports": lambda m, p: _analytical().apply_supports(m, str(p.get("kind", "pinned"))),
    "add_curtain_wall": lambda m, p: _cw().add_curtain_wall(m, p["start"], p["end"], float(p.get("height", 3.5)),
                                                           int(p.get("cols", 3)), int(p.get("rows", 2)),
                                                           float(p.get("mullion", 0.06)),
                                                           float(p.get("panel_thickness", 0.03)), p.get("storey")),
}


def _cw():
    """Lazy handle to the curtain-wall module."""
    from . import curtainwall
    return curtainwall


def _rebar():
    """Lazy handle to the reinforcement-detailing module."""
    from . import rebar
    return rebar


def _conn():
    """Lazy handle to the connections module (it imports edit helpers → avoid a cycle)."""
    from . import connections
    return connections


def _analytical():
    """Lazy handle to the structural analytical-model engine (W10-7)."""
    from . import analytical
    return analytical


def _rules():
    """Lazy handle to the detailing rule engine."""
    from . import rules
    return rules


def _sandbox():
    """Lazy handle to the A1 sandboxed code executor."""
    from . import sandbox
    return sandbox


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


def apply_recipe(ifc_path: str, recipe: str, params: dict, out_path: str) -> dict:
    """Apply a recipe to the IFC and save a new file. GUIDs of existing elements are
    preserved, so downstream pins/RFIs/clashes (keyed by GUID) survive."""
    if recipe not in RECIPES:
        raise ValueError(f"unknown recipe {recipe!r}; have {list(RECIPES)}")
    from . import guards  # E8 — reject a broken edit before it touches the model
    pre = guards.precheck(recipe, params)
    if not pre["ok"]:
        raise ValueError("; ".join(pre["errors"]))
    model = open_model(ifc_path)
    # E8 (model-aware): references must exist in THIS model — a hallucinated GUID, a typo'd storey,
    # or a door hosted on a slab is rejected before any mutation
    mpre = guards.model_precheck(model, recipe, params)
    if not mpre["ok"]:
        raise ValueError("; ".join(mpre["errors"]))
    changed = RECIPES[recipe](model, params)
    model.write(out_path)
    return {"recipe": recipe, "changed": changed, "out": out_path}


def apply_recipes(ifc_path: str, steps: list[dict], out_path: str) -> dict:
    """S4 — apply a SEQUENCE of `{recipe, params}` steps as ONE new version: the model opens once,
    every step mutates it in memory, and a single file is written — so a multi-step NL command (or
    any scripted batch) is one edit-history entry and undoes as **one step**, not N. Every step is
    guard-prechecked BEFORE anything runs (all-or-nothing: a bad step aborts the whole batch with
    nothing written); an unknown recipe fails the same way."""
    if not steps:
        raise ValueError("empty step list")
    from . import guards
    for i, s in enumerate(steps):
        recipe = s.get("recipe")
        if recipe not in RECIPES:
            raise ValueError(f"step {i + 1}: unknown recipe {recipe!r}; have {list(RECIPES)}")
        pre = guards.precheck(recipe, s.get("params") or {})
        if not pre["ok"]:
            raise ValueError(f"step {i + 1} ({recipe}): " + "; ".join(pre["errors"]))
    model = open_model(ifc_path)
    # E8 note: NO model-aware precheck on batches — a step may legally reference an element (or a
    # storey) a PRIOR step in the same batch creates, which can't be known up front. Single-recipe
    # applies get the full model_precheck; wired dependent flows use /edit/graph.
    results = []
    for s in steps:
        results.append({"recipe": s["recipe"],
                        "changed": RECIPES[s["recipe"]](model, s.get("params") or {})})
    model.write(out_path)
    return {"steps": results, "step_count": len(results), "out": out_path}
