"""Module full-text search — the portable search predicate + Postgres GIN-index DDL, extracted from
`modules.py`.

A pure leaf: every function takes the SQLAlchemy `Table` (or db) it operates on as an argument, so this
module imports nothing from `modules.py` (no cycle). `modules.py` injects its table registry — it keeps the
`fts_index_ddl(key)` / `ensure_fts_indexes(engine)` orchestration that knows `TABLES`, and re-exports the
query helpers here so `modules._pg_document` / `modules._pg_tsquery` keep working.

Postgres: stemmed, prefix, ranked full-text (`to_tsvector @@ to_tsquery`) with a matching GIN index built
from the *same* `_pg_document` expression so index and query can't drift. Everywhere else (SQLite dev/CI):
a substring `LIKE` fallback that needs no index.
"""
from __future__ import annotations

import re

from sqlalchemy import String, Table, cast, func, literal_column, or_
from sqlalchemy.orm import Session


def _is_postgres(db: Session) -> bool:
    try:
        return bool(db.bind) and db.bind.dialect.name == "postgresql"
    except Exception:
        return False


def _pg_tsquery(q: str) -> str | None:
    """A safe prefix tsquery from arbitrary user input: alnum words AND-ed, each prefix-matched
    (`conc & beam` -> `conc:* & beam:*`) so 'conc' finds 'concrete' and multi-word narrows."""
    words = re.findall(r"[A-Za-z0-9]+", q.lower())
    return " & ".join(f"{w}:*" for w in words) if words else None


def _pg_document(t: Table):
    """to_tsvector over ref + title + the whole field map (JSON cast to text). The regconfig is a
    `literal_column` (not a bind) so this exact expression can also be inlined into the GIN index DDL
    (`index_ddl`) — a bare "english" string renders as a bind param, which a CREATE INDEX can't use."""
    return func.to_tsvector(literal_column("'english'"), func.concat_ws(
        " ", func.coalesce(t.c.ref, ""), func.coalesce(t.c.title, ""), cast(t.c.data, String)))


def index_ddl(key: str, table: Table) -> str:
    """The `CREATE INDEX ... USING gin` DDL behind module full-text search, built from the *same*
    `_pg_document` the query's `@@` matches — so the indexed expression can't drift from the search
    expression. The regconfig is a literal_column and the coalesce defaults inline via literal_binds, so
    the whole to_tsvector(...) expression is safe to embed in a CREATE INDEX (no bind params)."""
    from sqlalchemy.dialects import postgresql
    expr = _pg_document(table).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return f'CREATE INDEX IF NOT EXISTS "ix_mod_{key}_fts" ON "mod_{key}" USING gin (({expr}))'


def search_filter(db: Session, t: Table, q: str):
    """Portable search predicate: Postgres full-text (stemmed, prefix, ranked) when available; a
    substring LIKE over ref/title/data everywhere else (SQLite dev)."""
    if _is_postgres(db):
        tsq = _pg_tsquery(q)
        if tsq:
            return _pg_document(t).op("@@")(func.to_tsquery("english", tsq))
    like = f"%{q.lower()}%"
    return or_(
        func.lower(func.coalesce(t.c.ref, "")).like(like),
        func.lower(func.coalesce(t.c.title, "")).like(like),
        func.lower(cast(t.c.data, String)).like(like),
    )
