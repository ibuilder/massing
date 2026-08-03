"""2D documentation — plan & section generation (Revit-style sheets, openBIM way).

Cuts the model geometry with a plane (trimesh section) and renders the cut polylines to
SVG. Plans are horizontal cuts at a storey height; sections are vertical cuts. Output is
plain SVG so it embeds in the viewer, prints, or drops onto a sheet with a title block.
"""
from __future__ import annotations

import logging
import os
import warnings
from typing import Any
from xml.sax.saxutils import escape as _xesc

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.unit as uunit
import math

import numpy as np
import trimesh

from .drawings_render import _dim_h, _dim_v, render_sheet_dxf, render_sheet_pdf, render_sheet_svg  # noqa: F401
from .geomconf import bounded_iterator
from .ifc_loader import open_model

warnings.filterwarnings("ignore")
log = logging.getLogger(__name__)

# (normal, kept-axes) for each view kind
_VIEWS = {
    "plan": (np.array([0.0, 0.0, 1.0]), (0, 1)),   # cut at Z, draw X/Y
    "section-x": (np.array([1.0, 0.0, 0.0]), (1, 2)),  # cut at X, draw Y/Z
    "section-y": (np.array([0.0, 1.0, 0.0]), (0, 2)),  # cut at Y, draw X/Z
}


def storey_elevations(model: ifcopenshell.file) -> list[dict[str, Any]]:
    """Storey elevations in METERS (iterator geometry is SI meters; the IfcBuildingStorey
    Elevation attribute is in the file's length unit, e.g. mm)."""
    scale = uunit.calculate_unit_scale(model)  # file unit -> meters
    out = []
    for s in model.by_type("IfcBuildingStorey"):
        elev = float(getattr(s, "Elevation", 0.0) or 0.0) * scale
        out.append({"name": s.Name, "elevation": elev, "guid": s.GlobalId})
    return sorted(out, key=lambda x: x["elevation"])


def resolve_storey(model: ifcopenshell.file, storey: str) -> float | None:
    """R38-SYNC-SELECT: a storey NAME → its elevation in metres, or None when no storey has that
    name. Matching is case-insensitive and whitespace-trimmed because the name travels through a
    query string typed by nobody — it comes from the viewer's level list, but a client and server
    disagreeing on case must degrade to 'not found', never to a silent cut at the wrong height."""
    want = storey.strip().lower()
    for lvl in storey_elevations(model):
        if str(lvl.get("name") or "").strip().lower() == want:
            return float(lvl["elevation"])
    return None


def _world_settings(geom_mod):
    """Geometry settings that apply each element's ObjectPlacement, so verts come back in WORLD space.
    Without this every element collapses to its own local origin — off-origin geometry stacks at (0,0)
    in plans/sections, and any annotation built from these verts misaligns with the linework."""
    settings = geom_mod.settings()
    try:
        settings.set("use-world-coords", True)
    except Exception:  # pragma: no cover - older builds use the enum name
        settings.set(settings.USE_WORLD_COORDS, True)
    return settings


# PERF-2 (GEOM-CACHE): tessellation is the dominant per-request cost — every section/elevation/DXF/
# sheet view re-baked the whole model, so this memoizes the bake.
#
# CACHE-KEY (v0.3.722): keyed by the model's CONTENT identity (`__aec_content_key__`, stamped by
# `ifc_loader.open_model` from path+mtime+size) rather than by `id(model)`.
#
# `id()` worked, but only inside one process and only with a strong ref held per entry to stop the
# address being reused after a GC — a guard whose existence is the tell. It also made the cache
# unshareable in principle: an address in one worker's heap means nothing in another, so the
# expensive half of the work could never be reused across workers no matter how it was stored.
#
# A model opened directly (`ifcopenshell.open`, bypassing `open_model`) carries no key; those fall
# back to identity, which is the previous behaviour and correct — an UNKNOWN identity must not
# collide with a known one, so it is never given a shared key.
_BAKE_CACHE: dict[Any, tuple[Any, list[tuple[str, str, trimesh.Trimesh]], int]] = {}
_BAKE_CACHE_MAX = 4

#: Byte budget for baked geometry, over the whole cache rather than per entry.
#:
#: A count of four was never a size. Four small houses are a few megabytes; four towers can be several
#: gigabytes, and the count reports "4" in both cases — a limit that cannot tell the difference between
#: those is not bounding anything, it is just a number that happens to be small most of the time. The
#: count stays as a secondary cap so a pathological number of tiny models cannot accumulate either.
#:
#: Deliberately built on the standard library. `cachetools` would have saved about twenty lines and
#: cost a dependency, a lockfile round trip and the supply-chain surface that comes with both. The
#: cross-worker half of this work still wants `diskcache`, where the alternative is writing a
#: lock-correct disk cache by hand and that trade goes the other way.
_BAKE_CACHE_BYTES = int(os.environ.get("AEC_BAKE_CACHE_MB", "1024")) * 1024 * 1024


def _mesh_bytes(meshes) -> int:
    """Roughly how much memory a baked set occupies — vertices + faces of every mesh.

    An underestimate by design: it counts the arrays that dominate and ignores per-object overhead.
    A cache budget wants a number that is monotonic in the real size and cheap to compute on every
    insert; precision here would cost more than the eviction it informs.
    """
    total = 0
    for _, _, m in meshes:
        for attr in ("vertices", "faces"):
            arr = getattr(m, attr, None)
            nbytes = getattr(arr, "nbytes", None)
            if nbytes:
                total += int(nbytes)
    return total


def _evict_to_budget() -> None:
    """Drop least-recently-inserted entries until the cache fits both its byte and count budgets.

    Always leaves at least one entry standing. A model larger than the whole budget would otherwise
    be evicted immediately after being baked, so every view would re-tessellate it — turning a cache
    into a tax. Serving one oversized model and going over budget is the better failure.
    """
    while len(_BAKE_CACHE) > 1 and (
            len(_BAKE_CACHE) > _BAKE_CACHE_MAX
            or sum(e[2] for e in _BAKE_CACHE.values()) > _BAKE_CACHE_BYTES):
        _BAKE_CACHE.pop(next(iter(_BAKE_CACHE)))


def bake_cache_stats() -> dict:
    """What the cache is actually holding. Exists so the budget can be observed rather than assumed —
    a cache nobody can measure is a cache nobody can size."""
    return {"entries": len(_BAKE_CACHE),
            "bytes": sum(e[2] for e in _BAKE_CACHE.values()),
            "budget_bytes": _BAKE_CACHE_BYTES,
            "max_entries": _BAKE_CACHE_MAX}


def _bake_key(model: ifcopenshell.file) -> tuple[str, Any]:
    """("content", key) when the file identity is known, else ("id", id(model))."""
    key = getattr(model, "__aec_content_key__", None)
    return ("content", key) if key else ("id", id(model))


def bake(model: ifcopenshell.file) -> list[tuple[str, str, trimesh.Trimesh]]:
    """Bake every element's world-space mesh ONCE so many views can section the same set. Cached by
    the model's content identity (see CACHE-KEY) — repeated views of one file tessellate only once,
    and a re-published file is a different key rather than a stale hit."""
    key = _bake_key(model)
    hit = _BAKE_CACHE.get(key)
    if hit is not None and (key[0] == "content" or hit[0] is model):
        # An id() key still needs the identity check — the address may have been reused. A content
        # key does not: it names the file, so any model object opened from it is interchangeable.
        return hit[1]
    # Cross-process: another worker may already have tessellated this exact file. Only content keys
    # are shared — an `id()` key names an address in ONE process's heap and would be a collision
    # waiting to happen if it were ever written somewhere other processes read.
    # The "g1:" prefix is a FORMAT version, not decoration. R38-PLAN-IDENTITY widened the payload
    # from (cls, verts, faces) to (guid, cls, verts, faces); a persisted cache written by an older
    # build holds the narrow shape under the same content hash. Unpacking it would raise, and while
    # the except below would catch that and re-bake, relying on an exception to detect a format is
    # how a cache quietly serves the wrong thing the day the shapes happen to be compatible. A
    # versioned key means the two formats never meet.
    shared_key = ("g1:" + key[1]) if key[0] == "content" else None
    if shared_key:
        from . import bake_shared
        payload = bake_shared.get(shared_key)
        if payload:
            try:
                meshes = [(guid, cls, trimesh.Trimesh(vertices=v, faces=f, process=False))
                          for guid, cls, v, f in payload]
                _BAKE_CACHE[key] = (model, meshes, _mesh_bytes(meshes))
                _evict_to_budget()
                return meshes
            except Exception:   # noqa: BLE001 — an entry we cannot rebuild is a miss, not a failure
                log.debug("shared bake entry unusable for %s; re-baking", shared_key)

    meshes = _bake_uncached(model)
    _BAKE_CACHE[key] = (model, meshes, _mesh_bytes(meshes))
    _evict_to_budget()          # bounded by BYTES first, count second (dict is insertion-ordered)
    if shared_key:
        from . import bake_shared
        # Arrays, not trimesh objects: a pickled third-party object is a format that moves when that
        # library upgrades, and an entry that deserialises into something subtly different is worse
        # than a miss.
        bake_shared.put(shared_key,
                        [(guid, cls, m.vertices, m.faces) for guid, cls, m in meshes])
    return meshes


def world_bounds(model: ifcopenshell.file) -> tuple[list[float], list[float]] | None:
    """PERF-2: the model's world-space AABB [min_xyz, max_xyz] (metres) without building any trimesh —
    just min/max over the geom-iterator verts. Reuses the bake cache when the model was already baked
    for a drawing (free), else runs a lean vert-only pass. None when the model has no geometry."""
    hit = _BAKE_CACHE.get(_bake_key(model))   # keyed by content since v0.3.722; id() never hit
    if hit is not None and hit[0] is model and hit[1]:
        pts = np.vstack([m.bounds for _, _, m in hit[1] if getattr(m, "bounds", None) is not None])
        return list(pts.min(axis=0)), list(pts.max(axis=0))
    it = bounded_iterator(geom, _world_settings(geom), model)
    if not it.initialize():
        return None
    mn = np.array([np.inf, np.inf, np.inf])
    mx = -mn
    while True:
        v = np.asarray(it.get().geometry.verts, dtype=float).reshape(-1, 3)
        if v.size:
            mn = np.minimum(mn, v.min(axis=0))
            mx = np.maximum(mx, v.max(axis=0))
        if not it.next():
            break
    return (list(mn), list(mx)) if np.isfinite(mn).all() else None


def _bake_uncached(model: ifcopenshell.file) -> list[tuple[str, str, trimesh.Trimesh]]:
    """R38-PLAN-IDENTITY: `(guid, ifc_class, mesh)`.

    The GlobalId was always in hand here — `shape.guid` is what `by_guid` is called with two lines
    down — and it used to be dropped on the floor, so every polyline downstream was anonymous and no
    drawing could name what it drew. Carrying it costs one string per element and is the difference
    between a drawing and a picture of one: 2D↔3D selection sync, click-a-wall-in-plan and precise
    pin anchoring all need the element behind the line, not just its class.
    """
    it = bounded_iterator(geom, _world_settings(geom), model)
    meshes: list[tuple[str, str, trimesh.Trimesh]] = []
    if not it.initialize():
        return meshes
    skipped = 0                              # parse-robustness: count + log, never silently thin the set
    while True:
        shape = it.get()
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if verts.size and faces.size:
            el = model.by_guid(shape.guid)
            cls = el.is_a() if el else shape.type
            try:
                meshes.append((shape.guid, cls,
                               trimesh.Trimesh(vertices=verts, faces=faces, process=False)))
            except Exception as exc:         # noqa: BLE001 — one bad mesh must not kill the whole bake
                skipped += 1
                log.debug("drawings.bake: unbuildable mesh %s (%s): %s", shape.guid, cls, exc)
        if not it.next():
            break
    if skipped:
        log.warning("drawings.bake: %d element mesh(es) skipped — those elements are missing from "
                    "every plan/section cut of this model", skipped)
    return meshes


def cut_baked(meshes: list[tuple[str, str, trimesh.Trimesh]], view: str, offset: float,
              classes: list[str] | None = None) -> list[np.ndarray]:
    """Section pre-baked meshes; returns (n,2) polylines in the view's drawing plane."""
    normal, axes = _VIEWS[view]
    origin = normal * offset
    want = {c.lower() for c in classes} if classes else None
    polylines: list[np.ndarray] = []
    skipped = 0
    for _guid, cls, mesh in meshes:
        if want and cls.lower() not in want:
            continue
        try:
            sec = mesh.section(plane_origin=origin, plane_normal=normal)
            if sec is not None:
                for poly in sec.discrete:
                    polylines.append(np.asarray(poly)[:, axes])
        except Exception as exc:             # noqa: BLE001 — one unsectionable mesh must not kill the cut
            skipped += 1
            log.debug("drawings.cut_baked: %s mesh failed to section: %s", cls, exc)
    if skipped:
        log.warning("drawings.cut_baked(%s@%.2f): %d mesh(es) failed to section — linework may be "
                    "incomplete for those elements", view, offset, skipped)
    return polylines


