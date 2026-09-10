"""IFC -> `.frag`, in Python, with no Node runtime — the desktop app's conversion path.

`ifcopenshell.geom` already tessellates, and it is already bundled in the desktop artifact. What was
missing was the file format, which `codec.py` now writes. This module is the join: iterate the
model's geometry, and emit one shell per element.

**Triangles are emitted as three-index profiles.** A `.frag` shell is a polygonal boundary
representation -- `points` plus index loops around planar faces -- and IfcOpenShell hands back
triangles. A triangle *is* a valid profile, so no re-facing is attempted: merging coplanar triangles
back into polygons would be a second geometric algorithm to get wrong, for a smaller file. The
browser triangulates profiles with earcut at load time, and a three-index loop is a no-op there.

**Coordinates.** The model's own placement is preserved in the vertex data, and the `coordinates`
field carries the offset the viewer renders relative to -- the "preserve real coordinates for export,
render near the scene origin" rule from CLAUDE.md. This writes the bounding-box centre of the first
element as that offset, which keeps a georeferenced model near the origin without moving anything.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .codec import FragModel, Mesh
from .schema import MAX_SHELL_POINTS

#: IFC classes that carry geometry but must NEVER be drawn: they are the VOIDS subtracted from
#: other elements, not solids. Emitting one fills the doorway it cut.
#:
#: **This was a live defect until the conformance comparison caught it.** `IfcOpeningElement` has a
#: representation, so "every product with a representation" — the obvious population — includes it,
#: and IfcOpenShell happily tessellates the void as a box. The Node importer excludes them; the
#: comparison reported exactly one GUID present in the Python output and absent from the reference,
#: and that GUID was the door opening. *The obvious population was wrong in the direction that
#: renders.*
_SUBTRACTIVE = ("IfcFeatureElementSubtraction", "IfcOpeningElement", "IfcVoidingFeature")

#: What belongs in the entity index: the things a person can select or inspect. Everything else in
#: an IFC file is the machinery that positions them.
#:
#: **Derived by matching the reference implementation, not by taste.** "Every non-relationship
#: entity" -- the first rule here -- indexed 282 entities for a model the Node importer indexes 57
#: of, because an IFC file is mostly `IfcCartesianPoint` (34) and `IfcDirection` (76): the geometry's
#: own scaffolding, which no viewer offers to select. These six supertypes reproduce the reference's
#: 57 exactly, class for class, on the same model.
#:
#: Stated as SUPERTYPES and tested with `is_a()`, so the schema's inheritance decides membership: a
#: subtype nobody here has heard of is still indexed, which a list of concrete class names would
#: silently drop.
_INDEXABLE = ("IfcRoot",                  # products, spatial structure, property sets
              "IfcPropertyAbstraction",   # the values inside a property set
              "IfcPhysicalQuantity",      # areas, lengths, volumes
              "IfcNamedUnit", "IfcDerivedUnit", "IfcUnitAssignment",
              "IfcMaterialDefinition")


def _is_indexable(entity) -> bool:
    """Does this entity belong in the model's selectable index? See `_INDEXABLE`."""
    if entity.is_a("IfcRelationship") or _is_subtractive(entity):
        return False
    return any(entity.is_a(k) for k in _INDEXABLE)


def _is_subtractive(product) -> bool:
    """Is this product a void rather than a solid? Asked by IFC inheritance, not by class name.

    `is_a(name)` walks the schema's type hierarchy, so a subtype nobody here has heard of is still
    excluded — which a literal name comparison against `product.is_a()` would miss.
    """
    return any(product.is_a(name) for name in _SUBTRACTIVE)


@dataclass
class ConversionResult:
    """What the conversion produced, and what it could not."""

    data: bytes
    elements: int
    meshes: int
    #: GlobalIds whose geometry IfcOpenShell refused. Named, never silently dropped: a converter
    #: that returns a smaller model without saying so is the failure this codebase keeps finding.
    failed: list[str]
    #: shells that had to be split because one element exceeded the uint16 index ceiling
    split: int
    #: voids (openings) skipped — reported so "fewer meshes than products" is explained, not noticed
    skipped_voids: int = 0


