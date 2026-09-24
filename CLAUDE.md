# Project: Massing

## What this is
A standalone web BIM **modeling program** + data platform for AEC firms. IFC is the source of truth.
The web app is a genuine authoring tool: create a model from scratch (blank IFC → levels/grid datum),
then draw walls/columns/slabs/families/MEP via server-side GUID-stable edit recipes — **not just a
viewer**. (Directional change, 2026-07: in-browser authoring is now a first-class goal, reversing the
earlier "web = viewer, Blender = editor" split.) Blender/Bonsai remains an optional advanced/interop
editor, not the required one. RVT support is an optional, paid Autodesk bridge — never assume RVT can
be read offline.

## Non-negotiables
- Reference model elements by IFC GlobalId (GUID), never by transient viewer IDs.
- Pre-convert IFC to Fragments on the server; never parse full IFC in the browser at runtime.
- Keep geometry and metadata separate: geometry streams as .frag; data comes from the API.
- Pins/RFIs/punchlist follow the BCF model so they round-trip with other BIM tools.
- The viewer must run fully offline (local WASM, self-hosted tiles).

## Stack
- Web: Vite + TS, web-ifc, @thatopen/{fragments,components,components-front,ui}, three (pinned pair).
- Services: Python, ifcopenshell, FastAPI, SQLAlchemy/Postgres, MinIO.
- Editor: Blender + Bonsai, driven via Bonsai-MCP.
- Optional: Autodesk APS Model Derivative (RVT→IFC), behind a feature flag with a cost warning.

## Build order
Phase 0 smoke tests → 1 conversion → 2 large-model → 3 viewer/tools → 4 API/BCF
→ 5 data export → 6 editor/families → 7 deploy.

## Watch out for
- @thatopen/components and @thatopen/fragments version coupling — pin a compatible pair.
- Bonsai-MCP execute_blender_code runs arbitrary Python: gate it, save first, chunk big ops.
- Set-origin/georeferencing: preserve real coordinates for export, render near scene origin.

## Local environment notes (this machine)
- **Bare `node` now resolves to v24.18.0 — the PATH workaround this line demanded is obsolete**
  (re-measured 2026-08-27). `which node` → `/c/Program Files/nodejs/node` → **v24.18.0**, npm
  **11.16.0**. v18.8.0 is still installed, at `/c/laragon/bin/nodejs/node-v18/node`, but it sits
  *later* on PATH and you no longer get it by default.
  `export PATH="/c/Program Files/nodejs:$PATH"` is therefore **belt-and-braces, not a requirement** —
  harmless to keep, and worth keeping in scripts, because the thing that changed is PATH *order*,
  which can change back the moment laragon updates.
  Both manifests declare `"engines": {"node": ">=24"}` and CI pins `node-version: 24`, so 24 is the
  supported baseline. **This is the fourth wrong value in these three lines**, and the first to be
  wrong in the *safe* direction: v20.3.1, then a version naming the Node you get *after* fixing PATH,
  then a major nobody had run in weeks — and now a workaround that outlived its cause. A stale
  instruction to *do something unnecessary* costs less than a stale one to skip something, but it
  still teaches the reader that this file is not to be trusted, which is the expensive part.
  **A config file that is subtly wrong is worse than one that is silent** — four drifts in, the only
  safe move is `which node && node -v`, never reading this line.
- **Python ≥ 3.12 is now a HARD FLOOR, not a preference** (corrected 2026-08-25; this line said
  "guide targets ≥ 3.11" and "prefer a 3.11+ interpreter … if available"). `requirements.lock` pins
  `numpy==2.5.2`, and numpy dropped <3.12 at 2.5.0 — so on 3.11 the install does not degrade, it
  **fails outright**: `No matching distribution found for numpy==2.5.2`. CI pins `python-version:
  "3.12"` in `ci.yml`, `db-migrations.yml`, `desktop.yml` and `security.yml`, and the lock is
  compiled in `python:3.12-slim`, the prod base image.
  *Same failure as the Node line above, in the other language: a floor that moved under a note
  phrased as advice.* "Prefer if available" is what a version note says when nobody has tried the
  alternative — and the alternative had stopped working. **Check a floor by creating the venv, not
  by reading this line.**
