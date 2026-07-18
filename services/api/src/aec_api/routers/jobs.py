"""JOB-QUEUE endpoints — enqueue heavy work, poll it, list a project's jobs."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job
from ..rbac import require_role

router = APIRouter()


@router.post("/projects/{pid}/jobs", status_code=201)
def enqueue_job(pid: str, kind: str = Body(..., embed=True),
                params: dict | None = Body(default=None, embed=True),
                db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Queue a background job for this project (editor — jobs do real work against the model/records).
    `kind` must be registered (400 with the registered list otherwise). Poll GET /projects/{pid}/jobs/{id}."""
    from .. import jobs
    try:
        j = jobs.enqueue(db, kind, pid, {**(params or {}), "project_id": pid}, actor=actor)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
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
