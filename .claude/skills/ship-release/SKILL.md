---
name: ship-release
description: The Massing release discipline — how to ship a verified, CI-green version-numbered release direct to main. Invoke whenever finishing a shippable change (feature, fix, doc). Covers version bump (both files), CHANGELOG/roadmap notes, the ruff/lint CI gotchas, tag, push, and CI/CodeQL verification.
---

# Ship a Massing release

> Standing directions for this repo: [docs/roadmap-directions.md](../../../docs/roadmap-directions.md). Read those first.

`main` is unprotected and ships version-numbered releases via **direct commits** (no PR gate). Each shippable change is its own release. Follow this exactly.

## 1. Verify before you ship
- **Backend (services/api, services/data):** run the affected `test_*.py` (see the `backend-tests` skill) and **ruff exactly as CI does**:
  ```
  cd services/api && python -m ruff check src/ ../data/src/
  ```
  A file-level `ruff check <file>` from elsewhere does NOT pick up `services/api/ruff.toml` (isort/I001) and gives false "passed". Prefer `ruff check --fix` to auto-sort imports; put third-party imports in their own group after stdlib.
- **Web (apps/web):** `export PATH="/c/Program Files/nodejs:$PATH"` then `npm run typecheck && npm run lint && npm run build` (Node 24; Node 18 breaks the build). Run `npx vitest run <path>` if unit tests cover the change.
- **Frontend UI:** the dev-preview geometry loader stalls at "preparing geometry", so verify rail UI via the `verify-frontend` skill (force `buildToolsPanel` by dispatching `aec:persona`), and flag any flow you couldn't exercise end-to-end.

## 2. Bump the version — THREE files, and the third is not edited by hand
```
git fetch origin --quiet          # avoid the version race (a background release may have taken the next number)
sed -i 's/"version": "0.3.X"/"version": "0.3.Y"/' apps/web/package.json apps/web/src-tauri/tauri.conf.json
cd apps/web && npm install --package-lock-only --ignore-scripts && cd -   # re-syncs package-lock.json
```
**`package-lock.json` carries the version too** — twice, at the root and under
`packages["apps/web"]` — and `versionConsistency.test.ts` asserts all of them agree. This step said
"BOTH files" until 2026-07-29, when a release ran the two `sed`s and went red on a lock nobody had
mentioned. Regenerating the lock is the fix rather than a third `sed`: hand-editing it would sync the
number while leaving whatever else the bump touched stale.

Nothing else notices this drift, which is why it needs a gate rather than care — `npm ci` compares
dependency *edges*, not version fields; the build never reads the lock's version; and a regenerated
lock silently re-syncs, so the mismatch exists only in the window where it can ship.

Confirm `origin/main` is where you branched (`git log origin/main --oneline -1`). If it advanced, rebase and bump to the next free number.

## 3. CHANGELOG + roadmap
- Prepend a `## vX.Y.Z — <title>` entry to `CHANGELOG.md` (newest at top).
- Add a `✅ … SHIPPED vX.Y.Z` note to the relevant `docs/roadmap.md` item.
- Keep competitor names OUT of shipped docs; interop names (Revit, Bonsai, Procore) are fine.

## 4. Commit, push, tag — but never onto a red main
Commit with the trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

**First check that main is green.** Step 1 verifies *your* commit; it says nothing about the state of
main you are appending to. On 2026-07-31 main went red at 06:12 from an unindexed `docs/internal/`
file, and over the next hour three further commits landed on top — including a **cut and tagged
release** — because each session had verified its own work and none asked about the build. The gate
fired correctly within three minutes. Nobody looked. There is a standing directive to query the CodeQL
alerts API after every push and it was followed every time; there was no equivalent for CI, so the
security scan got checked and the build did not.

```
gh run list --branch main --limit 3 --json headSha,status,conclusion   --jq '.[]|"[\(if .status != "completed" then "RUNNING" else .conclusion end)]  \(.headSha[0:8])"'
```
**Branch on `status`, never on whether `conclusion` looks empty.** A running job has `conclusion` as
the empty **string** — truthy in jq — so the obvious `.conclusion // "pending"` never fires and the
field prints blank. A blank reads as "nothing to worry about", so a pending gate becomes an invisible
one. `status` is the field that actually states whether the run finished; read that.