def cut_baked_guided(meshes: list[tuple[str, str, trimesh.Trimesh]], view: str,
                     offset: float) -> list[tuple[str, str, np.ndarray]]:
    """R38-PLAN-IDENTITY: like `cut_baked_classed`, but each polyline keeps the **GlobalId** of the
    element it came from — `(guid, ifc_class, polyline)`.

    This is the whole point of the ring: a plan whose linework carries identity is data, and one
    whose linework carries only a class is a picture. With the guid attached, a click in plan
    resolves to the same element the 3D view selects, and a pin dropped on a wall in a drawing
    anchors to that wall rather than to a coordinate that stops meaning anything the moment the
    model moves.

    **One element yields several polylines** — a wall cut at a doorway sections into two or more
    loops — so guids repeat down the list. That is the honest shape: the caller groups by guid. The
    alternative (one entry per element) would have to merge disjoint loops into a single polyline
    and would misdraw exactly the openings that make a plan worth reading.
    """
    normal, axes = _VIEWS[view]
    origin = normal * offset
    out: list[tuple[str, str, np.ndarray]] = []
    skipped: list[str] = []
    for guid, cls, mesh in meshes:
        try:
            sec = mesh.section(plane_origin=origin, plane_normal=normal)
            if sec is not None:
                for poly in sec.discrete:
                    out.append((guid, cls, np.asarray(poly)[:, axes]))
        except Exception as exc:             # noqa: BLE001 — one unsectionable mesh must not kill the cut
            # It "mirrored cut_baked's tolerance" but not its ACCOUNTING: `continue` alone, no
            # counter, no log. So the guided cut — the one this ring made the default — dropped
            # linework in total silence where the function it replaced had always warned. A plan
            # missing a wall renders perfectly; nothing about it says a wall is missing, and the
            # GUIDs make that worse rather than better, because everything still on the sheet
            # resolves correctly and invites you to trust the sheet.
            skipped.append(guid)
            log.debug("drawings.cut_baked_guided: %s (%s) failed to section: %s", guid, cls, exc)
    if skipped:
        log.warning("drawings.cut_baked_guided(%s@%.2f): %d of %d mesh(es) failed to section — "
                    "linework is INCOMPLETE for those elements (first: %s)",
                    view, offset, len(skipped), len(meshes), skipped[0])
    return out


def cut_baked_classed(meshes: list[tuple[str, str, trimesh.Trimesh]], view: str,
                      offset: float) -> list[tuple[str, np.ndarray]]:
    """DISC-poché variant of `cut_baked`: each polyline keeps its element's IFC class, so the plan can
    stroke by discipline."""
    normal, axes = _VIEWS[view]
    origin = normal * offset
    out: list[tuple[str, np.ndarray]] = []
    for _guid, cls, mesh in meshes:
        try:
            sec = mesh.section(plane_origin=origin, plane_normal=normal)
            if sec is not None:
                for poly in sec.discrete:
                    out.append((cls, np.asarray(poly)[:, axes]))
        except Exception:                    # noqa: BLE001 — mirror cut_baked's per-mesh tolerance
            continue
    return out


def cut(model: ifcopenshell.file, view: str, offset: float,
        classes: list[str] | None = None) -> list[np.ndarray]:
    """Return cut polylines as a list of (n,2) arrays in the view's drawing plane."""
    return cut_baked(bake(model), view, offset, classes)


def below_footprint_baked(meshes: list[tuple[str, str, trimesh.Trimesh]], cut_z: float, depth_z: float,
                          classes: list[str] | None = None) -> list[np.ndarray]:
    """VIEW-RANGE 'below' linework: the plan footprint of elements whose body lies **below** the cut plane
    but no deeper than the view-depth plane (`depth_z`) — e.g. footings/foundations under the slab that a
    single cut plane never intersects. Each qualifying mesh is sectioned through its own mid-height (a
    representative outline for a prismatic footing/pile cap) and returned as (n,2) XY polylines. This is
    the Revit view-range model: Top / Cut / Bottom + **View Depth**, so a plan can show what's below the
    cut without dropping the cut plane itself."""
    normal, axes = _VIEWS["plan"]
    want = {c.lower() for c in classes} if classes else None
    out: list[np.ndarray] = []
    for _guid, cls, mesh in meshes:
        if want and cls.lower() not in want:
            continue
        try:
            zmin, zmax = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
        except Exception:  # noqa: BLE001 — degenerate mesh with no bounds
            continue
        # entirely below the cut plane (top under the cut) and reaching no deeper than the view-depth plane
        if zmax > cut_z or zmax < depth_z:
            continue
        mid = (zmin + zmax) / 2.0
        try:
            sec = mesh.section(plane_origin=normal * mid, plane_normal=normal)
            if sec is not None:
                for poly in sec.discrete:
                    out.append(np.asarray(poly)[:, axes])
        except Exception:  # noqa: BLE001 — section can fail on thin/degenerate geometry
            pass
    return out


def to_svg(polylines: list[np.ndarray], title: str = "", subtitle: str = "",
           width: int = 1100, pad: int = 40) -> str:
    if not polylines:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="200">' \
               f'<text x="20" y="40" font-family="sans-serif">No geometry on this cut.</text></svg>'
    allpts = np.vstack(polylines)
    mn, mx = allpts.min(axis=0), allpts.max(axis=0)
    span = np.maximum(mx - mn, 1e-6)
    scale = (width - 2 * pad) / span[0]
    height = int(span[1] * scale + 2 * pad + 60)
    draw_h = span[1] * scale

    def tx(p):
        x = pad + (p[0] - mn[0]) * scale
        y = pad + draw_h - (p[1] - mn[1]) * scale  # flip Y (SVG y-down)
        return x, y

    paths = []
    for poly in polylines:
        pts = " ".join(f"{tx(p)[0]:.1f},{tx(p)[1]:.1f}" for p in poly)
        paths.append(f'<polyline points="{pts}" fill="none" stroke="#111" stroke-width="1"/>')

    ty = height - 30
    titleblock = (
        f'<line x1="{pad}" y1="{ty-12}" x2="{width-pad}" y2="{ty-12}" stroke="#111" stroke-width="1"/>'
        f'<text x="{pad}" y="{ty+8}" font-family="sans-serif" font-size="16" font-weight="700">{title}</text>'
        f'<text x="{width-pad}" y="{ty+8}" font-family="sans-serif" font-size="12" '
        f'text-anchor="end" fill="#555">{subtitle}</text>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" fill="#fff"/>'
        + "".join(paths) + titleblock + "</svg>"
    )


def _cluster(values: list[float], tol: float) -> list[float]:
    """Group near-equal coordinates into single grid lines (their mean)."""
    if not values:
        return []
    vals = sorted(values)
    groups, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            groups.append(cur); cur = [v]
    groups.append(cur)
    return [float(np.mean(g)) for g in groups]


def grid_from_meshes(meshes, tol: float = 0.4) -> dict[str, list[tuple[float, str]]]:
    """Derive a structural grid from IfcColumn centres (no IfcGrid in many IFC exports).
    Vertical lines (constant X) are numbered 1,2,3…; horizontal lines (constant Y) A,B,C…"""
    cxs, cys = [], []
    for _guid, cls, mesh in meshes:
        if cls.lower() != "ifccolumn":
            continue
        c = mesh.bounds.mean(axis=0) if mesh.bounds is not None else None
        if c is not None:
            cxs.append(float(c[0])); cys.append(float(c[1]))
    xlines = _cluster(cxs, tol)
    ylines = _cluster(cys, tol)
    labels_x = [str(i + 1) for i in range(len(xlines))]
    labels_y = [chr(ord("A") + i) for i in range(len(ylines))]
    return {"x": list(zip(xlines, labels_x)), "y": list(zip(ylines, labels_y))}


def _leader_callout(sx: float, sy: float, lx: float, ly: float, text: str, color: str = "#1769aa") -> str:
    """A leader line from element point (sx,sy) to a boxed label at (lx,ly), with a target dot.
    The line elbows horizontally into the label so it reads like a standard callout."""
    anchor = "start" if lx >= sx else "end"
    tx = lx + (4 if anchor == "start" else -4)
    elbow = lx - (10 if anchor == "start" else -10)   # short horizontal run into the text
    w = max(16, 7 * len(text) + 8)
    bx = lx - (2 if anchor == "start" else w - 2)
    return (
        f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="2.2" fill="{color}"/>'
        f'<polyline points="{sx:.1f},{sy:.1f} {elbow:.1f},{ly:.1f} {lx:.1f},{ly:.1f}" '
        f'fill="none" stroke="{color}" stroke-width="0.7"/>'
        f'<rect x="{bx:.1f}" y="{ly-9:.1f}" width="{w}" height="14" rx="2" fill="#fff" '
        f'stroke="{color}" stroke-width="0.6"/>'
        f'<text x="{tx:.1f}" y="{ly+2:.1f}" text-anchor="{anchor}" font-family="sans-serif" '
        f'font-size="10" fill="{color}">{text}</text>')


def plan_drawing_svg(meshes, elevation: float, cut_height: float, title: str,
                     grid: dict | None = None, dims: bool = True, width: int = 1200,
                     tags: list[dict] | None = None, callouts: list[dict] | None = None,
                     below: list[np.ndarray] | None = None, by_discipline: bool = False,
                     pins: list[dict] | None = None) -> str:
    # R38-SYNC-SELECT: the cut is always the GUIDED one now, so every polyline can carry the
    # GlobalId of the element it draws. `by_discipline` only decides colour + legend, not identity —
    # a plan whose linework forgets its elements in one rendering mode would make selection sync a
    # mode-dependent feature, which is worse than not having it.
    guided = cut_baked_guided(meshes, "plan", elevation + cut_height)
    polys = [p for _g, _c, p in guided]
    below = below or []
    grid = grid or {"x": [], "y": []}
    if not polys and not below and not (grid["x"] or grid["y"]):
        return to_svg([], title=title, subtitle="no geometry")

    # 'below' (view-depth) linework shares the plan extent so footings/foundations aren't clipped
    pts = ([np.vstack(polys)] if polys else []) + ([np.vstack(below)] if below else [])
    gx = [c for c, _ in grid["x"]]; gy = [c for c, _ in grid["y"]]
    xs = ([p[:, 0] for p in pts] or [np.array(gx)]) + ([np.array(gx)] if gx else [])
    ys = ([p[:, 1] for p in pts] or [np.array(gy)]) + ([np.array(gy)] if gy else [])
    mn = np.array([min(np.concatenate(xs)), min(np.concatenate(ys))])
    mx = np.array([max(np.concatenate(xs)), max(np.concatenate(ys))])
    span = np.maximum(mx - mn, 1e-6)

    gutter = 70  # room for bubbles + dimension lines
    pad = 30
    draw_w = width - 2 * pad - gutter
    scale = draw_w / span[0]
    draw_h = span[1] * scale
    height = int(draw_h + 2 * pad + gutter + 150)   # extra band for the titleblock + scale bar + notes
    ox = pad + gutter
    oy = pad + gutter

    def T(x, y):
        return ox + (x - mn[0]) * scale, oy + draw_h - (y - mn[1]) * scale

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" fill="#fff"/>']

    # grid lines + bubbles
    bub = 13
    for x, label in grid["x"]:
        sx, _ = T(x, mn[1]); _, ty = T(x, mx[1])
        out.append(f'<line x1="{sx:.1f}" y1="{oy-40:.1f}" x2="{sx:.1f}" y2="{oy+draw_h:.1f}" '
                   f'stroke="#bbb" stroke-width="0.6" stroke-dasharray="6 4"/>')
        out.append(f'<circle cx="{sx:.1f}" cy="{oy-40:.1f}" r="{bub}" fill="#fff" stroke="#111"/>'
                   f'<text x="{sx:.1f}" y="{oy-40+4:.1f}" text-anchor="middle" '
                   f'font-family="sans-serif" font-size="13" font-weight="700">{label}</text>')
    for y, label in grid["y"]:
        _, sy = T(mn[0], y)
        out.append(f'<line x1="{ox-40:.1f}" y1="{sy:.1f}" x2="{ox+draw_w:.1f}" y2="{sy:.1f}" '
                   f'stroke="#bbb" stroke-width="0.6" stroke-dasharray="6 4"/>')
        out.append(f'<circle cx="{ox-40:.1f}" cy="{sy:.1f}" r="{bub}" fill="#fff" stroke="#111"/>'
                   f'<text x="{ox-40:.1f}" y="{sy+4:.1f}" text-anchor="middle" '
                   f'font-family="sans-serif" font-size="13" font-weight="700">{label}</text>')

    # 'below cut' linework (view depth) — drawn first, dashed + light, so foundations/footings under the
    # cut plane read as beyond-the-cut per drawing convention (thin hidden line)
    for poly in below:
        pp = " ".join(f"{T(p[0], p[1])[0]:.1f},{T(p[0], p[1])[1]:.1f}" for p in poly)
        out.append(f'<polyline points="{pp}" fill="none" stroke="#999" stroke-width="0.5" '
                   f'stroke-dasharray="5 3"/>')

    # cut geometry — every polyline carries `data-guid` + `data-class` (R38-SYNC-SELECT), so a click
    # in the served plan resolves to the element the 3D view selects. An IFC GlobalId is 22 chars of
    # [0-9A-Za-z_$] and the class is an IFC schema identifier, so neither needs XML escaping.
    # DISC-poché (`by_discipline`) strokes with the discipline color + a legend; identity is carried
    # either way.
    if by_discipline:
        from . import disciplines as _disc

        used: dict[str, str] = {}
        for guid, cls, poly in guided:
            code = _disc.discipline_of_class(cls)
            col = _disc.discipline_color(code)
            used[code] = col
            pp = " ".join(f"{T(p[0], p[1])[0]:.1f},{T(p[0], p[1])[1]:.1f}" for p in poly)
            out.append(f'<polyline data-guid="{guid}" data-class="{cls}" points="{pp}" '
                       f'fill="none" stroke="{col}" stroke-width="1.1"/>')
        for i, (code, col) in enumerate(sorted(used.items())):
            ly = 20 + i * 16
            out.append(f'<rect x="{width - 150}" y="{ly}" width="12" height="10" fill="{col}"/>'
                       f'<text x="{width - 132}" y="{ly + 9}" font-size="11" '
                       f'font-family="sans-serif">{code}</text>')
        if used:
            out.append(f'<text x="{width - 150}" y="12" font-size="11" font-weight="bold" '
                       f'font-family="sans-serif">DISCIPLINES</text>')
    else:
        for guid, cls, poly in guided:
            pp = " ".join(f"{T(p[0], p[1])[0]:.1f},{T(p[0], p[1])[1]:.1f}" for p in poly)
            out.append(f'<polyline data-guid="{guid}" data-class="{cls}" points="{pp}" '
                       f'fill="none" stroke="#111" stroke-width="0.8"/>')

    # room tags (IfcSpace): name + net floor area at the space centroid
    for tag in (tags or []):
        if not (mn[0] <= tag["x"] <= mx[0] and mn[1] <= tag["y"] <= mx[1]):
            continue
        tx, tyy = T(tag["x"], tag["y"])                   # room names are user data — escape &/<
        out.append(f'<text x="{tx:.1f}" y="{tyy:.1f}" text-anchor="middle" font-family="sans-serif" '
                   f'font-size="12" font-weight="700" fill="#333">{_xesc(str(tag["name"]))}</text>')
        if tag.get("area"):
            out.append(f'<text x="{tx:.1f}" y="{tyy+13:.1f}" text-anchor="middle" '
                       f'font-family="sans-serif" font-size="10" fill="#777">{tag["area"]:.1f} m²</text>')

    # element callouts (e.g. doors/windows): leader from a boxed label to the element point.
    # labels splay radially outward from the plan centre so leaders don't cross the geometry.
    if callouts:
        import xml.sax.saxutils as _sx
        cxm = ox + draw_w / 2.0; cym = oy + draw_h / 2.0
        for co in callouts:
            if not (mn[0] <= co["x"] <= mx[0] and mn[1] <= co["y"] <= mx[1]):
                continue
            sx, sy = T(co["x"], co["y"])
            dx, dy = sx - cxm, sy - cym
            d = (dx * dx + dy * dy) ** 0.5 or 1.0
            L = 34.0
            lx, ly = sx + dx / d * L, sy + dy / d * L
            out.append(_leader_callout(sx, sy, lx, ly, _sx.escape(str(co["label"]))))

    # dimension strings between consecutive grid lines (mm)
    if dims:
        dy = oy + draw_h + 26
        for (x0, _), (x1, _) in zip(grid["x"], grid["x"][1:]):
            ax, _ = T(x0, mn[1]); bx, _ = T(x1, mn[1])
            mm = round((x1 - x0) * 1000)
            out.append(_dim_h(ax, bx, dy, mm))
        dx = ox - 26
        for (y0, _), (y1, _) in zip(grid["y"], grid["y"][1:]):
            _, ay = T(mn[0], y0); _, byy = T(mn[0], y1)
            mm = round((y1 - y0) * 1000)
            out.append(_dim_v(dx, ay, byy, mm))

    if below:
        ly = pad + 8
        out.append(f'<line x1="{pad}" y1="{ly-4:.0f}" x2="{pad+22}" y2="{ly-4:.0f}" stroke="#999" '
                   f'stroke-width="0.8" stroke-dasharray="5 3"/>'
                   f'<text x="{pad+28}" y="{ly:.0f}" font-family="sans-serif" font-size="10" '
                   f'fill="#777">below cut (view depth)</text>')
    out.append(_pin_layer(pins, T, mn, mx))
    out.append(_titleblock_band(width, height, pad, title, elevation + cut_height, scale, grid))
    out.append("</svg>")
    return "".join(out)


