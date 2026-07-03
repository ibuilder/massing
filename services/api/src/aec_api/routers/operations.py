"""Operations-phase endpoints — CMMS (PM generation + KPIs) and energy (EUI/trends + bridge status)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, cmms, energy, energy_star_bridge
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


@router.get("/energy/benchmark-status")
def benchmark_status(_: str = Depends(current_user)):
    """Whether an external benchmarking sync (EPA Portfolio Manager) is configured; local EUI/trends
    work without it."""
    return energy_star_bridge.status()
