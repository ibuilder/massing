"""Construction analytics — T&M (eTicket) cost rollup + the submittal register."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import (actions as actions_engine, changeorders as co_engine, closeout as closeout_engine,
                dailylog as dailylog_engine, distribution as dist_engine, projecthealth as health_engine,
                quality as quality_engine, rfi as rfi_engine, safety as safety_engine,
                submittals as sub_engine, tm as tm_engine)
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/modules/{key}/{rid}/distribution")
def record_distribution(pid: str, key: str, rid: str, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """Resolve a record's distribution (CC) field against the contact directory → recipients + emails."""
    return dist_engine.for_record(db, pid, key, rid)


@router.get("/projects/{pid}/tm-summary")
def tm_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Time & Material (eTicket) cost rollup — labor/material/equipment, billed vs unbilled."""
    return tm_engine.tm_summary(db, pid)


@router.get("/projects/{pid}/tm-by-change-event")
def tm_by_change_event(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """T&M (eTicket) cost rolled up by the change event each ticket is linked to."""
    return tm_engine.by_change_event(db, pid)


@router.get("/projects/{pid}/change-orders/log")
def co_log(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Change-order log — CO value pipeline (pending/approved/executed), reason mix, schedule exposure."""
    return co_engine.co_log(db, pid)


@router.get("/projects/{pid}/action-items/tracker")
def action_tracker(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Meeting & action-item tracker — open/overdue by assignee & priority, completion, meeting log."""
    return actions_engine.action_tracker(db, pid)


@router.get("/projects/{pid}/health")
def project_health(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Executive project-health rollup — per-domain status, overall score, ranked attention items."""
    return health_engine.project_health(db, pid)


@router.get("/projects/{pid}/closeout/summary")
def closeout_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Closeout analytics — punchlist completion/ball-in-court, commissioning, certificates, warranties, O&M."""
    return closeout_engine.closeout_summary(db, pid)


@router.get("/projects/{pid}/safety/summary")
def safety_summary(pid: str, hours: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Safety analytics — OSHA TRIR/DART/LTIFR, observation mix, toolbox coverage, violations.
    Pass ?hours=<total worker-hours> for exact rates; otherwise estimated from daily-report manpower."""
    return safety_engine.safety_summary(db, pid, hours)


@router.get("/projects/{pid}/daily-reports/summary")
def field_log_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Field-log rollup — manpower trend, weather-impact lost-days, reporting coverage."""
    return dailylog_engine.field_log_summary(db, pid)


@router.get("/projects/{pid}/rfi/register")
def rfi_register(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """RFI register — ball-in-court, overdue, response turnaround, cost/schedule-impact exposure."""
    return rfi_engine.rfi_register(db, pid)


@router.get("/projects/{pid}/quality/summary")
def quality_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Quality dashboard — inspection pass-rate KPIs, NCR disposition/close loop, deficiency ball-in-court."""
    return quality_engine.quality_summary(db, pid)


@router.get("/projects/{pid}/submittals/register")
def submittal_register(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Spec-section submittal register — turnaround, ball-in-court, overdue flags."""
    return sub_engine.submittal_register(db, pid)
