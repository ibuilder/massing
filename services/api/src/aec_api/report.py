"""Project status report (PDF) — a one-document executive snapshot aggregating the cross-module
dashboard (KPIs, cost, open items by module, ball-in-court). Built with reportlab (already a dep)."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


def _money(v: Any) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "-"


def project_status_pdf(db: Session, pid: str, project_name: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from . import dashboard

    d = dashboard.build(db, pid, "GC")          # GC party = whole-project view
    kp = d.get("kpis", {})
    cost = d.get("cost")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin = 40
    y = h - 50

    def newpage():
        nonlocal y
        c.showPage()
        y = h - 50

    def heading(text: str):
        nonlocal y
        if y < 90:
            newpage()
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, y, text)
        y -= 6
        c.setStrokeColor(colors.grey); c.line(margin, y, w - margin, y); c.setStrokeColor(colors.black)
        y -= 16

    def row(label: str, value: str, indent: int = 0):
        nonlocal y
        if y < 60:
            newpage()
        c.setFont("Helvetica", 10)
        c.drawString(margin + indent, y, label)
        c.drawRightString(w - margin, y, value)
        y -= 15

    # --- title block ---
    c.setFont("Helvetica-Bold", 18); c.drawString(margin, y, "Project Status Report"); y -= 22
    c.setFont("Helvetica", 11); c.drawString(margin, y, project_name or pid)
    c.drawRightString(w - margin, y, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")); y -= 8
    c.setStrokeColor(colors.black); c.line(margin, y, w - margin, y); y -= 24

    # --- KPIs ---
    heading("Summary")
    row("Total records", str(kp.get("total_records", 0)))
    row("Overdue items", str(kp.get("overdue", 0)))
    row("Open RFIs", str(kp.get("open_rfis", 0)))
    row("Pending change orders", str(kp.get("pending_change_orders", 0)))
    row("Open coordination/issues", str(kp.get("open_issues", 0)))
    row("Open quality (NCR/deficiency/insp.)", str(kp.get("open_quality", 0)))
    row("Open safety", str(kp.get("open_safety", 0)))
    row("Open punchlist", str(kp.get("open_punchlist", 0)))
    y -= 10

    # --- cost snapshot ---
    if cost:
        heading("Cost snapshot")
        row("Revised budget", _money(cost.get("budget")))
        row("Committed", _money(cost.get("committed")))
        row("Actual to date", _money(cost.get("actual")))
        row("Forecast at completion", _money(cost.get("forecast")))
        if cost.get("projected_over_under") is not None:
            row("Projected over / (under)", _money(cost.get("projected_over_under")))
        y -= 10

    # --- open items by module ---
    heading("Open items by module")
    by_module = [m for m in d.get("by_module", []) if m.get("count")]
    for m in by_module[:30]:
        states = m.get("by_state", {})
        detail = ", ".join(f"{n} {s}" for s, n in sorted(states.items(), key=lambda kv: -kv[1])[:4])
        row(f"{m['name']} ({m['count']})", detail or "-")
    y -= 10

    # --- ball-in-court action items ---
    actions = d.get("action_items", [])
    heading(f"Action items — ball in court ({len(actions)})")
    if not actions:
        row("None outstanding", "")
    for a in actions[:25]:
        row(f"{a['ref']} — {(a.get('title') or '')[:48]}", a.get("state", ""), indent=8)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, 30, "AEC BIM Platform — generated from live project data")
    c.showPage()
    c.save()
    return buf.getvalue()


def _memo_proforma(db: Session, pid: str):
    """Returns (result, source) for the memo: the project's most recent solved scenario when one
    exists (the real underwriting), else None — the memo then shows the capital stack from the
    cost budget alone (returns need operating assumptions, which a scenario carries)."""
    from .models import Scenario
    s = (db.query(Scenario).filter(Scenario.project_id == pid)
         .order_by(Scenario.created_at.desc()).first())
    if s and s.result:
        return s.result, s.name
    return None, None


def _pct(v) -> str:
    return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "n/a"


def investment_memo_pdf(db: Session, pid: str, project_name: str) -> bytes:
    """A confidential investment memorandum composed from live project data: executive summary,
    Sources & Uses, the hard/soft cost budget, returns, and a risk read. Returns scenario figures
    when the project has a solved proforma; otherwise the capital stack from the cost budget."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from . import ai, dashboard, dev_budget as dvb
    from .models import Project

    p = db.get(Project, pid)
    budget = (p.dev_budget if p and p.dev_budget else dvb.starter_budget())
    bs = dvb.summarize(budget)
    result, scenario_name = _memo_proforma(db, pid)
    su = (result or {}).get("sources_uses", {})
    ret = (result or {}).get("returns", {})
    d = dashboard.build(db, pid, "GC")
    risk = ai.risk_summary(d.get("kpis", {}), d.get("cost"))

    total_uses = su.get("total_uses") or bs["grand_total"]
    loan = su.get("loan_amount")
    equity = su.get("equity")
    if loan is None:                       # no scenario → size a default stack off the budget
        loan = round(total_uses * 0.65); equity = round(total_uses - loan)

    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=letter); w, h = letter
    margin = 40; y = h - 60

    def newpage():
        nonlocal y
        c.showPage(); y = h - 50

    def heading(text: str):
        nonlocal y
        if y < 110:
            newpage()
        c.setFont("Helvetica-Bold", 13); c.drawString(margin, y, text); y -= 6
        c.setStrokeColor(colors.grey); c.line(margin, y, w - margin, y); c.setStrokeColor(colors.black); y -= 16

    def row(label: str, value: str, indent: int = 0, bold: bool = False):
        nonlocal y
        if y < 60:
            newpage()
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(margin + indent, y, label[:70]); c.drawRightString(w - margin, y, value); y -= 15

    def para(text: str):
        nonlocal y
        c.setFont("Helvetica", 10)
        words = text.split(); line = ""
        for word in words:
            if c.stringWidth(line + " " + word, "Helvetica", 10) > w - 2 * margin:
                if y < 60:
                    newpage()
                c.drawString(margin, y, line); y -= 14; line = word
            else:
                line = (line + " " + word).strip()
        if line:
            if y < 60:
                newpage()
            c.drawString(margin, y, line); y -= 14

    # --- cover ---
    c.setFillColor(colors.HexColor("#16324f")); c.rect(0, h - 200, w, 200, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11); c.drawString(margin, h - 70, "CONFIDENTIAL INVESTMENT MEMORANDUM")
    c.setFont("Helvetica-Bold", 26); c.drawString(margin, h - 110, (project_name or pid)[:46])
    c.setFont("Helvetica", 12); c.drawString(margin, h - 134, "Real-Estate Development Opportunity")
    c.setFont("Helvetica", 10); c.drawString(margin, h - 170, datetime.now(timezone.utc).strftime("Prepared %B %d, %Y"))
    c.setFillColor(colors.black); y = h - 240

    heading("Executive Summary")
    if result:
        para(f"This memorandum presents the development of {project_name}. On total project costs "
             f"of {_money(total_uses)}, the deal is underwritten to a {_pct(ret.get('equity_irr'))} "
             f"equity IRR and a {ret.get('equity_multiple', 'n/a')}x equity multiple"
             + (f" (yield-on-cost {_pct(ret.get('yield_on_cost'))})." if ret.get('yield_on_cost') is not None else "."))
    else:
        para(f"This memorandum presents the development of {project_name}. Total project costs are "
             f"{_money(total_uses)}, funded with {_money(loan)} of senior debt and {_money(equity)} "
             f"of equity. Save a proforma scenario to include underwritten returns (IRR, multiple, "
             f"yield-on-cost) in this section.")
    y -= 6
    row("Total project cost", _money(total_uses), bold=True)
    row("Equity IRR", _pct(ret.get("equity_irr")) if result else "—")
    row("Equity multiple", f"{ret.get('equity_multiple', '—')}x" if result else "—")
    row("Hard / soft split", f"{bs['hard_pct'] * 100:.0f}% / {bs['soft_pct'] * 100:.0f}%")
    y -= 8

    heading("Sources & Uses")
    row("USES", "", bold=True)
    for cat, lbl in (("acquisition", "Acquisition"), ("hard", "Hard costs"), ("soft", "Soft costs")):
        cc = bs["categories"][cat]
        if cc["subtotal"]:
            row(lbl, _money(cc["subtotal"]), indent=8)
        if cc["contingency"]:
            row(f"{lbl} contingency ({cc['contingency_pct'] * 100:.0f}%)", _money(cc["contingency"]), indent=16)
    row("Total uses", _money(total_uses), indent=8, bold=True)
    y -= 4
    row("SOURCES", "", bold=True)
    row(f"Senior debt ({_pct(loan / total_uses) if total_uses else 'n/a'} LTC)", _money(loan), indent=8)
    row("Equity", _money(equity), indent=8)
    row("Total sources", _money((loan or 0) + (equity or 0)), indent=8, bold=True)
    y -= 8

    heading("Development Cost Budget")
    for cat, lbl in (("acquisition", "Acquisition"), ("hard", "Hard costs"), ("soft", "Soft costs")):
        cc = bs["categories"][cat]
        if not cc["lines"]:
            continue
        row(lbl, _money(cc["total"]), bold=True)
        for ln in cc["lines"][:12]:
            qty = ln["quantity"]
            desc = ln["description"] + (f"  ({qty:g} × {_money(ln['unit_cost'])})" if qty and qty != 1 else "")
            row(desc, _money(ln["total"]), indent=12)
    y -= 8

    if result:
        heading("Returns")
        row("Project IRR", _pct(ret.get("project_irr")))
        row("Equity IRR", _pct(ret.get("equity_irr")))
        row("Equity multiple", f"{ret.get('equity_multiple', 'n/a')}x")
        if ret.get("npv") is not None:
            row("NPV", _money(ret.get("npv")))
        if ret.get("yield_on_cost") is not None:
            row("Yield on cost", _pct(ret.get("yield_on_cost")))
        y -= 8

    heading("Risk Summary")
    para(risk.get("headline", ""))
    for r in risk.get("risks", [])[:8]:
        row(f"[{r['level'].upper()}] {r['text']}"[:78], "", indent=8)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, 30, "AEC BIM Platform — generated from live project data · Confidential")
    c.showPage(); c.save()
    return buf.getvalue()


