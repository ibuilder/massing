"""Pydantic v2 schemas (guide §1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TopicType = Literal["rfi", "punch", "clash", "info"]


class ProjectIn(BaseModel):
    name: str
    origin: dict[str, Any] | None = None
    source_ifc: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    origin: dict[str, Any] | None = None
    source_ifc: str | None = None
    # CODE-1: per-project jurisdiction (USPS state code) — code checkers auto-resolve the edition
    jurisdiction: str | None = None


class ProjectOut(ProjectIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    # what geometry the project actually has, for the picker: "frag" (published tile, loads in
    # the 3D viewer), "ifc" (source IFC only — drawings render, can be published), or None (empty).
    model_kind: str | None = None
    # whether a source IFC is on disk — gates IFC-only tools (drawings, clash/IDS, energy, authoring).
    # Independent of model_kind, since a project can have a published .frag with no source IFC.
    has_source_ifc: bool = False
    jurisdiction: str | None = None


class TopicIn(BaseModel):
    type: TopicType = "info"
    title: str
    description: str | None = None
    status: str = "open"
    priority: str | None = None
    assignee: str | None = None
    author: str | None = None
    due_date: datetime | None = None
    labels: list[str] | None = None
    anchor: dict[str, float] | None = None          # pin: {x,y,z}
    element_guids: list[str] | None = None           # referenced IFC GUIDs


class TopicPatch(BaseModel):
    type: TopicType | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    due_date: datetime | None = None
    labels: list[str] | None = None
    anchor: dict[str, float] | None = None
    element_guids: list[str] | None = None


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    guid: str
    project_id: str
    type: str
    title: str
    description: str | None
    status: str
    priority: str | None
    assignee: str | None
    author: str | None
    due_date: datetime | None
    labels: list[str] | None
    anchor: dict[str, float] | None
    element_guids: list[str] | None
    created_at: datetime
    modified_at: datetime


class CommentIn(BaseModel):
    author: str | None = None
    text: str
    viewpoint_id: str | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_id: str
    author: str | None
    text: str
    viewpoint_id: str | None
    created_at: datetime


class ViewpointIn(BaseModel):
    camera: dict[str, Any] | None = None
    clipping_planes: list[dict[str, Any]] | None = None
    visibility: dict[str, Any] | None = None
    components: list[str] | None = None
    snapshot: str | None = None


class ViewpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    guid: str
    topic_id: str
    camera: dict[str, Any] | None
    clipping_planes: list[dict[str, Any]] | None
    visibility: dict[str, Any] | None
    components: list[str] | None
    snapshot: str | None
    created_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_id: str
    filename: str
    content_type: str | None
    size: float
    kind: str
    storage_key: str
    created_at: datetime


# --- properties index (Phase 1 data, served read-only) ----------------------
class ElementProps(BaseModel):
    guid: str
    ifc_class: str
    name: str | None = None
    type_name: str | None = None
    storey: str | None = None
    psets: dict[str, Any] = Field(default_factory=dict)
    qtos: dict[str, Any] = Field(default_factory=dict)
