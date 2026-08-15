# Vendored: massingplan core

`massingplan/core/` from **MassingCloud/massingplan**, copied verbatim.

| | |
|---|---|
| Upstream | https://github.com/MassingCloud/massingplan |
| Commit | `a740241c0be9c1ac9789b72f1183301e6058f19e` |
| Synced | 2026-08-15 |
| Content digest | `8cbc89168ed83335` |
| Local deviations | **NONE** |

## What this is

**"Pure standard library" describes this subtree, not the upstream project.**
`massingplan/core/` imports nothing but the standard library, and an
import-linter contract plus a dependency-free CI job hold it that way, because
that is the property this copy depends on. The upstream *project* around it
declares Flask, SQLAlchemy, Alembic and argon2-cffi for its web application —
so anyone verifying the claim should read this directory, not that
`pyproject.toml`. Checking the project would give the wrong answer.

A pure-standard-library construction scheduling engine: multi-calendar CPM with
all four relationship types and all ten constraint types, data date and
progressed logic, DCMA 14-point quality assessment, Monte Carlo risk, resource
levelling, baseline comparison with delay attribution, and Primavera XER /
MS Project MSPDI interchange.

It replaces `aec_api/schedule_cpm.py`, which was Finish-to-Start only with no
lags, no calendars and no constraints, and which never wrote computed dates
back to the activities.

## Why it is vendored rather than installed

`services/api/src` is already on `PYTHONPATH` (see `services/api/Dockerfile`),
and `core` imports nothing outside the standard library, so this directory works
here with no packaging change. The API image installs a hash-pinned
`requirements.lock`, which would make every upstream bump a lock regeneration.

Publishing `massingplan-core` to PyPI is roadmapped; because the package is pure
stdlib, the switch is a one-line change.

## Do not edit these files here

Fix it upstream and re-sync. A local patch makes this a fork, and the next sync
silently reverts it.

## Re-syncing

**You pull; upstream does not push.** massingplan stages a kit and never writes
into this tree, so a re-sync happens when this repo decides it should — not
when somebody upstream runs a script.

From a massingplan checkout, build the kit:

```bash
python scripts/vendor_to_massing.py
```

Then, from this repo, take it:

```bash
cp -r <massingplan>/dist/vendor/services/api/. services/api/
```

That single copy carries the engine, the adapter modules and the conformance
gate, already in this tree's shape — `dist/vendor/services/api/` mirrors
`services/api/`, so nothing needs rewriting.

To see what has changed upstream before taking it, from massingplan:

```bash
python scripts/vendor_to_massing.py --check --massing
```

It reports drift by kind and writes nothing. Or by hand, engine only:

```bash
rm -rf services/api/src/massingplan
cp -r <massingplan>/massingplan/core services/api/src/massingplan
cp <massingplan>/massingplan/py.typed services/api/src/massingplan/py.typed
```

## Tests

`services/api/test_mp_engine.py` — a **stdlib-only** conformance gate. No pytest,
a `__main__` runner, flat placement, and a `test_mp_` prefix.

```bash
python test_mp_engine.py       # from services/api
```

Each of those three properties was learned on first adoption. Flat, because
`run_tests.py` discovers with a non-recursive glob and a suite one directory
down does not run — silently, with the gate green over the very defect it was
meant to catch. Prefixed, because `test_cpm`, `test_constraints` and
`test_graph` already exist flat here, so a bare stem resolves to the local file.
Stdlib, because this repo deliberately has no pytest and a vendored suite that
imports it dies before its first assertion.

**Register it with `run_tests.py`.** It is not discovered by accident, and a
gate nobody runs is worse than no gate — it reads as coverage.

The gate is not upstream's suite. massingplan runs roughly 780 tests on every
push, including a 100%-branch-coverage job on the calendar kernel; duplicating
those here would create two copies to keep in step. What this file answers is
the narrower question: does the copy in `src/massingplan` still behave the way
*this* repo's callers require? It checks the calendar adjoint invariant, the
`compute()` dict contract, that a sequential chain sums, that float is numeric
for completed work, that a cycle refuses rather than inventing dates, and that
`TASKPRED` is read on import.
