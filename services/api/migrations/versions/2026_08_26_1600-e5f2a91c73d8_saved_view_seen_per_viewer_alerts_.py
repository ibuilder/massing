"""saved_view_seen: per-viewer alerts on shared saved views

R22-REPORT-BUILDER item 4 shipped `SavedView.scope` so a view could be shared, and deliberately
stopped short of alerting anyone but the author. The reason is recorded on the model:
`saved_views.last_seen_at` was ONE column on ONE row, so a project-scoped view in a second person's
feed would have computed *their* "new since" from **the author's** last visit — the same confidently
wrong number the filter miscount produced one layer down.

This adds the per-viewer timestamp that item named, and **moves the existing data into it rather
than leaving the column behind**. Every non-null `last_seen_at` becomes a row for the view's own
owner, so nobody's feed resets: an author who last looked on Tuesday still counts from Tuesday.

The old column is then DROPPED. Keeping it would leave a populated, authoritative-looking column
that nothing reads, which is how a later change "fixes" something by reading it again and
reintroduces exactly the defect this table exists to prevent.

Revision ID: e5f2a91c73d8
Revises: c1a4e7b28d61
"""
import sqlalchemy as sa
from alembic import op

revision = "e5f2a91c73d8"
down_revision = "c1a4e7b28d61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_view_seen",
        sa.Column("id", sa.String(), primary_key=True),
        # CASCADE so a deleted view takes its viewers' reading times with it. Postgres enforces this;
        # SQLite does not without `PRAGMA foreign_keys=ON`, which this app never issues — so
        # `delete_view` also removes them explicitly. Both, because either alone is true on only one
        # of the two databases this project runs.
        sa.Column("view_id", sa.String(),
                  sa.ForeignKey("saved_views.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        # One row per (view, viewer). Two would make "when did I last look at this" ambiguous and the
        # feed would answer with whichever the query happened to return first.
        sa.UniqueConstraint("view_id", "user", name="uq_saved_view_seen_view_user"),
    )
    op.create_index("ix_saved_view_seen_view_id", "saved_view_seen", ["view_id"])
    op.create_index("ix_saved_view_seen_user", "saved_view_seen", ["user"])

    # Carry every owner's existing visit across. `hex(randomblob(16))` / `md5(random()::text)` give
    # the row an id without needing a Python round-trip over the table; the value is opaque and never
    # parsed. Done as one statement per dialect rather than one generic one, because SQLite and
    # Postgres do not share a random-id expression.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("""
            INSERT INTO saved_view_seen (id, view_id, "user", last_seen_at)
            SELECT md5(random()::text || id), id, "user", last_seen_at
            FROM saved_views WHERE last_seen_at IS NOT NULL
        """)
    else:
        op.execute("""
            INSERT INTO saved_view_seen (id, view_id, "user", last_seen_at)
            SELECT lower(hex(randomblob(16))), id, "user", last_seen_at
            FROM saved_views WHERE last_seen_at IS NOT NULL
        """)

    with op.batch_alter_table("saved_views") as batch_op:
        batch_op.drop_column("last_seen_at")


def downgrade() -> None:
    # Re-add the column and put each view's OWNER row back into it. A viewer's timestamp has nowhere
    # to go in the old shape — that is the limitation the column had, and the downgrade cannot invent
    # room for it. Owners are restored exactly; other viewers' visits are dropped, which returns the
    # feed to precisely the behaviour it had before this revision.
    with op.batch_alter_table("saved_views") as batch_op:
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        UPDATE saved_views SET last_seen_at = (
            SELECT s.last_seen_at FROM saved_view_seen s
            WHERE s.view_id = saved_views.id AND s."user" = saved_views."user"
        )
    """)
    op.drop_index("ix_saved_view_seen_user", table_name="saved_view_seen")
    op.drop_index("ix_saved_view_seen_view_id", table_name="saved_view_seen")
    op.drop_table("saved_view_seen")
