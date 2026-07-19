"""BCF-API-SRV (R15) — a server-side **BCF-API 2.1 / OpenCDE** surface over the native BCF model.

The platform already stores issues as BCF-model Topics (+ comments + viewpoints) and round-trips
`.bcfzip`. This exposes the **standard REST endpoints** (buildingSMART's open BCF-API 2.1 spec) that
external BCF managers — Revit, Navisworks, Solibri, BIMcollab, usBIM — connect to live, so a
coordinator's tool syncs topics/comments directly instead of exchanging files.

It's a thin conformance mapping onto the existing `Topic` / `Comment` rows (addressed by their BCF
`guid`), reusing the platform's Bearer-token auth via `require_role`. Scope: version negotiation +
projects + topics (list/get/create) + comments (list/create) — the sync essentials.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import Comment, Project, Topic
from ..rbac import current_user, member_project_ids, require_role

router = APIRouter()

# our free-form status/type → BCF TitleCase (extension values are allowed, so a passthrough title-case
# is spec-safe); managers display whatever they receive.
_STATUS = {"open": "Open", "closed": "Closed", "in_progress": "In Progress", "resolved": "Resolved",
           "reopened": "ReOpened"}
_TYPE = {"issue": "Issue", "clash": "Clash", "rfi": "Request", "punch": "Issue", "info": "Comment"}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def topic_to_bcf(t: Topic) -> dict[str, Any]:
    return {
        "guid": t.guid,
        "topic_type": _TYPE.get((t.type or "").lower(), (t.type or "Issue").title()),
        "topic_status": _STATUS.get((t.status or "").lower(), (t.status or "Open").title()),
        "priority": t.priority,
        "title": t.title,
        "description": t.description,
        "labels": t.labels or [],
        "assigned_to": t.assignee,
        "due_date": _iso(t.due_date),
        "creation_author": t.author,
        "creation_date": _iso(t.created_at),
        "modified_author": t.author,
        "modified_date": _iso(t.modified_at),
    }


def comment_to_bcf(c: Comment, topic_guid: str) -> dict[str, Any]:
    return {"guid": c.id, "date": _iso(c.created_at), "author": c.author,
            "comment": c.text, "topic_guid": topic_guid,
            "viewpoint_guid": c.viewpoint_id}


def _topic_or_404(db: Session, pid: str, guid: str) -> Topic:
    t = db.query(Topic).filter(Topic.project_id == pid, Topic.guid == guid).first()
    if not t:
        raise HTTPException(404, f"no topic '{guid}' in project")
    return t


# --- version negotiation (unauthenticated — the first call a BCF manager makes) ---------------------
@router.get("/bcf/versions")
def bcf_versions():
    """BCF-API version negotiation. Advertises 2.1 support."""
    return {"versions": [{"version_id": "2.1", "detailed_version": "2.1"}]}


@router.get("/bcf/2.1/auth")
def bcf_auth():
    """Auth discovery — the platform uses Bearer tokens (see /auth/login); no separate OAuth flow."""
    return {"oauth2_auth_url": None, "oauth2_token_url": "/auth/login",
            "http_basic_supported": False, "supported_oauth2_flows": []}


# --- projects ---------------------------------------------------------------------------------------
@router.get("/bcf/2.1/projects")
def bcf_projects(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Projects the caller can access, in BCF-API shape."""
    allowed = member_project_ids(db, user)            # None = unrestricted (RBAC off / admin)
    q = db.query(Project)
    if allowed is not None:
        q = q.filter(Project.id.in_(allowed))
    return [{"project_id": p.id, "name": p.name} for p in q.all()]


# --- topics (path param named `pid` so require_role resolves it; transparent to BCF clients) --------
@router.get("/bcf/2.1/projects/{pid}/topics")
def bcf_topics(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    rows = db.query(Topic).filter(Topic.project_id == pid).order_by(Topic.created_at.desc()).limit(2000).all()
    return [topic_to_bcf(t) for t in rows]


@router.post("/bcf/2.1/projects/{pid}/topics", status_code=201)
def bcf_create_topic(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                     actor: str = Depends(require_role("reviewer"))):
    """Create a topic from a BCF-API payload (title required; topic_type / topic_status / priority /
    labels / assigned_to / description optional)."""
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(422, "title is required")
    inv_status = {v: k for k, v in _STATUS.items()}
    inv_type = {v: k for k, v in _TYPE.items()}
    t = Topic(project_id=pid, title=title,
              type=inv_type.get(body.get("topic_type"), (body.get("topic_type") or "issue").lower()),
              status=inv_status.get(body.get("topic_status"), (body.get("topic_status") or "open").lower()),
              priority=body.get("priority"), assignee=body.get("assigned_to"),
              author=body.get("creation_author") or actor,
              description=body.get("description"),
              labels=body.get("labels") if isinstance(body.get("labels"), list) else None)
    db.add(t)
    db.flush()
    audit.record(db, action="bcf.topic.create", actor=actor, method="POST", topic_id=t.id,
                 path=f"/bcf/2.1/projects/{pid}/topics", detail={"title": title})
    db.commit()
    return topic_to_bcf(t)


@router.get("/bcf/2.1/projects/{pid}/topics/{guid}")
def bcf_topic(pid: str, guid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return topic_to_bcf(_topic_or_404(db, pid, guid))


# --- comments ---------------------------------------------------------------------------------------
@router.get("/bcf/2.1/projects/{pid}/topics/{guid}/comments")
def bcf_comments(pid: str, guid: str, db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    t = _topic_or_404(db, pid, guid)
    rows = db.query(Comment).filter(Comment.topic_id == t.id).order_by(Comment.created_at).all()
    return [comment_to_bcf(c, guid) for c in rows]


@router.post("/bcf/2.1/projects/{pid}/topics/{guid}/comments", status_code=201)
def bcf_create_comment(pid: str, guid: str, body: dict = Body(...), db: Session = Depends(get_db),
                       actor: str = Depends(require_role("reviewer"))):
    t = _topic_or_404(db, pid, guid)
    text = (body.get("comment") or "").strip()
    if not text:
        raise HTTPException(422, "comment is required")
    c = Comment(topic_id=t.id, text=text, author=body.get("author") or actor,
                viewpoint_id=body.get("viewpoint_guid"))
    db.add(c)
    db.flush()
    audit.record(db, action="bcf.comment.create", actor=actor, method="POST", topic_id=t.id,
                 path=f"/bcf/2.1/projects/{pid}/topics/{guid}/comments", detail={})
    db.commit()
    return comment_to_bcf(c, guid)
