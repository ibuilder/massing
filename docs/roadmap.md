# Roadmap

The single product roadmap — **open items only**, re-prioritized 2026-07-19 at **v0.3.509** after the
execution-queue wave (#0–16 shipped, see the archive). Everything ever shipped lives in
[roadmap-completed.md](roadmap-completed.md), including the v0.3.493–509 queue wave and the
v0.3.457–492 P1/P2 run. Supporting detail: [production-readiness.md](production-readiness.md) ·
[gc-portal.md](gc-portal.md) · [cost-db-import-plan.md](cost-db-import-plan.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
Standing sources: the 2026-07-19 R15 landscape+audit synthesis (execution order), the 🔬 R14 ring
(feature detail), and the REL/quality carry-overs — all audit-discovered items are represented below.

---

## ★ EXECUTION QUEUE — re-prioritized 2026-07-19 at v0.3.509 (current order of work)

**NOW:**
0. ✅ **HARDEN-2 — SHIPPED v0.3.510** — the hand audit over v0.3.495–509 found + fixed 2 security
   issues (S1 job-queue side door around the escalation admin gate → per-kind role map + audit;
   S2 unbounded rule library → count/length caps) and 7 bugs (B1 payload caps kept oldest-not-newest
   rows; B2 QUERY-DSL quoted-operator mis-parse; B3 MSPDI summary-task phantoms; B4/B5 4D player
   empty-timeline crash + no modal-close teardown; B6 Data-QA severity icons; B7 XER project name).
   All test-locked; 275/275 suites; clean categories verified (XSS, XER/MSPDI injection, authz tiers,
   storage keys, escalation idempotency, party_owner consumers).
1. ✅ **MARKUP-2 — COMPLETE v0.3.512–516** — **2a SHIPPED v0.3.512** (scoping note: the editor, server-persisted
   markups + RFI promotion, stamp library, revision register, and presence/SSE all pre-existed — the
   audit line overstated the gap). 2a = the project stamp library wired into the editor picker
   (per-disposition dynamic stamps) + **slip-sheet carry-forward**: markups stamp the register rev at
   save; revising tags `carried_from` (dashed-amber "verify against current revision" pins, never
   dropped). **2b markups grid SHIPPED v0.3.514**; **2c overlay compare SHIPPED v0.3.515**;
   **2d live co-markup SHIPPED v0.3.516** — the markup SSE stream + live pin refresh on every open
   sheet. **MARKUP-2 COMPLETE (v0.3.512–516).** (Sheet-space peer cursors = optional polish on the
   presence roster.)
2. ✅ **XLSX-ROUNDTRIP — SHIPPED v0.3.513** — `GET /model/roundtrip.csv?props=…` (guarded GUID-keyed
   export) → edit in Excel/Sheets → `POST /model/roundtrip/diff` (dry-run: changes + dtype inferred
   from old values + unknown GUIDs) → the new `set_props_by_guid` batch recipe applies the sheet in
   one GUID-stable pass + republish. Viewer "⇄ Property round-trip" tool with a confirm-apply diff
   table. (XLSX read via openpyxl; CSV formula-injection guarded.)
3. ✅ **DXF-EXPORT — SHIPPED v0.3.513 (Sprint 1)** — the composed sheet as R12 CAD entities
   (`GET /drawings/sheet.dxf`, layers BORDER/VIEW-n/ANNO/TITLEBLOCK, `render_sheet_dxf` + dxf.py
   entity builders) + the **↓ DXF** button on every view/sheet. Consultant-contract blocker cleared.
4. ✅ **PERF-4 — COMPLETE v0.3.519 (Sprint 5)** — DASH-UNION ✅514; trade AP → SQL SUM with
   `exclude_states` (NULL-state semantics preserved, equivalence-tested); CV name→id resolution →
   one id-only SQL probe (`find_id_by_field`). The remaining ~100 `limit=100000` sites genuinely
   consume row detail (journals, registers) — not aggregate candidates; convert opportunistically
   only when a site proves to be a pure sum/count.

**NEXT (compound the queue wave — each is a small, verified follow-up):**
5. ✅ **QUERY-DSL wiring — SHIPPED v0.3.513 (Sprint 1)** — clash sides accept selectors:
   `detect(guids_a=, guids_b=)` + `POST /clash?a_q=…&b_q=…` via `query_dsl.select` (bad → 422).
   (Bulk-edit already composes client-side: Query-select GUIDs → `set_props_by_guid`.)
6. ✅ **MODEL-CI-2+3 — COMPLETE v0.3.520 (Sprint 6)** — publish auto-enqueues `model_ci` (✅514);
   the pack is now 5 checks: rules · named · latest-clash · **pinned-IDS contract** (failing spec
   → fail; unpinned → skip) · **quantity drift** (>25% per-class swings vs the previous run →
   warn; baseline lives in the stored report). `ci/run?create_topics=true` → one open coordination
   Topic per failing check (BCF-model round-trip).
7. ✅ **FOURD-SIM-2 — SHIPPED v0.3.513 (Sprint 1)** — planned-vs-actual on the playback: frames carry
   `late_guids`/`early_guids` (actual_finish vs finish), the player tints slipped red / ahead green
   over the amber flash. (The logistics overlay on the play clock stays open — FOURD-SIM-3.)
8. ✅ **RESOURCE-LEVEL-2 — SHIPPED v0.3.513 (Sprint 1)** — `POST /schedule/resource-leveling/apply`:
   one leveling round within CPM float (week-granular, finish never moves, critical never shifts),
   audited; the **⚖ Level** button behind an explicit confirm.
9. ✅ **RULE-LIB-2 — SHIPPED v0.3.519 (Sprint 5)** — `aec_data/geometric_rules.py` on the clash
   broad-phase AABB path: `clearance` (approach space along the thin axis — covers
   clearance-in-front + maintainability access via scope), `escape_distance` (straight-line lower
   bound), `clear_width` (accessible-route 815 mm proxy). `POST /rules/geometry/run` with QUERY-DSL
   scopes + starter defaults; ⛶ viewer tool isolates violators. Swept-path route analysis stays
   out of scope (needs a nav-mesh, not AABBs).
10. ✅ **SURF-2b + SURF-4b** — SURF-2b SHIPPED v0.3.517 (all-packages bid-leveling summary +
    ✉ invite-bidders). SURF-4b SHIPPED v0.3.518: turnover-readiness strip on the Turnover panel
    (certificate ref/signers/record-model lock via `GET /turnover/status`) + 🚦 vendor procurement
    gate on the leveling tab (`GET /procurement/gate` — can-bid/can-bill + blockers). Scan-deviation
    was an overcount (field-verification already surfaced in the viewer). Securities stays flagged
    (regulated).
11. **WFE-3** *(M, deferred-by-choice)* — per-project configurable workflow transitions via the
    config-row trick; revisit after MARKUP-2 (lower value than the shipped automation).

**THEN (R14 Tier-1 feature builds):**
12. ✅ **CX-1 commissioning — SHIPPED v0.3.521 (Sprint 7)** — `cx.py`: model→asset seeding
    (equipment classes, GUID-deduped) + phase-typed checklist seeding with MEP FPT expected values
    (the `commissioning` module already carried the 5 phases — overcount again); `GET /cx/matrix`
    system × phase wall chart; `GET /cx/dossier` per-system package. Turnover panel: ⚡ seed +
    matrix + dossier drill-down. **R14 Tier-1 ring complete.**
13. ✅ **REBAR-RULES + BBS — SHIPPED v0.3.520 (Sprint 6)** — `aec_data/rebar_rules.py`: the
    ACI-envelope rule catalog (column/beam/wall/slab; `column_cage_params` names the governing
    limb), `check_cage` verifies authored cages (bar count + tie spacing; bare column = finding),
    `bar_bending_schedule` groups IfcReinforcingBar into marks with unit mass + tonnage
    (`GET /rebar/bbs` + `.csv`; ✓ + 📋 viewer tools).
14. ✅ **PROC-LOOP — SHIPPED v0.3.520 (Sprint 6)** — 3-way match already existed (audit overcount);
    the genuine deltas landed: `price_observation` module + capture on `level-quotes?record=true` +
    `GET /procurement/price-history` (min/median/max, latest + drift vs median, vendors, series);
    `material_request` module (requested→approved→ordered→delivered) +
    `POST /procurement/material-request/suggest` (QUERY-DSL selection → per-class QTO quantities,
    optional create keyed to GUIDs). Analytics panel: price ledger + suggest→create flow.

**REL/quality carry-overs (interleave one per few releases; all audit-discovered):**
15. ✅ **TEST-GAPS — CLOSED v0.3.521** — audit overcount: 5 of the 6 "untested" engines were
    already covered (clash_intel + permit_check have direct suites; scope_library in
    test_contracts, standards_expert in test_mcp_standards, schedule_viz smoke in test_research).
    The genuine gap — `distwaterfall.scenario` (investor allocation over run_waterfall) — now has
    test_distwaterfall (dollar conservation, pref clearance, pro-rata classes, period synthesis,
    overrides; tier math stays pinned in test_waterfall).
16. **REL-3 remainder** *(M)* — `modules.py` DI split (unblocks its CRUD/feeds leaves) · `main.py` ·
    `codecheck.py` · `connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/
    `massing.py` · `bcf_io.py` · `routers/generate.py`.
17. **REL-4 leaves** *(M)* — continue the god-file decomposition: `portal.ts` (next leaf) +
    `viewer/app.ts` leaves.
18. ✅ **ENTITLE-1 — SHIPPED v0.3.522 (Sprint 7)** — the framework existed (`licensing.require*`,
    enforcement off by default) but only `/source.ifc` + programmatic publish were gated. Wired the
    remaining model-export side-doors (`export.ifc`/`ifcx`/`gltf`/`glb`) so enforcement covers every
    out-path consistently (closes the IFC bypass); fixed the matrix (`glb` was missing from base
    exports → would 402 even at Enterprise; `ifcx` declared Commercial+). Test flips enforcement on
    and verifies each tier boundary. SSO/Navisworks gating deferred (auth-flow-coupled, lower value).
19. ◧ **JOB-QUEUE remainder** — **pid-lock SHIPPED v0.3.523 (Sprint 7)**: `register_kind(mutating=)`
    + a `pid_lock.mutating(project_id)` wrap in the worker dispatch, so a mutating job
    (`escalation_scan`, `model_ci`, future generative runs) can't race a concurrent edit; read/artifact
    kinds stay unwrapped. **Still open:** PAdES sealing on the queue (needs doc-reference plumbing —
    defer until a queued signing flow actually exists).
20. ✅ **CLOUD-BRIDGE — SHIPPED v0.3.524 (Sprint 7, user-directed)** — optional online licence
    validation against massing.cloud (`license_cloud.py`, off by default / offline-first). `POST
    /license/cloud-check` (admin) validates the recorded key via `{base}/validate` + `X-Massing-Secret`
    and applies the cloud-confirmed plan; `☁ Validate online` button in the licence panel. Secret lives
    only in operator config (masked, never returned/logged). Contract: docs/massing-cloud-bridge.md.

**THEN:** the ⚙️ RUNTIME ring below (orjson first — S effort, wide benefit; interleave the S items
between features) · R14 Tier-2/3 + 🧭 R15 remaining tiers (itemized below) — SCOPE-GAP · GOLDEN-THREAD ·
MEP-GRAPH · EST-BANDS · CLASH-TRIAGE · GIS-OUT · KEYS-2 · VIEW-TPL · WARN-1 · DRAW-STATUS · CBS-1 ·
BEP-GEN · ROLES-BIM · PM-CLOSE · SOLVER-OUT · NORM-VALID · VERSION-COMPARE-3D · IFCPATCH-LIB ·
BCF-API-SRV · TRANSMIT-ITP · SMART-VIEWS · MEETINGS · EST-ASSEMBLIES · REVISION-DELTA ·
ENERGY-PLUS · RADIANCE · FEM-EXPORT · FIELD-PWA · CLIENT-PORTAL · FAB-DELIVER · PHOTO-PIN ·
CMMS-OPS · schedule optioneering (ALICE-style, flagship L).

---

## 🧭 R15 ring — landscape gap analysis (2026-07-19; remaining open items)

*Deterministic, offline-capable features (cloud/paid flagged). Licenses mapped: MIT/BSD/Apache/LBNL
studied freely, LGPL reimplemented, AGPL/GPL/proprietary = techniques only. Shipped from this ring:
SCHED-P6 · FOURD-SIM core · QUERY-DSL · RULE-LIB core · RESOURCE-LEVEL named baselines · MODEL-CI
core (v0.3.504–509 — see archive). Open items:*

**Interop & scheduling:** schedule optioneering (ALICE-style: permute crew/sequence/zoning over
CPM+productivity+Takt, score thousands of scenarios — *L, flagship, our inputs are uniquely
all-present offline*).

**Model intelligence & QA:** **NORM-VALID** — normative IFC validation porting the buildingSMART
validation-service checks (STEP syntax, schema propositions, normative rules, bSDD alignment; MIT
reference) as an offline job · ◧ **VERSION-COMPARE-3D** — **in-viewer overlay SHIPPED v0.3.526**:
pick any two versions → added/removed/modified summary + a 3D overlay colouring added green /
modified amber (the `/versions/diff` snapshot data + change labels already shipped). **Still open:**
the per-property old/new value list (iTwin-style) — needs richer per-version property snapshots, not
just the fingerprint hashes stored today · ◧ **IFCPATCH-LIB** — **first recipes SHIPPED v0.3.527**:
`ifcpatch_lib.py` purge-orphan-property-sets + purge-empty-groups (dry-run `GET /model/maintenance`;
apply via the `/edit` republish path; 🧹 viewer tool). **Still open:** extract discipline subset ·
rebase coordinates (georef already covers set-origin) · unit-convert · merge/split.

**Documents & coordination:** ◧ **BCF-API-SRV** — **BCF-API 2.1 core SHIPPED v0.3.528**
(`routers/bcf_api.py`: `/bcf/versions` + `/bcf/2.1/{auth,projects,topics,comments}` mapping onto the
native Topic/Comment rows so Revit/Navisworks/Solibri/BIMcollab sync live). **Still open:**
viewpoints (SHIPPED v0.3.529 — camera/selection/snapshot round-trip) done; attachments over the API +
the BCF 3.0 shape still open · **TRANSMIT-ITP** — numbered
transmittals + Review Matrix routing + supplier-deliverables register + ITP/Test-Plan workflows
(extends the CDE plan) · ◧ **SMART-VIEWS** — **saved presets SHIPPED v0.3.525** (`smart_views.py`:
per-project name + QUERY-DSL selector + isolate/colour/hide, ★ viewer tool; validated + capped).
**SMART-VIEWS clash-freshness SHIPPED v0.3.530** (`coordination_fresh.py` + `/coordination/stale`
[+recheck] — advisory flag, never auto-closes). · **MEETINGS** — meeting series +
minutes + flagged action items linked to RFIs/issues (S).

**Estimating & precon depth:** **EST-ASSEMBLIES** — cost-item assemblies + resource-based rate
build-ups (crew+plant+material per unit rate) + RFQ/quote management inside the estimate ·
**REVISION-DELTA** — 2D drawing overlay diff → changed-quantity flags → estimate delta flow-through
(we have MODEL-DIFF, lack the 2D-revision→cost loop) · CBS view (R14) · EST-BANDS (R14).

**Analysis (permissive-license engines, offline):** **ENERGY-PLUS** — export model → IDF/OSM + run
EnergyPlus (BSD) for defensible annual energy *(L, ship binaries via jobs infra)* · **RADIANCE** —
export → Radiance scenes (LBNL) for annual daylight (DA/ASE/UDI) + glare (DGP) · **FEM-EXPORT** —
analytical model → Code_Aster/OpenSees for third-party verification of the gravity/lateral solver.

**Field & residential (heavier / GTM):** **FIELD-PWA** — offline-first mobile PWA with sheet sync +
auto slip-sheeting + hyperlinked callouts *(L)* · **CLIENT-PORTAL** — selections/allowances (choices
→ price deltas → CO/budget) · **FAB-DELIVER** — fabrication outputs from steel/rebar recipes
(assembly/part marks, DSTV-NC, bolt lists, BVBS bending schedules) · **PHOTO-PIN** — photo/360
pinning to plan locations with timeline compare (integrate photogrammetry, don't build) ·
**CLASH-TRIAGE** (R14) · **GIS-OUT** (R14) · **CMMS-OPS** — preventive-maintenance plans + work
orders on COBie-handover assets (*L, defer*).

**Explicitly not building (flagged from research):** photogrammetry pipelines, learned risk
forecasting (Monte Carlo already covers it), voice agents, and all LLM/computer-vision document
scanning (non-deterministic; we author the model). Cloud/paid to integrate-not-build: Cesium ion
imagery, Speckle Automate hosted runner, iTwin Platform REST, Autodesk APS, Pollination.

## 🔒 Audit findings status (2026-07-19)

**Security:** SEC-XSS (attachments) fixed v0.3.493; SURF-2 innerHTML XSS fixed v0.3.501 (CodeQL
caught it; `esc()` now exported + a standing memory rule). CodeQL 0 open alerts. HARDEN-2 (queue #0)
is the deeper hand pass over the new wave. Previously-verified clean: path containment, defusedxml,
AST-allowlist sandbox, RBAC membership scoping, HMAC signed URLs, production-secret guard.

**Performance:** shipped — ASYNC-BLOCK · GEOM-CACHE · QTO-CACHE · CLASH-JOBS · PANEL-LAZY ·
TEST-FASTPATH · PAYLOAD-CAPS · the 2 frontend leaks. **Open (queue #4):** DASH-UNION · lean-column
schedule load · SQL-aggregate the big-limit analytics.

## ⚙️ RUNTIME ring — runtime & tooling upgrades (researched 2026-07-19; licenses vetted)

*Rust/C-backed libraries + toolchain moves that improve performance, load time, modularization, and
UX with small, verifiable diffs. Every entry passes the license guardrails (MIT/BSD/Apache only).
Interleave the S items between feature releases; each is its own measured, verified release —
benchmark before/after, no adoption without a measured win.*

**Backend (Python):**
- ✅ **RT-ORJSON — SHIPPED v0.3.511** — orjson (Rust) as the default response serializer via our own
  thin `JSONResponse` subclass (FastAPI's `ORJSONResponse` is deprecated; our un-annotated-dict
  majority still renders through the response class). **Measured 7.1–9.4×** vs stdlib (prop-index
  27.5→3.8 ms). `OPT_NON_STR_KEYS` for int-keyed rollups; hash-locked via the lockfile workflow.
  **Remaining (S):** the hot `json.dumps/loads` storage-blob call sites (props.json index load,
  demo snapshot) — measure, then swap.
- **RT-UVLOOP** *(S, prod-container only)* — `--loop uvloop` (+ confirm `httptools`) in the Linux
  Docker entrypoint; a free event-loop win at high connection counts. Windows dev stays on asyncio
  (uvloop is Linux/macOS-only). Pair with a pass on worker count + keep-alive + `--limit-concurrency`
  and DB pool-size alignment (pool exhaustion, not CPU, is the classic outage).
- **RT-MSGSPEC** *(S, investigate)* — msgspec (C, BSD-3) typed-Struct decode for the ONE hot blob:
  the per-project property index load in `model_index`. Only if profiling shows the parse matters;
  Pydantic v2 stays for API models (its Rust core + our validation live there).
- **RT-ZSTD** *(S/M)* — zstandard (BSD) compression for large storage blobs at rest (props.json can
  be MB-scale) → faster load + smaller MinIO/disk; transparent wrap in `storage.py` keyed by a magic
  prefix, fully backward-compatible reads.

**Frontend (JS/TS):**
- **RT-OXLINT** *(S)* — [oxlint](https://oxc.rs) (Rust, MIT) as a fast pre-lint gate beside the
  pinned eslint 9.39.5 (oxlint is a standalone binary — immune to the Node 20.3.1 constraint that
  pins eslint). Sub-second lint on the whole tree locally + in CI; eslint stays authoritative until
  rule parity is proven.
- **RT-NODE-LANE** *(M, unblocker)* — upgrade the local Node toolchain (20.3.1 → 22 LTS): unpins
  eslint, unlocks Vite 7/8. Prereq for RT-ROLLDOWN; needs the "crypto is not defined"/laragon PATH
  cleanup done carefully.
- **RT-ROLLDOWN** *(M, after NODE-LANE)* — trial `rolldown-vite` / Vite 8 (Rust bundler) in a
  branch: reported 1.6–7.7× production-build speedups; verify the pinned
  @thatopen/fragments+components pair + PWA/workbox plugins survive, then adopt.
- **RT-VIRTUAL** *(M · UX)* — [@tanstack/virtual](https://tanstack.com/virtual/latest) (MIT,
  headless, ~10–15kb) to virtualize the big DOM lists: module record tables (mega-projects hold
  100k+ rows), my-work, boards, the model-browser tree. 60fps scrolling where today we render
  bounded slices; removes the "first 500" truncations UX-side.
- **RT-BVH** *(S/M, investigate)* — [three-mesh-bvh](https://github.com/gkjohnson/three-mesh-bvh)
  (MIT) BVH raycasting for OUR raw-three raycast paths (snap engine, measure, draft-proxy picking —
  Fragments' own picking stays vendor-managed). 500-rays/80k-tri @60fps class speedup; only where we
  cast against plain three geometry.
- **RT-KNIP** *(S · modularization)* — [knip](https://knip.dev) (ISC) unused-export/dead-dependency
  scans for apps/web → the evidence stream REL-7 requires (prove-then-delete); also surfaces
  accidental eager imports that grow the shell bundle (guards PANEL-LAZY).

**Explicitly evaluated, not adopted:** Biome (would replace the whole eslint setup — churn > win
while eslint is pinned; oxlint gives the speed without the migration) · granian (replacing
uvicorn/gunicorn is high-risk for no measured need) · wholesale msgspec/Pydantic swap (Pydantic v2
is already Rust-core) · vite-plugin-compression for Pages (GitHub Pages already serves gzip; no .br
control) · comlink/web-workers for client parsing (the heavy parsing is server-side by design).

---

## P2 — next ring (open items; sequence opportunistically)

**Designer workspace:** UX-3 library depth (thumbnails · drag-to-place · pick-host→auto-build ·
appendable IFC libraries · CC0 seed/H1) · UX-4 one-shell layout (Project-Browser spine + docked
Properties + Library + ribbon; a11y/mobile pass).

**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed
egress/life-safety plans (path-trace over the semantic graph) · B3 wall Axis + clip planes ·
E5 parametric handles · A2 RAG index over ifcopenshell/IFC docs.

**Authoring depth (Wave 10):** W10-2 parametric family generators (profiles + swept/boolean;
build123d/OCP optional track) · W10-9 dimensional constraints (planegcs LGPL; sidecar-solved, baked
to IFC) · W10-5 section/elevation annotation views.

**Finance/frontier:** GEN-SCORE depth (per-option 5D takeoffs + EPD carbon once options carry
models) · SITE-1 remaining slices (terrain DEM auto-fetch · parcel overlays) · COLLAB selection
halos (viewpoint payload carries `selectedGuid`).

**Reliability:** REL-6 tail (cargo-audit/gitleaks in CI when available) · REL-7 stays
evidence-gated (prove-then-delete small batches only).

## 🔬 R14 ring — field-research upgrades (2026-07-19; all open)

*Every item reimplements a proven WORKFLOW as a deterministic, offline feature grounded in the model
we own (GUID-everywhere provenance is the structural edge). Techniques only — no code from
unlicensed/proprietary sources.*

**Tier 1 (whitespace / highest leverage — queue #12–14):**
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

**Tier 3 (interop + UX wins):**
- **CLASH-TRIAGE** *(M)* — import external clash reports (Navisworks XML/HTML), filterable triage
  table with zoom-to + linked-model resolution, BCF status round-trip.
- **GIS-OUT** *(S/M)* — lean BIM→GIS export: exterior shell + footprint **GeoJSON in WGS84** (via the
  georef); CityJSON site-context import extending SITE-1.
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
  model-health gates) — always current.
- **ROLES-BIM** *(S)* — BIM-org personas (BIM manager · coordinator · information manager · QA/QC)
  as responsibility-matrix defaults mapped to ISO 19650 duties.
- **PM-CLOSE** *(S)* — project **charter** + **lessons-learned register** modules closing the PMBOK
  process-group spine.
- **SOLVER-OUT** *(S, flagged)* — structural-solver exchange exports of the analytical model for
  desktop solver round-trips.

*Explicitly skipped from this research pass: seed-stage unlicensed contractor-OS apps, parametric
beam/panel modeling cores (our GUID-stable recipes are ahead), and all LLM/computer-vision document
scanning.*

## P3 — gated (each entry names its unblocking event)

*Audited 2026-07-18: every entry below was re-checked and its gate still holds — none are buildable
offline on this machine. What CAN ship without the gate has already shipped; the rest stays honestly
gated rather than falsely ✅.*

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