# One colour per pin kind, matching the viewer's marker colours so the same issue reads the same way
# on the sheet as it does in 3D. A kind we do not know draws grey rather than being dropped — an
# unrendered pin is an issue nobody sees, which is the failure this whole feature exists to prevent.
_PIN_FILL = {"rfi": "#b45309", "punch": "#b91c1c", "clash": "#7c3aed", "info": "#1d4ed8"}


def _pin_layer(pins, T, mn, mx) -> str:
    """Draw issue pins on the plan — the thing that makes a coordination sheet worth printing.

    A pin is a real position in the building, so it is drawn at that position: the same world→sheet
    transform as the linework, not a legend off to one side. Each marker is a numbered balloon with
    a leader dot, numbered in the order given so the sheet can be read against a list.

    Two deliberate refusals:

    - **A pin outside the drawn extent is still drawn, clamped to the edge, and marked with a caret.**
      Silently dropping it would produce a sheet that looks complete and is not; an issue you cannot
      see is one nobody closes. The caret says "this is off-sheet" rather than lying about where it is.
    - **A pin with no usable position is not invented.** It is skipped and counted in the legend, so
      the sheet says "2 pins not located" instead of quietly showing fewer pins than exist.
    """
    if not pins:
        return ""
    parts: list[str] = ['<g id="pins">']
    unlocated = 0
    n = 0
    for p in pins:
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            unlocated += 1
            continue
        n += 1
        offsheet = not (mn[0] <= x <= mx[0] and mn[1] <= y <= mx[1])
        cx, cy = T(min(max(float(x), mn[0]), mx[0]), min(max(float(y), mn[1]), mx[1]))
        fill = _PIN_FILL.get(str(p.get("kind") or "info").lower(), "#6b7280")
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" fill="{fill}"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy - 16:.1f}" r="9" fill="{fill}" stroke="#fff" '
                     f'stroke-width="1.2"/>')
        parts.append(f'<line x1="{cx:.1f}" y1="{cy - 7:.1f}" x2="{cx:.1f}" y2="{cy - 2:.1f}" '
                     f'stroke="{fill}" stroke-width="1.2"/>')
        parts.append(f'<text x="{cx:.1f}" y="{cy - 12.5:.1f}" text-anchor="middle" '
                     f'font-family="sans-serif" font-size="9" fill="#fff">{n}</text>')
        if offsheet:
            parts.append(f'<text x="{cx:.1f}" y="{cy - 26:.1f}" text-anchor="middle" '
                         f'font-family="sans-serif" font-size="9" fill="{fill}">^</text>')
        label = _esc(str(p.get("label") or ""))[:48]
        if label:
            parts.append(f'<text x="{cx + 12:.1f}" y="{cy - 13:.1f}" font-family="sans-serif" '
                         f'font-size="9" fill="#333">{label}</text>')
    if unlocated:
        parts.append(f'<text x="12" y="16" font-family="sans-serif" font-size="10" fill="#b45309">'
                     f'{unlocated} pin(s) not located on this sheet</text>')
    parts.append("</g>")
    return "".join(parts)


def _esc(s: str) -> str:
    """XML-escape pin labels. They are user text going straight into an SVG document, and an SVG is
    served to a browser — an unescaped `&` breaks the sheet and an unescaped `<` is worse."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


# General notes shown on every plan sheet (standard-of-care boilerplate; NOT project-specific claims).
_PLAN_NOTES = (
    "1. Do not scale drawings — use figured dimensions.",
    "2. Verify all dimensions and conditions in the field before construction.",
    "3. Dimensions are to face of structure / grid unless noted otherwise.",
    "4. Refer to the full drawing set + specifications for scope.",
)


def _titleblock_band(width: int, height: int, pad: int, title: str, cut_z: float,
                     px_per_m: float, grid: dict) -> str:
    """A drawing-sheet bottom band: a bordered rule, the sheet title, a **general-notes** block, a
    **graphic scale bar** (px_per_m keeps it true at any zoom), a north arrow, and a compact **titleblock**
    (title · scale · cut). Composed inline so the standalone plan.svg reads like a real sheet."""
    title = _xesc(str(title))                              # storey name is user data
    top = height - 132
    tb_w = 250                                             # titleblock box width (right)
    tb_x = width - pad - tb_w
    o: list[str] = [f'<line x1="{pad}" y1="{top}" x2="{width-pad}" y2="{top}" stroke="#111" stroke-width="1.4"/>']
    # sheet title (left)
    o.append(f'<text x="{pad}" y="{top+26}" font-family="sans-serif" font-size="18" font-weight="800">{title}</text>')
    # general notes
    o.append(f'<text x="{pad}" y="{top+50}" font-family="sans-serif" font-size="11" font-weight="700" fill="#333">GENERAL NOTES</text>')
    for i, n in enumerate(_PLAN_NOTES):
        o.append(f'<text x="{pad}" y="{top+66+i*14}" font-family="sans-serif" font-size="10" fill="#555">{n}</text>')
    # graphic scale bar (0 / 5 / 10 m) — alternating filled segments; true regardless of on-screen zoom
    sb_x, sb_y, seg = pad + 300, top + 40, 5.0 * px_per_m  # 5 m per segment
    o.append(f'<text x="{sb_x}" y="{sb_y-6}" font-family="sans-serif" font-size="10" font-weight="700" fill="#333">GRAPHIC SCALE (m)</text>')
    for i in range(4):
        x0 = sb_x + i * seg
        o.append(f'<rect x="{x0:.1f}" y="{sb_y:.1f}" width="{seg:.1f}" height="7" fill="{"#111" if i % 2 else "#fff"}" stroke="#111" stroke-width="0.8"/>')
        o.append(f'<text x="{x0:.1f}" y="{sb_y+22:.1f}" text-anchor="middle" font-family="sans-serif" font-size="9" fill="#555">{i*5}</text>')
    o.append(f'<text x="{sb_x+4*seg:.1f}" y="{sb_y+22:.1f}" text-anchor="middle" font-family="sans-serif" font-size="9" fill="#555">20</text>')
    # north arrow
    nax = sb_x + 4 * seg + 40
    o.append(f'<g transform="translate({nax:.1f},{sb_y+2:.1f})"><polygon points="0,-14 5,6 0,1 -5,6" fill="#111"/>'
             f'<text x="0" y="20" text-anchor="middle" font-family="sans-serif" font-size="10" font-weight="700">N</text></g>')
    # titleblock box (right)
    o.append(f'<rect x="{tb_x}" y="{top+10}" width="{tb_w}" height="104" fill="none" stroke="#111" stroke-width="1"/>')
    o.append(f'<line x1="{tb_x}" y1="{top+44}" x2="{tb_x+tb_w}" y2="{top+44}" stroke="#111" stroke-width="0.6"/>')
    o.append(f'<line x1="{tb_x}" y1="{top+80}" x2="{tb_x+tb_w}" y2="{top+80}" stroke="#111" stroke-width="0.6"/>')
    o.append(f'<text x="{tb_x+10}" y="{top+32}" font-family="sans-serif" font-size="14" font-weight="800">{title}</text>')
    o.append(f'<text x="{tb_x+10}" y="{top+60}" font-family="sans-serif" font-size="9" fill="#777">SCALE</text>'
             f'<text x="{tb_x+10}" y="{top+73}" font-family="sans-serif" font-size="12" font-weight="700">As shown (see bar)</text>')
    o.append(f'<text x="{tb_x+10}" y="{top+96}" font-family="sans-serif" font-size="9" fill="#777">CUT PLANE</text>'
             f'<text x="{tb_x+120}" y="{top+96}" font-family="sans-serif" font-size="9" fill="#777">GRID</text>'
             f'<text x="{tb_x+10}" y="{top+109}" font-family="sans-serif" font-size="11" font-weight="700">{cut_z:.2f} m AFF</text>'
             f'<text x="{tb_x+120}" y="{top+109}" font-family="sans-serif" font-size="11" font-weight="700">{len(grid["x"])}×{len(grid["y"])}</text>')
    return "".join(o)


def space_tags(model: ifcopenshell.file, cut_z: float | None = None) -> list[dict]:
    """Room tags from IfcSpace: name + net floor area + plan centroid (for plan annotation). When `cut_z`
    (metres) is given, only spaces the horizontal cut plane passes through are tagged — so a level's plan
    shows *its* rooms, not every floor's rooms stacked on the shared footprint."""
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.element as _ue

    settings = _world_settings(_geom)   # world coords → tag centroids align with the world-placed linework
    tags = []
    skipped = 0
    for sp in model.by_type("IfcSpace"):
        name = getattr(sp, "LongName", None) or getattr(sp, "Name", None) or "Room"
        area = None
        for qset in _ue.get_psets(sp, qtos_only=True).values():
            area = area or qset.get("NetFloorArea") or qset.get("GrossFloorArea")
        try:
            shape = _geom.create_shape(settings, sp)
            v = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            if cut_z is not None and not (v[:, 2].min() - 0.05 <= cut_z <= v[:, 2].max() + 0.05):
                continue                            # this room isn't on the cut level — skip its tag
            cx, cy = float(v[:, 0].mean()), float(v[:, 1].mean())
            if area is None:  # footprint area fallback (convex hull of plan projection)
                from shapely.geometry import MultiPoint
                area = MultiPoint(v[:, :2]).convex_hull.area
        except Exception as exc:                 # noqa: BLE001 — a room with broken geometry loses its tag only
            skipped += 1
            log.debug("drawings.space_tags: geometry failed on %s (%s)", getattr(sp, "GlobalId", "?"), exc)
            continue
        tags.append({"name": name, "area": float(area) if area else None, "x": cx, "y": cy})
    if skipped:
        log.warning("drawings.space_tags: %d room(s) untagged (geometry failed) — the plan shows their "
                    "linework without a room tag", skipped)
    return tags


