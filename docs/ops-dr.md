# Operations: backup, restore & disaster recovery (OPS-DR)

The procurement-checklist answer: what is backed up, how it is restored, how the restore is *proven*,
and what the retention posture is. Everything here uses the stock stack (`docker-compose.prod.yml`) and
the two scripts in `scripts/` — no external backup service is required.

## What must survive

| Data | Where it lives | Captured by |
| --- | --- | --- |
| Project/module/topic records, users, tokens, audit log | Postgres (`postgres` service volume) | `db.sql.gz` (logical dump, `--clean --if-exists`) |
| Fragments, converted tiles, attachments, documents | MinIO (`minio` service volume) | `minio-data.tgz` (all buckets) |
| Uploaded source IFCs | the API container's `/app/ifc` volume | `ifc-data.tgz` |
| Operator config (secrets, `.env`, licence cloud shared secret) | **outside the repo/backups by design** | your secret manager — back it up there, never in these archives |

The application itself is stateless — any tagged image + a restored backup is a working stack.

## Taking a backup

```bash
./scripts/backup.sh                 # writes ./backups/aec-backup-<UTC ts>.tgz
BACKUP_KEEP=30 ./scripts/backup.sh /mnt/backups   # custom destination + retention depth
```

- One self-describing tarball (contains `MANIFEST.txt`) per run; safe while the stack is serving
  (pg_dump is transactional; object stores are copied whole).
- **Retention**: the script prunes archives beyond the newest `BACKUP_KEEP` (default 14) in the output
  directory. Pair a daily cron/scheduled task with the default and you hold two weeks of dailies.
- Ship the archive off-host (rsync/rclone to object storage) — a backup on the same disk as the
  database is a copy, not a backup.

## Restoring

```bash
./scripts/restore.sh ./backups/aec-backup-<ts>.tgz
```

Destructive and interactive (`YES` confirmation): stops `api`/`web`, restores the DB dump, replaces
MinIO objects and uploaded IFCs, restarts. Verify with `curl -s localhost:8000/health`, then open a
project and confirm the model loads and a module list renders.

## RPO / RTO

- **RPO** = your backup cadence. A daily cron gives ≤24 h; run `backup.sh` before every risky
  operation (migration, bulk import) to shrink the window to zero for planned work.
- **RTO** ≈ image pull + restore time. The dump restore is minutes; MinIO restore scales with object
  volume. On a fresh host: `docker compose -f docker-compose.prod.yml up -d` → `restore.sh` → done.

## The quarterly restore drill (a backup is a rumor until restored)

1. On a scratch host (or a second compose project via `-p drill`), bring up a fresh stack.
2. Run `restore.sh` with the latest production archive.
3. Prove it: `/health` is green → log in → open a project → the viewer loads the model → create and
   delete a test record → `GET /projects/{pid}/modules/rfi` returns the expected rows.
4. Record the drill date + archive timestamp + time-to-restore in your ops log. A drill that was not
   recorded did not happen.

## Retention & deletion posture

- **Backups**: `BACKUP_KEEP` bounds how long deleted data survives in archives. If a record must be
  purged for a data-subject request, purge it in the app, then let retention age the old archives out
  (or rebuild archives if contractually required sooner).
- **In-app**: the audit log and error log are append-only tables; project deletion removes the
  project's records, share tokens (and with them public access), and storage objects. Share tokens are
  soft-revocable instantly (`DELETE /projects/{pid}/share-tokens/{token}`).
- **Secrets**: never in the repo, never in these archives ([SECURITY.md](../SECURITY.md)); rotate via
  the operator config.

## Failure playbook (short form)

| Scenario | Move |
| --- | --- |
| Bad deploy / broken migration | roll the image tag back; if data was mutated, `restore.sh` the pre-deploy archive |
| Postgres volume lost | fresh volume → `restore.sh` (DB restores from the dump) |
| MinIO volume lost | `restore.sh` restores objects; source IFCs re-convert on demand |
| Whole host lost | new host → compose up → `restore.sh` from off-host archive |
| Suspected data corruption | stop `api`, back up the *corrupt* state first (forensics), then restore last-known-good |
