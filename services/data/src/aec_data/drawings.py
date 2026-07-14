"""2D documentation — plan & section generation (Revit-style sheets, openBIM way).

Cuts the model geometry with a plane (trimesh section) and renders the cut polylines to
SVG. Plans are horizontal cuts at a storey height; sections are vertical cuts. Output is
plain SVG so it embeds in the viewer, prints, or drops onto a sheet with a title block.
"""
from __future__ import annotations

import multiprocessing
import warnings
from typing import Any

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.unit as uunit
import numpy as np
import trimesh

from .ifc_loader import open_model

warnings.filterwarnings("ignore")

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


def bake(model: ifcopenshell.file) -> list[tuple[str, trimesh.Trimesh]]:
    """Bake every element's world-space mesh ONCE so many views can section the same set."""
    it = geom.iterator(_world_settings(geom), model, max(1, multiprocessing.cpu_count() - 1))
    meshes: list[tuple[str, trimesh.Trimesh]] = []
    if not it.initialize():
        return meshes
    while True:
        shape = it.get()
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if verts.size and faces.size:
            el = model.by_guid(shape.guid)
            cls = el.is_a() if el else shape.type
            try:
                meshes.append((cls, trimesh.Trimesh(vertices=verts, faces=faces, process=False)))
            except Exception:
                pass
        if not it.next():
            break
    return meshes


def cut_baked(meshes: list[tuple[str, trimesh.Trimesh]], view: str, offset: float,
              classes: list[str] | None = None) -> list[np.ndarray]:
    """Section pre-baked meshes; returns (n,2) polylines in the view's drawing plane."""
    normal, axes = _VIEWS[view]
    origin = normal * offset
    want = {c.lower() for c in classes} if classes else None
    polylines: list[np.ndarray] = []
    for cls, mesh in meshes:
        if want and cls.lower() not in want:
            continue
        try:
            sec = mesh.section(plane_origin=origin, plane_normal=normal)
            if sec is not None:
                for poly in sec.discrete:
                    polylines.append(np.asarray(poly)[:, axes])
        except Exception:
            pass
    return polylines


def cut(model: ifcopenshell.file, view: str, offset: float,
        classes: list[str] | None = None) -> list[np.ndarray]:
    """Return cut polylines as a list of (n,2) arrays in the view's drawing plane."""
    return cut_baked(bake(model), view, offset, classes)


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
    for cls, mesh in meshes:
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
                     tags: list[dict] | None = None, callouts: list[dict] | None = None) -> str:
    polys = cut_baked(meshes, "plan", elevation + cut_height)
    grid = grid or {"x": [], "y": []}
    if not polys and not (grid["x"] or grid["y"]):
        return to_svg([], title=title, subtitle="no geometry")

    pts = [np.vstack(polys)] if polys else []
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
    height = int(draw_h + 2 * pad + gutter + 60)
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

    # cut geometry
    for poly in polys:
        pp = " ".join(f"{T(p[0], p[1])[0]:.1f},{T(p[0], p[1])[1]:.1f}" for p in poly)
        out.append(f'<polyline points="{pp}" fill="none" stroke="#111" stroke-width="0.8"/>')

    # room tags (IfcSpace): name + net floor area at the space centroid
    for tag in (tags or []):
        if not (mn[0] <= tag["x"] <= mx[0] and mn[1] <= tag["y"] <= mx[1]):
            continue
        tx, tyy = T(tag["x"], tag["y"])
        out.append(f'<text x="{tx:.1f}" y="{tyy:.1f}" text-anchor="middle" font-family="sans-serif" '
                   f'font-size="12" font-weight="700" fill="#333">{tag["name"]}</text>')
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

    sub = f"cut @ {elevation + cut_height:.2f} m" + (f"  ·  grid {len(grid['x'])}×{len(grid['y'])}" if (grid["x"] or grid["y"]) else "")
    ty = height - 24
    out.append(f'<line x1="{pad}" y1="{ty-12}" x2="{width-pad}" y2="{ty-12}" stroke="#111" stroke-width="1"/>'
               f'<text x="{pad}" y="{ty+8}" font-family="sans-serif" font-size="16" font-weight="700">{title}</text>'
               f'<text x="{width-pad}" y="{ty+8}" text-anchor="end" font-family="sans-serif" '
               f'font-size="12" fill="#555">{sub}</text>')
    out.append("</svg>")
    return "".join(out)


