"""BCF-shaped ORM models (guide §7). Elements are referenced by IFC GlobalId (GUID),
never transient viewer IDs, so links survive re-conversion and model updates."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
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
    # developer cost budget: line-item hard/soft/acquisition costs + contingencies (dev_budget.py)
    dev_budget: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # specialty assets: on-site energy + vertical-farm (PFAL) revenue params (specialty.py)
    dev_specialty: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # property & tax assumptions: parcel/areas/purchase/taxes (dev_property.py)
    dev_property: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # W9-3: IFC5-style non-destructive property-override layer stack {"layers": [...]} — composes over
    # the model without mutating the IFC until baked. See layers.py.
    prop_layers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # W9-5: site-logistics resources {"resources": [...]} — temporary cranes/laydown/gates with a
    # schedule window, time-phased on the 4D timeline. See logistics.py.
    site_logistics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # COST-DB: the cost-database vintage this project's estimate is pinned to (reproducibility).
    # NULL = use the latest installed vintage. See cost_db.py + docs/cost-db-import-plan.md.
    cost_dataset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # CODE-1: USPS state code (e.g. "CA") — resolves the adopted code editions for every checker
    jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topics: Mapped[list[Topic]] = relationship(back_populates="project", cascade="all, delete-orphan")


class CostDataset(Base):
    """COST-DB versioning backbone — one row per installed cost-database **vintage**. Every priced row
    (`CostItem`) hangs off a dataset, so a 2024 estimate stays reproducible after newer data lands and a
    project pins exactly one vintage. Populated offline from public benchmarks (`origin=public_local`) or,
    later, from the massing.cloud subscription API (`origin=cloud_api`). See docs/cost-db-import-plan.md."""
    __tablename__ = "cost_datasets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    vintage_year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)         # 1-4, NULL = annual
    source_set: Mapped[str] = mapped_column(String, default="public")           # public | public+1build | enterprise
    tier: Mapped[str] = mapped_column(String, default="free")
    origin: Mapped[str] = mapped_column(String, default="public_local")         # public_local | cloud_api
    release_uuid: Mapped[str | None] = mapped_column(String, nullable=True)     # cloud release id
    checksum_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (Index("ix_cost_dataset_vintage", "vintage_year", "quarter", "source_set", "origin",
                            unique=True),)


class CostItem(Base):
    """A priced line item within a cost-database vintage (MasterFormat/Uniformat keyed). Value fields are
    inlined here for the offline vintage; the plan's separate `cost_value` normalization + `location_factor`
    / `escalation_index` arrive with the location engine + cloud importer."""
    __tablename__ = "cost_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("cost_datasets.id", ondelete="CASCADE"), index=True)
    masterformat_code: Mapped[str] = mapped_column(String, nullable=False)
    uniformat_code: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    uom: Mapped[str] = mapped_column(String, nullable=False)
    ifc_class: Mapped[str | None] = mapped_column(String, nullable=True)        # link to the model takeoff
    material_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    labor_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    equipment_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_cost_item_ds_mf", "dataset_id", "masterformat_code"),)


class ProjectModel(Base):
    """An additional discipline model layered onto a project beyond its primary `source_ifc` —
    e.g. STR / MEP / ARCH IFCs — so federated (cross-discipline) clash can run across them."""
    __tablename__ = "project_models"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    discipline: Mapped[str] = mapped_column(String, default="Model")
    ifc_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    shared_with: Mapped[list | None] = mapped_column(JSON, nullable=True)  # LP read-access users
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


class User(Base):
    """An account for token auth. Identity only — per-project authorization stays in
    ProjectMember. `role` is a global hint (admin can register others / is the bootstrap)."""
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="user")   # admin | user
    # nullable so the additive schema sync can add it to existing tables; NULL = legacy-active.
    # Deactivated accounts can't log in and their existing tokens stop authenticating.
    active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)   # for digest emails
    # subscription tier seam — everyone is "free" today; gating lives in entitlements.py so the
    # paid tiers are a one-place change later. Nullable for the additive schema sync; NULL = free.
    tier: Mapped[str | None] = mapped_column(String, default="free")
    # session-revocation watermark (unix seconds): tokens issued before this are rejected. Bumped
    # on password change / admin reset / "sign out everywhere". Nullable for the additive schema
    # sync; NULL = no revocation baseline (all unexpired tokens valid). See auth.create_token + rbac.
    token_epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # TOTP multi-factor auth (all nullable for the additive schema sync; NULL = MFA off). `mfa_secret`
    # is the base32 shared secret (kept even while pending-enable); `mfa_enabled` gates the login
    # challenge; `mfa_recovery` is a JSON list of salted one-time backup-code hashes. See totp.py.
    mfa_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    mfa_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mfa_recovery: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # SCIM 2.0 provisioning: the IdP's stable opaque id for this user (RFC 7643 externalId), used to
    # correlate on rename. `provisioned` marks accounts created/managed by the IdP (SSO-only, no
    # usable password). Both nullable for the additive schema sync. See routers/scim.py.
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provisioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SavedView(Base):
    """A user's saved filter/sort/column config for a module's list (server-side, so it
    follows them across devices). Keyed by project + module + user + name."""
    __tablename__ = "saved_views"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    module: Mapped[str] = mapped_column(String, index=True)
    user: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # saved-search alerts


class EnumOption(Base):
    """E1 — a project-level custom option added to a module field's `select`/`multiselect`
    enum (e.g. a firm's own discipline/trade/type), so users extend dropdowns without editing
    JSON. Merged with the module.json options at read time. Keyed by project + module + field."""
    __tablename__ = "enum_options"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    module: Mapped[str] = mapped_column(String, index=True)
    field: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RecordAttachment(Base):
    """File attached to any GC module record (object bytes live in storage/MinIO)."""
    __tablename__ = "record_attachments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    module: Mapped[str] = mapped_column(String, index=True)
    record_id: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[int] = mapped_column(default=0)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RecordActivity(Base):
    """Per-record activity timeline shared by all GC modules (create/update/transition/link)."""
    __tablename__ = "record_activity"
    # The notifications feed filters project_id then orders by ts desc — a composite index turns that
    # index-scan + filesort into a single ordered range scan (the feed is polled frequently).
    __table_args__ = (Index("ix_record_activity_proj_ts", "project_id", "ts"),)
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

    project: Mapped[Project] = relationship(back_populates="topics")
    comments: Mapped[list[Comment]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    viewpoints: Mapped[list[Viewpoint]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    viewpoint_id: Mapped[str | None] = mapped_column(ForeignKey("viewpoints.id"), nullable=True)
    # TOPIC-LIFE threading: the parent comment's id (same topic; validated in the route — plain String,
    # not a self-FK, so SQLite batch-alter stays trivial)
    reply_to: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped[Topic] = relationship(back_populates="comments")


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

    topic: Mapped[Topic] = relationship(back_populates="viewpoints")


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

    topic: Mapped[Topic] = relationship(back_populates="attachments")


class Job(Base):
    """JOB-QUEUE — one durable background job (queued → running → done | error). Heavy operations
    (full-model COBie export, bundles, generative runs) run through this instead of the request thread,
    and a process restart loses nothing: orphaned `running` rows re-queue on worker start (handlers are
    idempotent by contract). See `jobs.py`."""
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    state: Mapped[str] = mapped_column(String, default="queued", index=True)   # queued|running|done|error
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class ErrorLog(Base):
    """Captured errors for the admin observability feed — unhandled server exceptions (source=
    'server') and reported client-side JS errors (source='web'). Distinct from AuditLog (which is a
    business/compliance trail of user writes); this is the "what broke" log an operator checks.
    Retention-capped by errorlog.prune so it can never grow unbounded on the read-only prod tree."""
    __tablename__ = "error_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="server", index=True)  # server | web
    level: Mapped[str] = mapped_column(String, nullable=False, default="error")  # error | warning
    kind: Mapped[str | None] = mapped_column(String, nullable=True)          # exception class / event name
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AppSetting(Base):
    """Admin-configured server settings (integration keys for AI / email / SSO). A value here
    overrides the matching env var. Secrets are write-only over the API. See settings_store."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Template(Base):
    """A reusable set of records for a module — e.g. a pre-pour checklist or an inspection
    template (Procore parity). Apply it to a project to instantiate one record per item. Global
    (cross-project); `items` is a list of data blobs."""
    __tablename__ = "templates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    module: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ModelVersion(Base):
    """A snapshot of a project's model at each publish — the GUID set + count, so versions can be
    diffed (added/removed elements). GUID-stable authoring makes the diff meaningful."""
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(default=1)
    element_count: Mapped[int] = mapped_column(default=0)
    guids: Mapped[list] = mapped_column(JSON, default=list)
    # MODEL-DIFF: per-element fingerprint {guid: [name, ifc_class, type, storey, pset_hash, qto_hash]} so a
    # diff can detect *modified* elements (not just added/removed). Nullable — versions before this stay
    # added/removed-only. (_ensure_columns backfills the column on existing DBs.)
    fingerprints: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DrawingMarkup(Base):
    """A pin/redline note on a 2D sheet (plan/elevation/section). Stored in the sheet's intrinsic
    coordinate space (x,y) so it pans/zooms with the drawing. Can be promoted to a Topic (RFI)."""
    __tablename__ = "drawing_markups"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    sheet_id: Mapped[str] = mapped_column(String, index=True)   # e.g. "plan:02 - Floor"
    x: Mapped[float] = mapped_column(Float, default=0.0)         # anchor (first point) — pin overlay uses this
    y: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String, nullable=True)   # set when promoted to an RFI
    # Convergence: the 2D takeoff editor persists richer markups here too. kind = pin | distance | area |
    # count | rect | text | stamp; data carries the full geometry {pts, value, unit, page, text}.
    kind: Mapped[str] = mapped_column(String, default="pin")
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RefCounter(Base):
    """Per-(project, module) monotonic counter for human refs (RFI-001, …). A dedicated counter row
    incremented under a row lock — so concurrent creates never collide, and deleting a record never
    causes a later create to reuse a ref (which a COUNT(*)-based scheme did)."""
    __tablename__ = "ref_counters"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    module: Mapped[str] = mapped_column(String, primary_key=True)
    n: Mapped[int] = mapped_column(Integer, default=0)