- **RESOLVED 2026-08-27: 3.12.10 installed, and `services/api/.venv` now MEETS the floor.** This
  entry previously said the venv could not meet it and that CI was therefore the only authority for
  the backend. Both halves are now out of date, and the *reason* it had drifted was not the one
  recorded here.

  | package | `requirements.lock` | venv now | venv before |
  |---|---|---|---|
  | numpy | 2.5.2 | **2.5.2** ✓ | 2.2.6 |
  | fastapi | 0.141.1 | **0.141.1** ✓ | 0.137.0 |
  | cryptography | 50.0.0 | **50.0.0** ✓ | **49.0.0 — under the CVE-2026-69247 floor** |
  | pyhanko | 0.35.2 | **0.35.2** ✓ | 0.35.1 |

  **109 lock pins, 0 version mismatches.** Verified by comparing every pin against `pip list`, not by
  reading the installer's "Successfully installed". Full suite: **640/641 on 3.12**, the one failure
  being an unrelated lane's uncommitted work-in-progress, which fails identically on the old venv.

  **WHY IT HAD DRIFTED — not "nobody installed 3.12".** `requirements.lock` **cannot be installed on
  Windows at all**, on any Python version, and this is structural rather than an oversight:

  - `requirements.in` asks for `uvicorn[standard]`, whose `uvloop` dependency **does not support
    Windows**. `pip-compile` resolved in `python:3.12-slim` and emitted an *unconditional* pin, so the
    `sys_platform != "win32"` marker `uvicorn` itself declares is lost.
  - In the other direction, `click` needs **`colorama` on Windows**, which a Linux-compiled lock has
    no entry or hash for — so `--require-hashes` refuses on a dependency it never knew existed.

  So the local install is `pip install -r <lock, minus uvloop>` **without `--require-hashes`**: exact
  versions, hashes unenforced. That trade is deliberate and worth naming — version fidelity is what a
  test result depends on; hash pinning is a supply-chain control, and **CI still enforces it on every
  push**, which is where it protects the artifact. It was never running locally, because the install
  never succeeded.

  **The old 3.10.6 venv is kept as `.venv-py310-superseded`** (and `.gitignore` now matches `.venv*/`
  so a rebuild's backup does not show up in every lane's `git status`). Delete it once you are
  satisfied; there is no reason to go back to it — it sits under a HIGH-severity CVE floor.

  **What is still true:** a local pass proves less than CI, because CI runs Linux with `uvloop` and
  hash-verified wheels. But it is no longer measuring *different code* — the gap is now one package
  that cannot run on this OS, rather than a FastAPI minor and three numpy minors.
- Repo root: C:\Server\modelmaker (Windows / PowerShell).
- Backend suite runs **from `services/api`**, never the repo root — the root exits 127 and reports
  "0 failures", which reads exactly like a pass.

## Directions come before the roadmap
**Read [`docs/roadmap-directions.md`](docs/roadmap-directions.md) first**, then the lane table, then an
item from `docs/roadmap.md`. The directions carry the non-negotiables, the shared-clone hazards, the
testing and release discipline, and what "done" means. They were split out of the roadmap on
2026-07-31 so the roadmap could stay a clean list of work — if a rule seems to be missing from the
roadmap, it is in the directions.

## Verify, don't recall
Long sessions drift: instructions written early lose influence, and stale file contents linger in
context beside current ones. The countermeasure is not a better memory, it is **checks that fail**:
`services/api/test_reachable.py` (is it wired?), `apps/web/src/kernel/ties.test.ts` (do the aliases
agree?), `services/api/test_no_comparative_names.py` (do the public docs name a competitor
*comparatively* — as opposed to as a connector, an import format or an SSO provider, which are
allowed?), and the size guard in `services/api/test_file_sizes.py`. If a rule matters, write it as a
test — anything held only as prose will drift, **including the prose in this file: two of those four
names were wrong until 2026-07-31.** "test_no_competitors.py" never existed at all, and the size
guard is `test_file_sizes.py`, not "check_file_sizes.py".

