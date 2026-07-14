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


# plan poché fill per IFC class (matches the SVG stylesheet), for the PDF renderer
_PDF_FILL = {"IfcWall": (0.29, 0.29, 0.29), "IfcColumn": (0.16, 0.16, 0.16),
             "IfcSlab": (0.95, 0.95, 0.95), "IfcSpace": (0.93, 0.96, 1.0),
             "IfcRoof": (0.96, 0.94, 0.90), "IfcFooting": (0.90, 0.90, 0.90)}


def sheet_pdf(model: ifcopenshell.file, storey: str | None = None, scale: int = 100,
              project: str = "Project", number: str = "A-101", title: str = "FLOOR PLAN",
              date: str = "", drawn_by: str = "") -> bytes:
    """W11 C3b: render the issuable sheet (ARCH-D border + titleblock + plan poché + dimensions + keynote
    legend) **directly to PDF** via reportlab (BSD, no SVG→PDF dependency). Returns PDF bytes — the
    submittable construction-document deliverable. Reuses the same footprint/code helpers as the SVG path."""
    from io import BytesIO

    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    unit_scale = uu.calculate_unit_scale(model)
    paper = (1000.0 / float(scale)) * unit_scale
    margin_mm = 18.0

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
                shapes.append((el, cls, fp))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(_SHEET_W * mm, _SHEET_H * mm))
    inset = 8.0
    # sheet border
    c.setLineWidth(1)
    c.rect(inset * mm, inset * mm, (_SHEET_W - 2 * inset) * mm, (_SHEET_H - 2 * inset) * mm)

    if shapes:
        xs = [p[0] for _, _, fp in shapes for p in fp]
        ys = [p[1] for _, _, fp in shapes for p in fp]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        legend_mm = 62.0
        pw = (maxx - minx) * paper + 2 * margin_mm + legend_mm
        ph = (maxy - miny) * paper + 2 * margin_mm
        draw_w = _SHEET_W - _TB_W - 2 * inset - 6
        draw_h = _SHEET_H - 2 * inset - 6
        fit = min(draw_w / pw, draw_h / ph) if pw and ph else 1.0
        vw, vh = pw * fit, ph * fit
        vx = inset + 3 + (draw_w - vw) / 2
        vy = inset + 3 + (draw_h - vh) / 2

        def PT(x, y):
            """world (file units) → PDF points (origin bottom-left)."""
            sx = vx + ((x - minx) * paper + margin_mm) * fit
            sy = vy + ((maxy - y) * paper + margin_mm) * fit
            return sx * mm, (_SHEET_H - sy) * mm

        # plan poché
        for _el, cls, fp in shapes:
            path = c.beginPath()
            x0, y0 = PT(*fp[0])
            path.moveTo(x0, y0)
            for pnt in fp[1:]:
                path.lineTo(*PT(*pnt))
            path.close()
            c.setFillColorRGB(*_PDF_FILL.get(cls, (0.9, 0.9, 0.9)))
            c.setStrokeColorRGB(0.07, 0.07, 0.07)
            c.setLineWidth(0.3)
            c.drawPath(path, fill=1, stroke=1)

        # overall dimensions (width below, height left) in metres
        c.setStrokeColorRGB(0.0, 0.4, 0.8)
        c.setFillColorRGB(0.0, 0.4, 0.8)
        c.setFont("Helvetica", 6)
        (wx1, wy1), (wx2, _wy2) = PT(minx, miny), PT(maxx, miny)
        dy = wy1 - 8 * mm
        c.setLineWidth(0.4)
        c.line(wx1, dy, wx2, dy)
        c.drawCentredString((wx1 + wx2) / 2, dy + 2, f"{(maxx - minx) * unit_scale:.2f} m")
        (hx1, hy1), (_hx2, hy2) = PT(minx, miny), PT(minx, maxy)
        dx = hx1 - 8 * mm
        c.line(dx, hy1, dx, hy2)
        c.saveState()
        c.translate(dx - 2, (hy1 + hy2) / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{(maxy - miny) * unit_scale:.2f} m")
        c.restoreState()

        # keynotes: numbered bubbles + legend (from Track-D classification codes)
        order: dict[tuple[str, str], int] = {}
        legend_rows: list[tuple[int, str, str]] = []
        for el, _cls, fp in shapes:
            codes = _element_codes(el)
            pick = next((cc for sysn in _KEYNOTE_SYS for cc in codes if cc[0] == sysn), None)
            if not pick or not pick[1]:
                continue
            key = (pick[0], pick[1])
            if key not in order:
                order[key] = len(order) + 1
                legend_rows.append((order[key], f"{pick[0]} {pick[1]}", pick[2] or ""))
            cx, cy = _centroid(fp)
            bx, by = PT(cx, cy)
            c.setFillColorRGB(1, 1, 1)
            c.setStrokeColorRGB(0.7, 0, 0)
            c.setLineWidth(0.3)
            c.circle(bx, by, 2.4 * mm, fill=1, stroke=1)
            c.setFillColorRGB(0.7, 0, 0)
            c.setFont("Helvetica", 6)
            c.drawCentredString(bx, by - 2, str(order[key]))
        if legend_rows:
            lx = (_SHEET_W - _TB_W - inset - legend_mm + 4)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(lx * mm, (_SHEET_H - margin_mm) * mm, "KEYNOTES")
            c.setFont("Helvetica", 6)
            for i, (num, code, ttl) in enumerate(legend_rows[:24]):
                ry = margin_mm + 6 + i * 5
                by = (_SHEET_H - ry) * mm
                c.setFillColorRGB(1, 1, 1)
                c.setStrokeColorRGB(0.7, 0, 0)
                c.circle((lx + 2) * mm, by + 1, 2.2 * mm, fill=1, stroke=1)
                c.setFillColorRGB(0.7, 0, 0)
                c.drawCentredString((lx + 2) * mm, by - 1, str(num))
                c.setFillColorRGB(0.13, 0.13, 0.13)
                c.drawString((lx + 7) * mm, by, f"{code} - {ttl[:30]}")

    # titleblock
    tbx = _SHEET_W - _TB_W - inset
    tby = inset
    tbh = _SHEET_H - 2 * inset
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(1)
    c.rect(tbx * mm, tby * mm, _TB_W * mm, tbh * mm)
    c.setLineWidth(0.4)
    for yy in (16, 40, 64):
        c.line(tbx * mm, (tby + tbh - yy) * mm, (tbx + _TB_W) * mm, (tby + tbh - yy) * mm)
    c.setFont("Helvetica-Bold", 12)
    c.drawString((tbx + 6) * mm, (_SHEET_H - tby - 12) * mm, "MASSING")
    c.setFont("Helvetica", 7)
    c.drawString((tbx + 6) * mm, (_SHEET_H - tby - 22) * mm, project[:34])
    c.setFont("Helvetica-Bold", 9)
    c.drawString((tbx + 6) * mm, (_SHEET_H - (tby + tbh - 46)) * mm, title[:30])
    c.setFont("Helvetica", 7)
    scale_line = f"SCALE 1:{scale}" + (f"   {date}" if date else "")
    c.drawString((tbx + 6) * mm, (_SHEET_H - (tby + tbh - 30)) * mm, scale_line)
    if drawn_by:
        c.drawString((tbx + 6) * mm, (_SHEET_H - (tby + tbh - 22)) * mm, f"DRAWN {drawn_by}")
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString((tbx + _TB_W - 6) * mm, (_SHEET_H - (tby + tbh - 6)) * mm, number)
    # north arrow (simple)
    c.setFont("Helvetica", 7)
    c.drawCentredString((tbx + _TB_W - 16) * mm, (_SHEET_H - tby - 32) * mm, "N")

    c.showPage()
    c.save()
    return buf.getvalue()


def schedules(model: ifcopenshell.file) -> dict:
    """W11 C4: compute door / window / room schedules from the model — the tabular half of a CD set.
    Values come straight from the elements (marks, sizes, types, levels, areas). Returns
    {doors, windows, rooms} each {columns:[...], rows:[[...]]}."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(model)                    # metres per file unit

    def _lvl(el):
        st = ue.get_container(el) or ue.get_aggregate(el)
        return getattr(st, "Name", None) or ""

    def _m(v):
        try:
            return f"{float(v) * scale:.2f}" if v is not None else ""
        except (TypeError, ValueError):
            return ""

    def _type(el):
        t = ue.get_type(el)
        if t is not None and getattr(t, "Name", None):
            return t.Name
        return getattr(el, "PredefinedType", None) or ""

    def _opening(el):                                         # marks default from GUID tail when unnamed
        return getattr(el, "Name", None) or (el.GlobalId[:8])

    doors = [[_opening(d), _m(getattr(d, "OverallWidth", None)), _m(getattr(d, "OverallHeight", None)),
              _type(d), _lvl(d)] for d in model.by_type("IfcDoor")]
    windows = [[_opening(w), _m(getattr(w, "OverallWidth", None)), _m(getattr(w, "OverallHeight", None)),
                _type(w), _lvl(w)] for w in model.by_type("IfcWindow")]
    rooms = []
    for s in model.by_type("IfcSpace"):
        q = ue.get_pset(s, "Qto_SpaceBaseQuantities") or {}
        area = q.get("NetFloorArea") or q.get("GrossFloorArea")
        rooms.append([getattr(s, "Name", None) or "", getattr(s, "LongName", None) or "",
                      f"{float(area):.2f}" if area else "", _lvl(s)])

    return {
        "doors": {"columns": ["Mark", "Width (m)", "Height (m)", "Type", "Level"],
                  "rows": sorted(doors, key=lambda r: r[0])},
        "windows": {"columns": ["Mark", "Width (m)", "Height (m)", "Type", "Level"],
                    "rows": sorted(windows, key=lambda r: r[0])},
        "rooms": {"columns": ["No.", "Name", "Area (m²)", "Level"],
                  "rows": sorted(rooms, key=lambda r: r[0])},
    }


_SCHED_TITLE = {"doors": "DOOR SCHEDULE", "windows": "WINDOW SCHEDULE", "rooms": "ROOM SCHEDULE"}


def schedule_svg(model: ifcopenshell.file, kind: str = "doors") -> dict:
    """Render one schedule (doors|windows|rooms) as a standalone SVG table. Returns {svg, kind, rows}."""
    data = schedules(model).get(kind)
    if data is None:
        raise ValueError(f"unknown schedule {kind!r}; have doors|windows|rooms")
    cols, rows = data["columns"], data["rows"]
    title = _SCHED_TITLE.get(kind, kind.upper())
    col_w = 40.0
    row_h = 6.0
    pad = 8.0
    tw = col_w * len(cols)
    th = row_h * (len(rows) + 1)
    w = tw + 2 * pad
    h = th + 2 * pad + 8

    def cell(cx, cy, text, header=False, anchor="start"):
        cls = "sc-h" if header else "sc-c"
        x = cx + (2 if anchor == "start" else col_w / 2)
        return f'<text class="{cls}" x="{round(x, 2)}" y="{round(cy + 4, 2)}" text-anchor="{anchor}">{_esc(str(text))[:22]}</text>'

    parts = [f'<text class="sc-t" x="{pad}" y="{pad}">{title}</text>']
    y0 = pad + 6
    # header row
    parts.append(f'<rect class="sc-hr" x="{pad}" y="{round(y0, 2)}" width="{tw}" height="{row_h}"/>')
    for i, cname in enumerate(cols):
        parts.append(cell(pad + i * col_w, y0, cname, header=True))
    # body rows + grid
    for r, row in enumerate(rows):
        ry = y0 + (r + 1) * row_h
        for i, val in enumerate(row):
            parts.append(cell(pad + i * col_w, ry, val))
    for i in range(len(cols) + 1):                            # vertical rules
        vx = pad + i * col_w
        parts.append(f'<line class="sc-g" x1="{round(vx, 2)}" y1="{round(y0, 2)}" x2="{round(vx, 2)}" y2="{round(y0 + th, 2)}"/>')
    for r in range(len(rows) + 2):                            # horizontal rules
        ry = y0 + r * row_h
        parts.append(f'<line class="sc-g" x1="{pad}" y1="{round(ry, 2)}" x2="{round(pad + tw, 2)}" y2="{round(ry, 2)}"/>')

    style = (".sc-t{font:bold 4px sans-serif;fill:#000}.sc-h{font:bold 2.6px sans-serif;fill:#000}"
             ".sc-c{font:2.6px sans-serif;fill:#222}.sc-g{stroke:#333;stroke-width:0.2}"
             ".sc-hr{fill:#e8e8e8;stroke:none}")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w, 1)}mm" height="{round(h, 1)}mm" '
           f'viewBox="0 0 {round(w, 2)} {round(h, 2)}"><style>{style}</style>'
           f'<rect x="0" y="0" width="{round(w, 2)}" height="{round(h, 2)}" fill="#fff"/>'
           + "".join(parts) + "</svg>")
    return {"svg": svg, "kind": kind, "rows": len(rows)}


def _empty_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="60mm" viewBox="0 0 100 60">'
            f"<style>{_STYLE}</style>"
            '<rect class="sheet" x="0" y="0" width="100" height="60"/>'
            '<text class="label" x="8" y="30">No plan geometry (draw walls/slabs first)</text></svg>')
