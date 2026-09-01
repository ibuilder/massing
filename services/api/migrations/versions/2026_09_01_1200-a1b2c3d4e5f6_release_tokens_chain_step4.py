"""release_tokens: off-chain mint registry for asset-rights step 4

Records mock (or future on-chain) mints keyed by `content_hash`. Provenance binds to `asset_id`,
not `project_id`, which `import_bundle` regenerates on every `.mass` import.

Revision ID: a1b2c3d4e5f6
Revises: f4b8c2d51e93
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f4b8c2d51e93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("release_id", sa.String(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("manifest_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("provider", sa.String(), nullable=False, server_default="mock"),
        sa.Column("chain_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contract_address", sa.String(), nullable=False, server_default=""),
        sa.Column("token_id", sa.String(), nullable=False, server_default=""),
        sa.Column("tx_hash", sa.String(), nullable=True),
        sa.Column("metadata_uri", sa.String(), nullable=True),
        sa.Column("recipient", sa.String(), nullable=True),
        sa.Column("minted_by", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="minted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_release_tokens_content_hash"),
    )
    op.create_index("ix_release_tokens_asset_id", "release_tokens", ["asset_id"])
    op.create_index("ix_release_tokens_content_hash", "release_tokens", ["content_hash"])
    op.create_index("ix_release_tokens_project_id", "release_tokens", ["project_id"])
    op.create_index("ix_release_tokens_asset_created", "release_tokens", ["asset_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_release_tokens_asset_created", table_name="release_tokens")
    op.drop_index("ix_release_tokens_project_id", table_name="release_tokens")
    op.drop_index("ix_release_tokens_content_hash", table_name="release_tokens")
    op.drop_index("ix_release_tokens_asset_id", table_name="release_tokens")
    op.drop_table("release_tokens")
