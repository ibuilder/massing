"""Operations-phase endpoints — CMMS (PM generation + KPIs), energy (EUI/trends + bridge status),
reserve study / capital plan, and CAM reconciliation."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import audit, cam, cmms, deal_funnel, deal_memory, energy, energy_star_bridge, esg, fca, reserve, twin
from ..db import get_db
from ..models import Project
from ..rbac import current_user, member_project_ids, require_identified, require_role

router = APIRouter()


def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.post("/projects/{pid}/cmms/generate-pm")
def generate_pm(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("reviewer"))):
    """Create preventive work orders for every active PM schedule that's due (idempotent per cycle:
    a schedule with an open PM work order is skipped); advances each schedule's next-due date."""
    _project(db, pid)
    out = cmms.generate_pm(db, pid, actor)
    audit.record(db, action="cmms.generate_pm", actor=actor, method="POST",
                 path=f"/projects/{pid}/cmms/generate-pm", detail={"generated": out["generated"]})
    db.commit()
    return out


@router.get("/projects/{pid}/cmms/kpis")
def cmms_kpis(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Maintenance KPIs: open by priority/type, overdue, PM compliance %, MTTR (days)."""
    _project(db, pid)
    return cmms.kpis(db, pid)


@router.get("/projects/{pid}/energy/actual")
def energy_summary(pid: str, gfa_sf: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Operational (metered) energy rollup: site kBtu + cost by utility, monthly trend, water, and EUI
    (kBtu/sf/yr) using the model's GFA when loaded — or pass ?gfa_sf= explicitly. Distinct from
    GET /projects/{pid}/energy, which is the design-model simulation."""
    _project(db, pid)
    gfa = gfa_sf or energy.project_gfa_sf(db, pid)
    return energy.summary(db, pid, gfa_sf=gfa)


@router.get("/projects/{pid}/twin/readiness")
def twin_readiness(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Digital-twin + Digital Product Passport readiness: asset↔system linkage, sensor mapping,
    product-passport completeness, and the building-system graph."""
    _project(db, pid)
    return twin.readiness(db, pid)


@router.get("/energy/benchmark-status")
def benchmark_status(_: str = Depends(current_user)):
    """Whether an external benchmarking sync (EPA Portfolio Manager) is configured; local EUI/trends
    work without it."""
    return energy_star_bridge.status()


@router.get("/projects/{pid}/esg")
def esg_summary(pid: str, gfa_sf: float | None = None, db: Session = Depends(get_db),
                _: str = Depends(require_role("viewer"))):
    """Asset ESG rollup: metered energy (EUI), GHG Scope 1/2 from the local factor table, water,
    certification tracking, and the POE actual-vs-design EUI comparison."""
    _project(db, pid)
    gfa = gfa_sf or energy.project_gfa_sf(db, pid)
    return esg.summary(db, pid, gfa_sf=gfa)


@router.get("/projects/{pid}/reserves/study")
def reserve_study(pid: str, horizon_years: int = 25, opening_balance: float = 0.0,
                  annual_contribution: float = 0.0, inflation_pct: float = 0.0,
                  db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Reserve study: recurring replacement events (asset register install + expected life +
    replacement cost, plus open capital-plan items), year-by-year balance trajectory, first
    underfunded year, and the suggested level annual contribution."""
    _project(db, pid)
    return reserve.study(db, pid, horizon_years=horizon_years, opening_balance=opening_balance,
                         annual_contribution=annual_contribution, inflation_pct=inflation_pct)


@router.get("/projects/{pid}/fca/index")
def fca_index(pid: str, crv: float | None = None, gfa_sf: float | None = None,
              db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Facility Condition Index: FCI = (deferred maintenance + capital renewal) / current replacement
    value, with the band, the deferred/renewal split, and breakdowns by UNIFORMAT group, condition
    rating, worst elements, and recommended-year forecast — over the `fca_element` records."""
    _project(db, pid)
    gfa = gfa_sf or energy.project_gfa_sf(db, pid)
    return fca.index(db, pid, crv=crv, gfa_sf=gfa)


@router.get("/fca/portfolio")
def fca_portfolio(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Facility Condition Index per project across the portfolio, worst-first — the capital-
    prioritization view (fund the highest-FCI buildings first). Scoped to the caller's projects."""
    return fca.portfolio(db, project_ids=member_project_ids(db, user))


@router.get("/portfolio/deal-memory")
def portfolio_deal_memory(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """R35-DEAL-MEMORY: this operator's own closed projects as a comp set, scoped to their projects.

    The least commoditised layer in an underwriting stack, because it is made of the firm's own
    history and cannot be bought. It is also the easiest place here to manufacture a flattering
    number, so the engine reports only measurements that sit in a **different record** from the plan
    they are compared against — cost budget vs actual, planned finish vs actual finish.

    **`exit_cap_achieved` and `lease_up_months` are returned as `no_recorded_source`, not computed.**
    Nothing in this system records a realised exit cap or a lease-up actual; the only exit cap
    present is the ASSUMED one on a scenario. Reading that back as the realised value would compare
    a number to itself and report perfect underwriting accuracy forever — and that figure would then
    be used to justify the next deal. The refusal names what would have to be captured instead.

    Under the sample floor a metric reports `insufficient_history` rather than a distribution, and a
    project with no actual spend is excluded and counted rather than averaged in as zero variance,
    which would drag every distribution toward "we were exactly right".
    """
    return deal_memory.comps(db, project_ids=member_project_ids(db, user))


@router.get("/pipeline/funnel")
def pipeline_funnel(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """R22-PIPELINE: the acquisition funnel across the caller's projects — stage counts and value,
    conversion, probability-weighted value, cycle time and the data-quality tells.

    Acquisition is a funnel, not a project. `/portfolio/executive` answers "how are the deals we
    *won* doing?"; this answers the question upstream of it — what is in the book, how much of it
    historically closes, and how long it takes.

    **The weighted value is derived from this firm's own closed deals, never from a textbook
    ladder.** A stage without enough closed history reports `insufficient_history` and its deals are
    excluded from the headline **and counted**, with `coverage` stating what fraction of the book the
    number actually covers. That is the whole point: a weighted pipeline figure is a guess about
    conversion multiplied by real money and read as a forecast, so a partial number that says it is
    partial beats a complete one that quietly used somebody else's conversion rates.

    Cycle time is reported as closed-deal duration *beside* open-deal age and never blended — the
    deals still open are the slow ones, so a closed-only mean understates exactly when it is being
    used to promise a closing date.
    """
    return deal_funnel.from_projects(db, project_ids=member_project_ids(db, user))


@router.post("/pipeline/allocate")
def pipeline_allocate_route(body: dict = Body(...),
                            _user: str = Depends(require_identified)):
    """R31-PIPELINE-ALLOCATE: given candidate projects with a cost and a value, and a capital
    constraint, **which subset** — an exact integer optimum, not a ranking.

    The route above ranks projects worst-first and advises funding those first. That is a greedy
    heuristic, and greedy loses whenever one high-ratio project crowds out two smaller ones that
    together beat it. This returns the optimal set, what it displaced, and what greedy would have
    chosen, so the difference between the two decisions is visible rather than asserted.

    Body: `{candidates: [{id, name?, cost, value}], capital: number}`. **`value` is supplied by the
    caller** — NPV, profit, risk-adjusted return, whatever the committee is maximising. This endpoint
    does not infer it from project data: a value nobody stated is the one number that must not be
    invented here, since it decides what gets funded.
    """
    from .. import pipeline_allocate as pa

    try:
        return pa.allocate(body.get("candidates") or [], body.get("capital"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/projects/{pid}/cam/reconciliation")
def cam_reconciliation(pid: str, year: int | None = None, gross_up_to_pct: float = 95.0,
                       building_sf: float | None = None, db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    """CAM true-up for an operating year: recoverable pool (variable lines grossed up to the stated
    occupancy), per-tenant pro-rata share vs estimated payments, balance due/credit."""
    _project(db, pid)
    return cam.reconciliation(db, pid, year=year, gross_up_to_pct=gross_up_to_pct,
                              building_sf=building_sf)


@router.get("/projects/{pid}/cam/statement/{rid}.pdf")
def cam_statement(pid: str, rid: str, year: int | None = None, gross_up_to_pct: float = 95.0,
                  building_sf: float | None = None, db: Session = Depends(get_db),
                  actor: str = Depends(require_role("reviewer"))):
    """Per-tenant CAM reconciliation statement (PDF) for the lease record `rid`."""
    p = _project(db, pid)
    recon = cam.reconciliation(db, pid, year=year, gross_up_to_pct=gross_up_to_pct,
                               building_sf=building_sf)
    row = next((t for t in recon["tenants"] if t["id"] == rid or t["ref"] == rid), None)
    if not row:
        raise HTTPException(404, "lease not found in the reconciliation (needs rentable_sf)")
    pdf = cam.statement_pdf(recon, row, p.name or pid)
    audit.record(db, action="cam.statement", actor=actor, method="GET",
                 path=f"/projects/{pid}/cam/statement/{rid}.pdf", detail={"year": recon["year"]})
    db.commit()
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="cam-statement-{row["ref"]}-{recon["year"]}.pdf"'})
