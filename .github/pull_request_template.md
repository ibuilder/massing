# What & why

<!-- One paragraph: what changes, and the problem it solves. Link the roadmap item / issue if any. -->

## Checklist (mirrors CONTRIBUTING.md)

- [ ] Backend: `cd services/api && python -m ruff check src/ ../data/src/` clean
- [ ] Backend: affected `test_*.py` pass (new tests registered in `run_tests.py` TESTS)
- [ ] Web: `npm run typecheck && npm run lint && npm run build` clean (Node 20)
- [ ] No import cycles introduced (`test_import_cycles.py` / `no-import-cycles.test.ts` pass)
- [ ] `CHANGELOG.md` entry added (newest at top); roadmap item updated if applicable
- [ ] Version bumped in **both** `apps/web/package.json` and `apps/web/src-tauri/tauri.conf.json` (release PRs)
- [ ] No secrets, no competitor names in shipped docs (interop names OK)