def _dim_h(x0, x1, y, mm):
    return (f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="#0a6" stroke-width="0.8"/>'
            f'<line x1="{x0:.1f}" y1="{y-4:.1f}" x2="{x0:.1f}" y2="{y+4:.1f}" stroke="#0a6" stroke-width="0.8"/>'
            f'<line x1="{x1:.1f}" y1="{y-4:.1f}" x2="{x1:.1f}" y2="{y+4:.1f}" stroke="#0a6" stroke-width="0.8"/>'
            f'<text x="{(x0+x1)/2:.1f}" y="{y-4:.1f}" text-anchor="middle" font-family="sans-serif" '
            f'font-size="10" fill="#0a6">{mm}</text>')


def _dim_v(x, y0, y1, mm):
    return (f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y1:.1f}" stroke="#0a6" stroke-width="0.8"/>'
            f'<line x1="{x-4:.1f}" y1="{y0:.1f}" x2="{x+4:.1f}" y2="{y0:.1f}" stroke="#0a6" stroke-width="0.8"/>'
            f'<line x1="{x-4:.1f}" y1="{y1:.1f}" x2="{x+4:.1f}" y2="{y1:.1f}" stroke="#0a6" stroke-width="0.8"/>'
            f'<text x="{x-6:.1f}" y="{(y0+y1)/2:.1f}" text-anchor="middle" font-family="sans-serif" '
            f'font-size="10" fill="#0a6" transform="rotate(-90 {x-6:.1f} {(y0+y1)/2:.1f})">{mm}</text>')


def space_tags(model: ifcopenshell.file) -> list[dict]:
    """Room tags from IfcSpace: name + net floor area + plan centroid (for plan annotation)."""
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.element as _ue

    settings = _world_settings(_geom)   # world coords → tag centroids align with the world-placed linework
    tags = []
    for sp in model.by_type("IfcSpace"):
        name = getattr(sp, "LongName", None) or getattr(sp, "Name", None) or "Room"
        area = None
        for qset in _ue.get_psets(sp, qtos_only=True).values():
            area = area or qset.get("NetFloorArea") or qset.get("GrossFloorArea")
        try:
            shape = _geom.create_shape(settings, sp)
            v = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            cx, cy = float(v[:, 0].mean()), float(v[:, 1].mean())
            if area is None:  # footprint area fallback (convex hull of plan projection)
                from shapely.geometry import MultiPoint
                area = MultiPoint(v[:, :2]).convex_hull.area
        except Exception:
            continue
        tags.append({"name": name, "area": float(area) if area else None, "x": cx, "y": cy})
    return tags


def element_callouts(model: ifcopenshell.file, classes=("IfcDoor", "IfcWindow")) -> list[dict]:
    """Plan callouts for taggable elements: a label (Tag → Name → class) at the element's plan
    centroid. Rendered with a leader line pointing from the label to the element."""
    import ifcopenshell.geom as _geom

    settings = _world_settings(_geom)   # world coords → callout centroids align with the linework
    out: list[dict] = []
    for cls in classes:
        for el in model.by_type(cls):
            label = getattr(el, "Tag", None) or getattr(el, "Name", None) or cls.replace("Ifc", "")
            try:
                shape = _geom.create_shape(settings, el)
                v = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
                out.append({"label": str(label), "x": float(v[:, 0].mean()),
                            "y": float(v[:, 1].mean()), "kind": cls})
            except Exception:
                continue
    return out


def plan_svg(model: ifcopenshell.file, elevation: float, cut_height: float = 1.2,
             title: str = "PLAN", grid: bool = True, dims: bool = True,
             rooms: bool = True, callouts: bool | list[str] = False) -> str:
    meshes = bake(model)
    g = grid_from_meshes(meshes) if grid else {"x": [], "y": []}
    tags = space_tags(model) if rooms else []
    co = None
    if callouts:
        classes = callouts if isinstance(callouts, list) else ["IfcDoor", "IfcWindow"]
        co = element_callouts(model, tuple(classes))
    return plan_drawing_svg(meshes, elevation, cut_height, title, g, dims, tags=tags, callouts=co)


