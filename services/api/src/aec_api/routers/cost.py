"""Cost / financial endpoints (GC portal): G703 SOV register, G702 pay-app certificate
(+ formatted PDF), and the Cost Summary roll-up."""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import cost
from .. import modules as me
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

router = APIRouter()


@router.get("/estimate/labor/rates")
def labor_rates(_: str = Depends(current_user)):
    """EST-1: the productivity-rate catalog (man-hours/unit by trade) + condition loading factors."""
    from aec_data import productivity  # type: ignore

    return productivity.catalog()


@router.get("/projects/{pid}/estimate/labor")
def labor_estimate(pid: str, loading: str = "commercial", rate: float = 25.0, full: bool = False,
                   crews: int = 1, qto: bool = True,
                   db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """EST-1: a **cost + duration** estimate derived from the model's quantities via the
    productivity-rate library — man-hours → crew-days → cost per activity, condition-loaded, plus a
    **schedule duration** (crew-days roll up by trade → working/calendar days; `crews` = crews per trade
    running in parallel, which shortens each trade). Quantities come from the **real measured QTO
    takeoff** (Qto psets + geometry fallback, cached) by default; `qto=false` falls back to the rough
    element-dimension parse. With `full=true` it adds **material + equipment** cost lines. A starting
    point the estimator refines; excludes overhead/profit. Needs a source IFC."""
    from aec_data import productivity  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the estimate needs a model")
    if qto:
        from aec_data.qto import takeoff_file  # type: ignore
        rows = takeoff_file(p.source_ifc, force_geometry=True)
        return productivity.from_takeoff(rows, float(rate), loading, full=bool(full),
                                         crews_parallel=max(1, int(crews)))
    from aec_data.ifc_loader import open_model  # type: ignore
    return productivity.from_model(open_model(p.source_ifc), float(rate), loading, full=bool(full),
                                   crews_parallel=max(1, int(crews)))


@router.get("/projects/{pid}/proforma/live")
def proforma_live(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """PROFORMA-LIVE — the finance numbers that follow the model as you author: the current model
    version's **takeoff-priced construction cost** (cached per published version — cheap to poll after
    a reload), slab-derived **GFA**, cost/m², and the **delta vs the developer budget's hard cost**.
    The client refreshes this whenever the collab stream reports a new model version."""
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import dev_budget as dvb
    from .. import estimate as est

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the live proforma prices the model")
    rows = takeoff_file(p.source_ifc, force_geometry=True)         # content-cached per version
    out = est.estimate_from_takeoff(rows)
    cost = out.get("recommended_total") or out.get("total") or 0.0
    gfa = round(sum(float(r.get("area") or 0.0) for r in rows
                    if r.get("ifc_class") == "IfcSlab") / 2.0, 1)  # slab area ≈ both faces → /2
    budget_hard = None
    try:
        if p.dev_budget:
            budget_hard = (dvb.summarize(p.dev_budget).get("categories", {})
                           .get("hard", {}).get("total"))
    except Exception:  # noqa: BLE001 — a malformed budget never breaks the live readout
        budget_hard = None
    return {
        "model_version": Path(p.source_ifc).stem, "est_construction_cost": round(float(cost), 2),
        "gfa_m2": gfa, "cost_per_m2": round(float(cost) / gfa, 2) if gfa else None,
        "budget_hard_cost": budget_hard,
        "delta_vs_budget": round(float(cost) - float(budget_hard), 2) if budget_hard else None,
        "note": "Takeoff-priced from the current model (recommended total: benchmark-guarded). "
                "GFA approximated from slab areas. Refresh on each publish.",
    }


@router.get("/projects/{pid}/cost/calibration")
def cost_calibration(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """COST-AGENT — **learn from this project's own history**: compare the model's takeoff estimate
    against what the project has actually **committed** (awarded subcontract values) and **spent**
    (posted direct costs), and derive a calibration factor (clamped 0.5–2.0) future estimates can
    apply (`estimate_from_takeoff(benchmark_factor=…)`). Reported, never silently applied — the
    estimator decides. Needs a source IFC; committed/actuals are optional (factor null without them)."""
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import estimate as est

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — calibration compares against the model estimate")
    out = est.estimate_from_takeoff(takeoff_file(p.source_ifc, force_geometry=True))
    est_total = float(out.get("recommended_total") or out.get("total") or 0.0)

    def _sum(module: str, field: str) -> float:
        try:
            return sum(float((r.get("data") or {}).get(field) or 0.0)
                       for r in me.list_records(db, module, pid, limit=1_000_000)
                       if r.get("workflow_state") != "void")
        except Exception:  # noqa: BLE001 — module optional
            return 0.0

    committed = _sum("subcontract", "value")
    actual = _sum("direct_cost", "amount")
    basis, basis_total = (("actual", actual) if actual > 0 else
                          ("committed", committed) if committed > 0 else (None, 0.0))
    factor = None
    if basis and est_total > 0:
        factor = round(max(0.5, min(2.0, basis_total / est_total)), 3)
    return {
        "estimate_total": round(est_total, 2), "committed_total": round(committed, 2),
        "actual_total": round(actual, 2), "basis": basis,
        "calibration_factor": factor,
        "apply_hint": ("pass benchmark_factor to estimate_from_takeoff / re-run the estimate with the "
                       "factor to price the next iteration off this project's own outcomes"
                       if factor else "award subcontracts or post direct costs to enable calibration"),
        "note": "Factor = observed cost ÷ model estimate, clamped 0.5–2.0 (actuals preferred over "
                "commitments). Reported for the estimator — never auto-applied.",
    }


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


@router.get("/projects/{pid}/wip")
def wip_schedule(pid: str, method: str = "cost-to-cost",
                 db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Work-in-Progress schedule: percentage-of-completion → earned revenue vs billed →
    over-/under-billing (contract liability / asset), retainage, gross profit and backlog. The
    accounting twin to the earned-value module.

    `method=cost-to-cost` (default) drives POC by cost-to-date ÷ estimated cost; `method=units-installed`
    drives it by physical model progress (installed elements ÷ total, by IFC GlobalId). When a model is
    loaded the response carries a `model` block cross-checking physical vs cost progress either way."""
    from .. import wip
    return wip.schedule(db, pid, method=method)


@router.get("/projects/{pid}/wip/model-progress")
def wip_model_progress(pid: str, quantity: str | None = None,
                       db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Physical percent-complete straight from the model: installed elements ÷ total, keyed by IFC
    GlobalId, optionally weighted by an IFC base quantity (e.g. `quantity=NetVolume`). The independent
    'units-installed' progress signal that cross-checks cost-to-cost POC."""
    from .. import wip
    return wip.model_progress(db, pid, quantity=quantity)


@router.get("/wip/portfolio")
def wip_portfolio(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """WIP across your projects — one row each, worst cash position (largest under-billing) first."""
    from .. import wip
    from ..rbac import member_project_ids
    return wip.portfolio(db, project_ids=member_project_ids(db, user))


@router.get("/projects/{pid}/contractor-statements")
def contractor_statements(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Contractor financial statements: percentage-of-completion income statement (revenue earned, not
    billed) + the contract-position balance-sheet section (contract asset/liability, retainage, AP)."""
    from .. import contractor
    return contractor.statements(db, pid)


@router.get("/contractor-statements/portfolio")
def contractor_statements_portfolio(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Company-wide contractor statements — the POC P&L and contract position summed across your jobs."""
    from .. import contractor
    from ..rbac import member_project_ids
    return contractor.portfolio_statements(db, project_ids=member_project_ids(db, user))


@router.get("/projects/{pid}/cost/traceability")
def cost_traceability(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Cost traceability coverage — how much cost is tied to IFC model elements by GlobalId, per cost code."""
    from .. import traceability
    return traceability.summary(db, pid)


@router.get("/projects/{pid}/elements/{guid}/costs")
def element_costs(pid: str, guid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Every cost line (budget / commitment / direct cost / sub invoice) tagged to this IFC element."""
    from .. import traceability
    return traceability.element_costs(db, pid, guid)


@router.get("/projects/{pid}/elements/{guid}/records")
def element_records(pid: str, guid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Reverse deep-link — every record across all pinnable modules (RFIs, coordination issues, change
    orders, field verifications, schedule activities, …) tied to this IFC element by GlobalId. Closes the
    round-trip with the portal's record→element "show in model" direction."""
    from .. import traceability
    return traceability.element_records(db, pid, guid)


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

    from .. import fourd, storage
    from .. import project_budget as pb
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


@router.get("/projects/{pid}/5d/element-costs")
def element_costs_5d(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """5D-BIND: the GUID-keyed cost (+carbon) table off the **live** property index — element quantity
    (per the rate's basis) × class rate, so a GUID-stable edit + republish reprices automatically.
    Carbon rides the same row where the material matches. 404 until a model is loaded."""
    from fastapi import HTTPException

    from .. import cost_db, element_5d
    from .properties import _INDEX, _ensure_loaded
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project — load a model first")
    # Price through the project's pinned, localized + escalated cost vintage (same numbers as the takeoff);
    # falls back to the representative table when no vintage is installed.
    overrides, ds, adjustment = _vintage_overrides(db, pid)
    out = element_5d.element_costs(idx, rate_overrides=overrides)
    if ds:
        out["cost_vintage"] = cost_db.dataset_dict(ds)
    if adjustment:
        out["cost_adjustment"] = adjustment
    return out


@router.get("/projects/{pid}/5d/heatmap")
def elements_5d_map(pid: str, by: str = "progress", db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """Batch 5D for the whole model — bucket every element's GUID for a 3D heatmap. `by=progress`
    buckets by its schedule activity's %-complete (complete / in_progress / not_started); `by=cost`
    by its cost-code variance (over / on_under). Same hard-tied-or-by-trade resolution as the
    per-element 5D. Drives 'color the building by progress / cost status'."""
    import json

    from .. import fourd, storage
    from .. import project_budget as pb
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
        raise HTTPException(409, "no budget baseline set — POST /budget/baseline first") from None
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
    from aec_data import spaces as sp  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import estimate as est
    from ..deps import source_ifc_path
    path = source_ifc_path(db, pid)
    rows = takeoff_file(path, force_geometry=True)    # real geometry quantities (no cost map needed)
    # GFA (sf) from the model's spaces → a benchmark floor so a sparse model doesn't return a
    # misleadingly tiny number; the response flags which source to trust.
    try:
        net_m2 = sum(r.get("net_area") or 0 for r in sp.space_schedule(open_model(path)))
        gfa_sf = net_m2 * est.M2_TO_SF * est.NET_TO_GROSS   # spaces are NET; the $/sf benchmark is GROSS
    except Exception:                                 # noqa: BLE001 — benchmark is best-effort
        gfa_sf = None
    # COST-DB: price through the project's pinned cost vintage (reproducibility); falls back to the
    # shipped benchmark when no vintage is installed. The benchmark carries the same localization/
    # escalation factor as the model total so the trust comparison is same-dollars, not dollar-year skew.
    from .. import cost_db
    overrides, ds, adjustment = _vintage_overrides(db, pid)
    out = est.estimate_from_takeoff(rows, overrides=overrides, gfa_sf=gfa_sf,
                                    benchmark_factor=(adjustment or {}).get("combined_factor", 1.0))
    if ds:
        out["cost_vintage"] = cost_db.dataset_dict(ds)
    if adjustment:
        out["cost_adjustment"] = adjustment
    return out


def _market_params(db: Session, pid: str) -> dict:
    """Region + construction timeline for cost localization/escalation, from the project's adopted (else
    latest) `market_assumption` record — {} if none, so the neutral global-average index + no escalation
    apply. Mirrors the market router's resolution so the takeoff and the market panel agree."""
    def _int(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    try:
        recs = me.list_records(db, "market_assumption", pid, limit=1000)
    except Exception:                                 # noqa: BLE001 — module may be absent
        return {}
    if not recs:
        return {}
    adopted = [r for r in recs if r.get("workflow_state") == "adopted"]
    a = (adopted or recs)[-1].get("data") or {}
    rate = a.get("escalation_override_pct")
    return {"region": a.get("region"), "start_year": _int(a.get("construction_start_year")),
            "duration_months": _int(a.get("duration_months")),
            "rate_pct": float(rate) if rate not in (None, "") else None}


def _vintage_overrides(db: Session, pid: str):
    """The `{ifc_class: rate}` overrides + the dataset + the localization/escalation adjustment for a
    project's pinned cost vintage (or the latest installed). The rates are **localized** by the project
    region's cost index and **escalated** from the vintage year to the construction midpoint. Returns
    (None, None, None) when no vintage is installed → the shipped benchmark rates apply unchanged."""
    from .. import cost_db
    p = db.get(Project, pid)
    if not p:
        return None, None, None
    overrides, adjustment = cost_db.rates_for_project(db, p, **_market_params(db, pid))
    ds = cost_db.dataset_for_project(db, p)
    return overrides, ds, adjustment


@router.get("/estimate/resources/catalog")
def resource_catalog(_: str = Depends(current_user)):
    """The resource-based estimating reference: labor/material/equipment resources + assemblies
    (each with its built-up unit cost and L/M/E split) + the default IFC-class→assembly map."""
    from .. import assemblies as asm
    return asm.catalog()


@router.get("/projects/{pid}/estimate/resource-based")
def estimate_resource_based(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Resource-based (assembly) estimate from the IFC takeoff: each element class priced by building
    the cost UP from labor + material + equipment, returning the L/M/E split and total crew-hours
    (which feed resource loading + the schedule), not just a blended $/unit. 409 if no source IFC."""
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import assemblies as asm
    from ..deps import source_ifc_path
    path = source_ifc_path(db, pid)
    rows = takeoff_file(path, force_geometry=True)
    return asm.estimate_resource_based(rows)


@router.post("/projects/{pid}/takeoff/dxf")
async def takeoff_dxf(pid: str, file: UploadFile = File(...),
                      _: str = Depends(require_role("viewer"))):
    """Quantity takeoff from an uploaded 2D CAD drawing (.dxf) — linear metres, enclosed area and
    block counts per layer, so estimating isn't IFC-only. DWG must be converted to DXF first. The
    upload is parsed in a temp file (never persisted to the source tree) and discarded. 400 on a file
    that isn't readable DXF."""
    import os
    import tempfile

    from .. import dxf_takeoff
    data = await file.read()
    fd, tmp = tempfile.mkstemp(suffix=".dxf")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            return dxf_takeoff.takeoff(tmp)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@router.get("/classifications")
def list_classifications(_: str = Depends(current_user)):
    """Regional classification systems available for estimate coding / GAEB export."""
    from .. import classification as cls
    return {"systems": cls.systems()}


@router.get("/reference/authoring-matrix")
def reference_authoring_matrix(_: str = Depends(current_user)):
    """AUTHOR-MATRIX: the live authoring-coverage matrix — every GUID-stable edit recipe categorized by
    concern (create-structure / -enclosure / -mep / annotate / edit / type / group / data / lifecycle /
    analysis) with its IFC output. Derived from `edit.RECIPES`, so it never drifts from what's built."""
    from .. import authoring_matrix
    return authoring_matrix.matrix()


@router.get("/reference/disciplines")
def reference_disciplines(_: str = Depends(current_user)):
    """The Discipline Spine vocabularies: NCS disciplines (with their default MasterFormat divisions +
    Uniformat groups), the MasterFormat division master, and the Uniformat↔MasterFormat crosswalk.
    Drives the discipline/division selects and the model→sheets→specs→bid→budget joins."""
    from .. import classification as cls
    return {"disciplines": cls.disciplines(),
            "masterformat_divisions": cls.masterformat_divisions(),
            "uniformat_crosswalk": cls.uniformat_crosswalk(),
            "tree": cls.discipline_tree()}


# --- COST-DB: vintage-versioned cost database (offline public importer) -----------------------------
def _require_platform_admin(db: Session = Depends(get_db), user: str = Depends(current_user)) -> str:
    """Importing a vintage flips the GLOBAL `is_latest` flag → every unpinned project reprices. That is
    a platform operation, not a project edit: with RBAC off (dev / single-operator) it stays open like
    everything else; with RBAC on it requires a platform admin — a lone viewer-role member must never
    be able to silently reprice all projects' estimates (the audit's pricing-corruption scenario)."""
    from .. import rbac as _rbac
    if not _rbac.RBAC_ON or _rbac.LOCAL_MODE or user == "api-key":
        return user
    from .auth import require_admin_user
    require_admin_user(db=db, user=user)               # raises 403 unless AEC_ADMIN_EMAILS / legacy admin
    return user


@router.get("/cost/datasets")
def cost_datasets(db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Installed cost-database vintages + what the offline public importer can build (COST-DB)."""
    from .. import cost_db
    return {"datasets": cost_db.list_datasets(db), "available_public": cost_db.list_available_public()}


@router.post("/cost/datasets/import")
def cost_import(body: dict = Body(default={}), db: Session = Depends(get_db),
                _admin=Depends(_require_platform_admin)):
    """Build (import) a cost vintage. `{"vintage": 2025 | "latest", "quarter": null, "source": "public"}`.
    Offline **public** importer only for now — a `"source": "cloud"` request warns and falls back to the
    public build (the massing.cloud importer is a later build-order step). Idempotent; sets it as latest.
    **Platform-admin only**: importing flips the global `is_latest`, repricing every unpinned project."""
    from datetime import date

    from .. import cost_db
    v = body.get("vintage", "latest")
    year = date.today().year if v in (None, "latest") else int(v)
    quarter = body.get("quarter")
    warning = ("no cloud subscription configured — built the offline public vintage instead"
               if body.get("source") == "cloud" else None)
    ds = cost_db.import_public_vintage(db, year, quarter)
    return {**cost_db.dataset_dict(ds), "warning": warning}


@router.post("/cost/datasets/import-custom")
def cost_import_custom(body: dict = Body(default={}), db: Session = Depends(get_db),
                       _admin=Depends(_require_platform_admin)):
    """Import a firm's **own** cost book as a `custom`-origin vintage — so a project prices through the
    firm's historical/negotiated rates, not the shipped benchmark. Body:
    `{"vintage": 2025, "quarter": null, "name": "…", "rates": {"IfcWall": 180, …}}` (a flat class→rate map)
    or `{"rows": [{"ifc_class": "IfcWall", "total_cost": 180, "description": "…", "uom": "m2"}, …]}`.
    Re-importing the same (year, quarter) replaces that custom vintage in place. Sets it latest.
    **Platform-admin only**: a lone viewer must not be able to reprice every unpinned project's estimate
    (`is_latest` is a global flag — the audit's cross-project pricing-corruption scenario)."""
    from datetime import date

    from .. import cost_db
    v = body.get("vintage")
    year = int(v) if v not in (None, "", "latest") else date.today().year
    rows = cost_db.parse_cost_rows(body.get("rows") if body.get("rows") is not None else body.get("rates"))
    if not rows:
        raise HTTPException(400, "no valid priced rows — supply `rates` {ifc_class: rate} or `rows` [...]")
    ds = cost_db.import_custom_vintage(db, rows, year, body.get("quarter"), name=body.get("name"))
    return {**cost_db.dataset_dict(ds, item_count=len(rows)), "imported": len(rows)}


@router.get("/projects/{pid}/cost-vintage")
def get_cost_vintage(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The cost vintage a project's estimate resolves through — its pinned dataset, else the latest."""
    from .. import cost_db
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="project not found")
    ds = cost_db.dataset_for_project(db, p)
    _overrides, adjustment = cost_db.rates_for_project(db, p, **_market_params(db, pid))
    return {"pinned_id": p.cost_dataset_id, "resolved": cost_db.dataset_dict(ds) if ds else None,
            "adjustment": adjustment}


@router.post("/projects/{pid}/cost-vintage")
def set_cost_vintage(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                     _: str = Depends(require_role("editor"))):
    """Pin a project's estimate to a cost vintage. `{"dataset_id": "…"}` — null/absent = follow the latest
    installed vintage. Reproducibility: the estimate always prices through the pinned vintage."""
    from .. import cost_db
    from ..models import CostDataset
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="project not found")
    dataset_id = body.get("dataset_id")
    if dataset_id and db.get(CostDataset, dataset_id) is None:
        raise HTTPException(status_code=404, detail="cost dataset not found")
    cost_db.pin_project(db, p, dataset_id)
    ds = cost_db.dataset_for_project(db, p)
    return {"pinned_id": p.cost_dataset_id, "resolved": cost_db.dataset_dict(ds) if ds else None}


@router.get("/projects/{pid}/estimate/gaeb.x83")
def estimate_gaeb(pid: str, system: str = "din276", db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    """Export the model estimate as a GAEB DA XML 3.2 Bill of Quantities (X83), coded to a regional
    classification (din276 / nrm1 / masterformat). 409 if the project has no source IFC."""
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import classification as cls
    from .. import estimate as est
    from ..deps import source_ifc_path
    path = source_ifc_path(db, pid)
    rows = takeoff_file(path, force_geometry=True)
    est_out = est.estimate_from_takeoff(rows)
    p = db.get(Project, pid)
    xml = cls.gaeb_x83(p.name if p else "Project", est_out.get("lines", []), system)
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="estimate-{system}.x83"'})


@router.get("/projects/{pid}/qto/by-floor")
def qto_by_floor(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Quantity takeoff + cost broken down by floor (storey) and discipline (IFC class) — quantities
    and dollars mapped to where they sit in the building, with a per-floor total + a discipline
    roll-up. 409 if no source IFC."""
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import estimate as est
    from ..deps import source_ifc_path
    rows = takeoff_file(source_ifc_path(db, pid), force_geometry=True)
    from .. import cost_db
    overrides, ds, adjustment = _vintage_overrides(db, pid)
    out = est.estimate_by_storey(rows, overrides)
    if ds:
        out["cost_vintage"] = cost_db.dataset_dict(ds)
    if adjustment:
        out["cost_adjustment"] = adjustment
    return out


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
        raise HTTPException(400, str(e)) from e


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
