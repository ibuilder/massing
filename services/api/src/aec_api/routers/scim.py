"""SCIM 2.0 provisioning (RFC 7643/7644) — lets an enterprise IdP (Okta, Azure AD/Entra, OneLogin,
JumpCloud…) create, update, deactivate, and de-provision Massing accounts automatically as employees
join / move / leave. Users provisioned here are SSO-only (a random password they never use); they
sign in via OAuth/SAML. Deactivation (PATCH active=false or DELETE) blocks login *and* revokes any
live token immediately by bumping the session watermark.

Auth: a single bearer token the IdP is configured with — set `AEC_SCIM_TOKEN` (env or the settings
store). When it isn't set the whole surface returns 503 (feature disabled), so it can't be probed
open. The token is compared in constant time.

Scope: Users (the resource IdPs actually provision). Group push is intentionally out of scope —
per-project authorization lives in ProjectMember, not in IdP groups.
"""
from __future__ import annotations

import hmac
import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, settings_store
from ..db import get_db
from ..models import User

router = APIRouter()

_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


def _scim_token() -> str | None:
    """The configured IdP bearer token (env AEC_SCIM_TOKEN or settings store); None = disabled."""
    tok = settings_store.get("AEC_SCIM_TOKEN")
    return tok.strip() if tok and tok.strip() else None


def _scim_error(status: int, detail: str, scim_type: str | None = None) -> HTTPException:
    body: dict = {"schemas": [_ERROR_SCHEMA], "status": str(status), "detail": detail}
    if scim_type:
        body["scimType"] = scim_type
    return HTTPException(status, detail=body)


def require_scim(authorization: str | None = Header(default=None)) -> bool:
    """Gate every SCIM route on the configured bearer token (constant-time)."""
    configured = _scim_token()
    if not configured:
        raise _scim_error(503, "SCIM provisioning is not configured")
    presented = authorization[7:] if (authorization or "").startswith("Bearer ") else ""
    if not presented or not hmac.compare_digest(presented, configured):
        raise _scim_error(401, "invalid SCIM bearer token")
    return True


def _resource(u: User, request: Request | None = None) -> dict:
    """Serialize a User as a SCIM core User resource."""
    loc = None
    if request is not None:
        loc = str(request.url_for("scim_get_user", user_id=u.username))
    res = {
        "schemas": [_USER_SCHEMA],
        "id": u.username,
        "userName": u.username,
        "active": u.active is not False,
        "meta": {"resourceType": "User", "location": loc},
    }
    if u.external_id:
        res["externalId"] = u.external_id
    if u.email:
        res["emails"] = [{"value": u.email, "primary": True, "type": "work"}]
        res["name"] = {"formatted": u.email}
    return res


def _primary_email(payload: dict) -> str | None:
    emails = payload.get("emails") or []
    if not isinstance(emails, list):
        return None
    primary = next((e for e in emails if isinstance(e, dict) and e.get("primary")), None)
    pick = primary or (emails[0] if emails and isinstance(emails[0], dict) else None)
    v = (pick or {}).get("value") if pick else None
    return v.strip() if isinstance(v, str) and v.strip() else None


def _bump_epoch(u: User) -> None:
    """Revoke any live token for this user (deactivation must take effect immediately, not at expiry)."""
    import time
    u.token_epoch = int(time.time())


@router.get("/scim/v2/ServiceProviderConfig")
def scim_config(_: bool = Depends(require_scim)):
    """Advertise the supported feature set (RFC 7643 §5). We support filter + PATCH, not bulk/sort/etag."""
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "OAuth Bearer Token",
                                    "description": "Authentication via the IdP-configured bearer token"}],
    }


@router.get("/scim/v2/ResourceTypes")
def scim_resource_types(_: bool = Depends(require_scim)):
    return {
        "schemas": [_LIST_SCHEMA], "totalResults": 1, "startIndex": 1, "itemsPerPage": 1,
        "Resources": [{
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
            "id": "User", "name": "User", "endpoint": "/Users", "schema": _USER_SCHEMA,
        }],
    }


def _parse_username_filter(flt: str) -> str | None:
    """Extract the userName from a SCIM `userName eq "x"` filter (the only filter IdPs use here).
    Strip first + a single bounded whitespace run so the pattern has no ambiguous `\\s*…\\s*` (ReDoS)."""
    import re
    m = re.match(r'userName\s+eq\s+"([^"]*)"$', (flt or "").strip(), re.IGNORECASE)
    return m.group(1) if m else None


@router.get("/scim/v2/Users")
def scim_list_users(request: Request, _: bool = Depends(require_scim), db: Session = Depends(get_db),
                    filter: str | None = Query(default=None),  # noqa: A002 — SCIM's param name is "filter"
                    startIndex: int = Query(default=1, ge=1), count: int = Query(default=100, ge=0, le=200)):
    """List (or, with `filter=userName eq "x"`, look up) provisioned users. 1-based paging (RFC 7644)."""
    if filter:
        uname = _parse_username_filter(filter)
        if uname is None:
            raise _scim_error(400, "only `userName eq` filtering is supported", "invalidFilter")
        u = db.get(User, uname)
        matches = [u] if u else []
        total = len(matches)
        page = matches
    else:
        total = db.execute(select(func.count()).select_from(User)).scalar() or 0
        page = list(db.execute(select(User).order_by(User.username)
                               .offset(startIndex - 1).limit(count)).scalars()) if count else []
    return {
        "schemas": [_LIST_SCHEMA], "totalResults": total,
        "startIndex": startIndex, "itemsPerPage": len(page),
        "Resources": [_resource(u, request) for u in page],
    }


