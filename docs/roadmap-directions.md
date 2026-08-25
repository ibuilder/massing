# Roadmap directions — read this before the roadmap

**This file is the standing directions. [`roadmap.md`](roadmap.md) is only the list of work.**

Everything here was learned the expensive way on this repo — most of it from a defect that shipped, a
gate that passed while measuring nothing, or two agents overwriting each other. It is separated from the
roadmap so the roadmap can stay a clean list of *what to build*, and so these rules do not have to be
rediscovered by every session that opens it.

**Order of operations for any agent:** these directions → the lane table → an item from the roadmap.

---

## 1. Non-negotiables

Violating one of these is a defect regardless of how well the code works.

| | |
|---|---|
| **IFC is the source of truth** | Reference elements by **GlobalId (GUID)**, never a transient viewer id. |
| **Never parse full IFC in the browser** | Pre-convert to Fragments server-side. Geometry streams as `.frag`; data comes from the API. |
| **The viewer runs fully offline** | Local WASM, self-hosted tiles. No runtime network dependency. |
| **Licences: MIT / BSD / Apache / ISC / CC0-1.0** (and the other permissive names the classifier already accepts: Unlicense, Zlib, BSL-1.0 / Boost). **No GPL, no AGPL, no PolyForm/noncommercial, no BUSL.** | Code and content. CC0 is a public-domain dedication, strictly more permissive than MIT; the families shelf already shipped it. `BSL-1.0` is Boost (permitted); `BUSL` is Business Source (not). |
| **New dependencies need explicit user approval** | Version *bumps* of existing deps are routine; a new package is not. |
| **`@thatopen/components` + `@thatopen/fragments` are a pinned compatible pair** | `ties.test.ts` enforces it. A drifted `web-ifc` renders fine and mis-parses geometry. |
| **No competitor product names** in README / CHANGELOG / docs / commits | Interop and format names (IFC, BCF, COBie, Revit, Bonsai) are fine — a competitor *platform* name is not. Describe rival capabilities generically. |
| **The repo is PUBLIC** | Audit and security docs stay redacted. Working notes go in `docs/internal/`. |
| **Secrets live in operator config only** | Never in the repo, never in memory, never in a commit message. |

---

## 2. Verify, don't recall

Long sessions drift. The countermeasure is not a better memory, it is **a check that fails**.

- **If a rule matters, write it as a test.** Prose drifts — including the prose in `CLAUDE.md`, which has
  been wrong about the Node version in three different ways.
- **State what you CHECKED, not what you concluded.** "Read all three `module.json` files; 0 GUID fields
  across all three" is falsifiable. "ITP/NCR already exists" is not.
- **Cite the grade with the conclusion.** "451/452, the one failure passes standalone twice and touches
  none of my modules" is a usable claim. "Suite green" is not.
- **Refuse rather than invent.** A missing value gets chased; a confidently wrong one gets cited. When
  the honest answer is "I cannot tell you", say that — and where a system must return something, return
  an explicit `unavailable` **with its reason** rather than a plausible default.

### Premise-check before building

**Six of seven roadmap premises checked on one day were wrong**, and the count has kept rising — the
running total is now over a dozen items that turned out to be mostly built. Before starting an item:

1. Grep for the capability. It very often exists.
2. If it exists, ask whether the gap is *reach* (nothing calls it) rather than *capability*.
3. File the correction into the roadmap rather than deleting the entry — a "checked, already exists"
   line stops the next agent re-running the check.

### Measurement traps that have actually bitten

- **A count from a different reader answers a different question.** A whole-file regex said 455/455
  registered; the runner's own guard said five unregistered. Use the reader that *decides*.
- **`grep -l` answers "does this file contain it", never "where".** A gap-check grepped for the K-1
  code, got a **correct hit** on `capital.py`, then read one occurrence — a disclaimer at line 90 — and
  concluded the feature was absent. `grep -n` on the same pattern showed `k1_pack` at line 67
  immediately. **A correct hit, sampled wrongly, produces a confident absence** — worse than a miss,
  because the tool appeared to agree. Use `-n` and read the hits, or you are searching your sample
  rather than the file.
