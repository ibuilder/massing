"""Certified payroll (US DOL WH-347) — aggregates `timesheet` records x `labor_rate` rates into a
weekly certified-payroll report for Davis-Bacon / prevailing-wage public works. Straight time to 40h,
overtime at 1.5x beyond. Pure over the record dicts so it's testable without a DB."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _rate_map(labor_rates: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in labor_rates:
        d = r.get("data") or r
        t = (d.get("trade") or "").strip().lower()
        if t:
            out[t] = _num(d.get("rate"))
    return out


def wh347(timesheets: list[dict], labor_rates: list[dict], week_ending: date,
          prevailing: dict[str, float] | None = None) -> dict[str, Any]:
    """Weekly certified payroll for the 7 days ending `week_ending`. `prevailing`: optional
    {trade: min wage} to flag underpaid classifications."""
    days = [week_ending - timedelta(days=i) for i in range(6, -1, -1)]
    day_set = set(days)
    rates = _rate_map(labor_rates)
    prevailing = {k.lower(): v for k, v in (prevailing or {}).items()}
    workers: dict[str, dict] = {}
    for t in timesheets:
        d = t.get("data") or t
        dt = _parse(d.get("date"))
        if dt not in day_set:
            continue
        name = d.get("worker") or "?"
        trade = (d.get("trade") or "").strip()
        w = workers.setdefault(name, {"worker": name, "trade": trade,
                                      "daily": {dd.isoformat(): 0.0 for dd in days}, "total": 0.0})
        if trade and not w["trade"]:
            w["trade"] = trade
        hrs = _num(d.get("hours"))
        w["daily"][dt.isoformat()] += hrs
        w["total"] += hrs
    rows = []
    grand_gross = grand_hours = 0.0
    flags = []
    for w in workers.values():
        rate = rates.get((w["trade"] or "").lower(), 0.0)
        total = w["total"]
        ot = max(0.0, total - 40.0)
        st = total - ot
        gross = round(st * rate + ot * rate * 1.5, 2)
        grand_gross += gross
        grand_hours += total
        pw = prevailing.get((w["trade"] or "").lower())
        underpaid = pw is not None and rate < pw
        if underpaid:
            flags.append({"worker": w["worker"], "trade": w["trade"], "rate": rate, "prevailing": pw})
        rows.append({**w, "rate": rate, "straight_hours": round(st, 2), "ot_hours": round(ot, 2),
                     "gross": gross, "underpaid": underpaid})
    return {
        "week_ending": week_ending.isoformat(),
        "days": [dd.isoformat() for dd in days],
        "worker_count": len(rows),
        "total_hours": round(grand_hours, 2),
        "total_gross": round(grand_gross, 2),
        "prevailing_flags": flags,
        "rows": sorted(rows, key=lambda r: r["worker"]),
    }


def wh347_pdf(data: dict, project_name: str, contractor: str = "") -> bytes:
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    days = data["days"]
    head = ["Name", "Classification", "OT/ST"] + [d[5:] for d in days] + ["Total", "Rate", "Gross"]
    body = []
    for r in data["rows"]:
        body.append([r["worker"], r["trade"], f"{r['straight_hours']:.0f}/{r['ot_hours']:.0f}"]
                    + [f"{r['daily'][d]:.0f}" if r["daily"][d] else "" for d in days]
                    + [f"{r['total']:.0f}", f"${r['rate']:.2f}", f"${r['gross']:,.2f}"])
    if not body:
        body = [["(no hours this week)"] + [""] * (len(head) - 1)]
    rows = [head] + body + [["TOTAL", "", ""] + [""] * len(days)
                            + [f"{data['total_hours']:.0f}", "", f"${data['total_gross']:,.2f}"]]
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f4f6f8")]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), topMargin=0.6 * inch, title="WH-347 Certified Payroll")
    flow = [Paragraph("U.S. DOL Form WH-347 — Certified Payroll (Davis-Bacon)", ss["Title"]),
            Paragraph(f"Project: {project_name}{(' · Contractor: ' + contractor) if contractor else ''} · "
                      f"Week ending {data['week_ending']}", ss["Normal"]), Spacer(1, 10), t]
    if data["prevailing_flags"]:
        flow += [Spacer(1, 8), Paragraph("<b>Prevailing-wage flags:</b> " + ", ".join(
            f"{f['worker']} ({f['trade']}) ${f['rate']:.2f} &lt; ${f['prevailing']:.2f}"
            for f in data["prevailing_flags"]), ss["Normal"])]
    flow += [Spacer(1, 14), Paragraph("I certify that the above is correct and complete and that each "
             "laborer/mechanic has been paid not less than the applicable wage rates. (Statement of "
             "Compliance — signature on file.)", ss["Italic"])]
    doc.build(flow)
    return buf.getvalue()