**A sixth joined them on 2026-09-03: `services/api/test_ruff_scope.py`** — is the lint aimed at the
whole tree? CI ran `ruff check src/ ../data/src/` and printed "All checks passed!" while **726 of
1,338 tracked `.py` files were never linted at all**, the entire backend test suite among them. The
check was real; the SCOPE was the fiction, and a green lint step is exactly what makes that
invisible. The gate parses `ci.yml` for the ruff command and asserts *that* command reaches every
tracked `.py` outside an explicit vendored list — so it cannot drift from what CI runs, because it
reads what CI runs. **Widening it also broke something**: `--fix` stripped `# -*- coding: utf-8 -*-`
from four IronPython 2.7 files under `integrations/pyrevit/`, three holding non-ASCII source, which
is a SyntaxError at import on Python 2 and is executed by no CI here. *Scope and rule set are
different questions, and widening one can break the other.*

**A fifth joined them on 2026-08-28: `services/api/test_declared_imports.py`** — does our own
`import` list agree with what we declare? It exists because `httpx` was declared in no requirements
file at all and reached the lock only `# via anthropic`, so bumping that SDK to 1.x — which moved to
`httpx2` — would have deleted a package two shipped modules import. Nothing would have gone red:
both consumers are function-local, so the service boots, `/health` passes, the suite stays green, and
only the bSDD and site-context routes 500. `pillow` sat in the same position `# via reportlab`.
**A package our own source imports is a DIRECT dependency however else it happens to arrive**, and
transitive availability is a fact about somebody else's metadata that can change in a release nobody
here reviews. (The list above still says "four" on purpose — that sentence is about which of the
ORIGINAL four names were wrong, and rewriting it to say "five" would quietly destroy the record.)

**A seventh joined them on 2026-09-06: `services/api/test_seeding_sweep.py`** — is the seeding sweep
real, or only written down? Five find-or-create races were fixed across 2026-08-25/27 and what bound
them was recorded as prose in comments beside each fix. **A sweep held as prose is a check that can
only report good news**, and there were four more sites: the ones keyed by a composite NATURAL key
rather than a primary one, which `get_or_create_by_pk` could not express — so they stayed
unconverted *and unmentioned*. **A sweep is bounded by the fix available to it.** They were also the
worse ones: a primary key refuses the loser's INSERT (one 500, and the retry works), while a
non-unique index refuses nothing, so the race does not fail — **it succeeds twice**, and
`scalar_one_or_none` then raises on every later read of that element, permanently. *Severity ran
opposite to the order the sites were found in.* The gate derives the population by AST instead of
listing it — **and its own first draft found one of the four known races and reported the tree
clean**, because it looked for the `Model(...)` assignment only inside the statement holding the
`.add()`, and the doors are written as two statements. It now runs itself against the pre-fix SAML
door and must find it before it may report anything. *Derive the population AND prove the derivation
reaches it.*

**And it was blind a SECOND time, within hours of merging.** To decide whether a conditional insert
was a get-or-create it required the model's name in a lookup call *in the same function* — so
`modules.add_enum_option`, which reads through the helper `list_enum_options`, was skipped silently,
and behind it sat a third live instance of the class. The precondition is gone: every mapped model is
a candidate and the only shape detected is the conditional insert, which is syntactic. **A predicate
that decides what to LOOK at is more dangerous than one that decides what to report**, because
everything it excludes is invisible to its own output — the count looked complete both times.

