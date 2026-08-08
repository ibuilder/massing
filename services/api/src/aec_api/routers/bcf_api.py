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

import math
import os
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import audit, rbac, storage
from ..db import get_db
from ..models import Attachment, Comment, Project, Topic, Viewpoint
from ..rbac import current_user, member_project_ids, require_role
from ..serving import range_response

router = APIRouter()


def _xyz(v) -> dict | None:
    """Normalize a {x,y,z} dict or [x,y,z] list → {x,y,z} floats, else None."""
    if isinstance(v, dict) and all(k in v for k in ("x", "y", "z")):
        return {"x": float(v["x"]), "y": float(v["y"]), "z": float(v["z"])}
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}
    return None


def _dir(frm: dict, to: dict) -> dict:
    """Unit direction frm→to (BCF stores camera_direction as a unit vector, not a target point)."""
    d = {"x": to["x"] - frm["x"], "y": to["y"] - frm["y"], "z": to["z"] - frm["z"]}
    n = math.sqrt(d["x"] ** 2 + d["y"] ** 2 + d["z"] ** 2) or 1.0
    return {"x": d["x"] / n, "y": d["y"] / n, "z": d["z"] / n}

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


def viewpoint_to_bcf(v: Viewpoint) -> dict[str, Any]:
    """Map our camera/components/visibility onto the BCF-API 2.1 viewpoint shape (snapshot is fetched
    separately via .../snapshot)."""
    out: dict[str, Any] = {"guid": v.guid}
    cam = v.camera or {}
    pos, tgt = _xyz(cam.get("position")), _xyz(cam.get("target"))
    if pos and tgt:
        out["perspective_camera"] = {
            "camera_view_point": pos, "camera_direction": _dir(pos, tgt),
            "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
            "field_of_view": float(cam.get("fov") or 60)}
    if v.clipping_planes:
        out["clipping_planes"] = v.clipping_planes
    vis = v.visibility or {}
    out["components"] = {
        "selection": [{"ifc_guid": g} for g in (v.components or [])],
        "visibility": {"default_visibility": bool(vis.get("default_visibility", True)),
                       "exceptions": [{"ifc_guid": g} for g in (vis.get("exceptions") or [])]}}
    out["snapshot"] = {"snapshot_type": "png"} if v.snapshot else None
    return out


def _bcf_to_viewpoint_kwargs(body: dict) -> dict[str, Any]:
    """BCF-API viewpoint payload → our Viewpoint columns (camera / components / visibility / snapshot)."""
    pc = body.get("perspective_camera") or body.get("orthogonal_camera") or {}
    vp_pos, vp_dir = _xyz(pc.get("camera_view_point")), _xyz(pc.get("camera_direction"))
    camera = None
    if vp_pos and vp_dir:
        # BCF gives a unit direction, not a target — synthesize a target one unit ahead (the viewer
        # re-derives on load; only the ray matters).
        camera = {"type": "perspective", "position": vp_pos,
                  "target": {k: vp_pos[k] + vp_dir[k] for k in ("x", "y", "z")},
                  "fov": float(pc.get("field_of_view") or 60)}
    comps = body.get("components") or {}
    selection = [s.get("ifc_guid") for s in (comps.get("selection") or []) if s.get("ifc_guid")]
    vis_in = comps.get("visibility") or {}
    visibility = {"default_visibility": bool(vis_in.get("default_visibility", True)),
                  "exceptions": [e.get("ifc_guid") for e in (vis_in.get("exceptions") or []) if e.get("ifc_guid")]}
    snap = body.get("snapshot") or {}
    return {"camera": camera, "clipping_planes": body.get("clipping_planes"),
            "components": selection or None, "visibility": visibility,
            "snapshot": snap.get("snapshot_data")}


def _topic_or_404(db: Session, pid: str, guid: str) -> Topic:
    t = db.query(Topic).filter(Topic.project_id == pid, Topic.guid == guid).first()
    if not t:
        raise HTTPException(404, f"no topic '{guid}' in project")
    return t


# --- version negotiation (unauthenticated — the first call a BCF manager makes) ---------------------
@router.get("/bcf/versions")
def bcf_versions():
    """BCF-API version negotiation. Advertises 2.1 and 3.0; a manager picks the newest it speaks."""
    return {"versions": [{"version_id": "2.1", "detailed_version": "2.1"},
                         {"version_id": "3.0", "detailed_version": "3.0"}]}


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