# --- elevations (orthographic outline projections) --------------------------
# direction -> (kept axes, flip horizontal?, depth axis, near sign)
_DIRS = {
    "north": ((0, 2), False, 1, +1), "south": ((0, 2), True, 1, -1),   # look along Y, draw X/Z
    "east": ((1, 2), True, 0, +1), "west": ((1, 2), False, 0, -1),     # look along X, draw Y/Z
}


def elevation_outlines(meshes, direction: str, with_depth: bool = False):
    """Element silhouettes (convex hull of projected vertices). With with_depth, also returns
    a painter's-algorithm sort key (far→near) per element for hidden-line removal."""
    from shapely.geometry import MultiPoint

    axes, flip, depth_axis, near = _DIRS.get(direction, _DIRS["north"])
    outs = []
    for _cls, mesh in meshes:
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
        except Exception:
            pass
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


def _axis_center(meshes: list[tuple[str, trimesh.Trimesh]], ax: int) -> float:
    """Midpoint of the model's extent along world axis `ax` (0=x, 1=y) from the baked meshes —
    so an auto-placed section cuts through the building, not the world origin."""
    lo = hi = None
    for _, m in meshes:
        b = getattr(m, "bounds", None)
        if b is None:
            continue
        lo = b[0][ax] if lo is None else min(lo, b[0][ax])
        hi = b[1][ax] if hi is None else max(hi, b[1][ax])
    return 0.0 if lo is None else (lo + hi) / 2.0


def section_svg(model: ifcopenshell.file, axis: str, offset: float | None = None,
                title: str = "SECTION") -> str:
    """Cut the model on a vertical plane. `offset` is the world coordinate (metres) of the cut on the
    perpendicular axis; when None the cut auto-centres on the model so it lands through the building
    regardless of where the model sits relative to the origin."""
    view = "section-x" if axis == "x" else "section-y"
    meshes = bake(model)
    if offset is None:
        offset = _axis_center(meshes, 0 if axis == "x" else 1)
    polys = cut_baked(meshes, view, offset)
    return to_svg(polys, title=title, subtitle=f"{axis.upper()} = {offset:.2f} m")


def plan_file(ifc_path: str, elevation: float, cut_height: float = 1.2, title: str = "PLAN") -> str:
    return plan_svg(open_model(ifc_path), elevation, cut_height, title)


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