class Connection(Base):
    """An admin-registered data-source connection (postgres / supabase / procore). Secrets in
    `config` (DSN password, access token) are masked on read. See connectors."""
    __tablename__ = "connections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)        # postgres | supabase | procore
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {dsn} or {access_token}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SyncSchedule(Base):
    """A recurring import from a Procore connection into a project's modules (auto-sync). A
    background loop runs due schedules; `last_result` holds the most recent run summary."""
    __tablename__ = "sync_schedules"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False)
    procore_project_id: Mapped[str] = mapped_column(String, nullable=False)
    kinds: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # ["rfi","submittal","change_event"]
    interval_minutes: Mapped[int] = mapped_column(default=60)
    enabled: Mapped[bool | None] = mapped_column(Boolean, default=True)
    push: Mapped[bool | None] = mapped_column(Boolean, default=False)  # two-way: also push back to Procore
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ElementVerification(Base):
    """Field verification of a model element against design (Argyle-style spatial QA, photo-anchored).
    Keyed by IFC GlobalId so it survives re-conversion. status: pending | installed | verified |
    deviation. Drives the install-coverage dashboard and the deviation log handed to operations."""
    __tablename__ = "element_verifications"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, index=True)
    guid: Mapped[str] = mapped_column(String, index=True)
    ifc_class: Mapped[str | None] = mapped_column(String, nullable=True)
    storey: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="installed", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_key: Mapped[str | None] = mapped_column(String, nullable=True)  # storage key for a field photo
    verified_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ShareToken(Base):
    """CLIENT-PORTAL — a revocable, read-only share token that grants a non-authenticated external
    stakeholder access to a *curated* project digest (readiness only; no record-level data). The token
    string is a strong random secret and IS the credential; there is no per-token password. Revoking
    (soft) stops access immediately. See client_portal.digest for exactly what a token can read."""
    __tablename__ = "share_tokens"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    # PORTAL-TXN phase 2: OPT-IN per token — the default digest exposes NO financials; only a token
    # minted with show_payments=True carries the owner-invoice payment schedule (amounts/status).
    show_payments: Mapped[bool] = mapped_column(Boolean, default=False)


class ClientDecision(Base):
    """PORTAL-TXN — a client decision recorded through a share token: a timestamped, token-stamped
    approve/acknowledge/decline on a shared item (an estimate version, a change order, a selection…).
    NOT a payment and NOT an e-signature of record — a recorded client decision with status. Inputs are
    whitelisted + length-capped at the engine (public endpoint), and each token carries a hard decision
    cap so an unauthenticated holder can't grow the table unbounded."""
    __tablename__ = "client_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    item_type: Mapped[str] = mapped_column(String)     # whitelisted: estimate|change_order|selection|…
    item_ref: Mapped[str] = mapped_column(String)      # the shared item's label/ref (capped)
    action: Mapped[str] = mapped_column(String)        # approved | acknowledged | declined
    client_name: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
