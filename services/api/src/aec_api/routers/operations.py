"""Operations-phase endpoints — CMMS (PM generation + KPIs), energy (EUI/trends + bridge status),
reserve study / capital plan, and CAM reconciliation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from sqlalchemy.orm import Session

from .. import audit, cam, cmms, energy, energy_star_bridge, esg, reserve, twin
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

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
def cmms_kpis(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Maintenance KPIs: open by priority/type, overdue, PM compliance %, MTTR (days)."""
    _project(db, pid)
    return cmms.kpis(db, pid)


@router.get("/projects/{pid}/energy/actual")
def energy_summary(pid: str, gfa_sf: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(current_user)):
    """Operational (metered) energy rollup: site kBtu + cost by utility, monthly trend, water, and EUI
    (kBtu/sf/yr) using the model's GFA when loaded — or pass ?gfa_sf= explicitly. Distinct from
    GET /projects/{pid}/energy, which is the design-model simulation."""
    _project(db, pid)
    gfa = gfa_sf or energy.project_gfa_sf(db, pid)
    return energy.summary(db, pid, gfa_sf=gfa)


@router.get("/projects/{pid}/twin/readiness")
def twin_readiness(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
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
                _: str = Depends(current_user)):
    """Asset ESG rollup: metered energy (EUI), GHG Scope 1/2 from the local factor table, water,
    certification tracking, and the POE actual-vs-design EUI comparison."""
    _project(db, pid)
    gfa = gfa_sf or energy.project_gfa_sf(db, pid)
    return esg.summary(db, pid, gfa_sf=gfa)


@router.get("/projects/{pid}/reserves/study")
def reserve_study(pid: str, horizon_years: int = 25, opening_balance: float = 0.0,
                  annual_contribution: float = 0.0, inflation_pct: float = 0.0,
                  db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Reserve study: recurring replacement events (asset register install + expected life +
    replacement cost, plus open capital-plan items), year-by-year balance trajectory, first
    underfunded year, and the suggested level annual contribution."""
    _project(db, pid)
    return reserve.study(db, pid, horizon_years=horizon_years, opening_balance=opening_balance,
                         annual_contribution=annual_contribution, inflation_pct=inflation_pct)


@router.get("/projects/{pid}/cam/reconciliation")
def cam_reconciliation(pid: str, year: int | None = None, gross_up_to_pct: float = 95.0,
                       building_sf: float | None = None, db: Session = Depends(get_db),
                       _: str = Depends(current_user)):
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
