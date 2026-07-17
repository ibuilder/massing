---
name: backend-tests
description: How to run and add Python tests in the Massing API/data services. Invoke when writing or running backend tests, or debugging a CI test-gate failure. Covers the run_tests.py runner, the manifest guard, per-test env isolation, DB-lock cleanup, and the two idioms (DB-backed vs engine/IFC).
---

# Massing backend tests

There is **no pytest**. Tests are self-contained `test_*.py` scripts in `services/api/` that spin up their own `TestClient`, assert, print a one-line summary, and exit non-zero on failure.

## Run
```
cd services/api
PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe -X utf8 run_tests.py     # whole suite (~40 min)
PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe -X utf8 test_<name>.py    # one test
```
Use `-X utf8` — some tests print `→`/`²`/`³` and crash on the default Windows cp1252 console (a false failure; CI uses utf-8).

## The manifest guard — REGISTER NEW TESTS
`run_tests.py` has a hand-maintained `TESTS` list and a `_manifest_guard()` that **fails the whole run** if any `test_*.py` on disk isn't in the list. After adding `test_foo.py`, add `"test_foo"` to the `TESTS` list or CI fails before running anything.

## Two test idioms
- **DB-backed API test**: set `os.environ["DATABASE_URL"]`, `STORAGE_DIR`, and (if it uploads a source IFC) `IFC_DIR` — all to `./test_*`-prefixed local paths (gitignored). `os.environ.pop("AEC_RBAC", None)`. Use `TestClient(app)` + `X-User` header. Upload a model via `POST /projects/{pid}/source-ifc?publish=false`.
- **Engine/IFC test**: prepend `../data/src` to `sys.path`, build a model with `aec_data.massing.generate_blank_ifc` + `aec_data.edit.*`, and assert on `aec_data`/`aec_api` engine functions directly (no DB needed).

## Gotchas
- **Local DB lock**: a killed test can leave `test_*.db` locked ("Device or resource busy"). Clean `rm -f ./test_<name>.db; rm -rf ./test_storage_<name> ./test_ifc_<name>` before re-running; if truly stuck, run a throwaway copy with a different db name to verify logic (CI runs clean).
- **`edit_history` sidecar**: tests that author edits leave state under `STORAGE_DIR`; clean it between local runs (run_tests.py does this per-test).
- **Infinite SSE endpoints HANG under TestClient** (`c.stream` + `iter_lines` never returns). Test the payload/signature logic, not the live stream.
- **`app.routes` introspection is unreliable** for included-router paths — assert via a real `TestClient` call instead.
- **CI ruff runs from `services/api`** with its `ruff.toml` (isort). See the `ship-release` skill.

See memory: `backend-test-runner`, `ruff-ci-config-gotcha`.
