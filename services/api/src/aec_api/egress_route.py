"""D2 — routed egress: travel distance measured along the path someone would actually walk.

The platform already computes occupant load and egress capacity (`codecheck_egress`), and
`geometric_rules.check_escape_distance` checks distance to an exit — **straight-line**, and it says so.
That is the problem this module exists for. IBC 1017 limits *travel distance*, defined as the distance
along the path of egress travel; a straight line ignores every wall in the way, so it is always
shorter than the real route and often dramatically so. A straight-line check therefore fails in the
unsafe direction: it passes plans that do not comply, and no amount of care reading its output
recovers that, because the number itself is the wrong measurement.

The approach is deliberately boring and deterministic: rasterise the floor plate at the cut height,
mark cells blocked by anything the cut passes through, run a multi-source Dijkstra outward from every
exit, and read each space's distance off that field. No navmesh, no external solver, no network — and
the resulting distance field doubles as the route polyline to draw on the plan.

Grid resolution is a stated approximation, not a hidden one: a routed distance is reported with the
cell size it was measured at, because a 0.25 m grid cannot resolve a 0.2 m gap and pretending
otherwise would be the same mistake in a new place.
"""
from __future__ import annotations

import heapq
import math
from typing import Any

# Anything the plan cut passes through stops a person: walls, columns, and the shafts they enclose.
# Doors and openings are NOT obstructions — they are the gaps the route is supposed to find.
_BLOCKING = ("ifcwall", "ifcwallstandardcase", "ifccolumn", "ifcshadingdevice",
             "ifccurtainwall", "ifcmember", "ifcplate")
_DIAG = math.sqrt(2.0)
MAX_CELLS = 4_000_000          # ~1 km² at 0.5 m; beyond this the caller must coarsen deliberately


def _polys_at(model, elevation: float, cut_height: float):
    """Cut footprints of the blocking elements at the plan cut height, as (class, Nx2 array)."""
    from aec_data import drawings  # type: ignore
    meshes = drawings.bake(model)
    classed = drawings.cut_baked_classed(meshes, "plan", elevation + cut_height)
    return [(c, p) for c, p in classed if (c or "").lower() in _BLOCKING]


def build_grid(model, elevation: float = 0.0, cut_height: float = 1.2, cell: float = 0.3):
    """Rasterise the walkable plane. Returns (blocked, origin, cell, shape) where `blocked` is a
    boolean array — True where a person cannot stand."""
    import numpy as np

    from aec_data import drawings  # type: ignore
    bounds = drawings.world_bounds(model)
    if bounds is None:
        return None
    (minx, miny, _), (maxx, maxy, _) = bounds
    nx = int(math.ceil((maxx - minx) / cell)) + 2
    ny = int(math.ceil((maxy - miny) / cell)) + 2
    if nx * ny > MAX_CELLS:
        raise ValueError(f"grid would be {nx * ny} cells at {cell} m; pass a larger `cell`")
    blocked = np.zeros((nx, ny), dtype=bool)
    ox, oy = minx - cell, miny - cell

    for _cls, poly in _polys_at(model, elevation, cut_height):
        # a cut polyline is a closed loop; blocking its bounding cells is coarse but conservative in
        # the right direction — it never opens a route through a wall
        p = np.asarray(poly, dtype=float)
        if len(p) < 2:
            continue
        i0 = max(0, int((p[:, 0].min() - ox) / cell))
        i1 = min(nx - 1, int((p[:, 0].max() - ox) / cell))
        j0 = max(0, int((p[:, 1].min() - oy) / cell))
        j1 = min(ny - 1, int((p[:, 1].max() - oy) / cell))
        blocked[i0:i1 + 1, j0:j1 + 1] = True
    return blocked, (ox, oy), cell, (nx, ny)


def _cell_of(pt, origin, cell, shape):
    i = int((pt[0] - origin[0]) / cell)
    j = int((pt[1] - origin[1]) / cell)
    if 0 <= i < shape[0] and 0 <= j < shape[1]:
        return i, j
    return None


