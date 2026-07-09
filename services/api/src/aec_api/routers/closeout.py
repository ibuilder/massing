"""Turnover & draw endpoints (roadmap C/D): multi-period pay-app advance, auto lien waivers, and
warranty expiry tracking. Built on the config-driven module engine + the AIA cost engine."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cost as cost_engine
from .. import modules as me
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


def _parse_date(v) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except ValueError:
        return None


@router.get("/projects/{pid}/warranties/expiring")
def warranties_expiring(pid: str, within_days: int = 90, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """Warranties expiring within `within_days` (and any already expired) — turnover tracking so
    expiries don't lapse silently. Reads the `expires` date on each warranty record."""
    if "warranty" not in me.TABLES:
        raise HTTPException(409, "warranty module not loaded")
    today = date.today()
    horizon = today + timedelta(days=max(0, within_days))
    expiring, expired = [], []
    for r in me.list_records(db, "warranty", pid, limit=1_000_000):
        d = r.get("data") or {}
        exp = _parse_date(d.get("expires"))
        item = {"ref": r.get("ref"), "name": r.get("title") or d.get("name"),
                "vendor": d.get("vendor"), "expires": d.get("expires"),
                "days_left": (exp - today).days if exp else None}
        if exp is None:
            continue
        if exp < today:
            expired.append(item)
        elif exp <= horizon:
            expiring.append(item)
    expiring.sort(key=lambda x: x["days_left"])
    return {"within_days": within_days, "expired": expired, "expiring": expiring,
            "total_warranties": me.count_records(db, "warranty", pid)}


@router.get("/projects/{pid}/compliance/expiring")
def compliance_expiring(pid: str, within_days: int = 30, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """Insurance certificates (COI) and permits expiring within `within_days`, plus any already
    expired — so a super sees lapsing compliance before it bites. Both key off the canonical
    `expires` date; closed permits are ignored."""
    today = date.today()
    horizon = today + timedelta(days=max(0, within_days))
    out: dict[str, list] = {"expired": [], "expiring": []}
    sources = [("coi", "vendor", lambda d: True),
               ("permit", "name", lambda d: str(d.get("status", "")).lower() != "closed")]
    for key, label_field, keep in sources:
        if key not in me.TABLES:
            continue
        for r in me.list_records(db, key, pid, limit=1_000_000):
            d = r.get("data") or {}
            if not keep(d):
                continue
            exp = _parse_date(d.get("expires"))
            if exp is None:
                continue
            item = {"module": key, "ref": r.get("ref"),
                    "name": r.get("title") or d.get(label_field), "expires": d.get("expires"),
                    "days_left": (exp - today).days}
            if exp < today:
                out["expired"].append(item)
            elif exp <= horizon:
                out["expiring"].append(item)
    out["expiring"].sort(key=lambda x: x["days_left"])
    out["expired"].sort(key=lambda x: x["days_left"])
    return {"within_days": within_days, **out,
            "count": len(out["expired"]) + len(out["expiring"])}


@router.post("/projects/{pid}/cost/pay-app/advance")
def payapp_advance(pid: str, db: Session = Depends(get_db),
                   actor: str = Depends(require_role("editor"))):
    """Close the current pay-app period: roll each SOV line's `completed_this` into
    `completed_prev` and zero `completed_this`, so the next G702/G703 application starts a fresh
    period with the prior work correctly shown as previous certificates. Returns the next app no."""
    if "sov" not in me.TABLES:
        raise HTTPException(409, "SOV module not loaded")
    rows = me.list_records(db, "sov", pid, limit=1_000_000)
    if not rows:
        raise HTTPException(409, "no schedule-of-values lines to advance")
    advanced = 0
    for r in rows:
        d = dict(r.get("data") or {})
        this = float(d.get("completed_this") or 0)
        prev = float(d.get("completed_prev") or 0)
        d["completed_prev"] = round(prev + this, 2)
        d["completed_this"] = 0
        me.update_record(db, "sov", pid, r["id"], {"completed_prev": d["completed_prev"],
                                                    "completed_this": 0}, actor, "GC")
        advanced += 1
    next_app = int(max((float((r.get("data") or {}).get("application_no") or 0) for r in rows), default=0)) + 1
    return {"advanced_lines": advanced, "next_application_no": next_app}


@router.post("/projects/{pid}/cost/lien-waiver", status_code=201)
def lien_waiver_from_payapp(pid: str, app_no: int = Body(1, embed=True),
                            vendor: str = Body("", embed=True),
                            waiver_type: str = Body("Conditional Progress", embed=True),
                            db: Session = Depends(get_db),
                            actor: str = Depends(require_role("editor"))):
    """Generate a lien-waiver record for the current pay application — amount = the G702 current
    payment due — so each draw produces its waiver automatically."""
    if "lien_waiver" not in me.TABLES:
        raise HTTPException(409, "lien_waiver module not loaded")
    g702 = cost_engine.g702(db, pid, app_no=app_no)
    amount = round(float(g702.get("line8_current_payment_due") or 0), 2)
    rec = me.create_record(db, "lien_waiver", pid, {"data": {
        "vendor": vendor or "(prime)", "amount": amount, "waiver_type": waiver_type,
        "through_date": date.today().isoformat(),
    }}, actor, "GC")
    return {"lien_waiver": rec, "application_no": app_no, "amount": amount}
