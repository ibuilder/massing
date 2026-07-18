"""REL-3 leaf: 2D annotation authoring recipes — notes, dimensions, revision clouds, element tags.

The drawing-annotation recipe group split off `edit.py`: text notes, dimension lines with computed
labels, scalloped revision clouds with rev tags, and element-aware tags — all authored as IfcAnnotation
in the 2D Annotation subcontext so they render on the generated plans. Built on the `edit_core`
primitives (annotation context, element-mark, storey lookup) — never on another recipe. `edit.py`
re-exports every name, so `edit.add_annotation` / `edit.add_tag` importers (RECIPES, routers) are
unchanged.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api

from .edit_core import _annotation_context, _element_mark, _first_storey


def add_annotation(model: ifcopenshell.file, point, text: str, kind: str = "note",
                   storey: str | None = None, z: float = 0.0) -> str:
    """UX-2: place a 2D **text annotation** as an `IfcAnnotation` (an `IfcTextLiteral` in the Annotation
    context) at an [E, N] point — a model note / tag / callout that round-trips as real IFC and can feed the
    drawing generator. `kind` tags the ObjectType (note / tag / callout). GUID-stable. Returns the GUID."""
    import numpy as np

    txt = str(text or "").strip()
    if not txt:
        raise ValueError("annotation text is required")
    ctx = _annotation_context(model)
    ann = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcAnnotation", name=txt[:64])
    if hasattr(ann, "ObjectType"):
        ann.ObjectType = (kind or "note").strip().lower()
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = float(point[0]), float(point[1]), float(z)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=ann, matrix=m)
    place = model.create_entity("IfcAxis2Placement2D",
                                Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)))
    lit = model.create_entity("IfcTextLiteral", Literal=txt, Placement=place, Path="RIGHT")
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=ctx,
                              RepresentationIdentifier="Annotation", RepresentationType="Annotation2D",
                              Items=[lit])
    ifcopenshell.api.run("geometry.assign_representation", model, product=ann, representation=rep)
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[ann], relating_structure=st)
    return ann.GlobalId


def add_dimension(model: ifcopenshell.file, start, end, text: str | None = None,
                  storey: str | None = None, z: float = 0.0) -> dict:
    """UX-2: place a **dimension** annotation between two [E, N] points as an `IfcAnnotation` — a dimension
    line (`IfcPolyline` start→end) plus the measured distance as an `IfcTextLiteral` at the midpoint, in the
    Annotation context. `text` overrides the auto-computed distance label. Round-trips as real IFC and feeds
    the drawing generator. GUID-stable. Returns {guid, distance_m}."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    x1, y1 = float(start[0]), float(start[1])
    x2, y2 = float(end[0]), float(end[1])
    dist = math.hypot(x2 - x1, y2 - y1)
    if dist < 1e-6:
        raise ValueError("a dimension needs two distinct points")
    label = (text or f"{dist:.2f} m").strip()
    ctx = _annotation_context(model)
    ann = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcAnnotation", name=label)
    if hasattr(ann, "ObjectType"):
        ann.ObjectType = "dimension"
    mtx = np.eye(4); mtx[2, 3] = float(z)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=ann, matrix=mtx)
    pts = [model.create_entity("IfcCartesianPoint", (x1 / scale, y1 / scale)),
           model.create_entity("IfcCartesianPoint", (x2 / scale, y2 / scale))]
    line = model.create_entity("IfcPolyline", Points=pts)
    place = model.create_entity("IfcAxis2Placement2D",
                                Location=model.create_entity("IfcCartesianPoint",
                                                             ((x1 + x2) / 2 / scale, (y1 + y2) / 2 / scale)))
    lit = model.create_entity("IfcTextLiteral", Literal=label, Placement=place, Path="RIGHT")
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=ctx,
                              RepresentationIdentifier="Annotation", RepresentationType="Annotation2D",
                              Items=[line, lit])
    ifcopenshell.api.run("geometry.assign_representation", model, product=ann, representation=rep)
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[ann], relating_structure=st)
    return {"guid": ann.GlobalId, "distance_m": round(dist, 3)}


