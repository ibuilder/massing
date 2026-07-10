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
# The dev `X-User` header lets you act as any user without a token — convenient in dev, but an
# impersonation hole in production. It is honored only when RBAC is off (dev/local) or explicitly
# trusted via AEC_TRUST_XUSER=1 (used by the test suite). In production (RBAC on, flag unset) the
# only trusted identity is a signed bearer token / cookie / API key.
TRUST_XUSER = os.environ.get("AEC_TRUST_XUSER") == "1"
# Single-operator desktop build (AEC_LOCAL_MODE=1): the local user owns the one site, so there
# is no login and admin-only features (connections, settings, schedules) live in Settings,
# ungated. The Pro/cloud build leaves this off and keeps the account + admin gates.
LOCAL_MODE = os.environ.get("AEC_LOCAL_MODE") == "1"


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
    # no signed identity: trust the dev X-User header only in dev/test, never in production
    if not RBAC_ON or TRUST_XUSER:
        return x_user or "dev"
    return "anonymous"          # non-member → no project role → 403 on protected routes


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

    dep._role_gate = min_role   # tag so the route-authz guard test can detect the membership check
    return dep


def member_project_ids(db: Session, user: str) -> set[str] | None:
    """The set of project ids the caller may see in a cross-project roll-up. Returns None when RBAC is
    off (dev) or for the api-key/admin identity, meaning "no restriction". Otherwise only the projects
    the user is a member of — so portfolio aggregations never leak other tenants' data."""
    if not RBAC_ON or user == "api-key":
        return None
    rows = db.query(ProjectMember.project_id).filter(ProjectMember.user == user).all()
    return {r[0] for r in rows}


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
