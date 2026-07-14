"""W11 · Track C — construction-drawing generation (C1: plan SVG).

Our production geometry path is web-ifc → Fragments; the ifcopenshell OpenCASCADE engine produces no mesh
in this build, so the HLR section-cut approach isn't available. Instead we take the research-recommended
*optimization*: derive 2D linework **directly from the authored extruded-profile geometry**. Every element
our recipes create is an `IfcExtrudedAreaSolid` (rectangle or arbitrary-closed profile) extruded vertically,
so its plan footprint is exactly the profile polygon transformed by (element placement × solid position) —
computable deterministically, no geometry kernel needed. This covers walls/slabs/columns/roofs/footings/
spaces (the bulk of a plan).

`plan_svg` emits a clean, class-styled SVG plan (one polygon per element, CSS classes per IFC class so a
stylesheet controls poché/linweight) at a given scale — the first slice of the construction-document set.
Later slices add dimensions, tags/keynotes (from the Track-D classification codes), sheets and PDF/DXF.
"""
from __future__ import annotations

import math
from typing import Any

import ifcopenshell

# per-IFC-class fill/stroke so the plan reads like a drawing (poché). CSS classes, not inline styles.
_STYLE = """
.sheet{fill:#fff}
.el{stroke:#111;stroke-width:0.4;fill:#e8e8e8}
.IfcWall{fill:#4a4a4a}
.IfcColumn{fill:#2a2a2a}
.IfcSlab{fill:#f2f2f2}
.IfcSpace{fill:#eef4ff;stroke:#9bb7e0;stroke-dasharray:2 2}
.IfcRoof{fill:#f6efe6}
.grid{stroke:#b00;stroke-width:0.2;stroke-dasharray:4 2}
.label{font:2px sans-serif;fill:#333}
.dim line{stroke:#06c;stroke-width:0.2}
.dimt{font:2px sans-serif;fill:#06c;text-anchor:middle}
.kn{fill:#fff;stroke:#b00;stroke-width:0.3}
.knt{font:2.4px sans-serif;fill:#b00;text-anchor:middle;dominant-baseline:middle}
.lgd{font:2.6px sans-serif;fill:#222}
.lgd-h{font:bold 3px sans-serif;fill:#000}
""".strip()


def _placement_matrix(el):
    import ifcopenshell.util.placement as up
    import numpy as np

    if el.ObjectPlacement is None:
        return np.eye(4)
    return np.array(up.get_local_placement(el.ObjectPlacement), dtype=float)


def _axis2placement3d(pl):
    """A 4×4 from an IfcAxis2Placement3D (or 2D) — location + optional axis/refdirection."""
    import numpy as np

    m = np.eye(4)
    if pl is None:
        return m
    loc = getattr(pl, "Location", None)
    if loc is not None:
        c = list(loc.Coordinates) + [0.0] * (3 - len(loc.Coordinates))
        m[0:3, 3] = c[:3]
    axis = getattr(pl, "Axis", None)              # Z
    ref = getattr(pl, "RefDirection", None)       # X
    if axis is not None and ref is not None:
        z = np.array(list(axis.DirectionRatios) + [0.0] * (3 - len(axis.DirectionRatios)))[:3]
        x = np.array(list(ref.DirectionRatios) + [0.0] * (3 - len(ref.DirectionRatios)))[:3]
        z = z / (np.linalg.norm(z) or 1.0)
        x = x - z * float(np.dot(x, z))
        x = x / (np.linalg.norm(x) or 1.0)
        y = np.cross(z, x)
        m[0:3, 0], m[0:3, 1], m[0:3, 2] = x, y, z
    elif ref is not None and hasattr(ref, "DirectionRatios") and len(ref.DirectionRatios) == 2:
        d = ref.DirectionRatios
        ang = math.atan2(d[1], d[0])
        c, s = math.cos(ang), math.sin(ang)
        m[0:2, 0], m[0:2, 1] = [c, s], [-s, c]
    return m


def _profile_points(profile):
    """2D points (profile coords) for a rectangle or arbitrary-closed profile, or None."""
    import numpy as np

    if profile is None:
        return None
    if profile.is_a("IfcRectangleProfileDef"):
        x, y = float(profile.XDim) / 2.0, float(profile.YDim) / 2.0
        pts = np.array([[-x, -y], [x, -y], [x, y], [-x, y]])
        pos = getattr(profile, "Position", None)
        return _apply2d(pos, pts)
    if profile.is_a("IfcArbitraryClosedProfileDef"):
        curve = profile.OuterCurve
        if curve is not None and curve.is_a("IfcPolyline"):
            pts = np.array([[float(p.Coordinates[0]), float(p.Coordinates[1])] for p in curve.Points])
            return pts
    return None


