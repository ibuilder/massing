# Troubleshooting

Ordered by how often each one actually happens. Every item here is a failure someone has hit in this
repo, not a hypothetical.

## First: is the thing you are debugging even alive?

**A dying dev server imitates a product bug almost perfectly.** Panels are empty, saves silently fail,
lists render as zero rows — all indistinguishable from broken features.

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
```

`000` means nothing is listening. Confirm this **before** reading any frontend code. A `200` here is
the precondition for every other diagnosis on this page.

## The web app

### Blank viewer, blank panel, or a build that fails oddly
**Check your Node version first.**

```bash
node -v
```

It must report **24 or later**. Node 18 breaks the web build, and the symptom is usually a blank panel
rather than an honest error. On a machine where the wrong Node is first on `PATH`, put the right one
first:

```bash
export PATH="/c/Program Files/nodejs:$PATH"
```

Both manifests declare `"engines": {"node": ">=24"}` and CI pins 24, so 24 is the baseline. Do not trust
a version written in a document — including this one. Run `node -v`.

### A panel is blank but `tsc` is clean
That combination means a **stale dev bundle**, not a code error. The Vite dev graph is serving something
you have already changed. Hard-restart the dev server; a reload is not enough.

### The app loads but every panel is empty
The API is not reachable. Run the health check above. If the API is up, check the origin: **`localhost`
and `127.0.0.1` are different origins** to CORS, and mixing them produces exactly this. Use the same one
everywhere.

If you are driving a live preview, the backend is expected on port **8093**.

### The viewer never finishes loading a model
Geometry is streamed as pre-converted `.frag` tiles. If conversion has not run, there is nothing to
stream:

```bash
node services/converter/src/cli.mjs model.ifc model.frag
```

The browser deliberately cannot parse full IFC at runtime, so "just open the IFC" is not a fallback.

### A number shows `—` instead of a value
That is working as designed. A vitals value that cannot be computed renders as **`—` with its reason**
rather than `0`. On a structural-only model, Area reads `—` because there are no `IfcSpace` entities. A
`0` would look like an answer; the dash does not.

## Authoring

### An edit is rejected
`/edit/precheck` refuses edits that would write broken IFC. The rejection is the feature — read the
reason it gives. An authoring tool that lets you save an invalid model has just moved the failure to
whoever opens the file next.

### `execute_ifc_code` is unavailable
The AST-sandboxed ifcopenshell path is **feature-flagged off** by default. `GET /authoring/capabilities`
probes whether it is enabled. This is deliberate: it executes code, so it is gated rather than trusted.

### An element moved and now a record points at the wrong place
It should not — records anchor by **GlobalId**, not coordinates. If it happened, the record was anchored
by something transient. Viewer IDs are not durable identifiers; only GUIDs are.

## Modules and records

### A `PATCH` silently does nothing
The two shapes differ. Create wraps the fields; update does not:

```jsonc
POST  /projects/{id}/modules/{key}       { "data": { "title": "…" } }   // wrapped
PATCH /projects/{id}/modules/{key}/{rid} { "title": "…" }               // direct
```

### A new module is missing fields, or does not appear
`GET /modules` is an **allowlist** and silently drops keys it does not recognise. Check there first —
the data is usually present and unreported.

### A new module works locally and fails on a fresh deploy
`module.json` creates `mod_<key>` at runtime, but the table still needs a committed **Alembic
autogenerate revision** — and keep the Postgres FTS GIN index tail. Without it, the table exists on your
machine and nowhere else.

### Two fields render far apart in the form
Fields in the same fieldset must be **adjacent** in the field list. Contiguity is the grouping.

## Running the tests

### The backend suite reports "0 failures" and you do not believe it
You are probably in the wrong directory. Run it **from `services/api`**:

```bash
cd services/api && PYTHONPATH=src .venv/Scripts/python.exe run_tests.py
```

From the repo root it exits **127** and reports "0 failures", which reads exactly like a pass. There is
no `pytest` entry point — `run_tests.py` is the runner.

### Unicode errors in test output on Windows
Run with `PYTHONUTF8=1`.

### A test passes alone and fails in the suite
There is a known ifcopenshell flake under parallel execution on Windows. Re-run the test on its own to
confirm; if it passes solo, that is the flake and not your change.

### `test_desktop` starts failing after you build the web app
`npm run build` rewrites `dist/`, which `test_desktop` reads. Do not build the web app while the backend
suite is running.

## Deployment

### It works locally and is unsafe in production
The defaults are tuned for a laptop. Set real secrets in `.env`, turn on RBAC (`AEC_RBAC=1`), and work
through the [go-live checklist](../PRODUCTION_CHECKLIST.md). Every knob is documented in `.env.example`.

### Scratch files fail to write in the container
`/app` is read-only. Never write scratch into the source tree; use the container's temp location.

### A restore has never been tested
Then you do not have backups. [ops-dr.md](../ops-dr.md) covers how a restore is *proven*, not just
performed.

## Still stuck

- `/docs` on any running API is the live, authoritative endpoint reference.
- [operations.md](../operations.md) — day-2 runbook, health probes, common incidents.
- [ops/runbooks.md](../ops/runbooks.md) — incident runbooks.
- [Open an issue](https://github.com/ibuilder/massing/issues) with what you ran, what you expected, and
  what the health check returned.
