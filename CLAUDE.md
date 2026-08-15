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
- **`node` on the default PATH is v18.8.0, and v18 BREAKS the web build.** The good Node is not first
  on PATH, so every web command must start with:
  `export PATH="/c/Program Files/nodejs:$PATH"` → **v24.18.0** (verified 2026-07-29).
  Both manifests declare `"engines": {"node": ">=24"}` and CI pins `node-version: 24`, so 24 is the
  supported baseline — this note said **v20.3.1** until 2026-07-29, which was a *third* wrong value
  in the same three lines. It has now been wrong in two different ways: first naming the Node you get
  *after* fixing the PATH rather than the one you get, then naming a major nobody has run for weeks.
  **A config file that is subtly wrong is worse than one that is silent** — and a line that has
  drifted twice will drift again, so check it against `node -v` rather than reading it.
- python 3.10.6 — guide targets ≥ 3.11. Works for ifcopenshell 0.8.x / FastAPI / pydantic v2,
  but prefer a 3.11+ interpreter for the `services/` venvs if available.
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

**Ready now, on its side.** 25 published packages, all permissive and checked against *this* repository's allowed
licence list; a facade, "@massing/embed", exposing viewport, kernel, drawings, markup, ribbon and plugin host; a
seam ledger reporting 27 of 27 movable capabilities covered, each claim asserted against the built facade rather
than ticked in a table. Packaging is validated from real tarballs, so the swap is not blocked on anything
technical.

**Blocked on one thing:** the packages are not on npm yet. Until they are, this repository keeps its own viewer
and nothing here should change on account of the extraction.

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
