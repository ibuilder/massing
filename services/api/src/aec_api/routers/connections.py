"""Data-source connections (admin): register external databases (PostgreSQL / Supabase) and
Procore as connectable sources alongside the app's own database. Secrets are masked on read;
'test' validates reachability without persisting the live engine."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, connectors
from ..db import get_db
from ..models import Connection
from .auth import require_admin_user
from ..models import User

router = APIRouter()

_SECRET_KEYS = {"dsn", "access_token", "password"}


class ConnectionIn(BaseModel):
    name: str = ""          # optional for /connections/test (no record created)
    type: str
    config: dict = {}


def _public(c: Connection) -> dict:
    return {"id": c.id, "name": c.name, "type": c.type, "builtin": False,
            "config": connectors.public_config(c.type, c.config)}


@router.get("/connections")
def list_connections(db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    """Built-in local DB (with live status) + registered external connections (status on demand)."""
    rows = db.query(Connection).order_by(Connection.created_at).all()
    local = {"id": "local", "name": "Local (app database)", "type": "local", "builtin": True,
             "config": {}, "status": connectors.test("local", {})}
    return {"types": list(connectors.TYPES), "connections": [local] + [_public(c) for c in rows]}


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionIn, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin_user)):
    if body.type not in connectors.TYPES or body.type == "local":
        raise HTTPException(400, f"type must be one of {[t for t in connectors.TYPES if t != 'local']}")
    c = Connection(name=body.name, type=body.type, config=body.config or {})
    db.add(c)
    audit.record(db, action="connection.create", actor=admin.username, method="POST",
                 path="/connections", detail={"name": body.name, "type": body.type})  # no secrets
    db.commit()
    return _public(c)


@router.put("/connections/{cid}")
def update_connection(cid: str, body: ConnectionIn, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin_user)):
    c = db.get(Connection, cid)
    if not c:
        raise HTTPException(404, "no such connection")
    c.name = body.name or c.name
    # merge config: a blank secret keeps the stored value (so the form needn't re-send it)
    merged = dict(c.config or {})
    for k, v in (body.config or {}).items():
        if k in _SECRET_KEYS and not (v or "").strip():
            continue
        merged[k] = v
    c.config = merged
    audit.record(db, action="connection.update", actor=admin.username, method="PUT",
                 path=f"/connections/{cid}", detail={"id": cid})
    db.commit()
    return _public(c)


@router.delete("/connections/{cid}")
def delete_connection(cid: str, db: Session = Depends(get_db), admin: User = Depends(require_admin_user)):
    c = db.get(Connection, cid)
    if not c:
        raise HTTPException(404, "no such connection")
    db.delete(c)
    audit.record(db, action="connection.delete", actor=admin.username, method="DELETE",
                 path=f"/connections/{cid}", detail={"id": cid, "name": c.name})
    db.commit()
    return {"ok": True}


@router.post("/connections/test")
def test_config(body: ConnectionIn, _: User = Depends(require_admin_user)):
    """Test a posted config (used by the add/edit form before saving)."""
    return connectors.test(body.type, body.config or {})


@router.post("/connections/{cid}/test")
def test_connection(cid: str, db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    """Test a saved connection (uses the stored secret) + return its info payload."""
    c = db.get(Connection, cid)
    if not c:
        raise HTTPException(404, "no such connection")
    return {"status": connectors.test(c.type, c.config), "info": connectors.info(c.type, c.config)}


def _resolve(cid: str, db: Session) -> tuple[str, dict]:
    """Resolve a connection id to (type, config) — including the built-in 'local' app DB."""
    if cid == "local":
        return "local", {}
    c = db.get(Connection, cid)
    if not c:
        raise HTTPException(404, "no such connection")
    return c.type, (c.config or {})


@router.get("/connections/{cid}/tables")
def connection_tables(cid: str, db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    """List the connection's tables (SQL) or projects (Procore) — the data-plane browse entrypoint."""
    ctype, config = _resolve(cid, db)
    return connectors.tables(ctype, config)


@router.post("/connections/{cid}/query")
def connection_query(cid: str, sql: str = Body(..., embed=True), limit: int = Body(200, embed=True),
                     db: Session = Depends(get_db), _: User = Depends(require_admin_user)):
    """Run a read-only SELECT against a SQL connection (local / Postgres / Supabase)."""
    ctype, config = _resolve(cid, db)
    return connectors.query(ctype, config, sql, limit)
