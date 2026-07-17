"""Project package — the single shareable deliverable a GC or architect hands to a client: a **cover**,
a **visual overview** (a composed plan + section + elevation sheet), the **drawing set**, and a
**cost & feasibility** summary (model-takeoff estimate by discipline + the developer budget's capital
stack). One bound PDF that answers "show someone the design, the drawings, the cost, and the proforma."

Composes existing engines — `aec_data.drawings.default_sheet` (overview), `drawingset.compiled_set_pdf`
(the set), `aec_data.estimate` (model takeoff), `dev_budget` + `sources_uses` (feasibility) — and merges
with `pdfops`. A server-rendered 3D hero is out of scope (geometry streams client-side); a client can add
a captured screenshot as page 2 later.
"""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from typing import Any

_DS = Path(__file__).resolve().parents[2] / "data" / "src"
if str(_DS) not in sys.path:
    sys.path.insert(0, str(_DS))

_W_MM, _H_MM = 914.0, 610.0   # ARCH-D, matching the sheets


def _text_page(title: str, subtitle: str, blocks: list[tuple[str, list[tuple[str, str]]]]) -> bytes:
    """A titled summary page: a header + a series of (section-heading, [(label, value), …]) blocks."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(_W_MM * mm, _H_MM * mm))
    c.setLineWidth(1)
    c.rect(8 * mm, 8 * mm, (_W_MM - 16) * mm, (_H_MM - 16) * mm)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(28 * mm, (_H_MM - 55) * mm, title[:60])
    c.setFont("Helvetica", 15)
    c.drawString(28 * mm, (_H_MM - 72) * mm, subtitle)
    y = _H_MM - 100
    for heading, rows in blocks:
        c.setFont("Helvetica-Bold", 13)
        c.drawString(28 * mm, y * mm, heading)
        y -= 9
        c.setFont("Helvetica", 11)
        for label, value in rows:
            c.drawString(34 * mm, y * mm, str(label)[:60])
            c.drawRightString((_W_MM - 30) * mm, y * mm, str(value)[:40])
            y -= 7
            if y < 24:
                break
        y -= 6
        if y < 24:
            break
    c.showPage()
    c.save()
    return buf.getvalue()


def _money(n: float) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return "—"


def project_package_pdf(db, pid: str, project_name: str, source_ifc: str,
                        max_sheets: int = 8) -> bytes:
    """Build the client project-package PDF: cover · visual overview · drawing set · cost & feasibility.
    Reuses the model estimate + developer budget already in the project. Best-effort — a missing piece is
    skipped, never fatal."""
    from aec_data import drawings as dwg  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore
    from aec_data.qto import takeoff_file  # type: ignore

    from . import classification, drawingset, pdfops
    from . import dev_budget as dvb
    from . import estimate as est
    from . import sources_uses as su
    from .models import Project

    model = open_model(source_ifc)
    parts: list[bytes] = []

    # --- 1) cover + contents ------------------------------------------------------------------------
    parts.append(_text_page(project_name, "Project Package", [
        ("Contents", [("1", "Visual overview — plan · section · elevation"),
                      ("2", "Drawing set — cover, floor plans, schedules"),
                      ("3", "Cost & feasibility — model estimate + capital stack")])]))

    # --- 2) visual overview (composed multi-view sheet) ---------------------------------------------
    try:
        meta = {"project": project_name, "number": "G-001", "title": "PROJECT OVERVIEW"}
        parts.append(dwg.default_sheet(model, meta, page="A2", fmt="pdf"))
    except Exception:  # noqa: BLE001 — overview is best-effort
        pass

    # --- 3) the drawing set -------------------------------------------------------------------------
    try:
        parts.append(drawingset.compiled_set_pdf(source_ifc, project_name, scale=300,
                                                 max_sheets=max_sheets, include_schedules=True))
    except Exception:  # noqa: BLE001
        pass

    # --- 4) cost & feasibility ----------------------------------------------------------------------
    est_rows: list[tuple[str, str]] = []
    total = 0.0
    try:
        rows = takeoff_file(source_ifc, force_geometry=True)
        out = est.estimate_from_takeoff(rows)
        total = round(out.get("recommended_total") or out.get("total") or 0.0, 2)
        by_disc: dict[str, float] = {}
        for ln in out.get("lines", []):
            d = classification.discipline_name(
                classification.discipline_of_ifc_class(ln.get("ifc_class", ""))) or "General"
            by_disc[d] = by_disc.get(d, 0.0) + float(ln.get("amount") or 0.0)
        est_rows = [(d, _money(v)) for d, v in sorted(by_disc.items(), key=lambda x: -x[1])]
        est_rows.append(("Estimated construction total", _money(total)))
    except Exception:  # noqa: BLE001
        est_rows = [("Model estimate", "unavailable")]

    feas_rows: list[tuple[str, str]] = []
    try:
        p = db.get(Project, pid)
        budget = (p.dev_budget if p and p.dev_budget else dvb.starter_budget())
        summ = dvb.summarize(budget)
        cap = su.build(summ, {"ltc": 0.65, "rate": 0.075, "construction_months": 18})
        feas_rows = [
            ("Developer budget — grand total", _money(summ.get("grand_total"))),
            ("Hard cost", _money(summ.get("categories", {}).get("hard", {}).get("total"))),
            ("Soft cost", _money(summ.get("categories", {}).get("soft", {}).get("total"))),
            ("Total uses (with financing)", _money(cap.get("total_uses"))),
            ("Debt", _money(cap.get("debt"))),
            ("Equity", _money(cap.get("equity"))),
        ]
    except Exception:  # noqa: BLE001
        feas_rows = [("Developer budget", "not set")]

    parts.append(_text_page(project_name, "Cost & Feasibility", [
        ("Construction estimate — from the model takeoff", est_rows),
        ("Developer proforma — capital stack", feas_rows)]))

    return pdfops.merge(parts)


def package_contents(db, pid: str) -> dict[str, Any]:
    """A quick pre-flight of what the package will contain — which pieces are available for this project."""
    from .models import Project

    p = db.get(Project, pid)
    return {
        "has_model": bool(p and p.source_ifc),
        "has_budget": bool(p and p.dev_budget),
        "sections": ["cover", "overview", "drawing-set", "cost-and-feasibility"],
    }
