# Roadmap

The single product roadmap — **open items only**, reconciled + re-prioritized **2026-07-20 at v0.3.567**
after the quick-wins + flagship-sprints wave (v0.3.543–567). Everything ever shipped lives in
[roadmap-completed.md](roadmap-completed.md); per-release detail is in [CHANGELOG.md](../CHANGELOG.md).
Supporting detail: [production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[cost-db-import-plan.md](cost-db-import-plan.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
The R15 ring is closed and both flagship offline-verifiable sprints (Schedule Optioneering, Client-Portal)
are driven several phases deep; the **master-builder skill** is installed and co-evolves with the platform.
What remains is bounded R14/R15 tail depth, the big-ticket continuations, a runtime/tooling ring, and the
decomposition/design carry-overs.

**Status:** CodeQL 0 open alerts · full backend suite green (306 suites) · single-source version in
`apps/web/package.json` (v0.3.567).

---

## ▶ NOW — bounded, backend-testable, no new dependency (ship top-down)

*Each is an S/M release: a pure engine leaf or a config-module tweak + a thin surface + a test, grounded
in the model we own. Verifiable without the frontend. These are the cleanest next wins.*

1. **VERSION-COMPARE per-property** — the iTwin-style old/new value list per element (needs richer
   per-version property snapshots; the 3D overlay + change labels shipped v0.3.526). The tabular
   per-property delta is the remaining slice.
2. **IFCPATCH-LIB** — rebase coordinates · unit-convert · merge/split recipes (the purge recipes +
   SUBSET-EXPORT shipped v0.3.527/533). Pure ifcopenshell transforms behind edit-recipe gating.
3. **BCF-API-SRV depth** — attachments over the API + the **BCF 3.0** shape (2.1 core + viewpoints shipped
   v0.3.528–529).
4. ✅ **SPRINT D phase-3c — selections money card** *(v0.3.569)* — a ◈ Selections destination: net
   over/under, per-category deltas, the over-allowance CO candidates + a push-to-change-events button.
5. **SPRINT B phase-4b — CPM crew shifts + frontier chart** — CPM-driven crew shifts off the critical path;
   scale the enumeration; a Pareto-frontier **chart** (cost vs. duration scatter) on the 🧮 panel.
6. **SPRINT MB — per-step deep-links** — wire each Master Builder brief step's gap to the portal
   destination that closes it (nav-map the step keys to their tools).

## 🏔 BIG-TICKET SPRINTS — multi-release initiatives (open ONE track; slice + reassess)

- **SPRINT A — ENERGY & DAYLIGHT (via the jobs lane).** *(L)* EnergyPlus (BSD) + Radiance (LBNL) for
  defensible annual energy / daylight (DA·ASE·UDI) / glare (DGP). **Phase 1 (no binaries, de-risks the
  whole track):** the **IDF/gbXML envelope export** — model → surfaces/constructions/zones, mirroring the
  shipped FEM-EXPORT / SOLVER-OUT pattern. **Phase 2+:** ship the solver binaries through the durable job
  queue and run them; parse results back onto the model.
- **SPRINT C — FIELD-PWA.** *(L, mostly frontend)* Offline-first mobile PWA: sheet sync, auto
  slip-sheeting, hyperlinked callouts. **Phase 1:** the service-worker offline cache + sheet sync over the
  existing markup/SSE infra; then the field-optimized nav + callout links. *(Frontend-heavy — the preview
  stall + pane sandbox limit live click-testing; ships build/typecheck-verified with that caveat.)*
- **SPRINT E — FAB-DELIVER phase-2 (GATED).** The byte-exact **BVBS BF2D** bending file (and then
  **DSTV-NC** for steel) is held behind validation against the authoritative BVBS guideline **and** a real
  importer/validator — a wrong file mis-bends real steel (the fabrication-output doctrine in the skill's
  `construction-delivery.md`). **Unblock:** the spec + a validator.
- **PHOTO-PIN** *(L)* — photo/360 pinning to plan locations + timeline compare (integrate photogrammetry,
  don't build it). **CMMS-OPS** *(L, defer)* — preventive-maintenance plans + work orders on COBie assets.

## 🧵 R15 / R14 tail (open remainder)

- **NORM-VALID** — the STEP-syntax + bSDD lanes shipped v0.3.552; a deeper **implementer-agreement
  gauntlet** (full FILE_DESCRIPTION view-definition parse, unit-assignment completeness, relationship
  cardinality rules) is the remaining depth if a customer needs it.

## ⚙️ RUNTIME ring — runtime & tooling upgrades (interleave; measured wins only)

*Rust/C-backed libs + toolchain moves; MIT/BSD/Apache only; each is its own benchmarked release — no
adoption without a measured win. (RT-ORJSON shipped v0.3.511/550.)*

- **Needs a dependency OK:** **RT-OXLINT** ([oxlint](https://oxc.rs), Rust MIT — sub-second pre-lint gate
  beside the pinned eslint 9.39.5) · **RT-ZSTD** (zstandard BSD — transparent magic-prefix compression of
  MB-scale storage blobs in `storage.py`) · **RT-KNIP** ([knip](https://knip.dev) ISC — unused-export /
  dead-dep scan for `apps/web`, feeds REL-7).
- **No new dep:** **RT-UVLOOP** (`--loop uvloop` + `httptools` in the Linux Docker entrypoint; pair with a
  worker-count / keep-alive / `--limit-concurrency` / DB-pool alignment pass).
- **RT-VIRTUAL** *(M · UX)* — [@tanstack/virtual](https://tanstack.com/virtual/latest) (MIT) to virtualize
  the big DOM lists (module tables at 100k+ rows, my-work, boards, model-browser tree); removes the
  "first 500" truncations.
- **RT-BVH** *(S/M, investigate)* — [three-mesh-bvh](https://github.com/gkjohnson/three-mesh-bvh) (MIT) for
  OUR raw-three raycast paths (snap, measure, draft-proxy picking; Fragments' picking stays vendor-managed).
- **RT-MSGSPEC** *(S, investigate)* — msgspec (C, BSD-3) typed-Struct decode for the ONE hot blob (the
  per-project property-index load) — only if profiling shows the parse matters; Pydantic v2 stays for API.
- **RT-NODE-LANE → RT-ROLLDOWN** *(M, chain)* — upgrade local Node 20.3.1 → 22 LTS (unpins eslint, unlocks
  Vite 7/8), then trial `rolldown-vite` / Vite 8 (Rust bundler) in a branch — verify the pinned @thatopen
  pair + PWA/workbox survive before adopting.

*Evaluated, not adopting: Biome (churn > win while eslint pinned) · granian (no measured need) · wholesale
msgspec/Pydantic swap (Pydantic v2 is Rust-core) · client-side comlink parsing (heavy parse is server-side
by design).*

## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- **REL-3 remainder** *(M)* — `modules.py` DI split (unblocks its CRUD/feeds leaves) · `main.py` ·
  `codecheck.py` · `connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/`massing.py` ·
  `bcf_io.py` · `routers/generate.py`.
- **REL-4 leaves** *(M)* — continue the god-file decomposition: `portal.ts` (next leaf) + `viewer/app.ts`
  leaves.
- **WFE-3** *(M, deferred-by-choice)* — per-project configurable workflow transitions via the config-row
  trick (lower value than the shipped automation).
- **JOB-QUEUE PAdES** *(S, gated)* — PAdES sealing on the queue (needs doc-reference plumbing — defer until
  a queued signing flow exists).
- **REL-6 tail** — cargo-audit / gitleaks in CI when available.
- **REL-7** — evidence-gated dead-code removal (prove-then-delete small batches; RT-KNIP feeds it).

## 🎨 P2 — design & authoring depth (sequence opportunistically)

**Designer workspace:** UX-3 library depth (thumbnails · drag-to-place · pick-host→auto-build · appendable
IFC libraries · CC0 seed/H1) · UX-4 one-shell layout (Project-Browser spine + docked Properties + Library +
ribbon; a11y/mobile pass).

**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed egress/
life-safety plans (path-trace over the semantic graph) · B3 wall Axis + clip planes · E5 parametric handles ·
A2 RAG index over ifcopenshell/IFC docs.

**Authoring depth (Wave 10):** W10-2 parametric family generators (profiles + swept/boolean; build123d/OCP
optional track) · W10-9 dimensional constraints (planegcs LGPL; sidecar-solved, baked to IFC) · W10-5
section/elevation annotation views.

**Finance/frontier:** GEN-SCORE depth (per-option 5D takeoffs + EPD carbon once options carry models) ·
SITE-1 remaining slices (terrain DEM auto-fetch · parcel overlays) · COLLAB selection halos (viewpoint
payload carries `selectedGuid`).

## P3 — gated (each entry names its unblocking event)

*Re-checked 2026-07-20: every gate still holds — none are buildable offline on this machine. What CAN ship
without the gate has shipped; the rest stays honestly gated rather than falsely ✅.*

- **Upstream:** IFC5/IFCX *geometry* write (web-ifc/Fragments write path — the data path ships) · bSI
  Validation Service in CI (service account). Track buildingSMART.
- **Paid / flagged (never core):** VIZ-U1 Unity/Pixyz presentation build · VIZ-3 pixel-streamed cinematic ·
  VIZ-4 VR review · W9-7 AI PDF auto-takeoff · CODE-6 licensed code prose · COST-DB cloud ingest
  (massing.cloud manifest/signed bundles/delta/Ed25519 — the offline importers ship) · DWG (ODA) / USD (pxr)
  export.
- **Platform/pipeline:** native mobile Capacitor shell (needs macOS/Xcode + Android pipeline; PWA ships) ·
  SOC 2 feature set (KMS/retention/residency — cloud infra) · BMS/IoT telemetry (Brick/Haystack source
  required) · reality-capture progress quantification (capture data required).
- **Large optional builds (prerequisites complete):** coupled-frame FEM solve · viewer tile-streaming
  upgrade · AR field overlay · per-county location-factor/PPI DB tables.
- **Counsel-gated:** regulated syndication depth (the origination connector ships; licensed stack on
  customer pull). ⚖️ Not legal advice.
- **Environment note:** headless/hidden panes stall the Fragments raycast + web-ifc import *workers*
  (vendor-level; the app-side timeout fallback ships). Verify those two paths in a visible tab.

## Non-goals (documented rationale — not gaps)

`.mpp` parsing (proprietary; XML/CSV import is the path) · custom Revit plugin (certified `revit-ifc`
covers it) · portal core A4/A5 split (deliberate coupling) · live ENERGY-STAR/BAS integrations (flagged
stubs only) · CAFM/1031 tooling · scraping code prose (facts-of-law only) · GPL/AGPL vendor code
(reimplement techniques). Deliberate 501 bridges (money movement / KYC / paid APS) are a compliance pattern,
not gaps.

**Not building (from research):** photogrammetry pipelines · learned risk forecasting (Monte Carlo covers
it) · voice agents · all LLM/computer-vision document scanning (non-deterministic; we author the model).
Integrate-not-build: Cesium ion imagery · Speckle Automate hosted runner · iTwin Platform REST · Autodesk
APS · Pollination.

**License guardrails:** ifcopenshell/geom = LGPL (safe dep) · no AGPL (no PyMuPDF) · planegcs (LGPL,
extractable) over python-solvespace/OpenSCAD (GPL) · CC0/CC-BY assets vetted per-asset · OSM = ODbL
attribution as a separate layer.
