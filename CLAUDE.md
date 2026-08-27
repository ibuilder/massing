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
- **AND THE VENV ON THIS MACHINE DOES NOT MEET THAT FLOOR — measured 2026-08-27.** The line above
  says to check by creating the venv. Doing that here fails: **there is no 3.12 on this machine.**
  `python`→3.10.6, `python3`→3.11.9, `py`→3.11.3, and the py-launcher lists only 3.11. The existing
  `services/api/.venv` is **Python 3.10.6**, so it cannot install `requirements.lock` and never did:

  | package | `requirements.lock` (CI + prod) | what the local venv actually has |
  |---|---|---|
  | numpy | 2.5.2 | **2.2.6** |
  | fastapi | 0.141.1 | **0.137.0** |
  | pydantic | 2.13.4 | 2.13.4 ✓ |
  | ifcopenshell | 0.8.5 | 0.8.5 ✓ |

  **So every local backend green — including one reported minutes ago — is measured against
  different code than ships.** Not "an older environment": a *different* FastAPI minor and a numpy
  three minors back. A defect that appears only on the locked versions passes locally, every time,
  and CI is the only thing that can see it. This is the **env** dimension of "what exactly did it run
  on?", and it had no entry here at all until now.
  **CI remains the authority for the backend suite.** A local run is a smoke test of your edit, not
  evidence about the release. Installing 3.12 is a machine change and therefore the user's call —
  until then, do not report a local backend pass as if it settled anything about `requirements.lock`.
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
ground*. Its 24 entries are a dissection of this viewer as it stood around 2026-08-06. This viewer is **129 TS
files / 16,408 non-test lines / 53 test files** today, and the list names none of: the plan/sheets/specs canvas
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

**What an agent working in `apps/web/src/viewer` should know.** Twenty-eight commits have touched that directory
since extraction began on 2026-08-06, and `apps/web/src/viewer/app.ts` has gone from 5,064 lines to 3,444 —
largely R39-DECOMP-VIEWER, which is the same decomposition the extraction plan asks for and is being done here
first. That is good and it is also divergence: every one of those commits is a change the swap will have to
reconcile. So:

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
