"""Real-estate development finance (Proforma) endpoints: stateless solve + scenario CRUD.
The pure engine (aec_api.proforma) is validated by Pydantic models that double as the
OpenAPI contract. A full proforma + waterfall solves in <100ms — run it in-request."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import cost as cost_engine
from .. import modules as me
from .. import rbac
from ..db import get_db
from ..models import Scenario
from ..proforma.draws import reforecast
from ..proforma.monte_carlo import monte_carlo
from ..proforma.sensitivity import sensitivity
from ..proforma.solve import solve
from ..rbac import current_user

router = APIRouter()

# The proforma input contract (Timing/CostLine/Debt/…/Assumptions) lives in proforma_schemas so the
# router stays focused on endpoints. Re-exported here so `routers.proforma.Assumptions` still resolves.
from .proforma_schemas import (  # noqa: E402
    Assumptions,
)

__all__ = ["router", "Assumptions"]


@router.post("/proforma/solve")
def solve_stateless(a: Assumptions):
    """Solve a deal without persisting — full S&U, cash flows, returns, waterfall, plus underwriting
    guardrails (U5) that flag returns outside typical market bands."""
    from .. import underwrite
    result = solve(a.model_dump())
    return {**result, "guardrails": underwrite.guardrails(result)}


@router.post("/proforma/financials")
def financials_stateless(a: Assumptions):
    """Three financial statements + tax for a deal, without persisting: income statement (NOI →
    depreciation → interest → tax → net income), balance sheet (balances), GAAP cash-flow statement,
    depreciation/tax schedule with sale recapture + capital gains, after-tax returns, two-sided budget."""
    from .. import financials
    assumptions = a.model_dump()
    return financials.statements(solve(assumptions), assumptions)


def _latest_scenario(db: Session, pid: str):
    return (db.query(Scenario).filter(Scenario.project_id == pid)
            .order_by(Scenario.created_at.desc()).first())


@router.get("/projects/{pid}/financials")
def project_financials(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Financial statements for the project's latest saved scenario (income statement · balance sheet ·
    cash flow · tax · after-tax returns · two-sided budget)."""
    from .. import financials
    s = _latest_scenario(db, pid)
    if not s:
        raise HTTPException(404, "no saved scenario — solve & save a proforma first")
    result = s.result or solve(s.assumptions)
    return {"scenario": {"id": s.id, "name": s.name}, **financials.statements(result, s.assumptions)}


