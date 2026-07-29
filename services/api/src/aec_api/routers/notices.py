"""R22-NOTICE-CLOCK — the contractual notice register (project-scoped).

Reads the field record already in the platform (daily reports, change events, RFIs), finds the
events a contract requires notice of, and counts the days remaining under the contract family the
project has adopted on its prime contract record.

The adopted family is read from `prime_contract.notice_family`, not from a server default. A `family`
query parameter overrides it for a what-if, and is reported back as an override so a register read
under a different contract than the executed one is never mistaken for the real one.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import modules as me
from .. import notice_clock as nc
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


def _calendar(weekend: str | None, holidays: str | None) -> nc.Calendar:
    try:
        return nc.parse_calendar(weekend, holidays)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _adopted(db: Session, pid: str) -> tuple[str | None, str | None]:
    """(resolved family id, the raw value it came from) from the project's prime contract."""
    if "prime_contract" not in me.TABLES:
        return None, None
    rows = me.list_records(db, "prime_contract", pid, limit=1)
    raw = ((rows[0].get("data") if rows else None) or {}).get("notice_family")
    return nc.resolve_family(raw), raw


def _records(db: Session, key: str, limit: int, pid: str) -> list[dict]:
    return me.list_records(db, key, pid, limit=limit) if key in me.TABLES else []


@router.get("/projects/{pid}/notices/clauses")
def notice_clauses(pid: str, family: str | None = None, event_type: str | None = None,
                   db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The notice-provision library: contract families, their clauses, periods and citations.

    These are the standard provisions of the unamended forms. They exist so a project can adopt one
    and see what it is being measured against — not as a statement of what any particular contract
    says."""
    fam = nc.resolve_family(family) if family else None
    if family and not fam:
        raise HTTPException(422, f"unknown contract family {family!r}; "
                                 f"known: {', '.join(sorted(nc.FAMILIES))}")
    if event_type and event_type not in nc.EVENT_TYPES:
        raise HTTPException(422, f"unknown event type {event_type!r}; "
                                 f"known: {', '.join(nc.EVENT_TYPES)}")
    picked = [c for c in nc.CLAUSES
              if (fam is None or c.family == fam)
              and (event_type is None or event_type in c.event_types)]
    return {
        "families": [{"id": k, "label": v} for k, v in sorted(nc.FAMILIES.items())],
        "event_types": list(nc.EVENT_TYPES),
        "consequences": nc.CONSEQUENCES,
        "clauses": [{
            "id": c.id, "family": c.family, "family_label": nc.FAMILIES[c.family],
            "reference": c.reference, "event_types": list(c.event_types),
            "days": c.days, "basis": c.basis, "starts_on": c.starts_on,
            "consequence": c.consequence, "notify": c.notify, "citation": c.citation,
        } for c in picked],
        "verify": "verify every provision against the executed contract before relying on a date — "
                  "an amended sub-clause changes the number and this library cannot know it was amended",
    }


@router.get("/projects/{pid}/notices")
def notice_register(
    pid: str,
    family: str | None = None,
    as_of: str | None = None,
    due_soon_days: int = Query(7, ge=1, le=90),
    weekend: str | None = Query(None, description="e.g. 'Fri,Sat' — defaults to Sat,Sun"),
    holidays: str | None = Query(None, description="comma-separated YYYY-MM-DD public holidays"),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: str = Depends(require_role("viewer")),
):
    """The notice register: every triggering event in the field record against every notice provision
    of the adopted contract family, expired first.

    With no family adopted this returns an empty register and says why rather than picking one — a
    deadline computed under the wrong contract looks exactly like a deadline computed under the right
    one."""
    adopted, raw = _adopted(db, pid)
    override = nc.resolve_family(family) if family else None
    if family and not override:
        raise HTTPException(422, f"unknown contract family {family!r}; "
                                 f"known: {', '.join(sorted(nc.FAMILIES))}")
    used = override or adopted

    events = nc.detect(
        daily_reports=_records(db, "daily_report", limit, pid),
        change_events=_records(db, "change_event", limit, pid),
        rfis=_records(db, "rfi", limit, pid),
    )
    out = nc.scan(events, used, today=as_of, calendar=_calendar(weekend, holidays),
                  due_soon_days=due_soon_days)
    out["events_found"] = len(events)
    out["adopted_family"] = adopted
    out["adopted_raw"] = raw
    if override and override != adopted:
        out["override"] = {
            "family": override,
            "note": "computed under a family other than the one adopted on the prime contract — "
                    "this is a what-if, not the project's contractual position",
        }
    return out


@router.post("/projects/{pid}/notices/draft")
def notice_draft(
    pid: str,
    item: dict = Body(..., description="one item from GET /projects/{pid}/notices"),
    from_party: str = "the Contractor",
    to_party: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_role("editor")),
):
    """Draft the notice letter for one register item.

    Stateless — post back the item you were given, the same shape the register returns. It quotes the
    clause rather than paraphrasing it, leaves the signature block unfilled, and when the item's date
    is a *reported* date rather than a recorded occurrence it says so inside the letter, because the
    date in a notice is the part that gets tested."""
    if not isinstance(item, dict) or not isinstance(item.get("event"), dict):
        raise HTTPException(422, "item must be one element of the `items` array from "
                                 "GET /projects/{pid}/notices")
    if not item["event"].get("date"):
        raise HTTPException(422, "the item's event has no date; nothing can be drafted from it")
    from .. import models
    project = db.get(models.Project, pid)
    return {
        "letter": nc.draft(item, project=(project.name if project else pid),
                           from_party=from_party, to_party=to_party or ""),
        "clause": item.get("clause"),
        "due_date": item.get("due_date"),
        "status": item.get("status"),
    }