**An eighth joined them on 2026-09-06: `services/api/test_unique_read_guard.py`** — the READ side of the
seventh. `test_seeding_sweep` walks conditional inserts; this walks the queries that DEMAND one row.
`scalar_one_or_none()` does not prefer a single row, it **raises** on two — so a read filtered on
columns the schema does not constrain is a 500 that arms itself the first time a duplicate appears
and never disarms. It would have found the `element_verifications` defect **without anyone looking at
the writers**, which is the argument for having both: a future instance must now evade two unrelated
derivations rather than one. Population today: 5 reads — 3 backed by a unique constraint, 1 aggregate,
1 exempt. The exemption is `cloud_identities.cloud_sub`, which is indexed and NOT unique: at most one
row can carry a given sub, but the *ordering* guarantees it rather than the schema, and making it
unique is a product decision (it would forbid two local accounts deliberately linked to one cloud
identity) rather than a cleanup.
**It fails CLOSED, and that is the whole design** — a call site the analyser cannot resolve is
reported as UNKNOWN and reds the build, because the two blind spots above were both a predicate
deciding what to LOOK at. **And its own first draft had the same bug one layer up**: the self-test
asserted the analyser still *reported* an unresolvable read, so a mutation routing every unresolvable
read to "safe" PASSED. *Reporting a site and classifying it are two different questions, and asserting
one is not asserting the other.* The verdict function is now separate so it can be mutated directly.

**A ninth joined them on 2026-09-12: `services/api/test_scratch_ignored.py`** — is every scratch
directory the suite creates actually git-ignored? Thirteen were not, so a concurrent or crashed run
left residue that **`git status` reports identically to uncommitted work** — a stop hook read
`_shelf_famgeom/` exactly that way. The gate derives the population by parsing `"./<name>"` literals
and then asks **git itself** rather than reimplementing `.gitignore` matching. **Its first two drafts
were each wrong in the house style: the checker did not fail, it ANSWERED.** Without a trailing slash
git cannot tell an absent path is a directory, so every directory-only pattern missed and it reported
**377** uncovered; asked from `services/` rather than the repo root the paths resolved nowhere, the
per-directory `services/api/.gitignore` was never read, and it reported **35** — which would have had
nineteen redundant patterns added to fix nothing. *A wrong question returns a confident number, and a
number with a list attached reads as evidence.* Hence three self-tests, one per way of asking wrongly,
run before any verdict is printed. **And the per-directory canary is DERIVED, not named:** an earlier
draft hardcoded the one pattern it probed, so removing that pattern legitimately would have redded the
self-test with a message blaming the wrong cause — *a check whose failure message can misdiagnose is
worse than one that stays silent, because somebody acts on it.*

**A tenth joined them on 2026-09-13: `services/api/test_json_null_filter.py`** — is a NULL test ever
applied to a JSON column that can hold the JSON scalar `null`? SQLAlchemy stores a Python `None` in a
`JSON` column as `null` unless the column declares `none_as_null=True`, and that is **not SQL NULL**,
so `WHERE <json col> IS NOT NULL` matches every row ever written. The gate derives all 21 NULL tests
by AST and resolves each subject against the model metadata; it fails CLOSED, and it runs itself
against the one known instance before it may report anything. **The load-bearing distinction is that a
JSON EXTRACTION is not the JSON column** — `data ->> 'x'` is a text scalar that yields SQL NULL on both
backends for a missing key and a stored `null` alike — and conflating the two would have flagged every
register query in the tree. It deliberately does **not** demand `none_as_null=True` on all 588 JSON
columns (308 lack it): that is a write-behaviour change, not a gate, and the readers are two orders of
magnitude fewer than the writers.

**The same day, its sibling `services/api/test_pin_pgnull.py` taught the sharper lesson.** The pin
sweep migration skipped exactly the rows it existed to convert, and the finding was filed as a
PostgreSQL defect. **It is not a dialect defect — it is a DRIVER-DECODING defect**, and sqlite3
reproduces it exactly once a converter is registered, so the behavioural check runs on every
invocation rather than only where a server happens to exist. *A defect attributed to the dialect it
was found on is a defect nobody looks for anywhere else.* And the first draft of that check asserted
only the emitted SQL: reinstating the exact defect on top of the corrected statement left the SQL
identical and PASSED. **Asking the right question and then throwing the answer away are two different
failures, and only one is visible in the statement.**