- **Search every tree, not the one you expect.** A Band 4 probe reported "no module" for
  `R23-CONSTRAINTS` because it looked only in `services/api`; the module is in `services/data` and had
  a caller the same session had already read. Scope a probe to the capability, not to a directory.
- **On this repo, "already there" and "landed an hour ago" are indistinguishable** without checking the
  file's own `git log`. All sessions share one identity, so a sibling's fresh work reads exactly like
  history — one session re-checked a gap it had itself caused to be fixed and reported it as never
  having been one.
- **`grep -i` matches substrings.** `EIR` matches "their"; `MIDP` matches "midpoint". Word-bound it.
- **Long-line diffs lie.** `run_tests.py` packs ~200 entries per line, so one change re-renders the whole
  line. Ask for content (`git show <ref>:file | grep -c`), never a diff.
- **Specify a fixture by the property under test, never by a proxy for it.** "Convert one of the 50 MB
  `samples/*.ifc`" to get a big model for a *picking* benchmark was wrong and **inverted**: file size is
  anti-correlated with element count here, because those files are large as *text*, not as geometry.
  `basichouse.ifc` is 50.3 MB and holds **154** elements; `vertical_farm.ifc` is 1.5 MB and holds
  **1,840**. Converting the 50 MB file produced a 3.6 MB fragment set — exactly the size already on
  disk, so following the instruction reproduced the starting position. Picking scales with *elements*,
  so the fixture must be specified in elements. The tell: the instruction named a unit nobody was
  actually testing against.
- **A benchmark must assert that it measured something.** A picking benchmark returned a confident
  **p50 of 135 ms with `hits: 0`** — the browser pane was collapsed, `clientWidth` was 0, and every ray
  missed. That number would have *justified* the very timeout it was sent to test. Three sibling
  instrument bugs in the same run each produced a plausible result too: `byteLength` read **0** after
  `core.load` detached the ArrayBuffer to a worker ("fetched nothing, loaded fine"); canvas-relative
  coordinates hit 0/12 because the app passes viewport `clientX/clientY` and the canvas is offset; and
  the camera sat at its default. **Timings and counts are produced just as readily by a broken setup as
  a working one** — so assert on the evidence that the instrument engaged (`hits > 0`, bytes > 0), never
  on the output alone. Same shape as an all-zeros geometry import that "succeeds".
- **Report the distribution, not a mean.** p50 4 ms with p99 400 ms is a different verdict from a flat
  4 ms, and only the tail decides whether a fallback is justified. Split code paths that differ (a
  raycast *miss* was ~5× cheaper than a hit; a mean hid it), and always attach the scale the number was
  taken at — an unattached latency figure drifts to whatever claim wants support.
- **Never assemble a measurement from several reads of a live system.** Take one snapshot and derive.
- **`$?` after a pipe is the pipe's status.** Read exit codes directly.
- **"No test files found" is not a pass.** Neither is a `FAIL` with no traceback.

---

## 3. Working in a shared clone — seven hazards

Several agent sessions use **one checkout, one index, one branch set**. Every form below has happened.

| # | shared thing | failure |
|---|---|---|
| 1 | working tree | a stray `cd` or `add -A` stages someone else's files |
| 2 | **index** | a plain `git commit` sweeps someone else's *staged* files |
| 3 | **branch** | a plain `git push` publishes someone else's *commits* |
| 4 | **same file, different hunks** | staging by name still takes every change in that file |
| 5 | **`git commit` binds to whatever branch HEAD is on** | a session that never touched a branch can author its tip |
| 6 | **another session's uncommitted file fails your test run** | gates that read repo files from disk read whatever the checkout holds |
| 7 | **`.claude/worktrees/` is inside the repo** | a test runner started at the repo root collects **other sessions' worktrees** as if they were your source |

Hazard 7 is the only one that manufactures *failures* rather than hiding them, which makes it the
easiest to act on wrongly. `vitest run` from the repo root reported **152 failed files / 756 failed
tests** — every one of them another session's working copy. A positional path filter does **not** save
you: `.claude/worktrees/<name>/apps/web/src/…` contains `apps/web/src` as a substring, so the filter
matches the worktrees too. Run the workspace command (§5), which is scoped by config and is what CI runs.
**Before believing a mass failure, read the failing paths** — the fix is the invocation, not the code.