@router.get("/scim/v2/Users/{user_id}", name="scim_get_user")
def scim_get_user(user_id: str, request: Request, _: bool = Depends(require_scim),
                  db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise _scim_error(404, f"user {user_id!r} not found")
    return _resource(u, request)


@router.post("/scim/v2/Users", status_code=201)
def scim_create_user(request: Request, _: bool = Depends(require_scim), db: Session = Depends(get_db),
                     payload: dict = Body(...)):
    """Provision a new SSO-only account. Idempotent-ish: re-activating an existing username updates it
    (some IdPs POST on re-provision) rather than 409-ing, so a rehire cleanly reactivates."""
    uname = (payload.get("userName") or "").strip()
    if not uname:
        raise _scim_error(400, "userName is required", "invalidValue")
    existing = db.get(User, uname)
    if existing:
        # treat as re-provision: reactivate + refresh mapped attrs (avoids a hard 409 on rehire)
        existing.active = bool(payload.get("active", True))
        existing.external_id = payload.get("externalId") or existing.external_id
        email = _primary_email(payload)
        if email:
            existing.email = email
        db.commit()
        return JSONResponse(status_code=200, content=_resource(existing, request))
    u = User(
        username=uname,
        password_hash=auth.hash_password(secrets.token_urlsafe(24)),   # SSO-only; unusable password
        role="user",
        active=bool(payload.get("active", True)),
        email=_primary_email(payload),
        external_id=payload.get("externalId"),
        provisioned=True,
    )
    db.add(u)
    db.commit()
    return _resource(u, request)


@router.put("/scim/v2/Users/{user_id}")
def scim_replace_user(user_id: str, request: Request, _: bool = Depends(require_scim),
                      db: Session = Depends(get_db), payload: dict = Body(...)):
    """Full replace of the mutable attributes (userName is immutable — the id)."""
    u = db.get(User, user_id)
    if not u:
        raise _scim_error(404, f"user {user_id!r} not found")
    was_active = u.active is not False
    u.active = bool(payload.get("active", True))
    u.email = _primary_email(payload)
    if "externalId" in payload:
        u.external_id = payload.get("externalId")
    if was_active and not u.active:
        _bump_epoch(u)
    db.commit()
    return _resource(u, request)


def _apply_patch_op(u: User, op: dict) -> None:
    """Apply one PATCH operation. Handles the two shapes IdPs send for deactivation:
    {op:replace, path:active, value:false} (Okta) and {op:replace, value:{active:false}} (Azure)."""
    action = (op.get("op") or "").lower()
    if action not in ("replace", "add"):
        return
    path = (op.get("path") or "").strip()
    value = op.get("value")
    if path.lower() == "active":
        u.active = value if isinstance(value, bool) else str(value).lower() == "true"
    elif path.lower() in ("emails", "emails[type eq \"work\"].value") and value:
        if isinstance(value, str):
            u.email = value
        elif isinstance(value, list):
            u.email = _primary_email({"emails": value}) or u.email
    elif path.lower() == "externalid":
        u.external_id = value
    elif not path and isinstance(value, dict):
        if "active" in value:
            u.active = bool(value["active"])
        if value.get("externalId"):
            u.external_id = value["externalId"]
        em = _primary_email(value)
        if em:
            u.email = em


@router.patch("/scim/v2/Users/{user_id}")
def scim_patch_user(user_id: str, request: Request, _: bool = Depends(require_scim),
                    db: Session = Depends(get_db), payload: dict = Body(...)):
    """Partial update (RFC 7644 §3.5.2). The common case is deactivation on offboarding."""
    u = db.get(User, user_id)
    if not u:
        raise _scim_error(404, f"user {user_id!r} not found")
    was_active = u.active is not False
    for op in payload.get("Operations") or []:
        if isinstance(op, dict):
            _apply_patch_op(u, op)
    if was_active and u.active is False:
        _bump_epoch(u)              # deactivation revokes live tokens immediately
    db.commit()
    return _resource(u, request)


@router.delete("/scim/v2/Users/{user_id}", status_code=204)
def scim_delete_user(user_id: str, _: bool = Depends(require_scim), db: Session = Depends(get_db)):
    """De-provision. Soft-delete: deactivate + revoke tokens (keeps the audit trail / record authorship
    intact) rather than hard-deleting the row. A subsequent POST reactivates (rehire)."""
    u = db.get(User, user_id)
    if not u:
        raise _scim_error(404, f"user {user_id!r} not found")
    if u.active is not False:
        u.active = False
        _bump_epoch(u)
        db.commit()
    return JSONResponse(status_code=204, content=None)