def _settings():
    """Geometry settings: world coordinates, triangulated, no openings subtracted twice."""
    from ifcopenshell import geom
    s = geom.settings()
    # `USE_WORLD_COORDS` bakes each element's placement into its vertices, so every shell shares one
    # frame and the per-instance transforms stay identity. That is the simple, correct arrangement
    # here; instancing repeated geometry is an optimisation this does not attempt.
    # The setting's name changed between IfcOpenShell 0.7 and 0.8; try both and say so if neither
    # took, because silently falling back to LOCAL coordinates puts every element at the origin —
    # a model that renders, in one heap, which is far worse than a converter that refuses.
    tried: list[str] = []
    for name in ("USE_WORLD_COORDS", "use-world-coords"):
        try:
            s.set(name, True)
            return s
        except Exception as e:                # noqa: BLE001 — wrong name for this version; try the next
            tried.append(f"{name}: {e.__class__.__name__}")
    raise RuntimeError(
        "ifcopenshell geometry settings accept neither 'USE_WORLD_COORDS' nor 'use-world-coords'; "
        f"without world coordinates every element would be written at the origin ({tried})")


def _to_viewer_axes(x: float, y: float, z: float) -> tuple[float, float, float]:
    """IFC (Z-up, right-handed) -> Fragments/three.js (Y-up, right-handed).

    **The format is Y-up and IFC is Z-up, and getting this wrong lays the building on its side.**
    Measured against a reference file rather than assumed: the Node importer stores a 0.9 x 2.1 door
    with extents x=+/-0.45, y=+/-1.05, z=+/-0.087 -- height along **y**. The first draft here wrote
    IfcOpenShell's coordinates through unchanged, which puts height along z; the file loads, every
    count matches, and the model renders rotated a quarter turn. Nothing but a geometric comparison
    would have caught it.

    `(x, y, z) -> (x, z, -y)` is the rotation that takes Z-up to Y-up without mirroring: negating y
    rather than dropping its sign keeps the winding order, so faces do not turn inside out.
    """
    return (x, z, -y)


def _shells_for(verts: list[float], faces: list[int]) -> list[Mesh]:
    """One element's triangles as shells, split at the uint16 index ceiling.

    **Splitting rather than truncating is the whole point.** `ShellProfile.indices` is uint16, so a
    shell addresses at most 65,536 points; a wrapped index draws a face between two unrelated
    corners, which looks like a modelling error rather than a converter bug and would be chased in
    the wrong place. Each chunk re-bases its own points so every index stays in range.
    """
    out: list[Mesh] = []
    tri_count = len(faces) // 3
    start = 0
    while start < tri_count:
        pts: list[tuple[float, float, float]] = []
        remap: dict[int, int] = {}
        profiles: list[list[int]] = []
        end = start
        while end < tri_count:
            tri = faces[end * 3:end * 3 + 3]
            # would this triangle push the chunk past what a uint16 index can address?
            fresh = sum(1 for v in tri if v not in remap)
            if pts and len(pts) + fresh > MAX_SHELL_POINTS:
                break
            loop = []
            for v in tri:
                if v not in remap:
                    remap[v] = len(pts)
                    pts.append(_to_viewer_axes(
                        verts[v * 3], verts[v * 3 + 1], verts[v * 3 + 2]))
                loop.append(remap[v])
            profiles.append(loop)
            end += 1
        if not profiles:                       # a single triangle over the ceiling: impossible, but
            break                              # an unguarded `while` here would spin forever
        out.append(Mesh(points=pts, profiles=profiles, representation_class=1))
        start = end
    return out


