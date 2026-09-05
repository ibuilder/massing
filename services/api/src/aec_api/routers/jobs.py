"""JOB-QUEUE endpoints — enqueue heavy work, poll it, list a project's jobs."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import rbac
from ..db import get_db
from ..models import Job
from ..rbac import require_role

router = APIRouter()

# HARDEN-2 (S1): job kinds that do more than read/derive need a HIGHER role than the generic editor
# gate below — otherwise the queue is a side door around a stricter endpoint (escalation_scan applies
# the escalation pass that POST /escalations/run deliberately gates at admin + audits).
_KIND_MIN_ROLE = {"escalation_scan": "admin"}


def _require_kind_role(db: Session, pid: str, user: str, kind: str) -> None:
    """403 unless the caller meets the kind's minimum role (mirrors require_role, incl. the RBAC-off
    dev bypass)."""
    needed = _KIND_MIN_ROLE.get(kind)
    if needed is None or not rbac.RBAC_ON:
        return
    role = rbac.role_for(db, pid, user)
    if role is None or rbac.ROLE_ORDER.get(role, -1) < rbac.ROLE_ORDER[needed]:
        raise HTTPException(403, f"job kind {kind!r} requires {needed} on project "
                                 f"(user {user!r} has {role or 'no'} role)")


@router.post("/projects/{pid}/jobs", status_code=201)
def enqueue_job(pid: str, kind: str = Body(..., embed=True),
                params: dict | None = Body(default=None, embed=True),
                db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Queue a background job for this project (editor — jobs do real work against the model/records;
    kinds in `_KIND_MIN_ROLE` need more). `kind` must be registered (400 with the registered list
    otherwise). Poll GET /projects/{pid}/jobs/{id}."""
    from .. import audit, jobs
    _require_kind_role(db, pid, actor, kind)
    try:
        # Server-owned keys are STRIPPED from the caller's params, then written. `project_id` and
        # `actor` were previously only written last, which stops an override and was enough while
        # identity was all that rested on them. A handler sees only `params` -- never the Job row --
        # so the moment any kind needs to know WHO ran it, `params["actor"]` becomes an identity
        # claim, and a caller-supplied one would be believed. `clash_federated` is the first kind
        # that reads it (`clash_intel.coordinate` records the actor and their party role against
        # every coordination issue it creates), which is why this moved from "harmless" to
        # "load-bearing" in one commit.
        #
        # `routine_id` and `deliver_to` then joined them and write-last was no longer enough, because
        # nothing here writes those: together they make the worker MAIL the finished artifact, so a
        # forged pair could aim a delivery. Stripping is what makes the rule structural — see
        # `jobs.SERVER_ONLY_PARAMS` for why "an editor could do this through the deliver route
        # anyway" was true and still not a good enough guarantee to rest on.
        clean = {k: v for k, v in (params or {}).items() if k not in jobs.SERVER_ONLY_PARAMS}
        j = jobs.enqueue(db, kind, pid, {**clean, "project_id": pid, "actor": actor}, actor=actor)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if kind in _KIND_MIN_ROLE:                       # privileged kinds get the same audit trail as
        audit.record(db, action=f"job.enqueue:{kind}", actor=actor, method="POST",   # their endpoint
                     path=f"/projects/{pid}/jobs", detail={"job_id": j.id, "params": params or {}})
        db.commit()
    return jobs.job_dict(j)