@router.get("/projects/{pid}/budget/two-sided")
def two_sided_budget(pid: str, ltc: float = 0.65, rate: float = 0.075,
                     construction_months: int = 18, lp_pct: float = 0.9,
                     db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """The development budget as Uses (left) vs Sources (right) — from the latest scenario if one is
    saved, else built from the project's cost budget + the supplied debt/equity params."""
    from .. import dev_budget as dvb
    from .. import financials
    from .. import sources_uses as su
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    s = _latest_scenario(db, pid)
    if s:
        return financials.two_sided_budget(s.result or solve(s.assumptions), s.assumptions)
    # no scenario yet: assemble a two-sided view from the cost budget + sources-uses sizing
    summary = dvb.summarize(p.dev_budget or dvb.starter_budget())
    su_out = su.build(summary, {"ltc": ltc, "rate": rate, "construction_months": construction_months, "lp_pct": lp_pct})
    return {"uses": su_out["uses"], "sources": su_out["sources"],
            "total_uses": su_out["total_uses"], "total_sources": su_out["total_sources"],
            "balanced": su_out["balanced"]}


@router.get("/projects/{pid}/dev-budget")
def get_dev_budget(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """The project's developer cost budget (line-item hard/soft/acquisition + contingencies) plus a
    computed summary. Returns a starter budget if none is saved yet."""
    from .. import dev_budget as dvb
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    budget = p.dev_budget or dvb.starter_budget()
    return {"budget": budget, "summary": dvb.summarize(budget)}


class DevBudgetIn(BaseModel):
    lines: list[dict] = Field(default_factory=list)
    contingency: dict[str, float] = Field(default_factory=dict)


@router.put("/projects/{pid}/dev-budget")
def put_dev_budget(pid: str, body: DevBudgetIn, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("editor"))):
    """Save the developer cost budget; returns the recomputed summary."""
    from .. import dev_budget as dvb
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    budget = body.model_dump()
    p.dev_budget = budget
    db.commit()
    return {"budget": budget, "summary": dvb.summarize(budget)}


@router.get("/projects/{pid}/specialty")
def get_specialty(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Specialty assets (on-site energy + vertical-farm/PFAL) params + computed summary (capex,
    annual revenue/opex/energy-offset). Starter params if none saved."""
    from .. import specialty as sp
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    params = p.dev_specialty or sp.starter()
    return {"params": params, "summary": sp.summarize(params), "deltas": sp.to_proforma_deltas(params)}


@router.put("/projects/{pid}/specialty")
def put_specialty(pid: str, body: dict, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("editor"))):
    """Save specialty-asset params; returns the recomputed summary + proforma deltas."""
    from .. import specialty as sp
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    p.dev_specialty = body
    db.commit()
    return {"params": body, "summary": sp.summarize(body), "deltas": sp.to_proforma_deltas(body)}


@router.get("/projects/{pid}/property")
def get_property(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Property & tax assumptions + computed summary (totals, per-SF ratios, proforma deltas)."""
    from .. import dev_property as dp
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    prop = p.dev_property or dp.starter()
    return {"property": prop, "summary": dp.summarize(prop)}


@router.put("/projects/{pid}/property")
def put_property(pid: str, body: dict, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("editor"))):
    """Save property & tax assumptions; returns the recomputed summary."""
    from .. import dev_property as dp
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    p.dev_property = body
    db.commit()
    return {"property": body, "summary": dp.summarize(body)}


@router.get("/projects/{pid}/sources-uses")
def get_sources_uses(pid: str, ltc: float = 0.65, rate: float = 0.075,
                     construction_months: int = 18, lp_pct: float = 0.9,
                     db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Sources & Uses built from the project's cost budget — grouped Uses (acquisition/hard/soft/
    contingency + construction-loan interest) vs sized Sources (senior debt by LTC + LP/GP equity)."""
    from .. import dev_budget as dvb
    from .. import sources_uses as su
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    summary = dvb.summarize(p.dev_budget or dvb.starter_budget())
    params = {"ltc": ltc, "rate": rate, "construction_months": construction_months, "lp_pct": lp_pct}
    return su.build(summary, params)


@router.get("/projects/{pid}/investment-memo.pdf")
def investment_memo(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Confidential investment memorandum (PDF) composed from live project data — executive summary,
    Sources & Uses, the development cost budget, returns (from the latest solved scenario), and a
    risk read. The 'generate a presentation with financials' deliverable."""
    from fastapi import Response

    from .. import report
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    pdf = report.investment_memo_pdf(db, pid, p.name)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="investment-memo-{pid[:8]}.pdf"'})


@router.get("/projects/{pid}/investment-deck.pdf")
def investment_deck(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Pitch-deck (slide) variant of the investment memo — landscape, big numbers, the ask."""
    from fastapi import Response

    from .. import report
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    pdf = report.investment_deck_pdf(db, pid, p.name)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="pitch-deck-{pid[:8]}.pdf"'})


@router.get("/projects/{pid}/dev-budget/gmp-reconciliation")
def gmp_reconciliation(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Tie the developer's construction **hard cost** to the GC's actual **GMP**: the proforma was
    underwritten with a hard-cost line; the GC manages a live GMP (buyout + GC/GR + OH/fee). This
    shows them side by side so the developer sees whether construction is tracking the underwriting."""
    from .. import dev_budget as dvb
    from .. import project_budget as pb
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    budget = p.dev_budget or dvb.starter_budget()
    dev_hard = round(sum(dvb.line_total(ln) for ln in (budget.get("lines") or [])
                         if ln.get("category") == "hard"), 2)
    gmp = pb.gmp_budget(db, pid)
    gc_gmp = gmp["gmp"].get("revised") or gmp["gmp"]["computed"]
    tot = gmp["totals"]
    return {"dev_hard_cost": dev_hard, "gc_gmp": round(gc_gmp, 2),
            "delta": round(gc_gmp - dev_hard, 2), "in_sync": abs(gc_gmp - dev_hard) < 1.0,
            "gmp_committed": tot["committed"], "gmp_eac": tot.get("eac", tot["forecast"]),
            "gmp_variance_at_completion": tot["variance"]}


@router.post("/projects/{pid}/dev-budget/sync-gmp")
def sync_gmp_to_hard(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("editor"))):
    """Set the developer budget's construction hard cost to the GC's GMP — one click ties the
    underwriting to the live construction number. Replaces hard lines with a single synced GMP line;
    soft / acquisition / contingency are untouched. Returns the recomputed budget summary."""
    from .. import dev_budget as dvb
    from .. import project_budget as pb
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    gmp = pb.gmp_budget(db, pid)
    gc_gmp = round(gmp["gmp"].get("revised") or gmp["gmp"]["computed"], 2)
    budget = dict(p.dev_budget or dvb.starter_budget())
    lines = [dict(ln) for ln in (budget.get("lines") or []) if ln.get("category") != "hard"]
    lines.append({"category": "hard", "description": "Construction — GC GMP (synced)",
                  "unit_cost": gc_gmp, "quantity": 1, "cost_code": ""})
    budget["lines"] = lines
    p.dev_budget = budget
    db.commit()
    return {"synced": True, "hard_cost": gc_gmp, "budget": budget, "summary": dvb.summarize(budget)}


@router.get("/projects/{pid}/loan-draws")
def loan_draws(pid: str, ltc: float = 0.65, rate: float = 0.075, construction_months: int = 18,
               db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Construction-loan draw status from the GC's actual billing: owner invoices are the developer's
    draws to pay the GC, funded equity-first then debt. Returns the sized loan/equity (from Sources &
    Uses) vs drawn-to-date, the equity/loan split, and remaining loan availability — so the developer
    tracks the capital stack against what the contractor has actually billed."""
    from .. import dev_budget as dvb
    from .. import modules as _me
    from .. import sources_uses as su
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    from datetime import date as _date

    from .. import project_budget as _pb
    sumry = dvb.summarize(p.dev_budget or dvb.starter_budget())
    cap = su.build(sumry, {"ltc": ltc, "rate": rate, "construction_months": construction_months})
    debt, equity = float(cap["debt"]), float(cap["equity"])
    budgeted_interest = round(sum(float(u["amount"]) for u in cap.get("uses", [])
                                  if "interest" in str(u.get("label", "")).lower()), 2)
    invs = _me.list_records(db, "owner_invoice", pid, limit=1_000_000) if "owner_invoice" in _me.TABLES else []
    drawn = round(sum(float((r.get("data") or {}).get("amount") or 0) for r in invs), 2)
    equity_drawn = round(min(drawn, equity), 2)        # equity-first funding
    loan_drawn = round(max(0.0, drawn - equity), 2)

    # accrued interest on the OUTSTANDING loan balance — simple interest per tranche from its draw
    # date (the invoice period if a date, else the record's created_at) to today. Equity-funded
    # draws don't accrue; only the portion of each draw that lands on the loan does.
    today = _date.today()
    ordered = sorted(invs, key=lambda r: str(r.get("created_at") or ""))
    cum = 0.0
    accrued = 0.0
    loan_start = None
    for r in ordered:
        amt = float((r.get("data") or {}).get("amount") or 0)
        if amt <= 0:
            continue
        prev, cum = cum, cum + amt
        loan_portion = max(0.0, cum - equity) - max(0.0, prev - equity)
        if loan_portion <= 0:
            continue
        cd = r.get("created_at")
        dd = _pb._pdate((r.get("data") or {}).get("period")) or (cd.date() if hasattr(cd, "date") else None) or today
        loan_start = dd if loan_start is None else min(loan_start, dd)
        accrued += loan_portion * rate * max(0, (today - dd).days) / 365
    accrued = round(accrued, 2)

    # interest re-forecast: actual accrued-to-date + projected remaining carry, vs the underwritten
    # reserve — so the developer sees if the live carrying cost is tracking the underwriting. The
    # already-drawn loan balance carries the full remaining build; remaining draws ramp (avg ½ period).
    elapsed_m = ((today - loan_start).days / 30.4) if loan_start else 0.0
    remaining_m = max(0.0, construction_months - elapsed_m)
    remaining_loan = max(0.0, debt - loan_drawn)
    remaining_interest = (loan_drawn * rate * remaining_m / 12
                          + remaining_loan * rate * (remaining_m / 2) / 12)
    forecast_interest = round(accrued + remaining_interest, 2)
    interest_variance = round(budgeted_interest - forecast_interest, 2)   # +ve = under reserve (good)

    return {"loan_amount": round(debt, 2), "equity": round(equity, 2), "drawn_to_date": drawn,
            "equity_drawn": equity_drawn, "loan_drawn": loan_drawn,
            "loan_available": round(debt - loan_drawn, 2), "loan_balance": loan_drawn,
            "pct_capital_drawn": round(drawn / (debt + equity) * 100, 1) if (debt + equity) else 0.0,
            "interest_rate": rate, "accrued_interest": accrued,
            "loan_start": loan_start.isoformat() if loan_start else None,
            "outstanding_with_interest": round(loan_drawn + accrued, 2),
            "budgeted_interest_reserve": budgeted_interest,
            "forecast_interest": forecast_interest,
            "interest_variance": interest_variance,
            "invoice_count": len(invs)}


@router.get("/projects/{pid}/loan-draws/request.pdf")
def loan_draw_request_pdf(pid: str, app_no: int = 1, ltc: float = 0.65, rate: float = 0.075,
                          db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """The lender draw-request as a PDF — this draw (the GC pay-app amount due) against the
    construction loan, with cumulative draws, equity/loan split, balance, and availability."""
    from fastapi import Response

    from .. import cost as cost_engine
    from .. import report
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    draw = loan_draws(pid, ltc=ltc, rate=rate, db=db)
    draw["this_draw"] = round(float(cost_engine.g702(db, pid, app_no=app_no)["line8_current_payment_due"]), 2)
    pdf = report.draw_request_pdf(db, pid, p.name, draw, app_no=app_no)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="draw-request-{app_no}.pdf"'})


@router.get("/projects/{pid}/construction-draws")
def construction_draws(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """The developer's construction draw schedule, sourced from the GC's cost-loaded schedule (the
    same monthly S-curve behind on-schedule × on-budget) and actual owner invoices billed to date —
    so the developer's draw projection is the contractor's real plan, not a generic curve."""
    from .. import modules as _me
    from .. import project_budget as pb
    from ..models import Project as _P
    if db.get(_P, pid) is None:
        raise HTTPException(404, "project not found")
    cf = pb.cashflow(db, pid)
    invs = _me.list_records(db, "owner_invoice", pid, limit=1_000_000) if "owner_invoice" in _me.TABLES else []
    billed = round(sum(pb._n((r.get("data") or {}).get("amount")) for r in invs), 2)

    # per-cost-code draw composition — what the construction draw is *for*, from the SOV's
    # completed-to-date grouped by cost code (the draw rides the same budget-seeded SOV lines)
    cc_meta = {r["id"]: (r.get("data") or {}) for r in _me.list_records(db, "cost_code", pid, limit=1_000_000)} \
        if "cost_code" in _me.TABLES else {}
    by_cc: dict[str, dict] = {}
    for r in (_me.list_records(db, "sov", pid, limit=1_000_000) if "sov" in _me.TABLES else []):
        d = r.get("data") or {}
        completed = pb._n(d.get("completed_prev")) + pb._n(d.get("completed_this")) + pb._n(d.get("materials_stored"))
        if completed <= 0:
            continue
        cc = d.get("cost_code")
        meta = cc_meta.get(cc, {})
        key = meta.get("code") or d.get("description") or "Uncoded"
        b = by_cc.setdefault(key, {"code": key, "description": meta.get("description") or d.get("description"),
                                   "division": meta.get("division"), "billed": 0.0})
        b["billed"] = round(b["billed"] + completed, 2)
    cost_code_draws = sorted(by_cc.values(), key=lambda x: -x["billed"])

    return {"projected_total": cf["total"], "months": cf["months"], "peak_month_cost": cf["peak_month_cost"],
            "series": cf["series"], "actual_billed": billed, "invoice_count": len(invs),
            "pct_billed": round(billed / cf["total"] * 100, 1) if cf["total"] else 0.0,
            "by_cost_code": cost_code_draws}


@router.get("/projects/{pid}/dev-budget/cost-lines")
def dev_budget_cost_lines(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """The budget rolled into proforma cost_lines (the seed the Finance view applies)."""
    from .. import dev_budget as dvb
    from ..models import Project as _P
    p = db.get(_P, pid)
    if not p:
        raise HTTPException(404, "project not found")
    budget = p.dev_budget or dvb.starter_budget()
    return {"cost_lines": dvb.to_cost_lines(budget), "summary": dvb.summarize(budget)}


@router.get("/projects/{pid}/proforma/model-metrics")
def proforma_model_metrics(pid: str, db: Session = Depends(get_db), _sec: str = Depends(rbac.require_role("viewer"))):
    """Metrics from the project's source IFC, so the proforma can underwrite against the real
    model (areas → hard cost / rent, etc.) instead of hand-keyed numbers. 409 if no source IFC."""
    from aec_data import drawings as dr
    from aec_data import spaces as sp
    from aec_data.ifc_loader import open_model  # type: ignore

    from ..deps import source_ifc_path

    model = open_model(source_ifc_path(db, pid))
    rows = sp.space_schedule(model)
    areas = [r["net_area"] for r in rows if r.get("net_area")]
    nfa_m2 = round(sum(areas), 1)
    M2_TO_SF = 10.7639
    return {
        "space_count": len(rows),
        "spaces_with_area": len(areas),
        "storey_count": len(dr.storey_elevations(model)),
        "net_floor_area_m2": nfa_m2,
        "net_floor_area_sf": round(nfa_m2 * M2_TO_SF),
    }


class Axis(BaseModel):
    path: str                       # e.g. "exit.exit_cap" or "cost_lines.1.amount"
    values: list[float]


class SensitivityIn(BaseModel):
    assumptions: Assumptions
    x: Axis
    y: Axis
    metric: str = "returns.equity_irr"


@router.post("/proforma/sensitivity")
def run_sensitivity(body: SensitivityIn):
    """Two-variable data table: the metric solved across the x×y grid of two drivers."""
    return sensitivity(body.assumptions.model_dump(), body.x.path, body.x.values,
                       body.y.path, body.y.values, body.metric)


class Distribution(BaseModel):
    kind: Literal["normal", "uniform", "triangular"]
    mean: float | None = None      # normal
    std: float | None = None       # normal
    low: float | None = None       # uniform / triangular
    high: float | None = None      # uniform / triangular
    mode: float | None = None      # triangular
    min: float | None = None       # optional clamp
    max: float | None = None       # optional clamp


class MonteCarloVar(BaseModel):
    path: str                       # dotted assumption path, e.g. "exit.exit_cap"
    dist: Distribution


class MonteCarloIn(BaseModel):
    assumptions: Assumptions
    variables: list[MonteCarloVar] = Field(min_length=1)
    iterations: int = Field(default=1000, ge=100, le=5000)  # ~3ms/solve → 1000≈3s, 5000≈16s
    seed: int = 42
    metrics: list[str] | None = None       # default: equity/project IRR, multiple, NPV
    targets: dict[str, float] | None = None  # metric → threshold for P[metric ≥ threshold]


@router.post("/proforma/monte-carlo")
def run_monte_carlo(body: MonteCarloIn):
    """Probabilistic risk analysis: sample the given drivers, solve each draw, and return the
    distribution (percentiles, mean/std, P[≥target], histogram) of each output metric."""
    return monte_carlo(body.assumptions.model_dump(),
                       [{"path": v.path, "dist": v.dist.model_dump(exclude_none=True)}
                        for v in body.variables],
                       body.iterations, body.seed, body.metrics, body.targets)


# --- scenarios (persisted, versioned) ---------------------------------------
class ScenarioIn(BaseModel):
    name: str
    project_id: str | None = None
    assumptions: Assumptions


@router.post("/proforma/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, db: Session = Depends(get_db)):
    result = solve(body.assumptions.model_dump())
    s = Scenario(name=body.name, project_id=body.project_id,
                 assumptions=body.assumptions.model_dump(), result=result)
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name, "result": result}


@router.get("/proforma/scenarios")
def list_scenarios(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Scenario)
    if project_id:
        q = q.filter(Scenario.project_id == project_id)
    return [{"id": s.id, "name": s.name, "project_id": s.project_id,
             "returns": (s.result or {}).get("returns")} for s in q.order_by(Scenario.created_at).all()]


def _can_read(db: Session, s: Scenario, user: str) -> bool:
    """RBAC off → open. RBAC on → the scenario owner's project members or LPs it's shared with."""
    if not rbac.RBAC_ON:
        return True
    if user in (s.shared_with or []):
        return True
    if s.project_id and rbac.role_for(db, s.project_id, user) is not None:
        return True
    return False


@router.get("/proforma/scenarios/{sid}")
def get_scenario(sid: str, db: Session = Depends(get_db), user: str = Depends(current_user)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    if not _can_read(db, s, user):
        raise HTTPException(403, "not shared with you")
    return {"id": s.id, "name": s.name, "assumptions": s.assumptions, "result": s.result,
            "shared_with": s.shared_with or []}


@router.post("/proforma/scenarios/{sid}/share", status_code=201)
def share_scenario(sid: str, user: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Grant an LP (or any party) read access to this scenario."""
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    s.shared_with = sorted(set((s.shared_with or []) + [user]))
    db.commit()
    return {"id": s.id, "shared_with": s.shared_with}


@router.put("/proforma/scenarios/{sid}")
def update_scenario(sid: str, body: ScenarioIn, db: Session = Depends(get_db)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    if s.is_locked:
        raise HTTPException(409, "scenario is locked")
    s.assumptions = body.assumptions.model_dump()
    s.name = body.name
    s.result = solve(s.assumptions)
    db.commit()
    return {"id": s.id, "name": s.name, "result": s.result}


@router.post("/proforma/scenarios/{sid}/clone", status_code=201)
def clone_scenario(sid: str, name: str = Body(..., embed=True), db: Session = Depends(get_db)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    c = Scenario(name=name, project_id=s.project_id, assumptions=s.assumptions, result=s.result)
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name}


class Actual(BaseModel):
    actual_to_date: float = 0
    committed: float = 0
    cost_to_complete: float | None = None


class ForecastIn(BaseModel):
    actuals: list[Actual]
    as_of_month: int = 0


@router.post("/proforma/scenarios/{sid}/forecast")
def forecast_scenario(sid: str, body: ForecastIn, db: Session = Depends(get_db)):
    """Re-forecast the underwritten returns against actuals drawn to date (Phase 5 bridge)."""
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    return reforecast(s.assumptions, [a.model_dump() for a in body.actuals], body.as_of_month)


@router.post("/proforma/forecast")
def forecast_stateless(assumptions: Assumptions, actuals: list[Actual] = Body(...),
                       as_of_month: int = Body(0)):
    return reforecast(assumptions.model_dump(), [a.model_dump() for a in actuals], as_of_month)


class DrawPackageIn(BaseModel):
    project_id: str                 # the GC portal project to receive the SOV
    actuals: list[Actual]
    as_of_month: int = 0
    retainage_pct: float = 5.0
    app_no: int = 1


@router.post("/proforma/scenarios/{sid}/draw-package")
def draw_package(sid: str, body: DrawPackageIn, db: Session = Depends(get_db)):
    """Bridge underwriting → construction draws: turn the scenario's cost tree + actuals into
    Schedule-of-Values records on a GC project, then produce the AIA G702/G703 pay app —
    so the IRR you underwrote and the lender draw run off the SAME cost tree."""
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    if "sov" not in me.TABLES:
        raise HTTPException(409, "SOV module not loaded")
    fc = reforecast(s.assumptions, [a.model_dump() for a in body.actuals], body.as_of_month)
    pid = body.project_id
    # replace any prior SOV for this project so re-running is idempotent
    db.execute(delete(me.TABLES["sov"]).where(me.TABLES["sov"].c.project_id == pid))
    db.commit()
    for i, L in enumerate(fc["lines"]):
        me.create_record(db, "sov", pid, {"data": {
            "item_no": f"{i + 1:02d}", "description": L["name"], "cost_code": L["category"],
            "scheduled_value": L["forecast_at_completion"],   # revised contract value
            "completed_this": L["actual_to_date"],
            "retainage_pct": body.retainage_pct,
        }}, "proforma-bridge", "GC")
    g703 = cost_engine.g703(db, pid)
    g702 = cost_engine.g702(db, pid, app_no=body.app_no)
    return {
        "sov_lines_created": len(fc["lines"]),
        "g702": g702, "g703_totals": g703["totals"],
        "g702_pdf": f"/projects/{pid}/cost/g702.pdf?app_no={body.app_no}",
        "forecast_returns": fc["forecast_returns"],
    }


@router.get("/proforma/portfolio")
def portfolio(db: Session = Depends(get_db), user: str = Depends(rbac.current_user)):
    """Multi-deal roll-up across all solved scenarios: total capitalization, equity-weighted
    blended IRR, aggregate equity multiple, and per-deal metrics. Scoped to the caller's projects
    so the roll-up never blends other tenants' deals."""
    from collections import defaultdict
    from datetime import date as _date

    from ..proforma.returns import xirr

    allowed = rbac.member_project_ids(db, user)   # None = no restriction (dev / api-key)
    scens = [s for s in db.query(Scenario).order_by(Scenario.created_at).all()
             if s.result and (allowed is None or s.project_id in allowed)]
    deals = []
    tot_uses = tot_equity = tot_debt = 0.0
    w_eq = w_irr = 0.0
    tot_contrib = tot_dist = 0.0
    combined: dict = defaultdict(float)   # date -> summed equity cash flow across deals
    for s in scens:
        cf = s.result.get("cash_flow", {})
        for d, amt in zip(cf.get("dates", []), cf.get("equity", [])):
            combined[d] += float(amt)
        su = s.result.get("sources_uses", {})
        ret = s.result.get("returns", {})
        eq = float(su.get("equity", 0))
        tot_uses += float(su.get("total_uses", 0))
        tot_equity += eq
        tot_debt += float(su.get("loan_amount", 0))
        tot_contrib += float(ret.get("total_contributions", 0))
        tot_dist += float(ret.get("total_distributions", 0))
        eirr = ret.get("equity_irr")
        if eirr is not None:
            w_eq += eq; w_irr += eirr * eq
        deals.append({
            "id": s.id, "name": s.name, "project_id": s.project_id,
            "total_uses": round(float(su.get("total_uses", 0)), 0),
            "equity": round(eq, 0), "loan": round(float(su.get("loan_amount", 0)), 0),
            "equity_irr": eirr, "equity_multiple": ret.get("equity_multiple"),
        })
    # true portfolio IRR: XIRR on the combined dated equity cash flows across all deals
    combined_cf = sorted((_date.fromisoformat(d), v) for d, v in combined.items())
    portfolio_irr = xirr(combined_cf) if len(combined_cf) > 1 else None
    return {
        "deal_count": len(deals),
        "totals": {
            "total_capitalization": round(tot_uses, 0),
            "total_equity": round(tot_equity, 0),
            "total_debt": round(tot_debt, 0),
            "blended_ltc": round(tot_debt / tot_uses, 3) if tot_uses else 0,
            "portfolio_irr": round(portfolio_irr, 4) if portfolio_irr is not None else None,
            "blended_equity_irr": round(w_irr / w_eq, 4) if w_eq else None,
            "portfolio_equity_multiple": round(tot_dist / tot_contrib, 3) if tot_contrib else 0,
        },
        "deals": deals,
    }


@router.post("/proforma/compare")
def compare(ids: list[str] = Body(...), db: Session = Depends(get_db)):
    """Side-by-side metrics for several scenarios."""
    out = []
    for sid in ids:
        s = db.get(Scenario, sid)
        if s and s.result:
            out.append({"id": s.id, "name": s.name, "returns": s.result.get("returns"),
                        "sources_uses": s.result.get("sources_uses")})
    return out
