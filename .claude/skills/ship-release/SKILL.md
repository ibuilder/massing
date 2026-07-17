---
name: ship-release
description: The Massing release discipline — how to ship a verified, CI-green version-numbered release direct to main. Invoke whenever finishing a shippable change (feature, fix, doc). Covers version bump (both files), CHANGELOG/roadmap notes, the ruff/lint CI gotchas, tag, push, and CI/CodeQL verification.
---

# Ship a Massing release

`main` is unprotected and ships version-numbered releases via **direct commits** (no PR gate). Each shippable change is its own release. Follow this exactly.

## 1. Verify before you ship
- **Backend (services/api, services/data):** run the affected `test_*.py` (see the `backend-tests` skill) and **ruff exactly as CI does**:
  ```
  cd services/api && python -m ruff check src/ ../data/src/
  ```
  A file-level `ruff check <file>` from elsewhere does NOT pick up `services/api/ruff.toml` (isort/I001) and gives false "passed". Prefer `ruff check --fix` to auto-sort imports; put third-party imports in their own group after stdlib.
- **Web (apps/web):** `export PATH="/c/Program Files/nodejs:$PATH"` then `npm run typecheck && npm run lint && npm run build` (Node 20; Node 18 breaks the build). Run `npx vitest run <path>` if unit tests cover the change.
- **Frontend UI:** the dev-preview geometry loader stalls at "preparing geometry", so verify rail UI via the `verify-frontend` skill (force `buildToolsPanel` by dispatching `aec:persona`), and flag any flow you couldn't exercise end-to-end.

## 2. Bump the version — BOTH files
```
git fetch origin --quiet          # avoid the version race (a background release may have taken the next number)
sed -i 's/"version": "0.3.X"/"version": "0.3.Y"/' apps/web/package.json apps/web/src-tauri/tauri.conf.json
```
Confirm `origin/main` is where you branched (`git log origin/main --oneline -1`). If it advanced, rebase and bump to the next free number.

## 3. CHANGELOG + roadmap
- Prepend a `## vX.Y.Z — <title>` entry to `CHANGELOG.md` (newest at top).
- Add a `✅ … SHIPPED vX.Y.Z` note to the relevant `docs/roadmap.md` item.
- Keep competitor names OUT of shipped docs; interop names (Revit, Bonsai, Procore) are fine.

## 4. Commit, push, tag
Commit with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Then, guarding against a race:
```
if [ "$(git rev-parse origin/main)" = "$(git rev-parse HEAD~1)" ]; then
  git push origin HEAD:main && git tag vX.Y.Z && git push origin vX.Y.Z
else echo "RACE — rebase + rebump"; fi
```

## 5. Verify CI + CodeQL
- A "CI" workflow run showing `success` does NOT mean the **API test gate** ruff step passed, or that CodeQL is clean. Check both.
- After each push run the `security-monitoring` skill's CodeQL check (open **alerts**, not run status).
- The API test gate is slow (~15–20 min); each commit is independently verified locally, so keep shipping. Watch the first release carrying a new test file to confirm it's green in CI.

See memory: `main-fast-release-cadence`, `ruff-ci-config-gotcha`, `backend-test-runner`, `codeql-monitoring`, `web-build-needs-node-20`.
