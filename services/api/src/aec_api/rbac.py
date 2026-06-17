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

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import ProjectMember

ROLE_ORDER = {"viewer": 0, "reviewer": 1, "editor": 2, "admin": 3}
RBAC_ON = os.environ.get("AEC_RBAC") == "1"
API_KEY = os.environ.get("AEC_API_KEY")


def _resolve_active(db: Session, sub: str) -> str:
    """A token/cookie resolved to user `sub`; reject if the account was deactivated so that
    revoking access takes effect immediately, not only after the 7-day token expiry."""
    from .models import User
    u = db.get(User, sub)
    if u is not None and u.active is False:
        raise HTTPException(status_code=401, detail="account deactivated")
    return sub


def current_user(x_user: str | None = Header(default=None),
                 authorization: str | None = Header(default=None),
                 aec_token: str | None = Cookie(default=None),
                 db: Session = Depends(get_db)) -> str:
    """Identify the caller: a signed bearer token (real auth) → its user; the AEC_API_KEY
    bearer → 'api-key' (admin); the aec_token cookie (for SSE / direct-download links that
    can't set an Authorization header); otherwise the dev X-User header. They coexist.
    Token/cookie identities are checked against the account's active flag."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
        if API_KEY and token == API_KEY:
            return "api-key"
        from . import auth
        sub = auth.verify_token(token)
        if sub:
            return _resolve_active(db, sub)
    if aec_token:
        from . import auth
        sub = auth.verify_token(aec_token)
        if sub:
            return _resolve_active(db, sub)
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


def party_role_for(db: Session, project_id: str, user: str) -> str | None:
    if user == "api-key":
        return "GC"
    m = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id, ProjectMember.user == user).first()
    return m.party_role if m else None


def party_allowed(party: str | None, allowed: list[str] | str | None) -> bool:
    """GC and the api-key/admin always pass so the workflow never stalls (per spec).
    `allowed` may be a list, a single party string, or None — and `party` may be None."""
    if not RBAC_ON:
        return True
    if party in ("GC", "GeneralContractor"):
        return True
    if isinstance(allowed, str):
        allowed = [allowed]
    return party is not None and party in (allowed or [])


def grant(db: Session, project_id: str, user: str, role: str,
          party_role: str | None = None) -> ProjectMember:
    if role not in ROLE_ORDER:
        raise HTTPException(400, f"invalid role {role!r}")
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id, ProjectMember.user == user).first()
    if existing:
        existing.role = role
        if party_role is not None:
            existing.party_role = party_role
        return existing
    m = ProjectMember(project_id=project_id, user=user, role=role, party_role=party_role)
    db.add(m)
    return m