def render_sheet_svg(layout: dict, meta: dict) -> str:
    pw, ph = layout["page"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw:.0f}" height="{ph:.0f}" '
           f'viewBox="0 0 {pw:.0f} {ph:.0f}">',
           f'<rect width="{pw:.0f}" height="{ph:.0f}" fill="#fff"/>',
           f'<rect x="6" y="6" width="{pw-12:.0f}" height="{ph-12:.0f}" fill="none" stroke="#111" stroke-width="2"/>']
    for v in layout["views"]:
        x, y, w, h = v["rect"]
        out.append(f'<text x="{x+14:.0f}" y="{y+16:.0f}" font-family="sans-serif" '
                   f'font-size="13" font-weight="700">{v["label"]}  <tspan fill="#666" '
                   f'font-weight="400">{v["sub"]}  ·  {v["scale_text"]}</tspan></text>')
        # elevation cells use opaque white fill (hidden-line removal); others stroke-only
        shape = "polygon" if v.get("filled") else "polyline"
        fill = "#fff" if v.get("filled") else "none"
        for poly in v["polys"]:
            pts = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in poly)
            out.append(f'<{shape} points="{pts}" fill="{fill}" stroke="#111" stroke-width="0.6"/>')
        # grid / dimension / level annotations
        for e in v.get("extras", []):
            if e[0] == "lvl":
                _, x1, x2, yy = e
                out.append(f'<line x1="{x1:.1f}" y1="{yy:.1f}" x2="{x2:.1f}" y2="{yy:.1f}" '
                           f'stroke="#0a6" stroke-width="0.5" stroke-dasharray="6 3"/>')
            elif e[0] == "line":
                _, x1, y1, x2, y2, dash = e
                da = ' stroke-dasharray="5 3"' if dash else ""
                out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                           f'stroke="#bbb" stroke-width="0.5"{da}/>')
            elif e[0] == "bub":
                _, bx, byy, r, lbl = e
                out.append(f'<circle cx="{bx:.1f}" cy="{byy:.1f}" r="{r}" fill="#fff" stroke="#111" '
                           f'stroke-width="0.6"/><text x="{bx:.1f}" y="{byy+2.5:.1f}" '
                           f'text-anchor="middle" font-family="sans-serif" font-size="7" '
                           f'font-weight="700">{lbl}</text>')
            elif e[0] == "dim":
                _, x1, y1, x2, y2, txt = e
                if abs(y1 - y2) < 0.5:  # horizontal
                    out.append(_dim_h(x1, x2, y1, txt))
                else:
                    out.append(_dim_v(x1, y1, y2, txt))
    # title block (bottom strip)
    m = layout["margin"]
    by = ph - m - layout["tb_h"] + 10
    out.append(f'<line x1="{m}" y1="{by}" x2="{pw-m:.0f}" y2="{by}" stroke="#111" stroke-width="1.5"/>')
    out.append(f'<text x="{m+8}" y="{by+34:.0f}" font-family="sans-serif" font-size="22" '
               f'font-weight="800">{meta.get("project","PROJECT")}</text>')
    fields = [("SHEET", meta.get("sheet", "A-101")), ("ISSUED FOR", meta.get("purpose", "") or "—"),
              ("REV", str(meta.get("revision", "") or "—")), ("DATE", meta.get("date", "")),
              ("DRAWN", meta.get("drawn_by", "")), ("SCALE", "AS NOTED")]
    fx = pw - m - 360
    for i, (k, val) in enumerate(fields):
        cx = fx + (i % 2) * 180
        cy = by + 20 + (i // 2) * 28
        out.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-family="sans-serif" font-size="10" '
                   f'fill="#888">{k}</text><text x="{cx:.0f}" y="{cy+14:.0f}" '
                   f'font-family="sans-serif" font-size="13" font-weight="600">{val}</text>')
    out.append("</svg>")
    return "".join(out)


