"""Cost / financial endpoints (GC portal): G703 SOV register, G702 pay-app certificate
(+ formatted PDF), and the Cost Summary roll-up."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import cost
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/cost/g703")
def g703(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return cost.g703(db, pid)


@router.get("/projects/{pid}/cost/g702")
def g702(pid: str, app_no: int = 1, period: str | None = None,
         db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return cost.g702(db, pid, app_no, period)


@router.get("/projects/{pid}/cost/summary")
def summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return cost.summary(db, pid)


@router.get("/projects/{pid}/cost/g702.pdf")
def g702_pdf(pid: str, app_no: int = 1, period: str = "", db: Session = Depends(get_db),
             _: str = Depends(require_role("viewer"))):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    p = db.get(Project, pid)
    g7 = cost.g702(db, pid, app_no, period)
    g3 = cost.g703(db, pid)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    def money(v):
        return f"${v:,.2f}"

    # --- G702 certificate ---
    c.setFont("Helvetica-Bold", 15)
    c.drawString(40, h - 50, "APPLICATION AND CERTIFICATE FOR PAYMENT")
    c.setFont("Helvetica", 9)
    c.drawString(40, h - 65, "AIA Document G702 (style)")
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 90, f"Project: {(p.name if p else '')}")
    c.drawString(40, h - 105, f"Application No: {app_no}    Period: {period or '-'}")
    rows = [
        ("1. Original Contract Sum", g7["line1_original_contract_sum"]),
        ("2. Net change by Change Orders", g7["line2_net_change_orders"]),
        ("3. Contract Sum to Date", g7["line3_contract_sum_to_date"]),
        ("4. Total Completed & Stored to Date", g7["line4_total_completed_stored"]),
        ("5. Retainage", g7["line5_retainage"]),
        ("6. Total Earned Less Retainage", g7["line6_total_earned_less_retainage"]),
        ("7. Less Previous Certificates for Payment", g7["line7_less_previous_certificates"]),
        ("8. CURRENT PAYMENT DUE", g7["line8_current_payment_due"]),
        ("9. Balance to Finish, Including Retainage", g7["line9_balance_to_finish_incl_retainage"]),
    ]
    y = h - 140
    for i, (label, val) in enumerate(rows):
        bold = label.startswith("8.")
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(50, y, label)
        c.drawRightString(w - 50, y, money(val))
        y -= 22
    c.line(40, y + 8, w - 40, y + 8)
    c.showPage()

    # --- G703 continuation sheet ---
    c.setFont("Helvetica-Bold", 13); c.drawString(40, h - 45, "CONTINUATION SHEET — Schedule of Values (G703)")
    cols = [(40, "Item"), (80, "Description"), (300, "Sched."), (370, "Compl.+Stored"),
            (470, "%"), (510, "Balance")]
    c.setFont("Helvetica-Bold", 8)
    yy = h - 70
    for x, label in cols:
        c.drawString(x, yy, label)
    c.line(40, yy - 3, w - 40, yy - 3)
    c.setFont("Helvetica", 8)
    yy -= 16
    for ln in g3["lines"]:
        if yy < 50:
            c.showPage(); yy = h - 50; c.setFont("Helvetica", 8)
        c.drawString(40, yy, str(ln["item_no"] or ""))
        c.drawString(80, yy, str(ln["description"] or "")[:34])
        c.drawRightString(360, yy, money(ln["scheduled_value"]))
        c.drawRightString(460, yy, money(ln["total_completed_stored"]))
        c.drawRightString(500, yy, f"{ln['percent']}%")
        c.drawRightString(w - 45, yy, money(ln["balance_to_finish"]))
        yy -= 14
    t = g3["totals"]
    c.setFont("Helvetica-Bold", 8)
    c.drawString(80, yy - 4, "TOTALS")
    c.drawRightString(360, yy - 4, money(t["scheduled"]))
    c.drawRightString(460, yy - 4, money(t["completed"]))
    c.drawRightString(w - 45, yy - 4, money(t["balance"]))
    c.showPage(); c.save()
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="G702-{app_no}.pdf"'})
