# API service (Phase 4)

FastAPI backend for work artifacts attached to model data, modeled on the buildingSMART
**BCF** standard so issues round-trip with Solibri / ACC / BIMcollab.

Core resources:
- `topics` (type = rfi | punch | clash | info) with status/assignee/due_date/priority/labels
- `comments`, `viewpoints` (camera + clipping + visibility + components[guid]), `attachments`
- `bcf/export` → standards-compliant `.bcfzip`; `bcf/import`

Rules: reference elements by IFC **GlobalId (GUID)**, never transient viewer IDs. A pin is a
topic with a 3D anchor + element GUID(s). Audit-log all writes (RFIs/punchlist are
contractual records).

Stack: FastAPI + SQLAlchemy + Alembic + Postgres (sqlite for dev) + pydantic v2.
See root guide §7.
