"""CAM reconciliation — operating-expense recovery true-up for the hold phase.

The annual landlord ritual: compare what tenants paid in CAM estimates against their pro-rata share
of actual recoverable operating expenses, gross up occupancy-variable expenses to a stated occupancy
(the standard lease clause applies gross-up to VARIABLE expenses only — janitorial, utilities,
management — never fixed ones like insurance/taxes), and issue per-tenant true-up statements.
Deterministic on `cam_expense` + `lease` records; statement PDFs follow report.py patterns."""
from __future__ import annotations

import io
from datetime import date
from typing import Any

from . import modules as me


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def reconciliation(db, pid: str, year: int | None = None, gross_up_to_pct: float = 95.0,
                   building_sf: float | None = None) -> dict[str, Any]:
    """CAM true-up: recoverable pool (variable lines grossed up to `gross_up_to_pct` occupancy),
    each tenant's pro-rata share vs estimated payments (recovery_psf x sf), and the balance due."""
    yr = year or date.today().year
    expenses = [e for e in me.list_records(db, "cam_expense", pid, limit=10000)
                if int(_f(_d(e).get("year")) or yr) == yr]
    leases = [le for le in me.list_records(db, "lease", pid, limit=10000)
              if _f(_d(le).get("rentable_sf")) > 0]
    occupied_sf = sum(_f(_d(le).get("rentable_sf")) for le in leases)
    total_sf = building_sf if building_sf and building_sf > 0 else occupied_sf
    occ_pct = round(100 * occupied_sf / total_sf, 1) if total_sf else 0.0
    target = max(occ_pct, min(100.0, _f(gross_up_to_pct) or 95.0))

    lines = []
    pool = 0.0
    budget_total = actual_total = 0.0
    for e in expenses:
        d = _d(e)
        actual = _f(d.get("actual_annual"))
        budget = _f(d.get("budget_annual"))
        budget_total += budget
        actual_total += actual
        recoverable = (d.get("recoverable") or "Yes") == "Yes"
        variable = (d.get("variable") or "No") == "Yes"
        grossed = actual
        if recoverable and variable and occ_pct and occ_pct < target:
            grossed = actual * (target / occ_pct)
        lines.append({"ref": e.get("ref"), "category": d.get("category") or "Other",
                      "budget": round(budget, 2), "actual": round(actual, 2),
                      "variable": variable, "recoverable": recoverable,
                      "grossed_up": round(grossed if recoverable else 0.0, 2)})
        if recoverable:
            pool += grossed

    tenants = []
    for le in leases:
        d = _d(le)
        sf = _f(d.get("rentable_sf"))
        share_pct = sf / total_sf if total_sf else 0.0
        owed = pool * share_pct
        paid = _f(d.get("recovery_psf")) * sf
        tenants.append({"id": le["id"], "ref": le.get("ref"), "tenant": d.get("tenant") or "",
                        "suite": d.get("suite") or "", "rentable_sf": sf,
                        "share_pct": round(100 * share_pct, 2),
                        "share_of_expenses": round(owed, 2), "estimated_paid": round(paid, 2),
                        "balance_due": round(owed - paid, 2)})

    return {
        "year": yr, "occupied_sf": round(occupied_sf, 0), "building_sf": round(total_sf, 0),
        "occupancy_pct": occ_pct, "gross_up_to_pct": target,
        "expense_lines": lines, "budget_total": round(budget_total, 2),
        "actual_total": round(actual_total, 2), "recoverable_pool": round(pool, 2),
        "tenants": sorted(tenants, key=lambda t: -t["rentable_sf"]),
        "note": "Gross-up applies to occupancy-variable recoverable expenses only, up to the stated "
                "occupancy; fixed expenses (taxes, insurance) pass through at actual. Estimated "
                "payments = lease recovery_psf x rentable_sf.",
    }


def statement_pdf(recon: dict, tenant_row: dict, project_name: str) -> bytes:
    """Per-tenant CAM reconciliation statement (one page): expense pool by category, the tenant's
    pro-rata share, estimated payments, and the true-up balance."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin, y = 50, h - 50
    c.setFont("Helvetica-Bold", 16); c.drawString(margin, y, "CAM Reconciliation Statement"); y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"{project_name} - operating year {recon['year']}"); y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, f"Tenant: {tenant_row.get('tenant') or tenant_row.get('ref')}")
    c.drawRightString(w - margin, y, f"Suite {tenant_row.get('suite') or '-'}"); y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"Rentable area: {tenant_row['rentable_sf']:,.0f} sf")
    c.drawRightString(w - margin, y, f"Pro-rata share: {tenant_row['share_pct']}%"); y -= 22

    c.setFont("Helvetica-Bold", 10); c.drawString(margin, y, "Recoverable operating expenses")
    c.drawRightString(w - margin, y, "Grossed-up actual"); y -= 14
    c.setFont("Helvetica", 9)
    by_cat: dict[str, float] = {}
    for ln in recon["expense_lines"]:
        if ln["recoverable"]:
            by_cat[ln["category"]] = by_cat.get(ln["category"], 0.0) + ln["grossed_up"]
    for cat, amt in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        c.drawString(margin, y, cat)
        c.drawRightString(w - margin, y, f"${amt:,.2f}")
        y -= 13
        if y < 140:
            c.showPage(); y = h - 50; c.setFont("Helvetica", 9)
    y -= 6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, f"Recoverable pool (grossed up to {recon['gross_up_to_pct']}% occupancy)")
    c.drawRightString(w - margin, y, f"${recon['recoverable_pool']:,.2f}"); y -= 20

    rows = [
        (f"Your share ({tenant_row['share_pct']}%)", tenant_row["share_of_expenses"]),
        ("Estimated CAM payments", -tenant_row["estimated_paid"]),
    ]
    c.setFont("Helvetica", 10)
    for label, val in rows:
        c.drawString(margin, y, label)
        c.drawRightString(w - margin, y, f"${abs(val):,.2f}" + (" cr" if val < 0 else ""))
        y -= 16
    bal = tenant_row["balance_due"]
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "BALANCE DUE" if bal >= 0 else "CREDIT TO TENANT")
    c.drawRightString(w - margin, y, f"${abs(bal):,.2f}"); y -= 14
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, 40, recon["note"][:150])
    c.showPage(); c.save()
    return buf.getvalue()
