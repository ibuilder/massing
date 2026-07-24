# Backend engineering standards (Python / FastAPI / SQLAlchemy)

*R19 ENG-STD (2026-07-24). These are the conventions the codebase **actually runs on** — codified
from shipped practice, not aspiration. New code follows them; drift found against them is a fix
ticket, not a debate. Style baseline: PEP 8 via ruff (configured in-repo); typing on public
signatures; Python ≥ 3.10 (prefer 3.11+ for new venvs).*

## Architecture

- **Engine-leaf / adapter / one-gate.** Domain logic lives in a **pure engine module**
  (`aec_api/<engine>.py` or `aec_data/<engine>.py`): plain functions, dict/dataclass in → dict out,
  no HTTP and (where possible) no DB. The **router** is a thin adapter: parse/validate → call the
  engine → shape the response; exactly **one** authorization gate per route (`require_role`), never
  logic in two layers. Engines are what tests import.
- **Layering rule:** `aec_api` MAY import `aec_data`; **never** the reverse. `aec_data` is
  model/geometry-only (ifcopenshell world), reusable by the CLI and workers.
- **Reference by GUID.** Model elements are referenced by IFC GlobalId everywhere — API bodies,
  stored records, recipes. Transient viewer ids never cross the API boundary.
- **Module records** go through the module engine (`modules.py` + `module_schema.py` as the single
  source of truth for `module.json`). Create wraps the field map: `{"data": {...}}`; PATCH takes the
  field map directly. Same-fieldset fields stay adjacent (test-enforced).
- **Selectors compose on QUERY-DSL.** Any new scoping/filter feature reuses `query_dsl.select()` —
  one grammar for model elements, topics, and rules. No second selector language.
- **Stored-config caps.** Anything an editor can store that a viewer-level GET later evaluates gets
  count/size caps at save time (the `rule_library.MAX_*` pattern). Caps keep the **newest** rows
  (`desc().limit()` then re-sort), never silently hide new data.

## FastAPI & sessions

- Dependency-injected `Session` per request; explicit commits; no session escapes its request.
  Internal engines that need a session in tests use `SessionLocal()` context managers.
- Long/CPU work goes to the jobs lane (durable queue), never inline in a request. Geometry worker
  count is env-tunable (`AEC_GEOM_WORKERS`).
- Public (unauthenticated) endpoints are exceptional, hardened by construction: whitelists, length
  caps, hard count caps, revocation → 404 (the ShareToken pattern).
- Errors: raise `HTTPException` with a useful `detail` (include the offending field/name); 409 for
  optimistic-concurrency conflicts; 422 for validation.

## SQLAlchemy & migrations

- SQLAlchemy 2.x typed mappings (`Mapped[...]`/`mapped_column`). Aggregations in SQL, not Python
  loops (the P0 SQL-aggregate helpers). Never `dict(cursor)` — use `.all()` (ruff C416 autofix is
  unsafe on cursors).
- **Every new table/column ships an Alembic autogenerate revision in the same release.** SQLite
  non-null adds need `server_default`.
- **Postgres-only DDL discipline:** anything in an index expression must be IMMUTABLE (`concat_ws`
  is STABLE — use all-coalesced `||`). Every post-baseline migration creating a `mod_<key>` table
  hand-adds the Postgres-only FTS GIN block (static-guard-enforced in `test_alembic_migrations`).
  The real gate is `db-migrations.yml` against genuine Postgres — check its run after every
  migration release; SQLite cannot catch this class.

## Determinism & money

- Engines are deterministic: same input → same output, asserted byte-identical where it matters
  (view-template resolve is the reference). No wall-clock/randomness inside engines; timestamps come
  from the caller or the DB.
- Money at the API/storage boundary goes through `money.py` (Decimal). Pure analytical engines may
  compute in float but round once at the edge; Python `round()` is banker's rounding — test
  expectations accordingly. Never accumulate currency by repeated float addition across thousands of
  rows without a final Decimal reconciliation.
- User-supplied expressions are never `eval`'d: `calc_fields.py` (AST whitelist + node/length caps)
  is the only expression path. Regexes over user text: bounded quantifiers + input caps (ReDoS
  discipline).

## Testing

- Runner: `run_tests.py` (no pytest); tests are `test_*.py` in `services/api/`, **hardcoded in the
  TESTS list — register every new test file** (the runner tolerates missing files; a count drop is a
  signal, not noise).
- Full gate: `cd services/api && AEC_GEOM_WORKERS=1 PYTHONUTF8=1 PYTHONPATH="src;../data/src"
  ./.venv/Scripts/python.exe -X utf8 run_tests.py` — clean `test_*.db` / `_storage_*` artifacts
  first (cleanup globs must be artifact-shaped; never `test_*` bare).
- Test shape: each file is a self-contained scenario — env vars up top (`DATABASE_URL` sqlite
  scratch, `STORAGE_DIR`), engine asserts first, then route asserts via `TestClient`, one loud
  `print("... OK - ...")` summarizing what was proven. Golden/hand-computed fixtures for numeric
  engines.
- Targeted test per feature while building; the **full suite gates the release**, per sprint.

## Security invariants (the short list every PR is checked against)

`require_role` on every project route (test-enforced) · privileged operations gate every path, not
just the front door · no secrets in code/repo — env/operator config only · untrusted XML through
defusedxml · outbound fetches through the SSRF guard · non-crypto hashes flagged
`usedforsecurity=False` · CodeQL at 0 after every push (the `security-monitoring` skill is the
operating procedure).

## Releases

Version-numbered releases to main: bump `apps/web/package.json` + `src-tauri/tauri.conf.json`,
CHANGELOG newest-first (no competitor names — standing directive), roadmap marks, full suite green,
tag `v0.3.NNN`, then verify CI + CodeQL. Load-bearing decisions get an ADR (`docs/adr/`).
