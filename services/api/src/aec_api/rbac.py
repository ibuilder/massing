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
from datetime import datetime, timedelta, timezone

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


def _resolve_active(db: Session, sub: str, iat: int | None = None) -> str:
    """A token/cookie resolved to user `sub`; reject if the account was deactivated (so revoking
    access takes effect immediately, not only after the 7-day token expiry) OR if the token was
    issued before the account's session-revocation watermark (`token_epoch`, bumped on password
    change / admin reset / 'sign out everywhere' — so a leaked token dies the moment the password
    is rotated, not 7 days later)."""
    from .models import User
    u = db.get(User, sub)
    if u is not None and u.active is False:
        raise HTTPException(status_code=401, detail="account deactivated")
    if u is not None and u.token_epoch is not None and (iat or 0) < u.token_epoch:
        raise HTTPException(status_code=401, detail="session revoked — sign in again")
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
        claims = auth.verify_token_claims(token)
        if claims:
            return _resolve_active(db, claims["sub"], claims.get("iat"))
    if aec_token:
        from . import auth
        claims = auth.verify_token_claims(aec_token)
        if claims:
            return _resolve_active(db, claims["sub"], claims.get("iat"))
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


def require_identified(user: str = Depends(current_user)) -> str:
    """A caller who actually authenticated — for PLATFORM-GLOBAL routes with no `{pid}`.

    `current_user` IDENTIFIES; it does not AUTHORISE. With RBAC on and no bearer token, cookie or
    trusted header it returns the literal string `"anonymous"`, so `Depends(current_user)` alone is
    not a gate — it is a name. Routes have shipped with exactly that mistake twice: the
    `/jurisdiction/packs` set (a live probe returned 200 / **201** / 200 with no credentials while
    `GET /admin/errors` correctly returned 403 in the same run), and `/templates` + `/samples/{id}/open`,
    which `test_global_authz` had frozen as known-unguarded rather than fixed.

    This is the platform-global sibling of the `/projects/{pid}` rule in `route-authz-guard`: a route
    that LOOKS guarded because a dependency is present, when the dependency only identifies.

    It lives here rather than in a router because it is general: it was previously defined inside
    `routers/jurisdiction.py`, so every other module needing it would have imported a feature router,
    and deleting that feature would have taken the platform's only global authoriser with it.
    """
    if user in ("anonymous", None, ""):
        raise HTTPException(status_code=403, detail="authentication required")
    return user


def require_platform_admin(db: Session = Depends(get_db),
                           user: str = Depends(current_user)) -> str:
    """A caller allowed to change FIRM-WIDE state — for global routes with no owning project.

    `require_role("admin")` is the wrong gate for a global route, and not merely a weaker one: its
    dependency signature is `dep(pid: str, ...)`, so on a path with no `{pid}` FastAPI exposes `pid`
    as a **caller-supplied query parameter**. The caller therefore chooses which project's role is
    checked. `PUT /firm/rules` was gated that way, and the escalation is complete: register, create
    your own throwaway project (you are its admin), then
    `PUT /firm/rules?pid=<your own project>` → `200 {"saved": 1}`. Verified end to end. Because
    `firm_standards.save_rules` REPLACES the library, the same call also erases the firm's real
    standards — after which every project's rule-check passes with nothing left to check, which is
    worse than a visible failure.

    The pattern here is not new; it was already written correctly for the cost-vintage importer,
    whose docstring names this exact threat ("a lone viewer-role member must never be able to
    silently reprice all projects' estimates"). It lived privately in `routers/cost.py`, so the next
    global route had nothing to reuse and reached for `require_role` instead. That is why it now
    lives beside `require_identified` — a shared gate in a feature router is a gate the next author
    will not find.

    Open where the product is single-operator (RBAC off, LOCAL_MODE, or the api-key identity) so
    desktop and dev are unchanged; otherwise it needs a platform admin. NB for operators: with RBAC
    on, editing firm standards now requires `AEC_ADMIN_EMAILS` to name someone.
    """
    if not RBAC_ON or LOCAL_MODE or user == "api-key":
        return user
    from .routers.auth import require_admin_user  # deferred: routers import rbac, not the reverse
    require_admin_user(db=db, user=user)           # raises 403 unless AEC_ADMIN_EMAILS / legacy admin
    return user


def consume_stepup(db: Session, token: str, act: str, pw_hash: str, actor: str) -> bool:
    """Verify a step-up assertion AND spend it. True exactly once per assertion.

    `verify_stepup_token` alone makes the assertion time-bounded, not single-use: inside its 5-minute
    TTL the same token seals any number of documents. That gap matters for a professional seal
    specifically, because the claim a seal makes is per-document — "this human was in responsible
    charge of THIS work" — and a reusable assertion can only support the weaker "a human re-proved
    their password recently". An agent that captured one token could seal a stack.

    The spend is a PRIMARY KEY insert inside a SAVEPOINT, not a read-then-write: two concurrent
    replays would both pass an `if already_spent` check and both proceed. Here the second insert
    violates the constraint and the database refuses it, so the race has no winner to give away.
    The savepoint means that refusal rolls back only this insert, leaving the caller's transaction
    (and any audit row it has staged) intact.

    Returns False for every failure — bad signature, wrong act, expired, someone else's assertion,
    or already spent — so the caller cannot accidentally distinguish them in a response.
    """
    from sqlalchemy.exc import IntegrityError

    from . import auth as _auth
    from .models import StepUpSpent
    claims = _auth.verify_stepup_claims(token, act, pw_hash)
    if not claims or claims.get("sub") != actor:
        return False
    try:
        with db.begin_nested():
            db.add(StepUpSpent(jti=str(claims["jti"]), sub=actor, act=act))
    except IntegrityError:
        return False                      # already spent — a replay
    try:
        # Opportunistic prune: a spent row is worthless once its assertion could no longer verify.
        # Best-effort by design — failing to tidy must never fail a seal.
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(3600, _auth._STEPUP_TTL * 4))
        with db.begin_nested():
            db.query(StepUpSpent).filter(StepUpSpent.spent_at < cutoff).delete(
                synchronize_session=False)
    except Exception:  # noqa: BLE001
        pass
    return True


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
