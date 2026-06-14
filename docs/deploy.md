# Phase 7 — Hardening & deployment

## Stack (docker-compose)
- `postgres` — primary store (Topics/Comments/Viewpoints/Attachments/AuditLog).
- `minio` — object storage for source IFC, `.frag` tiles, `props.json`, attachments.
- `api` — FastAPI (services/api/Dockerfile).
- `converter` — Node IFC→Fragments worker (services/converter/Dockerfile), run as a job.
- `web` — built static assets served by any static host / CDN.

```bash
docker compose --profile full up --build      # api + postgres + minio
# convert a model (job-style):
docker compose run --rm converter samples/model.ifc /out/model.frag
```

## Configuration (env)
| Var | Service | Purpose |
|---|---|---|
| `DATABASE_URL` | api | `postgresql+psycopg://…` (sqlite for dev) |
| `STORAGE_DIR` / S3 creds | api | attachment + props storage |
| `AEC_API_KEY` | api | when set, write endpoints require `Authorization: Bearer <key>` |
| `S3_ENDPOINT/ACCESS/SECRET` | api, converter | MinIO/S3 |

## Auth & roles
`auth.require_writer` is a minimal API-key gate (off in dev). For production, replace with
project-scoped roles **viewer / reviewer / editor / admin** backed by your IdP, and apply
the dependency to all mutating routes. Reads can stay open or move behind the same IdP.

## Audit & backups
- Every write endpoint records an `AuditLog` row (actor, action, method, path, topic, detail)
  — RFIs/punchlist are contractual records.
- Back up Postgres + object storage on a schedule. Tiles are reproducible from source IFC;
  the database and attachments are the system of record.

## Offline / jobsite
Serve web-ifc WASM and `.frag` tiles from your own origin so the viewer runs fully offline.
The build already bundles the Fragments worker locally (no unpkg).

## Licensing — confirm before shipping (see ../LICENSE-NOTES.md)
Bonsai/Blender = GPL (keep as a *separate process you use*, not statically linked).
IfcOpenShell core = LGPL. That Open libraries + Bonsai-MCP = permissive (MIT-style).