**An eleventh joined them on 2026-09-13: `services/api/test_system_columns.py`** — does the
allowlist of sortable row columns name columns that EXIST? `modules_query.SYSTEM_COLUMNS` short-circuits
`_resolve_field`, whose own docstring is *"Never trust a caller-supplied field name"* — and the trust it
was actually extending was in the three literal lines above it. Two of its six names were columns on 0 of
139 register tables, so `t.c[name]` raised `KeyError` and `?sort=updated_at` was a **500 on caller input**
from a function written to return 400. **The stored form was the quieter one and therefore the worse one:**
`validate_view_config` resolves through the same function with no table in scope, so a saved view carrying
the phantom returned **201**, listed at **200**, and 500d only when somebody applied it — the cause two
screens from the symptom. *A defect that is refused loudly is nearly fixed; one that is accepted and stored
has to be found twice.* The fix is both halves — a runtime check against the table AND a corrected list —
because **either alone passes every test the other would fail**, so the gate deletes each in turn: it must
re-find both shipped phantoms before it may report anything, and it reinstates the pre-fix `_system_field`
and requires the `KeyError` to come back. *A static check that still passes with the guard removed is not
testing the guard.* `updated_at` was also the THIRD instance of that same typo on a module row — the other
two returned a permanent `None` and were found in August. **The same wrong name is not the same severity in
two places, and the loud one was found last.**

**A twelfth joined them on 2026-09-13: `services/api/test_court_primary.py`** — is the rule that
picks the ball-in-court *checkable*? `court_party` took the first outgoing transition on the stated
premise that "module authors list the primary forward action first", and the web register answered
the same question by unioning ALL of them: 10 states in 9 modules disagreed between the screen and
every money report. **The premise was false in two places** — `pull_plan_task.made_ready` lists a
rollback first, `permit.applied` lists `issue` before `start_review`. **And the obvious enforcement
could not be built**: deriving "forward" from the declared state order is measurably wrong, because
`action_item.states` is `['done', 'open']` — alphabetical, not a progression — leaving 45 states with
no forward transition and 39 with several. *A premise that cannot be checked has already drifted; the
only repair is to stop inferring it and DECLARE it.*
**The load-bearing move was bounding the population**: only 17 of 267 states need a declaration,
because for the other 250 the choice cannot change the answer. *A rule demanding 267 edits gets
abandoned halfway and leaves the tree half-declared, which is worse than not starting* — so the gate
demands a declaration exactly where one is load-bearing, and derives that set rather than listing it.
Two further lessons: the value is enriched at the two ROUTES, not in `list_records`, which has 274
call sites including a BCF export built from the row's keys — *the narrowest place that can carry a
fact is where it belongs*; and both routes resolve through `workflow_config.effective`, because
`transition` does, and reading the shipped workflow instead would have reopened the same
disagreement by a different door.

