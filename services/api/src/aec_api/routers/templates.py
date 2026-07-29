"""Reusable templates (Procore parity): save a module's records as a named template and apply it
to any project to instantiate one record per item — e.g. a pre-pour checklist, an inspection set."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import modules as me
from .. import rbac
from ..db import get_db
from ..models import Template
from ..rbac import current_user, require_identified, require_role

router = APIRouter()


def _public(t: Template) -> dict:
    return {"id": t.id, "module": t.module, "name": t.name, "item_count": len(t.items or []),
            "created_at": t.created_at.isoformat() if t.created_at else None}


class TemplateIn(BaseModel):
    module: str
    name: str
    items: list[dict] = []          # list of data blobs ({field: value})


@router.get("/templates")
def list_templates(module: str | None = None, db: Session = Depends(get_db),
                   _: str = Depends(current_user)):
    q = db.query(Template)
    if module:
        q = q.filter(Template.module == module)
    return [_public(t) for t in q.order_by(Template.module, Template.name).all()]


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, db: Session = Depends(get_db),
                    # require_identified, not current_user: `/templates` is outside
                    # _PROTECTED_PREFIXES, so with RBAC on an anonymous caller reached this
                    # and created a SHARED, cross-project template. current_user only names.
                    _: str = Depends(require_identified)):
    if body.module not in me.REGISTRY:
        raise HTTPException(400, f"unknown module {body.module!r}")
    t = Template(module=body.module, name=body.name, items=body.items or [])
    db.add(t)
    db.commit()
    return _public(t)


@router.delete("/templates/{tid}")
def delete_template(tid: str, db: Session = Depends(get_db),
                    # Same fix, and this was the worse half: an unauthenticated DELETE of a
                    # template every project can use.
                    _: str = Depends(require_identified)):
    t = db.get(Template, tid)
    if not t:
        raise HTTPException(404, "no such template")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/modules/{key}/save-template", status_code=201)
def save_template(pid: str, key: str, name: str = Body(..., embed=True),
                  db: Session = Depends(get_db), actor: str = Depends(require_role("viewer"))):
    """Capture the project's current records for `key` as a reusable template (data only)."""
    me.get_module(key)
    items = [r.get("data") or {} for r in me.list_records(db, key, pid, limit=1_000_000)]
    if not items:
        raise HTTPException(400, "no records to save as a template")
    t = Template(module=key, name=name, items=items)
    db.add(t)
    db.commit()
    return _public(t)


@router.post("/projects/{pid}/modules/{key}/apply-template/{tid}", status_code=201)
def apply_template(pid: str, key: str, tid: str, db: Session = Depends(get_db),
                   actor: str = Depends(require_role("editor"))):
    """Instantiate a template into the project — one new record per item."""
    t = db.get(Template, tid)
    if not t or t.module != key:
        raise HTTPException(404, "template not found for this module")
    party = rbac.party_role_for(db, pid, actor)
    created = 0
    for item in (t.items or []):
        me.create_record(db, key, pid, {"data": dict(item)}, actor, party)
        created += 1
    return {"applied": t.name, "created": created}
