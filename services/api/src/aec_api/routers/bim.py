"""Project, Topic (RFI/punch/clash/info), Comment, Viewpoint, Attachment, Pin, and BCF
endpoints (guide §7). Modeled on BCF-API so issues round-trip with other BIM tools."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from pydantic import BaseModel

from .. import audit, bcf_io, rbac, storage
from ..db import get_db
from ..models import Attachment, Comment, DrawingMarkup, Project, ProjectMember, Topic, Viewpoint
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


# --- drawing markup (2D sheet pins/redlines; promotable to RFIs) --------------
class MarkupIn(BaseModel):
    sheet_id: str
    x: float
    y: float
    note: str | None = None


def _markup_out(m: DrawingMarkup) -> dict:
    return {"id": m.id, "sheet_id": m.sheet_id, "x": m.x, "y": m.y, "note": m.note,
            "author": m.author, "topic_id": m.topic_id, "created_at": m.created_at}


@router.get("/projects/{pid}/drawings/markup")
def list_markup(pid: str, sheet: str | None = None, db: Session = Depends(get_db),
                _: str = Depends(require_role("viewer"))):
    """Markup pins for a project, optionally filtered to one sheet."""
    q = db.query(DrawingMarkup).filter(DrawingMarkup.project_id == pid)
    if sheet:
        q = q.filter(DrawingMarkup.sheet_id == sheet)
    return [_markup_out(m) for m in q.order_by(DrawingMarkup.created_at).all()]


@router.post("/projects/{pid}/drawings/markup", status_code=201)
def add_markup(pid: str, body: MarkupIn, db: Session = Depends(get_db),
               actor: str = Depends(require_role("reviewer"))):
    m = DrawingMarkup(project_id=pid, sheet_id=body.sheet_id, x=body.x, y=body.y,
                      note=body.note, author=actor)
    db.add(m)
    db.commit()
    return _markup_out(m)


@router.delete("/projects/{pid}/drawings/markup/{mid}")
def delete_markup(pid: str, mid: str, db: Session = Depends(get_db),
                  _: str = Depends(require_role("reviewer"))):
    m = db.get(DrawingMarkup, mid)
    if not m or m.project_id != pid:
        raise HTTPException(404, "no such markup")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/drawings/markup/{mid}/promote", status_code=201)
def promote_markup(pid: str, mid: str, db: Session = Depends(get_db),
                   actor: str = Depends(require_role("reviewer"))):
    """Promote a markup pin to an RFI Topic (Fieldlens/PlanGrid: a located issue on the sheet)."""
    m = db.get(DrawingMarkup, mid)
    if not m or m.project_id != pid:
        raise HTTPException(404, "no such markup")
    if m.topic_id:
        raise HTTPException(409, "markup already linked to an RFI")
    t = Topic(project_id=pid, type="rfi", status="open", author=actor,
              title=(m.note or "Drawing RFI")[:80],
              description=f"Raised from a drawing markup on sheet '{m.sheet_id}'.\n\n{m.note or ''}")
    db.add(t)
    db.flush()
    m.topic_id = t.id
    audit.record(db, action="markup.promote", actor=actor, method="POST", topic_id=t.id,
                 path=f"/projects/{pid}/drawings/markup/{mid}/promote", detail={"sheet": m.sheet_id})
    db.commit()
    return {"markup": _markup_out(m), "topic": {"id": t.id, "type": t.type, "title": t.title, "status": t.status}}


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


def _model_kind(p: Project) -> str | None:
    """What loadable geometry a project has — drives the picker's type tag.
    'frag' = a published Fragments tile (opens in the 3D viewer); 'ifc' = a source IFC on disk
    (drawings render, can be published to frag); None = no model yet."""
    from pathlib import Path
    if storage.exists(f"{p.id}/model.frag"):
        return "frag"
    if p.source_ifc and Path(p.source_ifc).exists():
        return "ifc"
    return None


def _with_kind(p: Project) -> Project:
    from pathlib import Path
    p.model_kind = _model_kind(p)               # set the (non-column) fields ProjectOut reads
    p.has_source_ifc = bool(p.source_ifc and Path(p.source_ifc).exists())
    return p


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return [_with_kind(p) for p in db.query(Project).all()]


@router.get("/projects/{pid}", response_model=ProjectOut)
def get_project(pid: str, db: Session = Depends(get_db)):
    return _with_kind(_project(db, pid))


@router.delete("/projects/{pid}")
def delete_project(pid: str, db: Session = Depends(get_db),
                   actor: str = Depends(require_role("admin"))):
    """Delete a project and everything it owns (rows + geometry + attachment blobs)."""
    from .. import bundle as bundle_io
    p = _project(db, pid)
    audit.record(db, action="project.delete", actor=actor, method="DELETE",
                 path=f"/projects/{pid}", detail={"id": pid, "name": p.name})
    return bundle_io.delete_project(db, pid)


@router.get("/projects/{pid}/versions")
def list_versions(pid: str, db: Session = Depends(get_db)):
    """Model version history — one snapshot per publish (version, element count, +N/-N note)."""
    from .. import versions
    return versions.history(db, pid)


@router.get("/projects/{pid}/versions/diff")
def diff_versions(pid: str, a: int, b: int, db: Session = Depends(get_db)):
    """Changed elements between two model versions — added / removed GUIDs + unchanged count."""
    from .. import versions
    return versions.diff(db, pid, a, b)


@router.get("/projects/{pid}/bundle")
def export_bundle(pid: str, db: Session = Depends(get_db)):
    """Download the whole project as a portable .mmproj bundle (geometry + all data + blobs)."""
    from .. import bundle as bundle_io
    p = _project(db, pid)
    data = bundle_io.export_bundle(db, pid)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p.name).strip() or "project"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.mmproj"'})


@router.post("/projects/import-bundle", response_model=ProjectOut, status_code=201)
async def import_bundle(file: UploadFile = File(...), name: str | None = Form(None),
                        db: Session = Depends(get_db)):
    """Open a .mmproj bundle as a new project (fresh id) — geometry, data, and blobs restored."""
    from .. import bundle as bundle_io
    new_pid = bundle_io.import_bundle(db, await file.read(), new_name=name)
    return _with_kind(_project(db, new_pid))


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