# --- viewpoints (the camera + selection that makes a topic navigable in 3D) -------------------------
@router.get("/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints")
def bcf_viewpoints(pid: str, guid: str, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    t = _topic_or_404(db, pid, guid)
    rows = db.query(Viewpoint).filter(Viewpoint.topic_id == t.id).order_by(Viewpoint.created_at).all()
    return [viewpoint_to_bcf(v) for v in rows]


@router.post("/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints", status_code=201)
def bcf_create_viewpoint(pid: str, guid: str, body: dict = Body(...), db: Session = Depends(get_db),
                         actor: str = Depends(require_role("reviewer"))):
    """Create a viewpoint from a BCF-API payload (perspective_camera + components + snapshot)."""
    t = _topic_or_404(db, pid, guid)
    v = Viewpoint(topic_id=t.id, **_bcf_to_viewpoint_kwargs(body))
    db.add(v)
    db.flush()
    audit.record(db, action="bcf.viewpoint.create", actor=actor, method="POST", topic_id=t.id,
                 path=f"/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints", detail={})
    db.commit()
    return viewpoint_to_bcf(v)


@router.get("/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints/{vguid}/snapshot")
def bcf_viewpoint_snapshot(pid: str, guid: str, vguid: str, db: Session = Depends(get_db),
                           _: str = Depends(require_role("viewer"))):
    """The viewpoint's PNG snapshot (BCF managers fetch it separately). 404 if none stored."""
    from fastapi import Response
    _topic_or_404(db, pid, guid)
    v = db.query(Viewpoint).filter(Viewpoint.guid == vguid).first()
    if not v or not v.snapshot:
        raise HTTPException(404, "no snapshot for this viewpoint")
    data = v.snapshot.split(",", 1)[-1] if v.snapshot.startswith("data:") else v.snapshot
    import base64
    import binascii
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(404, "snapshot is not decodable PNG data")
    return Response(raw, media_type="image/png")


# ===================================================================================================
# BCF 3.0 — the newer wire shape + documents over the API (R15 carry-over)
#
# Same native rows, a second conformance mapping. What 3.0 adds over our 2.1 surface, and what we
# therefore emit:
#   * ``server_assigned_id`` — the server's own stable handle for a topic (ours is the row id, which
#     is what every other Massing API addresses a topic by, so a BCF manager and our UI agree).
#   * ``authorization`` — what THIS caller may do to the object, resolved from their project role,
#     so a viewer-role integration greys out edit affordances instead of discovering a 403 on save.
#   * **documents** — attachments over the API. BCF 3.0 models documents at project level with
#     per-topic references; our attachments hang off a topic, so the project list is the union of
#     its topics' attachments and an upload targets a topic's ``document_references`` (documented
#     rather than faked — a project-level upload with no topic has nowhere to live in our model).
# ===================================================================================================

_EDIT_ROLES = ("reviewer", "editor", "admin")


def _authorization(db: Session, pid: str, user: str) -> dict[str, Any]:
    """What the caller may do here — role-derived, so the client's UI matches the server's answer."""
    role = None if not rbac.RBAC_ON else rbac.role_for(db, pid, user)
    may_edit = (not rbac.RBAC_ON) or (role in _EDIT_ROLES)
    actions = ["createComment", "createViewpoint", "createDocumentReference"] if may_edit else []
    return {"topic_actions": (["update", *actions] if may_edit else []),
            "topic_status": sorted(_STATUS.values()) if may_edit else []}


def topic_to_bcf3(t: Topic, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    """The 2.1 topic shape plus the 3.0 additions."""
    out = topic_to_bcf(t)
    out["server_assigned_id"] = t.id
    out["reference_links"] = []
    out["document_references"] = [a.id for a in (t.attachments or [])]
    if authorization is not None:
        out["authorization"] = authorization
    return out


def _document_to_bcf3(a: Attachment) -> dict[str, Any]:
    return {"guid": a.id, "filename": a.filename, "content_type": a.content_type,
            "size": int(a.size or 0), "date": _iso(a.created_at)}


@router.get("/bcf/3.0/auth")
def bcf3_auth():
    """Auth discovery (3.0) — Bearer tokens via /auth/login; no separate OAuth flow."""
    return {"oauth2_auth_url": None, "oauth2_token_url": "/auth/login",
            "http_basic_supported": False, "supported_oauth2_flows": []}


@router.get("/bcf/3.0/projects")
def bcf3_projects(db: Session = Depends(get_db), user: str = Depends(current_user)):
    allowed = member_project_ids(db, user)
    q = db.query(Project)
    if allowed is not None:
        q = q.filter(Project.id.in_(allowed))
    return [{"project_id": p.id, "name": p.name,
             "authorization": {"project_actions": ["createTopic", "createDocument"]}}
            for p in q.all()]


@router.get("/bcf/3.0/projects/{pid}/topics")
def bcf3_topics(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    authz = _authorization(db, pid, user)
    rows = (db.query(Topic).filter(Topic.project_id == pid)
            .order_by(Topic.created_at.desc()).limit(2000).all())
    return [topic_to_bcf3(t, authz) for t in rows]


@router.post("/bcf/3.0/projects/{pid}/topics", status_code=201)
def bcf3_create_topic(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                      actor: str = Depends(require_role("reviewer"))):
    """Create a topic from a 3.0 payload — the 2.1 creator, re-serialized in the 3.0 shape."""
    created = bcf_create_topic(pid, body, db, actor)
    t = db.query(Topic).filter(Topic.project_id == pid, Topic.guid == created["guid"]).first()
    return topic_to_bcf3(t, _authorization(db, pid, actor)) if t else created


@router.get("/bcf/3.0/projects/{pid}/topics/{guid}")
def bcf3_topic(pid: str, guid: str, db: Session = Depends(get_db),
               user: str = Depends(require_role("viewer"))):
    return topic_to_bcf3(_topic_or_404(db, pid, guid), _authorization(db, pid, user))


@router.get("/bcf/3.0/projects/{pid}/topics/{guid}/comments")
def bcf3_comments(pid: str, guid: str, db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    t = _topic_or_404(db, pid, guid)
    return [comment_to_bcf(c, guid) for c in sorted(t.comments, key=lambda c: c.created_at or 0)]


@router.post("/bcf/3.0/projects/{pid}/topics/{guid}/comments", status_code=201)
def bcf3_create_comment(pid: str, guid: str, body: dict = Body(...), db: Session = Depends(get_db),
                        actor: str = Depends(require_role("reviewer"))):
    return bcf_create_comment(pid, guid, body, db, actor)


@router.get("/bcf/3.0/projects/{pid}/topics/{guid}/viewpoints")
def bcf3_viewpoints(pid: str, guid: str, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    t = _topic_or_404(db, pid, guid)
    return [viewpoint_to_bcf(v) for v in t.viewpoints]


# --- documents (3.0 attachments over the API) -------------------------------------------------------
@router.get("/bcf/3.0/projects/{pid}/documents")
def bcf3_documents(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Every document in the project — the union of its topics' attachments, newest first."""
    rows = (db.query(Attachment).join(Topic, Attachment.topic_id == Topic.id)
            .filter(Topic.project_id == pid)
            .order_by(Attachment.created_at.desc()).limit(2000).all())
    return [_document_to_bcf3(a) for a in rows]


@router.get("/bcf/3.0/projects/{pid}/documents/{doc_guid}")
def bcf3_document_download(pid: str, doc_guid: str, request: Request, db: Session = Depends(get_db),
                           _: str = Depends(require_role("viewer"))):
    """Download one document's bytes (project-scoped, so a guid from another project 404s)."""
    a = (db.query(Attachment).join(Topic, Attachment.topic_id == Topic.id)
         .filter(Topic.project_id == pid, Attachment.id == doc_guid).first())
    if not a:
        raise HTTPException(404, "no such document in this project")
    return range_response(request, a.storage_key, a.content_type or "application/octet-stream",
                          filename=a.filename, disposition="attachment")


@router.get("/bcf/3.0/projects/{pid}/topics/{guid}/document_references")
def bcf3_document_refs(pid: str, guid: str, db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    t = _topic_or_404(db, pid, guid)
    return [{"guid": a.id, "document_guid": a.id, "description": a.filename}
            for a in (t.attachments or [])]


@router.post("/bcf/3.0/projects/{pid}/topics/{guid}/document_references", status_code=201)
async def bcf3_add_document(pid: str, guid: str, file: UploadFile = File(...),
                            db: Session = Depends(get_db),
                            _: str = Depends(require_role("reviewer"))):
    """Attach a document to a topic over the BCF API (the coordinator's tool uploads the PDF/photo
    directly). Same storage path and filename hardening as the native attachment route."""
    t = _topic_or_404(db, pid, guid)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(file.filename or "file")).lstrip(".") or "file"
    safe = safe.replace("..", "_")
    key = f"{pid}/{t.id}/{safe}"
    # R41-UPLOAD-WARK: streamed, exactly as the native attachment route does. Converted TOGETHER
    # with its twin on purpose — this route's docstring says "same storage path and filename
    # hardening as the native attachment route", and a pair that claims to be the same shape is
    # precisely the place a one-sided change goes unnoticed.
    size = await run_in_threadpool(storage.put_stream, key, storage.upload_chunks(file))
    a = Attachment(topic_id=t.id, filename=file.filename, content_type=file.content_type,
                   size=size, kind="file", storage_key=key)
    db.add(a)
    audit.record(db, action="bcf.document.create", method="POST", topic_id=t.id,
                 path=f"/bcf/3.0/projects/{pid}/topics/{guid}/document_references",
                 detail={"filename": file.filename})
    db.commit()
    return {"guid": a.id, "document_guid": a.id, "description": a.filename}
