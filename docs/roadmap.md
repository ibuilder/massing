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
3. ✅ **SITE-1 first slice — SHIPPED v0.3.460** *(★★★★)* — Open ▾ → Add site context: OSM buildings
   (height-extruded) + roads + land-use around the georeferenced site, fetched once server-side and
   cached (offline after), ODbL attribution shown. Live-verified: Empire State roof at exactly 443.2 m.
   *(Remaining slices: terrain DEM auto-fetch and parcel overlays — user-supplied GeoTIFF DEMs
   already load via `gis.ts`.)*
4. ✅ **UX-2 remaining — SHIPPED v0.3.461** — every annotation click snaps to the element's
   vertex/midpoint/corner/center (◻ glyph); two-click dimension/cloud flows show an anchor dot +
   dashed rubber guide line to the cursor. Live-verified (corner snap + tracking guide).
5. ✅ **EST-1 remaining — SHIPPED v0.3.462** — the labour estimate prices the measured QTO takeoff
   (`productivity.from_takeoff`, default on `/estimate/labor`), and `/schedule/from-estimate` upserts
   the crew-day durations as FS-chained EST activities into CPM/Gantt (⚙ button in the Schedule
   panel). Live-verified: crews 1→2 halved the durations and CPM went 118 d → 59 d.
6. **REL-4 slices 6+ — continue the viewer decomposition** *(M each)* — ✅ collab/presence (463) ·
   ✅ KEYS + dyn-input (467; app.ts 3,957) · ✅ Report Center → `reportCenter.ts` (468; main.ts
   1,187). Next leaves: measure/section tools · `portal.ts` (2,542). One live-verified leaf per
   release.
7. **JOB-QUEUE migration** *(S/M)* — ✅ the artifact-job pattern + the heaviest path shipped
   v0.3.464 (`compiled_set_pdf` kind + `GET /jobs/{id}/artifact` streaming). Remaining paths to
   migrate onto it: PAdES sealing · large exports (.glb/IFC) · generative runs.
8. ✅ **3D-HERO — SHIPPED v0.3.465** — 📸 in the viewer captures the live canvas → `PUT /hero` →
   the project package opens with a full-bleed 3D hero page. Live-verified (1.27 MB capture,
   package grew to 10 pages with the image embedded).
9. ✅ **SHEET-LINK — SHIPPED v0.3.466** — the compiled set's cover index rows are PDF GoTo links,
   detail callout bubbles link to in-set sheets, and SVG bubbles are `data-sheet` anchors.

## P2 — next ring (buildable; sequence opportunistically)

**Designer workspace (UX Master Pass):** UX-1 full ribbon merge (physically regroup the ~97 tools;
tab-filtering ships) · UX-3 library depth (thumbnails · drag-to-place · pick-host→auto-build ·
appendable IFC libraries · CC0 seed/H1) · UX-4 assemble the one-shell layout (Project-Browser spine +
docked Properties + Library + ribbon; a11y/mobile pass).

**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed
egress/life-safety plans (path-trace over the semantic graph) · D8 COMcheck/A117.1 → approvability +
BCF · `Pset_Massing_SpecLink` breadcrumb · F0b Box/Axis/FootPrint derivation · B3 wall Axis + clip
planes · B5 fastener/connection assemblies · E2 type-a-dimension (VCB) · E3 sketch-to-BIM push/pull ·
E5 parametric handles · E6 recipe-log design options · ✅ E7 live schedules while modeling (473 — `aec:model-published` → open sheets re-render) · ✅ E2
type-a-dimension/VCB (= the dynamic-input layer, v0.3.453/461/467) · E8
model-aware guardrails · A2 RAG index over ifcopenshell/IFC docs.

**Authoring depth (Wave 10/9):** W10-2 parametric family generators (profiles + swept/boolean;
build123d/OCP optional track) · W10-9 dimensional constraints (planegcs LGPL; sidecar-solved, baked to
IFC) · ✅ W10-4 coincident-port auto-connect (478 — `auto_connect_mep` recipe: one sweep wires
coincident segment-end/fitting points with IfcRelConnectsPorts; fittings claim the joints, idempotent) ·
W10-5 section/elevation annotation views · ✅ W10-6 keynote
legend (sheets render the KEYNOTES legend from Track-D codes, test-asserted) · W9-4 harder half (spec/code document text ingestion → cited NL answers) · W9-5 4D equipment
motion + swept crane clash · W9-6b headcount-program → zones + auto-furnish.

