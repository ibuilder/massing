"""REL-3 leaf: sheet renderers — turn a composed `layout` dict into an SVG string or a PDF byte-stream.

The pure output half of `drawings.py`: no ifcopenshell, no geometry, no model — just `layout`/`meta` dicts
of pre-computed view rectangles, polylines, annotation tuples and title-block fields. Extracted so the
geometry/compose half and the paper-output half evolve independently; `drawings.py` re-imports these
(so `drawings.render_sheet_svg` / `render_sheet_pdf` callers are unaffected) and also uses the shared
`_dim_h` / `_dim_v` dimension primitives in its plan generator.
"""
from __future__ import annotations


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


def render_sheet_dxf(layout: dict, meta: dict) -> str:
    """DXF-EXPORT: the composed sheet as an R12 DXF — the same `compose()` layout the SVG/PDF renderers
    consume, emitted as CAD entities so consultants get editable linework, not just paper. Layers:
    BORDER · TITLEBLOCK · TEXT · one `VIEW-n` per placed viewport (+ ANNO for grids/levels/dims/bubbles).
    DXF is Y-up, the layout is SVG-style Y-down → every y is flipped against the page height."""
    from . import dxf

    pw, ph = layout["page"]
    fy = lambda y: ph - y                              # noqa: E731 — page-space Y flip
    ents: list[str] = []
    # page border (mirrors the SVG's 6-unit inset frame)
    ents += dxf.polyline_entities([[(6, fy(6)), (pw - 6, fy(6)), (pw - 6, fy(ph - 6)),
                                    (6, fy(ph - 6)), (6, fy(6))]], layer="BORDER", closed_hint=True)
    for vi, v in enumerate(layout["views"]):
        layer = f"VIEW-{vi + 1}"
        x, y, _w, _h = v["rect"]
        ents.append(dxf.text_entity(x + 14, fy(y + 16), 10, f'{v["label"]} · {v["scale_text"]}', "TEXT"))
        ents += dxf.polyline_entities([[(p[0], fy(p[1])) for p in poly] for poly in v["polys"]],
                                      layer=layer, closed_hint=bool(v.get("filled")))
        for e in v.get("extras", []):
            if e[0] == "lvl":
                _, x1, x2, yy = e
                ents.append(dxf.line_entity(x1, fy(yy), x2, fy(yy), "ANNO"))
            elif e[0] == "line":
                _, x1, y1, x2, y2, _dash = e
                ents.append(dxf.line_entity(x1, fy(y1), x2, fy(y2), "ANNO"))
            elif e[0] == "bub":
                _, bx, byy, r, lbl = e
                ents.append(dxf.circle_entity(bx, fy(byy), r, "ANNO"))
                ents.append(dxf.text_entity(bx - r / 2, fy(byy + 2.5), 5, str(lbl), "ANNO"))
            elif e[0] == "dim":
                _, x1, y1, x2, y2, txt = e
                ents.append(dxf.line_entity(x1, fy(y1), x2, fy(y2), "ANNO"))
                ents.append(dxf.text_entity((x1 + x2) / 2, fy((y1 + y2) / 2) + 3, 6, str(txt), "ANNO"))
    # title block strip
    m = layout["margin"]
    by = ph - m - layout["tb_h"] + 10
    ents.append(dxf.line_entity(m, fy(by), pw - m, fy(by), "TITLEBLOCK"))
    ents.append(dxf.text_entity(m + 8, fy(by + 34), 16, str(meta.get("project", "PROJECT")), "TITLEBLOCK"))
    fields = [("SHEET", meta.get("sheet", "A-101")), ("ISSUED FOR", meta.get("purpose", "") or "—"),
              ("REV", str(meta.get("revision", "") or "—")), ("DATE", meta.get("date", "")),
              ("DRAWN", meta.get("drawn_by", "")), ("SCALE", "AS NOTED")]
    fx = pw - m - 360
    for i, (k, val) in enumerate(fields):
        cx = fx + (i % 2) * 180
        cy = by + 20 + (i // 2) * 28
        ents.append(dxf.text_entity(cx, fy(cy), 7, str(k), "TITLEBLOCK"))
        ents.append(dxf.text_entity(cx, fy(cy + 14), 9, str(val or ""), "TITLEBLOCK"))
    return dxf.document(ents)


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
