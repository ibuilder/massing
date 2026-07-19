"""Clash detection (Navisworks Clash Detective / Bonsai native parity).

Two-phase, like real clash engines:
  1. BROAD phase — bake world-space geometry once via the IfcOpenShell iterator, compute an
     axis-aligned bounding box per element, find overlapping boxes between two groups.
  2. NARROW phase — for each AABB candidate, compute the actual mesh boolean-intersection
     VOLUME (true hard clash with exact penetration). Falls back to the AABB overlap volume
     if the boolean fails on degenerate geometry.

Narrow phase needs trimesh + manifold3d; if unavailable, broad-phase results are returned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import ifcopenshell
import ifcopenshell.geom as geom
import numpy as np

from .geomconf import geom_workers
from .ifc_loader import open_model

try:
    import trimesh
    _MESH_OK = True
except Exception:  # pragma: no cover
    _MESH_OK = False


@dataclass
class ElementGeom:
    guid: str
    ifc_class: str
    name: str | None
    min: np.ndarray
    max: np.ndarray
    verts: np.ndarray = field(default=None, repr=False)   # (N,3)
    faces: np.ndarray = field(default=None, repr=False)   # (M,3)


def _compute_geometry(model: ifcopenshell.file, keep_mesh: bool) -> list[ElementGeom]:
    settings = geom.settings()
    out: list[ElementGeom] = []
    it = geom.iterator(settings, model, geom_workers())
    if not it.initialize():
        return out
    while True:
        shape = it.get()
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        if verts.size:
            el = model.by_guid(shape.guid)
            faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3) if keep_mesh else None
            out.append(ElementGeom(
                guid=shape.guid,
                ifc_class=el.is_a() if el else shape.type,
                name=getattr(el, "Name", None) if el else None,
                min=verts.min(axis=0), max=verts.max(axis=0),
                verts=verts if keep_mesh else None, faces=faces,
            ))
        if not it.next():
            break
    return out


def _aabb_overlap_volume(a: ElementGeom, b: ElementGeom) -> float:
    d = np.minimum(a.max, b.max) - np.maximum(a.min, b.min)
    return float(d[0] * d[1] * d[2]) if np.all(d > 0) else 0.0


def _mesh_intersection_volume(a: ElementGeom, b: ElementGeom) -> float | None:
    """Exact penetration volume via boolean intersection; None if it can't be computed."""
    if not _MESH_OK or a.verts is None or b.verts is None:
        return None
    try:
        ma = trimesh.Trimesh(vertices=a.verts, faces=a.faces, process=True)
        mb = trimesh.Trimesh(vertices=b.verts, faces=b.faces, process=True)
        ma.fix_normals(); mb.fix_normals()  # consistent winding for the boolean engine
        inter = trimesh.boolean.intersection([ma, mb], engine="manifold")
        vol = abs(float(inter.volume))
        return vol if np.isfinite(vol) else 0.0
    except Exception:
        return None


def detect(
    model: ifcopenshell.file,
    group_a: list[str] | None = None,
    group_b: list[str] | None = None,
    min_volume: float = 1e-3,
    tolerance: float = 0.0,
    narrow: bool = True,
    max_narrow: int = 800,
    guids_a: set[str] | None = None,
    guids_b: set[str] | None = None,
) -> list[dict[str, Any]]:
    """`group_*` scope a side by IFC class; `guids_*` (QUERY-DSL wiring) scope it to an explicit GUID
    set — e.g. the elements matching `IfcDuctSegment & storey=L3`. Both filters compose (AND)."""
    elems = _compute_geometry(model, keep_mesh=narrow and _MESH_OK)
    if tolerance:
        for e in elems:
            e.min = e.min + tolerance
            e.max = e.max - tolerance

    def pick(group, guids):
        out = elems
        if group:
            s = {g.lower() for g in group}
            out = [e for e in out if e.ifc_class.lower() in s]
        if guids is not None:
            out = [e for e in out if e.guid in guids]
        return out

    A, B = pick(group_a, guids_a), pick(group_b, guids_b)
    if not A or not B:
        return []

    mins_a = np.array([e.min for e in A]); maxs_a = np.array([e.max for e in A])
    mins_b = np.array([e.min for e in B]); maxs_b = np.array([e.max for e in B])
    overlap = (
        (mins_a[:, None, :] <= maxs_b[None, :, :]).all(axis=2)
        & (maxs_a[:, None, :] >= mins_b[None, :, :]).all(axis=2)
    )
    ia, ib = np.where(overlap)

    # candidate pairs with AABB overlap volume, de-duplicated, biggest first
    cands: list[tuple[float, ElementGeom, ElementGeom]] = []
    seen: set[tuple[str, str]] = set()
    for i, j in zip(ia.tolist(), ib.tolist()):
        a, b = A[i], B[j]
        if a.guid == b.guid:
            continue
        key = tuple(sorted((a.guid, b.guid)))
        if key in seen:
            continue
        seen.add(key)
        cands.append((_aabb_overlap_volume(a, b), a, b))
    cands.sort(key=lambda c: c[0], reverse=True)

    do_narrow = narrow and _MESH_OK
    clashes: list[dict[str, Any]] = []
    for rank, (aabb_vol, a, b) in enumerate(cands):
        method = "aabb"
        vol = aabb_vol
        if do_narrow:
            # cap protects against huge candidate sets; candidates are sorted by AABB
            # overlap (deepest first), so the cap keeps the most likely real clashes.
            if rank >= max_narrow:
                break
            mv = _mesh_intersection_volume(a, b)
            if mv is None:
                continue  # couldn't verify -> don't report an unverified box volume
            vol, method = mv, "mesh"
        if vol < min_volume:
            continue
        center = ((np.maximum(a.min, b.min) + np.minimum(a.max, b.max)) / 2).tolist()
        clashes.append({
            "a_guid": a.guid, "a_class": a.ifc_class, "a_name": a.name,
            "b_guid": b.guid, "b_class": b.ifc_class, "b_name": b.name,
            "volume": round(vol, 6), "method": method,
            "point": {"x": center[0], "y": center[1], "z": center[2]},
        })
    clashes.sort(key=lambda c: c["volume"], reverse=True)
    return clashes


