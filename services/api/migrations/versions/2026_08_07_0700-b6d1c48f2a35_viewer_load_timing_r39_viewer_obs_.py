"""viewer_load_timing (R39-VIEWER-OBS)

One row per viewer model-load, so "the viewer loads slowly" stops arriving as a feeling and becomes
p50/p95 by model-size band.

WHY ITS OWN TABLE, rather than a level on `error_log`. `errorlog.prune` trims to the newest
`max_rows` GLOBALLY, not per source. Timings are emitted on every load while errors are rare, so
sharing that table would let a busy afternoon in the viewer silently evict real errors out of the
operator's feed — the observability channel degrading the thing it shares a store with. `RecordActivity`
was the other candidate and is FK'd to module records, so it is the wrong shape entirely.

WHY `outcome` IS THE COLUMN THAT EARNS THE TABLE. A load can arrive without being SEEN: in the
CANVAS-RESIZE bug documented in `apps/web/src/viewer/world.ts`, the .frag fetch returned 200, the
worker parsed, the meshes existed and were visible — and the canvas was 0x493, so nothing appeared.
That was "recorded as an environment quirk and repeated as a verification limitation for weeks"
because no instrument could tell *arrived* from *seen*. `invisible` is that case. `stalled` is a load
that never produced a frame at all, recorded on a timer, because an instrument that only reports
successes is survivorship-biased against precisely the loads worth investigating.

NO FK ON project_id, deliberately, matching `error_log`. A diagnostic row about a load must survive
the project being deleted — losing the evidence when the subject goes away is how a slow-load report
becomes unreproducible. Nullable for the same reason.

Revision ID: b6d1c48f2a35
Revises: f4b8d2e17c93
Create Date: 2026-08-07 07:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "b6d1c48f2a35"
down_revision = "f4b8d2e17c93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "viewer_load_timing",
        sa.Column("id", sa.String(), primary_key=True),
        # NOT NULL to match `Mapped[datetime]` on the model — non-Optional there means NOT NULL, and
        # `alembic check` on Postgres compares the two. A row with no timestamp is useless anyway:
        # every read of this table filters by time. The Python-side `default=_now` fills it.
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False, server_default="ok"),
        sa.Column("bucket", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("fetch_ms", sa.Integer(), nullable=True),
        sa.Column("parse_ms", sa.Integer(), nullable=True),
        sa.Column("first_frame_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.Column("canvas_w", sa.Integer(), nullable=True),
        sa.Column("canvas_h", sa.Integer(), nullable=True),
    )
    # The question this table exists to answer is always "p95 for THIS band, lately", so ts/bucket/
    # outcome are the filters every read applies. project_id is indexed for the per-project view.
    op.create_index("ix_viewer_load_timing_ts", "viewer_load_timing", ["ts"])
    op.create_index("ix_viewer_load_timing_bucket", "viewer_load_timing", ["bucket"])
    op.create_index("ix_viewer_load_timing_outcome", "viewer_load_timing", ["outcome"])
    op.create_index("ix_viewer_load_timing_project_id", "viewer_load_timing", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_viewer_load_timing_project_id", table_name="viewer_load_timing")
    op.drop_index("ix_viewer_load_timing_outcome", table_name="viewer_load_timing")
    op.drop_index("ix_viewer_load_timing_bucket", table_name="viewer_load_timing")
    op.drop_index("ix_viewer_load_timing_ts", table_name="viewer_load_timing")
    op.drop_table("viewer_load_timing")