def render_sheet_pdf(layout: dict, meta: dict) -> bytes:
    import io

    from reportlab.pdfgen import canvas

    pw, ph = layout["page"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))

    def fy(y):  # SVG (top-left) -> PDF (bottom-left)
        return ph - y

    c.setLineWidth(2); c.rect(6, 6, pw - 12, ph - 12)
    for v in layout["views"]:
        x, y, w, h = v["rect"]
        c.setFont("Helvetica-Bold", 11); c.drawString(x + 14, fy(y + 16), v["label"])
        c.setFont("Helvetica", 9); c.setFillGray(0.4)
        c.drawString(x + 14 + 9 * len(v["label"]), fy(y + 16), f"  {v['sub']}  ·  {v['scale_text']}")
        c.setFillGray(0)
        c.setLineWidth(0.6)
        filled = v.get("filled")
        for poly in v["polys"]:
            p = c.beginPath()
            p.moveTo(poly[0][0], fy(poly[0][1]))
            for pt in poly[1:]:
                p.lineTo(pt[0], fy(pt[1]))
            if filled:
                p.close()
                c.saveState(); c.setFillGray(1)
                c.drawPath(p, stroke=1, fill=1)  # opaque white fill = hidden-line removal
                c.restoreState()
            else:
                c.drawPath(p)
        # grid / dimension / level annotations
        for e in v.get("extras", []):
            if e[0] == "lvl":
                _, x1, x2, yy = e
                c.saveState(); c.setStrokeColorRGB(0, 0.6, 0.4); c.setLineWidth(0.5); c.setDash(6, 3)
                c.line(x1, fy(yy), x2, fy(yy)); c.restoreState()
            elif e[0] == "line":
                _, x1, y1, x2, y2, dash = e
                c.saveState(); c.setStrokeGray(0.73); c.setLineWidth(0.5)
                if dash:
                    c.setDash(5, 3)
                c.line(x1, fy(y1), x2, fy(y2)); c.restoreState()
            elif e[0] == "bub":
                _, bx, byy, r, lbl = e
                c.saveState(); c.setFillGray(1); c.setStrokeGray(0); c.setLineWidth(0.6)
                c.circle(bx, fy(byy), r, stroke=1, fill=1)
                c.setFillGray(0); c.setFont("Helvetica-Bold", 6)
                c.drawCentredString(bx, fy(byy) - 2, str(lbl)); c.restoreState()
            elif e[0] == "dim":
                _, x1, y1, x2, y2, txt = e
                c.saveState(); c.setStrokeColorRGB(0, 0.6, 0.4); c.setFillColorRGB(0, 0.6, 0.4)
                c.setLineWidth(0.6); c.setFont("Helvetica", 6)
                c.line(x1, fy(y1), x2, fy(y2))
                if abs(y1 - y2) < 0.5:
                    c.drawCentredString((x1 + x2) / 2, fy(y1) + 2, str(txt))
                else:
                    c.saveState(); c.translate(x1 - 3, fy((y1 + y2) / 2)); c.rotate(90)
                    c.drawCentredString(0, 0, str(txt)); c.restoreState()
                c.restoreState()
    m = layout["margin"]; by = ph - m - layout["tb_h"] + 10
    c.setLineWidth(1.5); c.line(m, fy(by), pw - m, fy(by))
    c.setFont("Helvetica-Bold", 22); c.drawString(m + 8, fy(by + 34), meta.get("project", "PROJECT"))
    fields = [("SHEET", meta.get("sheet", "A-101")), ("ISSUED FOR", meta.get("purpose", "") or "—"),
              ("REV", str(meta.get("revision", "") or "—")), ("DATE", meta.get("date", "")),
              ("DRAWN", meta.get("drawn_by", "")), ("SCALE", "AS NOTED")]
    fx = pw - m - 360
    for i, (k, val) in enumerate(fields):
        cx = fx + (i % 2) * 180; cy = by + 20 + (i // 2) * 28
        c.setFont("Helvetica", 9); c.setFillGray(0.55); c.drawString(cx, fy(cy), k)
        c.setFillGray(0); c.setFont("Helvetica-Bold", 12); c.drawString(cx, fy(cy + 14), str(val))
    c.showPage(); c.save()
    return buf.getvalue()


def sheet(model: ifcopenshell.file, specs: list[dict], meta: dict,
          page: str = "A3", cols: int = 2, fmt: str = "svg"):
    layout = compose(bake(model), specs, page=page, cols=cols, levels=storey_elevations(model))
    return render_sheet_pdf(layout, meta) if fmt == "pdf" else render_sheet_svg(layout, meta)


def sheet_file(ifc_path: str, specs: list[dict], meta: dict, page="A3", cols=2, fmt="svg"):
    return sheet(open_model(ifc_path), specs, meta, page, cols, fmt)


def default_sheet(model: ifcopenshell.file, meta: dict, page: str = "A3", fmt: str = "svg"):
    """One-call sheet: a plan per storey (below the roof) + a section through the model
    centre. Bakes geometry once. Returns SVG string or PDF bytes."""
    meshes = bake(model)
    # model X bounds for the section line
    xs = [m.bounds for _, m in meshes if m.bounds is not None]
    mid_x = float(np.mean([b[:, 0].mean() for b in xs])) if xs else 0.0

    storeys = storey_elevations(model)
    top = max((s["elevation"] for s in storeys), default=0.0)
    specs = [{"kind": "plan", "elevation": s["elevation"], "title": f"PLAN {s['name']}"}
             for s in storeys if s["elevation"] < top - 0.01]
    specs.append({"kind": "section", "axis": "x", "offset": mid_x, "title": "SECTION A-A"})
    specs.append({"kind": "elevation", "direction": "north", "title": "NORTH ELEVATION"})

    layout = compose(meshes, specs, page=page, cols=2, levels=storeys)
    return render_sheet_pdf(layout, meta) if fmt == "pdf" else render_sheet_svg(layout, meta)
