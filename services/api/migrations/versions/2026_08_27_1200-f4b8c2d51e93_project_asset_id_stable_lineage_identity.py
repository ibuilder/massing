"""projects.asset_id: a lineage identity that survives a .mass round-trip

`bundle.import_bundle` mints a fresh `projects.id` on every import, deliberately, so a container can
be cloned into the same database or moved between machines without primary-key collisions. That is
the right behaviour for a row id and it makes `id` useless for provenance: export a project,
re-import it, and any attestation made against the old id names a project that no longer exists.

`asset_id` is the identity that survives. Export mints one lazily and writes it into the container;
import copies it across verbatim while regenerating everything else.

**Deliberately not unique, and deliberately not backfilled.**

Not unique, because cloning a container into the same database is a supported operation and produces
two rows that genuinely are the same asset. A unique constraint would make that import fail or force
it to invent a second identity, which would be a lie about the lineage.

Not backfilled, because an id invented here would differ on every database this migration ran
against, and two installations holding copies of the same project would disagree about its identity
while both looked authoritative. NULL means "no identity yet"; the next export mints one. An absent
value is honest, a fabricated one is not.

**Re-pointed from `e5f2a91c73d8` to `f7a3c82e19d4`.** Both were authored against the same parent in
parallel lanes, which briefly gave the graph two heads. `test_alembic_single_head` says to fix that
with a merge revision and *not* by re-pointing, "which lies to any database that already ran it" —
and that rule is right whenever both revisions have shipped. Here only one had: `f7a3c82e19d4` is in
committed history (v0.3.1115), while this file was still untracked and had run on nothing but a
throwaway test database. Re-pointing an unshipped revision tells no database anything false, and a
merge revision would permanently record a fork that never existed outside one working tree. If this
file had ever been committed, the merge revision would be the only correct answer.

Revision ID: f4b8c2d51e93
Revises: f7a3c82e19d4
"""
import sqlalchemy as sa
from alembic import op

revision = "f4b8c2d51e93"
down_revision = "f7a3c82e19d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("asset_id", sa.String(), nullable=True))
    op.create_index("ix_projects_asset_id", "projects", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_asset_id", table_name="projects")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("asset_id")