def space_tags_section(model: ifcopenshell.file, axis: str, offset: float,
                       tol: float = 0.05) -> list[dict]:
    """R21-SPACE-TAG-SECT — room names on a SECTION (CLINIC 1, IP RM.), not just on plans.

    `space_tags` tags rooms on a *horizontal* cut and returns plan centroids `(x, y)`. A section cuts on
    a **vertical** plane, so both halves of that are wrong for it: the inclusion test is against a
    different axis, and the label belongs at the room's centroid **in the section's own 2D frame**.

    The frame is read from `_VIEWS` rather than restated here — `section-x` cuts at X and draws (Y, Z),
    `section-y` cuts at Y and draws (X, Z). Hardcoding `(y, z)` would work for one axis and silently
    place every tag wrong for the other, which is the failure a reader would blame on the geometry
    rather than on the tagger.

    A room is tagged only when the cut plane actually passes through it, for the same reason the plan
    version takes `cut_z`: otherwise a section shows every room in the building stacked onto one cut.
    Returns `x`/`y` in **section 2D coordinates** (x = the in-plane horizontal, y = elevation), matching
    what `cut_baked` produces, so tags and linework share a frame.
    """
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.element as _ue

    view = "section-x" if axis == "x" else "section-y"
    normal, (u, v) = _VIEWS[view]
    cut_axis = int(np.argmax(np.abs(normal)))      # 0 for section-x, 1 for section-y

    settings = _world_settings(_geom)
    tags: list[dict] = []
    skipped = 0
    for sp in model.by_type("IfcSpace"):
        name = getattr(sp, "LongName", None) or getattr(sp, "Name", None) or "Room"
        area = None
        for qset in _ue.get_psets(sp, qtos_only=True).values():
            area = area or qset.get("NetFloorArea") or qset.get("GrossFloorArea")
        try:
            shape = _geom.create_shape(settings, sp)
            pts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            lo, hi = pts[:, cut_axis].min(), pts[:, cut_axis].max()
            if not (lo - tol <= offset <= hi + tol):
                continue                            # the cut misses this room — no tag
            cu, cv = float(pts[:, u].mean()), float(pts[:, v].mean())
        except Exception as exc:                    # noqa: BLE001 — one broken room loses its tag only
            skipped += 1
            log.debug("drawings.space_tags_section: geometry failed on %s (%s)",
                      getattr(sp, "GlobalId", "?"), exc)
            continue
        tags.append({"name": name, "area": float(area) if area else None, "x": cu, "y": cv})
    if skipped:
        log.warning("drawings.space_tags_section: %d room(s) untagged (geometry failed) — the section "
                    "shows their linework without a room tag", skipped)
    return tags


def component_dims_section(model: ifcopenshell.file, axis: str, offset: float,
                           tol: float = 0.05, thickness_tol: float = 0.005) -> list[dict]:
    """R21-DIM-COMPONENT — the layer breakdown of each assembly the cut passes through.

    The floor-to-floor chain answers "how high"; a fabricator asks "made of what, how thick". That is
    the `IfcMaterialLayerSet` — cladding, cavity, insulation, structure — and until now a section
    carried a single overall thickness with the build-up invisible, so the one drawing a trade works
    from could not be built from.

    Grouped by layer SET, not by element: a wall assembly repeated on eight storeys is one dimension
    string, for the same reason keynotes group. Only assemblies the cut actually passes through are
    returned, so a section does not advertise build-ups it never shows.

    **`declared` and `measured` are two different claims and both are reported.** `declared_m` is the
    sum of the layer thicknesses the model states; `measured_m` is the element's own thickness taken
    off its geometry. When they disagree the assembly is flagged rather than reconciled, because there
    is no basis for choosing: a layer set summing to 300 mm on a wall modelled at 250 mm means the
    drawing and the specification disagree, and a fabricator building to either one is building to a
    number nobody checked. Silently printing the declared total would hide exactly that.

    An element with **no** layer set is not a defect and is not invented — it is simply absent from the
    result, and `section_drawing_svg` says how many were skipped rather than implying full coverage.
    """
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.element as _ue

    view = "section-x" if axis == "x" else "section-y"
    normal, (u, v) = _VIEWS[view]
    cut_axis = int(np.argmax(np.abs(normal)))
    settings = _world_settings(_geom)

    sets: dict[int, dict] = {}
    no_layers = 0
    skipped = 0
    for el in model.by_type("IfcElement"):
        mat = None
        try:
            mat = _ue.get_material(el)
        except Exception:                              # noqa: BLE001 — material lookup is optional
            mat = None
        if mat is not None and mat.is_a("IfcMaterialLayerSetUsage"):
            mat = mat.ForLayerSet
        if mat is None or not mat.is_a("IfcMaterialLayerSet"):
            continue                                   # not a layered assembly — nothing to break down
        try:
            shape = _geom.create_shape(settings, el)
            pts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            lo, hi = pts[:, cut_axis].min(), pts[:, cut_axis].max()
            if not (lo - tol <= offset <= hi + tol):
                continue                               # the cut misses this element
            # thickness = the SMALLER in-plane footprint dimension; for a wall that is its thickness.
            # Taken from geometry so it is independent of what the layer set claims — the whole point
            # is to be able to disagree with it.
            ext = [pts[:, i].max() - pts[:, i].min() for i in (0, 1)]
            measured = float(min(ext))
        except Exception as exc:                       # noqa: BLE001 — one bad element loses its string
            skipped += 1
            log.debug("drawings.component_dims_section: geometry failed on %s (%s)",
                      getattr(el, "GlobalId", "?"), exc)
            continue

        layers = []
        for ly in (mat.MaterialLayers or []):
            m = getattr(ly, "Material", None)
            th = getattr(ly, "LayerThickness", None)
            layers.append({"name": getattr(ly, "Name", None),
                           "material": getattr(m, "Name", None) if m is not None else None,
                           "thickness_m": float(th) if isinstance(th, (int, float)) else None})
        if not layers:
            no_layers += 1
            continue                                   # a layer SET with no layers states nothing

        s = sets.setdefault(mat.id(), {
            "name": getattr(mat, "LayerSetName", None) or getattr(mat, "Name", None) or "ASSEMBLY",
            "layers": layers, "ifc_class": el.is_a(), "count": 0, "measured": []})
        s["count"] += 1
        s["measured"].append(measured)

    out: list[dict] = []
    for s in sets.values():
        # A layer with no stated thickness makes the SUM unknowable — refuse the total rather than
        # summing the ones that happen to be present, which would silently under-report the assembly.
        thicks = [ly["thickness_m"] for ly in s["layers"]]
        declared = round(sum(thicks), 4) if all(t is not None for t in thicks) else None
        measured = round(float(np.median(s["measured"])), 4) if s["measured"] else None
        agrees = None
        if declared is not None and measured is not None:
            agrees = abs(declared - measured) <= thickness_tol
        out.append({"name": s["name"], "ifc_class": s["ifc_class"], "element_count": s["count"],
                    "layers": s["layers"], "declared_m": declared, "measured_m": measured,
                    "agrees": agrees,
                    "delta_m": None if agrees is None else round(measured - declared, 4)})
    out.sort(key=lambda a: (-(a["declared_m"] or a["measured_m"] or 0), a["name"]))
    if skipped or no_layers:
        log.warning("drawings.component_dims_section: %d element(s) with unreadable geometry, %d layer "
                    "set(s) with no layers — those assemblies carry no dimension string", skipped, no_layers)
    return out


def element_callouts(model: ifcopenshell.file, classes=("IfcDoor", "IfcWindow"),
                     cut_z: float | None = None) -> list[dict]:
    """Plan callouts for taggable elements: a label (Tag → Name → class) at the element's plan
    centroid. When `cut_z` (metres) is given, only elements the cut plane passes through are labelled
    (so a level's plan tags its own doors/windows, not every floor's)."""
    import ifcopenshell.geom as _geom

    settings = _world_settings(_geom)   # world coords → callout centroids align with the linework
    out: list[dict] = []
    skipped = 0
    for cls in classes:
        for el in model.by_type(cls):
            label = getattr(el, "Tag", None) or getattr(el, "Name", None) or cls.replace("Ifc", "")
            try:
                shape = _geom.create_shape(settings, el)
                v = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
                if cut_z is not None and not (v[:, 2].min() - 0.05 <= cut_z <= v[:, 2].max() + 0.05):
                    continue
                out.append({"label": str(label), "x": float(v[:, 0].mean()),
                            "y": float(v[:, 1].mean()), "kind": cls})
            except Exception as exc:             # noqa: BLE001 — a broken element loses its callout only
                skipped += 1
                log.debug("drawings.element_callouts: geometry failed on %s %s (%s)",
                          cls, getattr(el, "GlobalId", "?"), exc)
                continue
    if skipped:
        log.warning("drawings.element_callouts: %d element(s) uncalled-out (geometry failed)", skipped)
    return out


def plan_svg(model: ifcopenshell.file, elevation: float, cut_height: float = 1.2,
             title: str = "PLAN", grid: bool = True, dims: bool = True,
             rooms: bool = True, callouts: bool | list[str] = False,
             view_depth: float | None = None, by_discipline: bool = False,
             pins: list[dict] | None = None) -> str:
    meshes = bake(model)
    cut_z = elevation + cut_height                 # the horizontal cut plane — tags/callouts filter to it
    g = grid_from_meshes(meshes) if grid else {"x": [], "y": []}
    tags = space_tags(model, cut_z=cut_z) if rooms else []
    co = None
    if callouts:
        classes = callouts if isinstance(callouts, list) else ["IfcDoor", "IfcWindow"]
        co = element_callouts(model, tuple(classes), cut_z=cut_z)
    # VIEW-RANGE: when a view depth (metres below the cut) is given, add the 'below' footprint of anything
    # under the cut but within that depth — foundations/footings show as dashed hidden lines on the plan.
    below = None
    if view_depth and view_depth > 0:
        below = below_footprint_baked(meshes, cut_z, cut_z - float(view_depth))
    return plan_drawing_svg(meshes, elevation, cut_height, title, g, dims,
                            tags=tags, callouts=co, below=below, by_discipline=by_discipline,
                            pins=pins)


# --- elevations (orthographic outline projections) --------------------------
# direction -> (kept axes, flip horizontal?, depth axis, near sign)
_DIRS = {
    "north": ((0, 2), False, 1, +1), "south": ((0, 2), True, 1, -1),   # look along Y, draw X/Z
    "east": ((1, 2), True, 0, +1), "west": ((1, 2), False, 0, -1),     # look along X, draw Y/Z
}


#: The exact isometric elevation, `atan(1/√2)` ≈ 35.26439°, as a value rather than a typed-out
#: decimal. The rounded 35.264 that stood here first was caught by `test_axon_view.py`: it skewed the
#: three axis foreshortenings apart by 6e-6, which is invisible on a page and still wrong — an
#: "isometric" whose axes do not foreshorten equally is by definition not one. Cheap to be exact.
ISO_ELEVATION_DEG = math.degrees(math.atan(1.0 / math.sqrt(2.0)))


def axon_basis(azimuth_deg: float = 45.0, elevation_deg: float = ISO_ELEVATION_DEG) -> np.ndarray:
    """Orthonormal 3×3 basis for an axonometric view: rows are (right, up, toward-viewer).

    The default is a true **isometric** — 45° around Z and `atan(1/√2)` above horizontal, the angle
    at which the three principal axes foreshorten equally. That is what an architectural axonometric
    means by "isometric", so it is the default rather than a rounded 30/45 that only looks right —
    and it is computed rather than typed, because the rounded decimal was measurably not isometric.
    """
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    # direction FROM the model TOWARD the viewer
    view = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    view /= np.linalg.norm(view)
    world_up = np.array([0.0, 0.0, 1.0])
    if abs(float(view @ world_up)) > 0.999:          # looking straight down: pick any stable right
        world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(world_up, view); right /= np.linalg.norm(right)
    up = np.cross(view, right)
    return np.vstack([right, up, view])


def axon_outlines(meshes: list[tuple[str, str, trimesh.Trimesh]],
                  azimuth_deg: float = 45.0, elevation_deg: float = ISO_ELEVATION_DEG,
                  ) -> list[tuple[str, str, np.ndarray, float]]:
    """CANVAS-PEER: element silhouettes under an **axonometric** projection, each keeping its GUID.

    Why this exists: 2D and 3D were not peers on paper. A plan goes model → `plan_svg` → sheet → PDF
    as vector linework derived from the geometry; "3D" went canvas → `toDataURL` → a raster hero
    image. One is a drawing, the other is a screenshot of a screen — different resolution, no scale,
    no identity, and nothing a sheet can compose. Calling them interchangeable modes while only one
    could be placed on a sheet would have been a UI promise the data could not keep.
    So an axonometric becomes a viewport like any other: same meshes, same silhouette-and-depth
    approach as `elevation_outlines`, same sheet composition, same PDF.

    Two things it does that `elevation_outlines` cannot:

    - **Arbitrary view direction.** That function reads `_DIRS`, which selects two of the three world
      axes — fine for north/south/east/west, structurally unable to express a view down a diagonal.
      Here the vertices are rotated into a view basis first, so any azimuth/elevation works and the
      axis-aligned cases fall out as the special case they are.
    - **It carries the GlobalId.** `elevation_outlines` drops it (`_guid`), which is why an elevation
      is a picture. R38-PLAN-IDENTITY established that linework carrying identity is data; an
      axonometric a user can click and resolve to the same element the 3D view selects is the whole
      reason the mode switch is worth building.

    Returns `(guid, ifc_class, hull_2d, depth)` sorted **far → near**, so a painter's-algorithm draw
    hides what is behind. Depth is the mean projected distance along the view axis, matching the
    approximation `elevation_outlines` already uses — cheap, and correct for the non-interpenetrating
    building elements this draws.
    """
    from shapely.geometry import MultiPoint

    basis = axon_basis(azimuth_deg, elevation_deg)
    out: list[tuple[str, str, np.ndarray, float]] = []
    skipped: list[str] = []
    for guid, cls, mesh in meshes:
        v = np.asarray(mesh.vertices)
        if len(v) < 3:
            continue
        proj = v @ basis.T                      # columns: right, up, toward-viewer
        try:
            hull = MultiPoint(proj[:, :2]).convex_hull
            if hull.geom_type != "Polygon":
                continue
            out.append((guid, cls, np.asarray(hull.exterior.coords), float(proj[:, 2].mean())))
        except Exception as exc:                # noqa: BLE001 — one degenerate hull, one lost silhouette
            skipped.append(guid)
            log.debug("drawings.axon_outlines: hull failed on a %s mesh (%s)", cls, exc)
    if skipped:
        log.warning("drawings.axon_outlines(az=%.1f, el=%.1f): %d of %d silhouette(s) skipped — the "
                    "axonometric is INCOMPLETE for those elements (first: %s)",
                    azimuth_deg, elevation_deg, len(skipped), len(meshes), skipped[0])
    out.sort(key=lambda r: r[3])                # far -> near
    return out


