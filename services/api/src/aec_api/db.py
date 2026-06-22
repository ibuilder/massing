"""Database setup. SQLite for dev; set DATABASE_URL to a Postgres DSN for prod (guide §7)."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./aec.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns() -> None:
    """Additive, dbDelta-style schema sync: create_all never ALTERs existing tables, so add
    any model columns missing from already-created tables. Additive only — never drops.
    Keeps SQLite (dev) and Postgres (prod) in sync as the models gain nullable columns."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            coltype = col.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'))


def _ensure_indexes() -> None:
    """Create any index defined on the models that's missing from an already-created table —
    create_all() only makes indexes for *new* tables, so this backfills new indexes (e.g. the
    module (project_id, workflow_state) composite) on existing DBs. Idempotent (checkfirst)."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            try:
                index.create(bind=engine, checkfirst=True)
            except Exception:        # noqa: BLE001 — never block startup on an index backfill
                pass


def init_db() -> None:
    from . import models  # noqa: F401  (register mappers)
    from . import modules  # GC portal: register one mod_<key> table per module.json
    modules.load_registry()
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _ensure_indexes()
    # load admin-configured integration settings into the in-process cache
    from . import settings_store
    with SessionLocal() as _s:
        settings_store.load(_s)
