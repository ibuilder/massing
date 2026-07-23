"""Market intelligence & cost escalation endpoints (Track M).

Surfaces the regional escalation / labour / location table + the warm-cold sector signal, and escalates a
cost to the construction midpoint for a project — reading the project's `market_assumption` record when
one exists, else query parameters."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import market_intelligence as mi
from .. import modules as me
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

router = APIRouter()


@router.post("/projects/{pid}/feasibility/sellout")
def feasibility_sellout(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """ABSORPTION-SELLOUT — phase revenue by absorption rate → the monthly sell-out curve, months-to-sellout
    (the carry driver), total revenue + carry. Body: `{units, absorption_per_month, avg_price,
    monthly_carry?, start_month?}`. 404 for a missing project."""
    from .. import absorption
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return absorption.sellout(body.get("units"), body.get("absorption_per_month"), body.get("avg_price"),
                              monthly_carry=body.get("monthly_carry") or 0.0,
                              start_month=int(body.get("start_month") or 1))


@router.post("/projects/{pid}/feasibility/lot-supply")
def feasibility_lot_supply(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                           _: str = Depends(require_role("viewer"))):
    """LOT-SUPPLY-INDEX — months of supply = VDL ÷ monthly absorption, as an index vs a balanced-market
    target (100 = equilibrium · > 125 oversupplied · < 75 undersupplied). Body: `{vdl, monthly_absorption,
    equilibrium_months?}`. 404 for a missing project."""
    from .. import absorption
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return absorption.lot_supply_index(body.get("vdl"), body.get("monthly_absorption"),
                                       equilibrium_months=float(body.get("equilibrium_months") or 6.0))


@router.get("/market/snapshot")
def market_snapshot(_: str = Depends(current_user)):
    """The market table — regions (escalation / labour / location index) + the warm/cold sector board."""
    return mi.snapshot()


def _assumption(db: Session, pid: str) -> dict:
    """The project's adopted (else latest) market_assumption fields, or {} if none."""
    try:
        recs = me.list_records(db, "market_assumption", pid, limit=1000)
    except Exception:                             # noqa: BLE001 — module may be absent
        return {}
    if not recs:
        return {}
    adopted = [r for r in recs if r.get("workflow_state") == "adopted"]
    chosen = (adopted or recs)[-1]
    return chosen.get("data") or {}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


@router.get("/projects/{pid}/market/context")
def market_context(pid: str, region: str | None = None, sector: str | None = None,
                   start_year: int | None = None, duration_months: int | None = None,
                   db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The project's market read: regional economics + sector temperature + the escalation factor to its
    construction midpoint. Query params override the project's `market_assumption` record."""
    a = _assumption(db, pid)
    region = region or a.get("region")
    sector = sector or a.get("sector")
    start_year = start_year or _int(a.get("construction_start_year"))
    duration_months = duration_months or _int(a.get("duration_months"))
    ctx = mi.project_context(region, sector, start_year=start_year, duration_months=duration_months)
    ctx["from_assumption"] = bool(a)
    return ctx


@router.get("/projects/{pid}/market/escalate")
def market_escalate(pid: str, amount: float, region: str | None = None,
                    start_year: int | None = None, duration_months: int | None = None,
                    to_year: int | None = None, rate_pct: float | None = None,
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Escalate `amount` to the construction midpoint (or `to_year`) using the region's annual rate —
    for adjusting a base estimate / proforma hard cost to when it will actually be built."""
    a = _assumption(db, pid)
    region = region or a.get("region")
    start_year = start_year or _int(a.get("construction_start_year"))
    duration_months = duration_months or _int(a.get("duration_months"))
    if rate_pct is None and a.get("escalation_override_pct") not in (None, ""):
        rate_pct = float(a["escalation_override_pct"])
    return mi.escalate(amount, region, start_year=start_year, duration_months=duration_months,
                       to_year=to_year, rate_pct=rate_pct)


@router.get("/projects/{pid}/market/exists")
def market_exists(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Whether the project exists (cheap guard used by the panel)."""
    return {"exists": bool(db.get(Project, pid))}