**AI & agents:** ✅ S4 multi-step undo grouping (471) · ✅ S5 clarifying questions (shipped: both
planner paths return `needs_clarification`, surfaced in the command bar + Ask panel) · ✅ AI read
tools (472 — model_quantities/computed_schedules/clash_results/code_violations in the MCP catalog) ·
✅ NL-QA recipes (474) · ✅ COST-AGENT (473 PROFORMA-LIVE = re-estimate on change; 475
`/cost/calibration` = learn from awarded/actual history) · READY-AGENT (proactive blockers w/ cited
evidence — ✅ 474, `/schedule/make-ready` cites predecessors' real % + open submittals) ·
✅ RISK-BOARD (v0.3.470 — `/risk-board` unifies 5 engines into one ranked register).

**Finance/frontier:** ✅ PROFORMA-LIVE (473 — `/proforma/live` cached takeoff cost + GFA + budget
delta; the viewer status updates after every load) · ✅ BOARDS (475) · ✅ ENV-1 (476 —
`/env/wind` Lawson screen: corner/downwash/channelling + mitigations, NOT-CFD labelled) ·
GEN-SCORE depth (per-option 5D takeoffs + EPD carbon once options carry models).

**Estimating/engineering:** ✅ MEP pressure-loss balancing + thermal loads + per-conductor tray fill
(477 — `/mep/pressure-loss` empirical-duct + Hazen-Williams rates with per-system index runs ·
`/mep/tray-fill` per-conductor NEC 392.22 from authored cable diameters · `/mep/thermal-loads`
space-by-space W/sf screen vs the block estimate; physics hand-checked in `test_mep_sizing`) ·
✅ DISC-poché (v0.3.469 — `by_discipline` on both plan renderers) · ✅ VIZ-2 presentation FX (477 —
SSAO + bloom EffectComposer on an MSAA target wrapped around render mode; live-verified pass chain) ·
✅ VIZ-1 parity confirmed (476 — live .glb valid glTF 2.0, all geometry classes present;
per-class merge is the documented design).

**Onboarding & codes:** ✅ B1 sign-in-first welcome panel (472 — 🔐 lead row, never walls) · ✅ B2
sign-in→tour (477 — the auth reload resumes into the coach-mark tour via a consumed one-shot flag;
live-verified) · ✅ A1/A2/C1 provider prominence (478 — the sign-in modal leads with big Google +
Microsoft buttons, everything else behind "More sign-in options"; live-verified) · B3/B4/C2
fast-follows · CODE-1 adoption-seed depth (✅ per-project jurisdiction
v0.3.471) · ✅ CODE-3 auto-resolve edition (v0.3.471 — egress + `apply_detailing_rules` cite the
adopted IBC edition) · ✅ CODE-4 local-amendment overlay (477 — `PUT/GET /code/amendments`: validated
per-family edition overrides beat the jurisdiction seed in `_project_ibc_edition` + recorded section
amendments ride the code context; audited, clearable).

**Reliability (REL):** REL-3 remainder (`modules.py` DI split · `main.py` · `codecheck.py` ·
`connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/`massing.py` · `bcf_io.py` ·
`routers/generate.py`) · REL-5 remainder (vite/bundle-budget FS reviewed — already single-pass, no change · `bridge.py`
dataclass · recipes dedupe) · REL-8 (CI no-cycle check; module-header docs) · REL-6 tail (✅ private-IP
webhook blocking 478 — `AEC_WEBHOOK_ALLOW_PRIVATE=0` refuses private/loopback targets, tested ·
cargo-audit/gitleaks in CI when available) · REL-7 stays evidence-gated (the bulk
dead-code claim was disproven; only prove-then-delete small batches).

## P3 — gated (each entry names its unblocking event)

*Audited 2026-07-18 during the P2 sweep: every entry below was re-checked and its gate still holds —
none are buildable offline on this machine tonight. What CAN ship without the gate has already shipped
(the offline COST-DB importers, the PWA, the data-path IFC5 export, the origination connector); the
rest stays honestly gated rather than falsely ✅.*

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
