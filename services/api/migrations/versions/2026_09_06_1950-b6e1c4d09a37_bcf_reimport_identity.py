"""BCF re-import identity: comments.guid, unique (project_id, guid) on topics and (topic_id, guid) on comments

`bcf_io.import_bcfzip` blind-inserted `Topic(guid=te.get("Guid"))` with no lookup at all, and threw
each `<Comment Guid="...">` away entirely. So re-importing an updated `.bcfzip` — the ordinary weekly
loop with a coordination tool — did not update anything, it made a second copy of every topic and a
second copy of every comment. Export then emitted two `<Topic>` elements carrying one GUID, which is
not valid BCF, so the duplication escaped this deployment and into whatever tool opened the file next.

Three changes, and the third is the one that makes the first two hold under concurrency:

  1. `comments.guid` — a comment's identity in the FILE, separate from our primary key. Backfilled
     `guid := id`, which is exactly what the exporter has been writing as `<Comment Guid>` all along,
     so every already-exported .bcfzip still matches its comments on re-import. Without the backfill
     the fix would only work for files exported after this migration.
  2. `uq_comments_topic_guid` on (topic_id, guid).
  3. `uq_topics_project_guid` on (project_id, guid).

## The dedupe RE-PARENTS, it does not delete

The sibling migrations this week (`d5f2a81c6b47`, `e7b3f4a9c218`, `a3c7d9e4f218`) drop the losing
rows, because an element verification or an enum option carries nothing. A topic carries comments,
viewpoints and attachments by foreign key, and audit entries, record comments and drawing markups by
a plain `topic_id` string with no FK behind it. Deleting a duplicate topic would take a real
conversation with it, and would leave those three soft references pointing at nothing.

So every child of a losing topic is moved to the survivor first, across all six tables, and only then
is the empty topic removed. The survivor is the EARLIEST row: a re-import's copy is the later one, so
the first import — the one whose id every other record already points at — is the one that stays.

Comments are deduped on (topic_id, guid) only AFTER the re-parenting, because re-parenting is what
brings a duplicate topic's copies of the same comment onto one topic in the first place. There the
earliest wins too, and `record_comments`/`audit_log` are not re-pointed at comment ids (neither
references one), so a plain delete is honest.

Revision ID: b6e1c4d09a37
Revises: a3c7d9e4f218
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b6e1c4d09a37"
down_revision: str | None = "a3c7d9e4f218"
branch_labels = None
depends_on = None

#: Everything that points at a topic. The first three are real foreign keys; the last three are
#: plain `topic_id` strings with no constraint behind them, which is exactly why they have to be
#: listed by hand — no schema reflection would find them, and a duplicate topic deleted without
#: them leaves three tables referring to a row that no longer exists.
_TOPIC_CHILDREN = ("comments", "viewpoints", "attachments",
                   "record_comments", "audit_log", "drawing_markups")


def _table_exists(conn, name: str) -> bool:
    return sa.inspect(conn).has_table(name)


def upgrade() -> None:
    conn = op.get_bind()
    pg = conn.dialect.name == "postgresql"

    with op.batch_alter_table("comments") as b:
        b.add_column(sa.Column("guid", sa.String(), nullable=True))
    # `guid := id` rather than a fresh uuid: the exporter has been writing `<Comment Guid="{id}">`
    # since BCF export shipped, so this is the value that already exists out in people's files.
    conn.execute(sa.text("UPDATE comments SET guid = id WHERE guid IS NULL"))
    # NOT NULL only after the backfill — the column is added nullable because the rows have no value
    # until the UPDATE above runs. The model declares it non-optional, so leaving it nullable is not
    # cosmetic: `alembic check` compares the two and reds the build, which is how this was caught.
    with op.batch_alter_table("comments") as b:
        b.alter_column("guid", existing_type=sa.String(), nullable=False)
    op.create_index("ix_comments_guid", "comments", ["guid"])

    # Writers held off across the dedupe and both index builds, for the reason d5f2a81c6b47 records:
    # a live API can insert the very duplicate just removed, and the index build then fails and
    # aborts the deploy. SHARE is what CREATE INDEX takes anyway. SQLite has no LOCK TABLE and
    # serialises writers for the whole transaction regardless.
    if pg:
        for t in ("topics", *(_TOPIC_CHILDREN)):
            if _table_exists(conn, t):
                conn.execute(sa.text(f"LOCK TABLE {t} IN SHARE MODE"))

    # ---- topics: re-parent the losers' children, then drop the empty rows --------------------
    dupes = conn.execute(sa.text(
        "SELECT project_id, guid FROM topics WHERE guid IS NOT NULL "
        "GROUP BY project_id, guid HAVING COUNT(*) > 1")).all()
    for pid, guid in dupes:
        rows = conn.execute(sa.text(
            "SELECT id FROM topics WHERE project_id = :p AND guid = :g "
            "ORDER BY created_at ASC, id ASC"), {"p": pid, "g": guid}).mappings().all()
        keep, losers = rows[0]["id"], [r["id"] for r in rows[1:]]
        if not losers:
            continue
        for table in _TOPIC_CHILDREN:
            if not _table_exists(conn, table):
                continue
            conn.execute(sa.text(f"UPDATE {table} SET topic_id = :keep WHERE topic_id IN :ids")
                         .bindparams(sa.bindparam("ids", value=losers, expanding=True)),
                         {"keep": keep, "ids": losers})
        conn.execute(sa.text("DELETE FROM topics WHERE id IN :ids").bindparams(
            sa.bindparam("ids", value=losers, expanding=True)))

    # ---- comments: dedupe AFTER re-parenting, which is what created the collisions -----------
    cdupes = conn.execute(sa.text(
        "SELECT topic_id, guid FROM comments WHERE guid IS NOT NULL "
        "GROUP BY topic_id, guid HAVING COUNT(*) > 1")).all()
    for tid, guid in cdupes:
        rows = conn.execute(sa.text(
            "SELECT id FROM comments WHERE topic_id = :t AND guid = :g "
            "ORDER BY created_at ASC, id ASC"), {"t": tid, "g": guid}).mappings().all()
        drop = [r["id"] for r in rows[1:]]
        if drop:
            conn.execute(sa.text("DELETE FROM comments WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=drop, expanding=True)))

    op.create_index("uq_topics_project_guid", "topics", ["project_id", "guid"], unique=True)
    op.create_index("uq_comments_topic_guid", "comments", ["topic_id", "guid"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_comments_topic_guid", table_name="comments")
    op.drop_index("uq_topics_project_guid", table_name="topics")
    op.drop_index("ix_comments_guid", table_name="comments")
    with op.batch_alter_table("comments") as b:
        b.drop_column("guid")