**Rules that follow:**

- **Stage by name, never `-a` / `-A`.** Then read `git show --stat` before pushing.
- **Push a SHA, not `HEAD`:** `git push origin <sha>:main`.
- **`git rev-parse --abbrev-ref HEAD` before every commit**, `git log --oneline origin/main..HEAD` before
  every push.
- **A file read does not name its object.** `cat`, `grep`, `git status` and the Read tool all answer
  about the *tree*. When the claim is about the branch, read `git show origin/main:<path>`.
- **Judge a commit by its file list, not its author.** All sessions share one git identity, so history
  cannot attribute anything.
- **Build release commits from `origin/main` blobs via a temp index** when the tree is dirty — it is
  immune to hazards 1, 4, 5 and 6 at once.
- **Before believing a test failure is yours**, run `git status <the file the test reads>`.
- **Uncommitted work is invisible to every git-based check.** A branch that exists only on disk is one
  `checkout` from gone — 419 lines were rescued that way once, and only because someone looked.

### The structural fix: don't share the tree at all

Every rule above is a way to *survive* a shared checkout. The cheaper answer is to stop sharing one,
and the reason nobody does is a cost that turns out not to exist.

Isolation looks expensive — a full environment is **~1.3 GB** (`node_modules` 478M + 15M, `.venv`
795M) and the disk sits at **97%**. But a worktree does not need its own copy of any of it. Measured
2026-07-31: **ten worktrees exist and not one has its own `node_modules` or `.venv`.**

- **Web:** an *in-repo* worktree resolves the root modules by upward lookup — verified from
  `.claude/worktrees/prov/apps/web`, `require.resolve('vitest')` →
  `C:\Server\modelmaker\node_modules\vitest`.
- **Backend:** run the **main clone's interpreter** with `PYTHONPATH` pointed at the *worktree's*
  sources. A full 473-suite gate ran that way for v0.3.809.

So the marginal cost of an isolated session is a source checkout — tens of MB, not gigabytes.

**The convention:**

1. **Work in `.claude/worktrees/<lane>`. The main clone is reserved for releases** — one owner for
   HEAD, so hazards 1, 2, 3 and 5 have no shared object to collide in.
2. **In-repo worktrees only.** An out-of-repo worktree (e.g. under scratchpad) is *outside* the
   upward-resolution path and gets **no `node_modules`** — a web suite there fails with a confusing
   missing-module error. The v0.3.809 gate only worked out-of-repo because the backend needs
   `PYTHONPATH`, not `node_modules`.
3. **Distinct dev-server ports per session.** `:8093` and `:5173` are singletons; tests are already
   headless (happy-dom, no browser) so only a live preview needs one.
4. **Branch from `origin/main`, never `main`.** In a worktree `git checkout main` **cannot succeed** —
   main is checked out in the primary clone and git refuses to have one branch in two working trees.
   That refusal is one line on stderr and nothing else changes, so a `2>/dev/null` turns it into a
   silent no-op and the next command inherits a state nobody chose. `git checkout -b <new> main` then
   works fine and resolves `main` as a **ref**, pointing wherever the local ref last pointed — which
   in a worktree is wherever it was when the session began.

   Measured 2026-08-07: a branch created that way was **140 commits stale** and every command reported
   success. It was caught only because `app.ts` measured 5,064 lines against a ratchet pinned at 3,751,
   and a ratchet that only revises down cannot sit below the file it measures. **The contradiction
   between two numbers was the entire signal.**

   Two generalisations worth more than the command: **never `2>/dev/null` a state-changing git
   command** — suppressing stderr on a query is untidy, suppressing it on `checkout` converts a
   refusal into a silent no-op; and **a ref name is not a ref** — `main` and `origin/main` are
   different objects that read identically in a command line.

        git fetch -q origin main && git checkout -q -b <branch> origin/main

    git worktree add .claude/worktrees/<lane> -b <branch> origin/main
    cd .claude/worktrees/<lane>
    # web:     npm run test --workspace apps/web      (resolves the root node_modules)
    # backend: PYTHONPATH="<wt>/services/api/src;<wt>/services/data/src" \
    #          /c/Server/modelmaker/services/api/.venv/Scripts/python.exe run_tests.py