def distance_field(blocked, sources: list[tuple[int, int]], cell: float):
    """Multi-source Dijkstra over the free cells: metres of walking to the nearest source.

    Eight-connected with a √2 diagonal cost, so a route across open floor is not overstated by ~40%
    the way a four-connected grid would. Unreachable cells stay at infinity — which is the answer that
    matters most, because a space with no route to any exit is the worst finding a plan can carry.
    """
    import numpy as np

    nx, ny = blocked.shape
    dist = np.full((nx, ny), np.inf, dtype=float)
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    heap: list[tuple[float, int, int]] = []
    for i, j in sources:
        if 0 <= i < nx and 0 <= j < ny and not blocked[i, j]:
            dist[i, j] = 0.0
            heap.append((0.0, i, j))
    heapq.heapify(heap)
    steps = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, _DIAG), (-1, 1, _DIAG), (1, -1, _DIAG), (1, 1, _DIAG)]
    while heap:
        d, i, j = heapq.heappop(heap)
        if d > dist[i, j]:
            continue
        for di, dj, w in steps:
            ni, nj = i + di, j + dj
            if not (0 <= ni < nx and 0 <= nj < ny) or blocked[ni, nj]:
                continue
            nd = d + w * cell
            if nd < dist[ni, nj]:
                dist[ni, nj] = nd
                prev[(ni, nj)] = (i, j)
                heapq.heappush(heap, (nd, ni, nj))
    return dist, prev


def _path_from(cellij, prev, origin, cell, limit: int = 4000):
    """Walk the predecessor chain back to the exit, in world metres."""
    pts, seen, cur = [], set(), cellij
    while cur is not None and cur not in seen and len(pts) < limit:
        seen.add(cur)
        pts.append((round(origin[0] + (cur[0] + 0.5) * cell, 3),
                    round(origin[1] + (cur[1] + 0.5) * cell, 3)))
        cur = prev.get(cur)
    return pts


def _centroids(model, classes: tuple[str, ...]) -> list[dict[str, Any]]:
    """World-space XY centroid + Z range per element of the given classes."""
    import contextlib

    import ifcopenshell.geom as geom
    import numpy as np

    settings = geom.settings()
    with contextlib.suppress(Exception):
        settings.set(settings.USE_WORLD_COORDS, True)
    want = {c.lower() for c in classes}
    out: list[dict[str, Any]] = []
    from aec_data.geomconf import bounded_iterator  # type: ignore
    it = bounded_iterator(geom, settings, model)
    if not it.initialize():
        return out
    while True:
        shape = it.get()
        if (shape.type or "").lower() in want:
            v = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            if len(v):
                out.append({"guid": shape.guid, "ifc_class": shape.type,
                            "name": getattr(shape, "name", "") or None,
                            "xy": (float(v[:, 0].mean()), float(v[:, 1].mean())),
                            "z": (float(v[:, 2].min()), float(v[:, 2].max()))})
        if not it.next():
            break
    return out


def _is_external(model, guid: str) -> bool:
    import ifcopenshell.util.element as ue
    try:
        el = model.by_guid(guid)
    except Exception:                            # noqa: BLE001 — a stale guid is simply not external
        return False
    ps = ue.get_pset(el, "Pset_DoorCommon") or {}
    v = ps.get("IsExternal")
    return v is True or str(v).lower() == "true"


def _nearest_free(blocked, ij, max_ring: int = 12):
    """The closest standable cell to `ij`. A space centroid can land inside a wall's blocked footprint
    (thin space, coarse grid); searching outward finds the floor instead of reporting no route."""
    nx, ny = blocked.shape
    i0, j0 = ij
    if 0 <= i0 < nx and 0 <= j0 < ny and not blocked[i0, j0]:
        return (i0, j0)
    for r in range(1, max_ring + 1):
        for di in range(-r, r + 1):
            for dj in (-r, r) if abs(di) != r else range(-r, r + 1):
                i, j = i0 + di, j0 + dj
                if 0 <= i < nx and 0 <= j < ny and not blocked[i, j]:
                    return (i, j)
    return None


