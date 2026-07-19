"""Database setup. SQLite for dev; set DATABASE_URL to a Postgres DSN for prod (guide §7)."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./aec.db")

if DATABASE_URL.startswith("sqlite"):
    _connect_args: dict = {"check_same_thread": False}
else:
    # Bound how long DB I/O can block — without this a black-holed DB (network partition / paused
    # host) makes every request (and the /ready probe) hang forever instead of failing fast.
    # connect_timeout bounds new connections; TCP keepalives bound an already-open pooled
    # connection whose peer has gone away (libpq detects the dead socket instead of waiting forever).
    _ct = int(os.environ.get("AEC_DB_CONNECT_TIMEOUT", "5"))
    _connect_args = {"connect_timeout": _ct, "keepalives": 1, "keepalives_idle": 5,
                     "keepalives_interval": 2, "keepalives_count": 2}
if DATABASE_URL.startswith("sqlite"):
    # SQLite uses a single-file lock; the default pool is fine (and QueuePool sizing is moot).
    _pool_kw: dict = {}
else:
    # Default SQLAlchemy pool (5 + 10 overflow) starves a multi-worker API under mega-project
    # concurrency — every request that touches the DB queues behind 15 connections. Size it from
    # the environment (per worker) and recycle idle connections so a long-lived pool doesn't hold
    # stale sockets. pool_timeout fails fast instead of hanging a request forever on pool exhaustion.
    _pool_kw = {
        "pool_size": int(os.environ.get("AEC_DB_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("AEC_DB_MAX_OVERFLOW", "20")),
        "pool_recycle": int(os.environ.get("AEC_DB_POOL_RECYCLE", "1800")),
        "pool_timeout": int(os.environ.get("AEC_DB_POOL_TIMEOUT", "30")),
    }
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True,
                       future=True, **_pool_kw)
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
    from sqlalchemy import inspect

    from . import (
        models,  # noqa: F401  (register mappers)
        modules,  # GC portal: register one mod_<key> table per module.json
    )
    modules.load_registry()
    # PERF-4 (TEST-FASTPATH): reconciliation only matters on an EXISTING db that predates a model
    # change. On a brand-new db, create_all() builds every table + its indexes current, so the
    # column/index sync is a pure no-op — an inspect round-trip per ~130 tables + a checkfirst per
    # index. Detect "fresh" BEFORE create_all (no known table present) and skip it. Every test spins
    # up a fresh SQLite db, so this is the bulk of the suite's per-test startup cost.
    known = {t.name for t in Base.metadata.sorted_tables}
    pre_existing = set(inspect(engine).get_table_names()) & known
    Base.metadata.create_all(bind=engine)
    if pre_existing:                      # an upgrade path: some tables predate this build → reconcile
        _ensure_columns()
        _ensure_indexes()
    # Postgres-only: GIN index behind the module full-text search (`@@`). No-op on SQLite.
    modules.ensure_fts_indexes(engine)
    # load admin-configured integration settings into the in-process cache
    from . import settings_store
    with SessionLocal() as _s:
        settings_store.load(_s)