**This does not change where logic runs.** The platform stays server-side-first by non-negotiable —
the server pre-converts IFC to fragments, the API serves data, the viewer renders. Worktree isolation
is a *development* boundary and is orthogonal to that.

**Still true in a worktree:** hazard 7 (a root-scoped runner collects every worktree — use the
workspace command), and the temp-index pattern remains the right way to land a commit when you are
*not* in your own tree.

### Two races the gates do NOT close, named so they are not assumed away

**1. A migration fork is invisible to both branches.** On 2026-08-07 two PRs each added a migration
chained off the same `down_revision`. **Both were individually green and both were correct** — each
branch had exactly one head; the second head exists only in the *union*. Main then could not
`alembic upgrade head` at all.

Detection already exists (`services/api/test_alembic_migrations.py` calls `command.upgrade(cfg, "head")`,
which raises `Multiple head revisions are present`), and CI runs on `pull_request`, so it tests the
**merge result**. What no gate can do is re-test PR B when PR A lands afterwards: B's green was
computed against a merge result that predates A, and it stays green and stays mergeable.

`required_status_checks.strict: true` would force every branch to be up to date before merging and
would catch it — **the user chose `strict: false` on 2026-08-07, deliberately**, because with three or
more sessions merging it means near-continuous rebasing and that defeats the release cadence. So the
risk is accepted, not solved.

**The mitigation that costs nothing is coordination, because no local check can see unpushed work:**
a branch carrying a migration **announces its parent revision when it opens**, so the next one chains
onto it rather than onto the shared ancestor.

**2. `enforce_admins: false` makes the protection advisory for whoever can bypass it.** Direct pushes
to `main` still work, which is load-bearing for the cadence. **The ability to bypass a gate is not
permission to** — hold yourself to it.

### Resolving a conflict

When a conflict is **additive on both sides**, "keep both" is right about the semantics and unreliable
about the **syntax** — the hunk boundary is chosen by diff, not by the language, so it can land
mid-construct. A resolution once passed every marker grep and failed to compile.

**Resolve, then compile.** A presence check is necessary and not sufficient.

### Undoing an edit — `checkout --` restores from a STALE HEAD here

`git checkout -- <file>` restores from **HEAD**, not from "before my last change", so it discards every
uncommitted edit to that file rather than the one you meant to undo. That is the generic hazard, and
in this clone it is worse: under the temp-index release pattern **local HEAD never moves**, so HEAD is
routinely many releases behind `origin/main`. The file you get back may be far older than anything you
were working on, and `git status` will look clean afterwards.

**Undo from a copy you made, not from git.** This applies especially to mutation-testing, where the
whole method is edit-run-restore.

The same staleness makes the working tree a poor measuring instrument. A local build, a local file
size, a local line count are all measurements *of the tree you have*, which is not the commit you are
reasoning about — a bundle budget was once set from one and landed below the artefact it gated.
**Measure in CI, or verify the tree's ref first.**

---

## 4. Lanes — how several agents work at once

The roadmap's lane table assigns every open item to exactly one lane, and lanes are **disjoint by file
path**. `apps/web/src/shell/roadmapLanes.test.ts` asserts both directions and fails on overlap.

1. **Claim a lane, not an item.** Two sessions in one lane collide; two in different lanes do not.
2. **Declare it** by message before starting.
3. **Land what you finish.** Do not leave completed work dirty in a shared tree.
4. **Version files and `CHANGELOG.md` belong to whoever holds the release**, not to the lane. Ship
   without them and let the release batch pick them up — or take the release and say so.
5. A carve-out in the lane table is written `!path`, in the same syntax the check reads. Prose
   exclusions are not boundaries.
6. **Checking the codebase is not checking the other agents.** A premise-check that reads the tree
   answers "is this built?" and cannot answer "is someone building it?" — the artefact does not exist
   anywhere the tree can see until it lands. On 2026-08-06 a lane correctly established that
   R22-PM-CONTRACTS was genuinely unbuilt, and dropped it on discovering another session had already
   committed it in a worktree. True about the repo, wrong about the work. Before starting, say so by
   message; a lane claim is cheap and a duplicated day is not.
