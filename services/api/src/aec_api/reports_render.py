"""Report Center renderers — turn a neutral `Report` into PDF (reportlab) or Excel sheets. Presentation
only: no knowledge of how a report was built, just how to draw it. Kept separate so the builders stay
data-focused and the rendering can evolve (styling, chart kinds) without touching them."""
from __future__ import annotations

import io
from datetime import date
from typing import Any

from .reports_core import Report


def to_pdf(rep: Report) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("RTitle", parent=ss["Title"], fontSize=18, spaceAfter=2))
    ss.add(ParagraphStyle("RSub", parent=ss["Normal"], textColor=colors.grey, spaceAfter=10))
    f: list[Any] = [Paragraph(rep.title, ss["RTitle"]),
                    Paragraph(f"{rep.subtitle} · {date.today().isoformat()}", ss["RSub"])]
    if rep.kpis:
        cells = [[Paragraph(f"<b>{v}</b><br/><font size=8 color='grey'>{k}</font>", ss["Normal"]) for k, v in rep.kpis[i:i + 4]]
                 for i in range(0, len(rep.kpis), 4)]
        kt = Table(cells, colWidths=[1.7 * inch] * 4)
        kt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        f += [kt, Spacer(1, 12)]
    for tbl in rep.tables:
        f.append(Paragraph(tbl["name"], ss["Heading3"]))
        data = [tbl["headers"]] + (tbl["rows"] or [["(none)"] + [""] * (len(tbl["headers"]) - 1)])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a4a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")])]))
        f += [t, Spacer(1, 12)]
    for ch in rep.charts:
        f.append(Paragraph(ch["name"], ss["Heading3"]))
        f += [_chart_drawing(ch), Spacer(1, 12)]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(letter), topMargin=0.7 * inch, bottomMargin=0.6 * inch,
                      leftMargin=0.6 * inch, rightMargin=0.6 * inch, title=rep.title).build(f)
    return buf.getvalue()


_CHART_COLORS = ["#4a8cff", "#33d17a", "#e6a700", "#9b7cff", "#4ac6e2", "#e2554a"]


def _chart_drawing(ch: dict[str, Any]):
    """A reportlab Drawing (bar or line) — built-in graphics, no extra dependency."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    W, H = 640, 220
    d = Drawing(W, H)
    cats = ch["categories"] or [""]
    series = ch["series"] or [{"name": "", "values": []}]
    if ch["kind"] == "line":
        lp = LinePlot()
        lp.x, lp.y, lp.width, lp.height = 44, 36, W - 80, H - 70
        lp.data = [list(enumerate(s["values"])) for s in series]
        for i in range(len(series)):
            lp.lines[i].strokeColor = colors.HexColor(_CHART_COLORS[i % len(_CHART_COLORS)])
            lp.lines[i].strokeWidth = 1.6
        lp.xValueAxis.valueMin = 0
        lp.xValueAxis.valueMax = max(1, len(cats) - 1)
        d.add(lp)
    else:
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 44, 40, W - 80, H - 76
        bc.data = [s["values"] for s in series]
        bc.categoryAxis.categoryNames = cats
        bc.categoryAxis.labels.fontSize = 7
        bc.categoryAxis.labels.angle = 20
        bc.categoryAxis.labels.dy = -4
        bc.valueAxis.valueMin = 0
        bc.barWidth = 4
        for i in range(len(series)):
            bc.bars[i].fillColor = colors.HexColor(_CHART_COLORS[i % len(_CHART_COLORS)])
        d.add(bc)
    # simple legend
    for i, s in enumerate(series):
        d.add(String(48 + i * 110, H - 12, "■ " + str(s["name"]),
                     fontSize=8, fillColor=colors.HexColor(_CHART_COLORS[i % len(_CHART_COLORS)])))
    return d


def to_sheets(rep: Report) -> dict[str, tuple[list[str], list[list[Any]]]]:
    """Excel sheets — KPIs first, then each table (sheet names capped at Excel's 31-char limit)."""
    sheets: dict[str, tuple[list[str], list[list[Any]]]] = {}
    if rep.kpis:
        sheets["Summary"] = (["Metric", "Value"], [[k, v] for k, v in rep.kpis])
    for i, tbl in enumerate(rep.tables):
        # Excel sheet titles forbid / \ ? * [ ] : and cap at 31 chars
        nm = "".join("-" if ch in r"/\?*[]:" else ch for ch in (tbl["name"] or f"Table {i + 1}"))[:31]
        sheets[nm or f"Table {i + 1}"] = (tbl["headers"], tbl["rows"])
    return sheets
