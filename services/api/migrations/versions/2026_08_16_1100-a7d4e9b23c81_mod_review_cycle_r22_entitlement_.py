"""mod_review_cycle (R22-ENTITLEMENT — the review round, so the argument has a number)

`permit` has a single `under_review` state, so a third review round is indistinguishable from a
first and the only recoverable duration is `applied_date -> issued_date`: one number for a process
that is a back-and-forth. That number cannot answer the question a seven-month permit actually
raises, which is never "how long" but *whose court did it sit in*. This is where the rounds live so
`approval_cycles` can split agency time from applicant time.

Revision ID: a7d4e9b23c81
Revises: e5f2a91c6b74
Create Date: 2026-08-16 11:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7d4e9b23c81'
down_revision: str | None = 'e5f2a91c6b74'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mod_review_cycle',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('project_id', sa.String(), nullable=True),
    sa.Column('ref', sa.String(), nullable=True),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('workflow_state', sa.String(), nullable=True),
    sa.Column('party_owner', sa.String(), nullable=True),
    sa.Column('assignee', sa.String(), nullable=True),
    sa.Column('created_by', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('modified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('anchor', sa.JSON(), nullable=True),
    sa.Column('element_guids', sa.JSON(), nullable=True),
    sa.Column('links', sa.JSON(), nullable=True),
    sa.Column('data', sa.JSON(), nullable=True),
    # Every mod_* table has carried this since R41-SCHEMA-STALE (e2c6f31b9a44); a template copied
    # from before August omits it and `alembic check` reports the drift.
    sa.Column('schema_version', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mod_review_cycle', schema=None) as batch_op:
        batch_op.create_index('ix_mod_review_cycle_proj_assignee', ['project_id', 'assignee'], unique=False)
        batch_op.create_index('ix_mod_review_cycle_proj_created', ['project_id', 'created_at'], unique=False)
        batch_op.create_index('ix_mod_review_cycle_proj_state', ['project_id', 'workflow_state'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_review_cycle_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_review_cycle_workflow_state'), ['workflow_state'], unique=False)

    # Postgres-only FTS GIN index. The baseline only indexes tables that existed at ITS point in the
    # chain, so a post-baseline module migration must create its own. Dropping this passes every
    # local SQLite test and fails the Postgres runtime-parity job.
    if op.get_bind().dialect.name == "postgresql":
        from aec_api import modules_registry
        from aec_api.modules_search import index_ddl
        modules_registry.load_registry()
        op.execute(index_ddl("review_cycle", modules_registry.TABLES["review_cycle"]))


def downgrade() -> None:
    with op.batch_alter_table('mod_review_cycle', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mod_review_cycle_workflow_state'))
        batch_op.drop_index(batch_op.f('ix_mod_review_cycle_project_id'))
        batch_op.drop_index('ix_mod_review_cycle_proj_state')
        batch_op.drop_index('ix_mod_review_cycle_proj_created')
        batch_op.drop_index('ix_mod_review_cycle_proj_assignee')

    op.drop_table('mod_review_cycle')
