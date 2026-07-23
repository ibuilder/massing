# Roadmap

The single product roadmap — **open items only**, reconciled + re-prioritized **2026-07-23 at v0.3.598**
(a second field-research pass — 14 external products + a security paper — added the 🧭 R17 ring and re-topped
the NOW list; the 🔬 R16 ring is now **complete** and archived). Everything ever shipped lives in
[roadmap-completed.md](roadmap-completed.md); per-release detail is in [CHANGELOG.md](../CHANGELOG.md).
Supporting detail: [production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[cost-db-import-plan.md](cost-db-import-plan.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
The R15 ring is closed and both flagship offline-verifiable sprints (Schedule Optioneering, Client-Portal)
are driven several phases deep; the **master-builder skill** is installed and co-evolves with the platform.
What remains is bounded R14/R15 tail depth, the big-ticket continuations, a runtime/tooling ring, and the
decomposition/design carry-overs.

**Status:** CodeQL 0 open alerts · full backend suite green (336 suites) · single-source version in
`apps/web/package.json` (v0.3.614) · CI on Node 22.

**🧭 R17 backend wave — SHIPPED (v0.3.600–614).** Every backend-testable R17 engine is live: **Sprint A**
CITED-ANSWER (the provenance flagship) + PERSONA-ANSWER · **Sprint C complete** EST-CONFIDENCE + BOE-LEDGER +
BUYOUT-SCHED + CONCEPT-BUDGET · **Sprint D** SCOPE-REG (TRANSMITTALS verified already covered) · **Sprint E
complete** PERMIT-TIMELINE + ABSORPTION-SELLOUT/LSI + PROGRESS-ROLLUP · **Sprint F** FILL-MATRIX +
PARCEL-IMPORT + WALL-ASSEMBLY thermal + PORTAL-TXN phase 1 · plus the RUNTIME benchmarked pass (Node 20→22
in CI + oxlint). **Remaining R17:** the viewer-coupled Sprint B/D features (BCF-VIEWPOINT · WALK-MODE ·
CITE-JUMP · 4D5D-VIEWER · TOPIC-BOARD · CLASH-WALKTHROUGH), DORMER, SCAN-4D, NODE-CANVAS, and the carried
◧ sub-phases noted per item.

**🔬 R16 ring — COMPLETE (v0.3.573–598).** All Tier-1/Tier-2 engines shipped: MARGIN-CBS · ASSET-REG ·
RECIPE-MACROS · MASSING-OPT · MEP-EQUIP+SPEC-CONFLICT · SPACE-UTIL · DESIGN-METRICS+DAYLIGHT · MEP-FITTINGS ·
PROD-ACTUALS · PROCURE-LEVEL · TESTFIT-ADJ (+ Design-Metrics/MEP-Fittings portal panels); Tier-3 SEC-SUPPLY
(license/SBOM audit + PDF sanity). Full item detail archived in [roadmap-completed.md](roadmap-completed.md);
the ◧ items with a remaining sub-phase are carried into the lists below.

---

## 🧭 R17 — field-research upgrades (2026-07-23)

Second broad research pass (14 external products across authoring/estimating/finance/reality-capture/BCF/VR +
a security paper). **Same strategic edge, sharpened:** the field keeps burning its budget reconstructing
structured data from unstructured input, and — critically — shipping **black-box AI answers a regulated
industry can't defend**. Because our data is **GUID-first and structured**, we both skip the reconstruction
problem *and* can make every AI answer **trace to its source deterministically**. That provenance layer is the
flagship. BUILD = deterministic/offline/we-own-it · INTEGRATE = optional feature-flagged connector (never a
runtime dep) · SKIP = conflicts with a constraint/non-goal.

**Sprint A — Provenance & AI trust (flagship; the thesis made concrete):**
- ◧ **★ CITED-ANSWER — provenance contract for every AI answer** *(M; v0.3.600).* ✅ `cited_answer.py` — the
  `CitedAnswer` contract: `{answer, claims:[{text, citations:[CitationRef], confidence}], conflicts, coverage,
  fully_cited, uncited_claims, …}` with `CitationRef = {source_type: ifc|doc|record|rule, document_id,
  revision, guid?, sheet?/page?/bbox?, record_ref?, rule_id?, span?}` + minters (`cite_ifc`/`cite_record`/
  `cite_rule`/`cite_doc`). Deterministic **coverage %** + a hard **uncited-claim guard**, **conflict
  surfacing** (two sources disagree on the same target → both provenances kept), and **provenance-as
  -confidence** (independent-source count · current-vs-stale revision penalty · source-type rank
  rule/IFC > record > doc). First producer `cited_query` + `POST /answer/cited-query` (every claim cites the
  GUIDs it derives from, broken down by property); client `citedQuery` + `test_cited_answer`. **Remaining:**
  emit the contract from the AI command bar / RFI-QA / KG answers; the CITE-JUMP show-your-work UI.
- **CITE-JUMP — "show your work" UI** *(S, needs viewer).* Every claim is click-to-expand → jumps the viewer
  to the cited GUID (reuses BCF-VIEWPOINT restore) and/or opens the cited record/sheet. Same interaction
  whether the source is geometry, a data record, or a code-check finding.
- ✅ **PERSONA-ANSWER — persona answer modes + structured output** *(S; v0.3.612).* `persona_answer.py`:
  Exec / PM / Field lenses over a `CitedAnswer` — persona-trimmed prose (claims/citations **never** dropped),
  a deterministic one-line **insight** (priority: conflicts > uncited > no-match > coverage) and ≤4
  **follow-up chips** derived from what the answer contains (all template strings, no LLM). Wired into
  `POST /answer/cited-query` via an optional `persona`; the plain contract is unchanged without it. The
  query-DSL scoping *is* the dataset-scoping toggle. Client + `test_persona_answer`.

**Sprint B — Model-navigable coordination (BCF depth + viewer):**
- **★ BCF-VIEWPOINT — capture/restore from the live viewer** *(M, needs viewer).* On new issue, serialize the
  camera (persp/ortho + FOV), the visible/hidden GUID sets, section/clipping planes, and a `toDataURL`
  snapshot into a BCF `VisualizationInfo`; "reopen issue" restores the exact camera + visibility. Turns our
  metadata-only BCF topics into navigable-in-context ones — and is the jump-to-citation mechanism for CITE-JUMP.
- **WALK-MODE — first-person walk + WebXR immersive** *(M, needs viewer).* WASD + pointer-lock eye-height
  camera over the loaded Fragments (desktop walk mode = higher ROI), plus `renderer.xr.enabled` + controller
  factory for any WebXR headset. Zero cloud, permissive-licensed on the three.js renderer we already ship.
- ◧ **TOPIC-BOARD — BCF kanban + smart-filters + lifecycle** *(S/M; backend v0.3.617).* ✅ `topic_board.py`
  + `GET /projects/{pid}/topics/board`: kanban columns by `status`/`priority`/`assignee`/`type` in **stable
  workflow order** (open → in progress → resolved → closed; unassigned last; newest-modified first within a
  column) + **smart filters reusing the QUERY-DSL grammar over topic fields** (`status=open & priority=High`,
  `title~duct`) — one selector grammar for model elements *and* topics; declared ahead of `/topics/{tid}` so
  'board' isn't captured as an id; bad group/selector → 422. Client (`topicsBoard`) + `test_topic_board`.
  **Remaining:** the frontend kanban panel · the buildingSMART status/stage state machine · threaded comments
  (`reply_to`) · the per-topic audit timeline.
- **CLASH-WALKTHROUGH** *(S).* Each existing clash → a saved BCF viewpoint (camera framed on the clash
  centroid, offending GUIDs isolated); step the clash list in walk/VR marking accept/reject. Reuse of the above.

**Sprint C — Estimating intelligence (deterministic, fills a real gap):**
- ✅ **★ EST-CONFIDENCE — per-line estimate maturity/confidence** *(M; v0.3.601).* `est_confidence.py` +
  `POST /projects/{pid}/estimate/confidence`: each line's confidence = **source** firmness (measured/quote >
  parametric/assembly > allowance/manual) modulated by **design phase** (CD > DD > SD > concept) → banded
  high/medium/low, cost-weighted to a project confidence + a **"% of budget still assumption-based"** KPI +
  avg contingency + the **worst-value least-grounded lines** to firm up. Client (`estimateConfidence`) +
  `test_est_confidence`. **Next:** BOE-LEDGER (the assumption ledger under these numbers).
- ✅ **BOE-LEDGER — Basis-of-Estimate assumption ledger** *(M; v0.3.613).* `boe_ledger.py` +
  `POST /projects/{pid}/estimate/boe`: **ledger** (normalized assumptions per line — source · quote ref ·
  escalation · contingency · basis date — with the undocumented-basis lines surfaced; a quote without a
  quote_ref is flagged), **phase_diff** (assumption drift SD→DD→CD: qty re-based · unit cost moved ·
  source upgraded, biggest total impact first), and **vs_actuals** (assumption→actual variance **decomposed
  exactly** into qty effect (Δq·uc) + price effect (aq·Δuc) — *which* assumption drove the miss). Pairs with
  EST-CONFIDENCE. Client (`estimateBoe`) + `test_boe_ledger`.
- ✅ **BUYOUT-SCHED — time-phased procurement schedule** *(M; v0.3.602; unique to us).* `buyout_schedule.py`
  + `POST /procurement/buyout-schedule`: join QTO lines to their installing activity (by activity id / cost
  code / trade) → **last-responsible-order = install start − lead time**, sorted soonest-order-first; with an
  `as_of` date each line is overdue / urgent (≤14d) / upcoming (≤30d) / ok, unmatched lines flagged
  'unscheduled'. Only we hold the model *and* the schedule. Client (`buyoutSchedule`) + `test_buyout_schedule`.
- ✅ **CONCEPT-BUDGET — parametric conceptual budget from own history** *(M; v0.3.614).* `concept_budget.py`
  + `POST /projects/{pid}/estimate/concept-budget`: `derive_rates(history)` turns the firm's completed
  projects into per-type $/area stats (n · p25 · median · p75, each project **escalated to the target year**
  before aggregation), and `budget(program)` prices a massing program (use · GFA · stories) at the
  own-history **median with a p25–p75 range** — default rate where a use has no history, **UNPRICED surfaced
  rather than guessed**, every line source-tagged (composes with EST-CONFIDENCE + BOE-LEDGER). Client
  (`estimateConceptBudget`) + `test_concept_budget`. Sprint C complete.

**Sprint D — Scope & 4D/5D spine (the connective structure):**
- ◧ **★ SCOPE-REG — first-class Scope register** *(M; v0.3.603).* `scope_register.py` +
  `POST /projects/{pid}/scope/register`: each scope item resolves its **quantity/value** (QTO by cost code),
  **owner** (responsible/package), and **schedule window** (activity by id/cost code) → a **gap analysis**
  surfacing unquantified / unallocated / unscheduled scope (gaps first, highest-value first) + %
  quantified/allocated/scheduled + by-owner rollup. The connective spine across QTO · CBS · responsibility ·
  schedule. Client (`scopeRegister`) + `test_scope_register`. **Remaining:** persist as a `scope_item` module.
- **4D5D-VIEWER — time + cost overlay scrubber** *(M/L, needs viewer).* Bind schedule activities + cost to
  GUIDs → a 4D timeline scrubber coloring elements by construction status/date with a running earned-value/
  cost readout. Deterministic, GUID-keyed.
- ✅ **TRANSMITTALS — already covered** *(verified 2026-07-23).* The `transmittal` module ships numbered
  TR- records (recipient · contents · purpose · method) with the workflow engine over them, plus the
  `issuance.py`/`distribution.py` drawing-issuance engines; PORTAL-TXN (v0.3.611) added the client
  **acknowledgement** path. No duplicate build needed.

**Sprint E — Feasibility & progress (deterministic BUILDs on data we can hold):**
- ✅ **PERMIT-TIMELINE — days-to-issue percentiles → pro-forma** *(M; v0.3.604).* `permit_timeline.py` +
  `POST /projects/{pid}/permits/timeline`: days-to-issue distribution (p25/median/p75) by jurisdiction ×
  type × valuation band + a seasonal profile over cached permit records; `estimate()` returns **median**
  (expected entitlement duration) + **p75** (conservative carry) for a target, broadening the cohort band →
  type → jurisdiction until stable. Reads the project's `permit` records (or supplied permits). Client
  (`permitsTimeline`) + `test_permit_timeline`. **Remaining:** wire the estimate into the pro-forma carry +
  `permit_check` expected-queue (the connector could also start storing the filed/applied date).
- ◧ **ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX — the revenue-side underwriting levers** *(M; v0.3.605).*
  `absorption.py` + `POST /projects/{pid}/feasibility/sellout` (absorption rate → monthly revenue phasing →
  months-to-sellout = the carry driver + total revenue/carry) + `POST .../feasibility/lot-supply` (the public
  Lot Supply Index: `months_of_supply = VDL / monthly_absorption`, indexed to a balanced-market target — 100
  equilibrium · >125 oversupplied · <75 undersupplied). Absorption input = user assumption offline; comparable
  = INTEGRATE. Clients (`feasibilitySellout`/`feasibilityLotSupply`) + `test_absorption`. **Remaining:** wire
  the sell-out revenue curve + carry into the pro-forma IRR.
- ◧ **PROGRESS-ROLLUP — % complete per class/trade from as-built presence** *(M; v0.3.606).*
  `progress_rollup.py` + `POST /projects/{pid}/progress/rollup`: given the design element set + the installed
  GUIDs, roll up **% complete by IFC class · discipline · level · overall, by count AND by value** (the two
  diverge where cheap elements are up but expensive ones are outstanding); elements derive from the model's
  property index when not supplied. Feeds the GC portal + earned value. Client (`progressRollup`) +
  `test_progress_rollup`. ✅ **SCAN-4D** *(v0.3.616)* — `capture_diff` + `POST /progress/capture-diff`: the
  diff between two capture timestamps — newly installed per class/level, **disappeared** elements (present
  at t1, absent at t2 — a re-scan/rework flag, never silently dropped), the progress delta + a daily rate;
  unknown GUIDs ignored (only the design set counts). Client (`progressCaptureDiff`). **Remaining:** wire
  the installed set from verified-progress / a scan match.

**Sprint F — Model-QA & authoring depth:**
- ◧ **FILL-MATRIX — property fill-rate pivot → bulk-edit loop** *(S/M; v0.3.607).* `fill_matrix.py` +
  `GET /projects/{pid}/model/fill-matrix`: a category × property fill-rate pivot over the property index —
  per IFC class, which `Pset::Prop` is systematically blank (`fill_rate`), with the **blank GUIDs** per
  property (the exact selection a bulk edit fills in one pass) + a query-DSL scope + `worst_gaps` (biggest
  partially-filled fields, most-blank-first). Client (`modelFillMatrix`) + `test_fill_matrix`. **Remaining:**
  the frontend one-click "fill the blanks" that pipes `blank_guids` + a value into the edit recipe.
- ✅ **WALL-ASSEMBLY — thermal from the layers** *(M; v0.3.610).* The layered-assembly *authoring* already
  shipped (`material_layers.py` + `assign_material_set`); the missing bridge was thermal.
  `assembly_thermal.py` + `GET /model/assembly-thermal`: every distinct `IfcMaterialLayerSet` → its
  **R/U-value computed from the layers** (thickness ÷ design-k per material category + surface films; air
  cavity at its fixed R; explicit k overrides), the elements using it, and a **per-layer material takeoff**
  (thickness × face area from the base quantities). Feeds the envelope/COMcheck pre-check with a computed —
  not asserted — U. Client (`modelAssemblyThermal`) + `test_assembly_thermal`.
- ◧ **PARCEL-IMPORT — cadastral parcel geometry → FAR/coverage math** *(S/M; v0.3.609).*
  `parcel_geometry.py` + `POST /parcels/analyze`: parse an uploaded GeoJSON/WKT boundary (no gov scraping) →
  area / perimeter / centroid / bbox (shoelace; lon/lat projected equirectangularly at the centroid latitude),
  and — with a zoning envelope + a proposal — **FAR / lot-coverage / height compliance** with per-axis slack +
  max-buildable GFA. Client (`parcelAnalyze`) + `test_parcel_geometry`. **Remaining:** bind the parcel to
  zoning/permit/administrative docs (docmanager link) + persist as a site record.
- ◧ **PORTAL-TXN — ShareToken read-only → transactional** *(M; phase-1 v0.3.611).* ✅ the tokenized
  **decision surface**: a `client_decisions` table (+ Alembic revision) and PUBLIC
  `POST /shared/{token}/decision` — a timestamped, token-stamped **approve / acknowledge / decline** on a
  shared item (estimate · proposal · CO · selection · invoice · document), hardened for a public endpoint
  (item-type/action whitelists · 120/500-char caps · a hard 200-decision-per-token cap · revoked-token 404) —
  NOT a payment and NOT an e-signature of record. The digest + public HTML page carry the newest-first
  **activity feed** (fully escaped); editors read the project-wide feed at `GET /client-decisions`.
  Clients (`sharedDecision`/`clientDecisions`) + `test_portal_txn`. **Remaining:** per-item Sent/Viewed/
  Approved status labels on the shared items themselves · the deposit/payment **schedule** display (schedule
  only — the payment rail stays SKIP) · a scoped client comment thread (BCF round-trip).
- **DORMER** *(S).* A GUID-stable parametric dormer/roof-window family recipe (roof-plane intersection geometry).

**Cross-cutting / substrate (interleave; larger, lower-urgency):**
- **NODE-CANVAS — reusable connector/node canvas** *(L).* A canvas substrate (channels = state-derived animated
  values via spring/ease · keyed reconciliation · anchor registry for wires · world/overlay/screen layers ·
  headless `step(n,dt)` for golden tests) for the graph-shaped features (MEP-GRAPH · recipe-macros · schedule
  dependencies · golden-thread). Borrow the *patterns*, not a canvas-only framework that would fight `@thatopen/ui`.
- **SEC-DATAFLOW — security-review process note** *(XS; done as a skill edit).* The security paper's empirical
  finding — *multi-file/cross-import data-flow vulnerabilities are the hardest and matter most* — folds into the
  `security-monitoring` skill: prioritize dataflow spanning router→dep→model→storage; SAST (CodeQL) is
  pattern-limited, so the agentic search→verify→refine review complements it. (SKIP running a local 350M model.)

**INTEGRATE (optional, feature-flagged, offline-degrading — never a runtime dependency):**
- Higher-coverage **permit backend** + **contractor license/history** feed (prequal/diligence) + **permit-density
  market-activity** feed + **new-home starts/pricing** feed (revenue-side market intel, complementing our
  cost-side escalation index). All behind the existing `opendata.py` `_fetch` indirection; degrade to
  "unavailable" offline. Named BCF-hub connectors; national e-ID/e-sign; ERP (Oracle/SAP) connectors.

**SKIP (reaffirmed non-goals):** LLM/OCR reconstruction of unstructured docs (bill/invoice/handwritten capture);
owning capture hardware / 360-video photogrammetry / hosted digital-twin cloud; native VR-headset app +
cloud multiuser co-presence sync; payment execution + financing rails; consumer marketplaces/listings;
running a local security LLM as a product feature.

> **Re-prioritization (top-down execution order):** Sprint A (**CITED-ANSWER** first — the flagship, pure
> backend/deterministic, no viewer needed for the contract + coverage/conflict engine) → the backend-testable
> estimating/scope engines that need no viewer (**EST-CONFIDENCE**, **BOE-LEDGER**, **BUYOUT-SCHED**,
> **SCOPE-REG**, **PERMIT-TIMELINE**, **ABSORPTION-SELLOUT**, **PROGRESS-ROLLUP**, **FILL-MATRIX**) → then the
> viewer-coupled coordination features (**BCF-VIEWPOINT**, **WALK-MODE**, **4D5D-VIEWER**, **CITE-JUMP**),
> flagged honestly since the dev-preview geometry stall limits live verification. SEC-DATAFLOW rides along as a
> skill edit. Each ships as its own CI-green, version-numbered release; group into the sprints above.

## ▶ NOW — bounded, backend-testable, no new dependency (ship top-down)

*Each is an S/M release: a pure engine leaf or a config-module tweak + a thin surface + a test, grounded
in the model we own. Verifiable without the frontend. These are the cleanest next wins.* **The top of the
list is now the 🧭 R17 backend-testable order (see the R17 ring above for full specifics).**

1. **★ CITED-ANSWER** *(R17 Sprint A)* — the provenance contract + deterministic coverage % / uncited-claim
   guard / conflict surfacing over our GUID-first sources. Pure backend engine + schema; the flagship, no
   viewer needed. **Build first.**
2. **EST-CONFIDENCE + BOE-LEDGER** *(R17 Sprint C)* — per-line estimate maturity/confidence + the
   Basis-of-Estimate assumption ledger. Deterministic scoring over QTO/estimate/commitment records.
3. **BUYOUT-SCHED** *(R17 Sprint C)* — time-phased procurement from model QTO + CPM (last-responsible-order).
4. **SCOPE-REG** *(R17 Sprint D)* — the first-class Scope register tying scope → QTO/CBS → responsible → activity.
5. **PERMIT-TIMELINE** *(R17 Sprint E)* — days-to-issue percentiles over cached permit data → pro-forma carry.
6. **ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX** *(R17 Sprint E)* — sell-out revenue schedule + months-of-supply.
7. **PROGRESS-ROLLUP** *(R17 Sprint E)* — % complete per IFC class/trade rolled up from `scan_deviation.py`.
8. **FILL-MATRIX** *(R17 Sprint F)* — category × property fill-rate pivot → query-DSL selection → bulk edit.
9. **PERSONA-ANSWER** *(R17 Sprint A)* — persona answer lenses + `{answer, insight, follow_ups}` + scoping.
10. **SEC-DATAFLOW** *(R17)* — fold the security paper's multi-file/cross-import dataflow-review focus into the
    `security-monitoring` skill (a skill edit, ride-along).

*Then the viewer-coupled R17 Sprint B/D features (**BCF-VIEWPOINT**, **WALK-MODE**, **CITE-JUMP**,
**4D5D-VIEWER**, **TOPIC-BOARD**, **CLASH-WALKTHROUGH**), flagged for the dev-preview geometry-stall
verification limit.*

**Carry-over open remainders (small, sequence opportunistically):** VERSION-COMPARE per-property **values**
(a stored per-version snapshot — names already ship) · **IFCPATCH-LIB** rebase/unit-convert/merge-split
recipes · **BCF-API-SRV** BCF 3.0 shape + attachments-over-API · RECIPE-MACROS → CADCMD/MCP mirror + headless
`massing` CLI · SPRINT B phase-4b → CPM-driven crew shifts + enumeration scale.

## 🔬 R16 — external-scan upgrades (2026-07-21) — ✅ COMPLETE (archived)

The full R16 ring shipped v0.3.573–598 (MARGIN-CBS · ASSET-REG · RECIPE-MACROS · MASSING-OPT ·
MEP-EQUIP+SPEC-CONFLICT · SPACE-UTIL · DESIGN-METRICS+DAYLIGHT · MEP-FITTINGS · PROD-ACTUALS · PROCURE-LEVEL ·
TESTFIT-ADJ · SEC-SUPPLY). Full spec archived in [roadmap-completed.md](roadmap-completed.md).

**Carried remainders (minor sub-phases, sequence opportunistically):** RECIPE-MACROS → CADCMD/MCP mirror +
headless `massing` CLI with `massing check` CI gate · MASSING-OPT → emit each option as a GUID-stable
edit-recipe chain · MEP-EQUIP → tie into submittals + budget/GMP + a curated starter · DESIGN-METRICS →
per-`IfcSpace` code-check rule sets · PROD-ACTUALS → persist a `progress_actual` module + LOB/4D surface ·
PROCURE-LEVEL → persist a `procurement_package` module + the send-RFQ bridge · TESTFIT-ADJ →
needs-daylight/exterior-wall + wet-wall terms + fold the dimensional pack into `rule_library` · SPACE-UTIL →
portal panel + cross-project benchmarking · SEC-SUPPLY → MCP tool-poisoning self-audit + a non-gating CI step.

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

**Benchmarked 2026-07-23** (measured on this machine — most of the ring is already solved or solves a
non-problem; only two items clear the "measured win" bar, and both need a dependency/toolchain OK):
- ✅ **RT-UVLOOP — already active (no-op).** `uvloop==0.22.1` + `httptools==0.8.0` are already in
  `requirements.lock` (via `uvicorn[standard]`) and the Docker CMD's `--loop auto`/`--http auto` already
  selects them on Linux. Nothing to ship (optionally pin `--loop uvloop` for explicitness; zero perf delta).
- ✗ **RT-MSGSPEC — NO-GO.** The one hot blob (`props.json`, the property index) is 262KB / 1,839 elems →
  `json.loads` **3.71 ms** (orjson 2.07 ms), LRU-cached per project — the parse never dominates a request, and
  RT-ORJSON already covers it; records are heterogeneous dicts, so msgspec's typed-Struct win doesn't apply.
- ✗ **RT-ZSTD — NO-GO.** The only MB-scale blobs are `.frag` tiles served via **HTTP byte-range reads**
  (compression breaks seeking) and already compact binary; the Redis scan cache already gzips. No hot
  compressed-JSON path.
- ✗ **RT-VIRTUAL — NO-GO.** Largest DOM row-cap is `slice(0, 1000)`; nothing renders 100k+ rows and the API
  already returns `truncated` flags over server-bounded results — solves a problem the data shapes don't have.
- ✅ **RT-OXLINT — added (v0.3.608).** `oxlint` (MIT) is a dev-dep + a `lint:fast` (`oxlint src`) script — an
  *additive* sub-second pre-lint, NOT a replacement for the 37.7 s type-aware eslint gate. **Caveat:** oxlint
  1.75's launcher needs Node ≥ 20.19, so it runs in CI (now 22) + local *after* the Node bump, **not** on a
  local 20.3.1 (`ERR_UNKNOWN_FILE_EXTENSION`) — the same pin below.
- ◧ **RT-NODE-LANE → RT-ROLLDOWN — CI half done (v0.3.608).** ✅ the four CI workflows bumped **Node 20→22**
  (LTS, low-risk). **Remaining local + follow-ons:** the developer's local Node is still 20.3.1 (upgrade to run
  eslint 10 / oxlint / Vite 7 locally); then **unpin eslint** (root `overrides`/`devDependencies` off 9.39.5),
  then Vite 6→7 behind a build benchmark (@thatopen are three.js peer-dep libs, bundler-agnostic;
  `vite-plugin-pwa ^1.3.0` supports v7), and **defer** Vite 8 / rolldown until that lane is green.
- **Still to measure (not yet benchmarked):** **RT-BVH** (three-mesh-bvh for our raw-three raycast paths —
  snap / measure / draft-proxy picking) · **RT-KNIP** (unused-export / dead-dep scan for `apps/web`, feeds REL-7).

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
