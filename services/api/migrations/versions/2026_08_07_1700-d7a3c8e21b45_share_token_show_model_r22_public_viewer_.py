"""share_tokens.show_model (R22-PUBLIC-VIEWER)

Adds a non-null, default-FALSE `show_model` to `share_tokens`: the per-token opt-in that lets one
share link fetch the project's geometry fragment.

PARENT REVISION IS ANNOUNCED: this chains off `c9a4e13b7f60`, the merge revision that resolved the
two-head fork earlier today. Stating it here is the standing rule adopted 2026-08-07 — two PRs both
took `f4b8d2e17c93` as parent, each was individually correct and individually green, and the fork
existed only in the union. Branch protection is on but `strict: false`, so a branch is never re-tested
against a main that moved; announcing the parent is the only thing that closes it, and it costs a
sentence.

DEFAULT FALSE, AND NOT BACKFILLED. Tokens minted before this column existed were handed to people who
were promised "a curated project digest (readiness only; no record-level data)". Defaulting them to
True would retroactively widen a link somebody already sent, which is the one thing a per-token opt-in
exists to prevent. `server_default="0"` so existing rows are False rather than NULL — a NULL read by
`not getattr(row, "show_model", False)` would deny correctly, but relying on falsiness where the
schema can state the fact is how a later refactor introduces a hole.

WHAT THE FLAG GRANTS, recorded beside the schema because this is where somebody will look. It permits
`{pid}/model.frag` — converted geometry, shapes and placements. It does NOT permit `{pid}/source.ifc`,
which carries every property set, classification and GlobalId in the model. "Share the model" reads as
either; only the narrow one is served.

Revision ID: d7a3c8e21b45
Revises: c9a4e13b7f60
Create Date: 2026-08-07 17:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "d7a3c8e21b45"
down_revision = "c9a4e13b7f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("share_tokens")}
    if "show_model" not in cols:          # idempotent: a fresh create_all already has it
        op.add_column("share_tokens", sa.Column(
            "show_model", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("share_tokens")}
    if "show_model" in cols:
        op.drop_column("share_tokens", "show_model")