def add_revision_cloud(model: ifcopenshell.file, points, tag: str | None = None,
                       storey: str | None = None, z: float = 0.0) -> dict:
    """UX-2: place a **revision cloud** as an `IfcAnnotation` (ObjectType "revision") — a scalloped closed
    `IfcPolyline` around the [E, N] region `points` (a rectangle if two corner points are given), plus an
    optional revision `tag` (delta/number) as an `IfcTextLiteral`. Round-trips as real IFC and renders on the
    generated plan (drawing.plan_svg). GUID-stable. Returns {guid, bumps}."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    pts_in = [[float(p[0]), float(p[1])] for p in (points or [])]
    if len(pts_in) == 2:                                       # two corners → rectangle loop
        (ax, ay), (bx, by) = pts_in
        pts_in = [[ax, ay], [bx, ay], [bx, by], [ax, by]]
    if len(pts_in) < 3:
        raise ValueError("a revision cloud needs a region: >=3 points, or 2 opposite corners")

    scale = uunit.calculate_unit_scale(model)
    # scalloped outline: walk each edge, emitting outward arcs (bumps) as short chords
    bump = 0.6 / scale                                         # ~0.6 m bump radius in file units
    loop = pts_in + [pts_in[0]]
    verts: list[tuple[float, float]] = []
    bumps = 0
    for (x1, y1), (x2, y2) in zip(loop, loop[1:]):
        seg = math.hypot(x2 - x1, y2 - y1) / scale
        n = max(2, int(seg / 1.2))                            # a bump roughly every ~1.2 m
        nx, ny = (y2 - y1), -(x2 - x1)                        # outward normal (CW loop → outward)
        nrm = math.hypot(nx, ny) or 1.0
        nx, ny = nx / nrm, ny / nrm
        for i in range(n):
            t0, tm = i / n, (i + 0.5) / n
            verts.append(((x1 + (x2 - x1) * t0) / scale, (y1 + (y2 - y1) * t0) / scale))
            verts.append(((x1 + (x2 - x1) * tm) / scale + nx * bump,
                          (y1 + (y2 - y1) * tm) / scale + ny * bump))
            bumps += 1
    verts.append((pts_in[0][0] / scale, pts_in[0][1] / scale))

    ctx = _annotation_context(model)
    label = (tag or "").strip()
    ann = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcAnnotation",
                               name=(f"Revision {label}".strip() or "Revision"))
    if hasattr(ann, "ObjectType"):
        ann.ObjectType = "revision"
    mtx = np.eye(4); mtx[2, 3] = float(z)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=ann, matrix=mtx)
    poly = model.create_entity("IfcPolyline",
                               Points=[model.create_entity("IfcCartesianPoint", (float(x), float(y)))
                                       for x, y in verts])
    items = [poly]
    if label:
        place = model.create_entity("IfcAxis2Placement2D",
                                    Location=model.create_entity("IfcCartesianPoint",
                                                                 (pts_in[0][0] / scale, pts_in[0][1] / scale)))
        items.append(model.create_entity("IfcTextLiteral", Literal=label, Placement=place, Path="RIGHT"))
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=ctx,
                              RepresentationIdentifier="Annotation", RepresentationType="Annotation2D",
                              Items=items)
    ifcopenshell.api.run("geometry.assign_representation", model, product=ann, representation=rep)
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[ann], relating_structure=st)
    return {"guid": ann.GlobalId, "bumps": bumps}


def add_tag(model: ifcopenshell.file, host_guid: str, text: str | None = None,
            storey: str | None = None, z: float | None = None) -> dict:
    """UX-2: place an **element-aware tag** — an `IfcAnnotation` (ObjectType "tag") whose label is read from
    the host element (its Name / Pset mark / type name), placed at the host's plan centroid and **assigned to
    it** (`IfcRelAssignsToProduct`), so the tag tracks the element it describes. `text` overrides the
    auto-read label. Renders on the generated plan. GUID-stable. Returns {guid, host, label}."""
    import ifcopenshell.util.placement as up
    import numpy as np

    try:
        host = model.by_guid(host_guid)
    except (RuntimeError, Exception):                  # noqa: BLE001 — by_guid raises on unknown GUID
        host = None
    if host is None:
        raise ValueError(f"unknown host element {host_guid}")
    label = (text or "").strip() or _element_mark(host)

    # tag point: the host's plan centroid (footprint if extruded, else its placement translation)
    fp = None
    try:
        from .drawing import _footprint
        fp = _footprint(host)
    except Exception:                                  # noqa: BLE001 — footprint best-effort
        fp = None
    if fp:
        px = sum(p[0] for p in fp) / len(fp)
        py = sum(p[1] for p in fp) / len(fp)
        pz = 0.0
    else:
        m = up.get_local_placement(host.ObjectPlacement) if host.ObjectPlacement is not None else np.eye(4)
        px, py, pz = float(m[0][3]), float(m[1][3]), float(m[2][3])
    zz = float(z) if z is not None else pz

    ctx = _annotation_context(model)
    ann = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcAnnotation", name=label[:64])
    if hasattr(ann, "ObjectType"):
        ann.ObjectType = "tag"
    mtx = np.eye(4); mtx[0, 3], mtx[1, 3], mtx[2, 3] = px, py, zz
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=ann, matrix=mtx)
    place = model.create_entity("IfcAxis2Placement2D",
                                Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)))
    lit = model.create_entity("IfcTextLiteral", Literal=label, Placement=place, Path="RIGHT")
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=ctx,
                              RepresentationIdentifier="Annotation", RepresentationType="Annotation2D",
                              Items=[lit])
    ifcopenshell.api.run("geometry.assign_representation", model, product=ann, representation=rep)
    # element-aware: assign the tag to the product it labels, so it tracks that element
    try:
        ifcopenshell.api.run("group.assign_product", model, products=[ann], relating_product=host)
    except Exception:                                  # noqa: BLE001 — fall back to a direct rel
        try:
            model.create_entity("IfcRelAssignsToProduct",
                                GlobalId=ifcopenshell.guid.new(),
                                RelatedObjects=[ann], RelatingProduct=host)
        except Exception:                              # noqa: BLE001 — assignment best-effort
            pass
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[ann], relating_structure=st)
    return {"guid": ann.GlobalId, "host": host_guid, "label": label}
