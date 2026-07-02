# Operator runbook (day-2)

The one-page "start here" for running Massing in production. For the full stack layout, storage, and
auth model, see **[deploy.md](deploy.md)**; this page is the operational quick-reference.

## Is it healthy?

Two probes (both exempt from the rate limiter; `/healthz` and `/readyz` are aliases):

| Endpoint | Meaning | Use for |
|---|---|---|
| `GET /health` | **Liveness** — process is up. Cheap, no dependencies. | restart probes |
| `GET /ready` | **Readiness** — process + DB reachable (`SELECT 1` under a wall-clock timeout; `503` if the DB is down/black-holed). | load-balancer routing |

```bash
curl -fsS http://localhost:8000/health   # {"status":"ok"}
curl -isS http://localhost:8000/ready     # 200 {"status":"ready","db":"up"}  |  503 if DB down
```

`AEC_READY_TIMEOUT` (default 3 seconds) bounds the readiness DB ping so a paused DB yields a prompt
503 instead of hanging the probe.

## Configure it

The full env table is in [deploy.md](deploy.md#configuration-env). The flags you touch most:

- **Set in prod:** `AEC_AUTH_SECRET` (a strong random value — unset means forgeable dev tokens and a
  logged warning), `DATABASE_URL` (Postgres), and the `S3_*` object-storage vars.
- **Enforce roles:** `AEC_RBAC=1` (project-scoped viewer < reviewer < editor < admin).
- **Rate limiting:** `AEC_RATE_LIMIT_RPM` (global per-IP; needs `AEC_REDIS_URL` to share across
  workers). The expensive AI-review / convert endpoints are throttled per-caller regardless — tune
  with `AEC_THROTTLE_REVIEW_RPM` / `AEC_THROTTLE_CONVERT_RPM` (0 disables).
- **Memory:** `AEC_PROPS_CACHE_PROJECTS` caps the in-process property-index LRU (default 16
  projects/worker). Lower it if a worker's RSS is a concern; evicted projects reload from storage.
- **Integrations** (also settable in the in-app **Settings** UI, no restart): Anthropic key,
  SMTP, Speckle (`SPECKLE_SERVER` must be `https://` and public — see the SSRF note in deploy.md),
  Autodesk APS (paid RVT→IFC).

## Back up & restore

DB + attachments + uploaded source IFCs are the system of record; `.frag` tiles are reproducible from
source IFC. Run from the repo root with the stack up (Windows: Git Bash / WSL):

```bash
./scripts/backup.sh                          # → ./backups/aec-backup-<ts>.tgz  (pg_dump + MinIO + IFCs)
./scripts/restore.sh backups/aec-backup-<ts>.tgz
```

Automate `backup.sh` on a schedule (cron / Task Scheduler) and copy the tarball off-box. Test a
restore into a scratch stack periodically — an untested backup is a hope, not a backup.

## Common incidents

- **App shows "offline" / 503s** → check `GET /ready`. If `db:down`, the Postgres host is unreachable
  (paused, credentials, network) — the API is fine and will recover when the DB does.
- **`429 rate limit exceeded`** → a caller hit the global limiter or an endpoint throttle. Raise the
  relevant `AEC_*_RPM`, or confirm it's abuse. With multiple workers, set `AEC_REDIS_URL` so the count
  is shared (otherwise each worker counts independently).
- **"Test connection" for Speckle fails with a private-address error** → the SSRF guard blocked a
  non-public host. Use a public `https://` Speckle server, or set `SPECKLE_ALLOW_PRIVATE=1` for a
  trusted LAN server.
- **Worker RSS creeping up on a busy multi-project server** → lower `AEC_PROPS_CACHE_PROJECTS`.
- **Auth warning in logs about a public dev secret** → set `AEC_AUTH_SECRET` and restart.

## Inspect the API live

Every endpoint the app uses is documented and runnable at **`/docs`** (FastAPI Swagger UI), e.g.
`http://localhost:8000/docs`. Handy for verifying a deploy, checking a payload shape, or debugging an
integration without the web app.

---

See also: [deploy.md](deploy.md) (full stack), [authoring-modules.md](authoring-modules.md) (add a
record type without code), [production-readiness.md](production-readiness.md).