**A thirteenth joined them on 2026-09-14: `services/api/test_pid_lock_pgxproc.py`** — does the advisory
lock exclude two PROCESSES? `services/api/test_pid_lock_xproc.py` is *named* for cross-process
serialisation and asserts a great deal about it; its one exclusion check is **two threads, in one
process, on SQLite**, where `_advisory()` takes nothing and the exclusion observed is entirely the
in-process `RLock`. So `pg_advisory_lock` — the whole of R35-PIDLOCK-XPROC — was exercised by no line
of this tree, and could have shipped acquiring nothing. **A test named for a property can assert every
neighbouring property and never the one in its name.** What it *did* prove across processes is that two
workers derive the same KEY: necessary, and silent on whether taking it excludes anybody. The new gate
runs two real OS processes against a real server and asserts their held intervals do not overlap —
**with two mutations, because either alone passes a lock that has stopped locking**: two different
projects MUST overlap (otherwise the positive check is measuring the order the harness starts things
in, and a lock that excluded *everything* would look identical), and a per-process key MUST overlap
(note 1's `hash()` defect, reinstated across real processes). Verified by deleting the acquisition
outright — the behavioural check reds independently of the static one, and one check that *stayed*
green under that mutation had its label narrowed rather than left: `cross_process_status()` reports the
DIALECT, so it says the advisory path was *available*, never that a lock was *taken*. It also pins the
acquisition as the BLOCKING form, because `_advisory` sets `acquired = True` without reading a result —
so a `pg_try_advisory_lock` "don't block the request" change would report a lock it does not hold. That
static pin is **redundant wherever a server exists** — measured, not assumed: with the swap applied the
behavioural check reds too, deterministically, because the harness starts B only once A is demonstrably
inside. Its value is the run with NO server — every ordinary local invocation, where the exclusion arm
cannot run at all. *A check earns its place from where it is the ONLY one, not from the worst case it
can be described as catching* — and the first draft of that sentence claimed the worst case.

**A fourteenth joined them on 2026-09-24: `services/api/test_gap_records.py`** — does a record that
calls a gap OPEN still have a gap to be about? `services/api/test_rmw_sweep.py` printed *"43 ORM
sites: 43 reasoned exempt or locked, 0 named open"* while **four records in two documents** —
RMW-LOCKGAP and RMW-TOKEN in `docs/roadmap.md`, G-10 and G-12 in `docs/security/threat-model.md`,
plus a summary line reading "**Four** sites remain open" — described that finished work as
outstanding. *A stale OPEN costs more than a stale CLOSED*: the roadmap's ranking sends the next
reader at it, the threat model shows a reviewer a live exposure, and RMW-TOKEN's entry had
additionally priced the fix as "a migration (add the column, backfill, route both writers through a
CAS)" — work nobody ever did, because both sites closed with a lock already in the tree. **One of
those entries was half wrong on the day it was FILED**: `realestate.save_appraisal` took its lock on
2026-09-13 and the entry naming it as open was written on 2026-09-14, because the gap was inherited
from an earlier sweep and the split copied that sweep's reading rather than re-measuring.
`services/api/test_roadmap_status.py` already asked the right question — *does the item's own gate
report the work done?* — but only for items somebody REGISTERED in its map, and nothing forces a
closing pull request to add itself. **A registry reports on what it contains, and its silence is
indistinguishable from a clean bill.** *(That file also had a fail-open hole, found by mutation and
fixed in the same change: `marked_open` was itself unasserted, and the loop reads
`if not marked_open(code): PASS; continue` — so breaking its bullet regex with one literal made
every registered item report PASS and the file print "every item with a measurement agrees with its
marker". Its one precondition check guarded that the ROADMAP was readable, not that the PREDICATE
could still say yes.)* The new gate derives both sides — subjects from the sweep ledgers by AST,
records from the two documents by indentation — and **the scoping clause is the load-bearing half,
learned rather than designed**: ruling on every open record reported SCALE-SEAM, an item about
`apps/web/src/api/client.ts`, as a stale concurrency gap because 894 lines into its body it mentions
`_restore_version`. *A rule applied outside the population it was reasoned about does not degrade
gracefully — it produces confident findings about records it has no view of.* Scope is now
"records that cite the gate", and the rule is "must name at least one OPEN site" rather than "must
name no closed one", because a genuinely open record cites its closed siblings for contrast and
RMW-LOCKGAP's did. Two spellings broke its first draft in opposite directions: without `/` in the
identifier chain, `routers/proforma.share_scenario` read as `routers` and RMW-TOKEN came back clean;
matching a PREFIX of a backticked span made `edit-mep` match the route `edit`. *A defect the
analyser cannot spell is invisible to it and reads exactly like an absent one; a prefix match
answers a question nobody asked, confidently.* It replays both documents as shipped at `53cfa71a`
and must re-find **all four** records and **nothing else** before it may report.

"Cite a gate only after `git ls-files` confirms it" is itself a rule held as prose, so it is now
`services/api/test_claude_md_gates.py`: every backticked code file named here, in
`docs/roadmap-directions.md` **and in `docs/roadmap.md`** must resolve to a tracked path — including
citations that carry a locator (a trailing ":line", "::symbol" or "#anchor"), which escaped the check
until 2026-08-01 and hid 21 of them. *Those example forms are in plain quotes on purpose — backticking
an illustrative filename makes it a citation, which is how this very sentence failed the gate once.* The roadmap contributes ~115 of the ~128 citations, so **it is the
doc most likely to fail a build on this**; two wrong paths were found the day it was added, one of
them naming the wrong *directory*, which matters because lanes are assigned by directory.

