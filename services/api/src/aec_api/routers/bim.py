"""Project, Topic (RFI/punch/clash/info), Comment, Viewpoint, Attachment, Pin, and BCF
endpoints (guide §7). Modeled on BCF-API so issues round-trip with other BIM tools."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from pydantic import BaseModel

from .. import audit, bcf_io, rbac, storage
from ..db import get_db
from ..models import Attachment, Comment, Project, ProjectMember, Topic, Viewpoint
from ..rbac import current_user, require_role
from ..serving import range_response
from ..schemas import (
    AttachmentOut, CommentIn, CommentOut, ProjectIn, ProjectOut, ProjectPatch,
    TopicIn, TopicOut, TopicPatch, ViewpointIn, ViewpointOut,
)

router = APIRouter()


# --- projects ----------------------------------------------------------------
@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db),
                   actor: str = Depends(current_user)):
    p = Project(name=body.name, origin=body.origin, source_ifc=body.source_ifc)
    db.add(p)
    db.flush()
    rbac.grant(db, p.id, actor, "admin", party_role="GC")  # creator: admin + GC party
    audit.record(db, action="project.create", actor=actor, method="POST",
                 path="/projects", detail={"name": body.name})
    db.commit()
    return p


# --- members (RBAC) ----------------------------------------------------------
class MemberIn(BaseModel):
    user: str
    role: str
    party_role: str | None = None
    company: str | None = None


@router.get("/projects/{pid}/me")
def my_membership(pid: str, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """The caller's own effective role on this project — drives UI capability gating. No role
    required (a non-member gets role=null). `rbac` tells the client whether gating is enforced;
    when it's off the client should treat the user as fully capable (matching the open API)."""
    return {"user": user, "role": rbac.role_for(db, pid, user),
            "party_role": rbac.party_role_for(db, pid, user), "rbac": rbac.RBAC_ON}


@router.post("/projects/{pid}/presence")
def heartbeat(pid: str, viewpoint: dict | None = Body(default=None, embed=True),
              user: str = Depends(current_user)):
    """Heartbeat presence (optionally sharing the current camera viewpoint) and get the live
    roster of other users viewing this project."""
    from .. import presence
    presence.touch(pid, user, viewpoint)
    return {"user": user, "active": presence.active(pid, exclude=user)}


@router.get("/projects/{pid}/presence")
def presence_roster(pid: str, user: str = Depends(current_user)):
    """Other users currently viewing this project (heartbeat within the TTL)."""
    from .. import presence
    return {"active": presence.active(pid, exclude=user)}


