# Roadmap

The single product roadmap — **open items only**, re-prioritized 2026-07-18 at **v0.3.456**.
Everything ever shipped (every wave, track, and release) lives in
[roadmap-completed.md](roadmap-completed.md), including the full pre-reprioritization snapshot.
Supporting detail: [production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[cost-db-import-plan.md](cost-db-import-plan.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
The live-verification loop is open (the v0.3.452 fix): viewer work is provable in-environment, so
priorities below favor what that unblocked.

---

## P1 — start now (buildable, live-verifiable, highest value)

1. ✅ **COLLAB-CURSORS — SHIPPED v0.3.458** *(★★★★★)* — per-user colored view-cones + name tags at each
   peer's live camera position (`peerCursors.ts`); the presence beat now shares your viewpoint each
   tick. Live-verified: appear at exact position → track → remove on departure. **COLLAB-1 complete.**
   *(Selection halos = a later nicety; the viewpoint payload would carry a `selectedGuid`.)*
2. ✅ **PREFLIGHT — SHIPPED v0.3.459** *(★★★★)* — the gate now composes all the shipped checks (model
   health · classification · keynotes · drawing-set QA · pinned IDS · open BCF), deep-links each one,
   and gates `POST /drawing-set/issue` (verdict stamped on the record; `enforce` → 409 on HOLD; UI
   🚦 button + ⛔ one-shot override). Also fixed the latent `table()` `innerHTML +=` handler-killer.
3. **SITE-1 first slice — open-geodata site context** *(M · ★★★★)* — drop the georeferenced model onto
   real context: OSM building footprints + parcels as extruded GeoJSON blocks + terrain DEM, as a
   separate reference layer (`gis.ts` loaders ship; this adds the fetch/compose UX). OSM = ODbL
   attribution, separate layer; viewer stays offline-capable (context is opt-in).
4. **UX-2 remaining — snap-as-you-place annotation** *(M)* — SketchUp-style endpoint/midpoint/edge
   snapping + live guide lines while placing notes/dims/tags, extending the shipped `snapEngine`
   (`resolveSnap`/`segmentSnaps` are built and tested; this is the placement-flow wiring).
5. **EST-1 remaining — QTO → durations → CPM** *(M)* — drive labour-estimate activity quantities from
   the real `aec_data.qto` takeoff and write the crew-day durations into the CPM/Gantt schedule.
6. **REL-4 slices 3+ — continue the viewer decomposition** *(M each)* — next leaves out of `app.ts`
   (4,044): the collab/presence block · the KEYS + dyn-input layer · measure/section tools; then
   `main.ts` (1,563) and `portal.ts` (2,542). One live-verified leaf per release.
7. **JOB-QUEUE migration** *(S/M)* — move the heavy inline paths (compiled drawing-set PDF · PAdES
   sealing · large exports · generative runs) onto the shipped durable queue (`jobs.register_kind`),
   returning a job id + poll instead of a long-hanging request.
8. **3D-HERO — package hero image** *(M)* — client screenshot-capture → upload → the project-package
   PDF gets a real 3D hero render (the capture path; headless render stays out of scope).
9. **SHEET-LINK — hyperlinked callouts** *(S · ★★★)* — clickable detail/section bubbles cross-link
   sheets in the SVG/PDF set (sheetgen + the markup layer).

## P2 — next ring (buildable; sequence opportunistically)

**Designer workspace (UX Master Pass):** UX-1 full ribbon merge (physically regroup the ~97 tools;
tab-filtering ships) · UX-3 library depth (thumbnails · drag-to-place · pick-host→auto-build ·
appendable IFC libraries · CC0 seed/H1) · UX-4 assemble the one-shell layout (Project-Browser spine +
docked Properties + Library + ribbon; a11y/mobile pass).

**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed
egress/life-safety plans (path-trace over the semantic graph) · D8 COMcheck/A117.1 → approvability +
BCF · `Pset_Massing_SpecLink` breadcrumb · F0b Box/Axis/FootPrint derivation · B3 wall Axis + clip
planes · B5 fastener/connection assemblies · E2 type-a-dimension (VCB) · E3 sketch-to-BIM push/pull ·
E5 parametric handles · E6 recipe-log design options · E7 live schedules while modeling · E8
model-aware guardrails · A2 RAG index over ifcopenshell/IFC docs.

**Authoring depth (Wave 10/9):** W10-2 parametric family generators (profiles + swept/boolean;
build123d/OCP optional track) · W10-9 dimensional constraints (planegcs LGPL; sidecar-solved, baked to
IFC) · W10-4 coincident-port auto-connect · W10-5 section/elevation annotation views · W10-6 keynote
legend · W9-4 harder half (spec/code document text ingestion → cited NL answers) · W9-5 4D equipment
motion + swept crane clash · W9-6b headcount-program → zones + auto-furnish.

**AI & agents:** S4 multi-step undo grouping · S5 clarifying questions · AI read tools
(quantities/schedules/clashes/violations) · NL-QA recipes ("audit + suggest fixes") · COST-AGENT
(re-estimate on geometry change + learn from history) · READY-AGENT (proactive blockers w/ cited
evidence) · RISK-BOARD (unify the computed hidden risks into one register).

**Finance/frontier:** PROFORMA-LIVE (yield/cost recompute inline as you model) · BOARDS (styled
design-option decks as first-class artifacts) · ENV-1 wind-comfort at massing (approximate, offline) ·
GEN-SCORE depth (per-option 5D takeoffs + EPD carbon once options carry models).

**Estimating/engineering:** MEP pressure-loss balancing + thermal loads + per-conductor tray fill ·
DISC-poché (color-by-discipline 2D) · VIZ-2 three.js PBR presentation mode · VIZ-1 parity confirm.

**Onboarding & codes:** B1 sign-in-first welcome panel (never a wall) · B2 sign-in→tour · A1/A2/C1
provider prominence · B3/B4/C2 fast-follows · CODE-1 adoption-seed depth + per-project jurisdiction ·
CODE-3 auto-resolve edition at /edit · CODE-4 local-amendment overlay.

**Reliability (REL):** REL-3 remainder (`modules.py` DI split · `main.py` · `codecheck.py` ·
`connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/`massing.py` · `bcf_io.py` ·
`routers/generate.py`) · REL-5 remainder (batch FS in `vite.config`/`bundle-budget` · `bridge.py`
dataclass · recipes dedupe) · REL-8 (CI no-cycle check; module-header docs) · REL-6 tail (private-IP
webhook blocking · cargo-audit/gitleaks in CI when available) · REL-7 stays evidence-gated (the bulk
dead-code claim was disproven; only prove-then-delete small batches).

## P3 — gated (each entry names its unblocking event)

- **Upstream:** IFC5/IFCX *geometry* write (web-ifc/Fragments write path — data path ships) · bSI
  Validation Service in CI (service account). Track buildingSMART.
- **Paid / flagged (never core):** VIZ-U1 Unity/Pixyz presentation build · VIZ-3 pixel-streamed
  cinematic · VIZ-4 VR review · W9-7 AI PDF auto-takeoff · CODE-6 licensed code prose · COST-DB cloud
  ingest (massing.cloud manifest/signed bundles/delta/Ed25519 — the offline importers ship) · DWG
  (ODA) / USD (pxr) export.
- **Platform/pipeline:** native mobile Capacitor shell (needs a macOS/Xcode + Android pipeline; PWA
  ships) · SOC 2 feature set (KMS/retention/residency — cloud infra) · BMS/IoT telemetry
  (Brick/Haystack source required) · reality-capture progress quantification (capture data required).
- **Large optional builds (prerequisites complete):** coupled-frame FEM solve · viewer tile-streaming
  upgrade · AR field overlay · per-county location-factor/PPI DB tables.
- **Counsel-gated:** regulated syndication depth (the origination connector ships; licensed stack on
  customer pull). ⚖️ Not legal advice.
- **Environment note:** headless/hidden panes stall the Fragments raycast + web-ifc import *workers*
  (vendor-level; the app-side timeout fallback ships). Verify those two paths in a visible tab.

## Non-goals (documented rationale — not gaps)

`.mpp` parsing (proprietary; XML/CSV import is the path) · custom Revit plugin (certified `revit-ifc`
covers it) · portal core A4/A5 split (deliberate coupling) · live ENERGY-STAR/BAS integrations
(flagged stubs only) · CAFM/1031 tooling · scraping code prose (facts-of-law only) · GPL/AGPL vendor
code (reimplement techniques). Deliberate 501 bridges (money movement / KYC / paid APS) are a
compliance pattern, not gaps.

**License guardrails:** ifcopenshell/geom = LGPL (safe dep) · no AGPL (no PyMuPDF) · planegcs (LGPL,
extractable) over python-solvespace/OpenSCAD (GPL) · CC0/CC-BY assets vetted per-asset · OSM = ODbL
attribution as a separate layer.