def _apply2d(pos, pts):
    import numpy as np

    if pos is None:
        return pts
    m = _axis2placement3d(pos)                    # handles 2D placement too
    out = []
    for px, py in pts:
        v = m @ np.array([px, py, 0.0, 1.0])
        out.append([v[0], v[1]])
    return np.array(out)


def _footprint(el):
    """World-XY footprint polygon [(x,y)…] (file units) for an extruded-profile element, or None."""
    import numpy as np

    rep = getattr(el, "Representation", None)
    if rep is None:
        return None
    solid = None
    for r in rep.Representations:
        for it in (r.Items or []):
            if it.is_a("IfcExtrudedAreaSolid"):
                solid = it
                break
        if solid:
            break
    if solid is None:
        return None
    pts2d = _profile_points(solid.SweptArea)
    if pts2d is None:
        return None
    world = _placement_matrix(el) @ _axis2placement3d(getattr(solid, "Position", None))
    out = []
    for px, py in pts2d:
        v = world @ np.array([px, py, 0.0, 1.0])
        out.append((float(v[0]), float(v[1])))
    return out


def _element_codes(el):
    """(system, code, title) tuples from an element's IfcRelAssociatesClassification — the Track-D
    keynote/spec codes that drive keynotes on the drawing."""
    out = []
    for rel in (getattr(el, "HasAssociations", None) or []):
        if not rel.is_a("IfcRelAssociatesClassification"):
            continue
        ref = rel.RelatingClassification
        src = getattr(ref, "ReferencedSource", None)
        while src is not None and src.is_a("IfcClassificationReference"):
            src = getattr(src, "ReferencedSource", None)
        out.append((getattr(src, "Name", None) if src is not None else None,
                    getattr(ref, "Identification", None), getattr(ref, "Name", None)))
    return out


def _centroid(fp):
    return (sum(p[0] for p in fp) / len(fp), sum(p[1] for p in fp) / len(fp))


# keynote systems, in priority order (a reference keynote points at the spec section → MasterFormat wins)
_KEYNOTE_SYS = ("MasterFormat", "UniFormat", "OmniClass", "Uniclass")

# elements worth drawing on a plan, coarsest→finest (drawing order)
_PLAN_CLASSES = ["IfcSlab", "IfcRoof", "IfcSpace", "IfcWall", "IfcColumn", "IfcFooting"]


