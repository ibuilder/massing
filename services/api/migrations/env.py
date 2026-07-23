"""Alembic environment for the Massing API.

Builds the COMPLETE target metadata the same way the app does at startup: the static ORM models
(``aec_api.models``) plus the config-driven dynamic module tables (``mod_<key>``, one per
``modules/<key>/module.json``), which are registered into ``Base.metadata`` by
``modules_registry.load_registry()``. Autogenerate / ``alembic check`` therefore see exactly the
schema the running app manages.

The DB URL is taken from the app's ``DATABASE_URL`` env var (same default as ``aec_api.db``) — never
hardcoded — so migrations run against whatever DB the app is configured for.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- make the app package importable when alembic runs from services/api/ ------------------------
# (prepend_sys_path in alembic.ini also covers the common case; this makes env.py robust to the CWD.)
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- assemble the full metadata (static models + dynamic module tables) --------------------------
from aec_api import (
    models,  # noqa: E402,F401  (imported for its side effect: registers ORM mappers)
    modules_registry,  # noqa: E402
)
from aec_api.db import Base  # noqa: E402

modules_registry.load_registry()  # registers every mod_<key> table into Base.metadata

target_metadata = Base.metadata


def _database_url() -> str:
    """The app's DB URL — env first, then aec_api.db's own default. Never hardcoded here."""
    from aec_api import db
    return os.environ.get("DATABASE_URL", db.DATABASE_URL)


def _include_object(obj, name, type_, reflected, compare_to):
    """Exclude the Postgres-only full-text GIN indexes (``ix_mod_<key>_fts``) from autogenerate
    comparison. They are expression indexes over ``to_tsvector(...)`` created imperatively by
    ``aec_api.modules.ensure_fts_indexes`` (raw DDL, not ORM metadata); the baseline revision
    recreates them by reusing that same DDL builder. Excluding the *reflected* index here keeps
    ``alembic check`` clean instead of reporting a phantom drop of an index Alembic can't render."""
    if type_ == "index" and name and name.startswith("ix_mod_") and name.endswith("_fts"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            compare_type=True,
            # SQLite can't ALTER in place, so real migrations use batch mode there. The baseline is
            # pure CREATE (no ALTER on any dialect), so it's generated with AEC_ALEMBIC_NO_BATCH=1 to
            # emit plain, dialect-neutral op.create_index instead of SQLite-flavored batch ops.
            render_as_batch=(connection.dialect.name == "sqlite"
                             and not os.environ.get("AEC_ALEMBIC_NO_BATCH")),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
