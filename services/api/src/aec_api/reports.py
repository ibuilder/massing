"""Report Center — detailed, exportable construction reports (PDF + Excel).

A small catalog of best-practice reports (executive health, cost, EVM/S-curve, operational logs,
contracts & signatures) built from the existing engines (px.py, project_budget.py, the modules
records) into a neutral structure, then rendered to PDF (reportlab) or Excel (openpyxl via exports).
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import project_budget as pb
from . import px
from .models import Project

# id -> (name, group)
REPORTS: dict[str, tuple[str, str]] = {
    "executive": ("Executive Summary", "Health"),
    "risk": ("Risk Digest", "Health"),
    "cost": ("Cost Report", "Cost"),
    "evm": ("EVM / S-Curve", "Cost"),
    "change_orders": ("Change Order Log", "Logs"),
    "rfi": ("RFI Log", "Logs"),
    "submittals": ("Submittal Log", "Logs"),
    "daily": ("Daily Report Log", "Logs"),
    "safety": ("Safety / Incident Log", "Logs"),
    "contracts": ("Contracts & Signatures", "Contracts"),
    "financials": ("Financial Statements", "Finance"),
}


def catalog() -> list[dict[str, str]]:
    return [{"id": k, "name": n, "group": g} for k, (n, g) in REPORTS.items()]


def _money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.0f}"
    except (TypeError, ValueError):
        return "$0"


class Report:
    """Neutral report structure → rendered to PDF or Excel."""
    def __init__(self, title: str, subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.kpis: list[tuple[str, str]] = []
        self.tables: list[dict[str, Any]] = []   # {name, headers:[str], rows:[[..]]}
        self.charts: list[dict[str, Any]] = []   # {kind:'bar'|'line', name, categories, series:[{name,values}]}

    def kpi(self, label: str, value: Any):
        self.kpis.append((label, str(value)))
        return self

    def table(self, name: str, headers: list[str], rows: list[list[Any]]):
        self.tables.append({"name": name, "headers": headers, "rows": rows})
        return self

    def chart(self, kind: str, name: str, categories: list[str], series: list[dict[str, Any]]):
        """A bar or line chart for the PDF (the Excel keeps the underlying table for re-charting)."""
        self.charts.append({"kind": kind, "name": name, "categories": categories, "series": series})
        return self


def _records(db: Session, key: str, pid: str) -> list[dict]:
    return me.list_records(db, key, pid, limit=100000) if key in me.TABLES else []


# --- per-report builders -----------------------------------------------------
def _executive(db: Session, pid: str, name: str) -> Report:
    s = px.summary(db, pid)
    sch, bud = s["schedule"], s["budget"]
    r = Report("Executive Summary", name)
    r.kpi("Overall status", s["status"].replace("_", " ").title())
    r.kpi("SPI", sch["spi"] if sch["spi"] is not None else "—")
    r.kpi("% complete", f"{sch['pct_complete']}%")
    r.kpi("EAC", _money(bud["eac"]))
    r.kpi("Variance at completion", _money(bud["variance_at_completion"]))
    r.kpi("Committed", f"{bud['committed_pct']}%")
    r.kpi("Spent", f"{bud['spent_pct']}%")
    open_counts = []
    for key, label in [("rfi", "Open RFIs"), ("submittal", "Open submittals"), ("cor", "Open change orders")]:
        recs = _records(db, key, pid)
        open_n = sum(1 for x in recs if x["workflow_state"] not in ("closed", "executed", "approved", "rejected", "answered", "void"))
        open_counts.append([label, open_n, len(recs)])
    incidents = _records(db, "incident", pid)
    open_counts.append(["Safety incidents", len(incidents), len(incidents)])
    r.table("Open items", ["Item", "Open", "Total"], open_counts)
    al = px.alerts(db, pid)
    r.kpi("Schedule alerts", f"{al['counts']['high']} high / {al['counts']['medium']} med")
    if al["alerts"]:
        r.table("Predictive schedule alerts", ["Level", "Alert", "Detail"],
                [[a["level"].upper(), a["title"], a.get("detail", "")] for a in al["alerts"][:25]])
    return r


def _cost(db: Session, pid: str, name: str) -> Report:
    b = pb.gmp_budget(db, pid)
    r = Report("Cost Report", name)
    t = b["totals"]
    r.kpi("GMP (computed)", _money(b["gmp"]["computed"]))
    r.kpi("Revised GMP", _money(b["gmp"]["revised"]))
    r.kpi("EAC", _money(t.get("eac", t["forecast"])))
    r.kpi("Variance", _money(t["variance"]))
    rows = [[c["name"], _money(c["budget"]), _money(c["committed"]), _money(c["actual"]),
             _money(c.get("forecast", c.get("eac"))), _money(c.get("variance"))]
            for c in b["categories"]]
    rows.append(["TOTAL", _money(t["budget"]), _money(t["committed"]), _money(t["actual"]),
                 _money(t.get("eac", t["forecast"])), _money(t["variance"])])
    r.table("Cost by category", ["Category", "Budget", "Committed", "Actual", "Forecast/EAC", "Variance"], rows)
    cats = [c for c in b["categories"] if (c.get("budget") or 0) > 0]
    if cats:
        r.chart("bar", "Budget vs committed vs actual vs EAC", [c["name"] for c in cats], [
            {"name": "Budget", "values": [round(c["budget"]) for c in cats]},
            {"name": "Committed", "values": [round(c.get("committed", 0)) for c in cats]},
            {"name": "Actual", "values": [round(c.get("actual", 0)) for c in cats]},
            {"name": "EAC", "values": [round(c.get("eac", c.get("forecast", c["budget"]))) for c in cats]},
        ])
    return r


def _evm(db: Session, pid: str, name: str) -> Report:
    s = px.summary(db, pid)
    cash = pb.cashflow(db, pid)
    r = Report("EVM / S-Curve", name)
    r.kpi("SPI", s["schedule"]["spi"] if s["schedule"]["spi"] is not None else "—")
    r.kpi("% complete", f"{s['schedule']['pct_complete']}%")
    r.kpi("EAC", _money(s["budget"]["eac"]))
    r.kpi("Cash to date", _money(next((b["cumulative"] for b in reversed(cash["series"]) if b.get("cumulative")), 0)))
    rows = [[b["month"], _money(b["cost"]), _money(b["cumulative"]), f"{b['pct']}%"] for b in cash["series"]]
    r.table("Cash-flow S-curve", ["Month", "Period", "Cumulative", "% of total"], rows)
    if len(cash["series"]) > 1:
        r.chart("line", "Cash-flow S-curve (cumulative)", [b["month"] for b in cash["series"]],
                [{"name": "Cumulative cost", "values": [round(b["cumulative"]) for b in cash["series"]]}])
    return r


def _log(db: Session, pid: str, name: str, key: str, title: str, cols: list[tuple[str, str]]) -> Report:
    recs = _records(db, key, pid)
    r = Report(title, name)
    r.kpi("Records", len(recs))
    rows = []
    for rec in recs:
        d = rec.get("data") or {}
        row = [rec.get("ref", "")]
        for field, _ in cols:
            v = d.get(field, "")
            row.append(_money(v) if field in ("amount", "value") else str(v))
        row.append(rec.get("workflow_state", ""))
        rows.append(row)
    r.table(title, ["Ref"] + [label for _, label in cols] + ["Status"], rows)
    return r


def _contracts(db: Session, pid: str, name: str) -> Report:
    r = Report("Contracts & Signatures", name)
    rows = []
    for key, who in [("prime_contract", "name"), ("subcontract", "vendor"), ("cor", "subject")]:
        for rec in _records(db, key, pid):
            d = rec.get("data") or {}
            sigs = d.get("signatures") or []
            rows.append([key.replace("_", " "), rec.get("ref", ""), str(d.get(who, "")),
                         _money(d.get("value") or d.get("amount")), rec.get("workflow_state", ""),
                         ", ".join(f"{s.get('party')}" for s in sigs) or "—"])
    r.kpi("Contract records", len(rows))
    r.table("Contracts", ["Type", "Ref", "Party", "Value", "Status", "Signed by"], rows)
    return r


def _risk(db: Session, pid: str, name: str) -> Report:
    dg = px.risk_digest(db, pid)
    r = Report("Risk Digest", name)
    r.kpi("Headline", dg.get("headline") or "—")
    r.kpi("Risks flagged", len(dg.get("risks", [])))
    if dg.get("risks"):
        r.table("Prioritized risks", ["Level", "Risk"],
                [[str(x.get("level", "")).upper(), x.get("text", "")] for x in dg["risks"]])
    if dg["drivers"].get("top_alerts"):
        r.table("Top schedule alerts", ["Level", "Alert", "Detail"],
                [[a["level"].upper(), a["title"], a.get("detail", "")] for a in dg["drivers"]["top_alerts"]])
    return r


def _financials(db: Session, pid: str, name: str) -> Report:
    """Income statement · balance sheet · cash flow · tax, from the project's latest proforma scenario."""
    from . import financials
    from .models import Scenario
    from .proforma.solve import solve
    r = Report("Financial Statements", name)
    s = (db.query(Scenario).filter(Scenario.project_id == pid)
         .order_by(Scenario.created_at.desc()).first())
    if not s:
        r.kpi("Status", "No saved proforma scenario — solve & save one in Finance first.")
        return r
    f = financials.statements(s.result or solve(s.assumptions), s.assumptions)
    a = f["assumptions"]
    r.kpi("Income-tax rate", f"{a['income_tax_rate'] * 100:.0f}%")
    r.kpi("Depreciation life", f"{a['depreciation_years']:.1f} yrs")
    r.kpi("After-tax equity IRR", f"{(f['after_tax_returns']['equity_irr'] or 0) * 100:.1f}%")
    r.table("Income statement (stabilized year)", ["Line", "Amount"],
            [[ln["label"], _money(ln["amount"])] for ln in f["income_statement"]["lines"]])
    r.table("Operating summary by year",
            ["Year", "NOI", "Interest", "Depreciation", "Taxable", "Income tax", "Net income"],
            [[y["year"], _money(y["noi"]), _money(y["interest"]), _money(y["depreciation"]),
              _money(y["taxable_income"]), _money(y["income_tax"]), _money(y["net_income"])]
             for y in f["income_statement"]["by_year"]])
    by = f["income_statement"]["by_year"]
    if len(by) > 1:
        r.chart("line", "NOI vs net income by year", [f"Yr {y['year']}" for y in by], [
            {"name": "NOI", "values": [round(y["noi"]) for y in by]},
            {"name": "Net income", "values": [round(y["net_income"]) for y in by]},
        ])
    bs = f["balance_sheet"]["by_year"][-1]
    r.table(f"Balance sheet (year {bs['year']})", ["Account", "Amount"], [
        ["Land", _money(bs["assets"]["land"])],
        ["Improvements (net of depreciation)", _money(bs["assets"]["improvements_net"])],
        ["Capitalized financing", _money(bs["assets"]["capitalized_financing"])],
        ["Total assets", _money(bs["assets"]["total"])],
        ["Loan", _money(bs["liabilities"]["total"])],
        ["Paid-in capital", _money(bs["equity"]["paid_in_capital"])],
        ["Retained earnings", _money(bs["equity"]["retained_earnings"])],
        ["Total liabilities + equity", _money(bs["liabilities"]["total"] + bs["equity"]["total"])],
    ])
    cfs = f["cash_flow_statement"]
    r.table("Cash-flow statement", ["Section", "Amount"], [
        ["Operating (after-tax)", _money(cfs["operating"]["after_tax_operating_cash_flow"])],
        ["Investing", _money(cfs["investing"]["total"])],
        ["Financing", _money(cfs["financing"]["total"])],
        ["Net change in cash", _money(cfs["net_change_in_cash"])],
    ])
    st = f["tax"]["sale"]
    r.table("Tax at sale", ["Item", "Amount"], [
        ["Net sale price", _money(st["net_sale"])],
        ["Adjusted basis", _money(st["adjusted_basis"])],
        ["Total gain", _money(st["total_gain"])],
        ["Depreciation recapture tax (25%)", _money(st["recapture_tax"])],
        ["Capital-gains tax (+NIIT)", _money(st["capital_gains_tax"])],
        ["Total sale tax", _money(st["total_sale_tax"])],
    ])
    return r


