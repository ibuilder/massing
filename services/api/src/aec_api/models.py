"""BCF-shaped ORM models (guide §7). Elements are referenced by IFC GlobalId (GUID),
never transient viewer IDs, so links survive re-conversion and model updates."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # working origin / georeferencing offset, persisted per project (guide §6)
    origin: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # server-side path to the source IFC, used by the data-export endpoints (guide §8)
    source_ifc: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topics: Mapped[list["Topic"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Scenario(Base):
    """A modeled version of a development deal (Proforma). assumptions + last solved result
    stored as JSON so scenarios version/diff cheaply (guide §5)."""
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_locked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProjectMember(Base):
    """Project-scoped roles. Two dimensions (GC portal):
      - CRUD capability role: viewer < reviewer < editor < admin
      - party role (workflow gate): GC | Owner | OwnersRep | Consultant | Subcontractor"""
    __tablename__ = "project_members"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, default="viewer")
    party_role: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RecordComment(Base):
    """Comments on any GC module record (shared table, keyed by module + record_id)."""
    __tablename__ = "record_comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    module: Mapped[str] = mapped_column(String, index=True)
    record_id: Mapped[str] = mapped_column(String, index=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RecordActivity(Base):
    """Per-record activity timeline shared by all GC modules (create/update/transition/link)."""
    __tablename__ = "record_activity"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    module: Mapped[str] = mapped_column(String, index=True)
    record_id: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    party: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Topic(Base):
    """An RFI / punchlist item / clash / info note. A *pin* is a Topic with an anchor."""
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    guid: Mapped[str] = mapped_column(String, default=_uuid, index=True)  # BCF topic guid
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)

    type: Mapped[str] = mapped_column(String, default="info")  # rfi|punch|clash|info
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    priority: Mapped[str | None] = mapped_column(String, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    labels: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # pin overlay: 3D anchor + the element GUID(s) it references
    anchor: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {x,y,z}
    element_guids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    project: Mapped["Project"] = relationship(back_populates="topics")
    comments: Mapped[list["Comment"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    viewpoints: Mapped[list["Viewpoint"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    viewpoint_id: Mapped[str | None] = mapped_column(ForeignKey("viewpoints.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="comments")


class Viewpoint(Base):
    """Camera + clipping + visibility + components[guid] — restored by the viewer (guide §6)."""
    __tablename__ = "viewpoints"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    guid: Mapped[str] = mapped_column(String, default=_uuid, index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)

    camera: Mapped[dict | None] = mapped_column(JSON, nullable=True)        # {type, position, target, fov}
    clipping_planes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    visibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # {default_visibility, exceptions[guid]}
    components: Mapped[list | None] = mapped_column(JSON, nullable=True)    # selected element GUIDs
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)       # data-uri png (optional)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="viewpoints")


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[int] = mapped_column(Float, default=0)
    kind: Mapped[str] = mapped_column(String, default="file")  # drawing|photo|pdf|file
    storage_key: Mapped[str] = mapped_column(String, nullable=False)  # object-storage key/path
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="attachments")


class AuditLog(Base):
    """Audit log on all write endpoints — RFIs/punchlist are contractual records (guide §10)."""
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
