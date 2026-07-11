"""Responsibility matrix (RACI / DACI) endpoints — the grid, its starter templates, role-column
config, and template application. Rows themselves are ordinary `responsibility` module records, so
create/edit/delete of individual cells goes through the generic /modules CRUD; these routes assemble
and validate the grid and seed it. See responsibility.py."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, responsibility
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.get("/projects/{pid}/responsibility")
def get_matrix(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The full RACI/DACI grid: role columns × activity rows, with per-row validation
    (exactly one Accountable, at least one Responsible) and role-load summary."""
    _project(db, pid)
    return responsibility.matrix(db, pid)


@router.get("/projects/{pid}/responsibility/templates")
def get_templates(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Starter matrices for the common construction phases (design delivery, buyout, execution, closeout)."""
    _project(db, pid)
    return {"templates": responsibility.templates()}


@router.put("/projects/{pid}/responsibility/config")
def put_config(pid: str, roles: list[str] = Body(..., embed=True),
               mode: str = Body("RACI", embed=True),
               db: Session = Depends(get_db), actor: str = Depends(require_role("reviewer"))):
    """Set the project's role columns and the matrix mode (RACI or DACI)."""
    _project(db, pid)
    out = responsibility.set_config(db, pid, roles, mode, actor)
    audit.record(db, action="responsibility.config", actor=actor, method="PUT",
                 path=f"/projects/{pid}/responsibility/config", detail=out)
    return out


@router.post("/projects/{pid}/responsibility/apply-template")
def apply_template(pid: str, key: str = Body(..., embed=True), mode: str = Body("RACI", embed=True),
                   db: Session = Depends(get_db), actor: str = Depends(require_role("reviewer"))):
    """Seed the matrix from a named starter template (also sets the default role columns + mode)."""
    _project(db, pid)
    out = responsibility.apply_template(db, pid, key, mode, actor)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    audit.record(db, action="responsibility.apply_template", actor=actor, method="POST",
                 path=f"/projects/{pid}/responsibility/apply-template", detail=out)
    return out