7. **One PR per landing.** Once a PR merges, the next slice needs a fresh branch off current main.
   Pushing a continuation to a merged PR's branch produces work that is **pushed, referenced by a
   link that still resolves, and merged nowhere** — GitHub does not reopen a merged PR. This happened
   the same day, and the reason it is dangerous is that "shipped" and "stranded" render identically:
   a merged PR plus a pushed branch. It was caught only because the message itemised a line count
   that disagreed with main.

### Shared files that need a heads-up

`services/api/run_tests.py` · `services/api/src/aec_api/main.py` · `docs/roadmap.md` · `CHANGELOG.md` ·
the version triple (`apps/web/package.json`, `src-tauri/tauri.conf.json`, `package-lock.json`).

---

## 5. Testing

**Backend** — from `services/api`, never the repo root (the root exits 127 and reports "0 failures",
which reads exactly like a pass):

```
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe -X utf8 -u run_tests.py
```

**Web** — Node **24+** (`export PATH="/c/Program Files/nodejs:$PATH"`; the default `node` on PATH is v18
and breaks the build). Typecheck with `npx tsc --noEmit` from `apps/web`. For the suite, run the
workspace command — **not a bare `vitest run` from the repo root**, which collects `.claude/worktrees/`
(hazard 7 above):

```
npm run test --workspace apps/web
```

This is the CI invocation; its `include: ["src/**/*.test.ts"]` is relative to `apps/web`, so worktrees
are structurally out of reach. Note the suite environment is **happy-dom**, where `import.meta.url` has
no `file:` scheme — a test that reads source off disk must resolve from `process.cwd()` (which is
`apps/web`), the way `shell/roadmapLanes.test.ts` does, not via `fileURLToPath`.

### Announce before a full suite

**Two suites on one machine share the SQLite files and both results become worthless.** The signature is
unmistakable once seen: a `FAIL` line with **no traceback**, and the same suite passing standalone.

This has occurred at three levels — targeted tests alongside your own suite, tooling (`npm install`,
`tsc`, git merges) alongside your own suite, and suite alongside suite. **None is visible from inside
the session causing it**, so announcing is the only control that works, because it is the only one that
crosses sessions.

- Announce before starting; do not start while another is announced.
- Run nothing else while yours is running.
- Record `git rev-parse HEAD` with any suite result you intend to cite — HEAD moves under you.

### What a test must do

- **A gate must be able to fail.** Mutation-check it: break the thing it guards and watch it go red.
  A threshold set below the truth measures the threshold, not the code.
- **Assert the partition, not the presence.** "Every type is either editable or deliberately read-only,
  and none is both" catches the next type. "`percent` renders" does not.
- **Value-check money, don't range-check it.** `assert x > 0` let a 100%-wrong promote split ship.
- **Test fixtures must be in the archive.** `git ls-files <path>` before a test reads it — the question
  is never "is it on disk" but "is it in the archive a fresh clone gets". `samples/*.ifc` are ignored
  and have turned `main` red **twice**. Generate the fixture in-test from an independent implementation
  instead.
- **Assert against a reader you didn't write.** A round-trip through your own writer and reader passes
  on the wrong format.
- **A test that supplies BOTH SIDES of a seam agrees with itself no matter which side is wrong.** The
  sharpest instance: a join read three field names *no engine emits*, and all nineteen unit checks
  passed — because the fixture was invented alongside the code. It would have reported every axis
  absent on a fully populated project. The same shape produced the worst bug in three separate PRs on
  one day, at three different layers (a join, an audit trail, a ledger key). The countermeasure that
  worked each time is a test supplying **neither** side: **drive the real producer, read the real
  consumer, assert they agree.** This is the twin of the refusal rule above — ask both "which checks
  still pass if the function does nothing?" and "which still pass if the other side is wrong?"
- **A mutation proves nothing unless it APPLIED, was NOT INERT, and failed for the right reason.**
  Three failure modes, all seen the same day.
  1. **It never applied.** The run passes and reads exactly like a surviving mutant. Assert the edit
     landed; do not trust the runner's output alone.
  2. **It applied and was inert** — the mutated code does not do the job you are testing. One lane
     mutated a function that *labels* clash groups rather than *forming* them: clean pass, and it
     reads as "this gate is prose". The only tell was that the measured numbers came back
     byte-identical. **Mutate the thing that does the work, and check that the output moved.**
  3. **It broke compilation.** Goes red while telling you nothing about the assertion, which makes it
     the most flattering of the three. Keep mutants syntactically valid (`if (false && cond)` rather
     than commenting a line out), and beware that MSYS collapses `//` in a shell argument.

