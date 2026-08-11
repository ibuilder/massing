# Vendored: massingplan core

`massingplan/core/` from **MassingCloud/massingplan**, copied verbatim.

| | |
|---|---|
| Upstream | https://github.com/MassingCloud/massingplan |
| Commit | `b703dca49b6a8f88b26fe114d2716989de4dbf5c` |
| Synced | 2026-08-11 (was `155640a7`, 2026-08-10) |
| Content digest | `d7d2ac5e71b0ac7e` — **recipe below** |
| Local deviations | **NONE** — verified in both directions, see below |

### How the digest is computed

Written down because the previous one was not. The recorded `3b94544306fb8c13` could not be
reproduced by any recipe tried here, so it could not be used to verify anything — **a recorded
verification value nobody can recompute is not a verification, it is a decoration.** It is replaced
rather than carried forward, and the method is now stated so the next sync can check it:

```
sha256 over, for each *.py in `massingplan/core` at the pin, sorted by full path:
    basename  then  file bytes with CRLF normalised to LF
truncated to 16 hex chars
```

CRLF normalisation matters and is not cosmetic: this repo sets `* text=auto`, so a checkout on
Windows has CRLF on disk while `git show` emits LF. A byte-for-byte comparison against upstream
reports **every line of every file** as changed. That is exactly what happened during this sync —
7 files looked modified, and normalised the real answer was 1.

### What changed at this pin

- `schedule.py` — **additive**: new `schedule_with_network()` returns the network `schedule()` had
  already built, so a caller needing the links stops calling `to_network()` a second time.
  `schedule()` delegates to it, so there is still one implementation and its signature is unchanged.
  26 insertions, 4 deletions.
- `locations.py` — **new, and inert here**: location-based (line-of-balance) scheduling. Nothing in
  our adapter imports it. Vendored anyway, because the pin names a tree and a *partial* copy is how
  two implementations start — the exact hazard upstream's own drift check watches for in both
  directions.

Verified before copying: **no file exists in our copy that is absent upstream**, so there were no
local edits to lose. That direction is the dangerous one — a fix made here and never sent up is
invisible to a one-way check.

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

From a massingplan checkout:

```bash
python scripts/vendor_to_massing.py --target C:/Server/modelmaker/services/api/src/massingplan
```

Or by hand:

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
