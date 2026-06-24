"""Cost / financial endpoints (GC portal): G703 SOV register, G702 pay-app certificate
(+ formatted PDF), and the Cost Summary roll-up."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Response
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
def g702(pid: str, app_no: int = 1, period: str | None = None, release_retainage: bool = False,
         db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return cost.g702(db, pid, app_no, period, release_retainage)


@router.post("/projects/{pid}/cost/advance-period")
def advance_period(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Close the current pay period (C1) — roll each SOV line's completed-this into completed-previous
    so the next pay application starts a fresh period."""
    return cost.advance_period(db, pid, user)


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


@router.get("/projects/{pid}/cost/lien-waiver")
def lien_waiver(pid: str, kind: str = "conditional_progress", app_no: int = 1, claimant: str = "",
                customer: str = "", through_date: str = "", db: Session = Depends(get_db),
                _: str = Depends(require_role("viewer"))):
    """A statutory lien waiver / release to accompany a pay app (C1). `kind`: conditional_progress |
    unconditional_progress | conditional_final | unconditional_final."""
    p = db.get(Project, pid)
    try:
        return cost.lien_waiver(db, pid, kind, app_no, claimant=claimant, customer=customer,
                                project_name=(p.name if p else ""), through_date=through_date)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/projects/{pid}/cost/lien-waiver.pdf")
def lien_waiver_pdf(pid: str, kind: str = "conditional_progress", app_no: int = 1, claimant: str = "",
                    customer: str = "", through_date: str = "", db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    p = db.get(Project, pid)
    lw = cost.lien_waiver(db, pid, kind, app_no, claimant=claimant, customer=customer,
                          project_name=(p.name if p else ""), through_date=through_date)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 14); c.drawString(40, h - 50, lw["title"].upper())
    y = h - 78
    c.setFont("Helvetica-Bold", 9)
    for line in simpleSplit("NOTICE: " + lw["notice"], "Helvetica-Bold", 9, w - 80):
        c.drawString(40, y, line); y -= 12
    y -= 10
    c.setFont("Helvetica", 11)
    for label, val in [("Project", lw["project_name"] or "-"), ("Claimant", lw["claimant"] or "-"),
                       ("Customer", lw["customer"] or "-"), ("Through date", lw["through_date"] or "-"),
                       ("Amount", f"${lw['amount']:,.2f}"), ("Application No.", str(lw["application_no"]))]:
        c.drawString(40, y, f"{label}:"); c.drawString(160, y, val); y -= 16
    y -= 8
    c.setFont("Helvetica", 10)
    for line in simpleSplit(lw["body"], "Helvetica", 10, w - 80):
        if y < 120: c.showPage(); y = h - 60; c.setFont("Helvetica", 10)
        c.drawString(40, y, line); y -= 13
    y -= 10
    c.setFont("Helvetica-Oblique", 9)
    for line in simpleSplit(lw["exceptions"], "Helvetica-Oblique", 9, w - 80):
        c.drawString(40, y, line); y -= 12
    y -= 30
    c.setFont("Helvetica", 10)
    c.line(40, y, 280, y); c.drawString(40, y - 12, "Signature of Claimant / Authorized Agent")
    c.line(330, y, w - 40, y); c.drawString(330, y - 12, "Date")
    c.showPage(); c.save()
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="lien-waiver-{kind}.pdf"'})
