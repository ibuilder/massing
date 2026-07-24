# Operations — incident runbooks & SLOs

*R19 OPS-OBS (2026-07-24). Incident playbooks beyond the DR runbook, service-level objectives over
the shipped observability surfaces, and the correlation spine. Companion: [ops-dr.md](../ops-dr.md)
(backup/restore + the quarterly drill) · [deploy.md](../deploy.md) · [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md).*

## Observability spine (what you have to work with)

- **Request IDs:** every request is stamped `X-Request-ID` (inbound honored, else generated) —
  propagated to OTel spans, Sentry events, and the error log. **Triage always starts from a
  request id**: error log → trace → the exact failing span.
- **Traces/metrics:** OTel (`otel.py`) — export to the operator's OTLP collector.
- **Errors:** Sentry (`sentry.py`) + the in-app error log (`errorlog.py`, request-id + clipped
  traceback), surfaced via the observability router.
- **Health:** the API health endpoint (DB + storage + Redis checks) — the probe for every runbook
  below; wire it to the operator's alerting.
- **Config sanity:** `scripts/validate_prod_config.py` — run after any config change.

## SLOs (self-hosted reference targets; tune per deployment)

| Surface | SLI | Target | Alert at |
|---|---|---|---|
| API availability | health-check success rate | 99.5% monthly | 2 consecutive failures |
| Interactive API latency | p95 on CRUD/read routes | < 500 ms | p95 > 1 s for 10 min |
| Conversion pipeline | job success rate (non-corrupt inputs) | 99% | any stuck job > 30 min |
| SSE/live surfaces | stream reconnect success | 99% | reconnect storm (> 10/min) |
| Error budget | 5xx rate | < 0.5% | > 1% for 10 min |
| Backups | successful nightly backup | 100% | any missed run |
| Restore drill | quarterly, verified | 4/year | missed quarter |

## Runbooks

### RB-1 — API down / health failing
1. Probe health; check container state (`docker ps`, restarts count).
2. Logs first 100 lines after last start — distinguish crash-loop (config/migration error) from
   resource kill (OOM).
3. Config error → `validate_prod_config.py`, fix, restart. Migration error → RB-3.
4. OOM → check upload/conversion activity (a huge IFC conversion is the usual spike); raise memory
   or lower `AEC_GEOM_WORKERS`; restart.
5. Verify: health green, then spot-check one project load + one module list with a fresh request id.

### RB-2 — Postgres trouble (down, corrupt, or full)
1. Down: restart the DB container; the API self-heals its pool.
2. Disk-full: clear WAL/temp or grow the volume **before** any other action.
3. Corruption/data loss: **stop writes** (stop the API), then restore per
   [ops-dr.md](../ops-dr.md) (latest manifest tarball → `restore.sh`); RPO = last backup.
4. After restore: run the Alembic upgrade to head (idempotent), health-probe, and reconcile the
   storage/DB pointer check below (RB-4 step 3).

### RB-3 — migration failure on deploy
1. The API refuses to start or `alembic upgrade` errors: read the failing revision id from the log.
2. Do NOT hand-edit schema. Roll the container back to the previous release tag (versions are
   tagged; images correspond) — the old code runs against the old schema.
3. Reproduce the chain locally against real Postgres (the `db-migrations.yml` job does exactly
   this); fix the migration in a release; redeploy.
4. Lesson on file: SQLite tests cannot catch Postgres-only failures (STABLE vs IMMUTABLE); trust
   the drift-guard workflow, and check its runs after any migration release.

### RB-4 — storage loss / object-store trouble (MinIO or volume)
1. Reads failing but DB fine: check mount/bucket health; restart MinIO.
2. Data loss: restore the storage portion of the manifest tarball (ops-dr) — Fragments tiles and
   derived artifacts can be **re-converted from source IFCs** if only derivatives are lost.
3. Reconcile: DB records pointing at missing objects → re-run conversion for affected projects;
   the model-warnings feed surfaces missing-artifact projects.

### RB-5 — bad deploy (functional regression, health green)
1. Confirm with a request id + the error log; identify the offending release from CHANGELOG.
2. Roll back to the previous version tag (schema-compatible unless a migration shipped — then
   prefer roll-forward with a fix release; migrations are not auto-reversed in prod).
3. File the regression; the fix ships as the next version-numbered release with a test.

### RB-6 — Redis loss (cache/SSE degradation)
1. Redis down does not lose durable data: scan cache and stream fan-out degrade.
2. Restart Redis; SSE clients auto-reconnect (resilience shipped v0.3.413–423); caches rewarm.
3. If flapping: run without cache (degraded latency) rather than restart-looping the API.

### RB-7 — license-bridge outage (massing.cloud unreachable)
1. Licensed features keep working per the offline-grace design (`license_cloud.py`); this is a
   WARN, not an outage.
2. Check outbound DNS/TLS from the host; the shared secret lives only in operator config — verify
   it wasn't rotated without a config update.
3. If grace expiry approaches with the bridge still down, contact the vendor path; do not patch
   around licensing.

### RB-8 — conversion job stuck
1. Job queue shows the job running > 30 min: inspect the worker log (the job id is in the record).
2. Kill the worker process; the queue's retry/dead-letter path takes over; the source IFC is
   untouched (conversions are derive-only).
3. Repeated failure on one file → pull the IFC, run the converter locally to isolate (usually a
   malformed file); attach findings to the project's model warnings.

## Correlation-ID audit (verified 2026-07-24)

Middleware stamps every request (`main.py`); OTel spans carry it (`otel.set_request_id`); the error
log persists it; responses echo it. Gap: background jobs log the **job id** but do not carry the
*originating* request id into worker spans — acceptable (jobs are durable records) and noted here
rather than patched speculatively.

## Postmortems

Any SLO-breaching incident gets a short postmortem in `docs/ops/` (what happened · timeline ·
root cause · what detected it vs. what should have · actions with owners). The FTS drift-guard
incident (CHANGELOG v0.3.628–632) is the format reference.
