"""Certified payroll endpoints — weekly WH-347 from timesheets x labor rates."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import modules as me
from .. import payroll, rbac
from ..db import get_db
from ..models import Project

router = APIRouter()


def _week(week_ending: str | None) -> date:
    if week_ending:
        try:
            return datetime.fromisoformat(week_ending[:10]).date()
        except ValueError:
            pass
    return date.today()


def _data(db: Session, pid: str, week_ending: str | None) -> dict:
    ts = me.list_records(db, "timesheet", pid, limit=100000) if "timesheet" in me.TABLES else []
    lr = me.list_records(db, "labor_rate", pid, limit=100000) if "labor_rate" in me.TABLES else []
    return payroll.wh347(ts, lr, _week(week_ending))


@router.get("/projects/{pid}/payroll")
def weekly_payroll(pid: str, week_ending: str | None = None, db: Session = Depends(get_db),
                   _: str = Depends(rbac.require_role("viewer"))):
    """Weekly certified-payroll summary (per worker hours, OT, rate, gross) for the week ending."""
    return _data(db, pid, week_ending)


@router.get("/projects/{pid}/payroll/wh347.pdf")
def wh347_pdf(pid: str, week_ending: str | None = None, db: Session = Depends(get_db),
              _: str = Depends(rbac.require_role("viewer"))):
    """The WH-347 certified-payroll PDF for the week."""
    data = _data(db, pid, week_ending)
    p = db.get(Project, pid)
    pdf = payroll.wh347_pdf(data, p.name if p else pid)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="wh347_{data["week_ending"]}.pdf"'})
