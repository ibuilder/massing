"""mod_fault_finding (R41-FDD-INGEST persistence)

Revision ID: b4c1f7d92e08
Revises: f4b8d2e17c93
Create Date: 2026-08-07 07:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4c1f7d92e08'
down_revision: str | None = 'f4b8d2e17c93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mod_fault_finding',
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
    # R41-SCHEMA-STALE added this to every mod_* table (revision e2c6f31b9a44). A register
    # created AFTER that revision must declare it at create_table, or  reports
    # model-vs-migration drift - which is how this was caught rather than shipping skewed.
    sa.Column('schema_version', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mod_fault_finding', schema=None) as batch_op:
        batch_op.create_index('ix_mod_fault_finding_proj_assignee', ['project_id', 'assignee'], unique=False)
        batch_op.create_index('ix_mod_fault_finding_proj_created', ['project_id', 'created_at'], unique=False)
        batch_op.create_index('ix_mod_fault_finding_proj_state', ['project_id', 'workflow_state'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_fault_finding_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_fault_finding_workflow_state'), ['workflow_state'], unique=False)

    # Postgres-only FTS GIN index — every module table gets one at runtime; a post-baseline module
    # migration must create its own (the baseline only indexes tables that exist at ITS point in the
    # chain, so skipping this silently loses full-text search on Postgres while passing every SQLite
    # test — which is exactly what makes it look like boilerplate).
    if op.get_bind().dialect.name == "postgresql":
        from aec_api import modules_registry
        from aec_api.modules_search import index_ddl
        modules_registry.load_registry()
        op.execute(index_ddl("fault_finding", modules_registry.TABLES["fault_finding"]))


def downgrade() -> None:
    with op.batch_alter_table('mod_fault_finding', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mod_fault_finding_workflow_state'))
        batch_op.drop_index(batch_op.f('ix_mod_fault_finding_project_id'))
        batch_op.drop_index('ix_mod_fault_finding_proj_state')
        batch_op.drop_index('ix_mod_fault_finding_proj_created')
        batch_op.drop_index('ix_mod_fault_finding_proj_assignee')

    op.drop_table('mod_fault_finding')
