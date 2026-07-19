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

## ★ EXECUTION QUEUE — re-prioritized 2026-07-19 at v0.3.492 (this is the current order of work)

Synthesized from a full field-research + landscape + audit pass: two agents surveyed the commercial
(Procore/ACC/P6/Solibri/Bluebeam/Aconex/CostX/…) and open-source (Bonsai/Speckle/xeokit/OpenProject/
EnergyPlus/Radiance/…) landscapes; a very-thorough codebase gap review; and security + performance
audits. **Key finding: the backend is far ahead of the frontend** — ~72 shipped capabilities have API
+ client wrappers but no UI surface, and most GC/owner workflow features already exist at the data
level. So the cheapest, highest-leverage value is **surfacing + workflow depth**, not new engines.
Everything below is deterministic + offline unless flagged. Work top-down; each is a verified release.

**NOW (security + perf hygiene + cheapest value):**
0. ✅ **SEC-XSS — SHIPPED v0.3.493-pending** — module-record attachments served inline only for a
   raster-image allowlist; text/html + SVG + blobs forced to `attachment`/octet-stream with
   `nosniff` + `Content-Security-Policy: sandbox` (was stored-XSS on the API origin). Tested.
1. ✅ **PERF-1 (ASYNC-BLOCK) — SHIPPED v0.3.494** — pdf ops + module import parse + large IFC-upload
   writes now `run_in_threadpool` (were stalling the event loop for all users).
2. ✅ **PERF-2 (GEOM-CACHE) — SHIPPED v0.3.494** — `drawings.bake()` memoized per model object;
   `world_bounds()` returns the AABB with no trimesh build; env/wind uses it. (frontend leaks from
   PERF-4 also shipped here: the once-installed guide-line listener + `collabPresence.dispose()`.)
3. **PERF-3 (QTO-CACHE + CLASH-JOBS)** *(M, High)* — cache `qto.takeoff_file` keyed on (mtime, cost-map)
   for the 7 cost endpoints; move `/clash` narrow-phase onto the existing jobs queue.
4. **PERF-4 (PAYLOAD-CAPS + DASH-UNION + TEST-FASTPATH)** *(M, Med)* — paginate `/topics` + `/pins`;
   lean-column single activity load per schedule request; SQL-aggregate the `limit=100000` analytics;
   one UNION-ALL for the 124-query dashboard; fresh-DB skip of `_ensure_columns/_indexes` in `init_db`
   (big CI-time win). Fold in the `buildToolsPanel` pointermove-listener leak + `collabPresence`
   interval cleanup.
5. **PANEL-LAZY** *(M, High-bundle)* — dynamic-import the 16 portal panels out of the eager shell
   (`portal.ts:10-25`) — the single biggest eager-bundle cut, and the CI budget already fights it.

**NEXT (surface the hidden backend — the ~72 orphaned capabilities, in themed UI waves):**
6. **SURF-1 — Schedule/interop surface** *(M)* — UI for XER import, earned-schedule, 4D, schedule
   alerts (all backed, no surface) — pairs with SCHED-P6 export below.
7. **SURF-2 — Estimating/takeoff surface** *(M)* — model-based estimate, resource-based estimate,
   DXF/scan takeoff, QTO-by-floor, bid leveling / invite bidders (backed, no surface).
8. **SURF-3 — Authoring surface** *(M)* — base-plate/shear-tab/curtain-wall/MEP-fitting/rebar-cage/
   assembly/type/detailing-rules/LOD/phase recipes reachable from the rail (backed, no surface).
9. **SURF-4 — QA + RE/ops surface** *(M)* — scan-deviation, model/data QA, code-check, code-adoptions;
   securities package, distributions, turnover status, procurement gate (backed, no surface).

**NEXT (workflow depth — the real backend gap the audit found):**
10. **WORKFLOW-ENGINE** *(L, ★★★★★)* — a real state-machine layer over submittals/RFI/CO/transmittals:
    configurable transitions, ball-in-court routing, overdue escalation, notifications — today these
    are read-side registers with computed columns, not processes.

**NEXT (twice-validated interop gaps — top of BOTH landscape reports):**
11. **SCHED-P6** *(M, ★★★★★)* — P6 XER + MS-Project XML **export/round-trip** (import ships) mapping
    contractor updates back to task GUIDs; the #1 credibility gate with schedulers.
