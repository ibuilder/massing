"""cloud_identities (CLOUD-SSO — massing.cloud as the identity broker)

The link between a local account and a massing.cloud account: the broker's subject id, the profile
it reports (name/avatar/tier/roles), and the OAuth tokens the app uses to read that user's project
library from the Vault API on their behalf.

A table rather than columns on `users` because the link is optional, sparse, and holds live
credentials that "disconnect" must be able to delete outright — a row delete, not a six-column wipe.

Revision ID: b3c7d1e94a52
Revises: a7d4e9b23c81
Create Date: 2026-08-24 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3c7d1e94a52'
down_revision: str | None = 'a7d4e9b23c81'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'cloud_identities',
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('cloud_sub', sa.String(), nullable=False),
        sa.Column('cloud_email', sa.String(), nullable=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('cloud_tier', sa.String(), nullable=True),
        sa.Column('cloud_roles', sa.JSON(), nullable=True),
        sa.Column('providers', sa.JSON(), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.Integer(), nullable=True),
        sa.Column('linked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ),
        sa.PrimaryKeyConstraint('username'),
    )
    op.create_index(op.f('ix_cloud_identities_cloud_sub'), 'cloud_identities', ['cloud_sub'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cloud_identities_cloud_sub'), table_name='cloud_identities')
    op.drop_table('cloud_identities')