@router.get("/projects/{pid}/members")
def list_members(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    rows = db.query(ProjectMember).filter(ProjectMember.project_id == pid).all()
    return [{"user": m.user, "role": m.role, "party_role": m.party_role, "company": m.company}
            for m in rows]


@router.post("/projects/{pid}/members", status_code=201)
def add_member(pid: str, body: MemberIn, db: Session = Depends(get_db),
               actor: str = Depends(require_role("admin"))):
    _project(db, pid)
    m = rbac.grant(db, pid, body.user, body.role, party_role=body.party_role)
    if body.company is not None:
        m.company = body.company
    audit.record(db, action="member.grant", actor=actor, method="POST", path=f"/projects/{pid}/members",
                 detail={"user": body.user, "role": body.role, "party_role": body.party_role})
    db.commit()
    return {"user": m.user, "role": m.role, "party_role": m.party_role}


@router.delete("/projects/{pid}/members/{member}")
def remove_member(pid: str, member: str, db: Session = Depends(get_db),
                  actor: str = Depends(require_role("admin"))):
    """Remove a member from the project. Won't remove the last admin (avoids an orphaned project)."""
    m = db.query(ProjectMember).filter(
        ProjectMember.project_id == pid, ProjectMember.user == member).first()
    if not m:
        raise HTTPException(404, "not a member of this project")
    if m.role == "admin":
        others = db.query(ProjectMember).filter(
            ProjectMember.project_id == pid, ProjectMember.role == "admin",
            ProjectMember.user != member).count()
        if others == 0:
            raise HTTPException(400, "cannot remove the last project admin")
    db.delete(m)
    audit.record(db, action="member.remove", actor=actor, method="DELETE",
                 path=f"/projects/{pid}/members/{member}", detail={"user": member})
    db.commit()
    return {"ok": True}


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@router.get("/projects/{pid}", response_model=ProjectOut)
def get_project(pid: str, db: Session = Depends(get_db)):
    return _project(db, pid)


@router.patch("/projects/{pid}", response_model=ProjectOut)
def patch_project(pid: str, body: ProjectPatch, db: Session = Depends(get_db),
                  actor: str = Depends(require_role("admin"))):
    p = _project(db, pid)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit.record(db, action="project.update", actor=actor, method="PATCH",
                 path=f"/projects/{pid}", detail=changes)
    db.commit()
    return p


# --- topics ------------------------------------------------------------------
@router.post("/projects/{pid}/topics", response_model=TopicOut, status_code=201)
def create_topic(pid: str, body: TopicIn, db: Session = Depends(get_db),
                 actor: str = Depends(require_role("reviewer"))):
    _project(db, pid)
    t = Topic(project_id=pid, **body.model_dump())
    db.add(t)
    db.flush()
    audit.record(db, action="topic.create", actor=actor, method="POST", topic_id=t.id,
                 path=f"/projects/{pid}/topics", detail={"type": t.type, "title": t.title})
    db.commit()
    return t


@router.get("/projects/{pid}/topics", response_model=list[TopicOut])
def list_topics(pid: str, type: str | None = None, status: str | None = None,
                db: Session = Depends(get_db)):
    q = db.query(Topic).filter(Topic.project_id == pid)
    if type:
        q = q.filter(Topic.type == type)
    if status:
        q = q.filter(Topic.status == status)
    return q.order_by(Topic.created_at).all()


@router.get("/projects/{pid}/topics/{tid}", response_model=TopicOut)
def get_topic(pid: str, tid: str, db: Session = Depends(get_db)):
    return _topic(db, pid, tid)


@router.patch("/projects/{pid}/topics/{tid}", response_model=TopicOut)
def patch_topic(pid: str, tid: str, body: TopicPatch, db: Session = Depends(get_db),
                actor: str = Depends(require_role("reviewer"))):
    t = _topic(db, pid, tid)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t, k, v)
    audit.record(db, action="topic.update", actor=actor, method="PATCH", topic_id=t.id,
                 path=f"/projects/{pid}/topics/{tid}", detail=changes)
    db.commit()
    return t


# --- pins (topics with a 3D anchor) -----------------------------------------
@router.get("/projects/{pid}/pins", response_model=list[TopicOut])
def list_pins(pid: str, db: Session = Depends(get_db)):
    return db.query(Topic).filter(Topic.project_id == pid, Topic.anchor.isnot(None)).all()


# --- comments ----------------------------------------------------------------
@router.post("/projects/{pid}/topics/{tid}/comments", response_model=CommentOut, status_code=201)
def add_comment(pid: str, tid: str, body: CommentIn, db: Session = Depends(get_db),
                _: str = Depends(require_role("reviewer"))):
    _topic(db, pid, tid)
    c = Comment(topic_id=tid, **body.model_dump())
    db.add(c)
    audit.record(db, action="comment.create", method="POST", topic_id=tid,
                 path=f"/projects/{pid}/topics/{tid}/comments")
    db.commit()
    return c


@router.get("/projects/{pid}/topics/{tid}/comments", response_model=list[CommentOut])
def list_comments(pid: str, tid: str, db: Session = Depends(get_db)):
    _topic(db, pid, tid)
    return db.query(Comment).filter(Comment.topic_id == tid).order_by(Comment.created_at).all()


