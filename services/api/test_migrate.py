"""Schema evolution: the app has no Alembic — by design it uses an additive, dbDelta-style sync on
startup (init_db -> create_all + _ensure_columns + _ensure_indexes), which fits the config-driven
dynamic module tables (mod_<key> registered into Base.metadata from module.json). This proves the
real sync path: a model that gains a nullable column gets that column ALTERed onto an already-created
table (SQLite + Postgres), and a new index backfills — idempotently, never dropping anything.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_migrate.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_migrate.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_test_migrate")
for f in ("./_test_migrate.db",):
    if os.path.exists(f):
        os.remove(f)

from sqlalchemy import Column, Index, Integer, String, Table, inspect  # noqa: E402

from aec_api import db  # noqa: E402

# 1) real production startup path: registers dynamic module tables + creates the full schema
db.init_db()

# 2) a throwaway table created with a single column, like an existing DB on an older app version
probe = Table("mig_probe", db.Base.metadata, Column("id", Integer, primary_key=True))
db.Base.metadata.create_all(bind=db.engine, tables=[probe])
cols = {c["name"] for c in inspect(db.engine).get_columns("mig_probe")}
assert cols == {"id"}, f"expected just id at first, got {cols}"

# 3) the model gains a nullable column in a newer release (create_all alone would NOT ALTER it in)
probe.append_column(Column("note", String))
db._ensure_columns()
cols = {c["name"] for c in inspect(db.engine).get_columns("mig_probe")}
assert "note" in cols, f"additive sync must ADD the new column, got {cols}"

# 4) idempotent: re-running the sync is a clean no-op (no duplicate-column error)
db._ensure_columns()

# 5) a new index defined on the model backfills onto the existing table (checkfirst, never throws)
Index("ix_mig_probe_note", probe.c.note)
db._ensure_indexes()
idx = {i["name"] for i in inspect(db.engine).get_indexes("mig_probe")}
assert "ix_mig_probe_note" in idx, f"new index must backfill, got {idx}"
db._ensure_indexes()  # idempotent

# 6) additive only — the original column is never dropped
assert "id" in {c["name"] for c in inspect(db.engine).get_columns("mig_probe")}

print("MIGRATE OK - additive sync adds new nullable columns + backfills indexes on existing tables; "
      "idempotent; additive-only (no drops); dynamic module tables created via init_db")
