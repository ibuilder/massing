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
               rename: dict[str, str] | None = Body(None, embed=True),
               drop: list[str] | None = Body(None, embed=True),
               db: Session = Depends(get_db), actor: str = Depends(require_role("reviewer"))):
    """Set the project's role columns and the matrix mode (RACI or DACI), migrating the cells to
    match **in one transaction**.

    `rename` maps an old column name to its new one, `drop` names columns whose cells should be
    cleared from every row; both are optional and describe how the cells move, since `roles` alone
    cannot distinguish a rename from a remove-plus-add. A mode change remaps the doer letter (R↔D)
    on its own. Nothing is written unless all of it can be."""
    _project(db, pid)
    try:
        out = responsibility.set_config(db, pid, roles, mode, actor, rename=rename, drop=drop,
                                        commit=False)
    except ValueError as e:
        # Raised before any write — the message names which of `roles`/`rename`/`drop` disagrees.
        raise HTTPException(400, str(e)) from e
    audit.record(db, action="responsibility.config", actor=actor, method="PUT",
                 path=f"/projects/{pid}/responsibility/config", detail=out)
    # ONE transaction for the matrix change AND its audit row: the engine is told not to commit, so
    # this is the only commit in the request. It used to commit inside the engine and again here,
    # which persisted the change first and the trail second — two transactions, and a crash between
    # them leaves a role rename with no record of who made it. Raised in review.
    db.commit()
    return out


@router.post("/projects/{pid}/responsibility/apply-template")
def apply_template(pid: str, key: str = Body(..., embed=True), mode: str = Body("RACI", embed=True),
                   db: Session = Depends(get_db), actor: str = Depends(require_role("reviewer"))):
    """Seed the matrix from a named starter template (also sets the default role columns + mode)."""
    _project(db, pid)
    out = responsibility.apply_template(db, pid, key, mode, actor, commit=False)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    audit.record(db, action="responsibility.apply_template", actor=actor, method="POST",
                 path=f"/projects/{pid}/responsibility/apply-template", detail=out)
    db.commit()   # ditto — the seeded rows, the config and this audit row are one transaction
    return out
