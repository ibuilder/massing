"""mod_pm_contract (R22-PM-CONTRACTS persistence)

Revision ID: a7e3b9c04d15
Revises: c81f5ad3e074
Create Date: 2026-08-06 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7e3b9c04d15'
down_revision: str | None = 'c81f5ad3e074'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mod_pm_contract',
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
    with op.batch_alter_table('mod_pm_contract', schema=None) as batch_op:
        batch_op.create_index('ix_mod_pm_contract_proj_assignee', ['project_id', 'assignee'], unique=False)
        batch_op.create_index('ix_mod_pm_contract_proj_created', ['project_id', 'created_at'], unique=False)
        batch_op.create_index('ix_mod_pm_contract_proj_state', ['project_id', 'workflow_state'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_pm_contract_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_pm_contract_workflow_state'), ['workflow_state'], unique=False)

    # Postgres-only FTS GIN index — every module table gets one at runtime; a post-baseline module
    # migration must create its own (the baseline only indexes tables that exist at ITS point in the
    # chain; the CI runtime-parity check enforces this).
    if op.get_bind().dialect.name == "postgresql":
        from aec_api import modules_registry
        from aec_api.modules_search import index_ddl
        modules_registry.load_registry()
        op.execute(index_ddl("pm_contract", modules_registry.TABLES["pm_contract"]))


def downgrade() -> None:
    with op.batch_alter_table('mod_pm_contract', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mod_pm_contract_workflow_state'))
        batch_op.drop_index(batch_op.f('ix_mod_pm_contract_project_id'))
        batch_op.drop_index('ix_mod_pm_contract_proj_state')
        batch_op.drop_index('ix_mod_pm_contract_proj_created')
        batch_op.drop_index('ix_mod_pm_contract_proj_assignee')

    op.drop_table('mod_pm_contract')