12. **FOURD-SIM** *(M, ★★★★★)* — 4D: element↔activity linking, time-phased playback, planned-vs-actual
    coloring, temp geometry (cranes/laydown) in the viewer — replaces Navisworks TimeLiner + SYNCHRO.
13. **QUERY-DSL** *(M, ★★★★)* — an ifcopenshell-selector/ECSQL-style filter language
    (`IfcWall & Pset_WallCommon.FireRating=2HR & storey=L3`) powering clash scopes, view filters,
    schedules, bulk edits, MCP tools — multiplies every existing feature.
14. **RULE-LIB** *(M, ★★★★)* — a Solibri-style user-authored parametric rule-check library
    (clearance-in-front-of, accessible route, escape distance, maintainability space) with a severity
    matrix, on the existing compliance substrate.
15. **RESOURCE-LEVEL** *(M)* — true resource-loaded scheduling + leveling + multiple named baselines
    with variance (today's leveling is advisory-only).
16. **MODEL-CI** *(M, ★★★★)* — "Automate-lite": rule packs (IDS/clash/code/QTO-delta/custom) auto-run
    on every commit/option-branch save with pass/fail badges + BCF/report artifacts (jobs infra ships).
17. **MARKUP-2** *(M)* — Bluebeam-parity: tool chests, markups-list DB with custom/formula columns,
    overlay compare, slip-sheet markup carry-forward, live co-markup (rides existing presence infra).
18. **XLSX-ROUNDTRIP** *(S)* — IfcCSV-style GUID-keyed property export→edit→re-import with a dry-run
    diff; the single most-used daily openBIM workflow.
19. **DXF-EXPORT** *(S)* — DXF export of generated drawings (PDF-only is a hard consultant-contract
    blocker; That Open has a DXF path to extend).

**THEN (R14 Tier-1 feature builds + the remaining landscape/UX tiers):**
20. **CX-1 commissioning** (R14) · **REBAR-RULES + BBS** (R14) · **PROC-LOOP 3-way match + price
    ledger** (R14) · then R14 Tier-2/3 + R15 Tier-2/3 (transmittals/ITP · assemblies+RFQ ·
    normative IFC validation · EnergyPlus/Radiance adapters · smart-views/auto-resolving issues ·
    meetings module · client-portal selections · fabrication deliverables · BEP-GEN · … see the
    🔬 R14 and 🧭 R15 sections for the full itemized lists).

**REL/quality carry-overs interleaved:** REL-3 remainder (modules.py DI split etc.) · REL-4 portal.ts
+ app.ts god-file leaves · test gaps on the 6 higher-risk untested engines (distwaterfall, clash_intel,
scope_library, standards_expert, schedule_viz, permit_check) · entitlement-tier enforcement.

*The pre-existing P1–P3 sections, the 🔬 R14 ring, and the 🧭 R15 landscape detail below remain the
canonical itemized descriptions; this queue is the ORDER. UI-surfacing (SURF-*) reuses shipped
endpoints, so those releases are frontend-only where the backend already covers them.*

---

## 🧭 R15 ring — landscape gap analysis (2026-07-19: commercial + open-source sweeps + 3 audits)

*Every item is a deterministic, offline-capable feature (cloud/paid dependencies flagged). Licenses
mapped: MIT/BSD/Apache/LBNL studied freely, LGPL reimplemented, AGPL/GPL/proprietary = techniques
only. The two landscape reports strongly cross-validated — P6/MSP interchange, 4D simulation,
model-CI, a query DSL, rule libraries, and markup depth top BOTH lists. Items promoted into the
execution queue above are cross-referenced; the rest are itemized here.*

**Interop & scheduling (highest cross-validated demand):** SCHED-P6 export round-trip (#11) · FOURD-SIM
(#12) · RESOURCE-LEVEL + multi-baseline variance (#15) · schedule optioneering (ALICE-style: permute
crew/sequence/zoning over CPM+productivity+Takt, score thousands of scenarios — *L, flagship, our
inputs are uniquely all-present offline*) · MSP XML import (folds into SCHED-P6).

**Model intelligence & QA:** QUERY-DSL (#13) · RULE-LIB (#14) · MODEL-CI (#16) · **NORM-VALID** —
normative IFC validation porting the buildingSMART validation-service checks (STEP syntax, schema
propositions, normative rules, bSDD alignment; MIT reference) as an offline job · **VERSION-COMPARE-3D**
— per-property old/new change lists (iTwin-style) + in-viewer added/removed/modified overlay between
any two versions/option branches (MODEL-DIFF data ships) · **IFCPATCH-LIB** — one-click maintenance
recipes (purge orphans, optimize, extract discipline subset, rebase coordinates, unit-convert,
merge/split).

**Documents & coordination:** MARKUP-2 (#17) · XLSX-ROUNDTRIP (#18) · DXF-EXPORT (#19) · **BCF-API-SRV**
— server-side BCF-API 3.0 / OpenCDE endpoints so Revit/Navisworks/BIMcollab BCF managers connect live
(spec is open) · **TRANSMIT-ITP** — numbered transmittals + Review Matrix routing + supplier-
deliverables register + ITP/Test-Plan workflows (Aconex parity; extends the CDE plan) · **SMART-VIEWS**
— property-driven saved color/filter presets + clash-bound issues that auto-resolve on model diff
(BIMcollab; cheap glue over MODEL-DIFF + clash) · **MEETINGS** — meeting series + minutes + flagged
action items linked to RFIs/issues (ACC just shipped it; S).

**Estimating & precon depth:** EST-ASSEMBLIES — cost-item assemblies + resource-based rate build-ups
(crew+plant+material per unit rate; Candy/WinEst) + RFQ/quote management inside the estimate (InEight) ·
**REVISION-DELTA** — 2D drawing overlay diff → changed-quantity flags → estimate delta flow-through
(CostX signature; we have MODEL-DIFF, lack the 2D-revision→cost loop) · CBS view (R14) · EST-BANDS (R14).

**Analysis (permissive-license engines, offline):** **ENERGY-PLUS** — export model → IDF/OSM + run
EnergyPlus (BSD) for defensible annual energy, backing the IECC screen with real numbers *(L, ship
binaries via jobs infra)* · **RADIANCE** — export → Radiance scenes (LBNL) for annual daylight
(DA/ASE/UDI) + glare (DGP) · **FEM-EXPORT** — analytical model → Code_Aster/OpenSees for third-party
verification of our gravity/lateral solver (trust unlock).

**Field & residential (heavier / GTM):** **FIELD-PWA** — offline-first mobile PWA with sheet sync +
auto slip-sheeting + hyperlinked callouts *(L; Fieldwire/PlanGrid wedge)* · **CLIENT-PORTAL** —
selections/allowances (choices → price deltas → CO/budget; Buildertrend residential moat) ·
**FAB-DELIVER** — fabrication outputs from steel/rebar recipes (assembly/part marks, DSTV-NC, bolt
lists, BVBS bending schedules; Tekla-adjacent, no web platform does this) · **PHOTO-PIN** — photo/360
pinning to plan locations with timeline compare (integrate OpenSpace/DroneDeploy for photogrammetry
rather than build) · **CLASH-TRIAGE** (R14) · **GIS-OUT** (R14) · **CMMS-OPS** — preventive-maintenance
plans + work orders on COBie-handover assets (openMAINT territory; the 50-year phase; *L, defer*).

**Explicitly not building (flagged from research):** photogrammetry pipelines, learned risk forecasting
(nPlan's data moat — Monte Carlo already covers it), voice agents over capture history, and all
LLM/computer-vision document scanning (non-deterministic; we author the model, so we never
reverse-engineer PDFs). Cloud/paid to integrate-not-build: Cesium ion imagery, Speckle Automate hosted
runner, iTwin Platform REST, Autodesk APS, Pollination.

## 🔒 Audit findings (2026-07-19 — fold into the NOW queue)

**Security** (one concrete finding; codebase otherwise well-hardened — path containment, defusedxml,
AST-allowlist sandbox, RBAC membership scoping, HMAC signed URLs, production-secret guard all verified
clean): ✅ SEC-XSS fixed (queue #0). No other exploitable issue surfaced.

**Performance** (ranked, → queue #1-5): GEOM-CACHE, ASYNC-BLOCK, QTO-CACHE, CLASH-JOBS, PANEL-LAZY,
DASH-UNION, PAYLOAD-CAPS, TEST-FASTPATH + the two frontend leaks. See the NOW block for the ordered
plan; all are deterministic refactors with no coverage loss.

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
   1,187) · ✅ measure/section → `measureSection.ts` (481; app.ts 3,948, order/behaviour
   live-verified). Next leaf: `portal.ts` (2,542). One live-verified leaf per release.
7. **JOB-QUEUE migration** *(S/M)* — ✅ the artifact-job pattern + the heaviest path shipped
   v0.3.464 (`compiled_set_pdf` kind + `GET /jobs/{id}/artifact` streaming) · ✅ large geometry
   exports (487 — `model_export` .glb/.gltf artifact job, glTF-magic verified). Remaining: PAdES
   sealing (needs the doc-reference plumbing) · generative runs (mutating jobs need the pid lock).
8. ✅ **3D-HERO — SHIPPED v0.3.465** — 📸 in the viewer captures the live canvas → `PUT /hero` →
   the project package opens with a full-bleed 3D hero page. Live-verified (1.27 MB capture,
   package grew to 10 pages with the image embedded).
9. ✅ **SHEET-LINK — SHIPPED v0.3.466** — the compiled set's cover index rows are PDF GoTo links,
   detail callout bubbles link to in-set sheets, and SVG bubbles are `data-sheet` anchors.

## P2 — next ring (buildable; sequence opportunistically)

**Designer workspace (UX Master Pass):** ✅ UX-1 full ribbon merge (491 — sections physically
regrouped into Build → Analyze & Coordinate → Document → Data DOM clusters with phase headers;
data-phase filtering, four real tabs, stale-tab migration; live-verified) · UX-3 library depth
(thumbnails · drag-to-place · pick-host→auto-build · appendable IFC libraries · CC0 seed/H1) ·
UX-4 assemble the one-shell layout (Project-Browser spine + docked Properties + Library + ribbon;
a11y/mobile pass).

**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed
egress/life-safety plans (path-trace over the semantic graph) · ✅ D8 COMcheck/A117.1 → approvability +
BCF (480 — WWR vs the IECC prescriptive cap · envelope U-value coverage · accessible entrance, all in
the pre-flight; `POST /codecheck/approvability/bcf` promotes failures to GUID-anchored topics) · ✅ `Pset_Massing_SpecLink` breadcrumb (479 — `set_spec_link` recipe + `/spec-links` rollup) ·
✅ F0b Box/Axis/FootPrint derivation (479 — `derive_representations`: bounds-true IfcBoundingBox +
mid-thickness Axis + FootPrint rectangle into the F0 subcontexts, idempotent) · B3 wall Axis + clip
planes · ✅ B5 fastener/connection assemblies (490 — `add_connection_assembly` plate+bolts +
IfcRelConnectsWithRealizingElements + `connection_summary` browser) · E2 type-a-dimension (VCB) ·
✅ E3 sketch-to-BIM push/pull (488 —
`extrude_profile` closed-sketch → extruded element + `set_extrusion_depth` in-place pull, both
tessellation-verified GUID-stable recipes) ·
E5 parametric handles · ✅ E6 recipe-log design-option branches (483 — `model_options.py`:
snapshot/list/activate/diff/delete named whole-model branches; activate is one undo step) ·
✅ E7 live schedules while modeling (473 — `aec:model-published` → open sheets re-render) · ✅ E2
type-a-dimension/VCB (= the dynamic-input layer, v0.3.453/461/467) · ✅ E8
model-aware guardrails (483 — `guards.model_precheck` in apply_recipe: storey exists, host is a
wall, GUIDs resolve, connect ends have ports; batches exempt by design) · A2 RAG index over
ifcopenshell/IFC docs.

**Authoring depth (Wave 10/9):** W10-2 parametric family generators (profiles + swept/boolean;
build123d/OCP optional track) · W10-9 dimensional constraints (planegcs LGPL; sidecar-solved, baked to
IFC) · ✅ W10-4 coincident-port auto-connect (478 — `auto_connect_mep` recipe: one sweep wires
coincident segment-end/fitting points with IfcRelConnectsPorts; fittings claim the joints, idempotent) ·
W10-5 section/elevation annotation views · ✅ W10-6 keynote
legend (sheets render the KEYNOTES legend from Track-D codes, test-asserted) · ✅ W9-4 harder half (486 — `doc_text.py`: PDF/text ingestion, section-header chunking with pages,
deterministic cited retrieval, extractive `/doctext/ask` + the `/rfi/qa` document fallthrough) · ✅ W9-5 4D equipment
motion + swept crane clash (485 — `position_at` walks paths by schedule progress; `/logistics/clash`
flags intersecting swing discs with the worst date + under-hook resources) · ✅ W9-6b
headcount-program → zones + auto-furnish (484 —
`program_fit`: largest-first allocation, Pset_Massing_Program zones, furnish-to-seat-count,
honest short_by reporting).

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
Microsoft buttons, everything else behind "More sign-in options"; live-verified) · ✅ B3/B4/C2
fast-follows (479 — role picker on first signed-in boot · tour confirmed at the 5-step cap ·
one-shot "sign in to save your work" nudge on a signed-out publish; live-verified) · CODE-1 adoption-seed depth (✅ per-project jurisdiction
v0.3.471) · ✅ CODE-3 auto-resolve edition (v0.3.471 — egress + `apply_detailing_rules` cite the
adopted IBC edition) · ✅ CODE-4 local-amendment overlay (477 — `PUT/GET /code/amendments`: validated
per-family edition overrides beat the jurisdiction seed in `_project_ibc_edition` + recorded section
amendments ride the code context; audited, clearable).

**Reliability (REL):** REL-3 remainder (`modules.py` DI split · `main.py` · `codecheck.py` ·
`connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/`massing.py` · `bcf_io.py` ·
`routers/generate.py`) · ✅ REL-5 COMPLETE (481 — `bridge.py` plan/execute → typed
Plan/ExecutionResult dataclasses · `recipes.py` storey-lookup dedupe · vite/bundle-budget FS was
already single-pass) · ✅ REL-8 COMPLETE (487 — all 359 modules carry header docstrings, now
ENFORCED in test_import_cycles beside the no-cycle guard) · REL-6 tail (✅ private-IP
webhook blocking 478 — `AEC_WEBHOOK_ALLOW_PRIVATE=0` refuses private/loopback targets, tested ·
cargo-audit/gitleaks in CI when available) · REL-7 stays evidence-gated (the bulk
dead-code claim was disproven; only prove-then-delete small batches).

## 🔬 R14 ring — field-research upgrades (2026-07-19: 13 infographics + 10 tools/products studied)

*Every item reimplements a proven WORKFLOW as a deterministic, offline feature grounded in the model
we own (GUID-everywhere provenance is our structural edge over the AI-first equivalents). Techniques
only — no code from unlicensed/proprietary sources; MIT/LGPL references studied, never pasted.*

**Tier 1 (whitespace / highest leverage):**
- **CX-1 — Commissioning module** *(L · ★★★★★)* — the lifecycle gap after punch/turnover: an asset
  registry **auto-derived from the model** (every MEP equipment class → a commissionable asset), a
  `cx_test` module with phase-typed checklists (pre-functional · functional-performance · integrated,
  from curated templates keyed to IFC class × discipline), the **system × phase completion matrix**
  panel, MEP-sizing design values as the FPT *expected-value* columns (a loop only a model-owning
  platform can close), and a per-system commissioning dossier via reports/sheetgen.
- **REBAR-RULES — per-typology reinforcement rules + BBS** *(M/L · ★★★★★)* — extend the rebar-cage
  recipe into a detailing-rule catalog (column ties/laps · beam stirrup zones from the shear envelope ·
  wall/opening trim + corner bars · footing mats), inputs = element + solver results, outputs =
  GUID-stable cage edits **stamped with the calc-run** (stale-cage flag on re-solve), plus a **bar
  bending schedule** (shape codes, cut lengths, weights) feeding 5D tonnage and S-sheets.
- **PROC-LOOP — procurement close-the-loop** *(M · ★★★★)* — deterministic **3-way match** (PO lines
  vs delivery records vs invoice lines, discrepancy flags) + a **price-observation ledger**: every
  priced quote/PO line becomes a dated observation per cost-DB item (trend/volatility, "your last 5
  purchases" surfaced at estimate time) + field material-requests keyed to QTO lines/GUIDs.

**Tier 2 (extends existing engines):**
- **SCOPE-GAP — bid-scope coverage + citations** *(M · ★★★★)* — QTO divisions vs bid-package scope
  coverage (uncovered elements / spec sections with no quantities → flagged gaps), a per-trade
  **scope/bid-form export where every line cites GUIDs + sheet + spec section** (click-to-highlight),
  and schedule-vs-model count reconciliation.
- **GOLDEN-THREAD — compliance evidence ledger** *(M · ★★★★)* — persist every code/approvability
  check outcome → responsible person → evidence artifact (drawing rev · doc · photo) → sign-off,
  versioned across the lifecycle (extends preflight + ISO 19650 codes); **check-scoping matrix**
  (building type × new-build/refurb/change-of-use activates rule packs); tolerant-geometry fallbacks
  so checks degrade gracefully on imported, poorly-classified IFC.
- **MEP-GRAPH — connector-topology graph + parallel runs** *(M · ★★★★)* — a first-class port-graph
  over IfcDistributionPort (proper path extraction → pressure-loss index runs become real paths),
  **parallel/stacked run generation** (trace a run → offset the path → re-intersect at bends →
  regenerate fittings; the multi-service rack workflow), nearest-open-connector matching hardening
  auto_connect.
- **EST-BANDS — range estimates + firm rate sheets** *(S/M · ★★★)* — low/likely/high bands per QTO
  line rolled to a bid range (pairs with the Monte Carlo risk engine) + a firm **rate-sheet overlay**
  on the localized cost vintages.

**Tier 3 (interop + UX wins from the infographic set):**
- **CLASH-TRIAGE** *(M)* — import external clash reports (Navisworks XML/HTML), filterable triage
  table with zoom-to + linked-model resolution, BCF status round-trip.
- **GIS-OUT** *(S/M)* — lean BIM→GIS export: exterior shell + footprint **GeoJSON in WGS84** (via the
  georef) — the <10%-size site-context artifact; CityJSON site-context import extending SITE-1.
- **KEYS-2** *(S)* — two-letter mnemonic shortcuts (WA wall · DR door · CS section · TH temp-hide …)
  layered on the command line, discoverable via a cheat-sheet overlay.
- **VIEW-TPL** *(S)* — saved **view templates** (camera + layers + color mode + section state) applied
  per view/sheet for consistency.
- **WARN-1** *(S)* — a persistent **model-warnings panel** (hygiene findings by type, count-badged,
  click-to-elements) elevating model_qa from a report to a workflow.
- **DRAW-STATUS** *(S)* — drawing-register lifecycle status (**Issued-for-Construction → Shop →
  As-Built**) with shop-drawing ↔ submittal linkage.
- **CBS-1** *(S/M)* — a Cost Breakdown Structure view over estimates: direct / indirect /
  **contingency / management reserve / taxes & fees** layers with hierarchical rollup.
- **BEP-GEN** *(M)* — generate the **BIM Execution Plan** from the project's LIVE configuration
  (pinned IDS, CDE folders, classification systems, roles/responsibility matrix, exchange formats,
  model-health gates) — the "information framework, not just a 3D model" deliverable, always current.
- **ROLES-BIM** *(S)* — BIM-org personas (BIM manager · coordinator · information manager · QA/QC)
  as responsibility-matrix defaults mapped to ISO 19650 duties.
- **PM-CLOSE** *(S)* — project **charter** + **lessons-learned register** modules closing the PMBOK
  process-group spine (initiate/close were thin).
- **SOLVER-OUT** *(S, flagged)* — structural-solver exchange exports of the analytical model for
  desktop solver round-trips.

*Explicitly skipped from this research pass: seed-stage unlicensed contractor-OS apps (nothing beyond
what the module engine ships), parametric beam/panel modeling cores (our GUID-stable recipes are
ahead), and all LLM/computer-vision document scanning (non-deterministic; we author the model, so we
never reverse-engineer PDFs).*

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
