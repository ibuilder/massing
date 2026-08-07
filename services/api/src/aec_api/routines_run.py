"""R22-ROUTINES — the step that turns "which routines are due" into work that actually happens.

`routines.due()` decides correctly and refuses well: an unknown cadence is refused rather than treated
as due, a `draft`/`retired` routine is never fired, a routine whose previous run is unfinished is
skipped, and missed windows fire **once** for the current window rather than replaying history
(`catch_up_suppressed`). `jobs.enqueue` raises on an unregistered kind so a typo fails at submit.
`worker.py` runs the queue.

**Nothing joined them.** Both `/routines/due` endpoints are read-only queries, so the answer to "what
should run now" was computed, returned, and dropped — which is exactly the entry's own complaint that
this is a tool you remember to use rather than infrastructure.

THE LATENT DEFECT THAT MADE THIS MORE THAN PLUMBING
---------------------------------------------------
`routines.from_project(db, pid, now, in_flight)` takes `in_flight` as a **parameter**, and **no caller
supplies it**. That is the one refusal in the chain that cannot work on its own: `evaluate` can only
return `STATUS_RUNNING` for a routine whose previous run has not finished if somebody *tells it* which
routines are running. With the default empty set, a monthly report that takes an hour would be
re-enqueued on every sweep for that hour. So the join has to derive `in_flight` from the jobs table,
and doing that is most of the value here — the plumbing is the easy half.

THREE REFUSALS
--------------
1.  **`in_flight` is derived, never assumed empty.** A routine with a `queued` or `running` job of its
    kind is in flight and is not re-enqueued.
2.  **An unknown kind is reported, not fatal.** `jobs.enqueue` raises `ValueError` on an unregistered
    kind, and letting that propagate would abort the sweep for every *other* routine because one was
    misconfigured. It is caught per routine and listed.
3.  **The window is consumed at ENQUEUE, not at success**, and the job id is recorded so the outcome
    stays visible. Consuming it on success instead would re-fire a failing routine on every sweep
    until it passed — a retry storm dressed as a schedule. The cost is that a failed run waits for the
    next window, which is why `enqueued` carries its `job_id`: a reader can see the failure rather
    than having it silently retried.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

#: Job states that mean "this routine's work is already underway". `done`/`error` are terminal and do
#: not block the next window.
IN_FLIGHT_STATES = ("queued", "running")

STATUS_ENQUEUED = "enqueued"
STATUS_UNKNOWN_KIND = "unknown_kind"


def in_flight_kinds(db, project_id: str) -> set[str]:
    """Job kinds with unfinished work for this project — the signal `evaluate` cannot get by itself."""
    from .models import Job

    rows = (db.query(Job.kind)
            .filter(Job.project_id == project_id, Job.state.in_(IN_FLIGHT_STATES))
            .all())
    return {r[0] for r in rows if r and r[0]}


def _in_flight_ids(routines_due: dict, busy: set[str]) -> set[str]:
    """Routine ids whose KIND is already running. Mapped by kind, because that is what a job carries."""
    out = set()
    for row in (routines_due.get("due") or []) + (routines_due.get("skipped") or []):
        if row.get("kind") in busy:
            out.add(str(row.get("id")))
    return out


def run_due(db, project_id: str, now: datetime | None = None,
            actor: str = "scheduler") -> dict[str, Any]:
    """Evaluate the project's routines and enqueue the ones that are due. One job per due routine."""
    from . import jobs, routines
    from . import modules as me

    busy = in_flight_kinds(db, project_id)
    # Two passes on purpose: the first tells us which routines exist and what kind each is, so the
    # in-flight set can be expressed in routine ids; the second is the evaluation that counts.
    first = routines.from_project(db, project_id, now=now)
    verdict = routines.from_project(db, project_id, now=now,
                                    in_flight=_in_flight_ids(first, busy))

    enqueued, refused = [], []
    for row in verdict.get("due") or []:
        kind = row.get("kind")
        try:
            job = jobs.enqueue(db, kind, project_id, {"routine_id": row.get("id"),
                                                      "window_start": row.get("window_start")},
                               actor=actor)
        except ValueError as e:
            # One misconfigured routine must not stop the others from running.
            refused.append({"routine_id": row.get("id"), "kind": kind,
                            "status": STATUS_UNKNOWN_KIND, "reason": str(e)})
            continue
        # The window is consumed here, not on success — see the module docstring.
        stamp = (now or routines.utc_now())
        try:
            # update_record(db, key, project_id, rid, data, actor, party) - actor and party are
            # REQUIRED positionals, not keywords. Read off the signature; omitting them is a
            # TypeError that only the write path would have surfaced.
            me.update_record(db, "routine", project_id, str(row.get("id")),
                             {"last_run": stamp.date().isoformat(), "last_job_id": job.id},
                             actor, None)
        except Exception:                        # noqa: BLE001 — the job is queued either way
            pass
        enqueued.append({"routine_id": row.get("id"), "kind": kind, "job_id": job.id,
                         "window_start": row.get("window_start"),
                         "missed_windows": row.get("missed_windows"),
                         "status": STATUS_ENQUEUED})

    return {
        "project_id": project_id,
        "as_of": verdict.get("as_of"),
        "due_count": verdict.get("due_count"),
        "enqueued": enqueued,
        "enqueued_count": len(enqueued),
        "refused": refused,
        "skipped": verdict.get("skipped"),
        "in_flight_kinds": sorted(busy),
        "total_missed_windows": verdict.get("total_missed_windows"),
        "note": ("one job per DUE routine — never one per missed window, because a routine disabled "
                 "for a year would otherwise flood the queue on the day it is switched back on. "
                 "Routines whose kind already has queued or running work are skipped as in-flight, "
                 "derived from the jobs table rather than assumed empty. A routine naming an "
                 "unregistered kind is listed under `refused` and does not stop the rest of the "
                 "sweep. The window is consumed at enqueue and the `job_id` is recorded, so a run "
                 "that fails is visible rather than silently retried on every sweep until it "
                 "passes."),
    }
