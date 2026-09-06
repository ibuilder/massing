"""unique (project, module, field, value) on enum_options — the third natural-key seeding race

`modules.add_enum_option` reads the existing options through `list_enum_options(db, project_id)`,
decides, and inserts — with nothing holding the world still in between and no unique key underneath.
Two people adding the same custom option at the same moment both read "not present" and both insert,
and `list_enum_options` appends without de-duplicating, so the value appears TWICE in the dropdown
and stays there.

Same class as `d5f2a81c6b47`, and found because that migration's gate could not see it: the earlier
`test_seeding_sweep` required the model's name to appear in a lookup call in the same function, and
this one reads through a helper. The gate now drops that precondition.

Milder than its two siblings — a duplicated dropdown entry, not a permanent 500 — and fixed the same
way because the fix is the same size either way.

Revision ID: e7b3f4a9c218
Revises: d5f2a81c6b47
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3f4a9c218"
down_revision: str | None = "d5f2a81c6b47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Writers held off across BOTH steps, for the reason d5f2a81c6b47 records: between the dedupe
    # and the index build a live API can insert the very duplicate just removed, and the index build
    # then fails and aborts the deploy. SHARE is what CREATE INDEX takes anyway. Postgres only —
    # SQLite has no LOCK TABLE and serialises writers for the whole transaction regardless.
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("LOCK TABLE enum_options IN SHARE MODE"))

    # Keep the earliest of each duplicate set: it is the one whose created_at the option list has
    # been ordering by, so the dropdown's order does not move under anyone.
    dupes = conn.execute(sa.text(
        'SELECT project_id, module, field, value FROM enum_options '
        'GROUP BY project_id, module, field, value HAVING COUNT(*) > 1')).all()
    for pid, module, field, value in dupes:
        rows = conn.execute(sa.text(
            'SELECT id FROM enum_options WHERE project_id = :p AND module = :m AND field = :f '
            'AND value = :v ORDER BY created_at ASC, id ASC'),
            {"p": pid, "m": module, "f": field, "v": value}).mappings().all()
        drop = [r["id"] for r in rows[1:]]
        if drop:
            conn.execute(sa.text("DELETE FROM enum_options WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=drop, expanding=True)))

    op.create_index("uq_enum_options_project_module_field_value", "enum_options",
                    ["project_id", "module", "field", "value"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_enum_options_project_module_field_value", table_name="enum_options")
