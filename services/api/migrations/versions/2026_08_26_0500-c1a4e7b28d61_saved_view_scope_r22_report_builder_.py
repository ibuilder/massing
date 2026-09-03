"""saved_view scope — R22-REPORT-BUILDER item 4 (a view can be a project report, not only a filter)

`SavedView` was owned AND seen by one user, so a saved view could never be a firm or project report.
`scope` separates ownership from visibility: ownership still decides who may edit or delete, scope
decides who may read and run.

Existing rows become `private`, which is exactly what they were — the column is added with a
server_default so a row written by an older process (a rolling deploy) is author-only rather than
NULL, and NULL here would be a view of undefined visibility.

Revision ID: c1a4e7b28d61
Revises: b3c7d1e94a52
Create Date: 2026-08-26 05:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "c1a4e7b28d61"
down_revision = "b3c7d1e94a52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("saved_views",
                  sa.Column("scope", sa.String(), nullable=False, server_default="private"))


def downgrade() -> None:
    op.drop_column("saved_views", "scope")
