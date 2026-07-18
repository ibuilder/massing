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


@router.get("/projects/{pid}/jobs")
def list_jobs(pid: str, limit: int = 50, db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """The project's jobs, newest first (bounded)."""
    from .. import jobs
    rows = db.scalars(select(Job).where(Job.project_id == pid)
                      .order_by(Job.created_at.desc()).limit(min(int(limit), 200)))
    return {"jobs": [jobs.job_dict(j) for j in rows]}
