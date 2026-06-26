"""Cost / financial endpoints (GC portal): G703 SOV register, G702 pay-app certificate
(+ formatted PDF), and the Cost Summary roll-up."""
from __future__ import annotations

import io
from datetime import date

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


def _proforma_hard(p) -> float | None:
    if not p or not p.dev_budget:
        return None
    lines = (p.dev_budget or {}).get("lines") or []
    return sum(float(ln.get("amount") or float(ln.get("unit_cost") or 0) * float(ln.get("quantity") or 1))
               for ln in lines if ln.get("category") == "hard")


@router.get("/projects/{pid}/px-summary")
def px_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The project-executive health view: on-schedule (SPI, % complete, critical path, lookahead,
    milestones) next to on-budget (GMP, EAC, variance-at-completion, buyout, cash flow), with an
    overall status. The single 'are we on schedule and on budget' answer."""
    from .. import px
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "project not found")
    return px.summary(db, pid, proforma_hard=_proforma_hard(p))


@router.get("/projects/{pid}/cost/g702.pdf")
def g702_pdf(pid: str, app_no: int = 1, period: str | None = None, release_retainage: bool = False,
             db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The owner pay application as a signable PDF — G702 certificate + G703 continuation sheet,
    drawn from the budget-seeded Schedule of Values."""
    from .. import report
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "project not found")
    pdf = report.payapp_pdf(db, pid, p.name, app_no=app_no, period=period, release_retainage=release_retainage)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="pay-app-{app_no}.pdf"'})