- **Self-test the instrument: plant a known positive and confirm it is found.** A scan that reports
  "zero problems" is indistinguishable from a scan that cannot see problems, and the second is more
  common than it sounds. The method that caught it: **inject a real instance of what you are looking
  for, in each language you claim to cover, and re-run.** If the count does not move, the clean bill
  of health is worthless. That is the technique behind mutation-checking a gate, applied to a
  one-off search — and a one-off search is exactly where nobody thinks to do it.

### Moving code without changing behaviour

- **State what you checked, not what you concluded.** Three sessions made this error on 2026-08-06 in
  three directions: "no test imports this file" became "there is no parity gate" (a source-reading
  gate existed and was stronger); "6 of 158 matched" became "the port does not work" (the reader was
  reading the wrong line); "this is unbuilt" became "nobody is building it". A checked claim can be
  refuted precisely; a concluded one can only be contradicted, which takes far longer to settle.
- **A ref is the DEFAULT; an accessor means you got lucky.** Captured state crosses an extraction
  seam three ways, and the ranking is the opposite of the intuitive one:
  1. **read-only** → pass an accessor (a getter). This is the *lucky* case, not the normal one.
  2. **read-write** → pass a mutable **ref**, ownership staying in the original scope.
  3. **neither** → pass by value, which is safe only for a `const`.

  **A getter cannot express a write.** When the moved code *assigns* to the captured binding, both
  obvious repairs are wrong in different ways: moving the declaration into the new module changes its
  **lifetime** (it may need to survive the enclosing builder re-running), and passing by value
  reintroduces the exact stale-closure bug accessors exist to prevent — silently, since it compiles.

  This was first written as an exception. It is not. **Any state a builder owns the lifecycle of will
  be written by it; only state it merely consults is read-only** — and in a closure that has grown to
  four thousand lines, most captured state is owned in one place and consulted in another. Measured
  across two consecutive extractions from the same file: the first had one read-write capture, the
  second had two of two, one of them a `??=`, which no getter can express at all.

- **Close the population by SCOPE, not by search.** Before threading a capture, enumerate its readers
  — and prefer an argument that makes the enumeration *exhaustive by construction*: a `let` declared
  inside a function, not exported, not attached to any global or object literal, **can only be read
  inside that function**, so there is nowhere else to look. That is categorically stronger than "I
  grepped every file carefully", which is the N−1-correct shape that fails on the Nth site.

  When you must grep, **match the boundary to the GRANULARITY of what you are looking for — and note
  that the two cases want opposite answers.** Written here as a flat "word-bound every pattern" on
  2026-08-06 and corrected the same day, because that advice is right for one case and silently
  disastrous for the other:

  * **Searching for an identifier** (does anything reference `discTree`?) → **word-bound it.** The
    name is the whole token, and an unbounded match invents dependencies (see below).
  * **Searching for a name FRAGMENT** (does any composite key get built by concatenation? → look for
    `key`, `cache`, `id`) → **word-bounding cannot match `cacheKey` or `cache_key`**, which are the
    likeliest real names. The filter excludes its own subject and issues a **confident clean bill of
    health**. That is what happened: 18 hits, zero findings, and the scan was worthless until it was
    self-tested with planted collisions.

  An unbounded search for `discTree` matched
  `private _discTree` in an unrelated file and read as "this variable escapes into the API client" —
  a dependency that does not exist, which would have been threaded through the seam to fix a
  non-problem. Same family as a search for `EIR` matching the word "their".
- **Prove a move was a move.** Diff the extracted body against the original range with
  `git show <ref>:<path>`, do not read it and judge. Do not re-indent — re-indenting can silently edit
  the contents of a multi-line template literal. Name every non-identical line in the PR; two out of
  1,180 with a stated reason is a good exception, and "mostly identical" is not a claim.

---

## 6. Shipping a release

One session holds the release; the others ship without version files.

