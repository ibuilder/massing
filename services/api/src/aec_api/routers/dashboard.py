"""Role-tailored dashboard endpoint (GC portal)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import ai, dashboard, mailer, oauth, rbac, report
from .. import modules as me
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/dashboard")
def get_dashboard(pid: str, party: str | None = None, db: Session = Depends(get_db),
                  user: str = Depends(require_role("viewer"))):
    """Dashboard tailored to `party` (defaults to the caller's project party role)."""
    party = party or rbac.party_role_for(db, pid, user) or "GC"
    return dashboard.build(db, pid, party)


_RECORDABLE = {"Recordable", "Lost Time", "Fatality"}
_LOST_TIME = {"Lost Time", "Fatality"}


@router.get("/projects/{pid}/safety/metrics")
def safety_metrics(pid: str, hours: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Safety analytics: incidents by OSHA class, recordable/lost-time counts, lost days, and
    TRIR/DART (per 200k hours) using `hours` or hours summed from timesheets + manpower logs."""
    incs = me.list_records(db, "incident", pid, limit=1_000_000)
    by_class: dict[str, int] = {}
    recordable = lost_time = lost_days = 0
    for r in incs:
        d = r.get("data") or {}
        cls = d.get("classification") or "Unclassified"
        by_class[cls] = by_class.get(cls, 0) + 1
        if cls in _RECORDABLE:
            recordable += 1
        if cls in _LOST_TIME:
            lost_time += 1
        try:
            lost_days += int(float(d.get("lost_days") or 0))
        except (TypeError, ValueError):
            pass
    if hours is None:                              # derive man-hours from the logs if not supplied
        def _sum(key, field):
            return sum(float((x.get("data") or {}).get(field) or 0) for x in me.list_records(db, key, pid, limit=1_000_000))
        hours = _sum("timesheet", "hours") + _sum("manpower_log", "hours")
    trir = round(recordable * 200000 / hours, 2) if hours else None
    dart = round(lost_time * 200000 / hours, 2) if hours else None
    return {"incident_count": len(incs), "by_class": by_class, "recordable_count": recordable,
            "lost_time_count": lost_time, "lost_days": lost_days, "hours_worked": round(hours, 1),
            "trir": trir, "dart": dart,
            "observation_count": len(me.list_records(db, "observation", pid, limit=1_000_000)),
            "toolbox_talk_count": len(me.list_records(db, "toolbox_talk", pid, limit=1_000_000))}


@router.get("/capabilities")
def capabilities():
    """Which optional integrations are wired (for at-a-glance status badges). Not sensitive —
    just feature flags + the configured SSO provider ids."""
    from .. import rbac
    return {"ai": ai.ai_enabled(), "email": mailer.smtp_configured(),
            "sso": [p["id"] for p in oauth.enabled_providers()],
            "local_mode": rbac.LOCAL_MODE}


@router.get("/projects/{pid}/ai/risk-summary")
def risk_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("reviewer"))):
    """AI/rules risk read over the project dashboard (owner/PM reporting)."""
    d = dashboard.build(db, pid, "GC")
    return {**ai.risk_summary(d.get("kpis", {}), d.get("cost")), "ai_enabled": ai.ai_enabled()}


@router.get("/projects/{pid}/report.pdf")
def status_report(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """One-page project status report (KPIs, cost, open items by module, ball-in-court) as a PDF."""
    proj = db.get(Project, pid)
    pdf = report.project_status_pdf(db, pid, proj.name if proj else pid)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="status-report.pdf"'})
