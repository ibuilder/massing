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
    )
    op.create_index("ix_release_tokens_asset_id", "release_tokens", ["asset_id"])
    #: UNIQUE ON THE INDEX, NOT A SEPARATE CONSTRAINT — the model is the spec.
    #:
    #: `models.py` declares `content_hash: Mapped[str] = mapped_column(String, unique=True,
    #: index=True)`, which SQLAlchemy renders as ONE unique index named
    #: `ix_release_tokens_content_hash`. The first draft of this migration wrote a named
    #: `UniqueConstraint("content_hash", name="uq_release_tokens_content_hash")` AND a non-unique
    #: index, so the database had a constraint the model does not declare and lacked the uniqueness
    #: the model does. `alembic check` caught it as three pending operations — remove the
    #: constraint, drop the index, re-add it unique — which is CI failing on a real divergence, not
    #: a style preference.
    #:
    #: The guarantee is identical either way (Postgres enforces a unique index exactly as it
    #: enforces a unique constraint); what differs is whether the schema matches the mapping, and a
    #: schema that has drifted from its model is how the next autogenerate produces a migration
    #: nobody meant to write.
    op.create_index("ix_release_tokens_content_hash", "release_tokens", ["content_hash"],
                    unique=True)
    op.create_index("ix_release_tokens_project_id", "release_tokens", ["project_id"])
    op.create_index("ix_release_tokens_asset_created", "release_tokens", ["asset_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_release_tokens_asset_created", table_name="release_tokens")
    op.drop_index("ix_release_tokens_project_id", table_name="release_tokens")
    op.drop_index("ix_release_tokens_content_hash", table_name="release_tokens")
    op.drop_index("ix_release_tokens_asset_id", table_name="release_tokens")
    op.drop_table("release_tokens")
