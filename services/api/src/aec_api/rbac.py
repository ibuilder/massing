"""Project-scoped role-based access control (guide §7/§10).

Roles, least → most privileged: viewer < reviewer < editor < admin.
  viewer    read models, properties, issues, drawings, exports
  reviewer  + create/comment topics & viewpoints (RFIs, markup)
  editor    + author IFC, publish, run clash-with-topics
  admin     + project settings, manage members

Enforcement is gated by env AEC_RBAC=1 (off in dev so local flows stay open). The caller is
identified by the `X-User` header; an optional `AEC_API_KEY` bearer is treated as admin.
"""
from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import ProjectMember

ROLE_ORDER = {"viewer": 0, "reviewer": 1, "editor": 2, "admin": 3}
RBAC_ON = os.environ.get("AEC_RBAC") == "1"
API_KEY = os.environ.get("AEC_API_KEY")


def current_user(x_user: str | None = Header(default=None),
                 authorization: str | None = Header(default=None)) -> str:
    if API_KEY and authorization == f"Bearer {API_KEY}":
        return "api-key"
    return x_user or "dev"


def role_for(db: Session, project_id: str, user: str) -> str | None:
    if user == "api-key":
        return "admin"
    m = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id, ProjectMember.user == user).first()
    return m.role if m else None


def require_role(min_role: str):
    """Dependency factory for routes with a {pid} path param."""
    needed = ROLE_ORDER[min_role]

    def dep(pid: str, db: Session = Depends(get_db), user: str = Depends(current_user)) -> str:
        if not RBAC_ON:
            return user
        role = role_for(db, pid, user)
        if role is None or ROLE_ORDER.get(role, -1) < needed:
            raise HTTPException(
                status_code=403,
                detail=f"requires {min_role} on project (user {user!r} has {role or 'no'} role)")
        return user

    return dep


def grant(db: Session, project_id: str, user: str, role: str) -> ProjectMember:
    if role not in ROLE_ORDER:
        raise HTTPException(400, f"invalid role {role!r}")
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id, ProjectMember.user == user).first()
    if existing:
        existing.role = role
        return existing
    m = ProjectMember(project_id=project_id, user=user, role=role)
    db.add(m)
    return m
