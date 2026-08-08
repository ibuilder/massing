"""jobs.heartbeat_at (JOB-WORKER-SCALE)

Adds a nullable `heartbeat_at` to `jobs` so orphan recovery can tell a crashed job from one a live
sibling worker is executing.

WHY IT IS NEEDED. `start_worker()` re-queued every `running` row in the database. That was correct
while exactly one process ever ran the queue, and became wrong when `docker compose --scale worker=N`
was documented in the compose file: a worker booting re-queued the jobs its siblings were mid-flight
on, and each then ran in two processes at once — for a mutating kind, two writers in one project.
The compare-and-swap in `_claim_next` cannot see this; it arbitrates who takes a row that is already
`queued`, and a row reset underneath a live worker is exactly what it hands out.

NULLABLE, AND NOT BACKFILLED. A row claimed by a build older than this column has no heartbeat, and
inventing one would assert a liveness that was never observed. `recover_orphans` treats NULL as stale
only when `started_at` is also older than the stale window, which recovers legacy rows without
catching a row a sibling claimed moments ago — a new claim stamps both fields in one statement.

Revision ID: f4b8d2e17c93
Revises: e2c6f31b9a44
Create Date: 2026-08-07 06:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "f4b8d2e17c93"
down_revision = "e2c6f31b9a44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("jobs")}
    if "heartbeat_at" not in cols:          # idempotent: a fresh create_all already has it
        op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("jobs")}
    if "heartbeat_at" in cols:
        op.drop_column("jobs", "heartbeat_at")