@router.get("/projects/{pid}/jobs/{job_id}")
def job_status(pid: str, job_id: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """One job's state + result/error. 404 when it doesn't exist or belongs to another project."""
    from .. import jobs
    j = db.get(Job, job_id)
    if j is None or j.project_id != pid:
        raise HTTPException(404, "job not found")
    return jobs.job_dict(j)


@router.get("/projects/{pid}/jobs/{job_id}/artifact")
def job_artifact(pid: str, job_id: str, db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """Download a finished job's binary artifact (e.g. the compiled drawing-set PDF). Artifact jobs
    park their output in object storage and put `artifact_key` in the result; this streams it back.
    409 while the job is still queued/running; 404 when the job has no artifact."""
    from fastapi import Response

    from .. import storage
    j = db.get(Job, job_id)
    if j is None or j.project_id != pid:
        raise HTTPException(404, "job not found")
    if j.state in ("queued", "running"):
        raise HTTPException(409, f"job is {j.state} — poll until done")
    res = j.result or {}
    key = res.get("artifact_key") if isinstance(res, dict) else None
    if j.state != "done" or not key or not storage.exists(key):
        raise HTTPException(404, "job has no artifact" + (f" (state {j.state}: {j.error})" if j.error else ""))
    fname = res.get("filename") or "artifact.bin"
    return Response(storage.get(key), media_type=res.get("media_type") or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


# R24-REPORTS-BY-MOMENT — "scheduled AND SHARED, not just downloaded" is the entry's own remainder,
# and the two halves had different blockers. SHARED is unblocked and lands here: the mailer already
# ships (stdlib smtplib, a Settings "Test connection" button, a digest route that sends real mail),
# it just had no way to carry a file.
#
# ⚠️ THIS COMMENT USED TO SAY "there is no scheduler of any kind in this tree (no APScheduler,
# croniter or cron)". THAT WAS FALSE, and it is the third copy of the claim to be corrected — the
# roadmap entry carried it, `test_artifact_deliver.py` carried it, and so did the changelog. The
# LIBRARY half is true and always was: none of those three is in `requirements.in`. But R22-ROUTINES
# hand-rolled a scheduler under a different item's name — `routines.py` (cadences, `window_start`,
# `due`, `from_project`), `routines_run.py`, a persisted `routine` register — and scheduled report
# packages ship today. A claim phrased as a search for a DEPENDENCY answered a question about a
# CAPABILITY, and then propagated to three files because each copy read true against the same
# grep.

@router.post("/projects/{pid}/jobs/{job_id}/deliver")
def deliver_artifact(pid: str, job_id: str, to: list[str] = Body(..., embed=True),
                     note: str = Body("", embed=True), db: Session = Depends(get_db),
                     user: str = Depends(require_role("editor"))):
    """Email a finished job's artifact to named recipients — the "shared, not just downloaded" half.

    Mirrors `job_artifact` exactly on lookup and refusal (404 wrong project, 409 while queued/running,
    404 when the job produced no artifact), because a caller should not have to learn two different
    answers to "is this artifact ready". Delivery then adds two refusals of its own: an empty
    recipient list is 422 rather than a silent no-op, and an artifact over 15 MB is 413 rather than a
    per-recipient "error" from a server that would have rejected it anyway.

    Returns a per-recipient status map (`sent` / `disabled` / `error`) in the same shape as the
    notification digest, so an unconfigured deployment reports `disabled` instead of failing.

    **The body of this is in `artifact_delivery`, because the worker needs it too.** A scheduled
    report package is assembled with nobody watching, and it has to reach its recipients by the same
    caps, the same de-duplication and the same audit record — a second copy of those would be a
    second thing to keep in step. What stays here is only the part that is about HTTP: the readiness
    refusals above, and turning a `DeliveryRefused` back into the status it has always carried.
    """
    from .. import artifact_delivery, storage
    j = db.get(Job, job_id)
    if j is None or j.project_id != pid:
        raise HTTPException(404, "job not found")
    if j.state in ("queued", "running"):
        raise HTTPException(409, f"job is {j.state} — poll until done")
    res = j.result or {}
    key = res.get("artifact_key") if isinstance(res, dict) else None
    if j.state != "done" or not key or not storage.exists(key):
        raise HTTPException(404, "job has no artifact" + (f" (state {j.state}: {j.error})" if j.error else ""))
    try:
        addrs = artifact_delivery.recipients(to)
        out = artifact_delivery.send(db, job_id=job_id, kind=j.kind, project_id=pid, result=res,
                                     addrs=addrs, actor=user,
                                     intro=f"{user} sent you {res.get('filename') or 'artifact.bin'} "
                                           f"from project {pid}.", note=note)
    except artifact_delivery.DeliveryRefused as e:
        raise HTTPException(e.status, e.detail) from e
    db.commit()
    return out


@router.get("/projects/{pid}/jobs")
def list_jobs(pid: str, limit: int = 50, db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """The project's jobs, newest first (bounded)."""
    from .. import jobs
    rows = db.scalars(select(Job).where(Job.project_id == pid)
                      .order_by(Job.created_at.desc()).limit(min(int(limit), 200)))
    return {"jobs": [jobs.job_dict(j) for j in rows]}
