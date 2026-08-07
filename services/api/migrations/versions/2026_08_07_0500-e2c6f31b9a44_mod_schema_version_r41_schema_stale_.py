"""mod_* schema_version (R41-SCHEMA-STALE)

Adds one nullable `schema_version` column to every `mod_<key>` register table.

WHY THIS IS ONE MIGRATION AND NOT 135. Every register gets its table from a single factory
(`modules_registry._table`), so the column is declared once — but the tables already EXIST in a
deployed database, and `Base.metadata.create_all` only creates missing tables, it never alters an
existing one. Without this revision the column would appear on a fresh SQLite test database (making
the suite pass) and be absent from every deployed Postgres (making every insert fail). That gap is
the reason "a new module needs an Alembic revision" is a standing rule here.

Discovered from the LIVE database, not from the registry. Iterating the Python registry would add
the column only to modules this build knows about and would silently skip a table left behind by a
module that was renamed or removed — and those legacy tables are exactly the ones whose rows are
most likely to be schema-stale. The inspector answers "what tables are actually there", which is
the question.

NOT BACKFILLED, on purpose. Stamping existing rows with today's signature would assert they were
written against a schema that may not have existed when they were written — a confident wrong value
in place of an honest unknown. NULL reads back as `stored: None`, and the payload checks in
`module_schema.schema_status` (orphaned / mistyped keys) need no stamp at all, so historical rows
still get the detection that matters.

Revision ID: e2c6f31b9a44
Revises: a7e3b9c04d15
Create Date: 2026-08-07 05:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "e2c6f31b9a44"
down_revision = "a7e3b9c04d15"
branch_labels = None
depends_on = None


def _module_tables(bind) -> list[str]:
    insp = sa.inspect(bind)
    return sorted(t for t in insp.get_table_names() if t.startswith("mod_"))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _module_tables(bind):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "schema_version" in cols:
            continue          # idempotent: a table created after the factory change already has it
        op.add_column(table, sa.Column("schema_version", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _module_tables(bind):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "schema_version" not in cols:
            continue
        op.drop_column(table, "schema_version")
