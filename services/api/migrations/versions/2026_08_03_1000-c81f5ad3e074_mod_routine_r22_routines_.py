"""mod_routine (R22-ROUTINES persistence)

Revision ID: c81f5ad3e074
Revises: d4a17c9e2b60
Create Date: 2026-08-03 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c81f5ad3e074'
down_revision: str | None = 'd4a17c9e2b60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mod_routine',
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
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mod_routine', schema=None) as batch_op:
        batch_op.create_index('ix_mod_routine_proj_assignee', ['project_id', 'assignee'], unique=False)
        batch_op.create_index('ix_mod_routine_proj_created', ['project_id', 'created_at'], unique=False)
        batch_op.create_index('ix_mod_routine_proj_state', ['project_id', 'workflow_state'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_routine_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_routine_workflow_state'), ['workflow_state'], unique=False)

    # Postgres-only FTS GIN index — every module table gets one at runtime; a post-baseline module
    # migration must create its own (the baseline only indexes tables that exist at ITS point in the
    # chain; the CI runtime-parity check enforces this).
    if op.get_bind().dialect.name == "postgresql":
        from aec_api import modules_registry
        from aec_api.modules_search import index_ddl
        modules_registry.load_registry()
        op.execute(index_ddl("routine", modules_registry.TABLES["routine"]))


def downgrade() -> None:
    with op.batch_alter_table('mod_routine', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mod_routine_workflow_state'))
        batch_op.drop_index(batch_op.f('ix_mod_routine_project_id'))
        batch_op.drop_index('ix_mod_routine_proj_state')
        batch_op.drop_index('ix_mod_routine_proj_created')
        batch_op.drop_index('ix_mod_routine_proj_assignee')

    op.drop_table('mod_routine')
