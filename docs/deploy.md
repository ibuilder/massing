# Phase 7 — Hardening & deployment

## Stack (docker-compose)
- `postgres` — primary store (projects/members/topics/comments/viewpoints/attachments/audit).
- `minio` — object storage (source IFC, `.frag` tiles, `props.json`, attachments).
- `api` — FastAPI; image bundles `services/data` so exports/clash/validate/drawings work.
- `web` — Vite build served by nginx (COOP/COEP headers for web-ifc threading).
- `converter` — Node IFC→Fragments, run as a job (`docker compose run`).

```bash
# core stack (api + web + postgres + minio)
docker compose --profile full up --build
#   web → http://localhost:8080    api → http://localhost:8000    minio console → :9001

# convert a model (drop it in ./data first)
docker compose --profile tools run --rm converter /data/model.ifc /data/model.frag

# enforce project roles
AEC_RBAC=1 docker compose --profile full up --build

# smoke test a running stack
API=http://localhost:8000 bash scripts/smoke-stack.sh samples/school_str.ifc
```

## Configuration (env)
| Var | Service | Purpose |
|---|---|---|
| `DATABASE_URL` | api | `postgresql+psycopg://…` (sqlite if unset, dev) |
| `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` | api | MinIO/S3 object storage; unset → local `STORAGE_DIR` |
| `AEC_RBAC` | api | `1` enforces project-scoped roles |
| `AEC_API_KEY` | api | bearer treated as admin (service-to-service) |

## Auth & roles (RBAC)
Project-scoped roles, least→most: **viewer < reviewer < editor < admin** (`rbac.py`).
- viewer: read models/properties/issues/drawings/exports
- reviewer: + create/comment topics & viewpoints, attachments (RFIs, markup)
- editor: + author IFC (`/edit`, `/publish`), clash-with-topics, BCF import
- admin: + project settings, manage members
The project creator becomes admin. Caller identified by `X-User` (swap for your IdP/JWT in
prod). Off by default (`AEC_RBAC` unset) so local dev stays open. Verified: `test_rbac.py`.

## Object storage & streaming
`storage.py` has Local and S3 (boto3) backends behind one interface incl. byte-range reads.
`.frag` tiles and attachments are served with **HTTP range requests** (`serving.py`): `206
Partial Content`, `Accept-Ranges`, `Content-Range`, immutable cache headers — so the viewer/
CDN stream large models. Verified: `test_serving.py` (200 full / 206 ranged / 416).

> Note: `/publish` reconvert spawns the Node converter; in the container that step is
> best-effort (reindex always runs). For prod, run conversion via the `converter` service
> and write the `.frag` to MinIO under `<project_id>/model.frag`.

## Audit & backups
Every write records an `AuditLog` row (actor, action, method, path, topic, detail) — RFIs/
punchlist are contractual records. Back up Postgres + the object store on a schedule; `.frag`
tiles are reproducible from source IFC, the DB + attachments are the system of record.

## Offline / jobsite
web-ifc WASM + the Fragments worker are bundled into the web image; tiles serve from your own
MinIO. No external CDN — the viewer runs fully offline.

## Licensing — see ../LICENSE-NOTES.md
Bonsai/Blender GPL (separate process), IfcOpenShell LGPL, That Open MIT-style.
