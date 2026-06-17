#!/usr/bin/env bash
# Restore the AEC BIM stack from a backup made by scripts/backup.sh.
# DESTRUCTIVE: overwrites the current database, MinIO objects, and uploaded IFCs.
#
#   ./scripts/restore.sh ./backups/aec-backup-<ts>.tgz
#
# Stops the app while restoring so nothing writes mid-restore, then brings it back up.
set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <backup.tgz>}"
[ -f "$ARCHIVE" ] || { echo "no such file: $ARCHIVE" >&2; exit 1; }

PGUSER="${POSTGRES_USER:-bim}"
PGDB="${POSTGRES_DB:-bim}"
DC="docker compose"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
tar xzf "$ARCHIVE" -C "$STAGE"
echo "==> Restoring from:"; cat "$STAGE/MANIFEST.txt"

printf '\nThis OVERWRITES the running stack. Type YES to continue: '
read -r confirm
[ "$confirm" = "YES" ] || { echo "aborted"; exit 1; }

echo "==> Stopping app (api, web) to quiesce writes"
$DC stop api web || true

echo "==> Restoring Postgres ($PGDB)"
gunzip -c "$STAGE/db.sql.gz" | $DC exec -T postgres psql -U "$PGUSER" -d "$PGDB" -q

MINIO_CID="$($DC ps -q minio)"
if [ -n "$MINIO_CID" ] && [ -f "$STAGE/minio-data.tgz" ]; then
  echo "==> Restoring MinIO objects (replace)"
  docker run --rm --volumes-from "$MINIO_CID" -v "$STAGE":/bak alpine \
    sh -c 'rm -rf /data/* && tar xzf /bak/minio-data.tgz -C /data'
  $DC restart minio
fi

API_CID="$($DC ps -q api)"
if [ -n "$API_CID" ] && [ -f "$STAGE/ifc-data.tgz" ]; then
  echo "==> Restoring uploaded source IFCs (replace)"
  docker run --rm --volumes-from "$API_CID" -v "$STAGE":/bak alpine \
    sh -c 'rm -rf /app/ifc/* && tar xzf /bak/ifc-data.tgz -C /app/ifc'
fi

echo "==> Bringing the app back up"
$DC start api web
echo "==> Restore complete. Verify: curl -s localhost:8000/health"
