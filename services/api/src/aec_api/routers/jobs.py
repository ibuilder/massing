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
        j = jobs.enqueue(db, kind, pid, {**(params or {}), "project_id": pid}, actor=actor)
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


@router.get("/projects/{pid}/jobs")
def list_jobs(pid: str, limit: int = 50, db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """The project's jobs, newest first (bounded)."""
    from .. import jobs
    rows = db.scalars(select(Job).where(Job.project_id == pid)
                      .order_by(Job.created_at.desc()).limit(min(int(limit), 200)))
    return {"jobs": [jobs.job_dict(j) for j in rows]}