`docs/roadmap-completed.md` is deliberately **not** gated: it is a historical record and names things
that were proposed and never built. **Backticks are therefore reserved for files that exist** — a
dead, historical or merely proposed name goes in plain quotes, since a backticked name reads as a live
citation whether or not anything backs it. Read that test's docstring before editing this list; the
lessons that cost the most live there, next to the check, not here.

## MassingViewer — the extraction, and what it means for `apps/web/src/viewer`

**MassingCloud/MassingViewer is live, public, MIT**, and is where this repository's Design Room engine is being
extracted to. It is not a fork and not a second viewer: massing is intended to consume it as a dependency and
delete its own copy. Written here on 2026-08-15 because nothing in these instructions mentioned it, and an agent
working in the viewer directory could not have known.

**Ready on its side, by its own measure — and EVALUATED AND DECLINED HERE on 2026-08-23.** A facade,
"@massing/embed" 0.2.0, MIT, exposing viewport, authoring session, commands, kernel, drawings, markup, ribbon and
plugin host; a seam ledger whose claims are asserted against the built facade rather than ticked in a table.
Packaging is validated from real tarballs, so the swap is not blocked on anything *packaging*.

**Numbers measured from the published tarball, because the ones this paragraph used to carry were wrong.** It
said "27 of 27 movable capabilities covered". Running its `seamCoverage()` out of the shipped "seam.js" reports
**20 of 20 movable, 4 boundaries, 24 entries total**, `ready: true`, *"apps/web/src/viewer can be deleted"*. The
dependency closure is **12 packages** (embed + 11), not 25.

**Why it was declined — the reason is architectural, not a matter of polish.** The facade's load path is
**IFC text into a browser-side tessellator**: `open(source: string | Uint8Array)` sniffs bytes, and the required
`Tessellator` is `(ifcText: string) => {meshes, guids}`. Its seam entry `kernel.open` says so —
*"load a model into the kernel from IFC text"*. **There is no notion of pre-converted Fragments anywhere in the
package** (grepped: the single "fragment" hit is a generic use in a section-box note). That collides head-on with
two non-negotiables at the top of this file — pre-convert on the server, never parse full IFC in the browser at
runtime; geometry streams as `.frag`. Adopting the facade means either breaking that, or keeping our own load
path outside it — and then it is no longer the whole surface, both copies live, and that is the fork their own
plan calls the only risk that can end the project.

**And its `ready: true` measures the wrong half.** The ledger's own test asserts every `covered` entry is
reachable through the facade's type — which proves each *claim is backed*, not that the *claims cover the
ground*. Its 24 entries are a dissection of this viewer as it stood around 2026-08-06. This viewer is **155 TS
files / 19,159 non-test lines / 65 test files** today (re-measured 2026-09-10), and the list names none of: the plan/sheets/specs canvas
modes, collaborative peer cursors, dimensional locks, viewer load timings, reference point clouds, GIS context,
or the model-bounds allowlist. *Derive the population AND the reach — a completeness verdict computed over a
self-authored list is confident and unfounded.*

**The family is also inert.** All 12 packages were published on 2026-08-08 in two bursts and **not one has been
modified in the 15 days since** (queried from the registry 2026-08-23), all still 0.1.x/0.2.0. Adopting a
dependency that is not moving, to replace code that changed today, inverts the divergence risk it exists to
solve.

**What would change the answer:** a Fragments-shaped load path in the facade — `open()` accepting pre-converted
fragment bytes, or a `KernelProvider` that streams them — plus a seam list derived from *this* tree rather than
from their plan. The decision remains the user's; this records an evaluation, not a veto.