def plan_svg(model: ifcopenshell.file, storey: str | None = None, scale: int = 100,
             margin_mm: float = 18.0, dimensions: bool = True, keynotes: bool = True) -> dict:
    """Generate a schematic **plan SVG** from element footprints. `storey` limits to one level (by name);
    `scale` is the drawing scale (1:`scale`). With `dimensions`, overall width/height dimension strings are
    drawn; with `keynotes`, elements carrying a Track-D classification code get numbered keynote bubbles + a
    legend. Returns {svg, elements, keynotes, bounds, scale}. Paper coords are millimetres at the scale."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu

    unit_scale = uu.calculate_unit_scale(model)               # metres per file unit
    paper = (1000.0 / float(scale)) * unit_scale              # file-unit → paper-mm

    shapes: list[tuple[Any, str, list]] = []
    for cls in _PLAN_CLASSES:
        for el in model.by_type(cls):
            if el.is_a("IfcElementType"):
                continue
            if storey:
                st = ue.get_container(el) or ue.get_aggregate(el)
                if st is None or (getattr(st, "Name", None) or "") != storey:
                    continue
            fp = _footprint(el)
            if fp and len(fp) >= 3:
                shapes.append((el, el.is_a(), fp))

    if not shapes:
        return {"svg": _empty_svg(), "elements": 0, "keynotes": 0, "bounds": None, "scale": scale}

    xs = [p[0] for _, _, fp in shapes for p in fp]
    ys = [p[1] for _, _, fp in shapes for p in fp]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    legend_mm = 62.0 if keynotes else 0.0
    w = (maxx - minx) * paper + 2 * margin_mm + legend_mm
    h = (maxy - miny) * paper + 2 * margin_mm

    def tx(x):        # world→paper, flip Y (SVG y grows down; plan north is up)
        return round((x - minx) * paper + margin_mm, 2)

    def ty(y):
        return round((maxy - y) * paper + margin_mm, 2)

    polys = [f'<polygon class="el {cls}" points="{" ".join(f"{tx(x)},{ty(y)}" for x, y in fp)}"/>'
             for _, cls, fp in shapes]

    # ── keynotes: unique classification codes across the drawn elements → numbered legend + bubbles ──
    bubbles: list[str] = []
    legend_rows: list[tuple[int, str, str]] = []
    if keynotes:
        order: dict[tuple[str, str], int] = {}
        for el, _cls, fp in shapes:
            codes = _element_codes(el)
            pick = next((c for sys in _KEYNOTE_SYS for c in codes if c[0] == sys), None)
            if not pick or not pick[1]:
                continue
            key = (pick[0], pick[1])
            if key not in order:
                order[key] = len(order) + 1
                legend_rows.append((order[key], f"{pick[0]} {pick[1]}", pick[2] or ""))
            num = order[key]
            cx, cy = _centroid(fp)
            bx, by = tx(cx), ty(cy)
            bubbles.append(f'<circle class="kn" cx="{bx}" cy="{by}" r="2.4"/>'
                           f'<text class="knt" x="{bx}" y="{round(by + 0.8, 2)}">{num}</text>')

    # ── dimensions: overall width (below) + overall height (left) ──
    dims: list[str] = []
    if dimensions:
        y0 = round(ty(miny) + 8, 2)                            # below the plan
        dims.append(_hdim(tx(minx), tx(maxx), y0, (maxx - minx) * unit_scale))
        x0 = round(tx(minx) - 8, 2)                            # left of the plan
        dims.append(_vdim(x0, ty(maxy), ty(miny), (maxy - miny) * unit_scale))

    legend_svg = ""
    if keynotes and legend_rows:
        lx = round(w - legend_mm + 4, 2)
        rows = [f'<text class="lgd-h" x="{lx}" y="{round(margin_mm, 2)}">KEYNOTES</text>']
        for i, (num, code, title) in enumerate(legend_rows[:24]):
            ry = round(margin_mm + 6 + i * 5, 2)
            rows.append(f'<circle class="kn" cx="{lx + 2}" cy="{round(ry - 1.2, 2)}" r="2.2"/>'
                        f'<text class="knt" x="{lx + 2}" y="{round(ry - 0.4, 2)}">{num}</text>'
                        f'<text class="lgd" x="{lx + 7}" y="{ry}">{_esc(code)} - {_esc(title)[:30]}</text>')
        legend_svg = "".join(rows)

    inner = (
        f"<style>{_STYLE}</style>"
        f'<rect class="sheet" x="0" y="0" width="{round(w, 2)}" height="{round(h, 2)}"/>'
        + "".join(polys) + "".join(dims) + "".join(bubbles) + legend_svg
        + f'<text class="label" x="{margin_mm}" y="{round(h - 4, 2)}">PLAN 1:{scale}'
        + (f" - {_esc(storey)}" if storey else "") + "</text>"
    )
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w, 1)}mm" height="{round(h, 1)}mm" '
           f'viewBox="0 0 {round(w, 2)} {round(h, 2)}">{inner}</svg>')
    return {"svg": svg, "inner": inner, "paper": [round(w, 2), round(h, 2)],
            "elements": len(shapes), "keynotes": len(legend_rows),
            "scale": scale, "bounds": {"min": [minx, miny], "max": [maxx, maxy]}}


def _fmt_m(v: float) -> str:
    return f"{v:.2f} m"


def _hdim(x1: float, x2: float, y: float, dist_m: float) -> str:
    """A horizontal dimension string with witness ticks and centred text (distance in metres)."""
    xm = round((x1 + x2) / 2, 2)
    return (f'<g class="dim"><line x1="{x1}" y1="{round(y - 3, 2)}" x2="{x1}" y2="{round(y + 1, 2)}"/>'
            f'<line x1="{x2}" y1="{round(y - 3, 2)}" x2="{x2}" y2="{round(y + 1, 2)}"/>'
            f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>'
            f'<text class="dimt" x="{xm}" y="{round(y - 1, 2)}">{_fmt_m(dist_m)}</text></g>')


def _vdim(x: float, y1: float, y2: float, dist_m: float) -> str:
    """A vertical dimension string (rotated text)."""
    ym = round((y1 + y2) / 2, 2)
    return (f'<g class="dim"><line x1="{round(x - 1, 2)}" y1="{y1}" x2="{round(x + 3, 2)}" y2="{y1}"/>'
            f'<line x1="{round(x - 1, 2)}" y1="{y2}" x2="{round(x + 3, 2)}" y2="{y2}"/>'
            f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}"/>'
            f'<text class="dimt" x="{round(x - 1, 2)}" y="{ym}" '
            f'transform="rotate(-90 {round(x - 1, 2)} {ym})">{_fmt_m(dist_m)}</text></g>')


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_SHEET_STYLE = (
    ".border{fill:none;stroke:#000;stroke-width:1}"
    ".tbline{stroke:#000;stroke-width:0.4}"
    ".tb-t{font:3.4px sans-serif;fill:#000}"
    ".tb-l{font:2.4px sans-serif;fill:#555}"
    ".tb-b{font:bold 5px sans-serif;fill:#000}"
    ".tb-logo{font:bold 6px sans-serif;fill:#000;letter-spacing:1px}"
    ".narrow{stroke:#000;stroke-width:0.5;fill:#000}"
)

# ARCH D landscape (in mm): 36×24 in
_SHEET_W, _SHEET_H = 914.0, 610.0
_TB_W = 150.0                      # titleblock strip width (right edge)


def sheet_svg(model: ifcopenshell.file, storey: str | None = None, scale: int = 100,
              project: str = "Project", number: str = "A-101", title: str = "FLOOR PLAN",
              date: str = "", drawn_by: str = "") -> dict:
    """W11 C3: compose an issuable **sheet** — an ARCH-D border with a titleblock (project, sheet number,
    scale, date, revision block, north arrow) and the plan drawing placed in a scaled viewport. Returns
    {svg, number, plan}. Pure SVG (no geometry kernel, no extra deps); PDF export is a follow-on slice."""
    plan = plan_svg(model, storey=storey, scale=scale)
    pw, ph = plan["paper"]

    inset = 8.0                                          # sheet border inset
    draw_w = _SHEET_W - _TB_W - 2 * inset - 6
    draw_h = _SHEET_H - 2 * inset - 6
    # fit the plan viewport into the drawing area, preserving aspect
    fit = min(draw_w / pw, draw_h / ph) if pw and ph else 1.0
    vw, vh = round(pw * fit, 2), round(ph * fit, 2)
    vx = round(inset + 3 + (draw_w - vw) / 2, 2)
    vy = round(inset + 3 + (draw_h - vh) / 2, 2)

    tbx = _SHEET_W - _TB_W - inset                       # titleblock left edge
    tby = inset
    tbh = _SHEET_H - 2 * inset
    # titleblock rows (from the bottom): sheet number (big), title, scale/date, project (top)
    rows = "".join(
        f'<line class="tbline" x1="{tbx}" y1="{round(tby + tbh - y, 2)}" '
        f'x2="{tbx + _TB_W}" y2="{round(tby + tbh - y, 2)}"/>'
        for y in (16, 40, 64))
    north = (f'<g transform="translate({round(tbx + _TB_W - 16, 2)},{round(tby + 20, 2)})">'
             f'<polygon class="narrow" points="0,-9 3,4 0,1 -3,4"/>'
             f'<text class="tb-l" x="0" y="10" text-anchor="middle">N</text></g>')

    plan_vp = (f'<svg x="{vx}" y="{vy}" width="{vw}" height="{vh}" '
               f'viewBox="0 0 {pw} {ph}" preserveAspectRatio="xMidYMid meet">{plan["inner"]}</svg>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_SHEET_W}mm" height="{_SHEET_H}mm" '
        f'viewBox="0 0 {_SHEET_W} {_SHEET_H}"><style>{_SHEET_STYLE}</style>'
        f'<rect x="0" y="0" width="{_SHEET_W}" height="{_SHEET_H}" fill="#fff"/>'
        f'<rect class="border" x="{inset}" y="{inset}" width="{_SHEET_W - 2 * inset}" '
        f'height="{_SHEET_H - 2 * inset}"/>'
        # drawing viewport
        + plan_vp
        # titleblock frame + rows
        + f'<rect class="border" x="{tbx}" y="{tby}" width="{_TB_W}" height="{tbh}"/>' + rows + north
        + f'<text class="tb-logo" x="{round(tbx + 6, 2)}" y="{round(tby + 12, 2)}">MASSING</text>'
        + f'<text class="tb-l" x="{round(tbx + 6, 2)}" y="{round(tby + 22, 2)}">{_esc(project)[:34]}</text>'
        # title
        + f'<text class="tb-t" x="{round(tbx + 6, 2)}" y="{round(tby + tbh - 46, 2)}">{_esc(title)[:30]}</text>'
        + (f'<text class="tb-l" x="{round(tbx + 6, 2)}" y="{round(tby + tbh - 26, 2)}">SCALE 1:{scale}'
           f'{"   " + _esc(date) if date else ""}</text>')
        + (f'<text class="tb-l" x="{round(tbx + 6, 2)}" y="{round(tby + tbh - 20, 2)}">'
           f'{("DRAWN " + _esc(drawn_by)) if drawn_by else ""}</text>')
        # big sheet number bottom-right
        + f'<text class="tb-b" x="{round(tbx + _TB_W - 6, 2)}" y="{round(tby + tbh - 5, 2)}" '
        f'text-anchor="end">{_esc(number)}</text>'
        + "</svg>"
    )
    return {"svg": svg, "number": number, "title": title,
            "plan": {"elements": plan["elements"], "keynotes": plan["keynotes"]}}


def _empty_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="60mm" viewBox="0 0 100 60">'
            f"<style>{_STYLE}</style>"
            '<rect class="sheet" x="0" y="0" width="100" height="60"/>'
            '<text class="label" x="8" y="30">No plan geometry (draw walls/slabs first)</text></svg>')
