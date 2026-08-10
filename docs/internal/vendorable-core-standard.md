# The vendorable-core standard for MassingCloud libraries

Internal. Derived from three adoptions measured on 2026-08-09 — one that worked, one that could not
be attempted, and one that was already right — rather than from preference.

## The rule

**A MassingCloud library that Massing may consume must have a framework-free core with zero runtime
dependencies, and an architecture test that fails the build when that stops being true.**

Web framework, ORM, HTTP server and CLI are *adapters* over that core, declared as optional extras.

## Why this, and not "standardise on FastAPI"

The obvious answer to "we have Flask here and FastAPI there" is to pick one. It is the wrong answer,
because the framework is not what we consume — the **calculation** is. Measured today:

| repo | framework | vendorable? |
|---|---|---|
| `massingplan` | Flask | **yes** — `massingplan/core/`, 19 modules, pure stdlib |
| `massingcapture` | FastAPI *(optional extra)* | **yes** — zero runtime deps, stdlib server bundled |
| `massingbill` | Flask | **no** — `services/application.py` (778 lines) and `services/sov.py` (398) import `sqlalchemy`, `extensions.db` and `models` |

massingplan is a **Flask** app and vendored cleanly into our **FastAPI** service without Flask coming
along, because the part we wanted had no framework in it. massingbill is blocked for the opposite
reason, and its blocker has nothing to do with Flask — it is that the pay-application arithmetic is
entangled with the ORM.

So the framework split is not the problem and unifying it would not have fixed anything. **Extracting
the core is the whole intervention.** Standardising on FastAPI would have cost real migration work
and left massingbill exactly as unadoptable as it is now.

## The reference implementation is `massingcapture`

Its `pyproject.toml` says `dependencies = []` and its docstring states the property plainly: format
detection, E57/LAS/PLY/GLB/EXIF probing, coordinate math, Procrustes registration, the walkthrough
graph, the job planner, the NodeODM client, the HTTP API and the browser viewer are **all standard
library**. Heavy things live in `adapters/` behind a token and are optional — including FastAPI:

> *"Mount the transport-agnostic API on FastAPI instead of the bundled stdlib server."*

That is the shape: a core that does not know what is calling it, a default server that needs nothing
installed, and every framework a choice the consumer makes.

Critically, `tests/test_architecture.py` **fails the build if the core gains a runtime dependency**.
The property is enforced, not intended — which is the difference between a standard and a preference.

## What a kit must also get right

Three defects found while adopting massingplan, none of which are about the core:

1. **Tests must run in the consumer's harness.** Ten vendored suites failed with
   `ModuleNotFoundError: No module named 'pytest'` — they are pytest-based and this repo deliberately
   has none. The vendored copy must be stdlib-runnable: plain `assert`, a `__main__` runner. The
   upstream repo can use whatever it likes; the *copy* matches the host.
2. **Test filenames must not collide.** `test_cpm`, `test_constraints` and `test_graph` already exist
   here among ~566 flat modules, so a bare name in our manifest resolves to *our* file. Namespace
   them.
3. **Generate the pin from a clean tree.** massingplan's vendor script warned its working tree was
   dirty, so the recorded SHA does not describe what was copied and the drift guard is not
   reproducible. The drift workflow is therefore not installed here yet.

And one that is about the core, but only shows up later: **verify the copied subtree, not the
project.** massingplan's `pyproject.toml` declares Flask, Flask-WTF, SQLAlchemy, alembic and
argon2-cffi. Checking that would have said "not vendorable". Checking `massingplan/core/` — the thing
the script actually copies — said pure stdlib, which was the truth. Derive the population *and* the
reach.

## What this does not say

It does not say a MassingCloud repo may not be a web application. massingbill and massingplan are
both full products and should stay that way. It says the part we consume must be separable, and that
separability is proven by a test rather than asserted in a README.

Related: [`docs/internal/dependency-advisories.md`](dependency-advisories.md) for what we carry
knowingly; the licence rule is unchanged and absolute — MIT / BSD / Apache-2.0 / ISC only, with GPL,
AGPL, CC BY-NC and SSPL as hard exclusions, read from the LICENSE file and never from a README.