# --- viewpoints --------------------------------------------------------------
@router.post("/projects/{pid}/topics/{tid}/viewpoints", response_model=ViewpointOut, status_code=201)
def add_viewpoint(pid: str, tid: str, body: ViewpointIn, db: Session = Depends(get_db),
                  _: str = Depends(require_role("reviewer"))):
    _topic(db, pid, tid)
    v = Viewpoint(topic_id=tid, **body.model_dump())
    db.add(v)
    audit.record(db, action="viewpoint.create", method="POST", topic_id=tid,
                 path=f"/projects/{pid}/topics/{tid}/viewpoints")
    db.commit()
    return v


@router.get("/projects/{pid}/topics/{tid}/viewpoints", response_model=list[ViewpointOut])
def list_viewpoints(pid: str, tid: str, db: Session = Depends(get_db)):
    _topic(db, pid, tid)
    return db.query(Viewpoint).filter(Viewpoint.topic_id == tid).all()


# --- attachments (drawings, photos, PDFs) -----------------------------------
@router.post("/projects/{pid}/topics/{tid}/attachments", response_model=AttachmentOut, status_code=201)
async def add_attachment(pid: str, tid: str, kind: str = Form("file"),
                         file: UploadFile = File(...), db: Session = Depends(get_db),
                         _: str = Depends(require_role("reviewer"))):
    _topic(db, pid, tid)
    data = await file.read()
    key = f"{pid}/{tid}/{file.filename}"
    storage.put(key, data)
    a = Attachment(topic_id=tid, filename=file.filename, content_type=file.content_type,
                   size=len(data), kind=kind, storage_key=key)
    db.add(a)
    audit.record(db, action="attachment.create", method="POST", topic_id=tid,
                 path=f"/projects/{pid}/topics/{tid}/attachments", detail={"filename": file.filename})
    db.commit()
    return a


@router.get("/projects/{pid}/topics/{tid}/attachments", response_model=list[AttachmentOut])
def list_attachments(pid: str, tid: str, db: Session = Depends(get_db)):
    _topic(db, pid, tid)
    return db.query(Attachment).filter(Attachment.topic_id == tid).all()


@router.get("/attachments/{aid}/download")
def download_attachment(aid: str, request: Request, db: Session = Depends(get_db)):
    a = db.get(Attachment, aid)
    if not a:
        raise HTTPException(404, "attachment not found")
    return range_response(request, a.storage_key, a.content_type or "application/octet-stream",
                          filename=a.filename, disposition="attachment")


@router.get("/projects/{pid}/model.frag")
def model_frag(pid: str, request: Request):
    """Serve the published Fragments tile with HTTP range support (streaming)."""
    return range_response(request, f"{pid}/model.frag", "application/octet-stream",
                          filename="model.frag")


@router.get("/projects/{pid}/source.ifc")
def source_ifc_download(pid: str, db: Session = Depends(get_db)):
    """Download the project's source IFC (Save → Export IFC)."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    p = _project(db, pid)
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC")
    return FileResponse(p.source_ifc, filename=Path(p.source_ifc).name,
                        media_type="application/octet-stream")


# --- BCF interoperability ----------------------------------------------------
@router.get("/projects/{pid}/bcf/export")
def bcf_export(pid: str, db: Session = Depends(get_db)):
    _project(db, pid)
    data = bcf_io.export_bcfzip(db, pid)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{pid}.bcfzip"'})


@router.post("/projects/{pid}/bcf/import")
async def bcf_import(pid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                     _: str = Depends(require_role("editor"))):
    _project(db, pid)
    count = bcf_io.import_bcfzip(db, pid, await file.read())
    audit.record(db, action="bcf.import", method="POST", path=f"/projects/{pid}/bcf/import",
                 detail={"topics": count})
    db.commit()
    return {"imported": count}


# --- helpers -----------------------------------------------------------------
def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def _topic(db: Session, pid: str, tid: str) -> Topic:
    t = db.get(Topic, tid)
    if not t or t.project_id != pid:
        raise HTTPException(404, "topic not found")
    return t