def analyze(model, elevation: float = 0.0, max_travel_m: float = 61.0,
            cut_height: float = 1.2, cell: float = 0.3,
            with_paths: bool = True) -> dict[str, Any]:
    """Routed travel distance from every space on a level to the nearest exit.

    `max_travel_m` defaults to 61 m (200 ft) — the IBC 1017.2 sprinklered Business limit. It is a
    parameter rather than a constant because the limit is occupancy- and sprinkler-dependent, and a
    hard-coded one would be wrong for most buildings that used it.

    Every result carries **both** the routed distance and the straight-line distance the old check
    used, plus their ratio. That comparison is the point: it shows, per space, how much a straight
    line was understating the walk.
    """

    built = build_grid(model, elevation, cut_height, cell)
    if built is None:
        return {"routed": False, "spaces": [], "note": "model has no geometry to route over"}
    blocked, origin, cell, shape = built

    doors = [d for d in _centroids(model, ("IfcDoor",))
             if d["z"][0] <= elevation + 2.5 and d["z"][1] >= elevation - 0.5]
    exits = [d for d in doors if _is_external(model, d["guid"])]
    if not exits:
        return {"routed": False, "spaces": [], "exits": 0,
                "note": "no exterior doors found — mark egress doors IsExternal so a route has "
                        "somewhere to go. Nothing is reported rather than routing to an arbitrary "
                        "door, which would produce confident and meaningless distances."}

    src = [c for c in (_nearest_free(blocked, _cell_of(d["xy"], origin, cell, shape) or (-1, -1))
                       for d in exits) if c is not None]
    dist, prev = distance_field(blocked, src, cell)

    spaces = [s for s in _centroids(model, ("IfcSpace",))
              if s["z"][0] <= elevation + 2.5 and s["z"][1] >= elevation - 0.5]
    rows: list[dict[str, Any]] = []
    for sp in spaces:
        ij = _cell_of(sp["xy"], origin, cell, shape)
        free = _nearest_free(blocked, ij) if ij else None
        straight = min(math.hypot(sp["xy"][0] - e["xy"][0], sp["xy"][1] - e["xy"][1]) for e in exits)
        row: dict[str, Any] = {"guid": sp["guid"], "name": sp["name"],
                               "straight_line_m": round(straight, 2)}
        d = float(dist[free]) if free else math.inf
        if not math.isfinite(d):
            # no route at all — the most serious finding a plan can carry, so it is never folded in
            # with the merely-too-long ones
            row.update(travel_m=None, compliant=False, unreachable=True,
                       detail="no route to any exit on this level")
        else:
            row.update(travel_m=round(d, 2), unreachable=False,
                       compliant=bool(d <= max_travel_m),
                       detour_ratio=round(d / straight, 2) if straight > 0.01 else None)
            if with_paths:
                row["path"] = _path_from(free, prev, origin, cell)
        rows.append(row)

    reachable = [r for r in rows if not r["unreachable"]]
    over = [r for r in reachable if not r["compliant"]]
    ratios = [r["detour_ratio"] for r in reachable if r.get("detour_ratio")]
    return {
        "routed": True, "elevation": elevation, "cell_m": cell, "max_travel_m": max_travel_m,
        "_exits_xy": [e["xy"] for e in exits],
        "exits": len(exits), "spaces": len(rows),
        "compliant": len(reachable) - len(over), "over_limit": len(over),
        "unreachable": sum(1 for r in rows if r["unreachable"]),
        "worst_travel_m": max((r["travel_m"] for r in reachable), default=None),
        "max_detour_ratio": max(ratios, default=None),
        "results": rows,
        "note": f"Travel distance measured ALONG the route on a {cell} m grid, which is what IBC 1017 "
                f"limits — a straight line ignores every wall between a space and its exit and so "
                f"reports a shorter distance than anyone can walk. `detour_ratio` is routed ÷ "
                f"straight-line, i.e. how much the old measurement understated each space. Grid "
                f"resolution is an approximation and is reported: a {cell} m grid cannot resolve a "
                f"gap narrower than one cell.",
    }


# ── the life-safety plan ─────────────────────────────────────────────────────────────────────────
_OVER = "#c62828"      # over the travel limit
_OK = "#2e7d32"        # compliant
_NONE = "#6a1b9a"      # no route at all