def build(db: Session, pid: str, report: str) -> Report:
    p = db.get(Project, pid)
    name = (p.name if p else pid)
    if report == "executive":
        return _executive(db, pid, name)
    if report == "risk":
        return _risk(db, pid, name)
    if report == "cost":
        return _cost(db, pid, name)
    if report == "evm":
        return _evm(db, pid, name)
    if report == "contracts":
        return _contracts(db, pid, name)
    if report == "financials":
        return _financials(db, pid, name)
    logs = {
        "change_orders": ("cor", "Change Order Log", [("subject", "Subject"), ("amount", "Amount"), ("reason", "Reason")]),
        "rfi": ("rfi", "RFI Log", [("subject", "Subject"), ("discipline", "Discipline"), ("cost_impact", "Cost impact")]),
        "submittals": ("submittal", "Submittal Log", [("title", "Title"), ("spec_section", "Spec"), ("type", "Type")]),
        "daily": ("daily_report", "Daily Report Log", [("report_date", "Date"), ("weather", "Weather")]),
        "safety": ("incident", "Safety / Incident Log", [("subject", "Subject"), ("classification", "Class"), ("severity", "Severity")]),
    }
    if report in logs:
        key, title, cols = logs[report]
        return _log(db, pid, name, key, title, cols)
    raise ValueError(f"unknown report {report!r}")


# --- renderers ---------------------------------------------------------------
def to_pdf(rep: Report) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
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
