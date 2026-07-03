# Contributing

Thanks for your interest — this is an open, IFC-native AEC platform and contributions are welcome,
whether it's a bug report, a module, a viewer tool, or docs.

## Ground rules
- **IFC is the source of truth.** Reference model elements by IFC `GlobalId` (GUID), never by
  transient viewer IDs. Keep geometry (`.frag`) and data (the API) separate.
- **Pins / RFIs / punchlist follow the BCF model** so they round-trip with other BIM tools.
- The web viewer must run **fully offline** (local WASM, self-hosted tiles).
- Pin a compatible **`@thatopen/components` ↔ `@thatopen/fragments` ↔ `three`** version pair.

## Dev setup
```bash
# full stack (web + API + Python data service + MinIO/Postgres)
docker compose --profile full up --build      # web :8080 · api :8000

# or run pieces directly
cd apps/web && npm install && npm run dev      # vite dev server (:5173)
```

## Before you open a PR
Run the gates locally — CI runs the same:
```bash
cd services/api && python -m ruff check src/ ../data/src/   # static-analysis gate (dead code + defects)
python services/api/run_tests.py               # API suites
cd services/data && PYTHONPATH=src ./.venv/Scripts/python test_massing.py   # (+ test_families, test_analysis)
cd apps/web && npm run typecheck && npm run test && npm run build
python -m bandit -q -r services/api/src services/data/src -ll -ii   # security scan (before shipping)
```
- Keep changes focused; match the surrounding code's style and comment density.
- Add/extend a test for behavior changes (the suites are plain scripts — easy to extend).
- Update `CHANGELOG.md` and, if relevant, `docs/roadmap.md`.

## Reporting bugs / ideas
Use **Issues** for bugs (include the IFC/model if you can share it) and **Discussions** for
questions, ideas, and "is this possible?" — both are watched.

## License
By contributing, you agree your contributions are licensed under the repository's `LICENSE`.