def module_log_pdf(db: Session, pid: str, key: str, project_name: str) -> bytes:
    """A printable register (log) of one module's records — ref, title, status, assignee, date.
    Drives the RFI log, submittal log, change-order log, etc. from the same engine."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from . import modules as me

    mod = me.get_module(key)
    recs = me.list_records(db, key, pid, limit=100000)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin = 40
    y = h - 50
    cols = [(margin, "Ref"), (margin + 80, "Title"), (w - 200, "Status"), (w - 110, "Assignee")]

    def header_row():
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        for x, label in cols:
            c.drawString(x, y, label)
        y -= 4
        c.setStrokeColor(colors.grey); c.line(margin, y, w - margin, y); c.setStrokeColor(colors.black)
        y -= 14

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, f"{mod.get('title', key)} Log"); y -= 20
    c.setFont("Helvetica", 10); c.drawString(margin, y, project_name or pid)
    c.drawRightString(w - margin, y, f"{len(recs)} records"); y -= 16
    header_row()
    c.setFont("Helvetica", 9)
    for r in recs:
        if y < 50:
            c.showPage(); y = h - 50; header_row(); c.setFont("Helvetica", 9)
        c.drawString(cols[0][0], y, str(r.get("ref") or "")[:11])
        c.drawString(cols[1][0], y, str(r.get("title") or "")[:62])
        c.drawString(cols[2][0], y, str(r.get("workflow_state") or "")[:14])
        c.drawString(cols[3][0], y, str(r.get("assignee") or "")[:14])
        y -= 14
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, 30, "AEC BIM Platform — generated from live project data")
    c.showPage(); c.save()
    return buf.getvalue()
