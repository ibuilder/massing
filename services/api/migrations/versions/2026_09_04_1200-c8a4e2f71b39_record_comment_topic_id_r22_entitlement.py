"""record_comments.topic_id — promote an agency review comment into an RFI (R22-ENTITLEMENT ⑤)

Revision ID: c8a4e2f71b39
Revises: f4b8c2d51e93
Create Date: 2026-09-04 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8a4e2f71b39'
down_revision: str | None = 'f4b8c2d51e93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and no server default: an existing comment has not been promoted, and NULL says that
    # without inventing a state for it. The back-link is what makes promotion idempotent.
    with op.batch_alter_table('record_comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('topic_id', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('record_comments', schema=None) as batch_op:
        batch_op.drop_column('topic_id')
