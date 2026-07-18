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
from xml.sax.saxutils import escape as _xesc

import ifcopenshell

# computed schedules live in drawing_schedules.py (a pure leaf); imported here for the PDF path + re-exported
# so `drawing.schedules` / `.schedule_csv` / `.schedule_svg` keep working.
from .drawing_schedules import (  # used by the PDF path (schedule_pdf)  # noqa: F401 — re-exported façade for callers
    _SCHED_TITLE,
    schedule_csv,
    schedule_svg,
    schedules,
)

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
.dc{fill:#fff;stroke:#06c;stroke-width:0.4}
.dcx{stroke:#06c;stroke-width:0.4}
.dct{font:2px sans-serif;fill:#06c;text-anchor:middle;dominant-baseline:middle}
.lead{stroke:#06c;stroke-width:0.25}
.ann-note{font:2.4px sans-serif;fill:#137a2b}
.ann-tag{font:bold 2.4px sans-serif;fill:#137a2b}
.ann-dim line{stroke:#137a2b;stroke-width:0.25}
.ann-dimt{font:2.2px sans-serif;fill:#137a2b;text-anchor:middle}
.ann-cloud{fill:none;stroke:#b00;stroke-width:0.45}
.ann-revtag{font:bold 2.6px sans-serif;fill:#fff}
.ann-revtag-box{fill:#b00;stroke:#800}
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


def _doc_sheet_ref(doc) -> str:
    """The NCS bottom-of-bubble sheet reference for a detail callout: the document's Identification
    (a stable detail/sheet key like 'A-541/3'), else the sheet number derived from the Location URI's
    basename (`details/S-501.pdf` → `S-501`), else '—'. Real sheet-number refs on the callout (D5)."""
    ident = getattr(doc, "Identification", None)
    if ident and str(ident).strip():
        return str(ident).strip()
    loc = getattr(doc, "Location", None)
    if loc and str(loc).strip():
        base = str(loc).strip().replace("\\", "/").rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0] if "." in base else base
        if stem:
            return stem[:12]
    return "—"


def _element_docs(el):
    """Attached detail drawings from an element's IfcRelAssociatesDocument as `(name, sheet_ref)` — the
    Track-D document carriers that drive **detail callouts** (name → DETAILS legend, sheet_ref → the
    bottom of the divided-circle bubble) on the drawing (D5)."""
    out = []
    for rel in (getattr(el, "HasAssociations", None) or []):
        if not rel.is_a("IfcRelAssociatesDocument"):
            continue
        doc = rel.RelatingDocument
        name = getattr(doc, "Name", None) or getattr(doc, "Identification", None)
        if name:
            out.append((str(name), _doc_sheet_ref(doc)))
    return out


def _centroid(fp):
    return (sum(p[0] for p in fp) / len(fp), sum(p[1] for p in fp) / len(fp))


# keynote systems, in priority order (a reference keynote points at the spec section → MasterFormat wins)
_KEYNOTE_SYS = ("MasterFormat", "UniFormat", "OmniClass", "Uniclass")

# elements worth drawing on a plan, coarsest→finest (drawing order)
_PLAN_CLASSES = ["IfcSlab", "IfcRoof", "IfcSpace", "IfcWall", "IfcColumn", "IfcFooting"]


def _annotations(model, storey):
    """View-placed `IfcAnnotation`s (from add_annotation / add_dimension / add_revision_cloud) as world-coord
    render items, so annotations authored in the model appear on the generated plan (UX-2 loop-closer). Each
    item is a dict: {kind, text?, point?:(x,y), polys?:[[(x,y)…]]} — kind is note/tag/callout/dimension/
    revision. Coordinates are file units in world space (same space as `_footprint`)."""
    import ifcopenshell.util.element as ue
    import numpy as np

    out = []
    for ann in model.by_type("IfcAnnotation"):
        if storey:
            st = ue.get_container(ann) or ue.get_aggregate(ann)
            if st is None or (getattr(st, "Name", None) or "") != storey:
                continue
        world = _placement_matrix(ann)                 # ann ObjectPlacement → world (file units)
        rep = getattr(ann, "Representation", None)
        if rep is None:
            continue
        kind = (getattr(ann, "ObjectType", None) or "note").strip().lower()
        text, polys, tpt = None, [], None
        for r in rep.Representations:
            for it in (r.Items or []):
                if it.is_a("IfcTextLiteral"):
                    text = getattr(it, "Literal", None)
                    loc = getattr(getattr(it, "Placement", None), "Location", None)
                    lx, ly = (list(loc.Coordinates) + [0.0])[:2] if loc is not None else (0.0, 0.0)
                    v = world @ np.array([float(lx), float(ly), 0.0, 1.0])
                    tpt = (float(v[0]), float(v[1]))
                elif it.is_a("IfcPolyline"):
                    line = []
                    for p in it.Points:
                        c = list(p.Coordinates) + [0.0]
                        v = world @ np.array([float(c[0]), float(c[1]), 0.0, 1.0])
                        line.append((float(v[0]), float(v[1])))
                    if len(line) >= 2:
                        polys.append(line)
        if text is None and not polys:
            continue
        out.append({"kind": kind, "text": text, "point": tpt, "polys": polys})
    return out


# DISC-poché — plan-class → discipline code (matches the canonical spine in aec_data.disciplines /
# aec_api.classification: MasterFormat div 03 → Structural, 04/07/space-planning → Architectural).
_PLAN_DISC: dict[str, tuple[str, str]] = {
    "IfcWall": ("A", "Architectural"), "IfcRoof": ("A", "Architectural"), "IfcSpace": ("A", "Architectural"),
    "IfcSlab": ("S", "Structural"), "IfcColumn": ("S", "Structural"), "IfcFooting": ("S", "Structural"),
}


def _discipline_css_legend(tx_right: float, ty_top: float) -> tuple[str, str]:
    """DISC-poché: per-class fill overrides tinted by discipline + a DISCIPLINES legend block.
    Returns (extra_css, legend_svg)."""
    from . import disciplines

    css_parts, seen = [], {}
    for cls, (code, label) in _PLAN_DISC.items():
        col = disciplines.discipline_color(code)
        css_parts.append(f".disc .{cls}{{fill:{col};fill-opacity:.55}}")
        seen[code] = (label, col)
    rows = []
    for i, (code, (label, col)) in enumerate(sorted(seen.items())):
        y = round(ty_top + 5 + i * 5, 2)
        rows.append(f'<rect x="{tx_right}" y="{y - 3}" width="4" height="3.4" fill="{col}" fill-opacity=".55" stroke="#333" stroke-width="0.2"/>'
                    f'<text class="label" x="{tx_right + 5.5}" y="{y}">{code} — {label}</text>')
    legend = (f'<text class="label" style="font-weight:bold" x="{tx_right}" y="{ty_top}">DISCIPLINES</text>'
              + "".join(rows))
    return "".join(css_parts), legend


def plan_svg(model: ifcopenshell.file, storey: str | None = None, scale: int = 100,
             margin_mm: float = 18.0, dimensions: bool = True, keynotes: bool = True,
             details: bool = True, annotations: bool = True, by_discipline: bool = False) -> dict:
    """Generate a schematic **plan SVG** from element footprints. `storey` limits to one level (by name);
    `scale` is the drawing scale (1:`scale`). With `dimensions`, overall width/height dimension strings are
    drawn; with `keynotes`, elements carrying a Track-D classification code get numbered keynote bubbles + a
    legend; with `details`, elements carrying an attached detail (IfcRelAssociatesDocument) get a **detail
    callout** (a divided circle) + a DETAILS legend keyed to the detail drawing (D5). Returns
    {svg, elements, keynotes, details, bounds, scale}. Paper coords are millimetres at the scale."""
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
        # carry `paper`/`inner` even when empty so sheet_svg can still compose a border+titleblock
        # sheet (a bogus storey / model with no plan geometry must not crash the sheet generator)
        empty = _empty_svg()
        inner = empty[empty.index(">", empty.index("<svg")) + 1: empty.rindex("</svg>")]
        return {"svg": empty, "inner": inner, "paper": [100.0, 60.0], "elements": 0,
                "keynotes": 0, "bounds": None, "scale": scale}

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

    # ── detail callouts: elements with an attached detail → a divided-circle callout + DETAILS legend ──
    callouts: list[str] = []
    detail_rows: list[tuple[int, str]] = []
    if details:
        dorder: dict[str, int] = {}
        for el, _cls, fp in shapes:
            docs = _element_docs(el)
            if not docs:
                continue
            name, sheet_ref = docs[0]
            if name not in dorder:
                dorder[name] = len(dorder) + 1
                detail_rows.append((dorder[name], name))
            dn = dorder[name]
            cx, cy = _centroid(fp)
            # offset up-left of the centroid so the callout doesn't sit on the keynote bubble
            bx, by = round(tx(cx) - 4, 2), round(ty(cy) - 4, 2)
            # NCS-style divided circle: detail number (top) over the real sheet ref (bottom) + a short leader
            # SHEET-LINK: the bubble is an SVG anchor carrying its target sheet — a click in the
            # Drawings workspace (or any SVG viewer honoring xlink) can jump to that sheet
            callouts.append(
                f'<a class="sheet-link" data-sheet="{_xesc(sheet_ref)}" href="#sheet={_xesc(sheet_ref)}">'
                f'<line class="lead" x1="{bx}" y1="{by}" x2="{round(tx(cx), 2)}" y2="{round(ty(cy), 2)}"/>'
                f'<circle class="dc" cx="{bx}" cy="{by}" r="3.2"/>'
                f'<line class="dcx" x1="{bx - 3.2}" y1="{by}" x2="{bx + 3.2}" y2="{by}"/>'
                f'<text class="dct" x="{bx}" y="{round(by - 0.6, 2)}">{dn}</text>'
                f'<text class="dct" x="{bx}" y="{round(by + 2.6, 2)}">{_xesc(sheet_ref)}</text></a>')

    # ── dimensions: overall width (below) + overall height (left) ──
    dims: list[str] = []
    if dimensions:
        y0 = round(ty(miny) + 8, 2)                            # below the plan
        dims.append(_hdim(tx(minx), tx(maxx), y0, (maxx - minx) * unit_scale))
        x0 = round(tx(minx) - 8, 2)                            # left of the plan
        dims.append(_vdim(x0, ty(maxy), ty(miny), (maxy - miny) * unit_scale))

    # ── view-placed annotations: notes / tags / callouts / dimensions / revision clouds (UX-2) ──
    ann_svg: list[str] = []
    ann_count = 0
    if annotations:
        for a in _annotations(model, storey):
            kind, txt, pt, apolys = a["kind"], a.get("text"), a.get("point"), a.get("polys") or []
            drew = False
            for line in apolys:                                # dimension line / revision cloud outline
                pts = " ".join(f"{tx(x)},{ty(y)}" for x, y in line)
                cls = "ann-cloud" if kind in ("revision", "cloud") else "ann-dim"
                if kind in ("revision", "cloud"):
                    ann_svg.append(f'<polyline class="ann-cloud" points="{pts}"/>')
                else:
                    ann_svg.append(f'<g class="ann-dim"><polyline fill="none" points="{pts}"/></g>')
                drew = True
            if txt:
                px, py = (tx(pt[0]), ty(pt[1])) if pt else (margin_mm + 2, margin_mm + 2)
                if kind == "revision":
                    bw = min(max(len(txt) * 1.5 + 2, 5), 30)
                    ann_svg.append(f'<rect class="ann-revtag-box" x="{round(px - 1, 2)}" '
                                   f'y="{round(py - 3, 2)}" width="{round(bw, 2)}" height="4" rx="0.6"/>'
                                   f'<text class="ann-revtag" x="{round(px + 0.5, 2)}" y="{round(py, 2)}">{_esc(txt)[:24]}</text>')
                else:
                    cls = "ann-dimt" if kind == "dimension" else ("ann-tag" if kind == "tag" else "ann-note")
                    ann_svg.append(f'<text class="{cls}" x="{px}" y="{py}">{_esc(txt)[:48]}</text>')
                drew = True
            if drew:
                ann_count += 1

    legend_svg = ""
    lx = round(w - legend_mm + 4, 2)
    ry_next = margin_mm
    if keynotes and legend_rows:
        rows = [f'<text class="lgd-h" x="{lx}" y="{round(margin_mm, 2)}">KEYNOTES</text>']
        for i, (num, code, title) in enumerate(legend_rows[:24]):
            ry = round(margin_mm + 6 + i * 5, 2)
            rows.append(f'<circle class="kn" cx="{lx + 2}" cy="{round(ry - 1.2, 2)}" r="2.2"/>'
                        f'<text class="knt" x="{lx + 2}" y="{round(ry - 0.4, 2)}">{num}</text>'
                        f'<text class="lgd" x="{lx + 7}" y="{ry}">{_esc(code)} - {_esc(title)[:30]}</text>')
        legend_svg = "".join(rows)
        ry_next = margin_mm + 6 + min(len(legend_rows), 24) * 5 + 4
    if details and detail_rows:
        rows = [f'<text class="lgd-h" x="{lx}" y="{round(ry_next, 2)}">DETAILS</text>']
        for i, (num, name) in enumerate(detail_rows[:16]):
            ry = round(ry_next + 6 + i * 5, 2)
            rows.append(f'<circle class="dc" cx="{lx + 2}" cy="{round(ry - 1.2, 2)}" r="2.4"/>'
                        f'<text class="dct" x="{lx + 2}" y="{round(ry - 0.4, 2)}">{num}</text>'
                        f'<text class="lgd" x="{lx + 7}" y="{ry}">{_esc(name)[:32]}</text>')
        legend_svg += "".join(rows)

    # DISC-poché: discipline-tinted fills + a DISCIPLINES legend (the plan reads by trade at a glance)
    disc_css = disc_legend = ""
    if by_discipline:
        disc_css, disc_legend = _discipline_css_legend(round(w - margin_mm - 42, 2), margin_mm + 4)
    inner = (
        f"<style>{_STYLE}{disc_css}</style>"
        f'<rect class="sheet" x="0" y="0" width="{round(w, 2)}" height="{round(h, 2)}"/>'
        + ('<g class="disc">' if by_discipline else "")
        + "".join(polys)
        + ("</g>" if by_discipline else "")
        + "".join(dims) + "".join(bubbles) + "".join(callouts)
        + "".join(ann_svg) + legend_svg + disc_legend
        + f'<text class="label" x="{margin_mm}" y="{round(h - 4, 2)}">PLAN 1:{scale}'
        + (f" - {_esc(storey)}" if storey else "") + "</text>"
    )
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w, 1)}mm" height="{round(h, 1)}mm" '
           f'viewBox="0 0 {round(w, 2)} {round(h, 2)}">{inner}</svg>')
    return {"svg": svg, "inner": inner, "paper": [round(w, 2), round(h, 2)],
            "elements": len(shapes), "keynotes": len(legend_rows), "details": len(detail_rows),
            "annotations": ann_count, "by_discipline": bool(by_discipline),
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
              date: str = "", drawn_by: str = "", link_out: list | None = None) -> bytes:
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

        # detail callouts: elements with an attached detail → an NCS divided-circle bubble (detail
        # number over the real sheet ref) + a DETAILS legend, below the keynotes (D5, PDF path)
        dorder: dict[str, int] = {}
        detail_rows: list[tuple[int, str]] = []
        for el, _cls, fp in shapes:
            docs = _element_docs(el)
            if not docs:
                continue
            name, sheet_ref = docs[0]
            if name not in dorder:
                dorder[name] = len(dorder) + 1
                detail_rows.append((dorder[name], name))
            dn = dorder[name]
            cx, cy = _centroid(fp)
            bx, by = PT(cx, cy)
            bx, by = bx - 4 * mm, by + 4 * mm          # offset up-left of the centroid (PDF y is up)
            rr = 3.2 * mm
            c.setFillColorRGB(1, 1, 1)
            c.setStrokeColorRGB(0.1, 0.1, 0.1)
            c.setLineWidth(0.3)
            c.line(bx + 1.5 * mm, by - 1.5 * mm, *PT(cx, cy))   # short leader to the element
            c.circle(bx, by, rr, fill=1, stroke=1)
            c.line(bx - rr, by, bx + rr, by)                    # NCS divider
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("Helvetica", 5)
            c.drawCentredString(bx, by + 1, str(dn))            # detail number (top)
            c.drawCentredString(bx, by - 4, sheet_ref[:8])      # sheet ref (bottom)
            if link_out is not None and sheet_ref and sheet_ref != "—":
                # SHEET-LINK: the bubble's hit-box (points) + its target sheet ref — the compiled set
                # binds it to a PDF GoTo link when that sheet is part of the set
                link_out.append({"sheet": sheet_ref, "rect": (bx - rr, by - rr, bx + rr, by + rr)})
        if detail_rows:
            lx = (_SHEET_W - _TB_W - inset - legend_mm + 4)
            hy = margin_mm + 6 + (len(legend_rows) + 1) * 5     # sit below the keynote legend
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(lx * mm, (_SHEET_H - hy) * mm, "DETAILS")
            c.setFont("Helvetica", 6)
            for k, (num, dname) in enumerate(detail_rows[:12]):
                ry = hy + 5 + k * 5
                by2 = (_SHEET_H - ry) * mm
                c.setFillColorRGB(1, 1, 1)
                c.setStrokeColorRGB(0.1, 0.1, 0.1)
                c.circle((lx + 2) * mm, by2 + 1, 2.2 * mm, fill=1, stroke=1)
                c.setFillColorRGB(0.1, 0.1, 0.1)
                c.drawCentredString((lx + 2) * mm, by2 - 1, str(num))
                c.setFillColorRGB(0.13, 0.13, 0.13)
                c.drawString((lx + 7) * mm, by2, dname[:32])

    _titleblock_pdf(c, mm, inset, project, number, title, f"SCALE 1:{scale}", date, drawn_by, north=True)

    c.showPage()
    c.save()
    return buf.getvalue()


def _titleblock_pdf(c, mm, inset: float, project: str, number: str, title: str,
                    scale_text: str, date: str, drawn_by: str, north: bool = False) -> None:
    """Draw the shared ARCH-D titleblock strip (right edge) on the reportlab canvas."""
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
    scale_line = scale_text + (f"   {date}" if date else "")
    c.drawString((tbx + 6) * mm, (_SHEET_H - (tby + tbh - 30)) * mm, scale_line)
    if drawn_by:
        c.drawString((tbx + 6) * mm, (_SHEET_H - (tby + tbh - 22)) * mm, f"DRAWN {drawn_by}")
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString((tbx + _TB_W - 6) * mm, (_SHEET_H - (tby + tbh - 6)) * mm, number)
    if north:
        c.setFont("Helvetica", 7)
        c.drawCentredString((tbx + _TB_W - 16) * mm, (_SHEET_H - tby - 32) * mm, "N")


def schedule_pdf(model: ifcopenshell.file, kinds: list[str] | None = None, project: str = "Project",
                 number: str = "A-601", title: str = "SCHEDULES", date: str = "",
                 drawn_by: str = "") -> bytes:
    """W11 C6: render the computed door/window/room **schedules onto an issuable ARCH-D sheet** (border +
    titleblock) as PDF via reportlab — the tabular half of the CD set as a submittable sheet, laid out in
    columns. `kinds` selects which schedules (default all three)."""
    from io import BytesIO

    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    data = schedules(model)
    kinds = kinds or ["doors", "windows", "rooms"]
    inset = 8.0

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(_SHEET_W * mm, _SHEET_H * mm))
    c.setLineWidth(1)
    c.setStrokeColorRGB(0, 0, 0)
    c.rect(inset * mm, inset * mm, (_SHEET_W - 2 * inset) * mm, (_SHEET_H - 2 * inset) * mm)

    area_left = inset + 6
    area_right = _SHEET_W - _TB_W - inset - 6
    top = _SHEET_H - inset - 12
    col_x = area_left
    col_w = 128.0                     # each schedule column block
    row_h = 5.2

    def _y(v):                        # sheet-space mm (top-origin) → PDF points (bottom-origin)
        return (_SHEET_H - v) * mm

    for kind in kinds:
        tbl = data.get(kind) or {"columns": [], "rows": []}
        cols, rows = tbl["columns"], tbl["rows"]
        if col_x + col_w > area_right and col_x > area_left:
            break                     # ran out of horizontal room on this single sheet
        y = top
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_x * mm, _y(y), _SCHED_TITLE.get(kind, kind.upper()))
        y += 6
        # header
        n = max(1, len(cols))
        cw = col_w / n
        c.setFont("Helvetica-Bold", 6)
        for i, h in enumerate(cols):
            c.drawString((col_x + i * cw) * mm, _y(y), str(h)[:16])
        y += 1.5
        c.setLineWidth(0.4)
        c.line(col_x * mm, _y(y), (col_x + col_w) * mm, _y(y))
        y += 3
        c.setFont("Helvetica", 6)
        for r in rows:
            if y > _SHEET_H - inset - 10:
                c.setFont("Helvetica-Oblique", 6)
                c.drawString(col_x * mm, _y(y), "… (truncated — see the interactive schedule)")
                break
            for i, cell in enumerate(r[:n]):
                c.drawString((col_x + i * cw) * mm, _y(y), str(cell)[:18])
            y += row_h
        col_x += col_w + 8

    _titleblock_pdf(c, mm, inset, project, number, title, "SCHEDULE", date, drawn_by)
    c.showPage()
    c.save()
    return buf.getvalue()


def _empty_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="60mm" viewBox="0 0 100 60">'
            f"<style>{_STYLE}</style>"
            '<rect class="sheet" x="0" y="0" width="100" height="60"/>'
            '<text class="label" x="8" y="30">No plan geometry (draw walls/slabs first)</text></svg>')
