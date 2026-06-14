"""Audit logging for write endpoints (guide §10)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor: str | None = None,
    method: str | None = None,
    path: str | None = None,
    topic_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(
        action=action, actor=actor, method=method, path=path,
        topic_id=topic_id, detail=detail,
    ))