Two sessions wrote the `//` form independently the day this section was added, one of them into memory
as the fix, and it had already printed blank rows that were read as "still running" from context
rather than noticed as a filter failure.

Related trap, same shape: **`gh --jq` does not accept `--arg`** — it exits with `unknown flag: --arg`
on stderr and prints nothing on stdout. Under a habit of skimming stdout that reads as a clean result.
Probe any filter before you loop on it, and prefer piping the JSON to a real interpreter that can be
made to print "not a verdict" rather than falling through to a reassuring default.

A red or pending main is not automatically a blocker — read it and decide. But **do not tag onto one**:
a tag is the thing that gets published, downloaded and rolled back, and it is the one step here that is
awkward to undo. If main is red, fix or wait; if it is pending, either wait for it or push without
tagging and tag once it lands.

**And tag the commit you actually verified.** The green-main check above answers "is the trunk
healthy"; this one answers "is the thing I am about to publish the thing I tested". They are different
questions and a release can fail the second while passing the first.

Concretely, v0.3.813: the release commit was prepared at 06:55 and three commits landed behind it over
the next four minutes — two of them **money fixes** (a fractional renovation pace that renovated
nothing; a half-month downtime rounded to zero). Tagging the release commit would have shipped a
version missing them. Tagging `main` would have shipped a CHANGELOG that did not mention them; the
entry was grepped for "fractional", "rounding" and "0.5" and returned zero hits. Neither option was
correct without editing first — the entry was amended, then main was tagged.

So immediately before `git tag`:

```
git fetch origin --quiet
git rev-parse HEAD origin/main            # must match — if not, you are tagging a stale commit
git log --oneline <release-commit>..origin/main   # must be EMPTY, or the CHANGELOG is already wrong
```

If commits have landed, do not tag either end. Amend the entry to cover them, commit that, and tag the
result. A tag is the one artefact here that gets published and downloaded, so it is the one place
where "close enough to what I verified" is not close enough.

Then, guarding against a race:
```
if [ "$(git rev-parse origin/main)" = "$(git rev-parse HEAD~1)" ]; then
  git push origin HEAD:main && git tag vX.Y.Z && git push origin vX.Y.Z
else echo "RACE — rebase + rebump"; fi
```

**Never merge or rebase inside the commit command, and re-check the triple after any that you do.**
The `RACE` branch above rebases onto whatever landed first — which is how v0.3.791 shipped red. Two
sessions released concurrently; the merge took the **manifest from one and the lock from the other**,
and git merged it cleanly because they are different files. No single edit was wrong, and the session
had run a green suite — on the tree *before* the merge. `versionConsistency.test.ts` caught it in CI,
one release later.

So after any rebase/merge, and always immediately before pushing:
```
node -e 'const a=require("./apps/web/package.json").version,
 b=require("./package-lock.json").packages["apps/web"].version,
 c=require("./apps/web/src-tauri/tauri.conf.json").version;
 console.log(a,b,c); if(new Set([a,b,c]).size>1){console.error("VERSION TRIPLE DISAGREES");process.exit(1)}'
```
The lock is the **root workspace lock** (`./package-lock.json`, keyed `packages["apps/web"]`) — there
is no `apps/web/package-lock.json`, and a check that reads that path returns empty and "passes".

The general rule this is one instance of: **verify what you are shipping, not what you happen to have.**
A suite run before a merge, or a typecheck against a working tree that still holds unstaged fixes,
measures a tree that is not the commit. To verify a commit, verify the commit.

## 5. Verify CI + CodeQL
- A "CI" workflow run showing `success` does NOT mean the **API test gate** ruff step passed, or that CodeQL is clean. Check both.
- After each push run the `security-monitoring` skill's CodeQL check (open **alerts**, not run status).
- The API test gate is slow (~15–20 min); each commit is independently verified locally, so keep shipping. Watch the first release carrying a new test file to confirm it's green in CI.

See memory: `main-fast-release-cadence`, `ruff-ci-config-gotcha`, `backend-test-runner`, `codeql-monitoring`, `web-build-needs-node-20`.
