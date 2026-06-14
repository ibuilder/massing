"""Project, Topic (RFI/punch/clash/info), Comment, Viewpoint, Attachment, Pin, and BCF
endpoints (guide §7). Modeled on BCF-API so issues round-trip with other BIM tools."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import audit, bcf_io, storage
from ..auth import require_writer
from ..db import get_db
from ..models import Attachment, Comment, Project, Topic, Viewpoint
from ..schemas import (
    AttachmentOut, CommentIn, CommentOut, ProjectIn, ProjectOut,
    TopicIn, TopicOut, TopicPatch, ViewpointIn, ViewpointOut,
)

router = APIRouter()


# --- projects ----------------------------------------------------------------
@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db),
                   actor: str = Depends(require_writer)):
    p = Project(name=body.name, origin=body.origin)
    db.add(p)
    audit.record(db, action="project.create", actor=actor, method="POST",
                 path="/projects", detail={"name": body.name})
    db.commit()
    return p


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@router.get("/projects/{pid}", response_model=ProjectOut)
def get_project(pid: str, db: Session = Depends(get_db)):
    return _project(db, pid)


# --- topics ------------------------------------------------------------------
@router.post("/projects/{pid}/topics", response_model=TopicOut, status_code=201)
def create_topic(pid: str, body: TopicIn, db: Session = Depends(get_db),
                 actor: str = Depends(require_writer)):
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
                actor: str = Depends(require_writer)):
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
def add_comment(pid: str, tid: str, body: CommentIn, db: Session = Depends(get_db)):
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
def add_viewpoint(pid: str, tid: str, body: ViewpointIn, db: Session = Depends(get_db)):
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
                         file: UploadFile = File(...), db: Session = Depends(get_db)):
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
def download_attachment(aid: str, db: Session = Depends(get_db)):
    a = db.get(Attachment, aid)
    if not a:
        raise HTTPException(404, "attachment not found")
    return Response(storage.get(a.storage_key), media_type=a.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{a.filename}"'})


# --- BCF interoperability ----------------------------------------------------
@router.get("/projects/{pid}/bcf/export")
def bcf_export(pid: str, db: Session = Depends(get_db)):
    _project(db, pid)
    data = bcf_io.export_bcfzip(db, pid)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{pid}.bcfzip"'})


@router.post("/projects/{pid}/bcf/import")
async def bcf_import(pid: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
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
