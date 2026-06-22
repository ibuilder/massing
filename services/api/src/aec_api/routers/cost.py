"""Cost / financial endpoints (GC portal): G703 SOV register, G702 pay-app certificate
(+ formatted PDF), and the Cost Summary roll-up."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from fastapi import Body

from .. import cost
from .. import modules as me
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


@router.get("/projects/{pid}/estimate/from-model")
def estimate_from_model(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Conceptual estimate from the IFC quantity takeoff × unit rates — priced line items by element
    class + a grand total (feeds the budget / proforma hard cost). 409 if no source IFC."""
    from ..deps import source_ifc_path
    from aec_data.qto import takeoff_file  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore
    from aec_data import spaces as sp  # type: ignore
    from .. import estimate as est
    path = source_ifc_path(db, pid)
    rows = takeoff_file(path, force_geometry=True)    # real geometry quantities (no cost map needed)
    # GFA (sf) from the model's spaces → a benchmark floor so a sparse model doesn't return a
    # misleadingly tiny number; the response flags which source to trust.
    try:
        net_m2 = sum(r.get("net_area") or 0 for r in sp.space_schedule(open_model(path)))
        gfa_sf = net_m2 * est.M2_TO_SF
    except Exception:                                 # noqa: BLE001 — benchmark is best-effort
        gfa_sf = None
    return est.estimate_from_takeoff(rows, gfa_sf=gfa_sf)


@router.post("/projects/{pid}/cost/tm")
def price_tm(pid: str, eticket_id: str = Body(...), lines: list[dict] = Body(...),
             db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Price T&M line items from the rate tables and write the totals back onto the eTicket."""
    result = cost.price_tm(db, pid, lines)
    me.update_record(db, "eticket", pid, eticket_id, {
        "tm_lines": result["lines"],
        "labor_total": result["labor_total"],
        "material_total": result["material_total"],
        "equipment_total": result["equipment_total"],
    }, user, None)
    return result


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
