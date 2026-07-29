"""R23-JURISDICTION-PACKS — the pack library, and a project's check against the packs for its place.

The library is global (a pack is meant to be shared); the check is project-scoped, because it needs
that project's model and that project's jurisdiction.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import jurisdiction_packs as jp
from .. import model_index
from ..db import get_db
from ..deps import get_project
from ..rbac import current_user, require_role
from .auth import require_admin_user

router = APIRouter()


def require_identified(user: str = Depends(current_user)) -> str:
    """A caller who actually authenticated.

    `current_user` IDENTIFIES; it does not AUTHORISE. With RBAC on and no bearer token, cookie or
    trusted header it returns the literal string `"anonymous"` — so `Depends(current_user)` on its
    own is not a gate, it is a name. These routes shipped with exactly that mistake and a live probe
    returned 200 / **201** / 200 with no credentials at all while `GET /admin/errors` correctly
    returned 403 in the same run.

    This is the platform-global sibling of the `/projects/{pid}` rule in `route-authz-guard`: a route
    that LOOKS guarded because a dependency is present, when the dependency only identifies.
    """
    if user in ("anonymous", None, ""):
        raise HTTPException(403, "authentication required")
    return user


@router.get("/jurisdiction/packs")
def list_packs(jurisdiction: str | None = Query(None), _: str = Depends(require_identified)):
    """Every data-requirement pack available, optionally filtered to one jurisdiction.

    The built-in `example` pack asserts nothing about any real place — it is there to show the shape.
    Real packs are imported by someone who can point at the document they came from, which is why
    `authority`, `edition` and `source` are required to store one."""
    try:
        packs = jp.library()
    except jp.PackError as e:
        raise HTTPException(409, str(e)) from e
    if jurisdiction:
        j = jurisdiction.strip().upper()
        packs = [p for p in packs if p.get("jurisdiction") == j]
    return {"packs": packs, "count": len(packs),
            "note": "a pack states whose requirement it is; the built-in `example` pack states that "
                    "it is an example and is attributed to nobody"}


@router.post("/jurisdiction/packs", status_code=201)
def import_pack(pack: dict = Body(...), _admin=Depends(require_admin_user)):
    """Import a data-requirement pack from an authority.

    Refused without `authority`, `edition` and `source`. That is not bureaucracy: a requirement
    nobody can trace is indistinguishable from one somebody made up, and this pack will be used to
    fail other people's models. Selectors are validated with the same parser that will evaluate
    them, so a requirement cannot store cleanly and then silently never match — which reads as a
    pass."""
    try:
        return jp.import_pack(pack)
    except jp.PackError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/jurisdiction/packs/{pack_id}")
def delete_pack(pack_id: str, _admin=Depends(require_admin_user)):
    try:
        removed = jp.delete_pack(pack_id)
    except jp.PackError as e:
        raise HTTPException(409, str(e)) from e
    if not removed:
        raise HTTPException(404, "no imported pack with that id (the built-in example cannot be deleted)")
    return {"deleted": pack_id}


@router.get("/projects/{pid}/jurisdiction/requirements")
def project_requirements(pid: str, pack: str | None = Query(None),
                         db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The data requirements that apply to this project, resolved from its jurisdiction.

    A project with no jurisdiction set gets an empty list and the reason — never a default pack. A
    requirement set from the wrong authority is not a conservative approximation of the right one;
    it is a different answer that looks exactly like it, and it would fail a model against rules
    nobody imposed. Pass `?pack=` to apply one explicitly instead."""
    project = get_project(db, pid)
    try:
        if pack:
            chosen = [p for p in jp.library() if p.get("id") == pack.strip().lower()]
            if not chosen:
                raise HTTPException(404, f"no pack with id {pack!r}")
            return {"jurisdiction": getattr(project, "jurisdiction", None), "packs": chosen,
                    "adopted": True, "explicit": True,
                    "note": "applied by id, not resolved from the project's jurisdiction"}
        return jp.resolve(getattr(project, "jurisdiction", None))
    except jp.PackError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/projects/{pid}/jurisdiction/check")
def project_check(pid: str, pack: str | None = Query(None),
                  db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Check the project's model against the data requirements for its jurisdiction.

    Every result carries the pack's authority and edition. A compliance figure detached from whose
    rules it measured is the kind of number that gets quoted at somebody, and `is_example` rides
    along so a run against the demonstration pack can never be mistaken for a real one."""
    project = get_project(db, pid)
    try:
        if pack:
            packs = [p for p in jp.library() if p.get("id") == pack.strip().lower()]
            if not packs:
                raise HTTPException(404, f"no pack with id {pack!r}")
            resolved = {"jurisdiction": getattr(project, "jurisdiction", None), "explicit": True}
        else:
            r = jp.resolve(getattr(project, "jurisdiction", None))
            packs, resolved = r["packs"], {k: r[k] for k in ("jurisdiction", "adopted", "why")}
        if not packs:
            return {**resolved, "model_scored": False, "packs": [],
                    "note": resolved.get("why") or "no pack applies to this project"}
        try:
            model_index.ensure_loaded(pid)
            idx = model_index.get_index(pid)
        except Exception:  # noqa: BLE001 — no model uploaded is an answer, not a failure
            idx = None
        return {**resolved, **jp.check(idx, packs)}
    except jp.PackError as e:
        raise HTTPException(409, str(e)) from e
