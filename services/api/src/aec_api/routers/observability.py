"""Observability endpoints: the admin error-log feed (`/admin/errors`) and the client-error intake
(`/client-errors`) that the web app posts JS exceptions to. The 'background section to check when
things break' — server 500s land here automatically (main.py handler); browser errors are posted by
the front-end hook. Admin-gated read; any signed-in user may report a client error (best-effort)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session

from .. import errorlog
from ..db import get_db
from ..rbac import current_user
from .auth import require_admin_user

router = APIRouter()


@router.get("/admin/errors")
def list_errors(limit: int = Query(100, ge=1, le=500), source: str | None = None,
                level: str | None = None, since_hours: int | None = Query(None, ge=1, le=8760),
                db: Session = Depends(get_db), _admin=Depends(require_admin_user)):
    """Newest-first error feed + a summary header. Admin only."""
    return {"stats": errorlog.stats(db),
            "errors": errorlog.recent(db, limit=limit, source=source, level=level, since_hours=since_hours)}


@router.delete("/admin/errors")
def clear_errors(db: Session = Depends(get_db), _admin=Depends(require_admin_user)):
    """Force-prune to the retention cap (housekeeping). Admin only."""
    return {"pruned": errorlog.prune(db)}


@router.post("/client-errors")
def report_client_error(request: Request, body: dict = Body(...),
                        db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Record a browser-side error (window.onerror / unhandledrejection / a failed fetch). Any signed-in
    user; best-effort so a reporting failure never disrupts the app. Body: {message, kind?, path?,
    level?, detail?}."""
    rid = getattr(request.state, "request_id", None)
    detail = body.get("detail") if isinstance(body.get("detail"), dict) else None
    eid = errorlog.record(
        db, source="web", level=(body.get("level") or "error"),
        kind=str(body.get("kind"))[:200] if body.get("kind") else "ClientError",
        message=str(body.get("message") or "")[:2000],
        path=str(body.get("path"))[:500] if body.get("path") else None,
        actor=user, request_id=rid, detail=detail,
    )
    return {"recorded": bool(eid), "id": eid}
