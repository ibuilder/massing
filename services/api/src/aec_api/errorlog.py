"""Error-log engine — the "what broke" feed behind the admin observability panel. Records unhandled
server exceptions (source='server') and reported client-side JS errors (source='web') to the
`error_log` table, distinct from the business AuditLog. Bounded by a retention cap so it can never grow
unbounded (important with a read-only /app prod tree + Postgres). Recording is best-effort and MUST
never raise into the request path — a logger that crashes the app defeats its own purpose."""
from __future__ import annotations

import logging
import os
import traceback as _tb
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import ErrorLog

_log = logging.getLogger("aec.errorlog")

# Retention: keep at most this many rows, and drop anything older than this many days. Env-overridable.
_MAX_ROWS = int(os.environ.get("AEC_ERRORLOG_MAX_ROWS", "5000") or "5000")
_MAX_DAYS = int(os.environ.get("AEC_ERRORLOG_MAX_DAYS", "30") or "30")
_MSG_CAP = 2000          # truncate message / traceback so one huge error can't bloat a row
_TB_CAP = 8000
_prune_calls = 0


def _clip(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def record(db: Session, *, source: str = "server", level: str = "error", kind: str | None = None,
           message: str | None = None, method: str | None = None, path: str | None = None,
           status: int | None = None, actor: str | None = None, project_id: str | None = None,
           request_id: str | None = None, exc: BaseException | None = None,
           detail: dict[str, Any] | None = None) -> str | None:
    """Write one error row. `exc`, if given, supplies the traceback + kind. Best-effort: swallows any
    DB failure (returns None) so logging can never take down the request it's trying to describe."""
    tb = None
    if exc is not None:
        kind = kind or type(exc).__name__
        message = message or str(exc)
        tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
    row = ErrorLog(
        source=source, level=level, kind=_clip(kind, 200), message=_clip(message, _MSG_CAP),
        method=method, path=_clip(path, 500), status=status, actor=actor, project_id=project_id,
        request_id=request_id, traceback=_clip(tb, _TB_CAP), detail=detail,
    )
    try:
        db.add(row)
        db.commit()
    except Exception:                       # noqa: BLE001 — never raise out of the error logger
        db.rollback()
        _log.exception("failed to persist error-log row")
        return None
    _maybe_prune(db)
    return row.id


def _maybe_prune(db: Session) -> None:
    """Amortized retention: run the prune roughly every 100 records, not on every write."""
    global _prune_calls
    _prune_calls += 1
    if _prune_calls % 100 == 0:
        try:
            prune(db)
        except Exception:                   # noqa: BLE001 — pruning failure must not break logging
            db.rollback()


def prune(db: Session, *, max_rows: int | None = None, max_days: int | None = None) -> int:
    """Enforce retention: delete rows older than max_days, then trim to the newest max_rows.
    Returns the number of rows deleted."""
    max_rows = _MAX_ROWS if max_rows is None else max_rows
    max_days = _MAX_DAYS if max_days is None else max_days
    deleted = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    res = db.execute(delete(ErrorLog).where(ErrorLog.ts < cutoff))
    deleted += res.rowcount or 0
    # trim the tail beyond max_rows (keep newest)
    total = db.scalar(select(func.count()).select_from(ErrorLog)) or 0
    if total > max_rows:
        cut_ids = db.scalars(
            select(ErrorLog.id).order_by(ErrorLog.ts.desc()).offset(max_rows)
        ).all()
        if cut_ids:
            res = db.execute(delete(ErrorLog).where(ErrorLog.id.in_(cut_ids)))
            deleted += res.rowcount or 0
    db.commit()
    return deleted


def recent(db: Session, *, limit: int = 100, source: str | None = None,
           level: str | None = None, since_hours: int | None = None) -> list[dict[str, Any]]:
    """Newest-first error feed for the admin panel, with optional source/level/time filters."""
    limit = max(1, min(int(limit), 500))
    stmt = select(ErrorLog).order_by(ErrorLog.ts.desc())
    if source:
        stmt = stmt.where(ErrorLog.source == source)
    if level:
        stmt = stmt.where(ErrorLog.level == level)
    if since_hours:
        stmt = stmt.where(ErrorLog.ts >= datetime.now(timezone.utc) - timedelta(hours=int(since_hours)))
    rows = db.scalars(stmt.limit(limit)).all()
    return [{
        "id": r.id, "ts": r.ts.isoformat() if r.ts else None, "source": r.source, "level": r.level,
        "kind": r.kind, "message": r.message, "method": r.method, "path": r.path, "status": r.status,
        "actor": r.actor, "project_id": r.project_id, "request_id": r.request_id,
        "traceback": r.traceback, "detail": r.detail,
    } for r in rows]


def stats(db: Session, *, since_hours: int = 24) -> dict[str, Any]:
    """Summary for the panel header: totals by source + a 24h count."""
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    total = db.scalar(select(func.count()).select_from(ErrorLog)) or 0
    recent_n = db.scalar(
        select(func.count()).select_from(ErrorLog).where(ErrorLog.ts >= since)
    ) or 0
    by_source = dict(db.execute(
        select(ErrorLog.source, func.count()).group_by(ErrorLog.source)
    ).all())
    return {"total": int(total), f"last_{since_hours}h": int(recent_n),
            "by_source": {k: int(v) for k, v in by_source.items()}}
