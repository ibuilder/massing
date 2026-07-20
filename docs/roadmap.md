# Roadmap

The single product roadmap — **open items only**, reconciled + re-prioritized **2026-07-19 at
v0.3.542** after the R15/R14 ring wave. Everything ever shipped lives in
[roadmap-completed.md](roadmap-completed.md) (the v0.3.510–542 wave, the v0.3.493–509 queue wave, and
the P1/P2 run before it); per-release detail is in [CHANGELOG.md](../CHANGELOG.md). Supporting detail:
[production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[cost-db-import-plan.md](cost-db-import-plan.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
The R15 ring is fully closed and the shippable R14 tiers are cleared; what remains is genuine bounded
feature depth, a runtime/tooling ring, the flagship-L builds, and the decomposition/design carry-overs.

**Status:** CodeQL 0 open alerts · full backend suite green (295 suites) · single-source version in
`apps/web/package.json`.

---

> **★ MASTER-BUILDER brief shipped v0.3.557** — the 8-step Master Builder Protocol (place → program/HBU →
> feasibility → regulatory → design → delivery → risk → handover) as one synthesis over the project's own
> data, grounded in its jurisdiction: `master_builder.py` + `GET /master-builder/brief` + the 🏛 panel,
> backed by the installed `master-builder` skill (`.claude/skills/master-builder`). **Phase-2a (v0.3.558):**
> place-grounding — code family from jurisdiction + hemisphere/climate band from the georeferenced
> coordinates + the hazard parameters to verify locally. **Phase-2b next:** per-step deep-links wired to
> their tools + a printable brief.

> **The bounded NOW batch shipped v0.3.544–549** — SCOPE-GAP, GOLDEN-THREAD, CLASH-TRIAGE (Navisworks
> XML), GIS-OUT, CBS-1, MEP-GRAPH — plus RT-ORJSON (v0.3.550) and a hardening pass (v0.3.551). Details
> in [CHANGELOG.md](../CHANGELOG.md); the "still open" refinements of each fold into the sprints below.

## ⚡ QUICK-WINS SPRINT — small, no-new-dependency, backend-testable (do these first)

*Each is an S-effort release: a pure engine leaf or a config-module tweak + a thin surface + a test,
grounded in the model we own. No new dependencies; verifiable without the frontend. Ship top-down.*

> **Batch shipped v0.3.552.** All five landed in one sprint release (per the batch-per-sprint cadence),
> each with a targeted test. Details in [CHANGELOG.md](../CHANGELOG.md).

1. ✅ **NORM-VALID tails** *(v0.3.552)* — the conformance gauntlet gained a **STEP-syntax lane**
   (`FILE_NAME` carries a name + timestamp) and a **bSDD/classification-coverage lane** (share of
   physical elements carrying a classification reference; pass ≥ 50%, else warn).
2. ✅ **WARN-1 — model-warnings feed** *(v0.3.552)* — `model_warnings.py` + `GET /models/warnings`
   flattens the hygiene (`model_qa`) + normative-conformance (`norm_valid`) lenses into one worst-first
   punch list (fails before warns, each row with its offender sample for zoom-to-GUID). *Panel is a thin
   follow-up (viewer quick-wins below).*
3. ✅ **DRAW-STATUS — drawing lifecycle** *(v0.3.552)* — the `drawing` module gained a distinct
   **lifecycle** field (*Not Issued → Issued for Construction → Shop Drawing → As-Built*), surfaced in
   the register list, separate from the revision-`status` field.
4. ✅ **SCOPE-GAP spec-section refinement** *(v0.3.552)* — `scope_gap` now unions the CSI spec sections
   each covering package cites (per discipline) and flags `covered_without_specs` — a discipline covered
   by a package citing no spec section (thin, non-traceable coverage), distinct from a true gap.
5. ✅ **GOLDEN-THREAD seed** *(v0.3.552)* — `POST /golden-thread/seed` populates the compliance-evidence
   ledger from the latest model-CI report (each check → a tracked requirement, outcome mapped from
   status); idempotent, so re-seeding after a fresh run only adds what's new.

**Needs a dependency OK (fast once approved):** RT-OXLINT (dev-only lint binary), RT-KNIP (dev-only
dead-code scan), RT-ZSTD (runtime `zstandard` for storage-blob compression). Flagged separately because
each adds a dependency — see the RUNTIME ring below.

**Viewer/UX quick wins (S; frontend — build/typecheck-verifiable, but the preview stall + pane sandbox
limit live click-testing, so these ship with that caveat):** VIEW-TPL (saved view templates) · KEYS-2
(two-letter mnemonic shortcuts) · the WARN-1 / GOLDEN-THREAD / coordination-import panels.

## ⚙️ RUNTIME ring — runtime & tooling upgrades (interleave S-items; measured wins only)

*Rust/C-backed libs + toolchain moves; MIT/BSD/Apache only; each is its own benchmarked release — no
adoption without a measured win.*

- ✅ **RT-ORJSON remainder** *(S, v0.3.550)* — the hot `json.loads/dumps` storage-blob sites (props.json
  index load + scan cache in `model_index`) now use orjson with a stdlib fallback. **Measured 924 KB
  blob: loads 1.7×, dumps 4.8×.** (Response serializer shipped v0.3.511.)
- **RT-OXLINT** *(S)* — [oxlint](https://oxc.rs) (Rust, MIT) as a sub-second pre-lint gate beside the
  pinned eslint 9.39.5 (standalone binary — immune to the Node 20.3.1 pin); eslint stays authoritative.
- **RT-ZSTD** *(S/M)* — zstandard (BSD) for large storage blobs at rest (props.json is MB-scale) →
  faster load + smaller disk/MinIO; transparent magic-prefix wrap in `storage.py`, backward-compatible.
- **RT-KNIP** *(S)* — [knip](https://knip.dev) (ISC) unused-export/dead-dep scan for `apps/web` — the
  evidence stream REL-7 needs; also catches accidental eager imports that grow the shell (guards PANEL-LAZY).
- **RT-UVLOOP** *(S, prod container)* — `--loop uvloop` (+ `httptools`) in the Linux Docker entrypoint;
  pair with a worker-count / keep-alive / `--limit-concurrency` / DB-pool alignment pass.
- **RT-VIRTUAL** *(M · UX)* — [@tanstack/virtual](https://tanstack.com/virtual/latest) (MIT) to
  virtualize the big DOM lists (module tables at 100k+ rows, my-work, boards, model-browser tree);
  removes the "first 500" truncations.
- **RT-BVH** *(S/M, investigate)* — [three-mesh-bvh](https://github.com/gkjohnson/three-mesh-bvh)
  (MIT) for OUR raw-three raycast paths (snap, measure, draft-proxy picking; Fragments' picking stays
  vendor-managed).
- **RT-MSGSPEC** *(S, investigate)* — msgspec (C, BSD-3) typed-Struct decode for the ONE hot blob (the
  per-project property-index load) — only if profiling shows the parse matters; Pydantic v2 stays for API.
- **RT-NODE-LANE → RT-ROLLDOWN** *(M, chain)* — upgrade local Node 20.3.1 → 22 LTS (unpins eslint,
  unlocks Vite 7/8), then trial `rolldown-vite` / Vite 8 (Rust bundler, reported 1.6–7.7× build) in a
  branch — verify the pinned @thatopen pair + PWA/workbox survive before adopting.

*Evaluated, not adopting: Biome (churn > win while eslint pinned) · granian (no measured need) ·
wholesale msgspec/Pydantic swap (Pydantic v2 is Rust-core) · client-side comlink parsing (heavy parse
is server-side by design).*

## 🧵 R15 / R14 tails (open remainders of shipped features)

- **NORM-VALID** — the full **STEP-syntax gauntlet** + a **bSDD-alignment lane** (the header/schema/
  implementer-agreement rules shipped v0.3.535).
- **VERSION-COMPARE per-property** — the iTwin-style old/new value list (needs richer per-version
  property snapshots; the 3D overlay + change labels shipped v0.3.526).
- **IFCPATCH-LIB** — rebase coordinates · unit-convert · merge/split (the purge recipes + SUBSET-EXPORT
  shipped v0.3.527/533).
- **BCF-API-SRV** — attachments over the API + the **BCF 3.0** shape (2.1 core + viewpoints shipped
  v0.3.528–529).
- **SOLVER-OUT** *(flagged)* — additional structural-solver exchange formats (Code_Aster) beyond the
  shipped OpenSees `.tcl` (FEM-EXPORT v0.3.532).

## 🏔 BIG-TICKET SPRINTS — multi-release initiatives (pick one; slice + check in between phases)

*Each is a directional investment that needs real infrastructure, not a single-release slice. Listed so
the shape + first increment of each is clear; open ONE track at a time, ship its first slice, and
reassess. Rough size + the "phase-1" that de-risks it are called out.*

- **SPRINT A — ENERGY & DAYLIGHT (via the jobs lane).** *(L)* Bring EnergyPlus (BSD) + Radiance (LBNL)
  online for defensible annual energy / daylight (DA·ASE·UDI) / glare (DGP). **Phase 1 (no binaries,
  de-risks the whole track):** the **IDF/gbXML envelope export** — model → surfaces/constructions/zones,
  mirroring the shipped FEM-EXPORT pattern. **Phase 2+:** ship the solver binaries through the durable
  job queue and run them; parse results back onto the model.
- **SPRINT B — SCHEDULE OPTIONEERING (ALICE-style).** *(L, flagship differentiator)* Permute crew /
  sequence / zoning over CPM + productivity + Takt and score thousands of scenarios — our inputs are
  uniquely all-present offline.
  - ✅ **Phase 1 — deterministic optioneer** *(v0.3.553)* — `schedule_options.py` + `POST /schedule/
    optioneer`: a bounded crew-loading (2nd crew on the bottleneck trades) + work-face-zoning grid over
    the Takt line-of-balance model, every scenario scored on makespan / cost / peak-congestion, ranked by
    a weighted time+cost score with a Pareto frontier + a recommended option vs. baseline. Pure & tested.
  - ✅ **Phase 2 — widen the search (engine)** *(v0.3.554)* — added **fast-track overlap** (successor
    starts when predecessor is `1-overlap` done, at a rework-risk premium) and opt-in **sequence
    permutation** (reorder `reorderable` trades, fixed trades stay put) as scenario levers, with the grid
    hard-capped at 800 (truncation reported). `overlap=0` reproduces phase-1 exactly.
  - ✅ **Phase 3 — scenario-comparison panel** *(v0.3.555)* — a 🧮 Schedule-optioneering card in the
    Schedule workspace: Run control + weighting selector + fast-track toggle, a recommended-plan summary
    (duration / cost / peak crews / saving vs. baseline), and a ranked scenario table with a Pareto-frontier
    marker and the recommended row highlighted.
  - ✅ **Phase 4a — optimise the real project** *(v0.3.556)* — the optioneer now derives the takt train
    from the project's own `schedule_activity` records (group by trade, per-floor takt = total ÷ floors,
    order by earliest start) instead of always defaulting to the residential train; `trade_source`
    reports body / schedule / default.
  - **Phase 4b** *(next)* — CPM-driven crew shifts off the critical path; scale the enumeration; and a
    Pareto frontier **chart** (cost vs. duration scatter).
- **SPRINT C — FIELD-PWA.** *(L, mostly frontend)* Offline-first mobile PWA: sheet sync, auto
  slip-sheeting, hyperlinked callouts. **Phase 1:** the service-worker offline cache + sheet sync over
  the existing markup/SSE infra; then the field-optimized nav + callout links.
- **SPRINT D — CLIENT-PORTAL.** *(L)* Selections / allowances (choices → price deltas → CO/budget) +
  external read-only stakeholder views. **Phase 1:** a tokenized read-only project digest (KPIs / model
  health / schedule) — needs a share-token model + a public route + a minimal page.
- **SPRINT E — FAB-DELIVER.** *(M/L)* Fabrication outputs from the steel/rebar recipes — assembly/part
  marks, **DSTV-NC**, bolt lists, **BVBS** bending schedules.
  - ✅ **Phase 1 — bending detail** *(v0.3.560)* — the bar-bending schedule now carries per-mark leg
    lengths, bend angles, bend count, and shape family off the authored geometry (`rebar_rules.bending_detail`
    + the BBS route/CSV); the human-read schedule a detailer works from.
  - **Phase 2 — BVBS machine export (GATED)** — the byte-exact BF2D bending file is held behind
    validation against the authoritative BVBS guideline **and** a real importer/validator (a wrong file
    mis-bends real steel — a consequential output, per the fabrication-output doctrine in the skill's
    `construction-delivery.md`). Needs the spec + a validator before it ships. Then **DSTV-NC** for steel.
- **PHOTO-PIN** *(L)* — photo/360 pinning to plan locations + timeline compare (integrate photogrammetry,
  don't build it). **CMMS-OPS** *(L, defer)* — preventive-maintenance plans + work orders on COBie assets.

## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- **REL-3 remainder** *(M)* — `modules.py` DI split (unblocks its CRUD/feeds leaves) · `main.py` ·
  `codecheck.py` · `connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/`massing.py` ·
  `bcf_io.py` · `routers/generate.py`.
- **REL-4 leaves** *(M)* — continue the god-file decomposition: `portal.ts` (next leaf) +
  `viewer/app.ts` leaves.
- **WFE-3** *(M, deferred-by-choice)* — per-project configurable workflow transitions via the config-row
  trick (lower value than the shipped automation).
- **JOB-QUEUE PAdES** *(S, gated)* — PAdES sealing on the queue (needs doc-reference plumbing — defer
  until a queued signing flow exists).
- **REL-6 tail** — cargo-audit / gitleaks in CI when available.
- **REL-7** — evidence-gated dead-code removal (prove-then-delete small batches; RT-KNIP feeds it).

## 🎨 P2 — design & authoring depth (sequence opportunistically)

**Designer workspace:** UX-3 library depth (thumbnails · drag-to-place · pick-host→auto-build ·
appendable IFC libraries · CC0 seed/H1) · UX-4 one-shell layout (Project-Browser spine + docked
Properties + Library + ribbon; a11y/mobile pass).

**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed
egress/life-safety plans (path-trace over the semantic graph) · B3 wall Axis + clip planes · E5
parametric handles · A2 RAG index over ifcopenshell/IFC docs.

**Authoring depth (Wave 10):** W10-2 parametric family generators (profiles + swept/boolean;
build123d/OCP optional track) · W10-9 dimensional constraints (planegcs LGPL; sidecar-solved, baked to
IFC) · W10-5 section/elevation annotation views.

**Finance/frontier:** GEN-SCORE depth (per-option 5D takeoffs + EPD carbon once options carry models) ·
SITE-1 remaining slices (terrain DEM auto-fetch · parcel overlays) · COLLAB selection halos (viewpoint
payload carries `selectedGuid`).

## P3 — gated (each entry names its unblocking event)

*Re-checked 2026-07-19: every gate still holds — none are buildable offline on this machine. What CAN
ship without the gate has shipped; the rest stays honestly gated rather than falsely ✅.*

- **Upstream:** IFC5/IFCX *geometry* write (web-ifc/Fragments write path — the data path ships) · bSI
  Validation Service in CI (service account). Track buildingSMART.
- **Paid / flagged (never core):** VIZ-U1 Unity/Pixyz presentation build · VIZ-3 pixel-streamed
  cinematic · VIZ-4 VR review · W9-7 AI PDF auto-takeoff · CODE-6 licensed code prose · COST-DB cloud
  ingest (massing.cloud manifest/signed bundles/delta/Ed25519 — the offline importers ship) · DWG (ODA)
  / USD (pxr) export.
- **Platform/pipeline:** native mobile Capacitor shell (needs macOS/Xcode + Android pipeline; PWA ships)
  · SOC 2 feature set (KMS/retention/residency — cloud infra) · BMS/IoT telemetry (Brick/Haystack source
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
(reimplement techniques). Deliberate 501 bridges (money movement / KYC / paid APS) are a compliance
pattern, not gaps.

**Not building (from research):** photogrammetry pipelines · learned risk forecasting (Monte Carlo
covers it) · voice agents · all LLM/computer-vision document scanning (non-deterministic; we author the
model). Integrate-not-build: Cesium ion imagery · Speckle Automate hosted runner · iTwin Platform REST ·
Autodesk APS · Pollination.

**License guardrails:** ifcopenshell/geom = LGPL (safe dep) · no AGPL (no PyMuPDF) · planegcs (LGPL,
extractable) over python-solvespace/OpenSCAD (GPL) · CC0/CC-BY assets vetted per-asset · OSM = ODbL
attribution as a separate layer.
