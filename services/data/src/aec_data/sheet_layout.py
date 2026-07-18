"""SHEET-VIEWPORTS (server slice) — true paper-space viewport composition.

`drawings.compose()` lays views in a uniform fit-to-cell grid. This is the mature endpoint of that
idea (the OCS layout model, server-side): a sheet is a set of **viewport rectangles**, each with its
own view (plan storey / section / elevation), an optional **fixed drawing scale** (1:N on paper — the
thing a printed set requires), an optional **class freeze** (a viewport showing only structure, only
MEP…), and geometric **clipping** to its rectangle — a fixed-scale view crops like a real viewport
instead of shrinking to fit. Renders through the same `render_sheet_svg/pdf` titleblock pipeline.

Viewport spec (all keys but `kind` optional):
    {"kind": "plan"|"section"|"elevation", "elevation"/"axis"+"offset"/"direction": …,
     "rect": [x, y, w, h] as FRACTIONS of the drawable area (page minus margins/titleblock),
     "scale": 100,                 # 1:100 on paper; omit/None → fit-to-rect (legacy behaviour)
     "classes": ["IfcWall", …],    # per-viewport layer/class freeze; omit → everything
     "center": [wx, wy],           # world point (view plane coords) at the viewport centre; omit → bbox centre
     "title": "LEVEL 2 PLAN"}

The interactive paper-space editor (drag viewports in the web app) builds on this; the composition
model itself is fully server-side and deterministic."""
from __future__ import annotations

import numpy as np

from .drawings import PAGES, _view_for_spec, bake, cut_baked, elevation_outlines, storey_elevations
from .drawings_render import render_sheet_pdf, render_sheet_svg
from .ifc_loader import open_model

# points per metre of world at 1:N — page space is PDF points (1 pt = 0.352778 mm; 1 m = 1000 mm).
_PT_PER_M_AT_1_1 = 1000.0 / 0.352778


def presets(name: str = "key") -> list[dict]:
    """Named viewport arrangements (fraction rects). `key`: big plan left, section + elevation stacked
    right. `quad`: 2×2. `plan-pair`: two plans side by side. Callers override any field per viewport."""
    if name == "quad":
        return [{"kind": "plan", "rect": [0.0, 0.0, 0.5, 0.5]},
                {"kind": "plan", "rect": [0.5, 0.0, 0.5, 0.5]},
                {"kind": "section", "axis": "x", "rect": [0.0, 0.5, 0.5, 0.5]},
                {"kind": "elevation", "direction": "south", "rect": [0.5, 0.5, 0.5, 0.5]}]
    if name == "plan-pair":
        return [{"kind": "plan", "rect": [0.0, 0.0, 0.5, 1.0]},
                {"kind": "plan", "rect": [0.5, 0.0, 0.5, 1.0]}]
    return [{"kind": "plan", "rect": [0.0, 0.0, 0.62, 1.0]},
            {"kind": "section", "axis": "x", "rect": [0.62, 0.0, 0.38, 0.5]},
            {"kind": "elevation", "direction": "north", "rect": [0.62, 0.5, 0.38, 0.5]}]