def detect_file(ifc_path: str, group_a=None, group_b=None, min_volume=1e-3,
                tolerance=0.0, narrow=True, max_narrow=800, guids_a=None, guids_b=None):
    return detect(open_model(ifc_path), group_a, group_b, min_volume, tolerance, narrow, max_narrow,
                  guids_a=guids_a, guids_b=guids_b)


def detect_federated(models: list[tuple[str, ifcopenshell.file]], min_volume: float = 1e-3,
                     narrow: bool = True, max_narrow: int = 1500) -> list[dict[str, Any]]:
    """Cross-discipline (federated) clash: clash elements ACROSS different models only.
    Intra-model overlaps (e.g. beam-column joints, by design) are excluded — exactly the
    coordination case Navisworks targets. `models` = [(discipline_name, ifc_file), ...]."""
    tagged: list[tuple[str, ElementGeom]] = []
    for name, model in models:
        for g in _compute_geometry(model, keep_mesh=narrow and _MESH_OK):
            tagged.append((name, g))
    if len({t for t, _ in tagged}) < 2:
        return []

    mins = np.array([g.min for _, g in tagged])
    maxs = np.array([g.max for _, g in tagged])
    tags = np.array([t for t, _ in tagged])
    overlap = (
        (mins[:, None, :] <= maxs[None, :, :]).all(axis=2)
        & (maxs[:, None, :] >= mins[None, :, :]).all(axis=2)
    )
    ia, ib = np.where(np.triu(overlap, k=1))  # unique pairs i<j

    cands = []
    for i, j in zip(ia.tolist(), ib.tolist()):
        if tags[i] == tags[j]:  # cross-model only
            continue
        a, b = tagged[i][1], tagged[j][1]
        cands.append((_aabb_overlap_volume(a, b), tagged[i][0], a, tagged[j][0], b))
    cands.sort(key=lambda c: c[0], reverse=True)

    do_narrow = narrow and _MESH_OK
    clashes = []
    for rank, (aabb_vol, ta, a, tb, b) in enumerate(cands):
        method, vol = "aabb", aabb_vol
        if do_narrow:
            if rank >= max_narrow:
                break
            mv = _mesh_intersection_volume(a, b)
            if mv is None:
                continue
            vol, method = mv, "mesh"
        if vol < min_volume:
            continue
        center = ((np.maximum(a.min, b.min) + np.minimum(a.max, b.max)) / 2).tolist()
        clashes.append({
            "a_model": ta, "a_guid": a.guid, "a_class": a.ifc_class, "a_name": a.name,
            "b_model": tb, "b_guid": b.guid, "b_class": b.ifc_class, "b_name": b.name,
            "volume": round(vol, 6), "method": method,
            "point": {"x": center[0], "y": center[1], "z": center[2]},
        })
    clashes.sort(key=lambda c: c["volume"], reverse=True)
    return clashes


def detect_federated_files(paths: dict[str, str], min_volume=1e-3, narrow=True, max_narrow=1500):
    return detect_federated([(name, open_model(p)) for name, p in paths.items()],
                            min_volume, narrow, max_narrow)
