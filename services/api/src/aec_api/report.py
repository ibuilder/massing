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


def payapp_pdf(db: Session, pid: str, project_name: str, app_no: int = 1,
               period: str | None = None, release_retainage: bool = False) -> bytes:
    """AIA-style Application & Certificate for Payment (G702) + Continuation Sheet (G703) as a PDF —
    the document the owner signs each draw. Drawn from the same SOV the GMP budget seeds."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from . import cost as cost_engine

    g702 = cost_engine.g702(db, pid, app_no=app_no, period=period, release_retainage=release_retainage)
    g703 = cost_engine.g703(db, pid)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin = 50

    # --- page 1: G702 certificate ----------------------------------------------
    y = h - 50
    c.setFont("Helvetica-Bold", 16); c.drawString(margin, y, "Application & Certificate for Payment"); y -= 16
    c.setFont("Helvetica", 9); c.drawString(margin, y, "AIA G702 — generated from live project data"); y -= 22
    c.setFont("Helvetica-Bold", 11); c.drawString(margin, y, project_name or pid); y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"Application No: {app_no}")
    c.drawString(margin + 200, y, f"Period: {period or '—'}")
    c.drawString(margin + 360, y, f"Retainage released: {'Yes' if release_retainage else 'No'}"); y -= 22

    rows = [
        ("1. Original Contract Sum", g702["line1_original_contract_sum"]),
        ("2. Net Change by Change Orders", g702["line2_net_change_orders"]),
        ("3. Contract Sum to Date", g702["line3_contract_sum_to_date"]),
        ("4. Total Completed & Stored to Date", g702["line4_total_completed_stored"]),
        ("5. Retainage", g702["line5_retainage"]),
        ("6. Total Earned Less Retainage", g702["line6_total_earned_less_retainage"]),
        ("7. Less Previous Certificates for Payment", g702["line7_less_previous_certificates"]),
        ("8. CURRENT PAYMENT DUE", g702["line8_current_payment_due"]),
        ("9. Balance to Finish, Incl. Retainage", g702["line9_balance_to_finish_incl_retainage"]),
    ]
    for label, val in rows:
        bold = label.startswith("8.")
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawString(margin, y, label)
        c.drawRightString(w - margin, y, _money(val))
        y -= 18
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, 40, "Certified from the project Schedule of Values (G703) — see continuation sheet.")
    c.showPage()

    # --- page 2: G703 continuation sheet ---------------------------------------
    y = h - 50
    c.setFont("Helvetica-Bold", 14); c.drawString(margin, y, "Continuation Sheet (G703)"); y -= 20
    cols = [(margin, "Item"), (margin + 45, "Description"), (margin + 250, "Scheduled"),
            (margin + 330, "Completed"), (margin + 410, "%"), (margin + 445, "Balance"), (margin + 510, "Retain.")]
    c.setFont("Helvetica-Bold", 8)
    for x, lbl in cols:
        c.drawString(x, y, lbl)
    y -= 4; c.line(margin, y, w - margin, y); y -= 12
    c.setFont("Helvetica", 8)
    for ln in g703["lines"]:
        if y < 60:
            c.showPage(); y = h - 50; c.setFont("Helvetica", 8)
        c.drawString(cols[0][0], y, str(ln.get("item_no") or "")[:6])
        c.drawString(cols[1][0], y, str(ln.get("description") or "")[:34])
        c.drawRightString(cols[2][0] + 55, y, _money(ln["scheduled_value"]))
        c.drawRightString(cols[3][0] + 55, y, _money(ln["total_completed_stored"]))
        c.drawRightString(cols[4][0] + 25, y, f"{ln['percent']:.0f}%")
        c.drawRightString(cols[5][0] + 55, y, _money(ln["balance_to_finish"]))
        c.drawRightString(cols[6][0] + 40, y, _money(ln["retainage"]))
        y -= 13
    t = g703["totals"]; y -= 4; c.line(margin, y, w - margin, y); y -= 13
    c.setFont("Helvetica-Bold", 8)
    c.drawString(cols[1][0], y, "TOTALS")
    c.drawRightString(cols[2][0] + 55, y, _money(t["scheduled"]))
    c.drawRightString(cols[3][0] + 55, y, _money(t["completed"]))
    c.drawRightString(cols[5][0] + 55, y, _money(t["balance"]))
    c.drawRightString(cols[6][0] + 40, y, _money(t["retainage"]))
    c.showPage()
    c.save()
    return buf.getvalue()


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


def _project_photos(db: Session, pid: str, limit: int = 3) -> list[bytes]:
    """Image attachments on the project's topics (pins/RFIs), for the deck's site photos. Best-effort:
    any read/storage failure just yields fewer photos rather than breaking the deck."""
    out: list[bytes] = []
    try:
        from . import storage
        from .models import Attachment, Topic
        q = (db.query(Attachment).join(Topic, Attachment.topic_id == Topic.id)
             .filter(Topic.project_id == pid)
             .filter((Attachment.kind == "photo") | (Attachment.content_type.like("image/%")))
             .limit(limit))
        for a in q.all():
            try:
                out.append(storage.get(a.storage_key))
            except Exception:                # noqa: BLE001 — skip a missing blob
                continue
    except Exception:                        # noqa: BLE001 — no attachments table / join issue
        return []
    return out


def investment_deck_pdf(db: Session, pid: str, project_name: str) -> bytes:
    """A pitch-deck variant of the investment memo — landscape slides with big numbers (title · the
    deal in numbers · **market & positioning** · Sources & Uses · **development timeline** · returns &
    the ask). Same live data as the memo; site photos pulled from project attachments when present."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfgen import canvas

    from . import ai, benchmarks as bm, dashboard, dev_budget as dvb
    from .models import Project

    p = db.get(Project, pid)
    bs = dvb.summarize(p.dev_budget if p and p.dev_budget else dvb.starter_budget())
    result, _ = _memo_proforma(db, pid)
    su = (result or {}).get("sources_uses", {})
    ret = (result or {}).get("returns", {})
    risk = ai.risk_summary(dashboard.build(db, pid, "GC").get("kpis", {}), None)
    bands = bm.all_benchmarks()["benchmarks"]
    photos = _project_photos(db, pid)
    total_uses = su.get("total_uses") or bs["grand_total"]
    loan = su.get("loan_amount") or round(total_uses * 0.65)
    equity = su.get("equity") or round(total_uses - loan)

    buf = io.BytesIO()
    W, H = landscape(letter)
    c = canvas.Canvas(buf, pagesize=(W, H))
    navy = colors.HexColor("#16324f")
    accent = colors.HexColor("#4a8cff")
    m = 54

    def slide(title: str):
        c.setFillColor(navy); c.rect(0, H - 64, W, 64, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 20); c.drawString(m, H - 44, title)
        c.setFillColor(colors.black)

    def kpi(x: float, y: float, value: str, label: str):
        c.setFillColor(accent); c.setFont("Helvetica-Bold", 30); c.drawString(x, y, value)
        c.setFillColor(colors.HexColor("#666")); c.setFont("Helvetica", 12); c.drawString(x, y - 18, label)
        c.setFillColor(colors.black)

    # 1 — title
    c.setFillColor(navy); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 13)
    c.drawString(m, H - 120, "CONFIDENTIAL INVESTMENT OPPORTUNITY")
    c.setFont("Helvetica-Bold", 40); c.drawString(m, H - 175, (project_name or pid)[:42])
    c.setFont("Helvetica", 16); c.drawString(m, H - 210, "Real-estate development — equity offering")
    c.setFont("Helvetica", 11); c.drawString(m, 50, datetime.now(timezone.utc).strftime("Prepared %B %d, %Y · generated from live project data"))
    if photos:                               # a site photo on the cover, if the project has one
        try:
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(io.BytesIO(photos[0])), W - 360, 90, 300, H - 280,
                        preserveAspectRatio=True, anchor="ne", mask="auto")
        except Exception:                    # noqa: BLE001 — a bad image must never break the deck
            pass
    c.showPage()

    # 2 — the deal in numbers
    slide("The deal in numbers")
    kpi(m, H - 160, _money(total_uses), "Total project cost")
    kpi(m + 300, H - 160, _money(equity), "Equity required")
    kpi(m, H - 270, _pct(ret.get("equity_irr")) if result else "—", "Equity IRR")
    kpi(m + 300, H - 270, f"{ret.get('equity_multiple', '—')}x" if result else "—", "Equity multiple")
    kpi(m, H - 380, _pct(ret.get("yield_on_cost")) if result else "—", "Yield on cost")
    kpi(m + 300, H - 380, f"{bs['hard_pct'] * 100:.0f}% / {bs['soft_pct'] * 100:.0f}%", "Hard / soft split")
    if not result:
        c.setFont("Helvetica-Oblique", 11); c.setFillColor(colors.HexColor("#999"))
        c.drawString(m, 50, "Save a proforma scenario to populate returns.")
    c.showPage()

    # 2b — market & positioning (the deal's figures against conceptual market bands)
    slide("Market & positioning")
    c.setFont("Helvetica", 12); c.setFillColor(colors.HexColor("#555"))
    c.drawString(m, H - 92, "Where this deal sits against conceptual underwriting ranges "
                 "(validate against local comps).")
    c.setFillColor(colors.black)

    def band_row(y: float, label: str, val: float | None, lo: float, hi: float, fmt):
        c.setFont("Helvetica-Bold", 13); c.drawString(m, y, label)
        bx, bw = m + 230, 360
        c.setFillColor(colors.HexColor("#e6edf6")); c.rect(bx, y - 4, bw, 14, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#999")); c.setFont("Helvetica", 9)
        c.drawString(bx, y - 18, fmt(lo)); c.drawRightString(bx + bw, y - 18, fmt(hi))
        if val is not None and hi > lo:
            t = max(0.0, min(1.0, (val - lo) / (hi - lo)))
            mx = bx + t * bw
            c.setFillColor(accent); c.circle(mx, y + 3, 6, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 11); c.drawCentredString(mx, y + 16, fmt(val))
        c.setFillColor(colors.black)

    pct = lambda v: f"{v * 100:.1f}%"
    y = H - 150
    band_row(y, "Yield on cost vs cap", ret.get("yield_on_cost"),
             bands["cap_rate"]["stabilized"][0], bands["cap_rate"]["value_add"][1], pct); y -= 70
    band_row(y, "Equity IRR", ret.get("equity_irr"),
             bands["equity_irr"]["typical"][0], bands["equity_irr"]["typical"][1], pct); y -= 70
    band_row(y, "Soft cost (% of hard)", bs.get("soft_pct"),
             bands["soft_cost_pct"]["range"][0], bands["soft_cost_pct"]["range"][1], pct); y -= 70
    c.setFont("Helvetica-Oblique", 9); c.setFillColor(colors.HexColor("#999"))
    c.drawString(m, 34, bm.all_benchmarks()["disclaimer"])
    c.setFillColor(colors.black)
    c.showPage()

    # 3 — sources & uses
    slide("Sources & Uses")
    y = H - 110; c.setFont("Helvetica-Bold", 14); c.drawString(m, y + 6, "USES"); c.drawString(W / 2 + m / 2, y + 6, "SOURCES")
    c.setFont("Helvetica", 13)
    uses = [("Acquisition", bs["categories"]["acquisition"]["subtotal"]), ("Hard costs", bs["categories"]["hard"]["subtotal"]),
            ("Soft costs", bs["categories"]["soft"]["subtotal"]), ("Contingency", sum(bs["categories"][x]["contingency"] for x in bs["categories"]))]
    for label, amt in uses:
        if amt:
            c.drawString(m, y, label); c.drawRightString(W / 2 - m / 2, y, _money(amt)); y -= 22
    c.setFont("Helvetica-Bold", 13); c.drawString(m, y, "Total uses"); c.drawRightString(W / 2 - m / 2, y, _money(total_uses))
    y = H - 110 - 22; c.setFont("Helvetica", 13)
    for label, amt in [(f"Senior debt ({_pct(loan / total_uses) if total_uses else 'n/a'})", loan), ("Equity", equity)]:
        c.drawString(W / 2 + m / 2, y, label); c.drawRightString(W - m, y, _money(amt)); y -= 22
    c.showPage()

    # 3b — development timeline (indicative phases drawn as a gantt-style bar)
    slide("Development timeline")
    timing = (result or {}).get("timing", {}) if isinstance(result, dict) else {}
    constr = int(timing.get("construction_months") or 18)
    lease = int(timing.get("leaseup_months") or 12)
    phases = [("Predevelopment", 6, colors.HexColor("#8aa0b8")),
              ("Construction", constr, accent),
              ("Lease-up", lease, colors.HexColor("#46b27a")),
              ("Stabilization", 12, colors.HexColor("#caa23a")),
              ("Sale / exit", 3, navy)]
    total = sum(d for _, d, _ in phases)
    x0, x1 = m, W - m
    span = x1 - x0
    bx = x0; barY = H - 220
    c.setFont("Helvetica", 11)
    for name, dur, col in phases:
        bw = span * dur / total
        c.setFillColor(col); c.rect(bx, barY, bw - 3, 46, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 10)
        if bw > 60:
            c.drawString(bx + 6, barY + 26, name); c.drawString(bx + 6, barY + 10, f"{dur} mo")
        bx += bw
    # month axis
    c.setFillColor(colors.HexColor("#999")); c.setFont("Helvetica", 9)
    cum = 0
    for _, dur, _ in phases:
        c.drawString(x0 + span * cum / total, barY - 16, f"M{cum}")
        cum += dur
    c.drawRightString(x1, barY - 16, f"M{total}")
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 14)
    c.drawString(m, barY - 70, f"~{total} months from start to exit "
                 f"({constr}-month construction, {lease}-month lease-up).")
    c.setFont("Helvetica-Oblique", 9); c.setFillColor(colors.HexColor("#999"))
    c.drawString(m, 34, "Indicative phasing; construction/lease-up from the saved scenario where set.")
    c.setFillColor(colors.black)
    c.showPage()

    # 4 — returns + the ask
    slide("Returns & the ask")
    if result:
        kpi(m, H - 160, _pct(ret.get("project_irr")), "Project IRR")
        kpi(m + 300, H - 160, _pct(ret.get("equity_irr")), "Equity IRR")
        kpi(m, H - 270, f"{ret.get('equity_multiple', '—')}x", "Equity multiple")
        kpi(m + 300, H - 270, _money(ret.get("npv")), "NPV")
    c.setFont("Helvetica-Bold", 16); c.setFillColor(navy)
    c.drawString(m, H - 360, f"The ask: {_money(equity)} of equity for a {_money(total_uses)} project.")
    c.setFillColor(colors.black); c.setFont("Helvetica", 12); ry = H - 400
    c.drawString(m, ry, "Key risks:"); ry -= 20
    for r in risk.get("risks", [])[:4]:
        c.drawString(m + 12, ry, f"• [{r['level'].upper()}] {r['text']}"[:110]); ry -= 18
    c.setFont("Helvetica-Oblique", 8); c.drawString(m, 30, "AEC BIM Platform — generated from live project data · Confidential")
    c.showPage()
    c.save()
    return buf.getvalue()


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
