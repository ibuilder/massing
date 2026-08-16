"""mod_answer_record (R22-PROVENANCE — the ANSWERS leg gets somewhere to live)

`provenance_report` reported the answers leg as `not_captured` — not "no data", but *this system has
nowhere to put it*. `cited_answer` was an in-flight contract consumed by decision_gate /
persona_answer / rfi_qa and discarded with the response, so a project-scoped verdict could never read
`admissible` no matter how well-cited the deal was. This is the store.

Revision ID: e5f2a91c6b74
Revises: d7a3c8e21b45
Create Date: 2026-08-16 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f2a91c6b74'
down_revision: str | None = 'd7a3c8e21b45'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('mod_answer_record',
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
    # R41-SCHEMA-STALE added this to every mod_* table in e2c6f31b9a44. A migration copied
    # from a pre-August template silently omits it and `alembic check` catches the drift --
    # the neighbour you copy carries its own age.
    sa.Column('schema_version', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mod_answer_record', schema=None) as batch_op:
        batch_op.create_index('ix_mod_answer_record_proj_assignee', ['project_id', 'assignee'], unique=False)
        batch_op.create_index('ix_mod_answer_record_proj_created', ['project_id', 'created_at'], unique=False)
        batch_op.create_index('ix_mod_answer_record_proj_state', ['project_id', 'workflow_state'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_answer_record_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mod_answer_record_workflow_state'), ['workflow_state'], unique=False)

    # Postgres-only FTS GIN index — every module table gets one at runtime; a post-baseline module
    # migration must create its own (the baseline only indexes tables that exist at ITS point in the
    # chain; the CI runtime-parity check enforces this). This is the part that looks like boilerplate
    # and is not: dropping it passes every local SQLite test and fails the Postgres parity job.
    if op.get_bind().dialect.name == "postgresql":
        from aec_api import modules_registry
        from aec_api.modules_search import index_ddl
        modules_registry.load_registry()
        op.execute(index_ddl("answer_record", modules_registry.TABLES["answer_record"]))


def downgrade() -> None:
    with op.batch_alter_table('mod_answer_record', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mod_answer_record_workflow_state'))
        batch_op.drop_index(batch_op.f('ix_mod_answer_record_project_id'))
        batch_op.drop_index('ix_mod_answer_record_proj_state')
        batch_op.drop_index('ix_mod_answer_record_proj_created')
        batch_op.drop_index('ix_mod_answer_record_proj_assignee')

    op.drop_table('mod_answer_record')
