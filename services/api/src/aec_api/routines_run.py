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

FOUR REFUSALS
-------------
1.  **`in_flight` is derived, never assumed empty.** A routine with a `queued` or `running` job of its
    kind is in flight and is not re-enqueued.
2.  **An unknown kind is reported, not fatal.** `jobs.enqueue` raises `ValueError` on an unregistered
    kind, and letting that propagate would abort the sweep for every *other* routine because one was
    misconfigured. It is caught per routine and listed.
3.  **A kind whose arguments are missing is refused, not enqueued half-formed.** `report_package`
    needs to know WHICH package; a routine that does not say is listed under `refused` with the
    moments it could have named. Enqueueing it anyway would put a job in the queue that can only fail
    at run time, which turns a configuration mistake into a failed run somebody has to diagnose.
4.  **The window is consumed at ENQUEUE, not at success**, and the job id is recorded so the outcome
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
STATUS_BAD_PARAMS = "bad_params"


def job_params(kind: str, row: dict) -> tuple[dict[str, Any], str | None, str | None]:
    """Params a routine's kind needs beyond `{routine_id, window_start}` — `(extra, refusal, note)`.

    R24-REPORTS-BY-MOMENT ③. Until this existed the sweep passed one params dict for every kind, so a
    kind needing its own arguments could not be scheduled at all, and `report_package` — assemble a
    named package of reports — was the one that needed them. "The owner package, every month" is the
    plainest thing anyone wants from a scheduler over a report catalog, and it was the one thing this
    scheduler could not do.

    A `refusal` is a string and means **do not enqueue**: it is listed under `refused` exactly like an
    unregistered kind, for the same reason, and it is built from our own constants rather than from an
    exception's text (see the note in `run_due` — that rule was learnt from a CodeQL finding, and a
    second place to leak from is still a leak).

    A `note` is advisory and the job runs anyway. It exists for the one case that is a mistake but not
    a failure: a routine that carries a `moment` for a kind that has no use for one, which is what you
    are left with after changing a routine's kind and not clearing the field. Silently ignoring the
    setting would be the "package quietly one row shorter" failure this feature is built to avoid;
    refusing to run a routine that is otherwise correct would be worse.
    """
    from . import report_moments

    moment = row.get("moment")
    if kind == "report_package":
        if not moment:
            return {}, ("a scheduled report package must say WHICH package: set this routine's "
                        f"moment to one of {sorted(report_moments.MOMENTS)}"), None
        if str(moment) not in report_moments.MOMENTS:
            return {}, (f"unknown report moment {str(moment)!r}; "
                        f"known: {sorted(report_moments.MOMENTS)}"), None
        return report_moments.package_params(str(moment)), None, None
    if moment:
        return {}, None, (f"this routine names the report moment {str(moment)!r}, which only "
                          f"report_package uses; {kind} takes no parameters, so it was ignored "
                          "rather than silently changing what ran")
    return {}, None, None


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
        extra, refusal, note = job_params(str(kind or ""), row)
        if refusal:
            # Same treatment as an unregistered kind: listed, and the sweep carries on. A routine
            # misconfigured in the OTHER direction — right kind, missing argument — used to be
            # impossible to express, so there was nothing to refuse; now it is, so it is.
            refused.append({"routine_id": row.get("id"), "kind": kind,
                            "status": STATUS_BAD_PARAMS, "reason": refusal})
            continue
        try:
            # `project_id` and `actor` are written LAST, after everything else, for the same reason
            # `routers/jobs.py` does it: a handler is called as `fn(db, j.params)` and never sees the
            # Job row, so anything it needs about WHERE it runs and WHO ran it has to be in `params`.
            #
            # THIS WAS MISSING AND IT MADE THE WHOLE SWEEP INERT. Every registered handler reads
            # `params.get("project_id")`, and two (`_clash_detect`, `_clash_federated`) read
            # `params.get("actor")` as an identity claim recorded against the coordination issues they
            # create. Without them a scheduled job did not fail at enqueue — it queued cleanly, ran,
            # and died on an empty project. Fixing the picklist so kinds stop being refused and
            # leaving this is exactly the "same defect one layer down" that fix was written to avoid,
            # and it was invisible because the tests asserted the ENQUEUE and never the RUN.
            job = jobs.enqueue(db, kind, project_id, {"routine_id": row.get("id"),
                                                      "window_start": row.get("window_start"),
                                                      **extra,
                                                      "project_id": project_id, "actor": actor},
                               actor=actor)
        except ValueError:
            # One misconfigured routine must not stop the others from running.
            #
            # The reason is REBUILT from the registry rather than echoed from the exception. The
            # previous version passed the caught exception's text straight onto a viewer-reachable
            # response, which CodeQL flags as py/stack-trace-exposure. The text of an exception is
            # not a contract: the next `raise ValueError` added inside `jobs.enqueue` would start
            # leaking whatever it happened to say, with nothing here to notice.
            #
            # Nothing is lost. `kind` is caller data already sitting in this same dict, and
            # `jobs.KINDS` is a server constant, so a reader still gets the bad name AND the valid
            # ones — the message is character-identical to what enqueue raises today, sourced from
            # the registry instead of from the traceback.
            refused.append({"routine_id": row.get("id"), "kind": kind,
                            "status": STATUS_UNKNOWN_KIND,
                            "reason": f"unknown job kind {kind!r}; "
                                      f"registered: {sorted(jobs.KINDS)}"})
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
                         "status": STATUS_ENQUEUED,
                         **({"params": sorted(extra)} if extra else {}),
                         **({"note": note} if note else {})})

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
