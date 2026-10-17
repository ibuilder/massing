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


#: How many records of ONE source the register scans. Bounded because this is a viewer-role GET over
#: three growing registers, and not caller-settable because the bound is a property of the answer's
#: trustworthiness rather than of the request: a caller who passes a small number gets a register
#: that silently omits events, which is the defect below. Twenty thousand per source is four orders
#: of magnitude more than a real project's daily reports and still a bound.
SCAN_CAP = 20_000


def _source_slice(db: Session, key: str, pid: str) -> tuple[list[dict], dict]:
    """The most recent `SCAN_CAP` records of one source, and what that leaves out.

    NOTICE-CLOCK-TRUNC. This read `me.list_records(db, key, pid, limit=limit)` with `limit` a query
    parameter defaulting to **500** — and `list_records` applies `ORDER BY created_at` *ascending*
    before the limit. So the register was computed over the **OLDEST** 500 records of each source,
    and the events whose notice periods are still running are by definition the **newest**. On a
    project with 600 daily reports the hundred most recent were invisible, and the register reported
    "nothing expired" in exactly the words it uses when nothing has expired.

    Three things made it invisible:

    * The engine is careful to a fault — `notice_clock`'s header enumerates three counting traps and
      it refuses rather than guessing on every one of them. *A guard is only as sound as the evidence
      it is handed, and nothing was checking the evidence.*
    * The response carried `events_found`, the number of triggering events DETECTED, which reads as
      the number there is.
    * Every other engine over these same tables passes `limit=100000` — `changeorders`, `dailylog`,
      `resilience`, `selections`, `tm`. This one route was the exception, on the one register where
      a missed recent event is a forfeited claim.

    The repository's own hardening checklist names this shape: *"Payload caps must keep the NEWEST
    rows: `order_by(asc).limit()` silently hides everything created after row N."* It was written
    about response payloads; this is the same mistake one layer earlier, where the cap decides what
    is COMPUTED rather than what is shown.
    """
    if key not in me.TABLES:
        return [], {"present": False, "scanned": 0, "total": 0, "truncated": False,
                    "oldest_scanned": None}
    total = me.count_records(db, key, pid)
    rows = me.list_records(db, key, pid, limit=SCAN_CAP,
                           sort="created_at", sort_dir="desc")
    oldest = (rows[-1].get("created_at") if rows else None)
    return rows, {
        "present": True, "scanned": len(rows), "total": total,
        "truncated": total > len(rows),
        # The bound a reader can act on, and it is a RECORDING bound rather than an event one:
        # the slice is ordered by `created_at`, so what it keeps is what was written down most
        # recently. That is the right end to keep — a back-dated daily report entered today has a
        # clock running today, and `notice_clock.detect` says so itself about RFIs, whose only date
        # is "when somebody wrote it down". It also means an old event recorded late IS in the
        # register while a newer one recorded later still may not be, so the sentence below says
        # "recorded", not "occurred". *A bound reported in the wrong units is worse than none,
        # because a reader acts on it* — the gate's first run asserted the event date here and the
        # mismatch is what surfaced the distinction.
        "oldest_scanned": oldest.isoformat() if hasattr(oldest, "isoformat") else oldest,
    }


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
    # `limit` is GONE, not defaulted higher. It bounded how much of the field record was scanned,
    # which is not a request-shaping knob: a caller passing a small number got a register that
    # silently omitted events. The bound is `SCAN_CAP`, the slice is newest-first, and what it left
    # out is reported. See `_source_slice`.
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

    rows: dict[str, list[dict]] = {}
    sources: dict[str, dict] = {}
    for key in ("daily_report", "change_event", "rfi"):
        rows[key], sources[key] = _source_slice(db, key, pid)
    events = nc.detect(
        daily_reports=rows["daily_report"],
        change_events=rows["change_event"],
        rfis=rows["rfi"],
    )
    out = nc.scan(events, used, today=as_of, calendar=_calendar(weekend, holidays),
                  due_soon_days=due_soon_days)
    out["events_found"] = len(events)
    # The COVERAGE beside the verdict. `events_found` is how many triggering events were detected,
    # which reads as how many there are; `sources` says what was looked at, and `complete` is the
    # only thing that makes "nothing expired" mean anything. A register over a subset of the field
    # record is not a conservative answer, it is a different one that looks identical.
    out["sources"] = sources
    out["complete"] = not any(s["truncated"] for s in sources.values())
    present = [k for k in sources if sources[k]["present"]]
    short = [k for k in present if sources[k]["truncated"]]
    counted = ", ".join(f"{sources[k]['total']} {k.replace('_', ' ')}s" for k in present)
    if short:
        cut = min((sources[k]["oldest_scanned"] or "") for k in short)
        out["coverage"] = (
            f"only the most recent {SCAN_CAP} record(s) of "
            + ", ".join(k.replace("_", " ") for k in short)
            + f" were scanned, out of {counted}"
            + (f" — nothing RECORDED before {cut[:10]} is in this register (the slice is ordered "
               "by when a record was written, not by when the event happened)" if cut else ""))
    else:
        out["coverage"] = f"every record in the field register was scanned ({counted})" if present             else "no field registers exist on this project, so there is nothing to scan"
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
