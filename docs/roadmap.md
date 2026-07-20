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

## ★ NOW — freshly prioritized bounded work (backend-testable first)

*Each is a small, verifiable release grounded in the model we own (GUID-everywhere provenance). Ship
top-down; interleave one RUNTIME-ring S-item every few features.*

1. ◧ **SCOPE-GAP — bid-scope coverage + GUID citations** *(M · ★★★★)* — **discipline-level coverage
   SHIPPED v0.3.544** (`scope_gap.py` + `GET /bidding/scope-gap`: model takeoff by NCS discipline vs
   `bid_package` claims → covered % + gaps with sample GUIDs + over-scoped packages; Model-coverage strip
   in the Bidding view). **Still open:** spec-section-level refinement · a per-trade scope/bid-form
   export where every line cites GUIDs + sheet + spec section · schedule-vs-model count reconciliation.
2. ◧ **GOLDEN-THREAD — compliance evidence ledger** *(M · ★★★★)* — **ledger + rollup SHIPPED v0.3.545**
   (`compliance_evidence` module: requirement → outcome → responsible → evidence → sign-off workflow;
   `golden_thread.py` + `GET /golden-thread`: signed-off % + outcome/category spread + risk-ranked
   broken-thread list). **Still open:** seed the ledger from the live preflight/code findings · a
   dedicated rollup panel · the check-scoping matrix (building type × new-build/refurb/change-of-use) ·
   tolerant-geometry fallbacks for imported, poorly-classified IFC.
3. ◧ **CLASH-TRIAGE — import external clash reports** *(M)* — **XLSX importer already shipped; native
   Navisworks XML added v0.3.546** (`clash_import.parse_clash_xml`/`import_clash_xml` + `POST
   /coordination/import-xml`: `<clashresult>` → coordination_issue, GUIDs harvested from clashobjects,
   defusedxml-hardened; each round-trips to BCF). **Still open:** an in-app coordination-import UI panel
   (both formats) · a filterable triage table with zoom-to · HTML-report format.
4. ◧ **GIS-OUT — lean BIM→GIS export** *(S/M)* — **footprint→WGS84 GeoJSON SHIPPED v0.3.547**
   (`gis_out.to_geojson` + `GET /models/footprint.geojson`: footprint bbox + site point anchored on the
   IfcSite lat/long via an equirectangular transform; the inbound CityGML→GeoJSON site-context import
   already shipped). **Still open:** the true exterior-shell polygon (vs bbox) · pyproj-grade reprojection
   from the projected CRS · a viewer map-overlay surface.
5. **CBS-1 — Cost Breakdown Structure view** *(S/M)* — direct / indirect / **contingency / management
   reserve / taxes & fees** layers over estimates with hierarchical rollup.
6. **MEP-GRAPH — connector-topology graph + parallel runs** *(M · ★★★★)* — a first-class port-graph
   over `IfcDistributionPort` (real path extraction → pressure-loss index runs become true paths),
   parallel/stacked run generation (trace → offset → re-intersect at bends → regenerate fittings), and
   nearest-open-connector hardening for `auto_connect`.
7. **EST-ASSEMBLIES depth** *(S/M)* — persist user-authored assemblies (a module) + wire assemblies
   into the model takeoff estimate + RFQ/quote management (builds on the shipped `assemblies_cost`).

**Viewer/UX quick wins (S; frontend — verify what the preview stall allows, flag the rest):**
- **WARN-1** — a persistent **model-warnings panel** (hygiene findings by type, count-badged,
  click-to-elements) elevating `model_qa` / NORM-VALID from a report to a workflow.
- **DRAW-STATUS** — drawing-register lifecycle status (**IFC → Shop → As-Built**) with shop-drawing ↔
  submittal linkage.
- **VIEW-TPL** — saved **view templates** (camera + layers + colour mode + section state) per view/sheet.
- **KEYS-2** — two-letter mnemonic shortcuts (WA wall · DR door · CS section · TH temp-hide …) on the
  command line, discoverable via a cheat-sheet overlay.

## ⚙️ RUNTIME ring — runtime & tooling upgrades (interleave S-items; measured wins only)

*Rust/C-backed libs + toolchain moves; MIT/BSD/Apache only; each is its own benchmarked release — no
adoption without a measured win.*

- **RT-ORJSON remainder** *(S)* — swap the hot `json.dumps/loads` storage-blob call sites (props.json
  index load, demo snapshot) to orjson (the response serializer already shipped, 7–9×).
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

## 🚀 Flagship-L — multi-release directional builds (sequence deliberately)

*Each needs real infrastructure (jobs + shipped binaries, a mobile PWA lane, an external-stakeholder
portal). Not single-release slices — open one track at a time and slice it.*

- **schedule optioneering (ALICE-style)** — permute crew/sequence/zoning over CPM + productivity + Takt,
  score thousands of scenarios. Our inputs are uniquely all-present offline; the flagship differentiator.
- **ENERGY-PLUS** — export model → IDF/OSM + run EnergyPlus (BSD) for defensible annual energy (ship
  binaries via the jobs infra). *First slice: the IDF geometry/envelope export (mirrors FEM-EXPORT).*
- **RADIANCE** — export → Radiance scenes (LBNL) for annual daylight (DA/ASE/UDI) + glare (DGP).
- **FIELD-PWA** — offline-first mobile PWA with sheet sync + auto slip-sheeting + hyperlinked callouts.
- **CLIENT-PORTAL** — selections/allowances (choices → price deltas → CO/budget); external read-only
  stakeholder views.
- **FAB-DELIVER** — fabrication outputs from the steel/rebar recipes (assembly/part marks, DSTV-NC,
  bolt lists, BVBS bending schedules).
- **PHOTO-PIN** — photo/360 pinning to plan locations with timeline compare (integrate photogrammetry,
  don't build it).
- **CMMS-OPS** — preventive-maintenance plans + work orders on the COBie-handover assets *(defer)*.

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
