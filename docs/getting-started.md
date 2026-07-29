# Getting started

Three ways in, in order of how quickly they get you to a model on screen. Pick one — they are
alternatives, not steps.

| Route | Good for | Needs |
| --- | --- | --- |
| [Live demo](#0-live-demo-nothing-to-install) | Seeing it work | A browser |
| [Desktop app](#1-desktop-app-one-project-at-a-time) | Using it on one project | A download |
| [Docker](#2-docker-the-full-stack) | The real thing, self-hosted | Docker |
| [Dev setup](#3-dev-setup-from-source) | Changing the code | Node 24, Python 3.12 |

## 0. Live demo (nothing to install)

**[massing.build/app](https://massing.build/app/)** runs the viewer with sample geometry. There is no
API behind it, so authoring, records and the proforma are not exercised — it streams committed sample
tiles. Good for a first look; not a trial of the platform.

## 1. Desktop app (one project at a time)

Download a signed build for Windows, macOS or Linux from
**[the latest release](https://github.com/ibuilder/massing/releases/latest)**. It auto-updates, is free,
and carries its own local storage — no server to run. Single-project by design; if you need several
projects or several people, use Docker.

## 2. Docker (the full stack)

The complete platform: web app, API, Postgres, object storage.

```bash
git clone https://github.com/ibuilder/massing.git && cd massing
cp .env.example .env
docker compose --profile full up --build
```

Web app on **http://localhost:8080**, API on **http://localhost:8000**.

Optionally fill a demo project that exercises every module and relation chain:

```bash
docker compose --profile full --profile seed run --rm seed
```

**Before you expose this to anyone**, set real secrets in `.env` and turn on RBAC (`AEC_RBAC=1`), then
work through the [go-live checklist](PRODUCTION_CHECKLIST.md). `.env.example` documents every knob.
Defaults are tuned for a laptop, not for the internet.

The web container reverse-proxies `/api` to the API, so there is no CORS to configure, and it sets the
cross-origin isolation headers that web-ifc needs for `SharedArrayBuffer`. Postgres, object storage and
IFC volumes persist across restarts.

## 3. Dev setup (from source)

**Node 24 and Python 3.12** are the supported baseline — both manifests declare `"engines": {"node": ">=24"}`
and CI pins them. Node 18 does not build the web app.

```bash
# 1. web app (offline; copies the WASM automatically)
cd apps/web && npm install && npm run dev              # http://localhost:5173

# 2. API
cd services/api && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn aec_api.main:app --reload       # http://localhost:8000

# 3. convert an IFC to Fragments (the Node converter)
node services/converter/src/cli.mjs model.ifc model.frag

# 4. data exports / drawings from the CLI
cd services/data && pip install -r requirements.txt
PYTHONPATH=src python -m aec_data.cli qto model.ifc qto.xlsx
```

Running the tests:

```bash
cd apps/web && npm run typecheck && npm run lint && npx vitest run
```

```bash
cd services/api && PYTHONPATH=src .venv/Scripts/python.exe run_tests.py
```

The backend suite must be run **from `services/api`**. From the repo root it exits 127 and reports
"0 failures", which is indistinguishable from a pass. There is no `pytest` entry point; `run_tests.py`
is the runner.

## Your first project

1. **Open the app** and take the first-run picker. An empty install offers a way in rather than an empty
   screen: load a sample project, or start a new model.
2. **Load a sample.** Samples ship as **`.mass` containers** — one file holding the geometry *and* every
   project table, so a sample opens as a project, not as meshes to look at. See
   [the `.mass` format](mass-format.md).
3. **Look at the vitals strip** along the bottom: LOD, area, $/ft², float, IRR, health. Those six
   numbers are computed from the one model and follow you into every room, so no two rooms can quote
   different figures. A value it cannot compute shows **`—` with its reason** — never a misleading `0`.
4. **Click an element.** Properties dock beside it. Every element is addressed by its IFC **GlobalId**,
   which is why a pin, an RFI and a cost line can all point at the same wall and still agree after you
   edit the model.
5. **Move between rooms.** The seven room tabs are the primary navigation and they are the same seven
   for everyone — see [the rooms](user-guide/rooms.md).

To start from nothing instead: **New model** gives you a blank IFC with levels and a grid datum, and the
**Draft** tools draw real IFC walls, columns and slabs from there.
See [authoring](user-guide/authoring.md).

## Where to go next

- **[User guide](user-guide/)** — the detailed tour, room by room.
- **[Walkthrough](walkthrough.md)** — if you would rather be shown than read.
- **[Authoring a module](authoring-modules.md)** — add your own record type with a JSON file.
- **[Troubleshooting](user-guide/troubleshooting.md)** — when something does not work.

## If it does not work

Two failures account for most first runs:

**A blank or stalled viewer.** Almost always the Node version. `node -v` must report 24 or later; v18
breaks the build in ways that surface as a blank panel rather than an error. Check this before
debugging anything else.

**The app loads but every panel is empty.** The API is not reachable. `curl http://localhost:8000/health`
— a `000` means the process is not running, and a dying dev server imitates a product bug almost
perfectly. Confirm the backend is alive before reading the frontend.

More in [troubleshooting](user-guide/troubleshooting.md).
