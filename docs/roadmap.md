# Roadmap

The single product roadmap — **open items only**, reconciled + re-prioritized **2026-07-21 at v0.3.571**
(a broad research pass on the construction-software field added the 🔬 R16 ring and re-topped the NOW list).
Everything ever shipped lives in
[roadmap-completed.md](roadmap-completed.md); per-release detail is in [CHANGELOG.md](../CHANGELOG.md).
Supporting detail: [production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[cost-db-import-plan.md](cost-db-import-plan.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
The R15 ring is closed and both flagship offline-verifiable sprints (Schedule Optioneering, Client-Portal)
are driven several phases deep; the **master-builder skill** is installed and co-evolves with the platform.
What remains is bounded R14/R15 tail depth, the big-ticket continuations, a runtime/tooling ring, and the
decomposition/design carry-overs.

**Status:** CodeQL 0 open alerts · full backend suite green (316 suites) · single-source version in
`apps/web/package.json` (v0.3.589).

**Recently merged (open-PR cleanup, v0.3.586–589):** the production-readiness PRs landed — **security +
performance hardening**, **operational hardening** (opt-in `/metrics` auth), **dependency hygiene**
(digest-pinned Docker base images), and the **observability stack**: **Alembic DB migrations** (C1,
baseline + drift-guard CI), **OpenTelemetry tracing** (C2) and **Sentry error alerting** (C3), all
env-gated no-ops until configured. The stale-branch backlog was cleaned (117 → 4 local branches; all work
already in main) and the GitHub Pages were re-skinned to one branded theme. Risky major upgrades (runtime
stack, thatopen/TS/Vite/ESLint/Capacitor majors, numpy 2.x) held for a deliberate later pass.

---

## ▶ NOW — bounded, backend-testable, no new dependency (ship top-down)

*Each is an S/M release: a pure engine leaf or a config-module tweak + a thin surface + a test, grounded
in the model we own. Verifiable without the frontend. These are the cleanest next wins.* **The top three
are R16 Tier-1 picks (see the R16 ring below for full specifics).**

- ✅ **MARGIN-CBS** *(R16; v0.3.573)* — per-cost-code reconciliation (budget vs committed vs actual vs
  billed → buyout margin + variance, over-committed/over-budget flags) at `GET /margin/by-costcode` + the
  📒 Cost-code Margin money card.
- ✅ **ASSET-REG** *(R16; v0.3.574)* — the maintainable-asset register derived from the IFC
  (`GET /model/assets` + a seed into the `asset_register` module) + the 🔧 Asset Register panel. Next: PM
  scheduling depth off the shipped `pm_schedule` module.
- ◧ **★ RECIPE-MACROS** *(R16; phase-1 v0.3.575)* — ✅ save a chained edit-recipe as a named,
  parameterized command: `macros.py` (`expand()` = model-free `${param}` substitution + defaults, type
  preserving) + `GET/PUT /macros` (recipe names validated vs the edit registry at save) + `POST
  .../{id}/expand` (preview) + `POST .../{id}/run` (whole chain as ONE GUID-stable version, single undo) +
  client plumbing + `test_macros`. **Remaining:** mirror macro-run into CADCMD/MCP + a headless `massing`
  CLI with `massing check` as a CI gate.

1. ~~**VERSION-COMPARE per-property**~~ — ✅ **changed-property *names*** shipped v0.3.570 (`diff` now
   names the exact Pset/Qto keys that changed, tagged added/removed/changed). The old/new **values** still
   need a richer per-version snapshot (a stored-column follow-up).
2. **IFCPATCH-LIB** — rebase coordinates · unit-convert · merge/split recipes (the purge recipes +
   SUBSET-EXPORT shipped v0.3.527/533). Pure ifcopenshell transforms behind edit-recipe gating.
3. **BCF-API-SRV depth** — attachments over the API + the **BCF 3.0** shape (2.1 core + viewpoints shipped
   v0.3.528–529).
4. ✅ **SPRINT D phase-3c — selections money card** *(v0.3.569)* — a ◈ Selections destination: net
   over/under, per-category deltas, the over-allowance CO candidates + a push-to-change-events button.
5. **SPRINT B phase-4b** — ✅ the Pareto-frontier **chart** (cost vs. duration scatter) shipped on the 🧮
   panel *(v0.3.571)*. Remaining: CPM-driven crew shifts off the critical path + scale the enumeration.
6. ✅ **SPRINT MB — per-step deep-links** *(v0.3.584)* — each Master Builder brief step now carries a
   portal `dest`; the 🏛 panel renders a "→ Close this gap" button that jumps to the tool (nav-map:
   place→model-analysis · program→program · feasibility→budget · regulatory→standards · design→model-QA ·
   delivery→schedule · risk→risk-review · handover→turnover), via a new `PanelContext.navigate`.

## 🔬 R16 — external-scan upgrades (2026-07-21)

Synthesized from a broad research pass on the construction-software field. **Recurring strategic
edge:** a large share of the field spends its core AI budget *reconstructing structured data from
unstructured inputs* (prose→plan, PDF→takeoff, email→line-items, bid-doc→equipment). Because **IFC is our
source of truth**, we skip that whole problem and invest the same effort in deterministic
scoring/optimization/validation on data we already hold — via the `rule_library.py` + `query_dsl.py`
selector/rule spine and the `schedule_options.py` optioneer pattern, which recur as the implementation
vehicle across almost every item. BUILD = deterministic/offline/we-own-it · INTEGRATE = optional
feature-flagged connector (never a runtime dep) · SKIP = conflicts with a constraint/non-goal.

**Tier 1 — flagship, high-value, reuse proven engines:**
- ◧ **MASSING-OPT — layout optioneer** *(L; phase-1 v0.3.576).* The literal "Massing" play. ✅
  `layout_options.py` `optioneer()` deterministically sweeps envelope levers (floor-to-floor · core
  efficiency · coverage strategy · unit size) over `massing.compute_massing`, scores each by a transparent
  yield-on-cost proforma, and ranks by objective + a Pareto cost-vs-profit frontier → `POST
  /massing/optioneer` (stateless) + client + ✅ the **🧮 Massing Optioneer portal panel** *(v0.3.582)*
  (envelope form → ranked options + frontier). **Remaining:** emit each option as a **GUID-stable
  edit-recipe chain** (blank IFC → levels/grid → walls/slabs).
- **MARGIN-CBS — per-cost-code live margin rollup** *(M).* One reconciliation view keyed on the
  CBS/cost-code (`CBS-1` shipped) that computes **committed vs. billed vs. earned margin** per cost code
  from one quantity record, tying QTO → pay-apps → actuals. `GET /projects/{pid}/margin/by-costcode` (reuse
  the where-aggregate SQL-helper shape) surfaced as a portal money card like the selections card. Closest
  fit to the GC portal; highest-value GC item in the scan.
- ✅ **ASSET-REG** *(v0.3.574)* + **PM-OPS — asset register + preventive maintenance** — the concrete first
  slice of the deferred CMMS-OPS. `GET /model/assets` deterministically derives the maintainable-asset
  register from the IFC by class (`classification.py` + `query_dsl.py`), GUID-keyed; a `pm_task` config
  module (asset-GUID link, PPM interval, last/next-due, warranty, spares, O&M docs via `docmanager.py`); +
  round-trip COBie export from the register. Extends the design-to-turnover lifecycle into operations, no
  new infra. (IFC = source of truth: FM data derives from the model, never a parallel sheet.)
- ◧ **MEP-EQUIP + SPEC-CONFLICT — equipment procurement + spec-vs-model conflict** *(M; phase-1 v0.3.580).*
  ✅ `equipment.py` + `GET /model/equipment` derives the equipment schedule straight from the IFC
  (`IfcEnergyConversionDevice`/`IfcFlowMovingDevice`/`IfcFlowTerminal`… subtype-resolved) — **no
  doc-scanning, because we own the model** — grouping procurable units by (class, type) into **RFQ
  line-items with a quantity + representative spec** (from the Psets) + GUIDs; ducts/pipes/controls
  excluded. Client `modelEquipment`. ✅ **SPEC-CONFLICT** *(phase-2 v0.3.581)* — `equipment.spec_conflicts`
  + `POST /model/equipment/spec-check` cross-checks each scheduled line's Pset values against a
  specified-requirement set (`{ifc_class: {spec_key: expected}}`) → conflicts + missing (the "air-cooled
  schedule vs water-cooled spec" catch), deterministic. ✅ the **🔩 Equipment schedule portal panel**
  *(v0.3.582)*. **Remaining:** tie into submittals + budget/GMP + QTO as an RFQ package + a curated starter
  requirement set + an in-panel spec-conflict view.
- **RECIPE-MACROS + headless `massing` CLI** *(M/L; three independent sources converge here).* Save a
  chained sequence of edit-recipes as a **named, parameterized,
  shareable command** with a typed-variable schema (`POST /macros`, `POST /macros/{key}/run`), executed as an
  **ordered, resumable background job** (reuse job-artifacts) through the **model-diff plan/preview/apply
  gate**. Surface the SAME registry across three faces — the viewer **CADCMD** line, the **MCP** tools, and a
  new headless **`massing` CLI** binary (structured-CLI contract: `--json` structured output, meaningful exit
  codes, fully non-interactive; `massing convert|validate|diff|select|edit run|export`). Headline: **`massing
  check`** runs model-CI (IDS/rule-library) and **exits non-zero on failure** so a CDE/repo pipeline fails
  the build when a model breaks compliance — the single most valuable ISO-19650 CI pattern in the scan. Dual
  auth (interactive session vs env-var CI token); an `eval`-against-the-running-model path (no cold re-convert).

**Tier 2 — solid, reuse engines:**
- **MEP-FITTINGS — auto fitting insertion** *(S/M).* At each `MEP-GRAPH` node a direction/size
  change *implies* a fitting (elbow/tee/reducer/transition); `mep_fittings.py` over the graph auto-inserts +
  counts them into QTO — deterministic geometry, no CV (IFC gives us what others infer from PDFs).
- **PROCURE-LEVEL — RFQ / quote-leveling** *(M).* Group QTO line items into buyout
  packages, emit a structured RFQ, and score returned quotes on a normalized per-unit basis (price + lead-time
  + coverage completeness) — `procurement.py` + a `procurement_package` module + `/procurement/level`, reusing
  the shipped bid-leveling scorer. (Supplier price/catalog feeds = INTEGRATE; placing the PO stays human.)
- **TESTFIT-ADJ — adjacency + dimensional rule packs** *(S/M).* Extend the test-fit solver with a
  declarative **adjacency matrix** (required-adjacent · must-not-be-adjacent · needs-daylight/exterior-wall ·
  needs-wet-wall) as an `adjacency_score` term, and a room-program **dimensional-compliance** rule pack
  (min-room-dim · min-ceiling-height · egress-width · setback) via `rule_library.py`/`/rules/run` scoped to
  `IfcSpace`.
- ◧ **DESIGN-METRICS + DAYLIGHT — live design-metrics engine** *(M; v0.3.591).* ✅ `design_metrics.py`
  + `GET /model/design-metrics`: program efficiency (floors · GFA · net floor area · net-to-gross · unit
  count · avg-unit · area-by-space-type) + a **deterministic average-daylight-factor ESTIMATE** from the
  model's own `IfcWindow` glazed area vs net floor area (CIBSE formula with documented constants → banded
  ≥2% good / 1–2% fair / <1% limited, clearly labelled an estimate, not ray-traced). Pure over an opened
  model so it recomputes on every edit; client + `test_design_metrics`. **Remaining:** a portal KPI panel +
  wiring per-`IfcSpace` code-check rule sets alongside the model-wide numbers.
- **PROD-ACTUALS — productivity actuals loop** *(M).* A `{task_id, qto_line, material_class, qty,
  cycle_time, idle_time, ts}` actuals schema at `POST /progress/actuals`, mapped to QTO (`EST-1` link) +
  schedule, computing **installed-rate actual vs planned takt** on the LOB/4D views. (Crane/telematics sensor
  = INTEGRATE CSV/webhook connector; on-hook CV = SKIP.)
- ◧ **SPACE-UTIL — utilization + supply/demand planner** *(S/M; v0.3.585).* ✅ `space_util.py` +
  `GET /model/space-utilization` (per-`IfcSpace` occupancy capacity at an area-per-person standard, by
  type) + `POST /model/space-demand` (headcount program → required-area-by-type → gap-vs-modelled-inventory,
  worst-deficit first); pure arithmetic, no sensors/ML; client + `test_space_util`. **Remaining:** a portal
  panel + extend the cross-project benchmarking (our own-projects analog to a large external dataset).

**Tier 3 — tooling / DX / security (cross-cutting):**
- **CSS-REFACTOR — panel CSS modernize** *(S).* Across the ~130-module panels: a shared
  `.stack > * + *` owl utility (kill per-child margin hacks), flex `space-between` over nth-child, `:is()` to
  collapse selector lists, standardized `:focus-visible` outlines (a11y), `16px` inputs (stop iOS zoom on the
  PWA), `:empty` to hide blank containers, logical properties for future RTL. Pure-CSS, offline-safe.
- **SEC-SUPPLY — supply-chain hardening** *(S).* Add an **SBOM (CycloneDX)
  generation + license/CVE scan** step to CI (mechanically enforces the MIT/BSD/Apache-only, no-AGPL
  constraint + catches supply-chain CVEs); an **MCP tool-poisoning self-audit** of our MCP server's tool
  defs; a lightweight **uploaded-PDF sanity check** (we ingest/emit PDFs). Folds into the `security-monitoring`
  skill. *(The pack is 90% blue/red-team off-topic — cherry-pick only these; it does NOT replace CodeQL or our
  esc() XSS discipline.)*
- **DX-HOOKS — Claude Code guardrails** *(S — needs the config path + an explicit OK,
  since hooks change harness behavior).* A `PreToolUse` secret-scan + destructive-command (`git reset --hard`
  / force-push / `rm -rf`) guard; a `Stop` hook that runs the `security-monitoring`/`backend-tests` skills so
  the "check after every push" directive is enforced by the harness not memory; the **Anthropic Security-Review
  GitHub Action** as an orthogonal second PR gate beside CodeQL; a SkillSpector-style scan of our own
  `.claude/skills`.

**INTEGRATE (optional, feature-flagged, never a runtime dependency):**
- **MARKET-DATA connector.** A flagged/paid `propdata.py` connector feeding the pro-forma /
  underwriting / valuation modules — parcel + rent-comps (ZORI/HUD FMR) + FHFA HPA + FEMA flood (ties into the
  shipped `resilience.py` DFE) + Opportunity-Zone flags + FRED macro. Same posture as the APS/RVT bridge:
  gate it, normalize to our inputs, never assume online. Also adopt two architecture-agnostic techniques from
  it as BUILD: the **self-enriching cache** (local store → on-miss fetch from an authoritative source → cache
  with source + fetched-at provenance) for our own reference/GIS lookups; and **weighted multi-source
  estimates that expose each component value + its weight** (not just the blend) — fits the golden-thread ethos.

**SKIP (reaffirmed non-goals — the scan's core-AI approaches we deliberately don't take):**
LLM natural-language plan generation, CV takeoff from 2D PDFs, LLM bid-doc
equipment extraction, on-sensor CV pick-classification, embedded-in-Revit agents — all reconstruct data we
already hold as structured IFC. Owning sensors / a sourcing marketplace / placing POs or moving money.
Skip-trace / owner-contact / foreclosure-lead (PII, off-mission).

> **Re-prioritization:** the ▶ NOW list above gains three R16 Tier-1 items at the top —
> **MARGIN-CBS** (small, high-value, closest GC fit), **ASSET-REG** (concrete CMMS-OPS first slice), and
> **RECIPE-MACROS/CLI** (converged-on by 3 sources). **MASSING-OPT** and **MEP-EQUIP** are the next authoring/
> MEP wins after those. Tier 3's **SEC-SUPPLY** + **CSS-REFACTOR** interleave as small hardening/quality
> releases.

## 🎚 UX-POLISH — interaction-craft ring (2026-07-21)

A research pass on interaction/UX patterns from the broader construction-software field. **Key finding:
the strongest ideas are *interaction polish*, not new modules — every worthwhile pattern is achievable
deterministically with zero cloud/AI.** These are UX upgrades over surfaces we already have. All BUILD
unless noted.

- ◧ **★ UX-ACT — actionable inline diagnostics** *(S; highest-leverage; phase-1 v0.3.577).* ✅
  `resolve_hint.py` — a shared resolve-action vocabulary (`open_module`/`navigate`/`open_record`) — + the
  **📒 margin card** now pairs each over-budget/over-committed cost code with a one-click **Fix** button
  that jumps to the causing records, filtered to that code (`dispatchResolveAction`/`resolveActionButtons`
  shared for the ring). **Remaining:** extend the same descriptors to the `rule_library.py` violations and
  `schedule_options.py` conflict feeds.
- **UX-CHIPS — universal status + delta chip component** *(S).* Standardize one component: timestamped
  **status chips** (Sent→Viewed→Won · Draft→Submitted · On-track/Over-budget) + **metric + colored-delta**
  chips (+12% · −$14K), used consistently across the GC/client-portal money cards, DRAW-STATUS, and
  lifecycle feeds. Deterministic, cheap, makes every list feel alive.
- **UX-KPI — KPI header + one-line plain narrative** *(S).* On the portal dashboards, a header row of
  metric + colored delta, plus an **auto-generated one-sentence summary** ("3 jobs on track, 1 over
  budget") — a **template string, not an LLM**. We already hold the numbers in the money cards.
- **UX-DEMO — one threaded demo project across every screen** *(S; demo-quality).* Thread a single
  richly-populated project through bids→budget→schedule→invoice so no screen shows an empty state —
  through every panel in `build_demo_data.py` / demoData.json. Kills empty-state screenshots.
- **COST-SPINE — one cost-code identity estimate→budget→invoice** *(M; design pass).* Formalize
  estimate-line = budget-line = invoice-line on the shared CBS/cost-code spine, with won-bid → contract →
  project → budget auto-flow (a number entered once propagates). Matches our IFC-GUID discipline; reuses
  CBS-1 + QUERY-DSL. (Overlaps MARGIN-CBS — do as its follow-on.)
- **UX-GANTT — weekly Gantt/calendar hybrid** *(M).* Schedule-presentation upgrade: inline **% on the
  task bar**, color-by-crew/task, and a metric strip (Crews-out · Conflicts count) above it. Deterministic.
- **UX-VIEWED — proposal/invoice "Viewed" tracking in the client portal** *(S).* Our tokenized
  ShareToken page already serves a digest — log a view-timestamp and show Sent/Viewed/Paid chips,
  self-hosted, no third party.
- **UX-AR — AR/AP status pipeline on money cards** *(S).* Sent→Approved→Paid status on invoices/bills
  as **manual status** (generation + tracking only — external payment processing stays out per the
  $0/offline constraint).

**SKIP (same non-goals as R16):** AI bill/invoice capture from unstructured docs (their AP wedge — OCR/LLM,
violates deterministic-core), plan/PDF→estimate via CV (our estimates derive from IFC QTO — *better*),
the "autonomous event-driven AI agent" framing, QuickBooks/Stripe/Gmail as a **mandatory** data backbone
(optional connectors only), and automated lien-waiver *filing* / online payment *processing* (money-movement).

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
