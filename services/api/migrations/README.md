# Database migrations (Alembic)

Alembic is the **source of truth** for the API database schema going forward. All future schema
changes (new tables, columns, indexes, constraints) MUST be made by generating a new revision — see
[Making a schema change](#making-a-schema-change).

> **Runtime note (this PR does NOT cut over).** The application still creates its schema at startup
> via `Base.metadata.create_all()` + the additive `_ensure_columns` / `_ensure_indexes` sync in
> `aec_api.db.init_db()`. Alembic is introduced here as the migration framework + a versioned
> baseline; the runtime is **not** yet driven by `alembic upgrade`. Replacing the additive path with
> migration-driven schema management is a separate follow-up. Nothing here runs migrations
> automatically at app startup.

## Layout

- `alembic.ini` — config (in `services/api/`). The DB URL is **not** hardcoded here.
- `migrations/env.py` — reads the DB URL from the app's `DATABASE_URL` env var (same default as
  `aec_api.db`) and builds the full target metadata: the static ORM models (`aec_api.models`) **plus**
  the config-driven dynamic module tables (`mod_<key>`, one per `modules/<key>/module.json`), which
  `modules_registry.load_registry()` registers into `Base.metadata`.
- `migrations/versions/` — revision scripts. The first is the baseline that creates the current schema.

All commands below run from `services/api/` with the app importable (the lock installs `alembic`):

```bash
cd services/api
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/massing   # or your prod DSN
```

## Existing databases (already built by the current runtime path) — STAMP, do not upgrade

An existing DB already has every table/column/index (create_all + `_ensure_*` built them). Running
the baseline against it would fail (tables already exist). Instead, **stamp** it at the baseline so
Alembic records it as up to date **without executing** the migration:

1. **Back up first.** `pg_dump` (or your managed-DB snapshot). Non-negotiable.
2. **Verify** the schema matches the current models — the surest check is the CI drift guard
   (`alembic check` reports no diff; see `.github/workflows/db-migrations.yml`). If it's clean, the
   DB matches the baseline.
3. **Stamp:**
   ```bash
   alembic stamp head
   ```
   This writes the baseline revision into the `alembic_version` table and runs no DDL.

## Fresh databases — UPGRADE

For a brand-new, empty DB, apply the baseline (and any later revisions):

```bash
alembic upgrade head
```

This creates the current schema. On PostgreSQL it also creates the full-text search **GIN indexes**
(`ix_mod_<key>_fts`) that the runtime otherwise builds via `modules.ensure_fts_indexes` — see
[Drift reconciled in the baseline](#drift-reconciled-in-the-baseline). On SQLite those indexes are
skipped (dev/CI use a `LIKE` fallback), matching runtime behavior.

## Making a schema change

1. Edit the models (`aec_api/models.py`) — or add a `modules/<key>/module.json` for a new module table.
2. Autogenerate a revision and **review it by hand** (autogenerate misses raw DDL / functional indexes):
   ```bash
   alembic revision --autogenerate -m "describe the change"
   ```
3. Apply it: `alembic upgrade head`. Commit the new file under `migrations/versions/`.

The CI drift guard fails if models and migrations disagree, so a forgotten revision won't merge.

## Drift reconciled in the baseline

The runtime creates one thing that lives **outside** ORM metadata, so autogenerate can't see it: the
Postgres-only full-text **GIN index** on each module table (`ix_mod_<key>_fts`, an expression index
over `to_tsvector(...)`, built by `aec_api.modules.ensure_fts_indexes`). The baseline revision
recreates these by reusing the exact same DDL builder (`aec_api.modules_search.index_ddl`), so the
migrated schema matches runtime on Postgres. `migrations/env.py` excludes these from `alembic check`
comparison (they are functional indexes Alembic can't render), keeping the drift guard clean.

Aside from that, the additive `_ensure_columns` / `_ensure_indexes` sync adds **nothing** beyond
model metadata — verified by diffing a create_all-built DB against an Alembic-upgraded DB (identical
tables + indexes). So the models are the only other source of schema truth, and the baseline captures
them faithfully.

> **Config-driven module tables:** because `mod_<key>` tables are registered from `module.json` files,
> adding a new module changes `Base.metadata`. The drift guard will then flag the new table until you
> generate a revision for it (or, for an existing DB that create_all already built it on, `alembic
> stamp` after adding the CREATE to a revision). Treat a new module's table like any other schema change.