**That blocker is GONE, and it was already gone when this section was written.** This said "the packages are
not on npm yet. Until they are, this repository keeps its own viewer and nothing here should change on account
of the extraction." Queried against the npm registry on 2026-08-21: **20 of the 25 package names are published,
all MIT, all dated 2026-08-08** — including "@massing/embed" at **0.2.0**, whose eleven declared dependencies
("core", "viewport", "authoring", "commands", "drawings2d", "fileio", "kernel-api", "markup", "observability",
"plugin-host", "ribbon") are every one of them published. This section is dated **2026-08-15**, a week after
that. *A standing instruction can be stale on the day it is written, and this one names its blocker so
confidently that no reader would think to check.* Not published: "i18n", "tessellate", "pwa", "assets",
"kernel-remote" — none of which "embed" depends on. *(Plain quotes, not backticks: this file's own rule two
sections up reserves backticks for files that exist, and these are package names in someone else's registry.
The paragraph above already followed that rule and the first draft of this one did not.)*

**What follows from that is the USER'S CALL, and nothing here changes until they make it.** The two breaking
changes below are real (async viewport creation, add/remove replacing `showModel`), the divergence is now
thirty-odd commits deep, and "adopt the facade" is a multi-release architectural commitment, not a dependency
bump. So: the *factual* blocker is corrected here because it was false; the *decision* it was gating is
untouched and still open. Keep shipping viewer work in the meantime — that guidance below is unchanged and was
never contingent on the npm question.

**What an agent working in `apps/web/src/viewer` should know.** **Seventy-nine** commits have touched that
directory since extraction began on 2026-08-06, and `apps/web/src/viewer/app.ts` has gone from 5,064 lines to
**2,442** — largely R39-DECOMP-VIEWER, which is the same decomposition the extraction plan asks for and is being
done here first. That is good and it is also divergence: every one of those commits is a change the swap will
have to reconcile. So:

  *(Both numbers were stale and are re-measured 2026-09-05 — this said "Twenty-eight commits" and "3,444 lines".
  Unlike the Node and Python drifts above, **this one moved in the direction that strengthens the argument**:
  more than twice the commits and another 936 lines out. A number that decays toward the conclusion it supports
  is the hardest kind to notice, because nothing it predicts ever looks wrong. Re-measure with
  `git log --oneline --since=2026-08-06 -- apps/web/src/viewer | wc -l` and
  `wc -l apps/web/src/viewer/app.ts`, never by reading this line — the same rule the two version notes above
  had to learn the expensive way.)*

  *(**And the line count above was stale again within the same pull request.** The correction first written
  here said **2,570**; slice ⑰ of R39-DECOMP-VIEWER landed in that same PR and made it **2,508**, so the
  paragraph diagnosing decay-toward-the-conclusion decayed toward its own conclusion before it was merged, and
  a review bot found it rather than the author. Two things follow. **A number and the change that moves it must
  land in the same edit, not the same commit** — "I will update the note after the slice" is a promise made
  inside the window where it is already wrong. And the authority is `services/api/test_file_sizes.py`, which
  pins `apps/web/src/viewer/app.ts` at an exact size and fails the build when it drifts; **this line is a
  narrative copy of a number that has a gate, and a copy is what drifts.** Read the pin, not the prose.
  The `wc -l` in the re-measure command above was also bare and would have waited on stdin — an instruction to
  verify that hangs is an instruction nobody runs twice.)*

- **Keep shipping.** Blocking this roadmap for the extraction would make the extraction expensive and it would
  die. Landing viewer work here is the correct default.
- **Prefer changes that survive the swap** — new behaviour behind the existing seams, rather than new coupling
  into `apps/web/src/viewer/app.ts`.
- **Two breaking changes are coming together, deliberately**, so this repository absorbs one: creating a viewport
  becomes asynchronous (WebGPU first, WebGL2 fallback), and single-model `showModel` becomes add/remove with
  per-model state. Selection stays keyed by IFC GlobalId across models, which is what `planPaneSelection` and the
  spec pane already rely on.
- **Never reference an element by a transient viewer id** across that boundary. GlobalId is the only identity
  that survives a reload, a re-tessellation, or a second model.