def _clip_segment(p0, p1, rect):
    """Liang–Barsky: clip segment p0→p1 to rect (x0,y0,x1,y1). Returns (a, b) points or None."""
    x0, y0, x1, y1 = rect
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p0[0] - x0), (dx, x1 - p0[0]), (-dy, p0[1] - y0), (dy, y1 - p0[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None                       # parallel and outside
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return ((p0[0] + t0 * dx, p0[1] + t0 * dy), (p0[0] + t1 * dx, p0[1] + t1 * dy))


def clip_polyline(poly: np.ndarray, rect: tuple[float, float, float, float]) -> list[np.ndarray]:
    """Clip a polyline to a rect; may split into multiple runs (re-entering geometry)."""
    runs: list[list] = []
    cur: list = []
    for i in range(len(poly) - 1):
        seg = _clip_segment(poly[i], poly[i + 1], rect)
        if seg is None:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
            continue
        a, b = seg
        if not cur:
            cur = [a, b]
        elif abs(cur[-1][0] - a[0]) < 1e-9 and abs(cur[-1][1] - a[1]) < 1e-9:
            cur.append(b)                          # continuous with the previous kept segment
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [a, b]
    if len(cur) >= 2:
        runs.append(cur)
    return [np.asarray(r) for r in runs]


def _filtered(meshes, classes):
    if not classes:
        return meshes
    want = {c.lower() for c in classes}
    return [(cls, m) for cls, m in meshes if cls.lower() in want]


def _view_polys(meshes, vp: dict) -> tuple[list[np.ndarray], str, str]:
    """Resolve one viewport's polylines, honoring the per-viewport class freeze."""
    kind = vp.get("kind", "plan")
    classes = vp.get("classes")
    if classes and kind in ("plan", "section"):
        if kind == "section":
            axis = vp.get("axis", "x")
            polys = cut_baked(meshes, "section-x" if axis == "x" else "section-y",
                              float(vp.get("offset", 0.0)), classes=list(classes))
            return polys, vp.get("title", f"SECTION {axis.upper()}"), f"{axis.upper()}={float(vp.get('offset', 0.0)):.1f} m"
        elev = float(vp.get("elevation", 0.0)) + float(vp.get("cut_height", 1.2))
        polys = cut_baked(meshes, "plan", elev, classes=list(classes))
        return polys, vp.get("title", "PLAN"), f"cut @ {elev:.2f} m"
    if classes and kind == "elevation":
        d = vp.get("direction", "north")
        items = elevation_outlines(_filtered(meshes, classes), d, with_depth=True)
        items.sort(key=lambda it: it[1])
        return [c for c, _ in items], vp.get("title", f"{d.upper()} ELEVATION"), f"{d} elev"
    return _view_for_spec(meshes, vp)


def compose_viewports(meshes, viewports: list[dict], page: str = "A1",
                      margin: float = 36.0, tb_h: float = 90.0,
                      levels: list[dict] | None = None) -> dict:
    """Compose paper-space viewports into the `render_sheet_svg/pdf` layout dict. Fixed `scale` places
    the view at true 1:N and CLIPS to the viewport rect (crop, not shrink); no scale → fit-to-rect."""
    pw, ph = PAGES.get(page, PAGES["A1"])
    ax, ay = margin, margin + tb_h                 # drawable area origin (y-down, titleblock on top band)
    aw, ah = pw - 2 * margin, ph - 2 * margin - tb_h
    pad, label_h = 10.0, 18.0
    views = []
    for vp in viewports:
        fx, fy, fw, fh = vp.get("rect") or [0.0, 0.0, 1.0, 1.0]
        cx, cy = ax + fx * aw, ay + fy * ah
        cw, ch = fw * aw, fh * ah
        iw, ih = cw - 2 * pad, ch - 2 * pad - label_h
        ox, oy = cx + pad, cy + pad + label_h      # inner viewport origin
        polys, label, sub = _view_polys(meshes, vp)
        placed: list[np.ndarray] = []
        scale_text = "no geometry"
        if polys:
            allp = np.vstack(polys)
            mn, mx = allp.min(axis=0), allp.max(axis=0)
            span = np.maximum(mx - mn, 1e-6)
            denom = vp.get("scale")
            if denom:                              # true paper scale — clip, never shrink
                s = _PT_PER_M_AT_1_1 / float(denom)
                wcx, wcy = vp.get("center") or ((mn[0] + mx[0]) / 2.0, (mn[1] + mx[1]) / 2.0)
                # world→sheet: centre (wcx,wcy) lands at the viewport centre; y flips (SVG y-down)
                vcx, vcy = ox + iw / 2.0, oy + ih / 2.0
                clip_rect = (ox, oy, ox + iw, oy + ih)
                for poly in polys:
                    pts = np.empty_like(poly, dtype=float)
                    pts[:, 0] = vcx + (poly[:, 0] - wcx) * s
                    pts[:, 1] = vcy - (poly[:, 1] - wcy) * s
                    placed.extend(clip_polyline(pts, clip_rect))
                scale_text = f"1:{int(denom)}"
            else:                                  # fit (legacy compose behaviour)
                s = min(iw / span[0], ih / span[1])
                dh = span[1] * s
                fox = ox + (iw - span[0] * s) / 2.0
                for poly in polys:
                    pts = np.empty_like(poly, dtype=float)
                    pts[:, 0] = fox + (poly[:, 0] - mn[0]) * s
                    pts[:, 1] = oy + dh - (poly[:, 1] - mn[1]) * s
                    placed.append(pts)
                scale_text = f"1:{round(1.0 / (s * 0.000352778))}"
        views.append({"label": vp.get("title") or label, "sub": sub, "scale_text": scale_text,
                      "kind": vp.get("kind", "plan"), "filled": vp.get("kind") == "elevation",
                      "rect": (cx, cy, cw, ch), "polys": placed, "extras": []})
    return {"page": (pw, ph), "tb_h": tb_h, "margin": margin, "views": views}


def layout_sheet(model, viewports: list[dict], meta: dict, page: str = "A1", fmt: str = "svg"):
    """One-call paper-space sheet from an open model. Returns SVG text or PDF bytes.
    `meta` accepts either `sheet` or `number` for the sheet number (the renderer's key is `sheet`)."""
    meta = {**(meta or {})}
    meta.setdefault("sheet", meta.get("number") or "A-101")
    layout = compose_viewports(bake(model), viewports, page=page, levels=storey_elevations(model))
    return render_sheet_pdf(layout, meta) if fmt == "pdf" else render_sheet_svg(layout, meta)


def layout_sheet_file(ifc_path: str, viewports: list[dict], meta: dict,
                      page: str = "A1", fmt: str = "svg"):
    return layout_sheet(open_model(ifc_path), viewports, meta, page, fmt)


__all__ = ["presets", "compose_viewports", "layout_sheet", "layout_sheet_file", "clip_polyline"]
