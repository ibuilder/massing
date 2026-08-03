"""Project assistant endpoint — plain-English Q&A across the whole project (modules, schedule,
budget, risk, rent roll)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import assistant, routines
from ..db import get_db
from ..rbac import require_identified, require_role

router = APIRouter()


@router.post("/projects/{pid}/assistant")
def project_assistant(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                      _: str = Depends(require_role("viewer"))):
    """Ask about the project in plain English ('how many open RFIs?', 'what's the SPI?', 'occupancy?').
    Grounded in a live project snapshot; returns the snapshot when no AI key is configured."""
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(422, "question required")
    return assistant.ask(db, pid, question)


@router.get("/projects/{pid}/assistant/snapshot")
def assistant_snapshot(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The grounded project snapshot the assistant uses (module tallies, schedule, budget, risk)."""
    return assistant.project_snapshot(db, pid)


@router.post("/routines/due")
def routines_due(body: dict = Body(default={}), _: str = Depends(require_identified)):
    """R22-ROUTINES — which recurring runs should be enqueued now, and why the rest were skipped.

    Body: `{routines:[{id, kind, cadence, project_id?, enabled?}], last_runs:{id: date},
    in_flight:[id], now?: iso-datetime}`. `now` is accepted so a caller can evaluate a boundary
    deterministically; omitted, the server clock is used.

    **Catch-up is reported, never replayed.** A routine three windows behind fires ONCE with
    `missed_windows: 3`. Replaying closed windows duplicates reports into the same inbox and bills
    repeat calls to a paid API — the outage is information, not a backlog to work through.

    Two further refusals: a routine whose previous run is still in flight is not re-enqueued
    (recurrence plus a slow job is a pile-up that reads as a load problem and is a scheduling bug),
    and **cadence is a closed set** — an unknown cadence is refused and the known ones listed rather
    than being treated as daily, because a routine running on a schedule nobody chose is worse than
    one that does not run.

    Skips are returned WITH their reasons: "nothing ran" and "nothing was due" are different facts,
    and a scheduler that reports only what it fired cannot tell you which.
    """
    now = body.get("now")
    when = None
    if now:
        from datetime import datetime
        try:
            when = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "now must be an ISO-8601 datetime") from None
    return routines.due(body.get("routines") or [], when or routines.utc_now(),
                        last_runs=body.get("last_runs") or {},
                        in_flight=set(body.get("in_flight") or []))
