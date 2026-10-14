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


def _expiry_state(v) -> tuple[date | None, str]:
    """The expiry date AND why there is not one: `dated`, `missing` or `unreadable`.

    **This replaced a `date | None`, and the `None` was the defect.** Both windows below used to
    `continue` past it, so a record with no readable expiry left every bucket with nothing said
    about it — and `date | None` cannot say which of two different problems happened:

    * **`missing`** — nobody filled the field in. The record is incomplete and looks incomplete.
    * **`unreadable`** — somebody filled it in and this cannot read it. ``"12/31/2026"`` is the
      ordinary way a US contractor writes a date and `datetime.fromisoformat` raises on it, so the
      record **looks complete to whoever typed it** and silently matches no window. *That is the
      worse of the two, and conflating them is why nobody had ever reported either.*

    Whitespace-only is `missing` rather than `unreadable`: the old `not v` sent `"   "` into
    `fromisoformat`, which raised, which became the same `None` as a blank. One `None`, three
    causes.
    """
    if not v or (isinstance(v, str) and not v.strip()):
        return None, "missing"
    try:
        return datetime.fromisoformat(str(v)[:10]).date(), "dated"
    except ValueError:
        return None, "unreadable"


def _expiry_coverage(population: int, considered: int, missing: int, unreadable: int,
                     skipped: int = 0, skipped_label: str = "") -> dict:
    """What the two windows below did NOT look at, in a shape that RECONCILES to the population.

    `considered + missing + unreadable + skipped == population` is asserted in
    `services/api/test_closeout.py`, and that is the whole design: *coverage that reconciles to the
    population is checkable, and coverage that does not is just another number.* A reader who finds
    an empty `expiring` list can then tell "nothing is lapsing" from "nothing was looked at".

    No boolean. A `complete: true` would be `not missing and not unreadable`, which the caller can
    read off these counts, and a verdict computed here is one the consumer stops thinking about.
    """
    unevaluated = missing + unreadable
    return {
        "population": population, "considered": considered,
        "missing_date": missing, "unreadable_date": unreadable, "unevaluated": unevaluated,
        **({"skipped": skipped, "skipped_reason": skipped_label} if skipped_label else {}),
        "reason": ("no records of this kind exist" if not population
                   else "every record carries a readable expiry date" if not unevaluated
                   else f"{unevaluated} of {population} record(s) were NOT evaluated: "
                        f"{missing} with no expiry date, {unreadable} with a date this server "
                        f"cannot read (expiry dates must be ISO-8601, e.g. 2026-12-31)"),
    }


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
    considered = missing = unreadable = 0
    rows = me.list_records(db, "warranty", pid, limit=1_000_000)
    for r in rows:
        d = r.get("data") or {}
        exp, state = _expiry_state(d.get("expires"))
        if state != "dated":
            missing += state == "missing"
            unreadable += state == "unreadable"
            continue
        considered += 1
        item = {"ref": r.get("ref"), "name": r.get("title") or d.get("name"),
                "vendor": d.get("vendor"), "expires": d.get("expires"),
                "days_left": (exp - today).days}
        if exp < today:
            expired.append(item)
        elif exp <= horizon:
            expiring.append(item)
    expiring.sort(key=lambda x: x["days_left"])
    # `total_warranties` was here on its own, and it made the omission WORSE rather than visible:
    # two empty lists beside a count of 40 reads as "40 warranties on file, none lapsing" when the
    # truth may be that 38 of them carry no readable date. *A reassuring denominator over a subset
    # is a stronger claim than silence.*
    return {"within_days": within_days, "expired": expired, "expiring": expiring,
            "total_warranties": me.count_records(db, "warranty", pid),
            "coverage": _expiry_coverage(len(rows), considered, missing, unreadable)}


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
    population = considered = missing = unreadable = skipped = 0
    for key, label_field, keep in sources:
        if key not in me.TABLES:
            continue
        for r in me.list_records(db, key, pid, limit=1_000_000):
            d = r.get("data") or {}
            population += 1
            if not keep(d):
                skipped += 1            # a CLOSED permit, correctly excluded — but counted, so the
                continue                # four buckets below reconcile to the population
            exp, state = _expiry_state(d.get("expires"))
            if state != "dated":
                missing += state == "missing"
                unreadable += state == "unreadable"
                continue
            considered += 1
            item = {"module": key, "ref": r.get("ref"),
                    "name": r.get("title") or d.get(label_field), "expires": d.get("expires"),
                    "days_left": (exp - today).days}
            if exp < today:
                out["expired"].append(item)
            elif exp <= horizon:
                out["expiring"].append(item)
    out["expiring"].sort(key=lambda x: x["days_left"])
    out["expired"].sort(key=lambda x: x["days_left"])
    # `count` is the reason this mattered: the project-health banner read `if (!cc.count)` and
    # printed "Compliance: no COI/permit expiries ✓" — a tick, over however many certificates
    # carried no readable date. The docstring above says a super should see lapsing compliance
    # "before it bites"; it cannot bite if the date was typed the ordinary American way.
    return {"within_days": within_days, **out,
            "count": len(out["expired"]) + len(out["expiring"]),
            "coverage": _expiry_coverage(population, considered, missing, unreadable,
                                         skipped, "closed permits are not a compliance risk")}


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