def elevation_outlines(meshes, direction: str, with_depth: bool = False):
    """Element silhouettes (convex hull of projected vertices). With with_depth, also returns
    a painter's-algorithm sort key (far→near) per element for hidden-line removal."""
    from shapely.geometry import MultiPoint

    axes, flip, depth_axis, near = _DIRS.get(direction, _DIRS["north"])
    outs = []
    skipped = 0
    for _guid, _cls, mesh in meshes:
        pts = mesh.vertices[:, axes]
        if len(pts) < 3:
            continue
        try:
            hull = MultiPoint(pts).convex_hull
            if hull.geom_type != "Polygon":
                continue
            coords = np.asarray(hull.exterior.coords)
            if flip:
                coords = coords.copy()
                coords[:, 0] = -coords[:, 0]
            if with_depth:
                depth = near * float(mesh.vertices[:, depth_axis].mean())  # larger = nearer
                outs.append((coords, depth))
            else:
                outs.append(coords)
        except Exception as exc:                 # noqa: BLE001 — a degenerate hull loses its silhouette only
            skipped += 1
            log.debug("drawings.elevation_outlines: hull failed on a %s mesh (%s)", _cls, exc)
    if skipped:
        log.warning("drawings.elevation_outlines(%s): %d silhouette(s) skipped (hull failed) — the "
                    "elevation may be missing those elements", direction, skipped)
    return outs


def elevation_svg(meshes, direction: str, levels: list[dict], title: str,
                  width: int = 1300, hidden_line: bool = True, grid: dict | None = None) -> str:
    items = elevation_outlines(meshes, direction, with_depth=True)
    if not items:
        return to_svg([], title=title, subtitle="no geometry")
    items.sort(key=lambda it: it[1])  # far → near (painter's algorithm)
    outs = [c for c, _ in items]
    allp = np.vstack(outs)
    mn, mx = allp.min(axis=0), allp.max(axis=0)
    span = np.maximum(mx - mn, 1e-6)
    gutter, pad, top = 120, 30, 40  # `top` leaves room for grid bubbles
    draw_w = width - 2 * pad - gutter
    scale = draw_w / span[0]
    draw_h = span[1] * scale
    height = int(draw_h + pad + top + 60)
    ox, oy = pad + gutter, top

    def T(x, z):
        return ox + (x - mn[0]) * scale, oy + draw_h - (z - mn[1]) * scale

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" fill="#fff"/>']

    # geometry first — painter's algorithm: opaque white fill so nearer silhouettes
    # occlude farther edges (hidden-line removal)
    fill = "#fff" if hidden_line else "none"
    for poly in outs:
        pp = " ".join(f"{T(p[0], p[1])[0]:.1f},{T(p[0], p[1])[1]:.1f}" for p in poly)
        out.append(f'<polygon points="{pp}" fill="{fill}" stroke="#111" stroke-width="0.6"/>')

    # grid bubbles on top: N/S elevations show the numbered (X) grid, E/W the lettered (Y)
    _, gflip, depth_axis, _ = _DIRS.get(direction, _DIRS["north"])
    if grid:
        glines = grid["x"] if depth_axis == 1 else grid["y"]   # depth Y → horizontal X
        for g, label in glines:
            h = -g if gflip else g
            if h < mn[0] - 0.5 or h > mx[0] + 0.5:
                continue
            gx, _ = T(h, mn[1])
            out.append(f'<line x1="{gx:.1f}" y1="{oy-24:.1f}" x2="{gx:.1f}" y2="{oy+draw_h:.1f}" '
                       f'stroke="#bbb" stroke-width="0.5" stroke-dasharray="5 3"/>')
            out.append(f'<circle cx="{gx:.1f}" cy="{oy-24:.1f}" r="9" fill="#fff" stroke="#111"/>'
                       f'<text x="{gx:.1f}" y="{oy-21:.1f}" text-anchor="middle" '
                       f'font-family="sans-serif" font-size="10" font-weight="700">{label}</text>')

    # storey level lines (Z) drawn on top — standard elevation annotation
    for lv in levels:
        z = lv["elevation"]
        if z < mn[1] - 0.1 or z > mx[1] + 0.1:
            continue
        _, ly = T(mn[0], z)
        out.append(f'<line x1="{ox-70:.1f}" y1="{ly:.1f}" x2="{ox+draw_w:.1f}" y2="{ly:.1f}" '
                   f'stroke="#0a6" stroke-width="0.6" stroke-dasharray="8 4"/>')
        out.append(f'<circle cx="{ox-70:.1f}" cy="{ly:.1f}" r="4" fill="#0a6"/>'
                   f'<text x="{ox-62:.1f}" y="{ly-3:.1f}" font-family="sans-serif" font-size="10" '
                   f'fill="#0a6">{lv["name"]}  +{z*1000:.0f}</text>')

    ty = height - 24
    out.append(f'<line x1="{pad}" y1="{ty-12}" x2="{width-pad}" y2="{ty-12}" stroke="#111" stroke-width="1"/>'
               f'<text x="{pad}" y="{ty+8}" font-family="sans-serif" font-size="16" font-weight="700">{title}</text>'
               f'<text x="{width-pad}" y="{ty+8}" text-anchor="end" font-family="sans-serif" '
               f'font-size="12" fill="#555">{direction.upper()} elevation  ·  {len(outs)} elements</text>')
    out.append("</svg>")
    return "".join(out)


def elevation(model: ifcopenshell.file, direction: str = "north", title: str | None = None) -> str:
    meshes = bake(model)
    levels = storey_elevations(model)
    grid = grid_from_meshes(meshes)
    return elevation_svg(meshes, direction, levels, title or f"{direction.upper()} ELEVATION", grid=grid)


def _axis_center(meshes: list[tuple[str, str, trimesh.Trimesh]], ax: int) -> float:
    """Midpoint of the model's extent along world axis `ax` (0=x, 1=y) from the baked meshes —
    so an auto-placed section cuts through the building, not the world origin."""
    lo = hi = None
    for _, _, m in meshes:
        b = getattr(m, "bounds", None)
        if b is None:
            continue
        lo = b[0][ax] if lo is None else min(lo, b[0][ax])
        hi = b[1][ax] if hi is None else max(hi, b[1][ax])
    return 0.0 if lo is None else (lo + hi) / 2.0


# ── W10-5 / C6: section annotation ───────────────────────────────────────────────────────────────
# Poché — the tone that fills what the cut plane passes THROUGH, so a reader can tell cut material
# from what is merely visible beyond it. That distinction is the whole point of a section, and a
# pure-linework section cannot make it: every edge looks equally solid.
#
# Grouped by what the material *is*, not by discipline, because poché answers "how heavy is this"
# rather than "whose scope is this". Anything unlisted gets the light tone — an unfamiliar class is
# drawn faintly rather than as if it were structure.
_POCHE = {
    "structure": (("ifcfooting", "ifcpile", "ifcslab", "ifccolumn", "ifcbeam", "ifcmember",
                   "ifcplate"), "#4a4a4a"),
    "enclosure": (("ifcwall", "ifcwallstandardcase", "ifccurtainwall", "ifcroof"), "#8a8a8a"),
    "opening": (("ifcdoor", "ifcwindow", "ifcstair", "ifcstairflight", "ifcramp"), "#d8d8d8"),
}
_POCHE_LIGHT = "#e8e8e8"
# LOD drives how much tone survives. At a coarse stage the drawing is about mass, so poché is solid;
# as the model sharpens the fill steps back and lets the linework carry the drawing. "line" is the
# historical behaviour — no fill at all.
_POCHE_OPACITY = {"coarse": 1.0, "fine": 0.45, "line": 0.0}
SECTION_LODS = frozenset(_POCHE_OPACITY)      # the API validates against this, not a second copy


def _poche_fill(cls: str, lod: str) -> str:
    if _POCHE_OPACITY.get(lod, 1.0) <= 0.0:
        return "none"
    low = (cls or "").lower()
    for classes, colour in _POCHE.values():
        if low in classes:
            return colour
    return _POCHE_LIGHT


# ── R21-HATCH: material hatch patterns on cut material ───────────────────────────────────────────
# A tone says "this is cut". A HATCH says what it is cut *through*. An issued detail separates
# concrete from reinforced concrete from steel from insulation from masonry by pattern, and a reader
# identifies the assembly from the patterns alone — which is why a set drawn in flat greys reads as a
# study and a set drawn with hatches reads as construction documents.
#
# Patterns are defined in PAPER space, not model space. That is the drafting convention: hatch
# spacing is a property of the sheet, so the same wall hatches identically at 1:100 and 1:10. The
# consequence is handled explicitly in `_hatch_for` below rather than ignored.
HATCH_MATERIALS = ("concrete", "reinforced_concrete", "steel", "masonry", "insulation",
                   "timber", "earth", "glass", "finish")

# keyword → category. Ordered: the first hit wins, so "reinforced concrete" must precede "concrete".
_MATERIAL_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("reinforced concrete", "rc ", "r.c.", "cast-in-place", "cast in place", "precast"), "reinforced_concrete"),
    (("concrete", "grout", "screed", "mortar"), "concrete"),
    (("steel", "metal", "aluminium", "aluminum", "iron", "galvan"), "steel"),
    (("masonry", "brick", "block", "cmu", "stone"), "masonry"),
    (("insulat", "mineral wool", "glass wool", "polyiso", "rockwool", "eps", "xps"), "insulation"),
    (("timber", "wood", "lumber", "plywood", "glulam", "clt"), "timber"),
    (("earth", "soil", "gravel", "sand", "hardcore", "fill"), "earth"),
    (("glass", "glazing", "glaz"), "glass"),
    (("gypsum", "plaster", "paint", "render", "tile", "carpet", "vinyl", "finish"), "finish"),
)

# When a model carries no material at all, fall back to what the class almost certainly is. Stated as
# a fallback rather than presented as fact — an unknown class hatches as `finish` (the lightest),
# never as structure.
_CLASS_MATERIAL_FALLBACK = {
    "ifcfooting": "reinforced_concrete", "ifcpile": "reinforced_concrete",
    "ifcslab": "reinforced_concrete", "ifccolumn": "reinforced_concrete",
    "ifcbeam": "reinforced_concrete", "ifcwall": "masonry", "ifcwallstandardcase": "masonry",
    "ifcmember": "steel", "ifcplate": "steel", "ifcrailing": "steel",
    "ifccurtainwall": "glass", "ifcwindow": "glass", "ifcdoor": "timber",
    "ifcroof": "concrete", "ifccovering": "finish",
}

# SVG <pattern> bodies, drawn on a `_HATCH_TILE`-unit tile in paper units. Deliberately conventional:
# 45° single for concrete, 45° cross for reinforced concrete, tight 45° for steel, horizontal courses
# for masonry, a soft batt zigzag for insulation, grain for timber, dots for earth.
_HATCH_TILE = 8
_HATCH_BODY: dict[str, str] = {
    "concrete": '<path d="M0,8 L8,0" stroke="{c}" stroke-width="0.6"/>'
                '<circle cx="2.5" cy="2.5" r="0.5" fill="{c}"/>'
                '<circle cx="6" cy="5.5" r="0.45" fill="{c}"/>',
    "reinforced_concrete": '<path d="M0,8 L8,0 M0,0 L8,8" stroke="{c}" stroke-width="0.6"/>',
    "steel": '<path d="M0,8 L8,0 M-2,2 L2,-2 M6,10 L10,6" stroke="{c}" stroke-width="0.9"/>',
    "masonry": '<path d="M0,2.6 H8 M0,5.3 H8" stroke="{c}" stroke-width="0.55"/>'
               '<path d="M4,0 V2.6 M0,2.6 V5.3 M4,5.3 V8" stroke="{c}" stroke-width="0.55"/>',
    "insulation": '<path d="M0,4 q2,-3 4,0 t4,0" fill="none" stroke="{c}" stroke-width="0.7"/>',
    "timber": '<path d="M0,2 H8 M0,6 H8" stroke="{c}" stroke-width="0.5"/>'
              '<path d="M1,0 q1.5,4 0,8 M5,0 q1.5,4 0,8" fill="none" stroke="{c}" stroke-width="0.45"/>',
    "earth": '<circle cx="2" cy="2" r="0.6" fill="{c}"/><circle cx="6" cy="4" r="0.55" fill="{c}"/>'
             '<circle cx="3.5" cy="6.5" r="0.5" fill="{c}"/>',
    "glass": '<path d="M0,8 L8,0" stroke="{c}" stroke-width="0.35"/>',
    "finish": '<path d="M0,8 L8,0" stroke="{c}" stroke-width="0.3" stroke-dasharray="1.5 2.5"/>',
}
_HATCH_INK = "#333"
# below this paper-space thickness a hatch is unreadable — the tile is wider than the element — so
# the fill degrades to the solid tone rather than emitting stripes nobody can resolve
MIN_HATCH_PX = 6.0