1. `git fetch` and confirm nothing is mid-flight.
2. Bump **all three** version files; regenerate the lock with
   `npm install --package-lock-only --ignore-scripts`.
3. **CHANGELOG entry goes above the HIGHEST version present**, not the one you branched from —
   concurrent releases otherwise interleave with no single wrong edit.
4. Full suite green, on the **merged** tree. "Merges cleanly" ≠ "merges and passes".
5. Re-check the version triple **after** any merge or rebase.
6. Race-guard the push (`origin/main == HEAD~1`), push a SHA, then tag.
7. **Check CodeQL alerts after every push** — a green *run* is not zero alerts; query the alerts API.

---

## 7. What "done" means

An item is done when the capability is **reachable**, not when the engine exists. Seven of eleven
engines once shipped with no route at all.

- A new route needs a started app to be provable: assert over HTTP with `TestClient`, since routers
  include lazily and schema presence proves only that it is *defined*.
- A new module needs an Alembic revision.
- Ask every sprint: **what did we build that nothing calls?**
- Prefer removing a reason something is unreachable over adding another engine beside it.

---

## 8. Recording work

- Roadmap entries carry the **reasoning**, not just the title — that is what makes them re-readable in
  a month.
- When an item is finished, move it to [`roadmap-completed.md`](roadmap-completed.md) **with its text**
  if the reasoning is worth keeping; one-line it if not. **Move it in the same change that finishes
  it.** Marking ✅ and leaving it in place is the single most common defect this roadmap has: the
  2026-08-25 reconciliation archived **twenty-one** such entries, and the words *"pending archive"*
  appeared **14 times in the lane table** — the cells an agent reads to choose work. Nothing could catch them, because `roadmapLanes.test.ts` skips ✅ lines when it
  builds the open population — **a shipped item that stays put is invisible to the only check that
  reads the file.** A status glyph is a note to a reader; only the move is a change to the file.
- When an item is checked and found already built, say so in place rather than deleting it.
- When a source is reviewed and rejected, **record the reason** — the rejected list is often the more
  useful half of a research pass, because it stops the exercise being re-run.
- Never leave a dangling item code in prose; the lane gate will fail on it, which is the point.
- **An in-progress marker is worse than a stale ✅, and it needs an expiry.** A29-GUIDE-UNDERLAY ③ read
  *"(in flight, PR #199)"* for **214 releases** after that PR merged. A ✅ merely leaves clutter;
  "in flight" reads as *someone else has this*, so it actively deters the reader who would have
  discovered it was done. **A pull-request number is the one staleness clock in the roadmap with a
  real timestamp attached — if a cell cites one, check whether it merged before believing the cell.**
- **Write an item's code ONCE.** A second bullet opening with the same code — a band summary, or the
  review a live entry rests on — parses as a second item, and `itemCodes()` collects into a `Set`, so
  the duplicate collapses and the count comes out right for the wrong reason. v0.3.1073 shipped as
  *"two entries for one item, again"*; it happened a third time and survived because the check that
  would see it de-duplicates before it counts. Supporting material goes under a heading that does
  **not** start with the code.

---

## 9. Editing a long doc — replace between markers, never splice at a match

`docs/roadmap.md` once accumulated **three duplicate NOW sections** with contradictory content,
because scripted edits *inserted* a section instead of replacing one, over several releases. That
lesson was written down — in `docs/roadmap.md`, about `docs/roadmap.md`.

**It then happened to `CHANGELOG.md`, and the note did not travel.** The v0.3.1019 nineteen-branch
integration renumbered colliding releases by splicing new `## vX.Y.Z` headers **above** the existing
ones, leaving **four orphan headers** — a version line with no body, directly on top of another
version line. Found 2026-08-25, roughly seventy releases later.

**A lesson recorded as prose about one file does not protect the file next to it.** So the rule now
lives where it can fail: `services/api/test_changelog_current.py` checks the changelog's *structure*
— no orphan headers, headers strictly newest-first, no entry duplicated, and version reuse pinned to
the one genuine historical collision (two commits really did both ship as v0.3.1019) by a down-only
ratchet. All four checks are mutation-verified.

When you must edit one of these files with a script: anchor on a unique marker, assert the anchor
appears **exactly once**, and replace a *range* — never insert at a matched string.
