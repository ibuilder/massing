# AGENTS.md

## Cursor Cloud specific instructions

This section is for Cloud Agents running in an environment where the startup **update script** has
already installed dependencies. It captures the non-obvious bits of running Massing here; standard
commands and product detail live in the README, `docs/getting-started.md`, and the `.claude/skills/`.

### What the update script already did
- Installed the web workspace deps (`npm install`, which also runs `apps/web` `predev` WASM copy).
- Ensured **Node 24** is installed via `nvm` (the repo requires `node >=24`; Node 18 breaks the web build).
- Installed the Python API deps into the **user site** (`~/.local`): `services/api/requirements.lock`
  (runtime, hash-pinned, py3.12/Linux — matches prod) and `services/api/requirements-dev.txt` (test/lint:
  httpx, ruff, bandit, pytest, coverage, DracoPy). `services/data`'s deps are a strict subset of the lock,
  so there is no separate install for it.

### Services (all run from source in dev)
| Service | Path | Dev run command | Port |
| --- | --- | --- | --- |
| Web (Vite + TS viewer/authoring UI) | `apps/web` | `npm run dev` | 5173 |
| API (FastAPI; bundles the `services/data` ifcopenshell library) | `services/api` | `uvicorn aec_api.main:app --reload` | 8000 |

Postgres + MinIO are **not** needed for dev: the API defaults to **SQLite** (`sqlite:///./aec.db`) and
**local filesystem storage**. Docker/`docker compose --profile full` is the self-host path, not required
here. The `converter` (Node IFC→Fragments) is job-style/optional — the API reconverts in-process on publish.

### Node 24 gotcha (important)
`/exec-daemon/node` (v22) sits first on `PATH` and **shadows** nvm's Node 24 even after `nvm use 24`.
Before any web command, put Node 24 first explicitly:
```bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; export PATH="$(nvm which 24 | xargs dirname):$PATH"
node -v   # must print v24.x
```

### Running the two dev servers
Start each in its own long-lived terminal (e.g. tmux). The web app in dev calls the API at
`http://localhost:8000` (see `apps/web/src/api/httpCore.ts`); CORS default already allows the Vite origin.

API — must set a **writable local `IFC_DIR`/`STORAGE_DIR`**, otherwise authoring endpoints 500 with
`PermissionError: /app` (the defaults are the in-container paths `/app/ifc`, `./storage`):
```bash
cd services/api
export PYTHONPATH="src:../data/src"          # both are required; ':' separator on Linux
export PATH="$HOME/.local/bin:$PATH"         # uvicorn/ruff console scripts live in ~/.local/bin
export IFC_DIR="$PWD/.devdata/ifc" STORAGE_DIR="$PWD/.devdata/storage"
mkdir -p "$IFC_DIR" "$STORAGE_DIR"
python -m uvicorn aec_api.main:app --host 0.0.0.0 --port 8000 --reload
```
Web (Node 24 activated as above): `cd apps/web && npm run dev`.

`AEC_RBAC` defaults to `0` in dev, so writes work without auth (the web app also sends no user). Health
check: `curl http://localhost:8000/health` → `{"status":"ok"}`.

### Lint / test / build
- Web (Node 24): `cd apps/web && npm run typecheck && npm run lint && npx vitest run` (build: `npm run build`).
- API lint (exactly as CI): `cd services/api && python -m ruff check src/ ../data/src/` — **not** `ruff check .`
  (the `test_*.py` files carry intentional late imports and would report isort noise).
- API tests: there is **no pytest entry point**. The runner is `run_tests.py` and must run **from
  `services/api`** (`PYTHONPATH="src:../data/src" PYTHONUTF8=1 python run_tests.py`). Run a single test the
  same way: `PYTHONPATH="src:../data/src" python test_<name>.py`. See `.claude/skills/backend-tests`.

### Hello-world (verified working)
New model → 3D authoring: welcome screen → **Start a project / New model from scratch** → pick a template
(e.g. *Office bay*) → the API authors a real IFC, reconverts to Fragments, and the viewer loads it; clicking
an element shows its IFC `GlobalId` + property sets. Backend equivalent:
`POST /projects` then `POST /projects/{id}/model/blank`, then poll `GET /projects/{id}/publish/status`.