def material_by_class(model: ifcopenshell.file) -> dict[str, str]:
    """Dominant hatch material per IFC class, read from the model's OWN materials.

    Class-level rather than element-level because the cut pipeline carries a class, not a GUID — and
    for a section that is the distinction that matters: the slab hatches as reinforced concrete and
    the wall as masonry. Where a class genuinely mixes materials the majority wins, which is a stated
    approximation, not a silent one.
    """
    import collections

    import ifcopenshell.util.element as ue
    votes: dict[str, collections.Counter] = {}
    for el in model.by_type("IfcElement"):
        try:
            mat = ue.get_material(el)
        except Exception:                     # noqa: BLE001 — a broken material must not stop the map
            continue
        names: list[str] = []
        for attr in ("Name", "ForLayerSet", "MaterialLayers", "Materials"):
            v = getattr(mat, attr, None)
            if isinstance(v, str):
                names.append(v)
        # layer sets / constituent sets: collect every layer's material name
        for holder in (getattr(mat, "MaterialLayers", None) or getattr(mat, "Materials", None) or []):
            n = getattr(getattr(holder, "Material", holder), "Name", None)
            if isinstance(n, str):
                names.append(n)
        blob = " ".join(names).lower()
        if not blob:
            continue
        cat = next((c for keys, c in _MATERIAL_KEYWORDS if any(k in blob for k in keys)), None)
        if cat:
            votes.setdefault(el.is_a().lower(), collections.Counter())[cat] += 1
    return {cls: c.most_common(1)[0][0] for cls, c in votes.items() if c}


def hatch_material(cls: str, materials: dict[str, str] | None) -> str:
    """The hatch category for an IFC class — the model's own material first, the class fallback next."""
    low = (cls or "").lower()
    if materials and low in materials:
        return materials[low]
    return _CLASS_MATERIAL_FALLBACK.get(low, "finish")


def hatch_defs(categories) -> str:
    """`<defs>` for exactly the categories used. Emitting only what is referenced keeps a section of
    three materials from carrying nine unused pattern definitions."""
    want = [c for c in HATCH_MATERIALS if c in set(categories)]
    if not want:
        return ""
    out = ["<defs>"]
    for cat in want:
        body = _HATCH_BODY[cat].format(c=_HATCH_INK)
        out.append(f'<pattern id="hatch-{cat}" width="{_HATCH_TILE}" height="{_HATCH_TILE}" '
                   f'patternUnits="userSpaceOnUse">{body}</pattern>')
    out.append("</defs>")
    return "".join(out)


# ── R21-KEYNOTE-SECT: assembly annotation on sections ───────────────────────────────────────────
# Sections had NO annotation layer at all. `_leader_callout` above serves plans, and its boxed label
# is the right mark there — a plan tag names an object. A section keynote does something different:
# it names the MATERIAL of a layer in an assembly, so the convention is a left-hand text column with
# a leader to a dot on the component, unboxed. Reproducing the boxed plan tag here would be the wrong
# drawing.
#
# Keynotes annotate each DISTINCT assembly once, not every polygon. A wall cut at eight storeys is
# one keynote, not eight — annotating every instance is how a section becomes unreadable.
_KEYNOTE_NAME = {
    "reinforced_concrete": "RC {kind} AS PER STRUCTURAL DRAWINGS",
    "concrete": "{t}CONCRETE {kind}",
    "steel": "STEEL {kind}",
    "masonry": "{t}MASONRY {kind}",
    "insulation": "{t}INSULATION",
    "timber": "TIMBER {kind}",
    "earth": "COMPACTED FILL",
    "glass": "GLAZED {kind}",
    "finish": "{kind} FINISH",
}
_KEYNOTE_KIND = {
    "ifcwall": "WALL", "ifcwallstandardcase": "WALL", "ifcslab": "SLAB", "ifcbeam": "BEAM",
    "ifccolumn": "COLUMN", "ifcfooting": "FOOTING", "ifcpile": "PILE", "ifcroof": "ROOF",
    "ifcmember": "MEMBER", "ifcplate": "PLATE", "ifccurtainwall": "CURTAIN WALL",
    "ifcwindow": "WINDOW", "ifcdoor": "DOOR", "ifccovering": "COVERING",
    "ifcstair": "STAIR", "ifcstairflight": "STAIR FLIGHT", "ifcrailing": "RAILING",
}


def callout_bubble(cx: float, cy: float, detail: str, sheet: str, r: float = 15.0) -> str:
    """The reference bubble: detail number over sheet number, split by a horizontal rule.

    This is the mark that makes a set navigable — it is read as "go to detail 12 on sheet A-501". The
    split circle is not decoration: the two halves are two different identifiers, and a reader relies on
    the position to tell which is which.
    """
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#fff" stroke="#111" '
            f'stroke-width="1.1"/>'
            f'<line x1="{cx-r:.1f}" y1="{cy:.1f}" x2="{cx+r:.1f}" y2="{cy:.1f}" stroke="#111" '
            f'stroke-width="1.1"/>'
            f'<text x="{cx:.1f}" y="{cy-3:.1f}" text-anchor="middle" font-family="sans-serif" '
            f'font-size="{r*0.72:.1f}" font-weight="700">{_xesc(str(detail))}</text>'
            f'<text x="{cx:.1f}" y="{cy+r*0.72:.1f}" text-anchor="middle" font-family="sans-serif" '
            f'font-size="{r*0.6:.1f}">{_xesc(str(sheet))}</text>')


def detail_title_bubble(x: float, y: float, number: str, title: str, scale: str,
                        r: float = 13.0) -> str:
    """A detail's OWN identity, under the drawing: number in a bubble, then title and scale on a rule.

    Deliberately not the same mark as `callout_bubble` — a callout points AWAY and needs the
    destination sheet; a title bubble says "you have arrived" and names what this is and at what scale.
    Drawing them alike is how readers end up chasing a reference back to the drawing they are on.
    """
    tx = x + r + 10
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#fff" stroke="#111" '
            f'stroke-width="1.4"/>'
            f'<text x="{x:.1f}" y="{y + r*0.36:.1f}" text-anchor="middle" font-family="sans-serif" '
            f'font-size="{r*1.0:.1f}" font-weight="700">{_xesc(str(number))}</text>'
            f'<text x="{tx:.1f}" y="{y - 2:.1f}" font-family="sans-serif" font-size="13" '
            f'font-weight="700">{_xesc(str(title).upper())}</text>'
            f'<text x="{tx:.1f}" y="{y + 13:.1f}" font-family="sans-serif" font-size="11" '
            f'fill="#555">{_xesc(str(scale))}</text>'
            f'<line x1="{x - r:.1f}" y1="{y + r + 5:.1f}" x2="{tx + 190:.1f}" y2="{y + r + 5:.1f}" '
            f'stroke="#111" stroke-width="1.4"/>')


# ── R21-TAGS: element tags that do not sit on top of each other ─────────────────────────────────
# A tag names an instance ("D2") and usually carries the number a reader came for ("900 × 2100").
# `space_tags` already labels rooms, but rooms are large and far apart; element tags are the hard
# case because doors and windows cluster, so the real problem is not "what does it say" but
# **placement**. Two tags on one baseline are worse than one tag, because a reader cannot tell which
# element either belongs to.
#
# The rule: a tag prefers to sit on its element. When that position is taken it is displaced to the
# nearest free slot, and displacement is exactly what earns it a leader — a tag drawn away from its
# element without a leader is an unattributed number.
TAG_W, TAG_H = 30.0, 14.0     # paper-space tag box
TAG_GAP = 3.0                 # minimum clear space between tag boxes
MAX_TAGS = 400                # past this a plan is a grey mass; the largest elements win


def _tag_hits(x: float, y: float, placed: list[tuple[float, float]]) -> bool:
    for px, py in placed:
        if abs(px - x) < TAG_W + TAG_GAP and abs(py - y) < TAG_H + TAG_GAP:
            return True
    return False


def place_tags(anchors: list[tuple[float, float, str]],
               max_tags: int = MAX_TAGS) -> list[dict]:
    """Place a tag for each anchor, displacing collisions onto a ring of candidate offsets.

    Deterministic: the same anchors in the same order always produce the same placement, because a
    drawing that shuffles its tags between two runs cannot be diffed or checked.

    Each result carries ``leader`` — True when the tag had to move off its element, which is the only
    case where a leader line is warranted. Drawing a leader on an undisplaced tag is noise; omitting
    one on a displaced tag is a number nobody can attribute.
    """
    # candidate offsets, nearest first: on the element, then the four sides, then the diagonals
    ring = [(0.0, 0.0),
            (0.0, -(TAG_H + TAG_GAP) * 1.6), (0.0, (TAG_H + TAG_GAP) * 1.6),
            (-(TAG_W + TAG_GAP) * 1.1, 0.0), ((TAG_W + TAG_GAP) * 1.1, 0.0),
            (-(TAG_W + TAG_GAP) * 1.1, -(TAG_H + TAG_GAP) * 1.6),
            ((TAG_W + TAG_GAP) * 1.1, -(TAG_H + TAG_GAP) * 1.6),
            (-(TAG_W + TAG_GAP) * 1.1, (TAG_H + TAG_GAP) * 1.6),
            ((TAG_W + TAG_GAP) * 1.1, (TAG_H + TAG_GAP) * 1.6)]
    placed: list[tuple[float, float]] = []
    out: list[dict] = []
    for ax, ay, text in anchors[:max_tags]:
        spot = None
        for k, (dx, dy) in enumerate(ring):
            if not _tag_hits(ax + dx, ay + dy, placed):
                spot = (ax + dx, ay + dy, k > 0)
                break
        if spot is None:
            # every candidate is taken. Push straight up in whole steps until something is free
            # rather than dropping the tag: a silently omitted tag is an element that looks untagged.
            step, n = (TAG_H + TAG_GAP) * 1.6, 2
            while _tag_hits(ax, ay - step * n, placed) and n < 60:
                n += 1
            spot = (ax, ay - step * n, True)
        x, y, displaced = spot
        placed.append((x, y))
        out.append({"x": round(x, 2), "y": round(y, 2), "anchor": [round(ax, 2), round(ay, 2)],
                    "text": text, "leader": bool(displaced)})
    return out


def tag_svg(tags: list[dict], color: str = "#111") -> str:
    """Boxed tags plus a leader for every displaced one."""
    out: list[str] = []
    for t in tags:
        x, y = t["x"], t["y"]
        if t.get("leader"):
            ax, ay = t["anchor"]
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                       f'stroke="{color}" stroke-width="0.5"/>'
                       f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="1.6" fill="{color}"/>')
        out.append(f'<rect x="{x - TAG_W / 2:.1f}" y="{y - TAG_H / 2:.1f}" width="{TAG_W}" '
                   f'height="{TAG_H}" rx="2" fill="#fff" stroke="{color}" stroke-width="0.8"/>'
                   f'<text x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle" '
                   f'font-family="sans-serif" font-size="9">{_xesc(str(t["text"]))}</text>')
    return "".join(out)


# ── R21-BREAKLINE: stop a view mid-element, honestly ────────────────────────────────────────────
# A detail that runs to the sheet edge tells the reader nothing about what happens beyond it — the
# element might stop there, or continue for thirty metres. The break line is the conventional mark
# that says "this element continues; the drawing does not". Without it, a partial view is
# indistinguishable from a complete one, which is the same class of error as a clash report that
# does not say which pairs it tested.
BREAK_AMPLITUDE = 6.0         # paper-space depth of the zig
BREAK_PERIOD = 22.0           # distance between zigs along the run