@router.post("/projects/{pid}/cost/pay-app/invoice", status_code=201)
def payapp_invoice(pid: str, app_no: int = Body(1, embed=True), period: str | None = Body(None, embed=True),
                   release_retainage: bool = Body(False, embed=True),
                   db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Create an owner-invoice record from the current pay application — amount = G702 current payment
    due — so each draw produces its owner invoice, linked to the prime contract. Closes the loop:
    budget → SOV → G702/G703 → owner invoice."""
    if "owner_invoice" not in me.TABLES:
        raise HTTPException(409, "owner_invoice module not loaded")
    g702 = cost.g702(db, pid, app_no=app_no, period=period, release_retainage=release_retainage)
    amount = round(float(g702["line8_current_payment_due"]), 2)
    pc = next((r for r in me.list_records(db, "prime_contract", pid, limit=1)), None)
    data = {"number": f"App {app_no}", "amount": amount, "period": period or "", "status": "draft"}
    if pc:
        data["prime_contract"] = pc["id"]
    rec = me.create_record(db, "owner_invoice", pid, {"data": data}, actor, "GC")
    return {"owner_invoice": rec, "application_no": app_no, "amount": amount}


@router.post("/projects/{pid}/cost/advance-period")
def advance_period(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Close the current pay period (C1) — roll each SOV line's completed-this into completed-previous
    so the next pay application starts a fresh period."""
    return cost.advance_period(db, pid, user)


@router.get("/projects/{pid}/cost/summary")
def summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return cost.summary(db, pid)


@router.get("/projects/{pid}/subcontractor-billing")
def subcontractor_billing(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Subcontractor billing — the GC-pays-subs mirror of owner billing. Each subcontract's pay
    applications (sub_invoice records) rolled up: contract value vs billed-to-date (approved/paid),
    retainage held, paid, and remaining-to-bill. Ties sub draws to the same cost codes and the GMP
    direct-cost actual, so what subs bill the GC reconciles against what the GC bills the owner."""
    def _n(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    subs = {r["id"]: r for r in me.list_records(db, "subcontract", pid, limit=1_000_000)} \
        if "subcontract" in me.TABLES else {}
    invs = me.list_records(db, "sub_invoice", pid, limit=1_000_000) if "sub_invoice" in me.TABLES else []
    rows: dict[str, dict] = {}
    for r in invs:
        d = r.get("data") or {}
        scid = d.get("subcontract")
        sub = subs.get(scid, {})
        sd = sub.get("data") or {}
        key = scid or d.get("vendor") or r.get("id")
        row = rows.setdefault(key, {
            "subcontract_ref": sub.get("ref"), "vendor": d.get("vendor") or sd.get("vendor"),
            "trade": sd.get("trade"), "cost_code": d.get("cost_code") or sd.get("cost_code"),
            "contract_value": round(_n(sd.get("value")), 2),
            "billed": 0.0, "retainage": 0.0, "paid": 0.0, "applications": 0})
        amt = _n(d.get("amount"))
        ret_pct = _n(d.get("retainage_pct")) or _n(sd.get("retainage_pct"))
        state = r.get("workflow_state")
        row["applications"] += 1
        if state in ("approved", "paid"):
            row["billed"] = round(row["billed"] + amt, 2)
            row["retainage"] = round(row["retainage"] + amt * ret_pct / 100, 2)
        if state == "paid":
            row["paid"] = round(row["paid"] + amt * (1 - ret_pct / 100), 2)
    for row in rows.values():
        row["remaining"] = round(row["contract_value"] - row["billed"], 2)
    out = sorted(rows.values(), key=lambda x: -x["billed"])
    tot = {k: round(sum(_n(r[k]) for r in out), 2) for k in ("contract_value", "billed", "retainage", "paid", "remaining")}
    return {"subs": out, "totals": tot, "subcontract_count": len(subs), "invoice_count": len(invs)}


@router.get("/projects/{pid}/elements/{guid}/5d")
def element_5d(pid: str, guid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """5D for a model element: click a GUID in the 3D view → its schedule activity (with %-complete,
    dates, whether it's hard-tied or matched by trade) and its cost code's budget vs committed vs
    actual. Ties the BIM model to the GC schedule + budget — the same relational data, by element."""
    import json

    from .. import fourd, project_budget as pb, storage
    # element metadata from the published props index
    meta: dict = {}
    elements: list = []
    try:
        idx = json.loads(storage.get(f"{pid}/props.json"))
        elements = idx.get("elements", [])
        meta = next((e for e in elements if e.get("guid") == guid), {})
    except Exception:                                  # noqa: BLE001 — no published index
        pass
    ifc_class, storey = meta.get("ifc_class"), meta.get("storey")

    acts = pb._records(db, "schedule_activity", pid)
    # schedule: prefer the activity that hard-tags this element; else map class → trade → floor
    activity, tagged = None, False
    for r in acts:
        if guid in (r.get("element_guids") or []):
            activity, tagged = r, True
            break
    if activity is None and ifc_class:
        trade = fourd._CLASS_TRADE_TO_ACTIVITY_TRADE.get(
            fourd.TRADE_FOR_CLASS.get(ifc_class, fourd._DEFAULT_TRADE))
        pool = sorted((r for r in acts if (r.get("data") or {}).get("trade") == trade),
                      key=lambda r: str((r.get("data") or {}).get("start") or ""))
        if pool:
            floors = max([fourd._floor_index(e.get("storey")) for e in elements] + [0]) + 1
            f = fourd._floor_index(storey)
            i = round(f / max(1, floors - 1) * (len(pool) - 1)) if len(pool) > 1 else 0
            activity = pool[i]

    sched, cc_id = None, None
    if activity:
        d = activity.get("data") or {}
        cc_id = d.get("cost_code")
        sched = {"ref": activity.get("ref"), "name": activity.get("title") or d.get("name"),
                 "trade": d.get("trade"), "percent": pb._n(d.get("percent")),
                 "start": d.get("start"), "finish": d.get("finish"),
                 "state": activity.get("workflow_state"), "hard_tied": tagged}

    # cost: pull the element's cost-code line straight from the GMP budget (budget/committed/actual)
    cost = None
    if cc_id:
        b = pb.gmp_budget(db, pid)
        line = next((ln for cat in b["categories"] for grp in (cat.get("groups") or [cat])
                     for ln in grp.get("lines", []) if ln.get("cost_code_id") == cc_id), None)
        if line:
            cost = {"code": line.get("code"), "ref": line.get("ref"), "name": line.get("name"),
                    "division": line.get("division"), "budget": line["budget"],
                    "committed": line["committed"], "actual": line["actual"],
                    "eac": line.get("eac"), "variance": line["variance"]}

    return {"guid": guid, "ifc_class": ifc_class, "storey": storey,
            "name": meta.get("name") or meta.get("type_name"), "schedule": sched, "cost": cost}


@router.get("/projects/{pid}/5d/heatmap")
def elements_5d_map(pid: str, by: str = "progress", db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """Batch 5D for the whole model — bucket every element's GUID for a 3D heatmap. `by=progress`
    buckets by its schedule activity's %-complete (complete / in_progress / not_started); `by=cost`
    by its cost-code variance (over / on_under). Same hard-tied-or-by-trade resolution as the
    per-element 5D. Drives 'color the building by progress / cost status'."""
    import json

    from .. import fourd, project_budget as pb, storage
    try:
        elements = json.loads(storage.get(f"{pid}/props.json")).get("elements", [])
    except Exception:                                  # noqa: BLE001 — no published index
        elements = []
    acts = pb._records(db, "schedule_activity", pid)
    tied: dict[str, dict] = {}
    by_trade: dict[str, list] = {}
    for r in acts:
        d = r.get("data") or {}
        for g in (r.get("element_guids") or []):
            tied[g] = r
        if d.get("trade"):
            by_trade.setdefault(d["trade"], []).append(r)
    for v in by_trade.values():
        v.sort(key=lambda r: str((r.get("data") or {}).get("start") or ""))
    floors = max([fourd._floor_index(e.get("storey")) for e in elements] + [0]) + 1

    cc_var: dict[str, float] = {}
    if by == "cost":
        b = pb.gmp_budget(db, pid)
        for cat in b["categories"]:
            for grp in (cat.get("groups") or [cat]):
                for ln in grp.get("lines", []):
                    if ln.get("cost_code_id"):
                        cc_var[ln["cost_code_id"]] = ln["variance"]

    buckets: dict[str, list] = {}
    for e in elements:
        g = e.get("guid")
        if not g:
            continue
        a = tied.get(g)
        if a is None:
            trade = fourd._CLASS_TRADE_TO_ACTIVITY_TRADE.get(
                fourd.TRADE_FOR_CLASS.get(e.get("ifc_class"), fourd._DEFAULT_TRADE))
            pool = by_trade.get(trade) or []
            if pool:
                f = fourd._floor_index(e.get("storey"))
                a = pool[round(f / max(1, floors - 1) * (len(pool) - 1)) if len(pool) > 1 else 0]
        if a is None:
            buckets.setdefault("unscheduled", []).append(g)
            continue
        d = a.get("data") or {}
        if by == "cost":
            key = "over" if cc_var.get(d.get("cost_code"), 0) < 0 else "on_under"
        else:
            p = pb._n(d.get("percent"))
            key = "complete" if p >= 100 else "in_progress" if p > 0 else "not_started"
        buckets.setdefault(key, []).append(g)
    return {"by": by, "buckets": buckets, "counts": {k: len(v) for k, v in buckets.items()},
            "element_count": len(elements)}


@router.get("/projects/{pid}/budget/gmp")
def gmp_budget(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Full GC project budget (GMP): direct trade work (by CSI division + bid package) + General
    Conditions / Requirements (incl. staffing projections) + Overhead + Fee + Contingency, each
    tracked budget vs committed vs actual vs variance. Reconciles to the prime-contract value and to
    the developer proforma's construction hard-cost line — the PX's on-budget view, under Schedule."""
    from .. import project_budget
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "project not found")
    hard = None
    if p.dev_budget:
        lines = (p.dev_budget or {}).get("lines") or []
        hard = sum(float(ln.get("amount") or float(ln.get("unit_cost") or 0) * float(ln.get("quantity") or 1))
                   for ln in lines if ln.get("category") == "hard")
    return project_budget.gmp_budget(db, pid, proforma_hard=hard)


_BUDGET_BASELINE_KEY = "{pid}/budget_baseline.json"


def _budget_lines_by_code(b: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for cat in b["categories"]:
        groups = cat.get("groups", []) if cat["key"] == "direct" else [cat]
        for grp in groups:
            for ln in grp.get("lines", []):
                key = ln.get("code") or ln.get("name")
                out[key] = round(out.get(key, 0.0) + float(ln.get("budget") or 0), 2)
    return out


@router.post("/projects/{pid}/budget/baseline", status_code=201)
def set_budget_baseline(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Snapshot the current GMP budget as the **baseline** (computed total + per-category + per-line).
    Budget variance is then measured against this — re-baseline after an approved change. One per project."""
    import json

    from .. import project_budget, storage
    b = project_budget.gmp_budget(db, pid)
    payload = {"captured_at": date.today().isoformat(), "gmp_computed": b["gmp"]["computed"],
               "categories": {c["key"]: c["budget"] for c in b["categories"]},
               "lines": _budget_lines_by_code(b)}
    storage.put(_BUDGET_BASELINE_KEY.format(pid=pid), json.dumps(payload).encode("utf-8"))
    return {"captured_at": payload["captured_at"], "gmp_computed": payload["gmp_computed"],
            "lines": len(payload["lines"])}


@router.delete("/projects/{pid}/budget/baseline")
def clear_budget_baseline(pid: str, _: str = Depends(require_role("editor"))):
    """Remove the budget baseline."""
    from .. import storage
    storage.delete(_BUDGET_BASELINE_KEY.format(pid=pid))
    return {"cleared": True}


@router.get("/projects/{pid}/budget/variance")
def budget_variance(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Movement of the GMP budget vs the baseline: total delta + per-category and per-line deltas
    (positive = grown since baseline). 409 if no baseline is set. Shows how the budget has drifted
    from the plan of record — the on-budget tracking a PX reports."""
    import json

    from .. import project_budget, storage
    try:
        base = json.loads(storage.get(_BUDGET_BASELINE_KEY.format(pid=pid)))
    except Exception:
        raise HTTPException(409, "no budget baseline set — POST /budget/baseline first")
    b = project_budget.gmp_budget(db, pid)
    cur_cats = {c["key"]: c["budget"] for c in b["categories"]}
    cat_delta = [{"key": k, "baseline": base["categories"].get(k, 0), "current": cur_cats.get(k, 0),
                  "delta": round(cur_cats.get(k, 0) - base["categories"].get(k, 0), 2)}
                 for k in sorted(set(base["categories"]) | set(cur_cats))]
    cur_lines = _budget_lines_by_code(b)
    line_delta = [{"code": k, "baseline": base["lines"].get(k, 0), "current": cur_lines.get(k, 0),
                   "delta": round(cur_lines.get(k, 0) - base["lines"].get(k, 0), 2)}
                  for k in sorted(set(base["lines"]) | set(cur_lines))
                  if abs(cur_lines.get(k, 0) - base["lines"].get(k, 0)) > 0.01]
    return {"captured_at": base["captured_at"],
            "baseline_gmp": base["gmp_computed"], "current_gmp": b["gmp"]["computed"],
            "total_delta": round(b["gmp"]["computed"] - base["gmp_computed"], 2),
            "categories": cat_delta, "lines": line_delta}


@router.get("/projects/{pid}/budget/cashflow")
def budget_cashflow(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Cost-loaded schedule → monthly cash-flow / draw curve. Spreads each schedule activity's
    budgeted cost across its start→finish months for the cumulative construction S-curve — where the
    Schedule and Budget destinations meet (the PX's monthly cash need)."""
    from .. import project_budget
    return project_budget.cashflow(db, pid)


@router.post("/projects/{pid}/cost/sov/from-budget", status_code=201)
def sov_from_budget(pid: str, replace: bool = False, db: Session = Depends(get_db),
                    actor: str = Depends(require_role("editor"))):
    """Seed the owner pay-app **Schedule of Values** from the GMP budget — one SOV line per cost-code
    budget line (carrying its cost-code link), plus General Conditions / Requirements / Overhead /
    Fee / Contingency, each at its GMP value. So the G702/G703 the owner is billed on draws from the
    same relational budget the PX manages. Idempotent: no-op if the SOV already has lines unless
    `?replace=true` rebuilds it. Retainage comes from the prime contract."""
    from .. import project_budget as pb
    if "sov" not in me.TABLES:
        raise HTTPException(409, "SOV module not loaded")
    existing = me.list_records(db, "sov", pid, limit=1_000_000)
    if existing and not replace:
        return {"created": 0, "skipped": len(existing),
                "note": "SOV already has lines — pass ?replace=true to rebuild from the budget"}
    for r in existing:
        me.delete_record(db, "sov", pid, r["id"], actor, "GC")

    b = pb.gmp_budget(db, pid)
    pc = next((r for r in me.list_records(db, "prime_contract", pid, limit=1)), None)
    ret = float(((pc or {}).get("data") or {}).get("retainage_pct") or 0)

    rows: list[tuple] = []
    for cat in b["categories"]:
        if cat["key"] == "direct":
            for grp in cat.get("groups", []):
                for ln in grp["lines"]:
                    if ln["budget"] > 0:
                        rows.append((ln["name"], ln.get("cost_code_id"), ln["budget"]))
        else:
            for ln in cat["lines"]:
                if ln["budget"] > 0:
                    rows.append((ln["name"], ln.get("cost_code_id"), ln["budget"]))

    created = 0
    for i, (desc, ccid, val) in enumerate(rows, 1):
        data = {"item_no": f"{i:02d}", "description": desc[:120],
                "scheduled_value": round(val, 2), "retainage_pct": ret}
        if ccid:
            data["cost_code"] = ccid
        me.create_record(db, "sov", pid, {"data": data}, actor, "GC")
        created += 1
    return {"created": created, "lines": len(rows),
            "scheduled_value": round(sum(v for _, _, v in rows), 2)}


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
