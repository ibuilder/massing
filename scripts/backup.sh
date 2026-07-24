#!/usr/bin/env bash
# Back up the AEC BIM stack: Postgres (logical dump) + MinIO objects + uploaded source IFCs.
# Produces one timestamped tarball under ./backups. Run from the repo root with the stack up.
#
#   ./scripts/backup.sh [output_dir]
#
# Windows: run from Git Bash or WSL. Restore with scripts/restore.sh.
set -euo pipefail

OUT_DIR="${1:-./backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PGUSER="${POSTGRES_USER:-bim}"
PGDB="${POSTGRES_DB:-bim}"
DC="docker compose"

echo "==> Postgres dump ($PGDB)"
$DC exec -T postgres pg_dump -U "$PGUSER" -d "$PGDB" --clean --if-exists | gzip > "$STAGE/db.sql.gz"

# MinIO objects + source IFCs straight from their volumes (no client/credentials needed).
# --volumes-from mounts the service container's volumes at their in-container paths.
MINIO_CID="$($DC ps -q minio)"
API_CID="$($DC ps -q api)"
[ -n "$MINIO_CID" ] || { echo "minio container not running" >&2; exit 1; }

echo "==> MinIO objects"
docker run --rm --volumes-from "$MINIO_CID" -v "$STAGE":/bak alpine \
  tar czf /bak/minio-data.tgz -C /data .

if [ -n "$API_CID" ]; then
  echo "==> Uploaded source IFCs"
  docker run --rm --volumes-from "$API_CID" -v "$STAGE":/bak alpine \
    sh -c 'tar czf /bak/ifc-data.tgz -C /app/ifc . 2>/dev/null || echo "(no /app/ifc)"'
fi

cat > "$STAGE/MANIFEST.txt" <<EOF
AEC BIM backup
created:   $TS
postgres:  db=$PGDB user=$PGUSER (db.sql.gz, --clean --if-exists)
minio:     minio-data.tgz (all buckets/objects)
ifc:       ifc-data.tgz (uploaded source IFCs, if present)
restore:   scripts/restore.sh <this-file>
EOF

mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/aec-backup-$TS.tgz"
tar czf "$ARCHIVE" -C "$STAGE" .
echo "==> Wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# Retention (OPS-DR): keep the newest $BACKUP_KEEP archives (default 14), prune the rest.
# Timestamped names sort chronologically, so `ls -1 | sort` oldest-first is safe.
KEEP="${BACKUP_KEEP:-14}"
PRUNE="$(ls -1 "$OUT_DIR"/aec-backup-*.tgz 2>/dev/null | sort | head -n -"$KEEP" || true)"
if [ -n "$PRUNE" ]; then
  echo "==> Retention: pruning $(echo "$PRUNE" | wc -l) archive(s) beyond the newest $KEEP"
  echo "$PRUNE" | xargs rm -f
fi