def convert(ifc_path: str, *, model_guid: str = "", progress=None) -> ConversionResult:
    """Convert an IFC file to `.frag` bytes.

    `progress(fraction)` is called as elements are processed, matching the Node CLI's callback so
    the two paths report the same way.
    """
    import ifcopenshell
    from ifcopenshell import geom

    f = ifcopenshell.open(ifc_path)
    settings = _settings()

    guids: list[str] = []
    guids_items: list[int] = []
    local_ids: list[int] = []
    categories: list[str] = []
    meshes_items: list[int] = []
    meshes: list[Mesh] = []
    failed: list[str] = []
    meshed: set[int] = set()
    split = 0

    every = [p for p in f.by_type("IfcProduct") if getattr(p, "Representation", None)]
    products = [p for p in every if not _is_subtractive(p)]
    skipped_voids = len(every) - len(products)
    total = max(1, len(products))
    for i, product in enumerate(products):
        if progress:
            progress(i / total)
        guid = getattr(product, "GlobalId", "") or ""
        try:
            shape = geom.create_shape(settings, product)
        except Exception:                      # noqa: BLE001 — unrepresentable geometry is a fact
            if guid:
                failed.append(guid)
            continue
        verts = list(shape.geometry.verts)
        faces = list(shape.geometry.faces)
        if not verts or not faces:
            if guid:
                failed.append(guid)
            continue
        shells = _shells_for(verts, faces)
        if len(shells) > 1:
            split += 1
        local_id = product.id()
        for shell in shells:
            meshes.append(shell)
            meshes_items.append(local_id)
        meshed.add(local_id)
    if progress:
        progress(1.0)

    # **The entity index covers the WHOLE model, not just what has geometry.** `local_ids` and
    # `categories` run in step over every entity; `guids` and `guids_items` cover the subset that
    # carries a GlobalId. The viewer resolves a picked mesh to an element through these tables, so
    # indexing only the meshed products — which the first draft did — leaves every other entity
    # unresolvable: a selected wall knows its own GlobalId, and its storey, space and property sets
    # are unreachable. Measured against the reference, which indexes 57 entities and 23 GUIDs for a
    # model with 8 meshed items.
    for entity in f:
        eid = entity.id()
        if not eid:                            # inline value types carry id 0 and are not entities
            continue
        # Relationships are edges, voids are holes, and cartesian points are scaffolding — none of
        # them is a thing a person selects. See `_INDEXABLE`.
        if not _is_indexable(entity):
            continue
        local_ids.append(eid)
        categories.append(entity.is_a().upper())
        eguid = getattr(entity, "GlobalId", None)
        if eguid:
            guids.append(eguid)
            guids_items.append(eid)

    # `coordinates` carries the model's real-world placement and vertices are stored RELATIVE to it.
    # This comment previously claimed the centring happened "without altering a single stored vertex",
    # which was the bug: an offset nothing is measured against is not an offset. Vertices stayed in
    # world coordinates, so a georeferenced site rendered far from the scene origin — the precision
    # loss CLAUDE.md names as a non-negotiable — and the two halves disagreed by exactly `origin`.
    #
    # The direction was MEASURED against the Node converter rather than reasoned about, because
    # getting it backwards moves every model by twice the offset and still looks plausible: for a
    # 20 m slab at IFC (0..20, 0..20), Node writes `position = (10, 0, -10)` and vertices spanning
    # -10..+10. Subtracting is what reproduces that.
    if meshes:
        xs = [p[0] for m in meshes for p in m.points]
        ys = [p[1] for m in meshes for p in m.points]
        zs = [p[2] for m in meshes for p in m.points]
        origin = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
        for mesh in meshes:
            mesh.points = [(p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
                           for p in mesh.points]
    else:
        origin = (0.0, 0.0, 0.0)

    metadata = json.dumps({
        "schema": f.schema,
        "names": [getattr(p, "Name", "") or "" for p in f.by_type("IfcProject")[:1]],
        "generator": "aec_data.fragments (python)",
        "created": datetime.now(timezone.utc).isoformat(),
    })
    model = FragModel(
        guid=model_guid or (f.by_type("IfcProject")[0].GlobalId if f.by_type("IfcProject") else ""),
        metadata=metadata,
        guids=guids, guids_items=guids_items,
        local_ids=local_ids, categories=categories,
        max_local_id=max(local_ids) if local_ids else 0,
        coordinates=origin,
        meshes_items=meshes_items, meshes=meshes,
    )
    from .codec import dumps
    return ConversionResult(data=dumps(model), elements=len(meshed), meshes=len(meshes),
                            failed=failed, split=split, skipped_voids=skipped_voids)
