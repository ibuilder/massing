"""Project assistant endpoint — plain-English Q&A across the whole project (modules, schedule,
budget, risk, rent roll)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import agent_packs, assistant, routines
from ..db import get_db
from ..models import Project
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


@router.post("/projects/{pid}/routines/run-due")
def project_routines_run_due(pid: str, db: Session = Depends(get_db),
                             actor: str = Depends(require_role("editor"))):
    """R22-ROUTINES — enqueue the routines that are due. The step that makes this infrastructure.

    `/routines/due` answers what *should* run and returns it; nothing acted on that answer, which is
    the entry's own complaint — AI as a tool you remember to use rather than something that happens.
    This enqueues one job per due routine and stamps the window as consumed.

    **`in_flight` is derived from the jobs table, not assumed empty.** `routines.from_project` takes it
    as a parameter and no caller supplied one, so the "previous run has not finished" refusal could
    never fire: a monthly report taking an hour would be re-enqueued on every sweep for that hour.

    Three refusals a scheduler is worthless without:

    * **one job per DUE routine, never one per missed window.** A routine dormant for a year fires
      once when switched back on, with the missed count reported — not twelve jobs at once.
    * **a routine naming an unregistered kind is listed under `refused`**, and does not abort the
      sweep for every correctly-configured routine beside it.
    * **the window is consumed at enqueue, with the `job_id` recorded.** Consuming it on success would
      re-fire a failing routine every sweep until it passed — a retry storm dressed as a schedule. The
      cost is that a failed run waits for the next window, which is why the job id is on the row."""
    from .. import routines_run
    return routines_run.run_due(db, pid, actor=actor)


@router.get("/projects/{pid}/routines/due")
def project_routines_due(pid: str, db: Session = Depends(get_db),
                         _: str = Depends(require_role("viewer"))):
    """R22-ROUTINES — which of THIS project's stored routines should be enqueued now.

    The persisted half of `/routines/due`: routines live in the `routine` register, and each carries
    its own `last_run`, so recurrence survives a restart — which is the point of storing them at all.

    **Only `active` routines are evaluated.** A `draft` was never switched on and a `retired` one was
    switched off deliberately; firing either would be the scheduler inventing intent. The ones it
    skipped for that reason are counted in `stored` vs `evaluated` rather than vanishing.

    Every refusal from the stateless endpoint still applies: catch-up is reported and never replayed
    (a routine three windows behind fires ONCE with `missed_windows: 3`), an unknown cadence is
    refused rather than defaulted, and skips come back with their reasons.
    """
    return routines.from_project(db, pid)


@router.get("/projects/{pid}/agent-packs")
def project_agent_packs(pid: str, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """R22-AGENT-PACKS — the governance console: which named agents exist, what each runs, which can
    write, and what has actually been run against this project.

    A pack is a **named view over tools that already exist** — "Submittal Review Agent" rather than
    `standards_check`. It grants nothing: every tool in every pack is already in `mcp_tools.TOOLS`,
    and `dispatch` applies its own membership and role checks regardless of which pack a caller came
    through. A pack that could widen access would be a privilege-escalation surface wearing the name
    of a governance feature.

    **Packs that can modify the project say so**, naming the write tools — a console that lists
    agents without distinguishing read from write is not one anybody can govern with.

    `runs` is the per-run history the ring entry calls the gating factor for enterprise adoption.
    Until R22-AGENT-PACKS only `run_recipe` wrote an audit row, so 16 of 18 tools ran with no trail.
    Every dispatch now records one — **including failures**, because a history of successes cannot
    answer what an agent *attempted*, which is the question asked after an incident.
    """
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return {**agent_packs.catalog(), **agent_packs.run_log(db, project_id=pid)}