def break_line(x1: float, y1: float, x2: float, y2: float,
               amplitude: float = BREAK_AMPLITUDE, period: float = BREAK_PERIOD) -> str:
    """The conventional zig-zag break across a run, as an SVG polyline.

    Degenerate runs return a straight segment rather than nothing: a break line that vanishes because
    the view happened to be narrow would silently turn a partial view back into an apparently
    complete one.
    """
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-6:
        return ""
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux                                   # unit normal: the zig direction
    pts = [(x1, y1)]
    n = max(1, int(length // max(period, 1.0)))
    for i in range(n):
        # one zig per period, centred in its span, alternating sides so the mark reads as a break
        t = (i + 0.5) * (length / n)
        s = amplitude if i % 2 == 0 else -amplitude
        pts.append((x1 + ux * (t - length / (n * 4)), y1 + uy * (t - length / (n * 4))))
        pts.append((x1 + ux * t + nx * s, y1 + uy * t + ny * s))
        pts.append((x1 + ux * (t + length / (n * 4)), y1 + uy * (t + length / (n * 4))))
    pts.append((x2, y2))
    path = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    return f'<polyline points="{path}" fill="none" stroke="#111" stroke-width="0.8"/>'


KEYNOTE_GUTTER = 320          # paper-space room for the text column, left of the level datums
MAX_KEYNOTES = 14             # past this a section stops being readable; the largest assemblies win
COMPONENT_COL = 170           # R21-DIM-COMPONENT: right-hand column for the assembly build-ups
COMPONENT_BAND_H = 34         # paper height one assembly's layer stack occupies, split in proportion
MAX_COMPONENT_DIMS = 6        # thickest assemblies win; the remainder is COUNTED on the sheet, not
                              # dropped silently — a truncated list that says nothing reads as complete


def keynote_text(cls: str, material: str, thickness_m: float | None = None) -> str:
    """The keynote for one cut assembly, built from what the MODEL knows: its material, its class and
    its measured thickness. Nothing is invented — an unrecognised class falls back to the class name
    with the IFC prefix stripped, which is still true, rather than to a guess that reads as authored."""
    kind = _KEYNOTE_KIND.get((cls or "").lower())
    if not kind:
        kind = (cls or "ELEMENT").upper().removeprefix("IFC") or "ELEMENT"
    t = ""
    if thickness_m and thickness_m > 0.001:
        t = f"{round(thickness_m * 1000):d}mm "
    return _KEYNOTE_NAME.get(material, "{t}{kind}").format(t=t, kind=kind).strip()


def _keynote_leaders(entries, col_x: float, top: float, bottom: float,
                     anchor_right: bool) -> str:
    """Stack keynotes in a column and lead each to its component.

    Rows are pushed apart so text never overlaps — an annotation layer that collides is worse than
    none, because a reader cannot tell which label belongs to which leader.
    """
    if not entries:
        return ""
    rows = sorted(entries, key=lambda e: e[1])          # by target y, so leaders rarely cross
    step = 15.0
    out: list[str] = []
    last_y = -1e9
    for tx, ty, text in rows:
        ly = max(ty, last_y + step, top)
        ly = min(ly, bottom)
        last_y = ly
        a = "end" if anchor_right else "start"
        lx = col_x
        out.append(
            f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="1.9" fill="#111"/>'
            f'<polyline points="{tx:.1f},{ty:.1f} {(lx + (14 if not anchor_right else -14)):.1f},{ly:.1f} '
            f'{lx:.1f},{ly:.1f}" fill="none" stroke="#111" stroke-width="0.5"/>'
            f'<text x="{lx + (-4 if anchor_right else 4):.1f}" y="{ly + 3:.1f}" text-anchor="{a}" '
            f'font-family="sans-serif" font-size="9.5" fill="#111">{_xesc(text)}</text>')
    return "".join(out)


def section_drawing_svg(meshes, axis: str, offset: float, levels: list[dict], title: str,
                        grid: dict | None = None, lod: str = "coarse", width: int = 1300,
                        hatch: bool = True, materials: dict[str, str] | None = None,
                        keynotes: bool = True, tags: list[dict] | None = None,
                        components: list[dict] | None = None) -> str:
    """An **annotated** section: poché, level datums, grid bubbles and a floor-to-floor dimension
    chain — the things that make a cut issuable rather than merely correct.

    A section exists to communicate vertical relationships, so the dimension chain is not decoration:
    the floor-to-floor rises and the overall height are the numbers a reader came for, and until now
    the only way to get them was to measure the screen.
    """
    if lod not in SECTION_LODS:
        # refuse rather than fall back: a silently-defaulted LOD produces a plausible drawing at the
        # wrong weight, and nothing downstream would show that the request was misspelled
        raise ValueError(f"lod must be one of {sorted(SECTION_LODS)}, got {lod!r}")
    view = "section-x" if axis == "x" else "section-y"
    classed = cut_baked_classed(meshes, view, offset)
    if not classed:
        return to_svg([], title=title, subtitle=f"{axis.upper()} = {offset:.2f} m — no geometry on this cut")
    polys = [p for _, p in classed]
    allp = np.vstack(polys)
    mn, mx = allp.min(axis=0), allp.max(axis=0)
    span = np.maximum(mx - mn, 1e-6)
    # the keynote column needs its own room: the existing 130 gutter is already spoken for by the
    # level-datum labels, and letting the two share it would overlap annotation with annotation
    # R21-DIM-COMPONENT: the assembly strings need their own column. Claimed only when there is
    # something to put in it — an empty reserved column would shrink every drawing that has no
    # layered assemblies, which is most sections at coarse LOD.
    comp_col = COMPONENT_COL if components else 0
    gutter, dim_col, pad, top = (KEYNOTE_GUTTER if keynotes else 130), 90, 30, 40
    dim_col += comp_col
    draw_w = width - 2 * pad - gutter - dim_col
    scale = draw_w / span[0]
    draw_h = span[1] * scale
    height = int(draw_h + pad + top + 60)
    ox, oy = pad + gutter, top

    def T(u, v):
        return ox + (u - mn[0]) * scale, oy + draw_h - (v - mn[1]) * scale

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" fill="#fff"/>']

    # cut material first, as filled loops — a section polyline from a solid IS a closed loop
    opacity = _POCHE_OPACITY.get(lod, 1.0)
    used_hatch: set[str] = set()
    poly_svg: list[str] = []
    for cls, poly in classed:
        pts = " ".join(f"{T(p[0], p[1])[0]:.1f},{T(p[0], p[1])[1]:.1f}" for p in poly)
        fill = _poche_fill(cls, lod)
        # R21-HATCH: hatch the cut when we can READ it. A hatch tile is a fixed size on the sheet, so
        # an element thinner than a couple of tiles would emit stripes nobody can resolve — at that
        # size the honest mark is the solid tone. This is why the same wall hatches at 1:10 and reads
        # as a filled sliver at 1:100, which is exactly what a drafter would do by hand.
        if hatch and fill != "none":
            p = np.asarray(poly, dtype=float)
            paper = min((p[:, 0].max() - p[:, 0].min()), (p[:, 1].max() - p[:, 1].min())) * scale
            if paper >= MIN_HATCH_PX:
                cat = hatch_material(cls, materials)
                used_hatch.add(cat)
                poly_svg.append(f'<polygon points="{pts}" fill="url(#hatch-{cat})" '
                                f'stroke="#111" stroke-width="1"/>')
                continue
        fo = f' fill-opacity="{opacity:.2f}"' if fill != "none" else ""
        poly_svg.append(f'<polygon points="{pts}" fill="{fill}"{fo} stroke="#111" stroke-width="1"/>')
    if used_hatch:
        out.append(hatch_defs(used_hatch))
    out.extend(poly_svg)

    # grid bubbles on the in-plane horizontal: a section on X draws world Y, and vice versa
    if grid:
        for g, label in (grid["y"] if axis == "x" else grid["x"]):
            if g < mn[0] - 0.5 or g > mx[0] + 0.5:
                continue
            gx, _ = T(g, mn[1])
            out.append(f'<line x1="{gx:.1f}" y1="{oy-24:.1f}" x2="{gx:.1f}" y2="{oy+draw_h:.1f}" '
                       f'stroke="#bbb" stroke-width="0.5" stroke-dasharray="5 3"/>'
                       f'<circle cx="{gx:.1f}" cy="{oy-24:.1f}" r="9" fill="#fff" stroke="#111"/>'
                       f'<text x="{gx:.1f}" y="{oy-21:.1f}" text-anchor="middle" '
                       f'font-family="sans-serif" font-size="10" font-weight="700">{_xesc(str(label))}</text>')

    # R21-SPACE-TAG-SECT: room names on the cut, at each space's centroid in the section's own frame.
    # `space_tags_section` already filtered to rooms the cut plane passes through, so this only has to
    # place them — and it clips to the drawn extent for the same reason the plan does, since a room
    # whose centroid falls outside the framed area would print its label over the titleblock.
    for tag in (tags or []):
        if not (mn[0] <= tag["x"] <= mx[0] and mn[1] <= tag["y"] <= mx[1]):
            continue
        tx, tyy = T(tag["x"], tag["y"])              # room names are user data — escape &/<
        out.append(f'<text x="{tx:.1f}" y="{tyy:.1f}" text-anchor="middle" font-family="sans-serif" '
                   f'font-size="12" font-weight="700" fill="#333">{_xesc(str(tag["name"]))}</text>')
        if tag.get("area"):
            out.append(f'<text x="{tx:.1f}" y="{tyy+13:.1f}" text-anchor="middle" '
                       f'font-family="sans-serif" font-size="10" fill="#777">{tag["area"]:.1f} m²</text>')

    # C6 reference-line datums: the level line runs the full width and past the drawing on the left,
    # because a datum is a reference for the whole drawing rather than a label on one element
    shown = [lv for lv in levels if mn[1] - 0.1 <= lv["elevation"] <= mx[1] + 0.1]
    for lv in shown:
        _, ly = T(mn[0], lv["elevation"])
        out.append(f'<line x1="{ox-100:.1f}" y1="{ly:.1f}" x2="{ox+draw_w:.1f}" y2="{ly:.1f}" '
                   f'stroke="#0a6" stroke-width="0.6" stroke-dasharray="8 4"/>'
                   f'<circle cx="{ox-100:.1f}" cy="{ly:.1f}" r="4" fill="#0a6"/>'
                   f'<text x="{ox-92:.1f}" y="{ly-3:.1f}" font-family="sans-serif" font-size="10" '
                   f'fill="#0a6">{_xesc(str(lv["name"] or ""))}  +{lv["elevation"]*1000:.0f}</text>')

    # R21-KEYNOTE-SECT: annotate each DISTINCT assembly once.
    # Grouping is what makes this readable rather than noise — a wall cut at eight storeys is ONE
    # keynote, not eight. Where a group has several instances the largest carries the leader, because
    # a dot on a sliver is a dot the reader cannot associate with anything.
    if keynotes and lod != "line":
        groups: dict[tuple, list] = {}
        for cls, poly in classed:
            p = np.asarray(poly, dtype=float)
            w, h = p[:, 0].max() - p[:, 0].min(), p[:, 1].max() - p[:, 1].min()
            thick = min(w, h)
            mat = hatch_material(cls, materials)
            # round the thickness so 199 mm and 201 mm of the same wall are ONE assembly, not two
            key = (cls, mat, round(thick, 2))
            groups.setdefault(key, []).append((w * h, p))
        picked = []
        for (cls, mat, thick), members in groups.items():
            area, p = max(members, key=lambda m: m[0])
            cx, cy = T(float(p[:, 0].mean()), float(p[:, 1].mean()))
            picked.append((area, cx, cy, keynote_text(cls, mat, thick)))
        picked.sort(key=lambda e: -e[0])
        entries = [(cx, cy, txt) for _, cx, cy, txt in picked[:MAX_KEYNOTES]]
        out.append(_keynote_leaders(entries, ox - 118, top, oy + draw_h, anchor_right=True))

    # the floor-to-floor chain + an overall dimension, in the right-hand column
    dx = ox + draw_w + 34
    for a, b in zip(shown, shown[1:]):
        _, ya = T(mn[0], a["elevation"])
        _, yb = T(mn[0], b["elevation"])
        out.append(_dim_v(dx, ya, yb, f'{(b["elevation"] - a["elevation"]) * 1000:.0f}'))
    if len(shown) > 1:
        _, y0 = T(mn[0], shown[0]["elevation"])
        _, y1 = T(mn[0], shown[-1]["elevation"])
        out.append(_dim_v(dx + 40, y0, y1,
                          f'{(shown[-1]["elevation"] - shown[0]["elevation"]) * 1000:.0f} OVERALL'))

    # R21-DIM-COMPONENT: the assembly build-ups, beside the floor-to-floor chain. The vertical chain
    # says how high; these say what it is made of and how thick each layer is — what a fabricator
    # measures. Each layer band is drawn in PROPORTION to its thickness, so a 12 mm board next to a
    # 150 mm insulation reads as the sliver it is rather than as an equal stripe.
    if components:
        cx0 = ox + draw_w + 34 + 88
        cy = top + 4
        out.append(f'<text x="{cx0}" y="{cy}" font-family="sans-serif" font-size="10" '
                   f'font-weight="700" fill="#111">ASSEMBLIES</text>')
        cy += 14
        for a in components[:MAX_COMPONENT_DIMS]:
            usable = [ly for ly in a["layers"] if (ly.get("thickness_m") or 0) > 0]
            total = sum(ly["thickness_m"] for ly in usable) or 1.0
            out.append(f'<text x="{cx0}" y="{cy}" font-family="sans-serif" font-size="9" '
                       f'font-weight="700" fill="#333">{_xesc(str(a["name"])[:22])}</text>')
            cy += 4
            band_top = cy
            for ly in usable:
                h = max(2.0, COMPONENT_BAND_H * ly["thickness_m"] / total)
                out.append(f'<rect x="{cx0}" y="{cy:.1f}" width="14" height="{h:.1f}" '
                           f'fill="none" stroke="#111" stroke-width="0.6"/>')
                label = ly.get("material") or ly.get("name") or "—"
                out.append(f'<text x="{cx0+18}" y="{cy + h/2 + 3:.1f}" font-family="sans-serif" '
                           f'font-size="8" fill="#111">{ly["thickness_m"]*1000:.0f}  '
                           f'{_xesc(str(label)[:16])}</text>')
                cy += h
            # the overall bracket carries BOTH numbers when they disagree — see component_dims_section:
            # declared and measured are different claims and reconciling them here would invent one
            if a["declared_m"] is not None:
                out.append(f'<line x1="{cx0-5}" y1="{band_top:.1f}" x2="{cx0-5}" y2="{cy:.1f}" '
                           f'stroke="#111" stroke-width="0.6"/>')
                out.append(f'<text x="{cx0-8}" y="{(band_top+cy)/2+3:.1f}" text-anchor="end" '
                           f'font-family="sans-serif" font-size="8" font-weight="700" '
                           f'fill="#111">{a["declared_m"]*1000:.0f}</text>')
            if a["agrees"] is False:
                out.append(f'<text x="{cx0}" y="{cy+9:.1f}" font-family="sans-serif" font-size="7.5" '
                           f'font-weight="700" fill="#b00">! modelled {a["measured_m"]*1000:.0f} '
                           f'({a["delta_m"]*1000:+.0f})</text>')
                cy += 9
            elif a["declared_m"] is None:
                out.append(f'<text x="{cx0}" y="{cy+9:.1f}" font-family="sans-serif" font-size="7.5" '
                           f'fill="#b00">! layer thickness not stated</text>')
                cy += 9
            cy += 12
        if len(components) > MAX_COMPONENT_DIMS:
            out.append(f'<text x="{cx0}" y="{cy:.1f}" font-family="sans-serif" font-size="8" '
                       f'fill="#555">+{len(components)-MAX_COMPONENT_DIMS} more assemblies</text>')

    ty = height - 24
    note = f'{axis.upper()} = {offset:.2f} m  ·  {len(classed)} cut elements  ·  poché {lod}'
    out.append(f'<line x1="{pad}" y1="{ty-12}" x2="{width-pad}" y2="{ty-12}" stroke="#111" stroke-width="1"/>'
               f'<text x="{pad}" y="{ty+8}" font-family="sans-serif" font-size="16" '
               f'font-weight="700">{_xesc(title)}</text>'
               f'<text x="{width-pad}" y="{ty+8}" text-anchor="end" font-family="sans-serif" '
               f'font-size="12" fill="#555">{note}</text>')
    out.append("</svg>")
    return "".join(out)


def section_svg(model: ifcopenshell.file, axis: str, offset: float | None = None,
                title: str = "SECTION", lod: str = "coarse", annotate: bool = True,
                hatch: bool = True, keynotes: bool = True, rooms: bool = True,
                components: bool = True) -> str:
    """Cut the model on a vertical plane. `offset` is the world coordinate (metres) of the cut on the
    perpendicular axis; when None the cut auto-centres on the model so it lands through the building
    regardless of where the model sits relative to the origin.

    Annotated by default (poché + level datums + grid + dimension chain). `annotate=False` returns the
    bare linework, which is what a CAD hand-off or a further-processing caller wants.
    """
    view = "section-x" if axis == "x" else "section-y"
    meshes = bake(model)
    if offset is None:
        offset = _axis_center(meshes, 0 if axis == "x" else 1)
    if not annotate:
        return to_svg(cut_baked(meshes, view, offset), title=title,
                      subtitle=f"{axis.upper()} = {offset:.2f} m")
    # the material map serves BOTH the hatch and the keynote text, so read it when either wants it —
    # scoping it to `hatch` alone would make hatch=false silently downgrade keynotes to class defaults
    return section_drawing_svg(meshes, axis, offset, storey_elevations(model), title,
                               grid=grid_from_meshes(meshes), lod=lod, hatch=hatch,
                               keynotes=keynotes,
                               # R21-SPACE-TAG-SECT — computed here, beside the cut it belongs to, so a
                               # section is annotated by default exactly as a plan is. `rooms=False`
                               # returns the un-tagged cut for a CAD hand-off.
                               tags=space_tags_section(model, axis, offset) if rooms else None,
                               # R21-DIM-COMPONENT — the layer build-ups of the assemblies this cut
                               # passes through. Empty list when the model carries no layer sets, which
                               # claims the column's width back rather than reserving it for nothing.
                               components=(component_dims_section(model, axis, offset) or None)
                               if components else None,
                               materials=material_by_class(model) if (hatch or keynotes) else None)


def plan_file(ifc_path: str, elevation: float, cut_height: float = 1.2, title: str = "PLAN") -> str:
    return plan_svg(open_model(ifc_path), elevation, cut_height, title)


# --- DXF export (CAD interchange) -------------------------------------------
def plan_dxf(model: ifcopenshell.file, elevation: float = 0.0, cut_height: float = 1.2) -> str:
    """Plan cut linework as R12 DXF — a horizontal section at `elevation + cut_height`."""
    from . import dxf
    return dxf.polylines_to_dxf(cut(model, "plan", elevation + cut_height), layer="PLAN")


def section_dxf(model: ifcopenshell.file, axis: str, offset: float | None = None) -> str:
    """Vertical section linework as R12 DXF; `offset` None auto-centres the cut on the model."""
    from . import dxf
    meshes = bake(model)
    if offset is None:
        offset = _axis_center(meshes, 0 if axis == "x" else 1)
    view = "section-x" if axis == "x" else "section-y"
    return dxf.polylines_to_dxf(cut_baked(meshes, view, offset), layer="SECTION")


def elevation_dxf(model: ifcopenshell.file, direction: str = "north") -> str:
    """Projected elevation outlines as R12 DXF (closed silhouettes)."""
    from . import dxf
    return dxf.polylines_to_dxf(elevation_outlines(bake(model), direction), layer="ELEVATION",
                                closed_hint=True)


# --- sheet composer (Revit-style sheet sets & title blocks) -----------------
_PT_PER_M = 1.0 / 0.000352778  # paper points per metre at 1:1

# page sizes in points (landscape)
PAGES = {"A3": (1190.55, 841.89), "A1": (2383.94, 1683.78), "A4": (841.89, 595.28)}


def _view_for_spec(meshes, spec: dict) -> tuple[list[np.ndarray], str, str]:
    kind = spec.get("kind", "plan")
    if kind == "section":
        axis = spec.get("axis", "x")
        off = float(spec.get("offset", 0.0))
        polys = cut_baked(meshes, "section-x" if axis == "x" else "section-y", off)
        return polys, spec.get("title", f"SECTION {axis.upper()}"), f"{axis.upper()}={off:.1f} m"
    if kind == "elevation":
        d = spec.get("direction", "north")
        items = elevation_outlines(meshes, d, with_depth=True)
        items.sort(key=lambda it: it[1])  # far→near for hidden-line removal
        return [c for c, _ in items], spec.get("title", f"{d.upper()} ELEVATION"), f"{d} elev"
    elev = float(spec.get("elevation", 0.0)) + float(spec.get("cut_height", 1.2))
    polys = cut_baked(meshes, "plan", elev)
    return polys, spec.get("title", "PLAN"), f"cut @ {elev:.2f} m"


def _vertical_extras(spec, grid, levels, mn, mx, ox, oy, dh, scale):
    """Grid verticals + bubbles + storey level datums for a section/elevation cell."""
    extras = []
    spanx = (mx[0] - mn[0]) * scale
    kind = spec.get("kind")
    # which world grid maps to the cell's horizontal axis, and any horizontal flip
    if kind == "section":
        glines = grid["y"] if spec.get("axis", "x") == "x" else grid["x"]
        flip = False
    else:  # elevation
        _, flip, depth_axis, _ = _DIRS.get(spec.get("direction", "north"), _DIRS["north"])
        glines = grid["x"] if depth_axis == 1 else grid["y"]
    for g, lbl in glines:
        h = -g if flip else g
        if not (mn[0] - 0.5 <= h <= mx[0] + 0.5):
            continue
        px = ox + (h - mn[0]) * scale
        extras.append(("line", px, oy - 9, px, oy + dh, True))
        extras.append(("bub", px, oy - 9, 5.5, lbl))
    for lv in levels:  # storey datums (Z → vertical axis)
        z = lv["elevation"]
        if not (mn[1] - 0.1 <= z <= mx[1] + 0.1):
            continue
        py = oy + dh - (z - mn[1]) * scale
        extras.append(("lvl", ox, ox + spanx, py))
    return extras


def _plan_extras(grid, mn, mx, ox, oy, dh, scale):
    """Grid lines + bubbles + overall dimensions for a plan cell, in sheet coords."""
    extras = []
    spanx = (mx[0] - mn[0]) * scale
    for gx, lbl in grid["x"]:
        if not (mn[0] - 0.5 <= gx <= mx[0] + 0.5):
            continue
        px = ox + (gx - mn[0]) * scale
        extras.append(("line", px, oy - 9, px, oy + dh, True))
        extras.append(("bub", px, oy - 9, 5.5, lbl))
    for gy, lbl in grid["y"]:
        if not (mn[1] - 0.5 <= gy <= mx[1] + 0.5):
            continue
        py = oy + dh - (gy - mn[1]) * scale
        extras.append(("line", ox - 9, py, ox + spanx, py, True))
        extras.append(("bub", ox - 9, py, 5.5, lbl))
    # overall extents (mm)
    extras.append(("dim", ox, oy + dh + 9, ox + spanx, oy + dh + 9, f"{round((mx[0]-mn[0])*1000)}"))
    extras.append(("dim", ox - 18, oy, ox - 18, oy + dh, f"{round((mx[1]-mn[1])*1000)}"))
    return extras


def compose(meshes, specs: list[dict], page: str = "A3", cols: int = 2,
            margin: float = 36.0, tb_h: float = 90.0, annotate: bool = True,
            levels: list[dict] | None = None) -> dict:
    pw, ph = PAGES.get(page, PAGES["A3"])
    rows = max(1, -(-len(specs) // cols))
    area_x0, area_y0 = margin, margin
    area_w = pw - 2 * margin
    area_h = ph - 2 * margin - tb_h
    cell_w, cell_h = area_w / cols, area_h / rows
    pad, label_h, gut = 14.0, 20.0, 20.0
    grid = grid_from_meshes(meshes) if annotate else {"x": [], "y": []}
    levels = levels or []

    views = []
    for i, spec in enumerate(specs):
        polys, label, sub = _view_for_spec(meshes, spec)
        kind = spec.get("kind", "plan")
        col, row = i % cols, i // cols
        cx = area_x0 + col * cell_w
        cy = area_y0 + tb_h + row * cell_h  # y-down (top-left origin)
        g = gut if annotate else 0.0
        iw, ih = cell_w - 2 * pad - g, cell_h - 2 * pad - label_h - g
        scale_text = "no geometry"
        placed: list[np.ndarray] = []
        extras: list = []
        if polys:
            allp = np.vstack(polys)
            mn, mx = allp.min(axis=0), allp.max(axis=0)
            span = np.maximum(mx - mn, 1e-6)
            scale = min(iw / span[0], ih / span[1])
            dh = span[1] * scale
            ox = cx + pad + g + (iw - span[0] * scale) / 2
            oy = cy + pad + label_h
            for poly in polys:
                pts = np.empty_like(poly, dtype=float)
                pts[:, 0] = ox + (poly[:, 0] - mn[0]) * scale
                pts[:, 1] = oy + dh - (poly[:, 1] - mn[1]) * scale  # flip Y within cell
                placed.append(pts)
            ratio = round(1.0 / (scale * 0.000352778))
            scale_text = f"1:{ratio}"
            if annotate:
                if kind == "plan":
                    extras = _plan_extras(grid, mn, mx, ox, oy, dh, scale)
                else:  # section / elevation
                    extras = _vertical_extras(spec, grid, levels, mn, mx, ox, oy, dh, scale)
        views.append({"label": label, "sub": sub, "scale_text": scale_text, "kind": kind,
                      "filled": kind == "elevation",
                      "rect": (cx, cy, cell_w, cell_h), "polys": placed, "extras": extras})
    return {"page": (pw, ph), "tb_h": tb_h, "margin": margin, "views": views}


def sheet(model: ifcopenshell.file, specs: list[dict], meta: dict,
          page: str = "A3", cols: int = 2, fmt: str = "svg"):
    layout = compose(bake(model), specs, page=page, cols=cols, levels=storey_elevations(model))
    if fmt == "dxf":
        return render_sheet_dxf(layout, meta)
    return render_sheet_pdf(layout, meta) if fmt == "pdf" else render_sheet_svg(layout, meta)


def sheet_file(ifc_path: str, specs: list[dict], meta: dict, page="A3", cols=2, fmt="svg"):
    return sheet(open_model(ifc_path), specs, meta, page, cols, fmt)


def default_sheet(model: ifcopenshell.file, meta: dict, page: str = "A3", fmt: str = "svg",
                  storey: str | None = None, max_plans: int = 4):
    """One-call **key-plan** sheet: representative plans + a section + an elevation, all on one page. Bakes
    geometry once. `storey` renders just that level's plan; otherwise up to `max_plans` levels are sampled
    evenly across the building (a tall tower has one sheet per level in the full set — cramming 30 plans on
    one page is neither fast nor legible). Returns SVG string or PDF bytes."""
    meshes = bake(model)
    xs = [m.bounds for _, _, m in meshes if m.bounds is not None]
    mid_x = float(np.mean([b[:, 0].mean() for b in xs])) if xs else 0.0

    storeys = storey_elevations(model)
    top = max((s["elevation"] for s in storeys), default=0.0)
    below_roof = [s for s in storeys if s["elevation"] < top - 0.01]
    if storey:                                            # a single named level
        chosen = [s for s in below_roof if (s["name"] or "") == storey] or below_roof[:1]
    elif len(below_roof) <= max_plans:
        chosen = below_roof
    else:                                                 # sample evenly (keep first + last + spread)
        step = (len(below_roof) - 1) / (max_plans - 1)
        idx = sorted({round(i * step) for i in range(max_plans)})
        chosen = [below_roof[i] for i in idx]
    specs = [{"kind": "plan", "elevation": s["elevation"], "title": f"PLAN {s['name']}"} for s in chosen]
    specs.append({"kind": "section", "axis": "x", "offset": mid_x, "title": "SECTION A-A"})
    specs.append({"kind": "elevation", "direction": "north", "title": "NORTH ELEVATION"})

    layout = compose(meshes, specs, page=page, cols=2, levels=storeys)
    if fmt == "dxf":
        return render_sheet_dxf(layout, meta)
    return render_sheet_pdf(layout, meta) if fmt == "pdf" else render_sheet_svg(layout, meta)
