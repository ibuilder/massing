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
`test_reachable.py` (is it wired?), `ties.test.ts` (do the aliases agree?), and the size ratchet in
`test_file_sizes.py`. If a rule matters, write it as a test — anything held only as prose will drift,
including the prose in this file.

Those names are themselves asserted by `test_claude_md_gates.py` — on 2026-07-31 two of the four
listed here were fiction, in the one section arguing prose drifts. **Backticks are therefore reserved
for files that exist**; a dead or historical name goes in plain quotes. Two rules that cost real time
to learn, kept with the gate rather than here: a name that does not resolve is not a missing
capability (search the *capability* before rebuilding anything), and **"the file exists" is not "main
is protected"** — ask `origin/main`, since a gate can be green on a branch for days. Read that test's
docstring before editing this list.