def plan_svg(model, elevation: float = 0.0, max_travel_m: float = 61.0,
             cut_height: float = 1.2, cell: float = 0.3, width: int = 1300) -> str:
    """The routed egress plan: walls, exits, and each space's actual path to its nearest exit.

    Routes are coloured by outcome rather than uniformly, because the reason a reviewer opens this
    drawing is to find the ones that fail. A compliant route in green next to an over-limit route in
    red makes the failing space findable at a glance; drawing them all the same colour would hide the
    finding inside the evidence for it.
    """
    from xml.sax.saxutils import escape as esc

    import numpy as np
    res = analyze(model, elevation, max_travel_m, cut_height, cell, with_paths=True)
    if not res.get("routed"):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="140">'
                f'<rect width="{width}" height="140" fill="#fff"/>'
                f'<text x="20" y="60" font-family="sans-serif" font-size="14">'
                f'{esc(str(res.get("note") or "no egress routes"))}</text></svg>')

    walls = [p for _c, p in _polys_at(model, elevation, cut_height)]
    pts = [np.asarray(p, dtype=float) for p in walls if len(p) >= 2]
    routes = [r for r in res["results"] if r.get("path")]
    allp = np.vstack(pts + [np.asarray(r["path"], dtype=float) for r in routes]) if (pts or routes) \
        else np.zeros((1, 2))
    mn, mx = allp.min(axis=0), allp.max(axis=0)
    span = np.maximum(mx - mn, 1e-6)
    pad, top = 40, 30
    scale = (width - 2 * pad) / span[0]
    draw_h = span[1] * scale
    height = int(draw_h + top + pad + 90)

    def T(p):
        return pad + (p[0] - mn[0]) * scale, top + draw_h - (p[1] - mn[1]) * scale

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" fill="#fff"/>']
    for p in pts:
        d = " ".join(f"{T(q)[0]:.1f},{T(q)[1]:.1f}" for q in p)
        out.append(f'<polyline points="{d}" fill="none" stroke="#111" stroke-width="1.2"/>')
    for r in routes:
        colour = _NONE if r["unreachable"] else (_OK if r["compliant"] else _OVER)
        d = " ".join(f"{T(q)[0]:.1f},{T(q)[1]:.1f}" for q in r["path"])
        out.append(f'<polyline points="{d}" fill="none" stroke="{colour}" stroke-width="2" '
                   f'stroke-linejoin="round" opacity="0.85"/>')
        sx, sy = T(r["path"][0])
        label = "no route" if r["unreachable"] else f'{r["travel_m"]:.0f} m'
        out.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{colour}"/>'
                   f'<text x="{sx + 6:.1f}" y="{sy - 4:.1f}" font-family="sans-serif" '
                   f'font-size="10" fill="{colour}">{esc(str(r.get("name") or ""))} {label}</text>')
    for ex in res["_exits_xy"]:
        ex_x, ex_y = T(ex)
        out.append(f'<rect x="{ex_x - 5:.1f}" y="{ex_y - 5:.1f}" width="10" height="10" '
                   f'fill="#fff" stroke="#111" stroke-width="1.5"/>'
                   f'<text x="{ex_x:.1f}" y="{ex_y + 18:.1f}" text-anchor="middle" '
                   f'font-family="sans-serif" font-size="9" font-weight="700">EXIT</text>')

    ty = height - 46
    summary = (f'{res["compliant"]} within {max_travel_m:.0f} m  ·  {res["over_limit"]} over  ·  '
               f'{res["unreachable"]} with no route  ·  measured along the route on a {cell} m grid')
    out.append(f'<line x1="{pad}" y1="{ty}" x2="{width - pad}" y2="{ty}" stroke="#111"/>'
               f'<text x="{pad}" y="{ty + 20}" font-family="sans-serif" font-size="15" '
               f'font-weight="700">EGRESS / LIFE-SAFETY PLAN</text>'
               f'<text x="{pad}" y="{ty + 36}" font-family="sans-serif" font-size="11" '
               f'fill="#555">{esc(summary)}</text>')
    out.append("</svg>")
    return "".join(out)
