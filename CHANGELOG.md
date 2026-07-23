# Changelog

All notable changes to Massing. Releases are signed, auto-updating desktop builds
(Windows / macOS / Linux); the updater always serves the latest. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## v0.3.619 — CLASH-WALKTHROUGH: every clash topic ships with a framed viewpoint

Review clashes by standing next to them: each clash becomes a navigable place, not a row in a table.

- Both clash runs (single-model `POST /clash` and federated `POST /clash/federated`) with
  `create_topics=true` now attach a **framed BCF viewpoint** to every created clash topic — the camera at a
  deterministic 4 m diagonal standoff, the target on the clash point, and the offending element pair as the
  viewpoint components.
- Reopening the topic in the viewer lands the reviewer right at the clash (the existing viewpoint-restore
  flow), and walk mode (v0.3.618) starts from there — the clash list becomes a walkthrough. Asserted in
  `test_federated_clash`: standoff distance exactly 4 m, target = anchor, components = the pair.
- A step-through UI (next/prev + accept/reject) remains as the follow-up. Backend suite green; CodeQL 0.

## v0.3.618 — WALK-MODE (desktop) + richer BCF viewpoint capture

The first viewer slice of the R17 coordination sprint: review the model the way you'd walk the building.

- **🚶 Walk mode** (`walkMode.ts`): a rail toggle that enters a pointer-lock **first-person WASD walkthrough**
  from the current camera — mouse-look (pitch clamped ±85°, never flips), Shift to run, E/Q to raise/lower
  eye height, forward always horizontal (walking, not flying), Esc exits back to the orbit camera exactly
  where the walk ended. The movement math is a headless `WalkController` covered by **7 vitest unit tests**
  (heading, strafe, run multiplier, pitch clamp, opposed keys cancel); the installer drives
  `controls.setLookAt` per animation frame with long tab-away frames clamped.
- **BCF viewpoint capture upgraded**: creating an issue now **always** captures the live view — previously a
  viewpoint was only saved when a 3D point had been picked. The capture carries the camera position, the real
  orbit target, and the **active section planes**, so reopening an issue lands in context; the `Viewpoint`
  client type gains `clipping_planes` / `snapshot`.
- Honest verification note: typecheck + lint + **128 vitest tests** + build all green; the pointer-lock walk
  itself is geometry-coupled and not live-exercised under the known dev-preview stall. Backend unchanged.

## v0.3.617 — TOPIC-BOARD (backend): a BCF kanban with query-DSL smart filters

The daily-driver view over the BCF topics we already store — deterministic boards, one selector grammar.

- **`topic_board.py` + `GET /projects/{pid}/topics/board`**: kanban columns grouped by `status` / `priority` /
  `assignee` / `type`, in **stable workflow order** (open → in progress → resolved → closed → reopened;
  priority Critical → Low; unassigned always last; newest-modified first within a column) so the board renders
  identically everywhere.
- **Smart filters reuse the QUERY-DSL grammar over topic fields** — `status=open & priority=High`,
  `title~duct`, `assignee` (field-exists) — the same selector spine that scopes model elements, clash runs,
  and rules now scopes the issue log. Bad group/selector → 422; the route is declared ahead of
  `/topics/{tid}` so "board" isn't captured as a topic id (regression-tested).
- `topicsBoard` client method + `test_topic_board`. The frontend kanban panel, status/stage state machine,
  threaded comments, and per-topic timeline remain as the follow-up. Backend suite green; CodeQL 0.

## v0.3.616 — SCAN-4D: the diff between two capture timestamps

Completes the progress pair: PROGRESS-ROLLUP reads one capture; this reads the *change* between two.

- **`progress_rollup.capture_diff` + `POST /projects/{pid}/progress/capture-diff`**: given the design element
  set and the installed GUIDs at two capture timestamps — what got **newly installed** (per IFC class and per
  level), the **progress delta** (t1 vs t2 percent-complete), and a **daily installation rate** when dates
  are supplied.
- Elements present at t1 but absent at t2 are surfaced as **disappeared** — a re-scan or rework flag, never
  silently dropped. GUIDs not in the design set are ignored (only real elements count). Elements derive from
  the model's property index when not supplied.
- `progressCaptureDiff` client method; covered in `test_progress_rollup` (hand-checked: 3 added over 10 days
  = 0.3/day, w1 disappearing flagged). Backend suite green; CodeQL 0.

## v0.3.615 — docs: sync README / roadmap / status to the R17 backend wave (v0.3.600–614)

Documentation refresh capturing the fifteen-release R17 backend wave — no code change.

- **roadmap.md** status → 336 suites / v0.3.614 / CI on Node 22, with a shipped-wave summary (Sprint A
  provenance flagship + Sprints C/E complete + D/F engines) and the remaining viewer-coupled items listed.
- **README.md** lead highlight rewritten around the provenance-first AI (`CitedAnswer`) + the
  estimating/feasibility engine spine. **status.md** watermark → v0.3.614.

## v0.3.614 — CONCEPT-BUDGET: a conceptual budget priced against your own completed projects

The front-of-funnel that matches the "Massing" name: a defensible first number from massing inputs, priced
against the firm's own history rather than an industry average. Completes the R17 estimating sprint.

- **`concept_budget.py` + `POST /projects/{pid}/estimate/concept-budget`**:
  - `derive_rates(history)` — the firm's completed projects (`building_type · gfa · actual_cost · year`) →
    per-type **$/area statistics** (n · p25 · median · p75), each project's rate **escalated to the target
    year** at a given annual rate before aggregation, so old jobs price forward honestly.
  - `budget(program)` — a massing program (use · GFA · stories) priced at the own-history **median** with a
    **p25–p75 range** per line and in total; a supplied default rate covers uses with no history, and a use
    with neither is surfaced **UNPRICED** rather than guessed.
- Every line carries its **source** ("own-history (n=…)" vs "default rate") — composing directly with
  EST-CONFIDENCE (historical > manual) and the BOE-LEDGER assumption trail. Hand-checked: three office
  projects at 300/350/400 $/SF → median 350, a 200k SF massing prices at $70M ($65–75M), +10% contingency.
- `estimateConceptBudget` client method + `test_concept_budget`. Backend suite green; CodeQL 0.

## v0.3.613 — BOE-LEDGER: the Basis-of-Estimate assumption ledger

The traceability layer *under* the estimate numbers — an estimate you can defend line-by-line, pairing with
EST-CONFIDENCE (which scores them).

- **`boe_ledger.py` + `POST /projects/{pid}/estimate/boe`**, three deterministic reads:
  - **ledger** — the normalized BoE (source · quote ref · escalation % · contingency % · basis date per
    line) with **documentation completeness**: lines missing a source or basis date are surfaced, and a
    quote-sourced line without a `quote_ref` is flagged. An undocumented basis is a dispute waiting to happen.
  - **phase_diff** — assumption drift between estimate versions (SD → DD → CD): qty re-based, unit cost
    moved, escalation/contingency shifted, source upgraded (allowance → quote), with the per-line total
    impact, biggest movement first, plus added/removed lines.
  - **vs_actuals** — once actuals land, the assumption→actual variance **decomposed exactly**: qty effect
    (Δqty × assumed unit cost) + price effect (actual qty × Δunit cost) sum to the variance, so the ledger
    says *which assumption* drove the miss, worst first.
- `estimateBoe` client method + `test_boe_ledger` (hand-checked: an $8,800 miss decomposes into $5,200 qty +
  $3,600 price). Backend suite green; CodeQL 0.

## v0.3.612 — PERSONA-ANSWER: persona lenses over the provenance contract (+ Sprint wrap-up)

The same cited data answers differently per seat — deterministically, with the provenance intact.

- **`persona_answer.py`**: Exec / PM / Field lenses over a `CitedAnswer` — the prose trims to the seat (exec
  two sentences, field one line, pm the breakdown) while **claims and citations are never dropped**; a
  deterministic one-line **insight** (priority: source conflicts > uncited claims > no-match > coverage) and
  ≤4 **follow-up chips** derived from what the answer actually contains (a conflict yields "show the
  conflicting sources", an exec match yields "what is the cost exposure…"). Template strings, no LLM.
- Wired into `POST /projects/{pid}/answer/cited-query` via an optional `persona` — without it, the plain
  CitedAnswer contract is byte-for-byte unchanged. The query-DSL scoping already serves as the
  dataset-scoping toggle. Client updated + `test_persona_answer`.
- **TRANSMITTALS verified already covered** (the numbered TR- `transmittal` module + workflow engine +
  issuance/distribution; PORTAL-TXN added the client-acknowledge path) — marked on the roadmap, no duplicate
  build. **SEC-DATAFLOW** folded into the security-monitoring skill: prioritize multi-file/cross-import
  data-flow review (router → helper → engine → storage) — the empirically hardest class, least covered by
  SAST patterns. Backend suite green; CodeQL 0.

## v0.3.611 — PORTAL-TXN phase 1: the client portal turns transactional (tokenized decisions)

The read-only ShareToken digest becomes a lightweight decision surface — the client can act, not just look —
while staying deterministic and hard-capped for a public endpoint.

- **`client_decisions` table** (+ an Alembic revision; the drift-guard stays clean) and a PUBLIC
  **`POST /shared/{token}/decision`**: a timestamped, token-stamped **approve / acknowledge / decline** on a
  shared item (estimate · proposal · change order · selection · invoice · document). Explicitly NOT a payment
  and NOT an e-signature of record — a recorded client decision with status.
- **Hardened for a public write path:** item-type and action whitelists (a `wire_transfer` or `paid` attempt
  is a 422), 120/500-char caps on refs/notes, a **hard 200-decision-per-token cap** (409 — an unauthenticated
  holder can't grow the table unbounded), and revoked/unknown tokens 404 with no enumeration signal.
- The shared digest and the public HTML page now carry the newest-first **activity feed** — rendered fully
  escaped (an injected `<script>` appears only as text). Editors read the project-wide decision feed at
  `GET /projects/{pid}/client-decisions`.
- `sharedDecision` / `clientDecisions` client methods + `test_portal_txn` (decisions, guards, caps, escape,
  revocation, the cap 409). Backend suite green; CodeQL 0.

## v0.3.610 — WALL-ASSEMBLY thermal: R/U-values computed from the layers themselves

The model already carries genuine layered assemblies (`IfcMaterialLayerSet`), and the envelope code-check
demands a U-value — but nothing bridged the two. Now the U is computed, not asserted.

- **`assembly_thermal.py` + `GET /projects/{pid}/model/assembly-thermal`**: every distinct layer set in the
  model → its **R/U** from the layers (R = thickness ÷ design k per material category, an air cavity at its
  fixed R, standard surface films; an explicit per-layer k overrides the catalog), the elements using it, and
  a **per-layer material takeoff** (thickness × face area from the base quantities).
- Hand-checked: a brick / cavity / insulation / gypsum wall computes R 2.224 (R-12.6 imperial) → U 0.45, with
  the insulation contributing 1.667 of it. Representative ASHRAE-style design k-values, clearly labelled an
  analytical pre-check (not a hot-box test).
- `modelAssemblyThermal` client method + `test_assembly_thermal` (pure math + an authored model with applied
  layer sets + the 409 route guard). Backend suite green; CodeQL 0.

## v0.3.609 — PARCEL-IMPORT: cadastral parcel geometry → FAR / coverage / height compliance

Upload-driven parcel ingest (no government scraping) that turns a boundary into the site math zoning and
feasibility key on.

- **`parcel_geometry.py` + `POST /parcels/analyze`**: parses a parcel boundary from **GeoJSON** (Polygon or
  Feature) or **WKT POLYGON** → **area / perimeter / centroid / bbox** via the shoelace formula. Lon/lat
  rings are projected equirectangularly at the centroid latitude (~0.1% accurate at parcel scale, verified
  within 1% in the test); projected-metre rings compute exactly.
- With a **zoning envelope** (`max_far` / `max_coverage` / `max_height_m`) and a **proposal** (`gfa_m2` /
  `footprint_m2` / `height_m`), reports per-axis **compliance with slack** — including the max-buildable GFA
  the FAR limit implies — and the overall violations list. Missing limits report `ok: null`, never guessed.
- Bad boundaries (a Point, malformed JSON/WKT) → 422. `parcelAnalyze` client method + `test_parcel_geometry`.
  Backend suite green; CodeQL 0.

## v0.3.608 — RUNTIME: Node 20→22 in CI + oxlint fast pre-lint (the two benchmarked GO items)

The two RUNTIME-ring items that cleared the "measured win" bar (the other four were already solved or solved
a non-problem — see the roadmap's benchmarked assessment).

- **Node 20 → 22 in CI:** the four GitHub Actions workflows (ci · desktop · pages · security) now run on Node
  22 LTS. Low-risk (Node 22 is a superset of 20 for our toolchain), and it's the prerequisite for later
  unpinning eslint and moving to Vite 7. eslint stays pinned at 9.39.5 for now (the developer's local Node is
  still 20.3.1); unpinning is a follow-up once local Node is bumped.
- **oxlint (MIT) added** as `apps/web` dev-dep + a `lint:fast` (`oxlint src`) script — an *additive*
  sub-second pre-lint for fast local feedback, **not** a replacement for the type-aware eslint gate (37.7 s;
  oxlint doesn't implement typescript-eslint's type-aware rules, so it can't shrink CI). **Caveat:** oxlint
  1.75's launcher requires Node ≥ 20.19, so it runs in CI (Node 22) and locally *after* a Node upgrade, but
  not on a local Node 20.3.1. The existing eslint + build gates are unaffected.

## v0.3.607 — FILL-MATRIX: a property fill-rate pivot that feeds a bulk-edit loop

Pinpoints *which* pset field is systematically blank and hands back the exact GUIDs to fix — the analytics →
selection → bulk-write loop as one move.

- **`fill_matrix.py` + `GET /projects/{pid}/model/fill-matrix`**: for each IFC class, the union of `Pset::Prop`
  keys seen on its elements with, per property, how many carry a non-empty value (`fill_rate`) and the **GUIDs
  that are blank** — the exact selection a `query_dsl` scope + edit recipe fills in one pass (each row also
  carries a ready selector string).
- **`worst_gaps`** surfaces the biggest partially-filled fields (present on some, missing on many) —
  most-blank-first — the highest-leverage data-quality fixes. Fully-filled properties are excluded.
- Pure over the property index we already hold; `modelFillMatrix` client method + `test_fill_matrix`. Backend
  suite green; CodeQL 0.

## v0.3.606 — PROGRESS-ROLLUP: % complete from as-built element presence (by count and value)

Turns element presence into a percent-complete rollup the GC portal and earned value can consume.

- **`progress_rollup.py` + `POST /projects/{pid}/progress/rollup`**: given the design model's expected element
  set and the set of GUIDs verified **installed**, roll up percent-complete **by IFC class, by trade/
  discipline, by level, and overall — by count AND by value**. Count and value diverge exactly where it
  matters (many cheap elements up vs. a few expensive ones outstanding), so both are reported.
- Elements derive from the model's property index when not supplied; discipline falls back to the
  classification map. Deterministic over the elements + installed GUIDs. `progressRollup` client method +
  `test_progress_rollup`. Backend suite green; CodeQL 0.

## v0.3.605 — ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX: the revenue-side underwriting levers

Our market work is cost-side (escalation); the biggest missing underwriting lever is *how fast the product
sells*. Two deterministic engines add it.

- **`absorption.py` + `POST /projects/{pid}/feasibility/sellout`**: an absorption rate (sales/month) phases
  revenue over time → the **monthly sell-out curve**, **months-to-sell-out** (the carry the pro-forma must
  underwrite), total revenue, and carry over the window. The last month sells the remainder on an uneven mix.
- **`POST /projects/{pid}/feasibility/lot-supply`**: the public **Lot Supply Index** —
  `months_of_supply = VDL ÷ monthly absorption`, indexed to a balanced-market target (100 = equilibrium ·
  > 125 oversupplied · < 75 undersupplied) — a defensible supply/demand read for land screening.
- Absorption rate is an input (a comparable rate is an optional market feed — INTEGRATE). Deterministic
  arithmetic; `feasibilitySellout` / `feasibilityLotSupply` client methods + `test_absorption`. Backend suite
  green; CodeQL 0.

## v0.3.604 — PERMIT-TIMELINE: days-to-issue analytics → a pro-forma entitlement driver

We already ingest permit feeds; the missing bridge was the *timeline model* between the raw feed and the
underwriting. This adds it — deterministically, no live fetch.

- **`permit_timeline.py` + `POST /projects/{pid}/permits/timeline`**: over the cached permit records (or a
  supplied set), days-to-issue = issued − filed, grouped by **jurisdiction × permit type × valuation band**
  into a p25 / median / p75 distribution, plus a seasonal issuance profile.
- **`estimate(target)`** returns the **median** (expected entitlement duration) and **p75** (the conservative
  carry the pro-forma should underwrite) for a jurisdiction / type / valuation, automatically **broadening the
  cohort** (band → type → jurisdiction → all) until the sample is statistically stable, and reporting which
  basis it used.
- Reads the project's `permit` module records when `permits` is omitted; 409 when there's no permit data.
  `permitsTimeline` client method + `test_permit_timeline`. Backend suite green; CodeQL 0.

## v0.3.603 — SCOPE-REG: a first-class scope register + gap analysis (the connective spine)

Ties the things we already hold *separately* — quantities, cost breakdown, responsibility, schedule — into
one register, and surfaces the holes.

- **`scope_register.py` + `POST /projects/{pid}/scope/register`**: each scope item resolves its
  **quantity/value** (from the QTO by cost code), its **owner** (responsible party / buyout package), and its
  **schedule window** (the activity that builds it, by id or cost code).
- The payload is the **gap analysis**: which scope is **unquantified**, which is **unallocated** (nobody owns
  it), which is **unscheduled** — the holes that sink a job — surfaced gaps-first, highest-value-first, with
  % quantified / allocated / scheduled and a by-owner value rollup.
- Deterministic over the supplied scope items + QTO lines + activities; the connective spine across QTO · CBS
  · responsibility · schedule. `scopeRegister` client method + `test_scope_register`. Backend suite green;
  CodeQL 0.

## v0.3.602 — BUYOUT-SCHED: time-phased procurement schedule from QTO × the construction schedule

Only we hold both the model *and* the CPM/Takt schedule, so we can answer the buyer's real question
deterministically: what to buy, how much, and by when to order it.

- **`buyout_schedule.py` + `POST /projects/{pid}/procurement/buyout-schedule`**: each QTO line is joined to
  the schedule activity that installs it (by explicit activity id, then cost code, then trade — the earliest
  matching install), and the **last-responsible-order date** = install start − lead time. Sorted
  soonest-order-first.
- With an `as_of` date, each line is classified **overdue / urgent (≤14 days) / upcoming (≤30 days) / ok**;
  lines with no matching activity are surfaced as **unscheduled** (assign a cost code or trade to place them).
  The rollup reports the overdue count, the next-30-day count, and the total value in the window.
- Lead times come from a per-line `lead_time_days`, else a material/trade/cost-code `lead_times` map, else a
  default. Pure arithmetic over the supplied lines + activities (no wall-clock — pass `as_of`).
  `buyoutSchedule` client method + `test_buyout_schedule`. Backend suite green; CodeQL 0.

## v0.3.601 — EST-CONFIDENCE: per-line estimate maturity + confidence scoring

A number should carry how much to trust it, not just its value — the continuity-of-cost idea, as pure
deterministic scoring over estimate lines we already hold.

- **`est_confidence.py` + `POST /projects/{pid}/estimate/confidence`**: each line's confidence is a function
  of its **source** (a quantity measured off the IFC or a returned quote is firm; a parametric assembly is
  softer; a manual allowance is soft) modulated by **design phase** (CD > DD > SD > concept), banded
  high / medium / low.
- Cost-weighted rollup → a project **confidence** score and band, a **"% of budget still assumption-based"**
  KPI (allowance / manual / parametric lines vs. measured / quoted), average contingency, cost-by-band and
  cost-by-source breakdowns, and the **worst-value least-grounded lines** to firm up next. Lines carrying a
  high contingency are flagged.
- No model, no LLM — arithmetic over supplied lines. `estimateConfidence` client method +
  `test_est_confidence`. Backend suite green; CodeQL 0.

## v0.3.600 — CITED-ANSWER: a provenance contract so every AI answer traces to its source

The R17 flagship — the thesis made concrete. A regulated industry can't act on a black-box answer; because
our data is GUID-first and structured we never *lose* provenance, we attach it deterministically.

- **`cited_answer.py`** defines the **`CitedAnswer`** contract: an answer composed from cited atomic **claims**,
  each carrying `CitationRef`s that point to a model element (IFC GlobalId), a data record (`module/{key}/{id}`),
  a rule/code-check, or a document location — always with the **revision** it came from. Minters:
  `cite_ifc` / `cite_record` / `cite_rule` / `cite_doc`.
- Deterministic, no LLM and no model-emitted confidence: **coverage %** (share of claims with ≥1 citation)
  with a hard **uncited-claim guard** (< 100% warns); **conflict surfacing** — when two claims assert
  different values for the same target (e.g. the model says a wall is 2HR but a code rule requires 3HR), both
  provenances are kept, never silently resolved; and **provenance-as-confidence** derived from the number of
  independent sources, a stale-revision penalty, and source-type rank (rule / IFC-property > record > doc).
- First producer: **`cited_query` + `POST /projects/{pid}/answer/cited-query`** — a model query whose every
  claim cites the GUIDs it is derived from, optionally broken down by a property's value. `citedQuery` client
  method + `test_cited_answer`. The AI command bar / RFI-QA / knowledge-graph answers adopt the contract next.
- Backend suite green; CodeQL 0.

## v0.3.599 — roadmap: R17 field-research ring + R16 archived + re-prioritized (docs)

A second broad field-research pass (14 external products across authoring / estimating / finance /
reality-capture / BCF / VR, plus a security research paper) → a new **🧭 R17 ring** on the roadmap, with the
completed **🔬 R16 ring archived** and the NOW list re-prioritized top-down. No code change.

- **Sharpened thesis:** the field ships black-box AI answers a regulated industry can't defend; because our
  data is GUID-first and structured, we can make every AI answer **trace to its source deterministically** —
  the provenance layer is the R17 flagship (**CITED-ANSWER**), scheduled first.
- **R17 sprints A–F** (backend-testable engines first, viewer-coupled after): provenance & AI trust
  (CITED-ANSWER · PERSONA-ANSWER) · model-navigable coordination (BCF viewpoint capture/restore · first-person
  walk + WebXR · topic kanban) · estimating intelligence (per-line confidence/maturity · basis-of-estimate
  ledger · time-phased buyout schedule · parametric conceptual budget) · scope & 4D/5D spine (a first-class
  Scope register · time+cost overlay scrubber) · feasibility (permit days-to-issue percentiles → pro-forma ·
  absorption sell-out schedule + lot-supply index · % complete from scan deviation) · model-QA & authoring
  (property fill-rate pivot → bulk edit · layered wall assemblies · cadastral parcel import · transactional
  client portal). Every external data feed stays an optional offline-degrading connector; LLM/OCR doc
  reconstruction, capture hardware, VR-headset app, and payment rails remain non-goals.
- **R16 ring marked complete** (v0.3.573–598) and its full spec moved to `roadmap-completed.md`, with the
  minor carried remainders kept on the open lists. The security paper's finding (multi-file/cross-import
  data-flow vulnerabilities are the hardest and highest-value) folds into the security-review process.

## v0.3.598 — SEC-SUPPLY: license/SBOM audit + PDF sanity check (supply-chain hardening)

Dependency-free supply-chain tooling (stdlib only), folded into the `security-monitoring` skill — it does
not replace CodeQL or the `esc()` XSS discipline.

- **License audit** (`supply_chain.license_audit`): classifies every installed Python distribution as
  **permitted** (MIT/BSD/Apache/ISC/PSF/Unlicense/Zlib) · **copyleft** · **unknown**, splitting **strong**
  copyleft (GPL/AGPL — the disallowed hard line) from **weak** (LGPL/MPL — accepted for the ifcopenshell /
  certifi core deps but surfaced). Word-boundary matched, so a BSD licence text's "EXEMPLARY" no longer
  false-matches "MPL". `python -m aec_api.supply_chain --gate` exits non-zero only on strong copyleft, so it
  never breaks CI over the known weak-copyleft core deps.
- **SBOM** (`supply_chain.sbom`): a minimal CycloneDX 1.5 component list (name · version · license).
- **PDF sanity check** (`supply_chain.pdf_sanity`): a lightweight pre-ingest validator — header, EOF, size
  cap, and active-content flags (JavaScript / Launch / EmbeddedFile / OpenAction). Not a full parser (no
  AGPL PyMuPDF).
- `test_supply_chain` + a SEC-SUPPLY section in the security-monitoring skill. Backend suite green; CodeQL 0.

## v0.3.597 — TESTFIT-ADJ: space adjacency graph + program-relation score + dimensional rule pack

Turns the program brief into a live constraint beside the geometry — the last R16 Tier-2 engine.

- **`adjacency.py` + `POST /projects/{pid}/model/adjacency`** (409 without a source IFC): builds an
  **adjacency graph** over the model's IfcSpaces — two spaces are adjacent when their footprints sit within a
  wall-thickness gap on the same storey. Footprints come straight from each space's extruded profile +
  placement (no OCC), and a corner-only touch is *not* counted as an adjacency.
- **Program scoring:** the graph is scored against a program's `required_adjacent` type-pairs (a pair is met
  if any A-type space touches a B-type space → satisfied ratio) and `forbidden` type-pairs (each violating
  A↔B instance is listed).
- **Dimensional compliance:** each space is checked against a rule pack — minimum room dimension (the short
  side of its footprint), minimum floor area, minimum clear/ceiling height — global or per space type.
- Pure over an opened model (recomputes on every edit); `modelAdjacency` client method + `test_adjacency`
  over a relabelled 2×2 grid (4 shared-wall edges, diagonals excluded; a required pair met + one unmet + a
  forbidden violation; the dimensional pack). Backend suite green; CodeQL 0.

## v0.3.596 — portal panels for the DESIGN-METRICS and MEP-FITTINGS engines

The two model-derived R16 Tier-2 engines now have UI in the portal (both in the **design workspace →
Model & standards** stage), turning shipped compute into visible product.

- **📐 Design Metrics panel** (`designMetrics.ts`): a program-efficiency KPI header (floors · net floor area ·
  GFA · net-to-gross · units · avg unit · spaces), a **daylight card** with the average-daylight-factor
  estimate colour-banded good/fair/limited (clearly labelled an estimate), and an area-by-space-type table
  with each type's share of net area.
- **🔩 MEP Fittings panel** (`mepFittings.ts`): the total implied-fitting count with per-type chips
  (elbow/tee/cross/reducer), a **QTO-lines** table (EA), and an "inferred at" detail table showing where and
  why each fitting was implied. Both 409 gracefully into a "needs a source IFC" message.
- Frontend-only (backend unchanged); typecheck + lint + build green. Wired via nav destinations + lazy
  importers, following the existing panel pattern. Input-form panels for the POST engines (PROD-ACTUALS,
  PROCURE-LEVEL) are a separate follow-up.

## v0.3.595 — docs: sync README / roadmap / status to the R16 Tier-2 engine wave (v0.3.591–594)

Documentation refresh capturing the four deterministic engines just shipped — no code change.

- **roadmap.md** status line → 320 suites / v0.3.594, with a "recently shipped" summary of the
  DESIGN-METRICS + DAYLIGHT, MEP-FITTINGS, PROD-ACTUALS, and PROCURE-LEVEL wave.
- **README.md** lead highlight rewritten around the four model/field/buyout engines.
- **status.md** point-in-time watermark advanced to v0.3.594.

## v0.3.594 — PROCURE-LEVEL: QTO → buyout packages + coverage/lead-time-aware quote scoring

The buyout loop on top of the estimate: turn the QTO into RFQ-ready packages, then score returned quotes on
more than headline price.

- **`buyout_packages` + `POST /projects/{pid}/procurement/buyout-packages`**: group QTO line items into
  buyout packages (by trade / CSI / material class / discipline), each carrying an **RFQ scope** (item · qty ·
  unit) the buyer can send out, ranked by estimated cost.
- **`score_quotes` + `POST /projects/{pid}/procurement/level`**: score returned quotes for one package against
  its RFQ scope on a normalized basis — **price** (extended over the scope quantities, with uncovered scope
  extrapolated at the supplier's covered average), **coverage completeness** (how much of the scope they
  priced), and **lead time** — into a composite [0,1] score that ranks the suppliers and lists each one's
  scope gaps. Incomplete bids are penalized on coverage, never silently dropped; the lead-time weight folds
  into price + coverage when no lead times are supplied. Per-item low prices are surfaced too.
- Deterministic on top of the existing quote-leveling; `buyoutPackages` / `procurementLevel` client methods +
  `test_procure_level`. Backend suite green; CodeQL 0.

## v0.3.593 — PROD-ACTUALS: installed-rate actual vs planned + crew utilization

The productivity actuals loop — so the line-of-balance / 4D view shows whether the field is gaining or
losing ground against takt, not just what's planned.

- **`prod_actuals.py` + `POST /projects/{pid}/progress/actuals`**: a `{task_id, qto_line, material_class,
  qty, cycle_time, idle_time, unit}` actuals schema rolled up per activity into the **installed rate**
  (qty ÷ productive/cycle hours) and **crew utilization** (productive ÷ (productive + idle)), then compared
  to the **planned** rate → **ahead / on-track / behind** (±5% band). When a planned quantity is known it
  also reports percent-complete, remaining quantity, and the hours projected to finish at the current rate.
- Rates are compared *within* an activity only — units differ across trades, so the rollup surfaces overall
  utilization (dimensionless) and per-group variance counts, worst-variance first, never a cross-trade rate.
- Pure over the supplied rows (field log / telematics CSV / manual entry); `progressActuals` client method +
  `test_prod_actuals`. Backend suite green; CodeQL 0.

## v0.3.592 — MEP-FITTINGS: implied tee / cross / reducer / elbow over the port graph → QTO

Every junction and transition of a connected MEP run *implies* a fitting — a duct/pipe network can't branch,
change diameter, or turn a corner without one. This reads the MEP port-connectivity graph and infers those
fittings deterministically (no CV — IFC already carries the connectivity others reconstruct from scans), so
the fitting count feeds buyout and estimate instead of only the segments drawn.

- **`mep_fittings.py` + `GET /projects/{pid}/mep/fittings`** (409 without a source IFC): **tee/cross** at each
  branch node (degree ≥3 → a tee, degree 4 → a cross, an *n*-way manifold → *n*−2 tees), **reducer** at a
  segment-to-segment joint with a nominal-size step, and **elbow** at a joint where the two segments change
  direction (sweep-axis angle read from the placement, folded so antiparallel still reads as straight).
- Reducer/elbow inference is confined to **segment↔segment** joints where neither element is a branch, so a
  tee's own legs and authored fittings are never double-counted; a reducing elbow counts once (as the elbow).
- Counts roll into a QTO **`qto_lines`** block (EA), plus a per-type breakdown and capped detail list.
  `mepFittings` client method + `test_mep_fittings` over three authored+connected mini-systems (a 3-way
  branch, a 300→200 mm in-line step, a 90° corner). Backend suite green; CodeQL 0.

## v0.3.591 — DESIGN-METRICS + DAYLIGHT: live program-efficiency + daylight estimate over the model

A new design-validation engine turns the model's own geometry into live design KPIs — recomputable on every
edit, so program efficiency and daylight adequacy become active constraints beside the geometry, not a
downstream report.

- **`design_metrics.py` + `GET /projects/{pid}/model/design-metrics`** (409 without a source IFC): **program
  efficiency** — floors, gross floor area (from the model's storey quantities, else net ÷ a typical
  efficiency), net floor area, net-to-gross ratio, unit count + average unit area (residential-typed spaces),
  and area rolled up by space type.
- **Deterministic daylight estimate:** total glazed area from the model's actual `IfcWindow`s → a
  window-to-floor ratio → an **average daylight factor** via the CIBSE formula with documented constants,
  banded **≥2% good · 1–2% fair · <1% limited**. Clearly labelled an *estimate* (an honest analytical first
  look before a real simulation — the ray-traced version rides the energy/daylight jobs lane), not a black box.
- Pure over an opened model (reuses the SPACE-UTIL space extractor); `modelDesignMetrics` client method +
  `test_design_metrics` (band thresholds, the CIBSE constant, metrics over a real authored model, route
  409/200). Backend suite green; CodeQL 0.

## v0.3.588 — GitHub Pages: one branded theme across all pages + clearer CTA

The landing + guide pages now share the **status.html design system** (the navy · cyan→violet "hologram
edges" theme that matches the brand marks), so the whole site reads as one branded product.

- **index.html** re-skinned onto the shared tokens: navy gradient ground + grid backdrop, cyan→violet
  gradient headline accent + primary buttons, mono eyebrows/pills, the Massing logo in the hero.
- **guide.html** palette swapped to the same tokens (it already shared the CSS-variable names, so the
  navy/cyan theme propagates), plus the logo mark added to its sticky header.
- **Clearer CTA:** the vague **"Free IFC viewer →"** button is now the primary **"Open the live demo →"**
  (and the in-page "Open the viewer →" matches); the download button steps back to secondary. Verified in
  the browser — branded palette applied, no horizontal overflow.

## v0.3.587 — observability: DB migrations + error alerting + tracing (#74 · #75)

Sprint 2 of the open-PR cleanup — the production observability stack, all env-gated and no-op until
configured. (#73 Sentry was already contained in #75, so it's closed as redundant.)

- **#74 Alembic DB migrations (C1)** — `alembic.ini` + `migrations/` with a baseline-current-schema
  revision (158 tables), an `env.py` wired to the app's metadata, and a `db-migrations` CI job that runs
  `upgrade head` + `alembic check` (drift guard) against Postgres. `test_alembic_migrations` builds head +
  asserts no drift. `alembic>=1.13` added to `requirements.in`/`.lock`.
- **#75 OpenTelemetry tracing (C2) + Sentry error alerting (C3)** — `otel.py` (traces only; no-op unless
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set; FastAPI + SQLAlchemy instrumentation, sample-rate control,
  request-id on the span) and `sentry.py` (external 500 alerting; no-op unless `AEC_SENTRY_DSN` is set;
  **fail-open** — capture failure never affects the response; PII scrubbing of auth/cookie/api-key +
  body). `test_otel` + `test_sentry` cover the enabled + disabled paths. Deps (`sentry-sdk[fastapi]`,
  the explicit `opentelemetry-*` packages — Apache-2.0/MIT) added to `requirements.in`/`.lock`.

Merged onto current main (run_tests test-list conflicts resolved to keep every test), ruff + full suite green.

## v0.3.586 — merge the ready hardening PRs (#70 · #71 · #72)

Sprint 1 of the open-PR cleanup — three additive, CI-green production-hardening branches, landed together
after re-verifying the full suite on top of current main.

- **#70 security + performance hardening** — from the production/enterprise audit: `serving.py`,
  `bcf_io.py`, and the convert/authoring/bim routers, with an `nginx.conf` pass; covered by
  `test_serving` / `test_subset_export` / extended `test_bcf`.
- **#71 operational hardening** — opt-in `/metrics` auth + configurable compose resource limits
  (`docker-compose*.yml`, `.env.example`, `main.py`); `test_metrics_auth`.
- **#72 dependency hygiene** — pin the Dockerfile base images by digest (api/web/converter) + an
  `npm audit fix` pass on `package-lock.json` + a `dependabot.yml` grouping tweak.

No version/CHANGELOG conflicts (all three were branched off v0.3.584); merged clean, ruff + full suite green.

## v0.3.585 — SPACE-UTIL: space utilization + supply/demand planner (R16 Tier-2)

Turn the model's `IfcSpace` inventory into a workplace-planning answer — deterministically, because we
hold the areas in the IFC (no sensors, no ML).

- **`space_util.py`** — `utilization(spaces, area_per_person)` gives each space an occupancy **capacity**
  (`floor(net-area ÷ area-per-person)`) rolled up by space type + totals; `demand(spaces, program,
  area_per_person)` compares a headcount **program** (`{space_type: headcount}`) against the modelled
  inventory → required vs. supplied area + the **gap** (deficit/surplus) per type, worst-deficit first.
  The computation is pure over a plain space list (fully unit-tested); `from_model` pulls the spaces off
  the IFC (`Qto_SpaceBaseQuantities` net/gross floor area, LongName/ObjectType for the type).
- **`GET /projects/{pid}/model/space-utilization?area_per_person=…`** + **`POST
  /projects/{pid}/model/space-demand`** ({program, area_per_person}). Client `modelSpaceUtilization` /
  `modelSpaceDemand`. `test_space_util` covers capacity math, the standard-changes-count case, the
  bad-standard fallback, the demand gap + worst-first sort, and the routes (409 without a model).

## v0.3.584 — SPRINT MB: the Master Builder brief's gaps are now one click from the fix

The 8-step Master Builder brief named a gap per step but left you to find the tool that closes it. Each
step now deep-links to the portal destination that addresses it — the same diagnosis→action move as UX-ACT.

- **`master_builder.py`** — each protocol step carries a portal `dest` (place→`__modelanalysis__` ·
  program→`__program__` · feasibility→`__budget__` · regulatory→`__standards__` · design→`__modelqa__` ·
  delivery→`__schedule__` · risk→`__review__` · handover→`__turnover__`), surfaced on every brief step.
  `test_master_builder` asserts each step's dest is a valid `__key__` and the full set is present.
- **Portal** — the `__key__`→render dispatch is hoisted out of `buildNav` into `destDispatch()`, and
  `PanelContext` gains a `navigate(key)` method (a clean way for any panel to jump to a first-class
  destination). The 🏛 Master Builder panel renders a **"→ Close this gap"** button per step (emphasized
  on gaps/partials, quiet when ready) that navigates straight there. Client `Step` type gains `dest`.
- Web typecheck + lint + build green.

## v0.3.583 — docs / Pages / demo refreshed to the R16 Tier-1 wave

Marketing + docs surfaces were last refreshed at v0.3.567; this brings them current to the whole
v0.3.573–582 wave (and fixes the stale 80-module count → 130).

- **README** — new lead highlight bullet for "deriving the deal, the buyout and the FM register straight
  from the model" (massing optioneer · cost-code margin + one-click fixes · asset register + equipment RFQ
  + spec-conflict · recipe-macros); module count 80 → **130** in both places.
- **GitHub Pages** — `status.html` "Recently shipped" section + cards rewritten to the R16 wave;
  `guide.html` "Recently added" callout rewritten; `status.md` watermark → v0.3.582.
- **Demo** — `demoData.json` regenerated (970 fixtures) against the current build.
- No code change; the backend suite is unchanged at 311 green.

## v0.3.582 — portal UIs for the shipped MASSING-OPT + MEP-EQUIP engines

The R16 Tier-1 engines shipped with backend + client methods but no portal surface; this makes two of them
usable.

- **🧮 Massing Optioneer** (developer › Acquire) — a compact zoning-envelope + acquisition form (lot,
  FAR, coverage, height, floor-to-floor, efficiency, unit size, land/hard-$/rent/cap) that runs
  MASSING-OPT and renders the ranked options — floors · units · GFA · yield-on-cost · profit · levers,
  with the **cost-vs-profit frontier** marked (✦) and a rank-by selector (yield / profit / units / net
  sellable). Stateless.
- **🔩 Equipment schedule** (construction › Build) — the MEP-EQUIP procurement schedule derived from the
  model: by-discipline tallies + the RFQ line-items (type · class · quantity · discipline · representative
  spec), ducts/pipes/fittings excluded.
- Both are lazy-imported panels wired into the portal nav + dispatch; typecheck + lint + build green.
  *(Live end-to-end not exercised — the dev preview's geometry stall + a frequently-stale local API gate
  interactive portal checks here; the panels mirror the proven asset/margin-card pattern and the backend
  routes are CI-covered.)*

## v0.3.581 — SPEC-CONFLICT: scheduled-vs-specified equipment cross-check (MEP-EQUIP phase-2)

Complete the MEP-EQUIP value prop — catch the "scheduled air-cooled unit vs. the spec's water-cooled
requirement" mismatch deterministically, by comparing the model's own Pset values (no doc-scanning).

- **`equipment.spec_conflicts(lines, requirements)`** — `requirements` is `{ifc_class: {spec_key:
  expected}}` over the canonical schedule spec labels; a **conflict** is a scheduled line whose Pset value
  disagrees with the spec (case-insensitive for strings; `expected` may be a list of acceptable values), a
  **missing** is a specified property the model doesn't carry. Pure over the schedule output.
- **`POST /projects/{pid}/model/equipment/spec-check`** runs the schedule then the cross-check → conflicts
  + missing + `units_in_conflict`. Client `equipmentSpecCheck`. `test_equipment` extended (conflict,
  case-insensitive match, missing, empty-requirements, route).
- *Next:* a curated starter requirement set + surfacing conflicts on a procurement panel / RFQ export.

## v0.3.580 — MEP-EQUIP: procurement equipment schedule from the IFC (R16 Tier-1)

Derive the RFQ equipment schedule straight from the model — no doc-scanning, because we own the model.

- **`equipment.py`** + `GET /projects/{pid}/model/equipment`: groups the procurable MEP units
  (`IfcEnergyConversionDevice` / `IfcFlowMovingDevice` / `IfcFlowStorageDevice` /
  `IfcFlowTreatmentDevice` / `IfcFlowController` / `IfcFlowTerminal` / `IfcTransportElement`, subtype-
  resolved) by **(class, type)** into **RFQ line-items with a quantity**, a representative spec pulled
  from the model's Psets (manufacturer / model / capacity / power / flow / voltage), and the unit GUIDs;
  plus by-discipline / by-class tallies. Ducts/pipes/fittings and controls are excluded (installed
  material / commissioned, not scheduled units). Where ASSET-REG lists every asset one-per-GUID for FM,
  this rolls them up for buyout.
- Client `modelEquipment`. `test_equipment` covers the type-grouping (two same-type terminals → one line,
  qty 2), the pump as its own line, duct exclusion, descending-quantity sort, and the 409.
- *Next:* SPEC-CONFLICT — a `rule_library.py` cross-check of each line's Pset values against a specified-
  requirement set (the scheduled-vs-specified mismatch catch) + a procurement panel / RFQ export.

## v0.3.579 — security: generic proforma solve-error, clearing the CodeQL alert

The actual sink behind the `py/stack-trace-exposure` alert: `_proforma_seed` caught a broad `Exception`
from the proforma solver and returned **`solve_error: str(e)`** in the response — that exception string
flowed out through `/generate/massing/preview`'s return. It now returns a **fixed note** ("the starter
proforma could not be solved") instead. Also hardened the remaining `/generate/massing` envelope 422 to the
same controlled `_ENVELOPE_422` message (v0.3.578 covered the preview + optioneer routes but not this one).
`test_generate` green. (v0.3.578 addressed a related `str(e)` path but not the flagged one — this clears it.)

## v0.3.578 — security: no exception string in the massing 422s (CodeQL)

CodeQL flagged `py/stack-trace-exposure` (medium) after the MASSING-OPT push: the new `/massing/optioneer`
route added a data-flow path in which a `ValueError` from `compute_massing` reached the HTTP response via
`str(e)` — the same pattern the older `/generate/massing/preview` route used. `compute_massing` only ever
raises one controlled validation message, so both routes now return a **fixed 422 detail** (`_ENVELOPE_422`)
instead of flowing the exception string to the client. Behaviour unchanged (still 422 on a bad envelope);
CodeQL back to 0 open alerts.

## v0.3.577 — UX-ACT: actionable inline diagnostics (UX-POLISH ring)

The first UX-POLISH build — pair a computed diagnostic with a one-click action next to it, instead of
leaving it a passive read-only number. We already compute the exposure; now you can act on it in one click.

- **`resolve_hint.py`** — a shared, tiny **resolve-action vocabulary** (`open_module` · `navigate` ·
  `open_record`) so every actionable feed emits the same descriptor shape and the portal renders them
  uniformly. Pure, no I/O.
- **MARGIN-CBS** now attaches an `actions` list to each flagged cost-code row: an **over-budget** code
  gets a "Review direct costs" jump, an **over-committed** code gets a "Review commitments" jump — each
  **pre-filtered to that cost code** so the PM lands on exactly the records behind the flag instead of
  hunting. A healthy code carries none. `test_margin` covers the descriptor shape + filter.
- **Portal** — a shared `dispatchResolveAction` / `resolveActionButtons` (in the margin panel module,
  reusable across the ring) renders the actions as inline buttons in a new **Fix** column on the 📒
  Cost-code Margin card; clicking one opens that module's records filtered to the code. `ResolveAction`
  type + client wiring.
- *Next:* extend the same action descriptors to the rule-run violations and schedule-conflict feeds.

## v0.3.576 — MASSING-OPT: the layout/massing optioneer (R16 Tier-1)

The literal "Massing" play — deterministically enumerate envelope options over a zoning envelope and rank
them by developer yield, mirroring the schedule optioneer but for the massing stage.

- **`layout_options.py`** — `optioneer(envelope, levers?, objective?, limit?)` sweeps the levers a
  developer turns early — **floor-to-floor · core efficiency · coverage strategy (podium vs. tower) · unit
  size/mix** — running each combination through the deterministic `massing.compute_massing` zoning→program
  engine, then scores each option with a transparent **yield-on-cost proforma** (NOI ÷ total cost, from the
  land + hard-$/sf + rent + cap-rate assumptions already on the envelope). Returns the options **ranked by
  objective** (`yield_on_cost` | `profit` | `units` | `net_sellable`) plus a real **Pareto cost-vs-profit
  frontier** (an option is on the frontier if no other is both cheaper *and* more profitable). Duplicate
  programs collapse; the base envelope is validated up front (a bad lot → 422).
- **`POST /massing/optioneer`** — stateless: no IFC is written (authoring the winning massing via the
  blank-IFC → levels/grid → walls/slabs recipe chain is the phase-2 emission). Client `massingOptioneer`.
  `test_layout_options` checks feasibility, yield math, the objective switch, and frontier non-domination
  (no frontier option beaten on both axes; a tighter floor-to-floor fits more floors under the height cap).
- *Next phase:* emit each option as a GUID-stable edit-recipe chain + a 🧮-style comparison panel.

## v0.3.575 — RECIPE-MACROS: save a chained edit-recipe as a named, parameterized command (R16 Tier-1)

The reuse multiplier the GUID-stable edit-recipe spine was built for — capture your standard assemblies
as commands instead of re-typing the same step sequence.

- **`macros.py`** — a macro is an ordered list of authoring-recipe steps (the same `{recipe, params}`
  shape `/edit/batch` runs) with **declared parameters** its steps reference as `${name}` placeholders.
  `expand(macro, args)` resolves placeholders + declared defaults into a concrete step list — pure and
  **model-free**, so a client can preview/validate before it ever touches the model. Type-preserving: a
  bare `"${x0}"` keeps its numeric/list value (a `[x,y]` point survives, not just strings); embedded
  placeholders string-interpolate. A required param with no value raises.
- **Routes** on the authoring router: `GET /projects/{pid}/macros` (saved library, falls back to a
  starter set), `PUT /projects/{pid}/macros` (validates **every step's recipe name against the edit
  engine's registry** before writing — a bad macro rejects the whole save 422, no partial overwrite),
  `POST .../macros/{id}/expand` (model-free preview), and `POST .../macros/{id}/run` (expands with args
  and applies the whole chain as **ONE GUID-stable version** — the same read→apply→pointer-swap
  `/edit/batch` uses, one edit-history entry so the macro undoes as a single step, honoring the COLLAB-1
  optimistic lock via `base_source`).
- Storage mirrors the rule library — one validated JSON blob per project with caps (≤100 macros, ≤60
  steps, ≤40 params) so a stored macro can't be amplified into an unbounded apply. Client
  `listMacros`/`saveMacros`/`expandMacro`/`runMacro` + the `EditMacro` type. `test_macros` covers
  substitution, defaults, atomic bad-recipe rejection, and the list/expand/run round-trip.
- *Next phases:* mirror macro-run into the CADCMD command line + MCP, and a headless `massing` CLI with
  a `massing check` CI gate.

## v0.3.574 — ASSET-REG: maintainable-asset register from the IFC (R16 Tier-1)

The second R16 build — derive the FM handover register straight from the model, deterministically (because
IFC is our source of truth), so it isn't hand-entered.

- **`model_assets.py` + `GET /projects/{pid}/model/assets`**: selects the maintainable serviceable assets
  from the IFC by class (subtype-resolved — `IfcEnergyConversionDevice` / `IfcFlowMovingDevice` /
  `IfcFlowController` / `IfcFlowTerminal` / `IfcFlowStorageDevice` / `IfcFlowTreatmentDevice` /
  `IfcDistributionControlElement` / `IfcTransportElement`, **excluding ducts/pipes/fittings** — you maintain
  the unit, not the duct run), GUID-keyed with discipline (`classification.py`) + storey + type + a coarse
  category, with per-discipline / per-category / per-class tallies.
- **`POST /projects/{pid}/model/assets/seed`** (editor): populates the shipped `asset_register` module from
  the derived assets, **idempotent by tag** (`{ifc_class}-{guid8}`) — one call turns the IFC into a
  populated FM register, ready for `pm_schedule` preventive maintenance + warranty/serial per asset.
- **🔧 Asset Register** portal destination (Operations nav, shown when the project uses the `asset_register`
  module): count + by-category/discipline chips + a "seed from model" button + the asset list. Client
  methods `modelAssets` / `seedModelAssets`. `test_model_assets` covers the class selection (terminals +
  pump + elevator in, duct out), tallies, the 409, and the idempotent seed.

## v0.3.573 — MARGIN-CBS: per-cost-code margin reconciliation (R16 Tier-1)

The first R16 build — the highest-value GC-portal item from the research pass: per-cost-code margin
reconciliation, done deterministically over our own cost modules.

- **`margin.py` + `GET /projects/{pid}/margin/by-costcode`**: one reconciliation view keyed on cost code
  that ties the portal's separate cost modules together — **budget** (revised control number) vs
  **committed** (subcontracts/POs) vs **actual** (direct costs) vs **billed** (sub invoices) — and computes
  per code the projected **buyout margin** (budget − committed), the **cost variance** (budget − actual),
  and **over-committed / over-budget** flags, sorted worst-margin first, with project totals.
- **📒 Cost-code Margin** portal destination (Cost/Budget nav group, shown when the project uses the
  `cost_code` module): a buyout-margin headline + a per-code table (budget/committed/actual/margin/variance,
  over-committed rows flagged). Client method `marginByCostCode`.
- Pure over the module records (tolerant currency parsing, guarded); `test_margin` covers the under/over-
  budget split, worst-first ordering, totals, empty + 404.

## v0.3.572 — Roadmap: R16 external-scan upgrade ring

Synthesized a web scan of 14 AEC/proptech products + 4 dev/skills
resources (css-protips, frontend-dev-bookmarks, awesome-claude-code, Anthropic-Cybersecurity-Skills)
into a new **🔬 R16 ring** in [docs/roadmap.md](docs/roadmap.md), with per-item engine/endpoint/module
specifics and BUILD / INTEGRATE / SKIP tags. Highlights: **MASSING-OPT** (a layout optioneer mirroring the
schedule-optioneer pattern), **MARGIN-CBS** (per-cost-code committed/billed/earned margin), **ASSET-REG +
PM-OPS** (asset register + preventive maintenance from the IFC), **MEP-EQUIP + SPEC-CONFLICT**,
**RECIPE-MACROS + a headless `massing` CLI** with a `massing check` CI gate, plus MEP auto-fittings,
RFQ quote-leveling, test-fit adjacency rules, a live design-metrics/daylight panel, a productivity-actuals
loop, and Tier-3 CSS/security/DX hardening. The recurring strategic note: because IFC is our source of
truth, we skip the "reconstruct structured data from unstructured inputs" problem most of these products
spend their AI budget on. The ▶ NOW list is re-topped with the three highest-value R16 Tier-1 picks.

## v0.3.571 — SCHED-OPT: Pareto frontier chart (SPRINT B phase-4b, part 1)

- The 🧮 Schedule-optioneering card now renders a compact **cost-vs-duration scatter**: every scenario is
  a dot (faint off-frontier, filled on the Pareto frontier), the **recommended** option is ringed (⊙), the
  **baseline** is a square (▢), and the frontier is drawn as a dashed line — so the time/cost tradeoff and
  which options are non-dominated read at a glance, beside the ranked table. Pure SVG, theme-aware.
- Frontend-only over the existing `/schedule/optioneer` data. *(CPM-driven crew shifts off the critical
  path — the other half of phase-4b — remain a backend follow-up.)*

## v0.3.570 — VERSION-COMPARE per-property (R15 tail)

The model version diff now names the **exact** properties/quantities that changed, not just "properties
changed".

- `versions._fingerprints` gained a 7th position — a flat **per-property hash map**
  (`{"SetName.PropName": value_hash}`) over each element's Psets + Qtos. Each is a short hash, so the
  stored version blob stays bounded (no raw values), and it reuses the existing `fingerprints` JSON
  column (**no migration**). Older versions store only positions [0..5] and degrade gracefully.
- `versions.diff` now attaches **`changed_properties`** to each modified element — the sorted keys whose
  hash differs, each tagged **added / removed / changed** — plus a top-level `property_detail_available`
  flag. The viewer's version-compare list appends the named keys after the change labels (e.g. "properties
  changed — Pset_WallCommon.FireRating, Qto_WallBaseQuantities.NetSideArea").
- Names *which* properties changed (the remaining old/new *values* need a richer per-version snapshot, a
  separate stored-column follow-up). `test_versions` extended.

## v0.3.569 — SELECTIONS money card (SPRINT D phase-3c)

The selections & allowances rollup is now surfaced in the portal, completing the SPRINT D phase-3 thread
end to end.

- A **◈ Selections** destination (in the Cost/Budget nav group, shown when the project uses the
  `selection` module): a headline **net over/under** vs. allowance, totals + priced/approved counts, the
  **per-category signed deltas**, and the over-allowance **change-order candidates** — with a one-click
  **"→ Push overages to change events"** button wired to the idempotent `/selections/push-change-events`.
- Frontend-only over the already-shipped, tested `/selections/summary` + `/selections/push-change-events`
  endpoints (v0.3.565–566); build/typecheck-verified (the preview stall limits live click-testing).

## v0.3.568 — Docs & demo refresh to current state

Brought every doc and the offline demo up to the v0.3.543–567 wave.

- **Roadmap reconciled** — the whole ✅-completed wave (quick-wins, SPRINT B Schedule Optioneering,
  SPRINT MB Master Builder + the skill, SPRINT D Client-Portal, SPRINT E rebar bending, SOLVER-OUT,
  RT-ORJSON, the hardening + security bumps) moved into `roadmap-completed.md`; `roadmap.md` rewritten
  fresh with **open items only**, re-prioritized around a bounded backend-testable NOW list (VERSION-COMPARE
  per-property, IFCPATCH-LIB, BCF-API-SRV depth, the SPRINT D/B/MB continuations) + the big-ticket tracks.
- **README** — new lead "Recent platform work" entry for the wave (schedule optioneering, the Master
  Builder brief + in-repo skill, the client-portal + selections/allowances, Code_Aster export, the
  model-warnings feed).
- **GitHub Pages** — `index.html` (GC-portal capability card updated: 130 modules, schedule optioneering,
  client-portal, selections & allowances, Master Builder brief; BIM card gains the model-warnings feed +
  the OpenSees/Code_Aster solver export) and `status.html` (release count refreshed; the second
  "Recently shipped" grid replaced with the current-wave cards). `status.md` watermark → v0.3.567, test
  count → 306.
- **Guide** — a "Recently added" callout covering the six new capabilities.
- **Demo** — `demoData.json` regenerated (970 fixtures) so the offline `/app/` demo renders the current
  feature set.

## v0.3.567 — SOLVER-OUT: Code_Aster mesh export (R15 tail)

A second independent structural-solver exchange beside the shipped OpenSees `.tcl`.

- **`fem_export.to_code_aster` + `GET /projects/{pid}/structure/code-aster.mail`**: exports the W10-7
  analytical frame as a **Code_Aster** mesh (`.mail`, ASTER text format, SI metres) — `COOR_3D` nodes,
  `SEG2` beam elements, a `BASE` node group (the fixed supports) and a `FRAME` element group. Same frame
  topology as the OpenSees export; a structural engineer can now independently verify the frame in
  Code_Aster (GPL) as well as OpenSees.
- Geometry/supports skeleton only — the engineer assigns the section (AFFE_CARA_ELEM), material, BCs on
  BASE, and the load case. A `⬇ Export Code_Aster (.mail)` button sits beside the OpenSees export in the
  structural tools; client method `codeAsterMailUrl`.

## v0.3.566 — SELECTIONS: push overages to change events (SPRINT D phase-3b)

Closes the selections → change-order → budget thread.

- **`POST /projects/{pid}/selections/push-change-events`** (`selections.push_to_change_events`): creates a
  **`change_event`** (reason *Allowance Reconciliation*, ROM = the overage) for every over-allowance
  selection that doesn't already have one — so the deltas flow into the change-order chain and the budget
  (via the change_event PCO rollups). **Idempotent** by a deterministic subject (`Allowance overage —
  {item} ({ref})`), so re-running only adds what's new — no duplicate change events.
- Each summary CO-candidate now carries its `change_subject` (the idempotency key). Client method
  `pushSelectionChangeEvents` wired.

## v0.3.565 — SELECTIONS: allowances → change-order candidates (SPRINT D phase-3)

Turns the owner's selections log into the money picture a builder actually manages.

- **`selections.py` + `GET /projects/{pid}/selections/summary`**: rolls up the `selection` records into
  allowance-vs-actual — total allowance, total actual, the **net over/under**, per-category signed deltas,
  approval count, and the **change-order candidates** (delta = actual − allowance; over is an add to the
  owner, under a credit) worst-first. Priced = selections with an actual cost entered.
- Tolerant currency parsing (`$1,200.50` → number), guarded so an unpriced or malformed selection is
  skipped rather than breaking the rollup; empty project → a zeroed summary. Client method
  `selectionsSummary` wired.

## v0.3.564 — CLIENT-PORTAL: public read-only share page (SPRINT D phase-2)

- **`GET /shared/{token}`** (public, no auth) now serves a **self-contained read-only HTML page** rendering
  the share digest — a readiness bar, the project + jurisdiction, and the 8 protocol steps with their
  status. A stakeholder opens the link and sees the project's readiness with no login and no app.
- **Every value is HTML-escaped** (`client_portal.to_html`), the page is marked `noindex,nofollow`, and it
  exposes only the same curated readiness data as the JSON digest — no record-level data. Covered by a test
  that a hostile project name (`<script>…`) is escaped, not executed.
- The 🔗 Share section in the 🏛 panel now links to the human HTML page (`sharedPageUrl`).

## v0.3.563 — CLIENT-PORTAL: tokenized read-only project digest (SPRINT D phase-1)

Opens the first external-stakeholder surface — a link an owner can hand out to see project readiness
without a login, without touching any record.

- **Share tokens** (`ShareToken` model + `client_portal.py`): an editor mints a **revocable, read-only
  share token** (a strong `secrets.token_urlsafe` secret) for a project — `POST/GET/DELETE
  /projects/{pid}/share-tokens` (editor-gated), bounded at 50 live tokens per project.
- **Public digest** (`GET /shared/{token}/digest`, **no auth** — the token is the credential): returns a
  **curated readiness digest** — project name, jurisdiction, the overall readiness score, and each
  protocol step's title + status. **Nothing else**: no findings detail, no GUIDs, no financials, no
  record-level data, no PII. An unknown or revoked token 404s (no enumeration signal); each view is
  counted on the token.
- **🔗 Share read-only** section in the 🏛 Master Builder panel: create a labeled link, see its view
  count, open it, and revoke it.
- Hard-railed by design (per the build-doctrine): the public surface is strictly read-only and exposes
  only what's safe to share, so a leaked token reveals a readiness summary and nothing more.

## v0.3.562 — MASTER-BUILDER: shareable Markdown brief (SPRINT MB phase-2b)

- `master_builder.to_markdown()` + `GET /projects/{pid}/master-builder/brief.md` (text/markdown): the
  8-step brief as a printable one-page document — readiness header, place grounding (jurisdiction, code
  family, coordinates, climate band), a section per protocol step with its ✅/🟡/⛔ status, findings and
  gaps, the hazards-to-verify list, and the honest-status disclaimer. A **⬇ Markdown** button in the 🏛
  panel downloads it (wired to `masterBuilderBriefMdUrl`).

## v0.3.561 — Security: clear the brace-expansion advisories

- Bumped the two vulnerable transitive `brace-expansion` instances (a ReDoS advisory) to their patched
  versions — `2.1.1 → 2.1.2` and `5.0.6 → 5.0.7` — via a lockfile-only `npm audit fix`. The three
  non-vulnerable `1.1.16` copies are untouched. `npm audit` now reports **0 vulnerabilities**, clearing
  the 2 high Dependabot alerts on the default branch. Build-tooling transitive deps only (eslint /
  redocly / jake), not in the shipped app bundle; no code change.

## v0.3.560 — FAB-DELIVER: rebar bending detail (SPRINT E phase-1)

The first fabrication-delivery slice — the human-read bending schedule a detailer and fabricator
actually work from, ahead of any machine format.

- The bar bending schedule (`rebar_rules.bar_bending_schedule` → `GET /projects/{pid}/rebar/bbs`) now
  carries **per-mark bending detail** off the authored bar geometry: **leg lengths** (mm), the
  **deviation/bend angle** at each interior vertex (degrees), the **bend count**, and a **shape family**
  (straight · single bend (L) · double bend (U/crank) · closed tie/stirrup · N-bend). The CSV export
  gains Bends / Legs / Bend-angles columns.
- Pure `rebar_rules.bending_detail(points, closed)` is unit-testable (an L-bar → 1 bend, two legs, a 90°
  corner; collinear points → 0 bends).
- **The BVBS/BF2D machine bending-file export is deliberately deferred**, held behind a validation gate:
  a byte-wrong bending file makes a machine mis-bend real steel, so per the fabrication-output doctrine it
  ships only once validated against the authoritative BVBS spec **and** a real importer. The `master-builder`
  skill (v0.3.2, `construction-delivery.md`) documents this honest boundary.

## v0.3.559 — Hardening pass over the v0.3.552–558 feature wave

Between-sprint adversarial bug-hunt + XSS/security hand-audit over the seven new releases (WARN-1,
NORM-VALID tails, SCOPE-GAP, GOLDEN-THREAD seed, SCHED-OPT phases 1–4a, Master Builder brief phases 1–2a).
No high-severity issue found — the frontend had **no XSS** (every model-derived string escaped), route
role-gating was sound, the optioneer's 800-scenario cap genuinely bounds enumeration, and the
division/zero paths were all guarded. Three concrete low-severity defects fixed:

- **Master Builder** — `_dms_to_deg` read the coordinate sign only from the degrees component, so a
  sub-degree southern/western site (e.g. IFC `[0, -30, 0]` = −0.5°) decoded as positive and reported the
  wrong hemisphere/climate band. Now the sign is taken from any DMS component (the IFC rule).
- **SCHED-OPT** — the optioneer engine now **normalises caller-supplied trades** (a null / non-numeric /
  string `takt_days`, a non-dict entry, or a nameless trade is coerced or dropped) and **value-clamps
  `floors` (≤ 2000) and zones (≤ 24)** before enumerating — a malformed or absurd body can no longer 500
  or attempt a multi-GB allocation. The route now returns **422** (not 500) for non-numeric
  `floors` / `zone_options` / `overlap_options` / non-list `trades`.
- **SCHED-OPT panel** — the recommended-scenario row highlight compared object identity (`s === rec`),
  which is never true across a JSON round-trip, so the row never highlighted; now matches on `rank`.

## v0.3.558 — MASTER-BUILDER: ground the brief in real coordinates (SPRINT MB phase-2a)

The Master Builder brief now grounds itself in the project's actual place, not just its jurisdiction.

- **Place-grounding** — the brief resolves the **code family** from the jurisdiction (a US state → ICC /
  IBC-derived) and, when the model is **georeferenced**, decodes the site's IFC lat/long (compound
  degrees-minutes-seconds) to derive the **hemisphere** and a broad **climate band** (universal physics).
  The place step now cites the real coordinates as a finding.
- **Hazards to verify locally** — per the ground-in-place doctrine, it never invents load values; it
  emits the list of location-specific parameters to read from the site's hazard basis (seismic Ss/S1,
  basic wind speed, ground snow, flood design elevation, energy-code climate zone) — the parameter to
  look up, marked for local confirmation. Surfaced as a collapsible "Verify locally" card in the 🏛 panel.
- The route feeds the brief the model's georeferencing best-effort (guarded); the engine stays pure
  (coordinates passed in, no I/O). `master-builder` skill co-evolved to v0.3.1 (`global-codes.md` §8
  documents the mechanized grounding).

## v0.3.557 — MASTER-BUILDER: the whole project in one brief (SPRINT MB phase-1)

A new synthesis that holds the entire project in one view — the software embodiment of the
Master Builder Protocol.

- **`master_builder.py` engine** + `GET /projects/{pid}/master-builder/brief`: runs the 8 protocol
  steps (place → program/HBU → feasibility → regulatory → design-integration → delivery → risk →
  handover) over the project's *own* data, **grounds the whole brief in the project's jurisdiction**
  (the field that resolves which code editions and hazard loads govern), and returns a per-step
  readiness status (`ready` / `partial` / `gap`) with the concrete gap and a link to the tool that
  closes it, plus an overall readiness score.
- It is a **synthesis over the platform's existing engines** — georeferencing, budget, schedule + bid
  packages, the compliance-evidence golden thread, the clash coordination log, the risk board, and the
  facility-condition/asset basis — reading the canonical signals, never re-deriving them. Every probe is
  guarded, so a missing module degrades a step to a gap rather than erroring.
- Honest-status boundary carried in the payload: a readiness synthesis over the data on hand is **not a
  substitute** for licensed engineering/architectural judgment, an AHJ plan check, or committed
  underwriting.
- **🏛 Master Builder** panel (Model & standards nav): a readiness header (score + grounded-in-place +
  the reframe prompt) and one card per protocol step (status pill, the "why", what's present, the gap),
  wired to `masterBuilderBrief`.
- Ships with the **`master-builder` skill** (`.claude/skills/master-builder`, v0.3.0) — the reasoning
  doctrine behind the feature; the skill's `build-doctrine.md` gained the "synthesis over sources of
  truth" principle and `digital-toolkit.md` now documents this endpoint as the protocol's reference
  implementation.

## v0.3.556 — SCHED-OPT: optimize the real project — takt train from the schedule (SPRINT B phase-4a)

The optioneer no longer always defaults to the residential takt train — it now **derives the trade
train from the project's own schedule** when one exists.

- When the `/schedule/optioneer` request omits `trades`, the route builds the takt train from the
  project's `schedule_activity` records: group by trade, sum each trade's duration, and set its
  per-floor takt = total ÷ floors; trades order by earliest start (a stable, schedule-honouring
  sequence). Falls back to the residential takt train when there's no usable schedule (< 2 trades with
  duration).
- The response carries `trade_source` (`body` / `schedule` / `default`) and the panel's recommended
  line names it ("… N trades from your project schedule"), so it's clear the optioneer is optimising
  real project data — not a generic template.

## v0.3.555 — SCHED-OPT: scenario-comparison panel (SPRINT B phase-3)

Surfaces the optioneer in the Schedule workspace so the ranked scenarios are usable, not just an API.

- A **🧮 Schedule optioneering** card on the Schedule panel: a **▶ Run** control with a weighting
  selector (Balanced / Fastest / Cheapest) and a fast-track toggle, a **recommended-plan summary**
  (duration, cost, peak crews, saving vs. baseline, its lever mix), and a **ranked scenario table**
  (top 12 — levers, days, cost, peak crews, Pareto-frontier marker) with the recommended row
  highlighted. Wired to the `scheduleOptioneer` client method.
- Frontend only (no backend change) — verified by typecheck / lint / build; the card renders even
  without a model (defaults to the residential takt train), so it's exercisable on any project.

## v0.3.554 — SCHED-OPT: widen the search — fast-track overlap + sequence permutation (SPRINT B phase-2)

Widens the optioneer's search space with two more levers, so the enumerated frontier spans real
schedule-compression moves — not just crews and zoning.

- **Fast-track overlap** — a scenario lever (`overlap_options`) where a successor trade may start a floor
  when its predecessor is `1-overlap` complete (rather than fully finished), while still never *finishing*
  a floor before its predecessor. Compresses the makespan at a **rework-risk premium** proportional to the
  overlap fraction, so fast-tracking shows up as a distinct time/cost tradeoff on the Pareto frontier.
  `overlap=0` reproduces the strict finish-to-start line-of-balance exactly (backward-compatible default).
- **Sequence permutation** — opt-in (`permute_sequence`): trades flagged `reorderable` are permuted among
  their own slots while fixed trades stay put (e.g. Structure keeps leading), surfacing whether a different
  trade order shortens the run. Bounded — capped at 4 flexible trades / 6 sequence variants.
- The whole grid (crews × zoning × overlap × sequence) is **hard-capped at 800 scenarios** with the
  truncation reported (`truncated`), never silent. The result now carries a `levers` summary
  (zones / overlaps / sequence-variant count / crew candidates).
- Deterministic and pure throughout; `test_schedule_options` extended to cover both new levers +
  the bound. Client method `scheduleOptioneer` accepts the new options.

## v0.3.553 — SCHED-OPT: deterministic schedule optioneering (SPRINT B phase-1)

First slice of the schedule-optioneering track — permute the construction plan and score the options,
the way a dedicated optioneering tool does, but exactly and offline because our inputs (the Takt trade
train + per-floor production rates) are already present.

- **SCHED-OPT engine** (`schedule_options.py`) + `POST /projects/{pid}/schedule/optioneer`: enumerates a
  bounded crew-loading + work-face-zoning option grid over the Takt line-of-balance model and ranks every
  scenario. Levers: a **second crew** on the bottleneck (slowest) trades — halves that trade's
  days-per-floor at a mobilisation premium; and **zoning** — splitting each floor into Z work-face zones
  lets the train pipeline tighter (shorter makespan) at the cost of more concurrent crews + a per-zone
  setup. Work content is conserved across scenarios, so the enumerated tradeoff is schedule compression +
  peak congestion vs. a crew premium — the real buyout question.
- Each scenario carries makespan (days/weeks), peak concurrent crews, labor crew-days, and cost; the
  result ranks by a min-max-normalised weighted **time + cost score**, flags the **Pareto frontier** (not
  beaten on both time and cost), and returns a **recommended** option + its saving vs. the single-crew /
  one-zone baseline. Weighting toward cost keeps the baseline; toward time picks a compressed option.
- Deterministic and pure (no solver, no randomness) — fully unit-tested. Client method `scheduleOptioneer`
  wired; the scenario-comparison panel is the phase-2 follow-up.

## v0.3.552 — Quick-wins sprint: model-warnings feed + check-lane depth

A batch of low-risk, high-clarity refinements across the model-quality and coordination engines —
cleaning up the small items before the big-ticket sprints.

- **WARN-1 — unified model-warnings feed** (`GET /projects/{pid}/models/warnings`): a new
  `model_warnings.py` engine flattens every individual defect the hygiene lens (`model_qa` —
  duplicate GUIDs, orphans, overlapping duplicates, unenclosed spaces, blank names, wrong-storey)
  and the normative-conformance lens (`norm_valid`) surface into one worst-first punch list —
  fails before warns, each row carrying its offender sample for zoom-to-GUID. Where the model-CI
  badge says pass/warn/fail, this is the actionable list behind it.
- **NORM-VALID tails** — the conformance gauntlet gains two lanes: a STEP-syntax check that the
  ISO-10303-21 `FILE_NAME` header carries a name + timestamp, and a bSDD/classification-coverage
  check reporting the share of physical elements associated to a classification reference
  (pass ≥ 50%, else warn).
- **SCOPE-GAP spec-section refinement** — bid-package coverage now unions the CSI spec sections
  each covering package cites and surfaces them per discipline; a discipline covered by a package
  that names **no** spec section is flagged as `covered_without_specs` (thin, non-traceable
  coverage) — distinct from a true scope gap.
- **GOLDEN-THREAD seed** (`POST /projects/{pid}/golden-thread/seed`): populate the compliance-
  evidence ledger from the latest model-CI report — each check becomes a tracked requirement
  (outcome mapped from its status) so the thread starts from the checks already run instead of a
  blank slate. Idempotent — re-seeding after a fresh run only adds what's new.
- **DRAW-STATUS** — the drawing module gains a `lifecycle` field (Not Issued · Issued for
  Construction · Shop Drawing · As-Built), surfaced in the drawing list, distinct from the
  revision-status field.

## v0.3.551 — Hardening pass over v0.3.544–550

- Between-sprint adversarial bug-hunt + security hand-audit over the seven new engines (SCOPE-GAP,
  GOLDEN-THREAD, CLASH-TRIAGE XML, GIS-OUT, CBS-1, MEP-GRAPH, the RT-ORJSON swap). No crash / hang /
  security hole found — the two priority suspicions (a possible `mep_graph` longest-path hang on a
  cyclic network; division-by-zero across the ratio helpers) were both **verified safe** (BFS-parent
  reconstruction can't loop; every ratio is `if total else 0.0`-guarded). Three low-severity items fixed:
  - **GIS-OUT** — the near-pole longitude-scale guard was dead code (`cos(90°)` is `6e-17`, not `0`, so
    `or 1.0` never fired); now `max(..., 1.0)` clamps it so a site near the poles can't blow up the transform.
  - **CLASH-TRIAGE** — `_write_issues` no longer pops `_guids` off the caller's parsed rows (reads instead),
    so a future "parse once, write twice" caller can't silently lose the model-GUID anchoring.
  - **CLASH-TRIAGE** — the Navisworks XML import now rejects an over-large upload (>50 MB) before building
    the DOM, bounding memory (the row cap already bounded the created issues).

## v0.3.550 — RT-ORJSON remainder: orjson at the hot storage-blob sites

- **Faster index loads.** The response serializer already used orjson (v0.3.511); this swaps the
  remaining hot `json.loads/dumps` at the storage-blob call sites — the per-project **props.json index
  load** (on every model-index cache miss) and the **scan cache** read/write — to orjson, with the same
  graceful stdlib fallback for an orjson-less venv. **Measured on a 924 KB props blob: `orjson.loads`
  1.7× (19.8→11.4 ms), `orjson.dumps` 4.8× (16.1→3.4 ms)** vs stdlib; `OPT_NON_STR_KEYS` +
  `OPT_SERIALIZE_NUMPY` mirror stdlib's acceptance of int keys and `numpy.float64`. First of the RUNTIME
  ring's measured-win S-items.

## v0.3.549 — MEP-GRAPH: port connectivity graph + run/path extraction

- **From "unconnected ports" to the actual network.** `GET /projects/{pid}/mep/graph` builds a
  first-class port graph over `IfcDistributionPort` (nodes = MEP elements, edges = the port-to-port
  `IfcRelConnectsPorts` connections from `connect_mep`) and extracts the connected **runs**: each with
  its endpoints (degree-1 terminals), branch points (degree ≥3), class tally, and the **longest linear
  path** — the index-run backbone a balancing engineer follows and the foundation a real path-based
  pressure-loss calc needs (vs. today's per-segment sum). Isolated elements (no connected port) are
  reported as the wiring gap. Sixth item off the re-prioritized roadmap (R14 Tier-2), closing the NOW
  batch. *(Parallel/stacked run generation — the geometry-authoring half — remains open.)*

## v0.3.548 — CBS-1: Cost Breakdown Structure over the model estimate

- **The estimator's layering, not the developer proforma.** `GET /projects/{pid}/estimate/cbs` takes
  the model's takeoff-priced **direct cost** and layers it through **indirect / general conditions →
  contingency (known risks) → management reserve (unknown-unknowns, a PMBOK layer held separately from
  contingency) → overhead & profit → taxes & fees**, each with its amount, rate and share of the total.
  Every rate is overridable via query. Surfaced as a **🧱 Cost breakdown (CBS)** button in the Budget
  panel's model-estimate group. Fifth item off the re-prioritized roadmap (R14 Tier-3); conceptual-grade.

## v0.3.547 — GIS-OUT: BIM footprint → WGS84 GeoJSON

- **Drop the model onto a real map.** `GET /projects/{pid}/models/footprint.geojson` exports the
  building footprint (plan bounding box) + a site point as a **WGS84 GeoJSON FeatureCollection**,
  anchored on the model's `IfcSite` reference lat/long and transformed from local metres with a
  dependency-free **equirectangular local-tangent** approximation (rotated by the model's true-north
  bearing) — building-scale accurate, no pyproj. `available` is false when the model carries no site
  lat/long. Complements the inbound CityGML→GeoJSON site-context import. Fourth item off the
  re-prioritized roadmap (R14 Tier-3).

## v0.3.546 — CLASH-TRIAGE: import native Navisworks clash-report XML

- **The other standard clash export.** The XLSX clash-report importer already shipped; this adds the
  **native Navisworks XML** format (the `smart:` namespace `<clashresult>` export coordinators produce
  straight from Navisworks). `POST /projects/{pid}/coordination/import-xml` parses each clash into a
  `coordination_issue` — name → subject, its clash test → discipline, clash type/distance/status →
  description, and both element GlobalIds harvested from the `clashobjects` so it anchors on the model
  and round-trips to BCF. Namespace-agnostic and tolerant; untrusted XML is parsed with **defusedxml**
  (XXE / entity-expansion hardened). Third item off the re-prioritized roadmap (R14 Tier-3).

## v0.3.545 — GOLDEN-THREAD: the compliance evidence ledger

- **Every requirement traced to evidence + a sign-off.** A new **Compliance Evidence** register (one
  record per requirement → outcome → responsible party → evidence artifact, on an `open → evidenced →
  sign-off` workflow) plus `GET /projects/{pid}/golden-thread` — the rollup: how complete the thread is
  (**signed-off %**), the outcome/category spread, and the **broken-thread list** — requirements still
  missing evidence or a sign-off, ranked worst-first (a failed or pending requirement with no evidence
  attached is the top risk). Extends the point-in-time preflight/code checks into an auditable, versioned,
  sign-off-tracked record. Second item off the re-prioritized roadmap (R14 Tier-2). *(A dedicated
  golden-thread rollup panel is the open UI follow-up; the ledger records edit via the Quality workspace.)*

## v0.3.544 — SCOPE-GAP: does every element land in a bid package?

- **The scope hole a GC finds at buyout, found at precon.** `GET /projects/{pid}/bidding/scope-gap`
  maps the model's takeoff (grouped by NCS discipline) against the project's `bid_package` records and
  flags **gaps** — disciplines present in the model with *no* covering package, i.e. quantities not in
  any bid yet (with sample GUIDs to click-highlight the uncovered elements) — a covered-percentage, and
  **over-scoped packages** whose discipline has no model elements. Distinct from the ITB bid-*response*
  coverage. Surfaced under the Bidding leveling view as a **Model coverage** strip. First item off the
  freshly re-prioritized roadmap (R14 Tier-2).

## v0.3.543 — Docs refresh, roadmap reconciliation & dev-console polish

- **Roadmap reconciled + re-prioritized.** The R15 ring and the shippable R14 tiers are fully closed;
  the v0.3.510–542 wave moved to [roadmap-completed.md](docs/roadmap-completed.md) and `roadmap.md` was
  rewritten as a fresh, open-items-only backlog (NOW: SCOPE-GAP · GOLDEN-THREAD · CLASH-TRIAGE · GIS-OUT ·
  CBS-1 · MEP-GRAPH; a RUNTIME ring; R15/R14 tails; the flagship-L builds; decomposition + P2 carry-overs).
- **Docs brought current.** README's "recent work" recap now covers v0.3.413–542; `status.md` corrected
  (stale version + test count + the obsolete "authoring needs Blender" framing — in-browser authoring ships
  as server-side recipes); marketing one-liners gained the structural-solve/OpenSees, NORM-VALID, BEP-GEN,
  subset-export, range-estimate, revision→cost, and live-BCF entries. Pages demo snapshot regenerated.
- **Dev console fix.** The Vite dev "Multiple instances of Three.js" warning is silenced by also excluding
  `three` from `optimizeDeps` (the `@thatopen/*` packages import it raw, so pre-bundling the app's own copy
  loaded a second instance in dev) — with `resolve.dedupe: ["three"]`, every importer now shares the one
  `node_modules/three`. Production was already single-instance via `manualChunks`.

## v0.3.542 — EST-BANDS: range estimate (low / likely / high → probabilistic bid range)

- **A conceptual estimate is a range, not a number.** `GET /projects/{pid}/estimate/bands` prices the
  model's takeoff and puts a three-point **low / likely / high** band on every line from design-stage
  cost uncertainty by discipline (structure ±15%, MEP ±30%, sitework ±35%, …). It rolls up two ways: a
  **correlated envelope** (every line at its extreme together — the worst/best case) and an
  **independent probabilistic P10 / P50 / P90 bid range** (a CLT normal approximation of the summed
  per-line triangular distributions, which diversification tightens inside the envelope). Overlay a
  firm rate sheet by passing `overrides`. Surfaced as a **📊 Range (low/likely/high)** button in the
  Budget panel's model-estimate group. Conceptual-grade — not a bid.
- **Dev CORS fix.** The API's default `AEC_CORS_ORIGINS` now trusts **both** `http://localhost:5173`
  and `http://127.0.0.1:5173` — they're distinct CORS origins, and since the web app's default API URL
  is the `127.0.0.1` form, a dev opening the app at `127.0.0.1:5173` was previously blocked by CORS even
  with the API running. (Production is unaffected — same-origin via the nginx `/api` proxy.)

## v0.3.541 — MEETINGS: link action items to RFIs & issues

- **Minutes that trace to the record.** Meeting **action items** could reference their source meeting;
  they can now also link a **Linked RFI** and a **Linked Issue**, so a flagged action captured in
  minutes traces to the RFI or coordination issue it concerns — and each RFI/issue shows the action as
  an incoming reference in its related view. This closes the last MEETINGS sub-item (the meeting series,
  agenda→minutes, and action-item register were already in place).

## v0.3.540 — TRANSMIT-ITP: Inspection & Test Plan register

- **The QA plan, not just the results log.** Added an **Inspection & Test Plan** register — one record
  per planned inspection/test on a work activity, with the ITP essentials: the inspection point type
  (**Hold Point** / Witness Point / Review / Surveillance / Monitor), method, **acceptance criteria**,
  frequency, responsible + verifying party, and the record/form required. Its `planned → active →
  verified` workflow models a hold point releasing work and gates verification on acceptance criteria
  being set. This complements the existing `inspection` module (which logs field *results*) and closes
  the remaining TRANSMIT-ITP gap — numbered transmittals, the submittal review-matrix routing, and the
  supplier-deliverables register were already covered by the `transmittal` and `submittal` modules.

## v0.3.539 — PM-CLOSE: project charter + lessons-learned register

- **Closing the PMBOK process-group spine.** Two new config-driven registers on the module engine:
  a **Project Charter** (Preconstruction / initiating) — sponsor, business case, SMART objectives,
  scope in/out, budget authority, milestones, assumptions/constraints/risks, stakeholders, with a
  `draft → in_review → approved` authorization workflow — and a **Lessons Learned** register
  (Closeout / closing) — one record per lesson with category, phase, impact, root cause and a
  feed-forward recommendation, on a `logged → reviewed → adopted` workflow. Both appear automatically
  in their workspace nav (construction + developer) with generic CRUD, import, search and the SLA feed.

## v0.3.538 — ROLES-BIM: ISO 19650 information-management responsibility template

- **The BIM-org, not just the construction org.** The responsibility matrix's four starter templates
  were all construction/PM-oriented (design delivery, buyout, execution, closeout) over the same seven
  delivery-role columns. Added a **BIM information management (ISO 19650)** template that brings its own
  role columns — the BIM-org personas *Appointing Party · Information Manager · BIM Manager · BIM
  Coordinator · Task Team · QA/QC* — mapped across nine ISO 19650-2 information-management duties (EIR →
  BEP → CDE setup → authoring → federation/coordination → model QA → authorize → deliver → PIM→AIM
  handover). Templates may now declare their own `roles`, so applying it switches the matrix columns to
  the information-management org. Appears automatically in the existing Responsibility-matrix template
  picker.

## v0.3.537 — BEP-GEN: the BIM Execution Plan, generated from live config

- **The BEP is never a stale side-document.** `GET /projects/{pid}/bep` composes the ISO 19650 BIM
  Execution Plan from what the project *actually* has configured right now: standards + classification
  systems, information requirements (EIR/BEP/AIR coverage + IDS), the RACI responsibility matrix, CDE
  container state + metadata discipline, the source model's schema/exchange formats, and the
  model-quality acceptance gates (NORM-VALID / Model QA / IDS / change-control). Each section reports
  `configured` and degrades gracefully — a fresh project still yields a valid six-section skeleton that
  fills in as the team works, with a completeness roll-up. Surfaced as a **📘 Generate BIM Execution
  Plan** action in the CDE / Standards panel.

## v0.3.536 — REVISION-DELTA: the cost impact of a model revision

- **"What changed" → "what it costs."** `GET /projects/{pid}/versions/cost-delta?a=&b=` turns a
  version diff into a conceptual cost impact: **added** elements (present in the current model) are
  priced from the live quantity takeoff through the conceptual estimator; **removed** elements are
  counted by IFC class from the prior version's fingerprints (their quantities aren't stored, so they
  aren't priced); elements whose **quantity changed** are flagged for re-estimate (before/after
  magnitudes aren't both retained, so no automatic net is claimed). Honest about the version store's
  limits — a change-management aid, not a change order. Surfaced as a **$ Cost impact** button in the
  viewer's Version-compare tool, beside the 3D overlay.

## v0.3.535 — NORM-VALID: normative openBIM conformance gauntlet

- **Does this IFC *conform*, not just is it well-authored.** A validation gauntlet in the spirit of
  the buildingSMART validation service — `GET /projects/{pid}/models/norm-valid` runs header + schema
  + IFC implementer-agreement checks: a recognised `FILE_SCHEMA` and populated header, exactly one
  `IfcProject` carrying units + a geometric context, every `IfcRoot` GlobalId a valid & unique 22-char
  `IfcGloballyUniqueId`, OwnerHistory presence (required in IFC2X3, optional after), and no physical
  element left outside the spatial structure. Each check reports **pass / warn / fail**; `passed` is
  true when nothing fails (warnings don't block). Complements `model_qa` (authoring quality) and IDS
  (data completeness). Surfaced as a **📋 Normative validation** tool in the viewer's QA group.

## v0.3.534 — Harden the subset-export temp path (CodeQL py/path-injection)

- The `/export/subset.ifc` handler built its scratch filename from the URL `pid`
  (`subset-{pid}-….ifc`). Project ids are server-generated UUIDs, so this was not
  exploitable, but the taint tripped CodeQL's `py/path-injection`. The scratch file now
  comes from `tempfile.mkstemp` — a server-chosen path with no request input in it; `pid`
  survives only as the download filename in the `Content-Disposition` header.

## v0.3.533 — SUBSET-EXPORT: hand off a discipline slice as a standalone IFC

- **Selector → standalone IFC.** `GET /projects/{pid}/export/subset.ifc?query=<QUERY-DSL>` streams an
  IFC containing only the elements matching a selector (e.g. `IfcDuctSegment | IfcPipeSegment`,
  `discipline=Structural`) — the scope slice you hand a consultant. Every physical element outside the
  keep-set is removed via `root.remove_product` (which detaches its containment / opening / property
  relationships and purges the owned geometry); the spatial skeleton (project → site → building →
  storey → space) and shared units/contexts are preserved, so the slice is a valid, correctly-contained
  IFC with **GUIDs unchanged**. The export gates behind `require_export` like the source-IFC download,
  and runs on an uncached copy of the model so the shared in-memory index is never mutated. In the
  viewer's Query-select tool a **⬇ IFC** button downloads the slice for the current selector.

## v0.3.532 — FEM-EXPORT: analytical model → OpenSees (.tcl)

- **Third-party structural verification.** Export the W10-7 analytical frame as an OpenSees
  (`.tcl`) input file — dedup shared member endpoints into nodes, fully fix the base-level nodes,
  and write one `elasticBeamColumn` per member with a per-orientation geometric transform (a
  column's local axis is vertical, so it takes a different reference vector than a beam). Units are
  kip·inch·ksi; sections are nominal defaults, so the file is a runnable *geometry + connectivity +
  supports* skeleton an engineer re-sections and loads to independently verify the built-in
  gravity/lateral solver in a third-party FE solver. `GET /projects/{pid}/structure/opensees.tcl`
  streams the file (409 until an analytical model is derived); a **⬇ Export OpenSees (.tcl)** button
  sits next to the statics-solve tool in the viewer's structural panel.

## v0.3.531 — EST-ASSEMBLIES: cost-item unit-rate build-ups (R15)

- New **cost assemblies** — a unit rate composed from its component resources (labour crew +
  material + equipment + sub), the way an estimator actually builds a price, so the number is
  auditable and re-costs when a wage or material price moves. `GET /estimate/assemblies` returns a
  starter library (CMU wall, cast-in-place slab, metal-stud partition) with each rate pre-computed;
  `POST /estimate/assembly/price` builds up a rate from an `assembly_id` or a custom component list
  (`{resource, kind, qty, unit, unit_cost, waste_pct}`), supports per-resource `overrides`, and
  extends over a take-off `quantity`. Analytics panel gains a **Cost assemblies** table with a
  per-line quantity → total.

## v0.3.530 — SMART-VIEWS: clash-freshness (auto-flag stale coordination issues)

- Completes SMART-VIEWS: open **clash / coordination issues whose referenced elements changed**
  between two model versions are surfaced as likely-stale (resolved, moved, or worse).
  `GET /projects/{pid}/coordination/stale?a=&b=` lists them (reusing the version diff's
  added/removed/modified GUIDs against each topic's `element_guids`);
  `POST .../coordination/stale/recheck` flags each with a `model-changed` label + a re-verify comment.
  Deliberately **advisory — never auto-closes** (a changed element doesn't prove a clash is gone), and
  idempotent.

## v0.3.529 — BCF-API-SRV: viewpoints over the API (R15)

- The BCF-API 2.1 surface gains **viewpoints** — the camera + selection + snapshot that make a topic
  navigable in 3D. `GET/POST /bcf/2.1/projects/{pid}/topics/{guid}/viewpoints` map our camera
  (`position`/`target`) to the BCF `perspective_camera` (`camera_view_point` + unit
  `camera_direction`), `components.selection` / `visibility.exceptions`, and clipping planes; the PNG
  snapshot streams from `.../viewpoints/{vguid}/snapshot`. A viewpoint created over the BCF-API is the
  same row the native viewpoint route returns — completing the BCF sync-object set
  (topics · comments · viewpoints) external managers need.

## v0.3.528 — BCF-API-SRV: live BCF-API 2.1 (OpenCDE) endpoints (R15)

- New **server-side BCF-API 2.1** surface (`routers/bcf_api.py`) so external BCF managers — Revit,
  Navisworks, Solibri, BIMcollab, usBIM — connect and sync issues live instead of exchanging
  `.bcfzip` files. `GET /bcf/versions` negotiates the version, `GET /bcf/2.1/auth` advertises the
  token URL, `GET /bcf/2.1/projects` lists accessible projects, and topics (list / get-by-guid /
  create) + comments (list / create) map the standard BCF-API JSON — `topic_type`, `topic_status`,
  `assigned_to`, `creation_author`, `labels` — directly onto the existing `Topic` / `Comment` rows.
  A topic created over the BCF-API is the same row the native `/projects/{pid}/topics` returns (and
  round-trips through `.bcfzip` export), reusing the platform's Bearer-token auth + role gates.

## v0.3.527 — IFCPATCH-LIB: one-click model maintenance recipes (R15)

- New **model cleanup** — deterministic maintenance passes that remove dead data an IFC accumulates:
  **purge orphaned property sets** (an `IfcPropertySet` attached to no element or type — its owned
  properties go with it) and **purge empty groups** (a plain `IfcGroup` with no members; never
  systems / zones). Both are GUID-stable for kept elements, so pins / RFIs / clashes survive.
- `GET /projects/{pid}/model/maintenance` is a **dry-run scan** (what each recipe would remove, with
  a sample) — the recipes ride the existing `POST /edit` apply→republish pipeline
  (`purge_orphan_psets` / `purge_empty_groups`, both idempotent). New **🧹 Model cleanup** viewer tool
  scans and runs each purge with a live count.

## v0.3.526 — VERSION-COMPARE-3D: pick-any-two version overlay (R15)

- The viewer's version tool becomes a real **version compare**: pick **any two** published versions
  (not just the latest pair) and get the added / removed / modified summary plus a **◉ Overlay in 3D**
  that colours added elements green and modified elements amber in the loaded model (with a reset).
  Modified elements still list their change labels (renamed · reclassified · retyped · re-leveled ·
  properties · quantities) and select in 3D on click. Frontend-only — the per-version snapshot diff
  (`GET /versions/diff`) already shipped.
- **Security**: `smart_views.run` no longer echoes a `QueryError` string into its response (the saved
  selector is validated at save, so the branch is defensive) — clears a `py/stack-trace-exposure`
  CodeQL finding.

## v0.3.525 — SMART-VIEWS: saved property-driven view presets (R15)

- New **smart views** — user-authored, per-project saved view presets over the model (the
  Solibri/Navisworks "saved search → view" staple). Each is a name + a QUERY-DSL selector + a display
  mode (**isolate / colour / hide**) + an optional colour, persisted with the project. The **★ Smart
  views** viewer tool lists them, applies one (isolates / colours / hides the resolved elements in
  3D), and saves the current selector as a new preset. Built entirely on QUERY-DSL (`query_dsl.select`)
  + the storage sidecar — cheap glue, not a new subsystem.
- Endpoints (`GET/PUT /projects/{pid}/smart-views`, `GET …/{vid}/run`): selectors are validated at
  save (a bad selector rejects the whole set atomically with 422, never clobbering the saved views);
  caps on count/length + hex-checked colours (HARDEN pattern).

## v0.3.524 — CLOUD-BRIDGE: optional online licence validation (massing.cloud)

- New **massing.cloud licence bridge** (`license_cloud.py`) — the "online check" the licensing module
  always anticipated. Off by default (offline-first): the recorded plan is authoritative on its own,
  so a cloud outage never locks a paying operator out. When enabled, the app validates the recorded
  key against `POST {base}/validate` with the shared `X-Massing-Secret`, normalizes the verdict
  (unknown tier → free), and — via the admin **`POST /license/cloud-check`** (+ a *☁ Validate online*
  button in the licence panel) — writes the cloud-confirmed plan back to Settings. An explicit
  `valid:false` downgrades to Free; an unreachable cloud changes nothing.
- The shared secret lives only in the operator's config (`MASSING_CLOUD_SECRET`, a **secret** setting)
  — masked in the Settings catalog, never returned by any endpoint, never logged. Contract documented
  in [docs/massing-cloud-bridge.md](docs/massing-cloud-bridge.md) for the massing.cloud plugin to mirror.
- **Container hardening**: the API runtime image no longer copies the base image's global `npm` CLI
  (`/usr/local/lib/node_modules`) into production. The API invokes the IFC→Fragments converter via
  `node <script>` with deps in `/app/node_modules` and never runs `npm` at runtime, so dropping the
  npm CLI removes its bundled deps (cross-spawn / glob / minimatch / sigstore / tar) and their CVEs
  from the image, clearing the Trivy container-scan gate and shrinking the image.

## v0.3.523 — JOB-QUEUE: mutating jobs hold the project mutation lock

- Job handlers that **write project state** now run under `pid_lock.mutating(project_id)` — the same
  per-project lock the API edit path and the docmanager/edit_history sidecars already take. A queued
  mutating job (e.g. `escalation_scan`, which escalates records) can no longer interleave its
  read-modify-write with a concurrent edit or another mutating job on the same project.
- `register_kind(name, fn, mutating=True)` declares a mutating kind; the worker wraps only those
  (when the job carries a `project_id`) in the lock. Read/artifact kinds
  (`model_export`, `clash_detect`, `cobie_export`, `compiled_set_pdf`) are unaffected — the wrap is
  a no-op for them, so nothing serializes that doesn't need to.

## v0.3.522 — ENTITLE-1: consistent export entitlement enforcement

- **Closed the IFC-export side-doors**: `/model/export.ifc` and `/model/export.ifcx` now gate on the
  export entitlement just like `/source.ifc` did — previously a licensee could bypass the IFC gate
  through the drawings/standards routes when enforcement was on.
- **Gated the 3D-export routes** (`/model/export.gltf`, `/model/export.glb`) on the base (Home+)
  export entitlement, so free-tier enforcement now covers every model-out path.
- **Fixed the tier matrix**: `glb` (binary glTF) was absent from the base export set — it would have
  402'd even at Enterprise; it's now a Home+ base export alongside `gltf`. `ifcx` (IFC5 / ifcJSON) is
  declared as Commercial+ openBIM data-out. All gates remain **no-ops in open mode** (enforcement is
  off by default — no licence required until an operator flips `MASSING_LICENSE_ENFORCE`).

## v0.3.521 — CX-1: commissioning as a first-class loop (R14 Tier-1 complete)

- **Seed from the model** (`POST /cx/seed` + the ⚡ button on Turnover): equipment classes in the
  published model become GUID-keyed `asset_register` records (deduped on re-seed), and every
  systemed asset gets its phase-typed `commissioning` tests (Pre-Functional + Functional) — the
  Functional stamped with **FPT expected values** from the MEP equipment register (capacity / flow /
  size per system).
- **System × phase matrix** (`GET /cx/matrix`): the Cx wall chart — per-cell total / tested /
  accepted / pass / fail across Pre-Functional → Retro-Cx, with per-system asset counts and
  completion %. Rendered on the Turnover panel with per-system **dossier** drill-down
  (`GET /cx/dossier` — assets, tests by phase, expected values, best-effort punch mentions).
- With CX-1, PROC-LOOP, and REBAR-RULES/BBS shipped, **all of the 🔬 R14 Tier-1 ring is complete**.
- **TEST-GAPS closed**: the audit's "6 untested engines" was mostly overcount (5 already covered);
  the genuine gap — the distribution-waterfall investor allocator — now has a direct suite
  (dollar conservation, pref clearance, pro-rata classes, period synthesis).

## v0.3.520 — MODEL-CI-3 · PROC-LOOP · REBAR-RULES + BBS

- **Security**: the ⧉ compare overlay now allowlists its image source (data:image/png / blob: only),
  closing the CodeQL js/xss-through-dom warning on the file-picked prior revision.
- **REBAR-RULES + BBS (R14)**: a per-typology reinforcement catalog (`aec_data/rebar_rules.py`,
  ACI 318-informed — the column tie-spacing envelope min(16·d_bar, 48·d_tie, least dimension) with
  the governing limb named), a **cage checker** (`GET /rebar/check?column=` + the ✓ viewer tool —
  longitudinal bar count and tie spacing verified against the envelope; a bare column is a finding),
  and the **bar bending schedule** (`GET /rebar/bbs` + `.csv`, 📋 viewer tool): every authored
  `IfcReinforcingBar` grouped into marks by size · shape · cut length with unit mass (π r² × 7850)
  and total tonnage — the fabricator/5D quantity.

- **Model CI grows to a 5-check pack**: `ids` validates the model against the project's **pinned
  IDS** (the information-delivery contract — any failing specification fails the build; unpinned
  projects skip), and `qto_delta` compares headline per-class quantities against the previous CI
  run (>25% swings, appeared/vanished classes → warn — a review flag, never a hard fail; the
  baseline rides inside the stored report). `POST /ci/run?create_topics=true` turns each failing
  check into an open coordination Topic (BCF-model) so CI failures round-trip like any issue.
- **PROC-LOOP (R14)**: quote leveling with `record=true` persists every priced line as a
  `price_observation` (source="quote") — the **price-observation ledger**
  (`GET /procurement/price-history`) rolls up min/median/avg/max, the latest price + vendor,
  latest-vs-median drift, and a spark series per material. **Field material requests**: a new
  `material_request` module (requested→approved→ordered→delivered) plus
  `POST /procurement/material-request/suggest` — a QUERY-DSL model selection becomes per-class
  quantity suggestions straight from the QTO takeoff (volume→m³, area→m², else count), optionally
  created as requests keyed to the element GUIDs. Analytics panel gains the price ledger table and
  the suggest→create flow; the 3-way-match table now escapes record-derived text.

## v0.3.519 — RULE-LIB-2 geometric rule checks + PERF-4 complete

- **Geometric rule checks** (`POST /projects/{pid}/rules/geometry/run` + the ⛶ Geometry check
  viewer tool): AABB-level spatial checks on the clash broad-phase geometry path — `clearance`
  (door/equipment needs a clear approach on at least one side along its thin axis; host wall and
  floor excluded), `escape_distance` (straight-line to the nearest exit ≤ max — the lower bound of
  egress travel distance, so violations are always real), `clear_width` (accessible 815 mm opening
  proxy). QUERY-DSL selectors scope each check; a starter set runs when none are posted; violations
  isolate in the viewer. The spatial questions the property rule library can't express.
- **PERF-4 closed out**: trade AP is now a SQL `SUM` with state exclusion (`sum_field
  exclude_states`, NULL states kept — equivalence-tested against the old Python loop), and CV
  progress name→id resolution is a single id-only SQL probe (`find_id_by_field`, case-insensitive
  on the name field or title) instead of a per-estimate table scan.

## v0.3.518 — SURF-4b: turnover readiness + vendor procurement gate surfaced

- The Turnover panel now opens with a **readiness strip**: substantial-completion certificate ref +
  signers, record-model lock state (and locked version), or "ready to certify / not yet ready" when
  no certificate is on file — `GET /turnover/status`, previously backed but never surfaced.
- New **🚦 vendor gate** check on the bid-leveling tab: name a vendor and see can-bid / can-bill at
  a glance with the exact compliance blockers (COI status + expiry, prequal, subcontract execution,
  lien waiver) — `GET /procurement/gate`, also previously unsurfaced.

## v0.3.517 — SURF-2b: bid-leveling summary + invite-bidders surfaced

- The bid-leveling tab now opens with the **all-packages leveling summary** (`GET /bids/leveling` —
  low / high / avg / spread per package, previously backed but never surfaced); picking a package
  still drills into the per-bid detail. New **✉ Invite** action sends the ITB to comma-separated
  companies via the existing `POST /bidding/packages/{id}/invite` and reports who was invited.
  Frontend-only; panel live-load verified in the preview.

## v0.3.516 — MARKUP-2d: live co-markup — the MARKUP-2 track is complete

- **Live co-markup**: a new SSE stream (`GET /projects/{pid}/drawings/markup/stream`, mirroring the
  pull-plan/notifications pattern — cheap count+latest signature polled server-side, fresh session
  per poll) pushes whenever anyone saves a markup, and the drawings browser subscribes on open — so
  every open sheet **live-refreshes its pins the moment a teammate marks up**, no reload. Resilient
  `liveStream` client handle; the initial snapshot is skipped so opening doesn't double-load.
- With 2a (stamp library + slip-sheet), 2b (cross-sheet grid), and 2c (overlay compare), **queue #1
  MARKUP-2 is fully shipped** across v0.3.512–516. Sheet-space peer cursors remain a polish idea on
  the presence roster (free-form viewpoint payload — no protocol change needed when wanted).

## v0.3.515 — MARKUP-2c: light-table overlay compare

- **"⧉ Compare"** on any sheet view overlays an uploaded prior revision (SVG, or PDF page 1
  rasterized via the bundled pdf.js) on the live sheet, classic light-table style: the current sheet
  tints **blue**, the prior tints **red** with multiply blending — shared linework reads dark,
  removed-since-prior work pops red, added work pops blue. Adjustable prior-layer opacity; rides the
  existing pan/zoom (the overlay lives in the transformed stage); second click toggles off and
  restores normal rendering. Frontend-only — no server change.
- Remaining MARKUP slice: 2d live co-markup (2D presence payload + markup-mutation broadcast).

## v0.3.514 — SPRINT 2: dashboard UNION-ALL · CI-on-publish + clash check · cross-sheet markups grid

**DASH-UNION (PERF-4)** — the role dashboard's per-module status tallies now come from **one
UNION-ALL round-trip** (`modules.state_counts_all`) instead of one GROUP BY per registered module
(~124 queries). Counts proven byte-identical by an equivalence test against every per-module query.

**MODEL-CI-2 (#6)** — the quality gate is now **automatic**: every successful publish enqueues a
`model_ci` job on the durable queue, so the badge is always fresh without anyone clicking "run"
(best-effort — a queue hiccup never fails a good publish). The pack gains a third check: **Latest
clash run** reads the newest `clash_detect` job result (clashes → warn, zero → pass, no run → skip —
coordination work, not automatically a defect). IDS/QTO-delta checks remain open (MODEL-CI-3).

**MARKUP-2b (#1)** — the **cross-sheet markups grid**: a "☰ Markups" button in the drawings browser
lists every markup in the project — sheet, kind, note, measure, author, revision, RFI-link and
⟳ carried-forward status — with Σ totals per kind (count + summed distance/area). DOM built with
`textContent` throughout (XSS-safe by construction). `drawingMarkup()` without a sheet now returns
the whole project (the server always supported it).

## v0.3.513 — SPRINT 1: XLSX round-trip · sheet DXF · selector-scoped clash · 4D variance · apply-leveling

Five queue items in one sprint release (the new cadence: targeted tests per feature while building,
one full-suite + gates + CI pass at the sprint boundary).

**XLSX-ROUNDTRIP (#2)** — the single most-used daily openBIM workflow (IfcCSV-style), end to end:
  - **Export** `GET /projects/{pid}/model/roundtrip.csv?props=Pset_WallCommon.FireRating,…` — one row
    per element (guid, ifc_class, name + the chosen `Pset.Prop` columns), formula-injection-guarded
    for Excel.
  - **Dry-run diff** `POST /projects/{pid}/model/roundtrip/diff` (CSV or XLSX upload) — exactly which
    cells would change (`{guid, pset, prop, old, new}`), unknown GUIDs reported, blank cells ignored,
    **`dtype` inferred from the OLD value's type** so a numeric property edited in a spreadsheet
    doesn't silently flip to a string. Nothing is written by the diff.
  - **Apply** rides the existing GUID-stable edit path: a new **`set_props_by_guid`** batch recipe
    (`aec_data.edit_asbuilt`) applies the whole sheet in ONE model pass + republish — not one edit
    call per cell. Bad rows are skipped, never abort the batch.
  - Viewer gains **"⇄ Property round-trip (CSV/XLSX)"**: pick columns → export → upload the edited
    file → review the diff table → one-click "Apply N changes + republish". New
    `roundtripExport`/`roundtripDiff` client methods.
- `test_xlsx_roundtrip` covers the recipe against a real IFC (str + typed float + skipped bad row)
  and the endpoints (guarded export, diff semantics, 422s).

**DXF-EXPORT (#3)** — every composed **sheet** now exports as editable R12 CAD linework, not just
paper: `GET /drawings/sheet.dxf` (same composition as sheet.svg/pdf) with layers
BORDER / VIEW-n / ANNO / TITLEBLOCK, annotation LINE/CIRCLE/TEXT entities, the titleblock as TEXT,
and the SVG-space Y flipped for DXF's Y-up. New `render_sheet_dxf` + dxf.py entity builders
(LINE/CIRCLE/TEXT/document); a **↓ DXF** button beside ↓ SVG downloads any view or sheet
(plan/section/elevation .dxf routes already shipped). Clears the PDF-only consultant-contract blocker.

**QUERY-DSL wiring (#5)** — the clash engine + route now accept **selector-scoped sides**:
`clash.detect(..., guids_a=, guids_b=)` composes GUID-set filters with the class filters, and
`POST /clash` takes `a_q`/`b_q` selector strings (`IfcDuctSegment & storey=L3`) resolved through
`query_dsl.select` (bad selector → 422). One grammar now scopes isolate, rules, CI, and clash.

**FOURD-SIM-2 (#7)** — planned-vs-actual on the 4D playback: each frame splits its completions into
`late_guids` / `early_guids` (activity `actual_finish` vs `finish`, hard-tied and trade-mapped
elements alike), and the player tints slipped work **red** / ahead-of-plan work **green** over the
amber "built today" flash, with late/early counts in the readout. On-time work stays neutral.

**RESOURCE-LEVEL-2 (#8)** — leveling now has a WRITE half: `POST /schedule/resource-leveling/apply
{cap}` applies one leveling round — over-allocated activities with CPM float shift forward
(week-granular, most-float-first, **the finish never moves**, critical path never shifts), mutating
`schedule_activity` dates through the audited module engine. Returns moves + before/after peak and
over-allocated weeks, truthfully reporting when a plan *can't* level under the cap. Schedule panel
gains **⚖ Level** behind an explicit confirm; re-renders CPM/Gantt on success.

## v0.3.512 — MARKUP-2a: project stamp library in the editor + slip-sheet carry-forward (queue #1)

- First MARKUP-2 slice. Scoping note: the markup stack was far ahead of the roadmap line — the 2D
  editor (8 tools), server-persisted structured markups with RFI promotion, the stamp-template
  library, the full sheet-revision register, and the presence/SSE plumbing all already shipped. The
  genuine gaps are integration + a few net-new UIs; this slice closes the two highest-leverage:
  - **Project stamp library in the editor** — the PDF editor's stamp picker now leads with the
    server library (`GET /stamps/library`: EJCDC/CSI review, inspection, status, seal templates),
    each review template fanned out per disposition as a dynamic `{{user}}/{{date}}` stamp, with the
    quick built-ins behind it. Wired automatically for every server-PDF session via `openPdfUrl`.
  - **Slip-sheet carry-forward (the honest workflow)** — markups now stamp the drawing register's
    **current revision** at save (`data.rev`, both the SVG-pin and `#pdf` editor spaces). Revising a
    sheet (`POST /drawings/{id}/revise`) tags every pre-existing markup `carried_from: <old rev>` —
    they keep rendering (a located comment is never dropped) but show as **⟳ carried — "verify
    against the current revision"** (dashed amber pin + tooltip). Fresh markups stamp the new rev;
    re-revising carries only untagged rows. `markups_carried` reported in the revise response.
- `test_markup` extended with the full slip-sheet round-trip (stamp → revise → carry → fresh-rev →
  re-revise). Remaining slices: MARKUP-2b markups grid · 2c overlay compare · 2d live co-markup.

## v0.3.511 — RT-ORJSON: Rust-backed JSON responses (⚙️ RUNTIME ring #1)

- Every default API response now serializes with **orjson** (Rust; Apache-2.0/MIT) — measured
  **7.1–9.4× faster** than stdlib on our representative payloads (a 5k-element property index drops
  27.5 → 3.8 ms per response; 2k module records 4.4 → 0.6 ms; 300 4D frames 1.6 → 0.2 ms).
- Implementation notes: we ship our **own** thin `JSONResponse` subclass rather than FastAPI's
  `ORJSONResponse` (deprecated in current FastAPI — its native Pydantic path only covers *annotated*
  routes, while most of our endpoints return plain dicts that still render through the default
  response class). `OPT_NON_STR_KEYS` preserves stdlib behavior for int-keyed rollups and
  `OPT_SERIALIZE_NUMPY` for `numpy.float64` (a float *subclass* stdlib accepted silently — the full
  suite caught 12 analysis endpoints emitting it; numpy arrays now serialize natively too). One real
  behavior change: `NaN`/`Infinity` now serialize as `null` instead of stdlib's literal `NaN` — which
  was *invalid JSON* that would have broken any browser `JSON.parse`. Graceful fallback to stdlib if
  orjson is absent. Dependency added via the hash-locked flow (`requirements.in`
  → the `lockfile.yml` pip-compile workflow in the prod py3.12 container → `requirements.lock`; the
  regenerated lock adds exactly one package, zero drift).
- Verified: warnings-as-errors smoke + the full 275-suite gate exercising every endpoint through the
  orjson render path (which also caught the int-key case).

## v0.3.510 — HARDEN-2: security + bug audit of the queue wave · roadmap reconciliation · RUNTIME ring

- A dedicated hand audit of everything shipped v0.3.495–509 (beyond CodeQL's 0-alert baseline) found
  and fixed 2 security issues + 7 bugs — every fix test-locked:
  - **S1 (sec)** — the job queue was a side door around the escalation admin gate: an *editor* could
    enqueue `escalation_scan` (with an arbitrary ladder) even though `POST /escalations/run` is
    admin-only + audited. Job kinds now carry a per-kind minimum role checked at enqueue (mirroring
    `require_role`, incl. the dev bypass) and privileged enqueues write the same audit trail.
  - **S2 (sec)** — the rule library was unbounded: caps added (≤200 rules, ≤500-char selectors,
    ≤40-char ids) so a stored library can't amplify viewer-level `GET /rules/run` into unbounded CPU.
  - **B1** — the v0.3.496 `/topics` + `/pins` payload caps kept the *oldest* rows, silently hiding
    every newly created issue/pin past the cap. The cap now keeps the newest (desc + re-sort so
    under-cap responses are byte-identical to before).
  - **B2** — QUERY-DSL's operator split took the highest-precedence operator *anywhere*, so a quoted
    value containing `=`/`>` (`Reference~"C=1"`) mis-parsed and silently matched nothing — a stored
    rule could false-"pass" Model-CI. Now leftmost-operator, quote-aware; and a bare ifc-prefixed
    *field* (`ifc_class`) is no longer hijacked by the bare-class shorthand.
  - **B3** — `parse_mspdi` imported MS Project *summary* tasks (project/WBS rollups are named + dated)
    as phantom activities; `<Summary>1</Summary>` / outline-0 tasks are now skipped.
  - **B4/B5** — 4D player: an empty-frames reload left live controls over `frames:[]` (TypeError) —
    now fully resets; and `showResult` gained an `onClose` hook so closing the modal (✕/Esc/backdrop/
    replaced) stops the play timer and restores visibility instead of leaving the model isolated.
  - **B6** — Data-QA severity dots never rendered (`high/medium/low` map vs the endpoint's
    `required/recommended`); **B7** — the exported `.xer` now carries the project name in ERMHDR.
- **Roadmap reconciliation:** all shipped items (the v0.3.493–509 queue wave AND the v0.3.457–492
  P1/P2 run) moved to [roadmap-completed.md](docs/roadmap-completed.md); [roadmap.md](docs/roadmap.md)
  rewritten as open-items-only with a fresh prioritized queue (MARKUP-2 → XLSX-ROUNDTRIP → DXF-EXPORT
  → PERF-4 remainder → the *-2 follow-ups → R14 Tier-1 → REL/test-gap carry-overs).
- **⚙️ RUNTIME ring added** (researched, license-vetted): orjson (first), uvloop (prod container),
  msgspec/zstd (investigate), oxlint, Node-22 lane → Rolldown/Vite-8 trial, TanStack Virtual,
  three-mesh-bvh (investigate), knip — each gated on a measured before/after win.

## v0.3.509 — MODEL-CI: "Automate-lite" quality-gate check pack (queue #16)

- A model check pack that runs on demand and produces a **pass / warn / fail badge** stored as an
  artifact, so every model version carries a quality gate. Each check is a thin adapter over an engine
  that already ships — the pack grows by registering one function (same shape as the job-kind registry):
  - **Rule library** — the RULE-LIB rules must pass; a high-severity failure fails the build, medium/low
    warns.
  - **Elements named** — a data-completeness gate on the share of named elements (<50% fail, <90% warn).
- New `aec_api/model_ci.py` (per-project JSON blob, no migration; a broken check fails rather than
  crashing the run) + `POST /projects/{pid}/ci/run` and `GET /projects/{pid}/ci/latest` (the badge
  source). Viewer gains a **"▢ Model CI (quality gate)"** tool showing the overall badge + per-check
  status; `ciRun`/`ciLatest` client methods + `ModelCiReport` type. `test_model_ci` (275 suites green).
- **MODEL-CI-2:** auto-run on publish/option-branch save (enqueue a CI job on the durable queue) + more
  checks (clash / IDS / QTO-delta) and BCF/report artifacts — the engines exist; wiring them into the
  pack + the publish hook is the follow-up.

## v0.3.508 — RESOURCE-LEVEL: multiple named schedule baselines + variance (queue #15)

- The single plan-of-record baseline becomes a **library of named baselines** — "GMP", "Recovery",
  "post-ASI-014" — each a frozen snapshot of every activity's planned start/finish/budget, so a team can
  track drift against the contract baseline *and* a later re-baseline at the same time. Variance can be
  measured against any chosen baseline (or `latest`): per-activity slip in days + added/removed + a
  by-status rollup (slipped / improved / on-baseline / added / removed / max-slip).
- New `aec_api/schedule_baselines.py` (per-project JSON blob, bounded history, no migration) +
  `GET/POST /schedule/baselines`, `DELETE /schedule/baselines/{id}`,
  `GET /schedule/baselines/{id|latest}/variance`. The legacy singular `/schedule/baseline` +
  `/schedule/variance` are untouched — the named library is a superset. Schedule panel gains a
  **"📌 Baselines"** drawer (capture / list / click-to-compare / delete); client methods added.
  `test_schedule_baselines` (274 suites green).
- Resource-loading S-curves + the over-allocation leveling *advisory* already ship
  (`resource_loading.py`); *applying* a level (mutating dates within float) is the RESOURCE-LEVEL-2
  follow-up — it rewrites the schedule, so it lands on its own with an explicit confirm.

## v0.3.507 — RULE-LIB: user-authored parametric rule library (queue #14)

- A Solibri-style rule library a firm can author without code, built on QUERY-DSL. Each rule is two
  selector strings + a severity: **`scope`** (which elements it applies to) and **`require`** (the
  condition each in-scope element must satisfy). An in-scope element that fails `require` is a
  violation — so "every fire door needs a fire rating" is `scope: IfcDoor` / `require:
  Pset_DoorCommon.FireRating`, and "external walls declare a fire rating" is `scope: IfcWall &
  Pset_WallCommon.IsExternal=true` / `require: Pset_WallCommon.FireRating`.
- New `aec_api/rule_library.py` (per-project JSON blob, no migration; a starter set seeds an empty
  library) + `GET/PUT /projects/{pid}/rules` (selectors validated before an atomic save → 422 on a bad
  rule) and `GET /projects/{pid}/rules/run` → per-rule pass/fail + offending GUIDs + by-severity
  rollup. Viewer gains a **"✔ Rule check"** tool listing each rule's pass/fail with an "isolate
  failures" link; new `rulesRun` client method. `test_rule_library` (273 suites green).
- Geometric/relational checks (clearance-in-front-of, escape distance, accessible route) need swept
  geometry, not the property index — deferred to a RULE-LIB-2 riding the logistics/clash geometry path.

## v0.3.506 — QUERY-DSL: a selector language over the model (queue #13)

- Adds a compact selector grammar so one filter language scopes clash runs, view filters, schedules,
  bulk edits, and MCP tools — instead of each feature inventing its own filter shape. Combine terms
  with `&`: `IfcWall & Pset_WallCommon.FireRating=2HR & storey=L3`. Fields: `ifc_class`, `storey`,
  `type_name` (alias `type`), `name`, `discipline`, or any `Pset.Prop`; operators `= != >= <= > < ~`
  (contains) plus a bare `Pset.Prop` for existence. Comparisons are numeric when both sides parse as
  numbers, else case-insensitive string.
- New `aec_api/query_dsl.py` (`parse`/`matches`/`select`, reusing `model_query._val` for field
  resolution) + `GET /projects/{pid}/model/select?q=…` → matching GUIDs + parsed predicates (bad query
  → 422). Viewer gains a **"🔎 Query-select (filter language)"** tool that runs a query and isolates
  the matches in 3D; new `modelSelect` client method. Unit-tested end to end (`test_query_dsl`, 272 suites).

## v0.3.505 — FOURD-SIM: time-phased 4D construction playback in the viewer (queue #12)

- Turns the (already server-computed + unit-tested) `/schedule/4d` timeline into a viewer playback — the
  one genuinely-missing piece of 4D. A new **"⏱ 4D construction sequence (playback)"** tool loads the
  day-by-day timeline and lets you **scrub or auto-play** through construction days: every element built
  up to the current day is shown, everything not yet built is hidden, and the day's completions flash
  **amber** — so the model assembles itself as the sequence advances (the Navisworks TimeLiner / SYNCHRO
  core). Source selector (auto / GC schedule / takt), day slider, play/pause/step/reset, and a
  day·date·%·built readout. Uses the schedule's element↔activity ties (hard-tied first, then by trade +
  floor). New `viewer/fourD.ts` + reusable `LayerManager.colorGuids`/`resetColors` primitives.
- Scope note (audit correction): 4D element↔activity linking and temporary site-logistics geometry were
  **already shipped** (the `element_guids` tie + "Tie 3D selection", and W9-5 logistics with path motion
  and swept-crane clash). The only real gap was the viewer never consuming the 4D frames — now closed.
  Planned-vs-actual variance *coloring* on the timeline (the math ships in `/schedule/variance`) follows
  as FOURD-SIM-2.

## v0.3.504 — SCHED-P6: P6 .xer + MS-Project XML export / round-trip (queue #11)

- Closes the schedule round-trip. Import already read Primavera P6 **.xer** and **PMXML**; this adds the
  return path so contractor updates flow both ways without GUID drift:
  - **Export** `GET /projects/{pid}/schedule/export?fmt=xer|msp` serializes the *live* schedule — every
    `schedule_activity` (imported **and** hand-entered, with the GC's edits) — keyed by the P6 activity
    code (`wbs`). `xer` → a P6 `.xer` (TASK table with task_code/dates/type/percent); `msp` → **MS-Project
    XML (MSPDI)** with the code in each task's `<WBS>`.
  - **Round-trip** closes: re-importing an exported file matches the same records by code and updates in
    place. Import now also auto-detects **MSPDI** (`<Task>`) alongside P6 PMXML (`<Activity>`), so a file
    edited in MS Project comes back cleanly — new `parse_mspdi` + `to_xer`/`to_mspdi` in `aec_data.schedule`.
  - Schedule panel gains **⤓ Export .xer** / **⤓ Export MSP .xml** buttons next to the P6/MSP import;
    new `exportSchedule` client method.

## v0.3.503 — WFE-2: escalation surface on the portal home

- Surfaces the v0.3.502 escalation engine so it isn't a backend orphan. The portal command-center home,
  below the "⏰ Deadlines" feed, now shows an **"▲ Escalations"** section whenever overdue records have
  crossed an escalation rung: a per-level summary (L3×n · L2×n · L1×n), the top items badged with their
  level + days-late + ball-in-court party, and a one-click **"Escalate & notify the ball-in-court
  party"** action. The action is admin-gated on the server (a 403 surfaces as a toast); on success it
  re-renders the home so the freshly-cleared items drop off. New `escalationsScan`/`escalationsRun`
  client methods + `EscalationScan`/`EscalationRun` types.

## v0.3.502 — WORKFLOW-ENGINE: overdue escalation + explicit ball-in-court (queue #10)

- The workflow layer already had the full state machine (per-doc-type states/transitions, party gating,
  `requires`/evidence gates, transition audit, notifications feed + SSE, and a `due_feed` SLA view).
  The genuine gaps were **automation and clarity**, and this closes both:
  - **Explicit ball-in-court** — a record's `party_owner` now **tracks the workflow** instead of going
    stale at creation. Each transition moves it to the new state's court (the party owing the primary
    next move, e.g. an RFI entering `open` → *Consultant/OwnersRep*, then `answered` → *GC*), so
    "whose court is this in?" is a stored, filterable, board-groupable value.
  - **Overdue escalation** — a new `escalation.py` engine turns the read-only `due_feed` into action.
    Each overdue record climbs an escalation **ladder** as it ages (L1 at 0–2 days late, L2 at 3–6,
    L3 at 7+); `run` writes an `escalation:L{n}` entry to the record's timeline, which the existing
    notifications feed surfaces to the ball-in-court party and the assignee — so an ignored RFI /
    submittal / change order nudges the responsible party harder the longer it sits. Idempotent per
    rung (guarded by the highest level already on the timeline), so a nightly pass never spams.
  - Endpoints `GET /projects/{pid}/escalations` (read-only preview) + `POST …/escalations/run`
    (admin, audited), plus an `escalation_scan` durable **job kind** so the pass can run off the
    request path / on a schedule (crash-recovery safe because it's idempotent).
- UI surface (an escalation badge on the notifications/SLA view) follows as WFE-2.

## v0.3.501 — fix(sec): escape untrusted text in the Budget estimating drawer (XSS)

- Closes a stored/DOM-XSS path introduced in v0.3.499 (SURF-2): the "📐 Estimate from the model" card
  wrote an uploaded DXF's **filename** — and server/model-derived free-text (layer names, storey labels,
  trade names, IFC-class strings, unit labels) — into `innerHTML` without escaping. A file named
  `<img src=x onerror=…>.dxf` would have executed script on selection. All such interpolations now pass
  through a shared `esc()` helper (now exported from `ui/charts`). Numeric/enum fields are unaffected.

## v0.3.500 — SURF-4: Data-QA surface — required-property completeness in the viewer (queue #9)

- Fourth UI-surfacing wave item: a **"🔍 Data QA"** button in the viewer's QA section surfaces the
  backed-but-unsurfaced `/elements/qa` required-property-completeness engine. It renders the overall
  compliant/non-compliant split with a percentage, then a per-rule breakdown (label, severity dot,
  present vs. missing counts). Each rule with gaps offers a **"select missing"** link that highlights
  the offending elements in the model (up to 200 GUIDs) via the existing `sets.fromGuids` → `selectMap`
  path — so a modeler can jump straight from "37 walls missing FireRating" to those walls on screen.
- Audit note: the codebase-review "orphan capability" count was materially overstated. SURF-3 (phasing/
  LOD) and most SURF-4 candidates (code-check, model-health, quantity distributions) were already
  surfaced under different route/method names; the recipe dispatch-by-name path produces false-positive
  "orphans" in a wrapper-name heuristic. Verified by feature/route, not wrapper name, before building.

## v0.3.499 — SURF-2: estimating/takeoff surface — model estimates + DXF takeoff (queue #7)

- Second UI-surfacing wave item: a **"📐 Estimate from the model"** card in the Budget panel wires
  up four backed-but-unsurfaced estimating capabilities, each filling a shared results drawer:
  - **＄ Conceptual (unit-rate)** — `estimateFromModel`: the IFC takeoff × cost-DB unit rates →
    priced line items, total, and the unpriced-class list.
  - **🧱 Resource-based (L/M/E)** — `estimateResourceBased`: assembly build-ups (labor + material +
    equipment) with crew-hours and a by-trade table.
  - **🏢 QTO by floor** — `qtoByFloor`: quantity + cost per storey and discipline.
  - **⬒ Takeoff a DXF** — `takeoffDxf`: a 2D CAD file picker → linear metres, enclosed area, and
    block counts per layer (flags unitless DXFs).
- All four routes ship + are CI-covered; pure surface. Frontend-only (backend tree identical to
  v0.3.498); typecheck · lint · 121 vitest · build green; panel load-verified.

## v0.3.498 — SURF-1: schedule interop surface — P6/MSP import, alerts, earned schedule (queue #6)

- First of the **UI-surfacing wave**: three fully-backed schedule capabilities that had **no
  user-facing surface** now appear in the Schedule panel's toolbar:
  - **⇪ Import P6/MSP** — a file picker feeding `importXer` (Primavera `.xer` or MS-Project
    `.xml`/PMXML, auto-detected); imported tasks become editable `schedule_activity` records with
    real calendar dates and the CPM/Gantt re-renders off them. The #1 scheduler-credibility gate.
  - **🔔 Alerts** — the predictive `schedule/alerts` (overdue · late-start · at-risk predecessor ·
    SPI · procurement) in a collapsible drawer with severity dots + high/medium/low counts.
  - **⏱ Earned Schedule** — the time-based EVM metric (`evm/earned-schedule`: SPI(t), SV(t) periods,
    forecast finish) alongside the existing dollar earned-value card.
- All three routes already ship + are CI-covered; this is pure surface. Frontend-only (backend tree
  identical to v0.3.497); typecheck · lint · 121 vitest · build green; panel module load-verified.

## v0.3.497 — PANEL-LAZY: portal panels dynamic-imported out of the eager shell (queue #5)

- The ~30 secondary portal panels (operations/FCA/spine/resilience/energy/turnover, analytics,
  aiassist, EVM, WIP, ledger, traceability, resource-loading, design/lifecycle/diligence/ESG,
  materials, module-graph, standards/program/BIM-KPI/IDS/model-analysis, responsibility, documents,
  budget, schedule-views) are now **dynamically imported at first open** instead of statically bundled
  into the app shell. Each panel file (and its heavy deps — charts, tables, module-graph) becomes its
  own chunk fetched only when the user navigates to that destination.
- The wrapper methods went from `renderX(this.panelCtx())` to `async () => (await import("./panels/Y"))
  .renderX(...)`; every call site already `void`s the result or routes through `goDest`/dispatch
  (Promise-tolerant), so behaviour is unchanged. Verified: the dynamic chunk resolves and exposes its
  renderers; build splits ~15 panel chunks (aiassist 16KB, analytics 20KB, design 18KB, budget 14KB…)
  out of the eager `index-*.js` the CI bundle budget reads.
- Frontend-only (backend tree identical to v0.3.496); web gates green (typecheck · lint · 121 vitest ·
  build); live-verified in the dev preview.

## v0.3.496 — PERF-4a: test-fastpath schema-sync skip · topics/pins payload caps (queue #4)

- **TEST-FASTPATH**: `init_db` now detects a **brand-new database** (no known table present before
  `create_all`) and skips the additive `_ensure_columns`/`_ensure_indexes` reconciliation — on a
  fresh DB `create_all` already builds every table + index current, so the sync (an `inspect`
  round-trip per ~130 tables + a `checkfirst`-create per index) was pure startup overhead. Every
  test spins up a fresh SQLite DB, so this trims the bulk of per-test boot cost; the upgrade path
  (some tables predate the build) still reconciles exactly as before. `test_migrate` still exercises
  `_ensure_columns`/`_ensure_indexes` directly, unchanged.
- **PAYLOAD-CAPS**: `GET /projects/{pid}/topics` gains `limit` (default 500, hard cap 2000) +
  `offset` pagination — on a mega-project the issue/clash log is the unbounded-serialize growth
  driver; `GET /pins` hard-caps at 5000 (beyond usefully renderable). Existing param-less callers
  get the first newest-order page; over-cap limits clamp rather than error.
- Remaining PERF-4: the 124-query dashboard UNION-ALL is a larger rewrite deferred to its own batch.
- 270/270 backend suites; web gates green.

## v0.3.495 — PERF-3: QTO/discipline caching · clash off the request path (queue #3)

- **QTO-CACHE**: `qto.takeoff_file` was already memoized on (path, mtime, cost-map); this extends the
  same mtime-keyed cache to `discipline_summary_file` (the `/quantities/disciplines` roll-up), which
  falls back to per-element `create_shape` for volume/length — it re-ran the geometry pass on every
  GET. Bounded LRU (24 entries), evict-oldest; a re-parse (new mtime) yields a fresh entry so it can
  never go stale.
- **CLASH-JOBS**: a new `clash_detect` job kind runs the narrow-phase (mesh-boolean) clash on the
  durable worker instead of a request slot — the same engine as `POST /projects/{pid}/clash`, so a
  minutes-long large-model run never holds a thread or hits the HTTP timeout. Returns the clash
  summary + top rows as a job result; topic creation stays on the interactive route.
- Test-proven: `clash_detect` round-trips through the queue; `discipline_summary_file` cache verified
  by test_discipline; 270/270 backend suites, web gates green.

## v0.3.494 — PERF: async-block, geometry cache, frontend leaks (execution queue NOW #1–2, #4)

- **PERF-1 (ASYNC-BLOCK)**: the pdf_info/merge/split/extract/rotate routes, the module Excel/CSV
  import parse, and the large source-IFC / discipline-model upload writes now run in a threadpool —
  they were `async def` calling blocking pypdf / openpyxl / multi-hundred-MB `write_bytes` + MinIO
  `put` on the event loop, stalling **every** request in the process. (The sibling pdf_stamp/seal
  routes already did this; now they all do.)
- **PERF-2 (GEOM-CACHE)**: `drawings.bake()` — the dominant per-request CPU cost, re-tessellating the
  whole model on every section/elevation/DXF/sheet view — is now **memoized per model object**
  (`open_model` is lru-cached, so an unchanged file hands back the same object; a re-parse yields a
  new object → fresh bake, so it can't serve stale geometry). Added `world_bounds()` that returns the
  model AABB without building trimeshes (reuses the bake cache when present), and env/wind now derives
  its bounding box through it instead of a full bake. Tested (second bake is identity; bounds agree).
- **PERF-4 (frontend leaks)**: the UX-2 guide-line `pointermove` listener is installed **once**
  instead of stacking a new one (plus a leaked closure) on every persona-triggered `buildToolsPanel`
  rebuild; `collabPresence` now keeps + exposes `dispose()` to clear its 20 s heartbeat interval and
  close its SSE stream on viewer teardown (both previously leaked on re-init).
- Backend suite green; web gates green (typecheck · lint · 121 vitest · build). No behaviour change —
  pure performance + hygiene.

## v0.3.493 — SEC: attachment stored-XSS fix · 🧭 R15 landscape plan + re-prioritized queue

- **SECURITY (stored XSS)**: module-record attachments were served **inline** with the client-supplied
  `Content-Type`, so a `text/html` or `image/svg+xml` upload with `<script>` executed JS on the API
  origin against a lured member's session. Inline serving is now restricted to a **raster-image
  allowlist** (png/jpeg/gif/webp/bmp); everything else is forced to `Content-Disposition: attachment`
  + `application/octet-stream`, with `X-Content-Type-Options: nosniff` and
  `Content-Security-Policy: sandbox; default-src 'none'` on the response. Filenames run through the
  existing whitelist. Regression-tested (HTML + SVG both forced to attachment; images still inline).
- **🧭 R15 ring + re-prioritized execution queue** added to the roadmap from a full research pass —
  commercial + open-source landscape sweeps, a very-thorough codebase gap review, and security +
  performance audits. Headline finding: the **backend is far ahead of the frontend** (~72 shipped
  capabilities have no UI), so the new order leads with security/perf hygiene, then UI-surfacing
  waves, then a real workflow state-machine layer, then the twice-validated interop gaps
  (P6/MSP export round-trip, 4D simulation, model query DSL, Solibri-style rule library, model-CI,
  Bluebeam-parity markup), then the R14/R15 feature tiers. All deterministic + offline; licenses
  mapped; non-deterministic AI/photogrammetry features explicitly out of scope.
- The performance audit's ranked fixes (GEOM-CACHE, ASYNC-BLOCK, QTO-CACHE, CLASH-JOBS, PANEL-LAZY,
  DASH-UNION, PAYLOAD-CAPS, TEST-FASTPATH) are queued as the NOW block for execution.

## v0.3.492 — R14 research ring planned · doc_text ReDoS round 2

- **🔬 R14 ring added to the roadmap** — a field-research pass (13 infographics + 10 open-source
  tools/products studied) synthesized into 18 planned upgrades, ranked in three tiers:
  **Tier 1** — a full commissioning module (model-derived asset registry, phase-typed checklists,
  system×phase matrix, MEP design values as expected FPT values) · per-typology reinforcement rules
  + bar bending schedules with calc-run provenance · procurement close-the-loop (3-way match +
  price-observation ledger into the cost DB). **Tier 2** — bid-scope coverage gaps with cited scope
  lines · a compliance evidence ledger ("golden thread") · an MEP connector-topology graph with
  parallel-run generation · range estimates + firm rate sheets. **Tier 3** — clash-report triage
  import, lean BIM→GIS GeoJSON export, mnemonic shortcuts, view templates, a warnings panel,
  drawing-status lifecycle, CBS rollups, a live BIM Execution Plan generator, BIM-org roles, and
  charter/lessons-learned modules. All deterministic + offline; techniques only, no code lifted.
- **doc_text ReDoS, round 2**: CodeQL re-flagged the section matcher — the leading `\s*` was
  ambiguous against the optional `SECTION\s+` prefix (quadratic on space-runs). The line is now
  stripped before matching and every whitespace quantifier is bounded. Behaviour unchanged.

## v0.3.491 — UX-1 full ribbon merge: physical phase clusters (P2 · designer workspace)

- The Tools rail's sections are now **physically regrouped by lifecycle phase** — the DOM reorders
  into **Build → Analyze & Coordinate → Document → Data** clusters with a header over each, so
  "Advanced authoring" sits beside "Draw elements" instead of at the bottom of an accretion list.
  Every section declares its phase once at creation (`data-phase`); the ribbon filters on that,
  never by parsing titles at runtime.
- The ribbon consolidates to the **four real phases** (+ All): the old separate Analyze / Coordinate
  tabs both showed the same single section. A stale saved tab migrates to All. Persona-secondary
  tools now sort to the end of their phase cluster with a "more" badge (replacing the positional
  "More tools" separator the reorder would have orphaned).
- Live-verified: cluster order + headers, Build-tab filtering to exactly its three groups, header
  hiding on filtered tabs, persistence, and the stale-tab migration.

## v0.3.490 — B5 fastener/connection assemblies (P2 · Wave 11)

- **`add_connection_assembly` recipe**: a connection plate + bolt array authored at the joint
  between two members, grouped into an `IfcElementAssembly`, **and** — the semantic B6's base
  plates/shear tabs lacked — an **`IfcRelConnectsWithRealizingElements`** recording that A connects
  to B *realized by* the plate and fasteners (`ConnectionType` BOLTED/WELDED). That's the construct
  fabrication and detailing tools round-trip. Welded connections carry the weldment plate alone.
- **`connection_summary`** — the fabrication-level connection browser: every realized connection
  with its members, type, and realizing parts.
- Test-proven (A↔B realized by 5 parts; bolted + welded both listed; same-member and unknown kinds
  reject) and registered (83 recipes, matrix guard green). Completes B5.

## v0.3.489 — security: bounded doc_text regexes (CodeQL ReDoS)

- The two section-number regexes in `doc_text.py` used an unbounded `\d+(\.\d+)+`, which backtracks
  polynomially on adversarial `9.9.9…` input (CodeQL `py/polynomial-redos` ×2, flagged on
  v0.3.486's ingestion/search paths). Quantifiers are now **bounded** (`\d{1,4}(\.\d{1,4}){1,6}` —
  real section numbers are short) and the search query is capped at 500 chars as defense in depth.
  Behaviour unchanged (both consumer suites green); the CodeQL count returns to 0.

## v0.3.488 — E3 sketch-to-BIM push/pull (P2 · Master-builder UX)

- **`extrude_profile` recipe** — sketch-to-BIM: a closed 2D profile (XY metres) extruded to height
  as a real IFC element (generic proxy mass by default; walls/slabs/coverings/members when the
  sketch IS one), placed on the storey with an optional base lift. Tessellation-verified: an
  L-shaped sketch becomes exactly a 6 × 5 × 4 m solid.
- **`set_extrusion_depth` recipe** — the **pull**: change any simple extrusion's depth **in place**
  (a wall's height, a slab's thickness, a sketch mass's rise) by editing its
  `IfcExtrudedAreaSolid.Depth`. GUID-stable — the element, psets, and every reference survive; only
  the geometry deepens. Non-extruded targets (meshes/booleans) reject cleanly.
- Both registered (82 recipes, matrix guard green) and guarded (short profiles, bad classes/depths,
  stale GUIDs). Completes E3.

## v0.3.487 — JOB-QUEUE geometry exports · REL-8 complete (P2 · reliability)

- **JOB-QUEUE — `model_export` artifact job**: the heavy **.glb/.gltf geometry exports** now run as
  background jobs — tessellation off the request thread, the file parked in object storage,
  `GET /jobs/{id}/artifact` streams it (valid glTF magic verified). The inline
  `/model/export.glb|.gltf` routes stay for small models; this is the no-timeout path for big ones.
  A bad format errors on the job row (the worker survives).
- **REL-8 — COMPLETE**: audited all 359 first-party modules — every one already opens with a header
  docstring — and made it durable: `test_import_cycles` now **enforces** the header-docstring rule
  alongside the existing no-cycle guard, so a future module can't ship undocumented.

## v0.3.486 — W9-4 document-text ingestion → cited NL answers (P2 · knowledge graph)

- **`doc_text.py` + 4 routes under `/projects/{pid}/doctext`**: ingest a specification / code
  commentary / report (**JSON text or a raw PDF body**, extracted via pypdf) — chunks split at
  spec-section headers ("SECTION 09 21 16") and numbered headings with **page tracking**
  (headerless documents fall back to paragraph chunks). `search` is deterministic token-overlap
  retrieval with section-number boosting; `ask` returns an **extractive answer — the document's own
  words** — cited by document · section · page, and says so honestly when nothing matches. No LLM
  involved or silently invoked: quoting the answer on an RFI is quoting the spec.
- **`/rfi/qa` now falls through to the documents**: a question no model intent claims searches the
  ingested text before the overview — `intent: "document"` with `kind: "document"` citations.
  Completes the W9-4 harder half (spec/code document text → cited NL answers).
- Test-proven end to end, including the PDF path ("4000 psi" survives canvas → pypdf → chunk →
  answer) and the QA fallthrough.

## v0.3.485 — W9-5 4D equipment motion + swept crane-reach clash (P2 · site logistics)

- **Motion along paths**: a logistics resource with a `path` now **interpolates its position by
  schedule progress** (arc-length along the polyline) — a crawler crane walks its runway, a hoist
  relocates bay by bay — and `/logistics/state` carries the interpolated position so the 4D overlay
  draws equipment where it IS on that date, not where it started.
- **`GET /projects/{pid}/logistics/clash` — swept crane-reach clash**: crane pairs whose swing discs
  intersect **while both are on site** (closest approach sampled along any motion paths, with the
  worst date and the overlap in metres — "both tower cranes swing over the same bay in June");
  time-separated or distant pairs clear. Static resources (trailers/laydown/gates/parking) **under a
  crane's hook** surface as safety flags, not clashes. Plan-level screen, honestly disclaimed (not a
  jib kinematic simulation). Completes W9-5.
- Test-proven: schedule midpoint → 50 m along a 100 m runway; a 30 m pair with 20 m jibs clashes
  with 10 m overlap; a **walking** crane creates a clash only as it arrives; the trailer flags.

## v0.3.484 — W9-6b headcount program → zones + auto-furnish (P2 · generative fit-out)

- **W9-6b — `program_fit` recipe**: give it a **headcount program** (`{Engineering: 40, Sales: 20}`)
  and it allocates the model's spaces to departments (largest rooms to the largest remaining asks),
  stamps each allocated space as that department's **zone** (`LongName` + `Pset_Massing_Program`
  Department/SeatsAllocated), and **furnishes it to exactly the allocated seat count** using the
  W9-6 gridder (aisle-cleared desk/table templates). The report partitions allocated vs unallocated
  rooms and never silently under-seats — an over-capacity ask comes back `short_by: N`. Test-proven:
  an 11-seat program authors exactly 11 desks; a 500-seat ask on two small rooms reports the
  shortage. Completes the W9-6 generative fit-out track.

## v0.3.483 — E6 model-option branches · E8 model-aware guardrails (P2 · Master-builder UX)

- **E6 — recipe-log design-option branches** (`model_options.py` + 5 routes under
  `/projects/{pid}/model/options`): **snapshot the current model as a named branch** ("Scheme A —
  steel frame"), keep editing, snapshot again, and **switch between schemes** — each activate goes
  through the same edit-history push as any edit, so the switch itself is one undo step. `GET` lists
  branches (the byte-identical one flagged `current`); `.../diff` reports added/removed element
  GUIDs + per-class count deltas vs the working model; `DELETE` drops a branch (history untouched).
  Whole-model branches — per-element overlays remain the W9-3 layer system. Distinct from
  `design_options.py` (which compares metrics, not models).
- **E8 — model-aware guardrails** (`guards.model_precheck`, enforced in `apply_recipe`): references
  are now validated against the **open model** before any mutation — a typo'd storey (available
  names listed), a door hosted on a slab, a hallucinated host/element GUID, a `connect_mep` end
  with no ports, and a fully-stale GUID batch are all rejected; a partly-stale batch warns and
  proceeds. Batches (`apply_recipes`) deliberately skip this layer — a step may legally reference
  what a prior step in the same batch creates (wired flows use `/edit/graph`). Completes E8.
- Both test-proven end to end (branch → edit → diff `+1 IfcWall` → activate → undo returns to the
  other scheme; slab-hosted door blocked before write).

## v0.3.482 — CI fix: approvability test writes models to a temp dir

- The new D8 BCF test generated its model through `/generate/massing` with the default `IFC_DIR`,
  which resolves under `/app` — **read-only in the CI container** (the container-readonly-tmp
  pattern again). The test now points `IFC_DIR` at a temp dir, like every other generator test.
  No product code changed; the v0.3.480 API gate goes back green.

## v0.3.481 — REL-4 measure/section leaf · REL-5 bridge dataclasses (P2 · reliability)

- **REL-4 — `viewer/measureSection.ts`**: the measure/visibility toolbar group (↔ ▱ ✂ ⊙ ◐ ⌫ ⊞) and
  the section-box tool extracted from `app.ts` into a leaf (two positional installers because other
  groups interleave). Pure extraction — button order, behaviour and DOM unchanged, live-verified;
  `app.ts` 3,970 → 3,948 lines and keeps the tool instances (click handlers, settings, shortcuts).
- **REL-5 — editor-bridge hardening**: `bridge.py`'s `plan`/`execute` now return typed
  **`Plan`/`PlanStep`/`ExecutionResult` dataclasses** (the safety-gate step shapes are part of the
  contract, so they're spelled out), and `recipes.py`'s duplicated storey lookup is deduped into
  `_find_storey`. The offline safety-gate test updated and green (save-first, chunking, confirm
  gate, dry-run default). This closes the REL-5 remainder — the vite/bundle-budget FS item was
  audited earlier as already single-pass.

## v0.3.480 — D8 COMcheck/A117.1 approvability layer + BCF round-trip (P2 · Wave 11)

- **D8 — the approvability pre-flight grows the energy/accessibility layer** (3 new cited checks):
  - **Window-wall ratio** vs the IECC C402.4.1 prescriptive 30% cap — computed from the authored
    exterior walls (explicitly `IsExternal`-flagged; unflagged walls are never guessed at) and the
    windows' overall dims. Over the cap → `info` steering to the COMcheck trade-off/performance path.
  - **Envelope U-values present (COMcheck-ready)** — every envelope element (external walls, windows,
    roofs) must carry a `ThermalTransmittance`/U-value before a COMcheck submission is possible;
    missing ones fail with their GUIDs.
  - **Accessible entrance** (IBC 1105.1 / A117.1 404) — at least one door at the 32 in clear width.
- **D8 → BCF**: `POST /projects/{pid}/codecheck/approvability/bcf` promotes every failed (high) and
  info (normal) check to GUID-anchored, labeled BCF topics — the plan-review punchlist round-trips
  with clashes/RFIs. Idempotent (re-running replaces its own topics).
- Test-proven end to end: WWR 0% → pass, ~32% → info; stamping U-values flips the COMcheck check to
  pass; topics created/replaced idempotently. The model-health issuance gate now legitimately blocks
  on missing envelope U-values.

## v0.3.479 — F0b coarse view derivation · SpecLink breadcrumbs (P2 · Wave 11)

- **F0b — `derive_representations` recipe**: derives the coarse view-keyed representations from Body
  geometry — a dimension-true **`IfcBoundingBox`** in the Model/Box subcontext, a 2-point
  **Axis centreline** (mid-thickness, linear elements only) in Model/Axis, and a closed **FootPrint
  rectangle** in Plan/FootPrint — so massing display and schematic plans have a cheap per-view
  fallback on every element. Bounds-based by design (not a silhouette); idempotent per element+kind;
  sweeps the whole model or a GUID list. Completes the F0 spine's promised derivation half.
- **SpecLink — `set_spec_link` recipe + `GET /projects/{pid}/spec-links`**: stamp
  `Pset_Massing_SpecLink` (MasterFormat **SpecSection** + optional title/url) on elements as the
  quick model→spec breadcrumb (distinct from the formal `classify` carrier), and read the rollup —
  each linked section with its element tally + the unlinked count — for submittal/schedule grouping.
- Both registered in the authoring matrix (79 recipes, completeness guard green) and test-proven
  (bounding-box dims hand-checked against a 5 m × 0.2 m × 3 m wall).
- **B3/B4/C2 — onboarding fast-follows**: first signed-in boot offers a **role picker** (tailors
  workspaces immediately; skippable, never repeats, defers to any manual choice) · the coach-mark
  tour is confirmed at its **5-step cap** · publishing a model edit while signed out shows a one-shot
  dismissible **"sign in to save your work"** nudge (30 s auto-dismiss, never a wall). All three
  live-verified.

## v0.3.478 — W10-4 coincident-port auto-connect · webhook private-IP blocking (P2)

- **W10-4 — `auto_connect_mep` recipe**: one pass wires every unconnected MEP element pair whose
  connection points coincide (segment ends from placement + the sizing pset's length; fittings and
  terminals at their placement point) with `IfcRelConnectsPorts` — a run drawn end-to-end with a
  fitting at each junction snaps into a connected network without N manual `connect_mep` calls.
  Nearest pairs first; at a joint the **fitting claims the ports** (never a direct segment-to-segment
  weld through an elbow); strays stay untouched; re-running is a no-op (already-connected pairs and
  consumed port budgets are respected). Test-proven on an A–elbow–B–tee–C network.
- **REL-6 — webhook private-IP blocking**: set `AEC_WEBHOOK_ALLOW_PRIVATE=0` (env or Settings) and
  outbound webhooks refuse targets that resolve to private/loopback/link-local addresses (blocks
  cloud-metadata and intranet probing via a compromised settings key). Default stays permissive —
  on-prem LAN listeners are a legitimate operator choice; `file://` and friends remain always-refused.
- **A1/A2/C1 — provider-first sign-in modal**: the sign-in dialog now **leads with big Google +
  Microsoft buttons** (co-equal defaults; the first configured provider takes the lead slot when
  neither is set up), every other provider collapses behind **"More sign-in options"**, and the
  password form follows the divider. Live-verified with a stubbed 3-provider config.
- Backend suite green; web gates green.

## v0.3.477 — VIZ-2 presentation FX · CODE-4 local amendments · MEP engineering depth (P2)

- **VIZ-2 — SSAO + bloom presentation FX** in render mode: the viewer's render toggle now routes the
  frame through a three.js **EffectComposer** (SSAO contact shadows → subtle bloom → tone-mapped
  output on an MSAA half-float target), on top of the existing sun/soft-shadow/IBL/PBR upgrade.
  Wraps the engine renderer's per-frame render — no engine changes, overlay/ortho renders stay raw,
  toggling off restores the raw path and disposes the chain. Offline + license-free (bundled three
  examples). Live-verified: one wrapped call runs the full pass chain; off → single raw render.
- **CODE-4 — local-amendment overlay**: `PUT/GET /projects/{pid}/code/amendments` records the AHJ's
  **local amendments** on top of the statewide adoption — a per-family **edition override** (must be
  a published edition; beats the jurisdiction seed everywhere `_project_ibc_edition` is consulted,
  i.e. every model code check) plus recorded **section amendments** (family + section + note) that
  ride on the code context so citations can flag "locally amended — read the ordinance". Hard 422
  validation; an empty list clears the overlay; audited. `codes.apply_amendments` is the pure core.
- **MEP engineering depth** (`mep_sizing.py` + three routes):
  - **`GET /projects/{pid}/mep/pressure-loss`** — friction loss per authored duct/pipe run (empirical
    round-galvanized duct rate + **Hazen-Williams** pipe rate from the sizing pset's size + flow +
    length), checked against equal-friction budgets (0.10 in.wg / 4 ft per 100 ft), with per-system
    series-sum totals and the **index run** a balancing engineer hunts first.
  - **`GET /projects/{pid}/mep/tray-fill`** — **per-conductor NEC 392.22** cable-tray fill computed
    from the actual authored `IfcCableSegment` diameters on each tray's system vs the Table
    392.22(A) allowable (7 in² per 6 in of width) — no supplied ratio needed.
  - **`GET /projects/{pid}/mep/thermal-loads`** — space-by-space **cooling-load screen** (W/sf
    method): people/lighting/equipment densities by space type + a flat envelope allowance per
    IfcSpace, summed to tons vs the block `GFA ÷ 350` estimate, showing *where* the load lives.
  - All hand-checked against the physics in `test_mep_sizing` and honestly disclaimed (screens, not
    PE designs).
- **B2 — sign-in → tour**: signing in from the welcome panel now resumes straight into the coach-mark
  tour after the auth reload (a consumed one-shot flag), instead of dropping the new user on the raw
  workspace. Live-verified: reload with the flag → tour step 1 opens, welcome suppressed, flag cleared.
- Backend suite green (268/268); web gates green (typecheck · lint · 121 vitest · build).

## v0.3.476 — ENV-1 wind-comfort screen · VIZ-1 export parity confirmed (P2)

- **ENV-1 — `POST /projects/{pid}/env/wind`**: a pedestrian **wind-comfort screen** at massing stage —
  corner acceleration, downwash (with the podium-interception rule), and passage channelling, each
  graded on the **Lawson comfort categories** (A sitting → E uncomfortable → unsafe > 15 m/s) with
  the standard mitigations (podium/canopy, corner chamfers, porous screens). Dims explicit or derived
  from the source model's bounds. Deterministic rules of thumb, honestly labelled **NOT CFD** — a
  screen to steer massing, verified with a wind consultant for tall/exposed sites. `test_env_wind`
  covers the physics behaviors (podium cuts the downwash factor; a 10 m gap channels, 40 m doesn't;
  >15 m/s grades unsafe).
- **VIZ-1 — .glb export parity confirmed** against the live dev model: a valid glTF 2.0 binary with
  every geometry class present (Slab/Space/Wall nodes, all named). Noted design trade-off: the
  exporter merges **per IFC class** (compact presentation export), so per-element identity lives in
  the IFC/Fragments path, not the .glb — as documented on the endpoint.
- Backend suite green; web gates green.

## v0.3.475 — COST-AGENT calibration · BOARDS option decks (P2 · AI & finance frontier)

- **COST-AGENT — `GET /projects/{pid}/cost/calibration`**: the project learns from its own history —
  the model's takeoff estimate compared against **awarded subcontract values** and **posted direct
  costs**, deriving a calibration factor (observed ÷ estimate, clamped 0.5–2.0, actuals preferred)
  that `estimate_from_takeoff(benchmark_factor=…)` can apply to the next iteration. Reported, never
  silently applied. Test-proven: awarding a subcontract at 1.2× the estimate yields factor 1.2.
  (The re-estimate-on-geometry-change half shipped as PROFORMA-LIVE in v0.3.473.)
- **BOARDS — `POST /projects/{pid}/design/options/board.pdf`**: a GEN-SCORE run becomes a styled
  one-page **design-option deck** — title + recommendation, the cost/carbon/yield/compliance
  comparison table, and composite score bars — the client-facing artifact of an options study
  (`option_score.board_pdf`, deterministic reportlab).
- `test_productivity` + `test_option_score` extended; backend suite green; web gates green.

## v0.3.474 — NL-QA "audit + suggest fixes" · READY-AGENT make-ready register (P2 · AI & agents)

- **`POST /projects/{pid}/ai/audit`** — the ranked decision-readiness gaps, now with an **executable
  fix step** attached wherever a deterministic recipe can close the gap (elements missing their
  keynote/detail → `apply_detailing_rules`). The returned `fix_steps` drop straight into
  `POST /edit/batch`, so "audit → apply every automatic fix → one undoable version" is a two-call
  flow — proven in-test end-to-end. Gaps without a safe automatic fix keep their prose guidance;
  the audit itself never writes.
- **READY-AGENT — `GET /projects/{pid}/schedule/make-ready?days=N`** — every activity starting in the
  window, its preconditions **checked with cited evidence** (incomplete predecessors by ref + their
  real % complete · open submittals by ref/state) and a ready/blocked verdict. The Last Planner
  "can next week's work actually start?" answered proactively. Test-proven: a start blocked by a 20%-
  complete predecessor cites exactly that.
- Backend suite green; web gates green.

## v0.3.473 — PROFORMA-LIVE: the finance numbers follow the model as you author (P2 · finance frontier)

- **`GET /projects/{pid}/proforma/live`** — the current model version's **takeoff-priced construction
  cost** (the benchmark-guarded recommended total, content-cached per published version so it's cheap
  to poll), slab-derived **GFA**, **cost/m²**, and the **delta vs the developer budget's hard cost**.
- **The viewer surfaces it automatically:** after every model (re)load the status line reads the live
  figures — live-verified on the dev project: *“model cost $166,740 · GFA 958.5 m²”*. Re-publish an
  edit and the number moves with the geometry.
- **E7 — live paper while modeling:** the viewer now broadcasts `aec:model-published` after every
  successful model (re)load, and an open Drawings-workspace sheet — floor plan or door/window/room
  schedule — re-renders itself against the new geometry. Author a wall, watch the plan and the
  schedules update.
- **Fixed the CI flake that reddened v0.3.471/472:** the doc-graph QA's GUID regex was ``-anchored,
  but IFC GUIDs may start/end with `$` (not a word character) — such GUIDs never matched and "what
  governs <guid>?" fell back to the overview answer whenever the random test GUID ended in `$` (it did,
  twice in a row, on CI). Now matched with explicit alphabet lookarounds + a regression test over
  `$`-edged GUIDs.
- `test_productivity` extended (cost > 0, GFA > 0, cost/m², version stamp). Backend suite green;
  web typecheck / eslint / vitest (121) / build green.

## v0.3.472 — AI read tools · sign-in-first welcome (B1) · four P2 items confirmed shipped

- **The model's own numbers, readable by any agent.** The MCP catalog grows four read tools —
  `model_quantities` (discipline QTO roll-up), `computed_schedules` (door/window/room, the A-601
  data), `clash_results` (geometric intersections with GUIDs), `code_violations` (IBC 1004/1005
  occupancy/egress findings) — 18 tools total; model-less projects get a clear error, not a trace.
- **B1 — the welcome now leads with sign-in, never walls.** A 🔐 sign-in row (Google · Microsoft ·
  Procore SSO or username, via the topbar's own modal through the new `openSignIn()` export) heads
  the first-run panel; every quick-start path below it still works signed-out. Live-verified: the
  row renders first, the button opens the login modal, the never-walls copy is present.
- **Confirmed shipped (audited with proof, now marked):** S5 clarifying questions (both planner
  paths return `needs_clarification`; two UI surfaces show it) · E2 type-a-dimension/VCB (the
  dynamic-input layer: type "6", "<30", "6<30" mid-draw — v0.3.453/461/467) · W10-6 keynote legend
  (sheets render the KEYNOTES legend from Track-D codes, test-asserted) · REL-5's build-script
  batch-FS review (bundle-budget is already single-pass; no change needed).
- Backend suite 267/267; web typecheck / eslint / vitest (121) / build green.

## v0.3.471 — per-project jurisdiction + auto-resolved code edition (CODE-1b/3) · one-undo NL batches (S4)

- **CODE-1b — the project knows its jurisdiction.** `Project.jurisdiction` (USPS state code) is now a
  first-class field (PATCH `/projects/{pid}`, returned on GET; the column auto-migrates). **CODE-3 —
  the edition resolves itself:** the egress/occupancy checker cites the jurisdiction's **adopted IBC
  edition** automatically (unset → national baseline, always with the verify-with-AHJ note), and the
  `apply_detailing_rules` recipe at `POST /edit` rewords its citations to the adopted edition when the
  caller didn't pass one.
- **S4 — multi-step commands undo as one step.** New `POST /projects/{pid}/edit/batch`
  (`steps: [{recipe, params}, …]`) opens the model once, applies every step in memory, writes ONE
  version and pushes ONE edit-history entry — so a multi-step NL command reverts with a single undo.
  All-or-nothing: every step is guard-prechecked before anything runs; a bad step aborts the batch
  with nothing written. Honors the COLLAB-1 optimistic lock.
- `test_codes` extended (PATCH round-trip; FL → IBC 2021; no jurisdiction → baseline) and
  `test_edit_undo` extended (3-step batch → exactly one undo entry; one undo reverts all; bad middle
  step aborts atomically; empty batch 400). Backend suite green.

## v0.3.470 — RISK-BOARD: one register for every computed risk signal (P2 · AI & agents)

- **`GET /projects/{pid}/risk-board`** unifies the platform's computed risks into one ranked,
  deep-linked register: **Monte-Carlo schedule risk** (P80 buffer + the top delay driver by
  criticality) · **predictive schedule alerts** (overdue / late starts / blocked predecessors /
  procurement) · **EVM** (CPI/SPI below par with the recommended EAC) · **pre-flight issuance
  blockers** · **overdue open coordination issues** (aging items become claims). Every row is
  re-derived from its engine on each call — aggregation only, no new stored state; a broken lane
  drops out and reports itself in `lanes`, never breaking the board.
- The Schedule panel opens with a **🚨 Risk board** card (band + severity counts + the top 10 items).
- Live-verified on the dev project: all 5 lanes `ok`, band `critical` — 4 pre-flight blockers + the
  9.1-day P80 buffer computed from the EST-1 schedule. `test_risk_board` covers the empty board,
  signal seeding (overdue activity → alert; overdue high topic → coordination + preflight), ranking,
  deep links, and band escalation. Backend suite green; web gates green.

## v0.3.469 — DISC-poché: 2D plans read by trade (P2 · estimating/engineering)

- **`by_discipline=true` on both plan renderers.** The **cut-plane plan** (`/drawings/plan.svg`)
  strokes every element's linework with its canonical discipline color and adds a DISCIPLINES legend
  (`drawings.cut_baked_classed` keeps each polyline's IFC class through the section). The
  **footprint/sheet renderer** (`drawing.plan_svg`, feeding sheet SVG/PDF) tints its poché fills the
  same way with its own legend. Off by default — the classic monochrome poché is untouched.
- The data layer gains its renderer-side mini-spine: `disciplines.discipline_of_class` (walls/roofs/
  coverings/doors → A · slabs/columns/beams/footings → S · duct → M · pipe → P · cable/electrical → E,
  General-grey fallback), mirroring the canonical `aec_api.classification` map without a cross-layer
  import.
- Live-verified on the dev project: the plan cut rendered the DISCIPLINES legend with
  architectural-grey (#4B5563) wall strokes. `test_sections` + `test_drawing` extended (exact hex
  asserts + spine mapping + well-formedness); backend suite green.

## v0.3.468 — REL-4 slice 5: the Report Center becomes its own module

- `reportCenter.ts` (new, 469 lines) now owns the whole Report Center modal — every exportable
  report (PDF / in-app markup / Excel) and the interactive project tools & analytics (drawing-set
  register + issuance + 🚦 pre-flight gate, WH-347 payroll, PDF tools, project health, assistant,
  field-verification coverage). Extracted verbatim from `main.ts`, which drops **1,645 → 1,187
  lines** and keeps a one-line `openReportCenter(api, projectId)` call.
- Live-verified after the extraction: the modal opened with 54 report-download rows, the Drawing-set
  register tool loaded with the 🚦 Pre-flight button, and all three issuance records rendered.
- Typecheck / eslint / vitest (121) / build green.

## v0.3.467 — REL-4 slice 4: the KEYS + dynamic-input layer becomes its own viewer leaf

- `viewer/keysDyn.ts` (new, 126 lines) owns the Revit-style **2-letter draw-tool shortcuts** (WA/SL/
  CL/… · Esc disarms · ? help) with their HUD, the **typed distance/angle constraint** buffer
  ("6", "<30", "6<30") with its ⌨ HUD, and the **snap-glyph** feedback. `app.ts` keeps one
  `installKeysDyn(deps)` call; the handle exposes `dynBuf()/setDynBuf/flashSnapGlyph` for the draft
  flow. `app.ts` **3,957 lines** (4,361 at the start of this arc — five leaves out).
- Live-verified after the extraction: typing `W` showed the shortcut HUD, `WA` armed the Wall tool
  ("Wall armed — click in the model to place"), the dyn HUD is mounted, `?` opened the shortcuts
  help, and Esc disarmed. Typecheck / eslint / vitest (121) / build green.

## v0.3.466 — SHEET-LINK: the compiled drawing set navigates like a hyperlinked document (P1 #9)

- **The cover's drawing index is now clickable.** Every index row on the compiled-set cover carries a
  real PDF **GoTo link annotation** to its sheet page (`_cover_pdf` reports each row's hit-box;
  `compiled_set_pdf` binds them post-merge with pypdf) — open the set, click A-102, land on A-102.
- **Detail callout bubbles cross-link too.** The NCS divided-circle callouts report their hit-box +
  target sheet ref from the PDF renderer (`drawing.sheet_pdf(link_out=…)`); whenever the referenced
  sheet is part of the compiled set, the bubble becomes a clickable link to it. In the **SVG** path
  each bubble is now an `<a class="sheet-link" data-sheet="…">` anchor, so the Drawings workspace (or
  any SVG viewer) can jump on click.
- Links are an enhancement layer — if the binder fails for any reason the un-linked set still ships
  (fail-open). `test_drawing` (SVG anchor + link_out boxes) and `test_drawing_set` (≥4 cover links,
  callout-to-A-102 binding on the plan page) cover it; backend suite green.

## v0.3.465 — 3D-HERO: capture the live 3D view as the project package's hero page (P1 #8)

- **📸 one click in the viewer** renders a fresh frame, captures the WebGL canvas as a PNG, and pins
  it as the project's **hero image** (`PUT /projects/{pid}/hero` — magic-byte checked, 10 MB cap;
  GET streams it back, DELETE clears). The client project-package PDF now opens with it: a
  full-bleed, aspect-preserved **3D hero page** right after the cover (`package.py::_hero_page`).
  Headless server rendering stays out of scope — the capture path is the deliberate design.
- Live-verified end-to-end: the 📸 button captured a real **1.27 MB PNG** of the live model view,
  the server stored + streamed it back, and the package PDF grew to 10 pages with a 779 KB embedded
  image on page 2.
- `test_project_package` extended (404 → magic-byte 400 → PNG round-trip → package gains exactly one
  page → DELETE); backend suite green; web typecheck / eslint / vitest (121) / build green.

## v0.3.464 — JOB-QUEUE: the compiled drawing-set PDF runs on the durable queue with a downloadable artifact (P1 #7 begins)

- **Artifact jobs.** The durable queue gains its first binary-artifact kind: `compiled_set_pdf`
  renders the whole drawing set (cover + plan per storey + schedules) **off the request thread**,
  parks the PDF in object storage, and the poll result carries `artifact_key`. A new
  `GET /projects/{pid}/jobs/{id}/artifact` streams the bytes back (409 while queued/running,
  404 when a job has no artifact) — the reusable pattern the remaining heavy paths (PAdES sealing ·
  large exports · generative runs) migrate onto next.
- Enqueue with the existing `POST /projects/{pid}/jobs` (`{kind: "compiled_set_pdf", params:
  {scale?, max_sheets?, schedules?}}` — the same knobs as the inline endpoint, which stays for
  small sets). Live-verified: enqueue → `running` → `done` in one poll cycle, and the artifact
  endpoint streamed a real multi-page `%PDF` for the dev project.
- `test_jobs` extended (artifact round-trip + no-artifact 404); backend suite green.

## v0.3.463 — REL-4 slice 3: the collab/presence block becomes its own viewer leaf

- `viewer/collabPresence.ts` (new, ~150 lines) now owns the whole COLLAB-1 surface: the 👥 presence /
  ⤴ share-view / 📱 QR rail buttons, the 20 s heartbeat that shares this client's live viewpoint, the
  per-user 3D peer cursors, and the publish-reload banner fed by the model SSE stream. `app.ts` keeps a
  single `installCollabPresence(deps)` call; the handle exposes `captureViewpoint`/`jumpToViewpoint`
  (env tools · BCF viewpoints · share flows) and `resync()` for `loadProjectModel` (your own publish
  never nags you to reload). `app.ts` 4,107 → ~4,010 lines.
- Live-verified after the extraction: the reloaded client's heartbeat appeared in the server roster
  (through the leaf), a seeded peer rendered its view-cone cursor at exactly (20, 10, 15) with cone +
  dot + name sprite, the presence button read 👥 1, and the ⤴ share flow round-tripped.
- Typecheck / eslint / vitest (121) / build green.

## v0.3.462 — EST-1: QTO → crew-day durations → CPM (P1 #5)

- **The labour estimate now prices the real takeoff.** `productivity.from_takeoff` routes each
  measured QTO row (Qto psets + geometry fallback) to its productivity activity — walls → masonry
  face area, slabs → casting volume + finish area, columns/beams/footings → concrete volume (steel
  tonnage → erection), coverings → tile/ceiling area, pipe/duct/tray/cable runs → install lengths.
  `GET /estimate/labor` uses it by default (`qto=false` falls back to the rough dimension parse).
- **One click writes the durations into the schedule.** `POST /projects/{pid}/schedule/from-estimate`
  upserts one `schedule_activity` per trade group (WBS `EST`, crew-day durations, FS-chained) — CPM,
  Gantt, lookahead and Monte-Carlo risk immediately run on model-derived durations. Re-running
  refreshes durations without duplicating; manual activities are untouched. The Schedule panel grew a
  **⚙ Durations from model (QTO)** button.
- Live-verified on the dev project: 2 trade activities (Concrete 112 d → Masonry 6 d, FS chain,
  CPM 118 d); re-running with `crews: 2` refreshed the same records to 56 d + 3 d (CPM 59 d);
  `/schedule/cpm` shows the ACT-001 → ACT-002 critical path and the Gantt SVG renders it.
- `test_productivity` extended (from_takeoff mapping math + the endpoint's upsert/409/CPM chain);
  backend suite green; web typecheck / eslint / vitest (121) / build green.

## v0.3.461 — UX-2: snap-as-you-place annotation + live guide lines (P1 #4)

- **Every placed annotation now lands exactly on geometry.** A plain model click snaps the picked
  point to the hit element's nearest **vertex / bounding-edge midpoint / corner / center** (the
  classic osnap set, 0.4 m tolerance) with the ◻ snap glyph — so notes, 2-point dimensions, revision
  clouds, tags, MEP fittings and every other `lastPoint` consumer anchors on the element, not on the
  raw raycast point. `snapToGeometry` grew the midpoint/center candidates.
- **Live guide line for two-click flows.** Arming a dimension or revision cloud drops an **anchor dot**
  at the first (snapped) point and stretches a **dashed rubber line to the cursor** until the second
  click — you see exactly what will be measured before committing. Cleans up on completion.
- Live-verified: an exact-corner click flashed ◻ snap (the point snapped to the wall corner); arming
  Dimension created the `annot-guide` group (dot + dashed line) and the rubber end tracked the
  pointer across the ground plane. Typecheck / eslint / vitest (121) / build green.

## v0.3.460 — SITE-1: open-geodata site context — drop the model onto its real surroundings (P1 #3)

- **One click adds the neighborhood.** Open ▾ → *Add site context (OSM buildings)…* fetches the
  OpenStreetMap **building footprints (height-extruded), roads, and land-use parcels** around the
  site and renders them as a separate reference layer under the model. Coordinates come from the
  model's georeference (IfcSite lat/long, DMS→decimal) or typed lat/lon; radius 50–2000 m.
- **Fetch-once, offline-after.** The server (`site_context.py` + `GET /projects/{pid}/site-context`)
  queries Overpass once and caches the normalized GeoJSON in object storage — afterwards the layer
  loads fully offline (live: first fetch 4.7 s, cache hit 59 ms). `refresh=true` re-queries; DELETE
  clears. OSM data is **ODbL** — the attribution ships in every payload and shows with the layer.
- **Real heights.** Buildings extrude to their tagged `height` (else `building:levels` × 3 m, else
  6 m). Live-verified in Midtown Manhattan: 210 buildings / 249 roads; the Empire State Building's
  roof lands at exactly **443.2 m** in the scene; projection is centred on the fetch anchor so the
  context sits in the model's frame.
- Engine follows the injectable-transport client pattern — the test suite runs fully offline against
  a MockTransport (`test_site_context.py`: DMS georef, Overpass→GeoJSON normalization, cache/409/
  DELETE paths). Viewer code extends `gis.ts` (`buildSiteContext`: earcut roof caps + wall quads).
- Typecheck / eslint / vitest (121) / build green; backend suite green.

## v0.3.459 — PREFLIGHT: the issuance gate now covers keynotes · drawing-set QA · pinned IDS, deep-links every check, and gates the Issue action (P1 #2)

- **The pre-flight gate is now the full pre-issuance audit.** Three new lenses join model health /
  classification / open-issues: **keynote/spec completeness** (the detail-rule QA — components missing
  a required keynote), **drawing-set QA** (set integrity · issuance hygiene · model cross-checks, when
  sheets exist), and the **pinned-IDS validation** (the project's contractual spec, when one is pinned).
  Every check now carries a **deep link** to the API tool that drills into it (`preflight.py`).
- **Wired into the issuance flow.** `POST /drawing-set/issue` runs the gate automatically and **stamps
  the verdict on the issuance record** (a permanent "what did the gate say at the moment of release");
  `enforce: true` makes a HOLD block the issue with a 409 listing the blocking checks. The Drawing-set
  register UI grew a **🚦 Pre-flight** button (verdict + iconized checklist + ↗ deep links), and
  **📤 Issue set** now enforces by default — on a HOLD it renders the evidence and arms a one-shot
  **⛔ Issue anyway** override.
- **Root-cause bug fix found by live-driving the UI:** the Report-Center `table()` helper used
  `innerHTML +=`, which reparses the whole tool body and **silently detaches every button handler
  wired before it** — the issuance tools (Generate / Issue / Pre-flight) were dead whenever the
  register table rendered after them. It now appends a real element.
- Live-verified end-to-end on the dev stack: gate returned a genuine HOLD with all 8 lenses (the
  pinned IDS correctly failing 2/5 specs against the real model); enforced issue → 409; UI checklist +
  deep links rendered; the override issued and the record carries the 4-blocker HOLD stamp; a corrupt
  pinned IDS degrades gracefully (lens absent, no 500).
- Backend suite green (test_issuance + test_model_health extended); web typecheck/lint/vitest(121)/build green.

## v0.3.458 — COLLAB-CURSORS: multiplayer presence cursors in the viewer (P1 #1)

- **See where everyone is looking, live.** Every peer whose presence heartbeat carries a camera
  viewpoint renders as a colored **view-cone + name tag** at their camera position, aimed at their
  look-target (`viewer/peerCursors.ts` — a REL-4-style leaf from day one). Colors are stable per user
  (name-hash → hue); cursors upsert/track/remove as the roster changes; you are never shown your own.
- **The 20 s presence beat now shares your live camera viewpoint** (previously only the explicit
  ⤴ share button did) — that's what makes the cursors continuous. No protocol change: the heartbeat
  always accepted a viewpoint; the roster + the collab SSE `editors` both feed the same reconciler.
- **Live-verified end-to-end**: a seeded peer's cursor appeared at exactly its camera position
  (15, 9, 12) with cone + dot + name sprite; our own beat's viewpoint showed up in the server roster;
  and when the peer departed, the next beat removed the cursor. This completes COLLAB-1
  (awareness + edit-lock + live-reload shipped earlier; cursors were the remainder).
- Typecheck + eslint + vitest (121) + build green.

## v0.3.457 — roadmap reorganized: completed work archived, open items re-prioritized

- **`docs/roadmap.md` 679 → ~130 lines, open items only.** The full pre-reprioritization snapshot —
  every ✅/🟡-shipped entry across the UI/UX pass, Waves 9–11, the frontier bets, CAD-UX lessons,
  REL/enterprise tracks — is preserved verbatim in `roadmap-completed.md` as a dated archive section.
- The live roadmap is now three rings: **P1** (9 buildable, live-verifiable items, led by multiplayer
  cursors · the PREFLIGHT issuance gate · SITE-1 site context · snap-as-you-place annotation ·
  QTO→CPM durations · continued REL-4 slices · JOB-QUEUE migration · the package 3D hero · sheet
  hyperlinks), **P2** (the designer-workspace, CD-depth, authoring, AI-agent, finance, reliability and
  onboarding rings), and **P3 gated** (each entry names its concrete unblocking event), plus documented
  non-goals + license guardrails.

## v0.3.456 — REL-4 slice 2: the file-IO leaf out of the viewer god-file

- **`viewer/app.ts` 4,215 → 4,044 lines**: every file open / import / export path — IFC (small
  in-browser parse, large via the server pipeline with replace-confirm + publish + reload), Fragments,
  the paid convert bridge, reference overlays (mesh/point-cloud/basemap), sample models, and the
  Tauri-native open/save dialogs — extracted into `viewer/fileIO.ts` (218 lines) behind an explicit
  17-field deps seam. Pure extraction; `refCount` ownership moves into the leaf.
- Verified: typecheck + eslint + vitest (121) + build green, and live in the running viewer the
  `openFile("ifc", …)` dispatch reaches the legacy small-file branch with the correct loading overlay
  (the in-pane WASM import worker itself is a documented headless-pane limitation, identical
  before/after; the Fragments load path is proven by every boot). Cumulative REL-4: app.ts
  **4,361 → 4,044** across two live-verified slices.

## v0.3.455 — REL-4 begins: the first live-verified leaf out of the viewer god-file

- **`viewer/app.ts` 4,361 → 4,215 lines**: the environment & navigation tool set — render mode
  (sun + soft shadows), the **sun/shadow study** panel, the **first-person walkthrough**, and the
  **storey levels overlay** — extracted into `viewer/envTools.ts` (180 lines) behind an explicit deps
  seam (viewer, loader, toolbar factory, viewpoint capture, settings). Pure extraction; the sun study
  now flips the render button via a direct reference instead of scanning the toolbar by title.
- **Why this is the first app.ts split that could ship safely**: the newly-unblocked live loop proved
  behaviour unchanged in the running viewer — render mode toggles, the sun panel opens and computes
  (altitude 71° · azimuth 179° S for July noon at 40.7°N), walk mode engages, and the levels overlay
  adds exactly one grid per storey (4). Typecheck + eslint + vitest (121) + build green.
- REL-4 continues leaf-by-leaf with the same prove-it-live discipline.

## v0.3.454 — SHEET-VIEWPORTS complete: the interactive paper-space editor (lesson #8 done)

- **Drawings ▸ ⊞ Paper space** — the client half of the v0.3.449 layout engine, live-verified:
  - preset picker (`key` / `quad` / `plan-pair`, fetched from the server) + page (A1/A3/A4) + sheet
    number/title;
  - per-viewport controls: view kind (plan storey elevation · section axis@offset · elevation
    direction), fixed **1:N scale** (blank = fit), **class freeze**, add/remove;
  - a live server-composed **SVG preview** with **drag-to-move viewport overlays** — drag a dashed
    rectangle on the sheet; its fraction rect updates and the sheet recomposes (500 ms debounce);
  - **⬇ PDF** downloads the submittable sheet through the real endpoint.
- Composition stays entirely server-side and deterministic — the editor only edits the viewport spec.
- **Live-verified in the running app**: preset composed in ~0.5 s with 3 draggable overlays; a
  pointer-drag moved a viewport from rect (0, 0) to (0.12, 0.12) — exactly the drag delta — the sheet
  recomposed, and the PDF downloaded. Typecheck + eslint + vitest (121) + build green.
- With this, OpenAEC-study lesson #8 is **complete** (server slice v0.3.449 + this editor).

## v0.3.453 — SNAP-KIT phase 2: dynamic input + snap glyphs, live-verified to the IFC (lesson #2 complete)

- **Type the constraint mid-draw.** With a draw tool armed and a first point placed, typing `6`, `<30`
  or `6<30` builds a distance/angle constraint in a **HUD** ("⌨ 8<60 → 8 m @ 60° — click to place");
  the next click is constrained through the tested snap engine — the typed value **beats every
  automatic snap** (geometry, axis inference, polar, grid): explicit intent is never re-snapped away.
  Backspace edits, Esc clears with the tool. Pure parser (`dynInput.ts`), strict like the CAD polar
  tokens (`6<`, double-`<`, zero/negative distance → rejected), +3 vitest.
- **Snap-kind glyphs**: each placed point flashes what won — `◻ snap` (geometry vertex), `∠ axis`
  (inference), `◇ 45°` (polar), `⌨ 8<60` (typed) — the phase-2 osnap feedback.
- **Two interaction bugs found by driving the live viewer** (the newly-unblocked Gate-A loop):
  - a lingering **measure mode silently ate every draft click** — an armed draw tool now always wins
    over measure (measure keeps the click only when nothing is armed);
  - a stalled Fragments **raycast could wedge the click pipeline forever** — it now races a 1.5 s
    timeout and falls back to the ground plane, so drafting keeps working through any worker stall.
- **Live-verified end-to-end, to the IFC bytes**: armed the wall tool via KEYS (`WA`), clicked a point,
  typed `8<60`, clicked again — the placed point measured **exactly 8.00 m @ 60.0°** from the first;
  the wall authored + published, and the source IFC confirms two live-authored walls at **30.0°** (the
  v0.3.439 CAD polar command) and **60.0°** (this dynamic input). Typecheck + eslint + vitest (121) +
  build green.

## v0.3.452 — the "preparing geometry…" hang, root-caused and fixed (Gate A unblocked)

- **The bug**: after a model loads, `fitToModels`/`fitToItems` awaited an **animated** camera-controls
  transition. That promise resolves from the rAF-driven update loop — and a **hidden tab throttles rAF
  to zero**, so the fit never settled and the "preparing geometry…" loading overlay hung forever. Any
  user who switched tabs mid-load hit it; embedded/headless panes hit it every time (which is why the
  dev-preview "geometry loader stall" haunted every prior session — the geometry was actually loaded
  and rendering behind the stuck overlay the whole time).
- **The fix**: animate the fit only when the tab is visible (`!document.hidden`) — a hidden tab gets an
  instant fit, which needs no rAF. One line in each fit path.
- **Verified live, end-to-end, for the first time in this environment**: full stack up (API :8093 +
  Vite), model published (real Fragments conversion), viewer boots past the overlay, the Project
  Browser builds (levels/disciplines/classes/types), and — the capstone — a **polar-coordinate wall**
  (`WALL 0,0 @6<30 3`, the v0.3.439 grammar) typed into the live CAD command bar authored → published →
  reconverted → reloaded (3→4 meshes), with the source IFC confirming the wall axis at **exactly
  30.0°**, midpoint (2.598, 1.5). Undo depth 1.
- This clears the roadmap's **Gate A** (live-viewer verification): SNAP-KIT phase 2, REL-4, the
  paper-space editor, and the SITE-1 composed view are now verifiable in-environment.
- Typecheck + eslint + vitest (118) + build green.

## v0.3.451 — CI fix: the two new suites write IFC uploads to a writable dir

- `test_jobs` and `test_sheet_layout` (new in v0.3.448/449) upload a source IFC, and the default
  `IFC_DIR=/app/ifc` is **read-only in the CI container** (it resolves writable on the Windows dev
  machine, so the local gates were green while CI failed with `PermissionError: /app`). Both now set a
  local `IFC_DIR` the way `test_cost_db` already does. Test-env-only change — no src delta; both suites
  re-verified locally.

## v0.3.450 — roadmap completion: DEV-3 incremental typecheck + the ⛔ gated ledger

- **DEV-3 (measured, not guessed)**: `tsc` incremental mode with the buildinfo in `node_modules/.cache`
  (never committed) — local `npm run typecheck` **67s cold → 9.4s warm (7×)**; CI runs cold and is
  unchanged. Typecheck + eslint + vitest (118) + build verified with the change.
- **The roadmap reaches its honest completion point.** Every item that could be built and verified in
  this environment has shipped across v0.3.413–450 (the audit remediation, GEN-SCORE, PLUGIN-REGISTRY,
  VIEWER-FUNNEL, the zero-row portfolio roll-up, the authoring-router split, JOB-QUEUE, the
  SHEET-VIEWPORTS server slice, and the CAD-UX lesson arc). What remains is now a **⛔ Blocked / gated
  ledger** in the roadmap where every entry names its concrete unblocking event:
  - **Gate A** live-viewer verification (SNAP-KIT phase 2, REL-4, the paper-space editor, SITE-1 UX,
    tile-streaming, multiplayer cursors, AR);
  - **Gate B** upstream dependencies (IFC5/IFCX write, bSI Validation Service);
  - **Gate C** paid/networked services (cloud cost ingest, paid APS, SOC 2 infra, BMS/IoT telemetry);
  - **Gate D** large optional builds with complete prerequisites (coupled-frame FEM, 3D hero, Unity,
    reality capture, the frontier bets).
- DEV-2 closed with rationale (cross-process coverage on a 265-suite parallel gate costs ~30-50% wall
  for an unactioned number); SITE-1's overlay half noted as already shipping (`gis.ts` GeoJSON / DEM /
  basemap loaders).

## v0.3.449 — SHEET-VIEWPORTS: true paper-space viewport composition (CAD-UX lesson #8, server slice)

- **Sheets stop being fit-to-cell grids and become real paper space.** `sheet_layout.py`: a sheet is a
  set of **viewport rectangles** (fractions of the drawable area), each with:
  - its own view — plan storey / section / elevation;
  - an optional **fixed drawing scale** — the view is placed at true 1:N on paper and **geometrically
    clipped** to its rectangle (Liang-Barsky segment clipping, split runs on re-entry) — a fixed-scale
    viewport crops like a real one instead of shrinking to fit;
  - an optional **per-viewport class freeze** (a structure-only or MEP-only viewport of the same model);
  - fit-to-rect fallback when no scale is given (the legacy behaviour).
- Preset arrangements (`key` / `quad` / `plan-pair`) as starting points; rendered through the shared
  titleblock pipeline (SVG + PDF). `POST /projects/{pid}/drawings/layout.svg|.pdf` +
  `GET /drawings/layout/presets` (in the authoring-docs leaf).
- The interactive paper-space editor (drag viewports in the web app) builds directly on these endpoints —
  tracked as the viewer-gated remainder in the roadmap.
- `test_sheet_layout`: hand-computed clipping (corner-crossing kept, exit/re-enter splits, outside
  dropped), exact 1:50 scale text + clipped-inside-rect proof, class-freeze filtering, SVG/PDF render,
  endpoints incl. the 409-without-a-model path. 265/265 suites green; ruff clean.

## v0.3.448 — JOB-QUEUE: durable background jobs (then-bucket)

- **Heavy work stops hanging HTTP requests and stops dying with the process.** `jobs.py` is the smallest
  durable queue that fixes both with no new dependencies:
  - jobs persist as DB rows (`queued → running → done | error`) with params/result/error + timestamps;
  - one daemon worker per process claims the oldest queued job and runs its handler with its own session;
  - **crash recovery** — on worker start, any job orphaned in `running` by a dead process re-queues and
    runs again (handlers are idempotent by contract — they re-derive, never increment);
  - a handler exception lands on the row (`error` + message), never kills the worker;
  - **registry of kinds** (`register_kind`) — one line to add a kind, the same extension shape as edit
    recipes, so plugins can register job kinds too.
- Built-in kinds: `echo` (diagnostic) and the real `cobie_export` — the full-model COBie handover parse
  now proves itself in the background and reports per-sheet row counts.
- Endpoints: `POST /projects/{pid}/jobs` (editor) → `GET /projects/{pid}/jobs/{id}` (poll, cross-project
  404) → `GET /projects/{pid}/jobs` (list, bounded). Worker starts in the app lifespan.
- Unknown kinds fail **at submit** (400 with the registered list), not silently in the queue.
- `test_jobs`: crash recovery (orphaned running → re-queued → completed), error capture, endpoints,
  cross-project 404, the real background COBie export on a generated model. 264/264 suites; ruff clean.
- Inline heavy paths (bundle export, PAdES, generative runs) migrate onto the queue opportunistically —
  the infrastructure and the pattern are now in place.

## v0.3.447 — REL-3: the authoring god-router splits into leaves

- **`routers/authoring.py` 1,350 → 1,030 lines**, with 21 read-only endpoints extracted into two
  responsibility-named leaves included by the parent (so **every URL and main.py are unchanged** —
  zero caller/test churn):
  - `authoring_docs.py` — the documentation & provenance set: plan/sheet/schedule SVG · CSV · PDF, the
    spec manual, detailing/keynote QA, the document graph + element sources;
  - `authoring_analysis.py` — structural (analytical model, gravity solve, ASCE 7 lateral) + MEP
    (system browser, sizing, connectivity, sprinkler coverage) + the element-connection graph;
  - `authoring_shared.py` — the shared project-with-source precondition + safe-filename helper.
- `authoring.py` keeps what it is actually about: the edit/recipe surface (apply, graph, preview,
  history/undo, AI author, publish). Behaviorally smoked: all 12 moved URL families live at unchanged
  paths (409-not-404 on a sourceless project). 263/263 suites green; ruff clean.

## v0.3.446 — PERF: the owner portfolio roll-up goes zero-row

- **`/portfolio/summary` no longer materializes any module rows into Python.** The audit's N+1 finding:
  per project it loaded every open/mitigating risk row (for a sum) and every incident row (for a
  classification tally). Now all four per-project figures are SQL aggregates — risk count via state-scoped
  COUNT, risk exposure via the (new) state-scoped `sum_field`, OSHA-recordable tally via the (new)
  `count_field_in` JSON-classification COUNT, open RFIs via the existing COUNT — so the owner dashboard
  scales with the project count, not the record count.
- New portable helpers in the module engine (Postgres `->>`/SQLite `json_extract`):
  `sum_field(..., states=[…])` and `count_field_in(db, key, pid, field, values)` — reusable for every
  future tally that today walks rows.
- Verified against the 3,000-row mega-project scale suite (dashboard tallies unchanged) + tenant-scoping
  + dashboard suites. 263/263 green; ruff clean.

## v0.3.445 — VIEWER-FUNNEL: the demo gets its free-IFC-viewer identity (+ roadmap closures)

- **massing.build now names what it already ships**: the hero CTA and a dedicated landing section present
  the live demo as a **free in-browser IFC viewer & model checker** — open your own .ifc (small files
  parse in-browser via WASM, "no signup, no install, no upload — your model never leaves your machine"),
  inspect properties/quantities, run read-only model QA — with the explicit upgrade path to the free
  desktop app / full stack. Visually verified. (CAD-UX lesson #5 — the viewer-funnel positioning.)
- **Roadmap closures backed by the v0.3.441 audit evidence** (no code change needed):
  - UI-SURFACE №11 — the caller scan found no zero-caller client methods (flagged names were recipes
    dispatched by string); nothing to delete.
  - REL-5/7 — `errorReporting.ts` already wires window.onerror + unhandledrejection to the error log,
    panel promises carry near-universal `.catch` coverage, and the "~1,075 dead lines" claim did not
    survive proof.

## v0.3.444 — PLUGIN-REGISTRY: manifest-gated recipe plugins (CAD-UX lesson #6)

- **Third-party authoring recipes without archaeology.** A plugin is a directory with a `plugin.json`
  manifest + a `register(api)` entry that adds **namespaced GUID-stable recipes** (`<plugin>.<recipe>`)
  into the same registry every authoring surface dispatches — `POST /edit`, the CAD command line, the AI
  bar, MCP `run_recipe` — and they appear in the authoring matrix automatically, categorized.
- **Three hard gates** (the OpenAEC-study design, adapted):
  - **opt-in** — plugins execute Python at load, so discovery is OFF unless `AEC_PLUGINS_ENABLED=1`;
  - **api-version gate** — the manifest's `api_version` MAJOR must match the host's `PLUGIN_API_VERSION`
    (1.0); a mismatch refuses the plugin with a clear reason instead of loading the wrong contract;
  - **collision refusal** — an existing recipe key is never overwritten.
- Refusals are data + logs, never fatal (one broken plugin can't block the rest); reload is idempotent
  (previous registrations replaced). `GET /plugins` shows loaded + refused with reasons;
  `POST /plugins/reload` is platform-admin (RBAC on). Loaded at boot via the app lifespan.
- **Template + worked example** at `plugins/` (`example-wall-brand`: stamps a pset on every wall by
  reusing the host's own `edit.set_pset_on_class` primitive — build on the toolkit, don't re-invent).
- `test_plugin_registry`: off-by-default, all four refusal modes (bad api / no manifest / register()
  raised / collision), idempotent reload, the namespaced recipe applied through `apply_recipe` on a real
  IFC + visible categorized in the authoring matrix, endpoints incl. the RBAC-on 403 on reload.
  263/263 suites green; ruff clean.

## v0.3.443 — GEN-SCORE: generative design-option scoring (cost · carbon · yield · code)

- **The frontier bet lands**: `option_score.py` generates a deterministic variant grid around a zoning
  envelope (`generate_options` — FAR-utilisation steps × building types) and ranks every candidate
  through the platform's own engines in one pass:
  - **cost** — conceptual $/SF (regionalized, escalated);
  - **carbon** — whole-building embodied-carbon benchmarks (kgCO₂e/m² GFA by building type, editable
    defaults aligned with the cost catalog);
  - **yield** — net sellable/leasable area from the massing engine;
  - **compliance** — FAR-achieved and height-limit zoning checks: a violating option is flagged, its
    composite capped below every compliant one, and it is never `recommended`.
  Criteria are min-max normalized within the option set (a flat criterion scores 100 for all — it can't
  differentiate, so it penalizes no one) and combined by overridable weights.
- `POST /projects/{pid}/design/options/generate` + `/design/options/score`; typed client methods; a
  **⚖ Score options** block on the conceptual-estimator card (Analytics ▸ Risk & Cost): lot W/D + FAR +
  height limit → ranked table (score, $/sf, tCO₂e, floors, GFA, code ✓/✗, ★ recommended).
- Deterministic, offline, no LLM — the "generative" part is a systematic grid, the scoring is the
  engines. Deepen later with per-option 5D takeoffs + EPD carbon once options carry real models.
- `test_option_score`: hand-computed grid (2×3), warehouse-beats-hospital on cost+carbon with equal
  yield, carbon total = GFA × benchmark, weight steering, compliance gating, empty-set 400, endpoints
  end-to-end. 262/262 suites green; web typecheck + eslint + vitest (118) + build green.

## v0.3.442 — full-codebase audit: backend fixes, parse robustness, infra hygiene

The backend + cross-cutting lanes of the same audit as v0.3.441 (three parallel deep passes over the
whole tree), every finding fixed and verified:

- **IFC cache bypass (P1 perf)** — `deps.open_source_ifc` called raw `ifcopenshell.open()` per request,
  so every hit on the QA / health / georeferencing endpoints (which dashboards poll) reparsed the full
  model from disk while authoring endpoints served the same file from the LRU. Now routed through the
  shared `(path, mtime, size)`-keyed cache — same invalidation on re-upload.
- **Cost-vintage import gating (P1)** — importing a vintage flips the global `is_latest`, silently
  repricing every unpinned project's estimate — yet the routes were auth-only. Now: open with RBAC off
  (dev/single-operator parity), **platform-admin** (`AEC_ADMIN_EMAILS`) with RBAC on. +403 test.
- **Authoring race (P1)** — two concurrent edits (or an `/edit` racing an MCP `run_recipe`) both read the
  same `source_ifc` and the last pointer-swap commit silently orphaned the other user's authored version.
  All three read-modify-write paths (`/edit`, `/edit/graph`, MCP `_run_recipe`) now hold the per-project
  `pid_lock` for the whole load→apply→swap→commit cycle, re-reading the pointer under the lock.
- **One escalation baseline (P2)** — the conceptual estimate escalated its headline from a private
  2025/4.5% pair while `total_at_construction_midpoint` in the same response used the market table's
  2026/region rates. Now both derive from `market_intelligence` — no unaccounted gap.
- **Honest GFA benchmark (P2)** — the model-vs-benchmark trust test compared escalated model dollars
  against a base-year benchmark computed from NET area. The benchmark now grosses up net→gross (×1.15)
  and carries the same localization/escalation factor as the model total — `recommended` flips on model
  completeness, not on dollar-year or area-basis skew.
- **Parse robustness (COBie + drawings)** — all 8 silent `except: pass` swallow sites (psets, contact
  emails, zone/system members; mesh bake, section cuts, room tags, element callouts, elevation
  silhouettes) now **count what they skip and log it** (debug per element + one summary warning per
  operation). A half-parsed model is visible in the export log, never silently thin. Shapes unchanged.
- **One billed-to-date** — `project_budget.billed_to_date` (SQL SUM) replaces three hand-rolled
  owner-invoice sums (loan-draws keeps its row-walk — it needs per-tranche dates for interest accrual).
- **Infra** — security scan pinned to Python 3.12 (audit the interpreter that ships); the version guard
  now locks the whole @thatopen suite + three as a recorded known-good tuple (bumping one package alone
  fails CI until the tuple is deliberately updated; negative-tested); inert CodeQL template step removed;
  `cost_db.resolve` docstring corrected (nearest-above fallback).

Audit non-findings worth recording: caches are bounded (LRU + eviction), temp files clean up in
`finally`, the test-manifest guard structurally prevents orphan suites. 261/261 suites green; ruff clean.

## v0.3.441 — web audit fixes: live streams that actually live, honest sorting, strict polar

From the full-codebase audit (frontend lane) — five defects the toolchain can't see:

- **SSE auth (P1)** — the backend accepts an `aec_token` cookie precisely because EventSource cannot send
  an Authorization header, but the client never set it: under production RBAC every live stream
  (model collab, notifications, pull-plan board) resolved anonymous → 403 → silent infinite reconnect.
  `setToken` now mirrors the bearer token into the cookie (Path=/, SameSite=Lax, Secure on https;
  cleared on logout), so the "real-time" features are real in production, not just in dev.
- **SSE demo guard (P1)** — `liveStream` now short-circuits in the Pages/demo build (no backend there):
  previously opening the viewer or Schedule panel in the public demo spawned an EventSource that died
  CLOSED and retried forever (5s→60s), spamming console errors. Same `IS_DEMO` guard every fetch has.
- **Live-board teardown (P2)** — the pull-plan SSE stream + presence timer now close synchronously when
  the Schedule panel re-renders (module-level replacement) and on the first event after the view is
  left — rapid Schedule↔Home toggling used to stack concurrent streams for up to 20 s.
- **Record-list sorting (P2)** — the module-table comparator is now type-aware: numeric fields compare as
  numbers ("10" after "9"), blanks group at the end in both directions ("5 < ''" and "5 > ''" are both
  false, so blank rows used to scatter randomly through a numeric sort).
- **CAD polar strictness (P2)** — malformed polar tokens now error instead of guessing: `5<` (angle
  dropped) drew a wall due east, `<45` a zero-length wall, `@5<45<90` silently ignored the tail —
  `Number("")` is 0. Exactly one `<` with a number on each side is required. +1 vitest case (4 forms).

Typecheck + eslint + vitest (118) + build green.

## v0.3.440 — COST-DB: import your own cost book (custom vintage)

- **A firm can now price through its OWN rates**, not just the shipped benchmark. `POST
  /cost/datasets/import-custom` installs a cost book as a `custom`-origin vintage:
  - body is a flat `{"rates": {"IfcWall": 180, "IfcColumn": 240}}` map (quickest) **or**
    `{"rows": [{"ifc_class": "IfcWall", "total_cost": 180, "description": "…", "uom": "m2"}, …]}`;
  - missing MasterFormat codes are filled from the classification spine off the IFC class;
  - re-importing the same (year, quarter) **replaces that custom vintage in place** (a corrected upload
    never duplicates); it's set latest and a project prices through it, localized + escalated like any
    vintage.
- New `cost_db.import_custom_vintage` + a pure, tolerant `parse_cost_rows` (accepts `total_cost`/`rate`/
  `cost`/`unit_cost`, drops rows without an ifc_class or a positive rate). Offline — this is the "+ import"
  the COST-DB task always implied. `test_cost_db` extended (both body forms, in-place replace, empty→400,
  the parser edge cases). 261/261 suites green; ruff clean.

## v0.3.439 — CAD command line: AutoCAD relative + polar coordinates

- **The command line now speaks the coordinate grammar every drafter already knows.** Point tokens in
  `WALL`/`BEAM`/`SLAB` accept, in addition to `x,y` absolute:
  - `@dx,dy` — **relative** cartesian (offset from the previous point in the command);
  - `d<a` / `@d<a` — **polar** (distance `d` at angle `a`° CCW from east), absolute-from-origin or relative.
  So `WALL 0,0 @5<0` draws 5 m east, `WALL 0,0 @5<90` 5 m north, and `SLAB 0,0 @4<0 @4<90 @4<180 0.3`
  walks a 4 m square slab — no mental cartesian arithmetic. Absolute `x,y` is unchanged.
- Pure-parser change (`cadCommands.ts`), so it's exhaustively unit-tested and flows through the existing
  command-bar dispatch with no viewer wiring. 4 new vitest cases (relative, relative-polar, absolute-polar,
  the polar square). Typecheck + eslint + full vitest (117) + build all green.

## v0.3.438 — the developer proforma carries the cost provenance too

- **One cost basis, visible everywhere.** The dev-budget **sync-from-model** now returns the same
  `cost_adjustment` block (location index · escalation · combined factor) the takeoff and 5D endpoints
  carry — so a developer sees *why* the model-derived hard cost is what it is (which vintage, localized to
  which region, escalated to which year), not just the number. The hard cost itself already priced through
  the localized/escalated vintage (v0.3.436); this surfaces the provenance, it does not re-apply it.
- Completes the cost-provenance theme across all three model-cost surfaces (takeoff · 5D · proforma).
  Backend-only; covered by the existing dev-budget sync test path. 261/261 suites green; ruff clean.

## v0.3.437 — 5D element costs price through the localized/escalated vintage

- **The per-element 5D table now agrees with the takeoff.** `/5d/element-costs` (5D-BIND) priced every
  GUID off the static representative rate table while `/qto/by-floor` priced through the project's
  localized + escalated cost vintage — the two could disagree. `element_5d.element_costs` now takes an
  optional `rate_overrides` map and the endpoint feeds it the same `_vintage_overrides` the takeoff uses.
  The rate **basis** (volume/area/length/count) always stays representative; only the rate magnitude is
  overridden — exactly how the estimate layers overrides. The response carries `cost_vintage` +
  `cost_adjustment` like the takeoff, so per-element and roll-up numbers are one source of truth.
- Falls back to the representative table when no vintage is installed (unchanged behaviour). `test_element_5d`
  extended (override changes only the targeted class; others keep the base rate). 261/261 suites; ruff clean.

## v0.3.436 — COST-DB: localized + escalated cost vintages (offline)

- **Element-level estimates are now project-real, still offline.** A cost vintage stores national-average
  rates for its year; `cost_db.rates_for_project` makes them specific to *this* project by multiplying by
  the project region's **location cost index** and **escalating** from the vintage year to the construction
  midpoint — reusing the shipped market table (`market_intelligence.escalation_factor`), no network.
- **Wired into the estimate path.** `/qto/by-floor` and `/estimate/from-model` price the takeoff through the
  localized + escalated rates and return a `cost_adjustment` block (location index · escalation factor ·
  combined factor); `GET /projects/{pid}/cost-vintage` previews the same adjustment without running a
  takeoff. Region + timeline come from the project's `market_assumption` (adopted, else latest) — the same
  source the market panel reads, so the numbers agree.
- **Refactor:** `escalation_factor(region, from_year=…, to_year|start_year…)` extracted from `escalate` so a
  vintage's rates are only ever escalated over the years they actually span (vintage year → midpoint), and a
  dollar amount still escalates from the base year exactly as before. Neutral by default: no region + no
  timeline → global-average index (1.00) and no escalation, so rates are unchanged.
- Backend-only; no UI change. `test_cost_db` extended (localize × escalate math, neutral defaults, both
  endpoints carry the adjustment). 261/261 suites green; ruff clean.

## v0.3.435 — MCP-PACK: the MCP surface becomes a first-class authoring + analysis agent (CAD-UX lesson #7)

- **The MCP tool catalog grew 8 → 14.** External AI agents (Claude Desktop, an agent) can now drive the
  authoring + analysis engines, not just read status — through the *same* gated engines the UI and HTTP API
  use, so nothing is duplicated and the surface can never exceed a normal caller:
  - `list_recipes` — the authoring-coverage matrix (every recipe drivable, by category + IFC output);
  - `run_recipe` — apply a **GUID-stable authoring recipe** (add_wall, add_column, set_pset, …), saving a
    new audited, undoable IFC version (reconvert/publish stays on the normal flow);
  - `schedule_risk` — Monte Carlo P10/P50/P80/P90 completion + delay drivers;
  - `carbon_report` — A1–A3 embodied carbon + Buy Clean limits + LEED inventory;
  - `permit_readiness` — submission-readiness over egress + code + sheet coverage;
  - `drawing_qa` — drawing-set QA (duplicate/gap numbers, titleblock, model cross-checks).
- **Same authorization as the UI.** The two write tools (`create_rfi`, `run_recipe`) carry the identical
  **editor**-role gate their HTTP routes use when RBAC is on — membership alone isn't enough; a viewer-role
  member is refused. Read tools stay membership-scoped (a non-member identity is refused per SEC-MCP).
- **A drop-in Claude skill pack** at `docs/mcp-skills/` — `SKILL.md` plus three copy-ready playbooks
  (draft-an-RFI, run-a-takeoff, drive-a-recipe) so an agent knows *how* to use the tools: read before
  writing, ground every action in the project's real state, publish after a batch of edits.
- `docs/mcp.md` + README refreshed; `test_mcp_standards` extended (catalog, the new engine tools, the
  editor gate on `run_recipe`, the no-model error signals). 261/261 suites green; ruff clean.

## v0.3.434 — SNAP-KIT (phase 1): the precision engine + polar tracking in draft mode (CAD-UX lesson #2)

- **New authoring precision** (from the OpenAEC study — object-snap / polar / dynamic-input is the other
  half of "friendly CAD"). A pure, unit-tested geometry engine `snapEngine.ts` (sibling to `inference.ts`):
  - **`resolveSnap`** — nearest object-snap among candidates within tolerance, priority-ordered
    (endpoint › intersection › center › perpendicular › midpoint › grid › nearest); **`segmentSnaps`**
    emits endpoint + midpoint candidates for a polyline (the viewer feeds it what it raycasts);
  - **`polarConstrain`** — AutoCAD polar tracking: snap the bearing from an origin to the nearest N°
    increment (distance preserved), with a lock flag + the locked angle;
  - **`applyDynamicInput`** — constrain the rubber-band by a typed distance and/or angle (the
    "5 <Tab> 90 <Enter>" flow) — distance-only keeps bearing, angle-only keeps length, both give an
    exact point.
- **Wired into draft drawing now**: when the axis/parallel inference doesn't lock, the click snaps to the
  nearest **45° increment** from the previous point — catching the diagonals the axis-only inference
  missed. Additive + guarded (a hard geometry-vertex snap always wins).
- 14 exhaustive vitest cases + verified live in the browser runtime (polar ~46°→45° with distance
  preserved, dynamic-input distance/angle exact, endpoint-beats-midpoint). Typecheck + eslint + full
  vitest (113) + build green. *(Phase 2 — osnap glyphs + a live dynamic-input overlay in the cursor — is
  tracked in roadmap §🧭; the tested engine is ready for it.)*

## v0.3.433 — docs: client-vs-server architecture doc (OpenAEC-study lesson #4)

- New [`docs/client-vs-server.md`](docs/client-vs-server.md): where work runs and why — the thin-client /
  Python-authoring-service boundary (client renders/snaps/drafts; server holds the IFC source of truth and
  does every geometry mutation + analysis), plus the two platform limits that shape the client, banked
  from the OpenAEC study: **WebGL2 has no vertex-stage storage buffers** (custom 2D fill/linetype must
  triangulate or gate on WebGPU — today our 2D is server-side SVG/PDF, so it's moot) and **wasm is
  single-threaded without SharedArrayBuffer**, which needs cross-origin isolation (documenting exactly how
  nginx COOP/COEP + the Pages `coi-serviceworker` provide it, and why the attachment route sets CORP).
  Doubles as onboarding + architecture reference; no code change.

## v0.3.432 — docs: roadmap hygiene — archive the shipped upgrade cycle, refresh the intro

- Roadmap maintenance per the file's own "holds only what's OPEN" rule: the intro now reads **latest
  release v0.3.431** (was v0.3.412); the fully-shipped 🎯 upgrade-plan tiers (P0/P1/P2/P3 v0.3.413–428)
  and the CADCMD/AUTHOR-MATRIX study outputs are archived in `roadmap-completed.md` with a compact
  pointer left in `roadmap.md`; the "Current focus" section rewritten to name only what's genuinely open
  (REL-4 web decomposition, REL-3 remainder, DEV-2/3, REL-5/7, COBie robustness, the №11 tail, the №18
  bucket, and the remaining CAD-UX lessons). No code change.

## v0.3.431 — AUTHOR-MATRIX: a live authoring-coverage matrix (OpenAEC-study lesson #3)

- **New reference surface** (from the OpenAEC study — their COMMANDS.md capability tracker is a cheap,
  brutally-honest maturity signal). `authoring_matrix` derives an authoring-coverage table **live from
  the `edit.RECIPES` registry** + a curated category/output map: **76 recipes across 14 categories**
  (create-structure / -enclosure / -opening / -space / -mep / -content · annotate · edit · type · group ·
  data · lifecycle · analysis), each with the IFC element it produces.
- Served at `GET /reference/authoring-matrix`, rendered to the committed `docs/authoring-matrix.md`, and
  guarded by a **completeness test** — a newly-added recipe with no category fails the gate, so the
  coverage doc can't silently drift from what's actually built (the honest tracker only works if it stays
  honest). It also documents that every recipe is one GUID-stable pass, dispatchable from the CAD command
  line, the AI command bar, the node canvas, or the panels.
- Verified: the matrix covers every registry entry exactly once, create-* rows all name an IFC output,
  the markdown renders clean, and the endpoint serves it; `ruff` clean.

## v0.3.430 — CADCMD: a CAD command line over the viewer (OpenAEC-study lesson #1)

- **New authoring surface** (from the OpenAEC / Open CAD Studio study — their single biggest UX win is
  importing AutoCAD muscle memory). A **deterministic CAD command line** in the viewer's authoring tools,
  instant and offline (no LLM roundtrip), driving the same GUID-stable edit recipes as the panels:
  - AutoCAD-style grammar + single-letter aliases — `WALL`/`W`, `COLUMN`/`C`, `BEAM`/`B`, `SLAB`/`S`,
    `LEVEL`/`LVL`, `SPACE`/`SP` — e.g. `WALL 0,0 5,0 3`, `C 2,2 3.2 0.4`, `SLAB 0,0 5,0 5,5 0,5 0.25`;
  - **↑/↓ history**, **spacebar repeats the last command** on an empty line, `Esc` clears, `HELP` lists
    the grammar and `HELP WALL` shows one usage; every parse error carries the usage string.
  - The parser is a **pure module** (`cadCommands.ts`) — no DOM, no network — so it's exhaustively unit
    tested (11 cases: each verb + aliases, defaults, z-coordinate ignore, trailing-thickness detection,
    and the error paths); the viewer supplies only the input + apply/reload.
- Complements (doesn't replace) the AI "type what you want" bar: the CAD line is exact and instant for
  drafters who already know the grammar; the AI bar is forgiving for everyone else.
- Verified: typecheck + eslint + full vitest (99, +11) + production build green. The OpenAEC study's other
  lessons (snap/dynamic-input kit, authoring-coverage matrix, client-vs-server doc, plugin registry, MCP
  pack, sheet viewports) are captured in `docs/roadmap.md` §🧭.

## v0.3.429 — UI-SURFACE: schedule acceleration levers on the Schedule panel (P2 №11)

- Surfaced the **schedule-optimization advisory** (`/schedule/optimize`) — it was API-only. The Schedule
  panel now shows a "🚀 Acceleration levers" card directly under the Monte Carlo risk card: the crash
  candidates (longest critical activities) and fast-track candidates (consecutive critical activities to
  overlap) with the days each saves, the best-single-lever headline, and the optional AI narrative. The
  pairing is the point — the risk card says *how late you might be*, this card says *how to pull it back*.
- Advisory only (it never rewrites the schedule), and it degrades to a hint when the network has no
  critical path. Verified: typecheck + eslint + vitest + build green.
- *(№11 note: the earlier "~70 unused client methods" over-counted — most flagged names are authoring
  recipes dispatched by string, or methods surfaced under a variant name like `bidLevelingDetail`; the
  genuinely-dark high-value read endpoints are being surfaced, not deleted.)*

## v0.3.428 — 5D-BIND: every GlobalId carries its live cost (+carbon) row (P3 №17)

- **New capability** (upgrade-plan P3 №17 — the last buildable P3 item; №16 LAYOUT-EXPORT was found
  already shipped in Wave 8). New `element_5d.element_costs`: the **GUID-keyed 5D table off the live
  property index** — element quantity (in the rate's basis: volume/area/length/count, from the
  element's own Qto sets) × the class rate — so a GUID-stable edit → republish → reindex **reprices
  automatically**, nothing to resync. Honest exclusions: no rate or a basis/Qto family mismatch is
  skipped, never guessed.
- **Carbon rides the same row** where the material matches — one table serving cost heatmaps, carbon
  hotspots, and (later) generative option scoring against cost + carbon + code in one pass. Class +
  storey rollups, top-cost list. `GET /projects/{pid}/5d/element-costs` (404 until a model loads).
- Hand-computed fixture (wall/slab/door/pipe across all four bases; mismatch exclusions asserted) and
  the reprice semantics proven: doubling the slab volume changes exactly that row (cost 825→1650,
  carbon 450→900). cost/estimate suites green.

## v0.3.427 — QA-AGENT: drawing-set QA review, every finding sheet-cited (P3 №15)

- **New capability** (upgrade-plan P3 №15; agentic drawing review is the 2026 benchmark — but most
  tools review raster PDFs; this platform generates its sheets, so QA checks the **structured source**
  directly — no OCR, no hallucination). New `drawing_qa.review`:
  - **Set integrity** — duplicate sheet numbers (critical → HOLD), numbering gaps that name the missing
    sheets, empty titleblock fields (title/discipline);
  - **Issuance hygiene** — issued sheets with no issue date, unparseable revision tokens;
  - **Model cross-checks** — plans-per-storey (an N-storey model needs N plan sheets), a door schedule
    when doors are modeled, S/M/P-series coverage when structural/MEP elements exist;
  - findings ranked critical → major → minor, each **cited to its sheet**, with a HOLD / REVIEW / CLEAN
    verdict. Runs register-only without a model and adds the cross-checks when one loads.
- `GET /projects/{pid}/drawing-set/qa`. Deterministic + offline (the honest core an AI reviewer can
  later narrate). Verified on a deliberately-defective register (dup A-101, missing A-103, issued-no-date,
  bad revision, blank title) + a 5-storey model; drawing-set/sheetgen/issuance suites green.

## v0.3.426 — UI-SURFACE: the new engines are now visible in the portal (P2 №11, first slice)

- The three capabilities shipped in v0.3.423–425 now have a UI (they were API-only):
  - **Schedule panel → "🎲 Schedule risk (Monte Carlo)"** — CPM vs P50 vs P80 (+ calendar finishes),
    on-time odds, the P80 buffer a reliable commitment needs, PPC-calibration note, and the top-5
    delay drivers with criticality % and mean slip.
  - **Risk & Cost panel → "Carbon compliance"** — total tCO₂e off the model with coverage % and
    intensity, the Buy Clean pass/needs-EPD table with headroom, and the top hotspots.
  - **Risk & Cost panel → "Permit-submission readiness"** — READY/NOT-READY verdict, readiness % +
    approvability %, and the ranked deficiency list with actions.
- New typed client methods (`scheduleRisk`, `carbonComplianceReport`, `permitReadiness`); panels degrade
  to a "load a model" hint when no model/index exists. *(Remaining in №11: triage of the legacy unused
  client methods.)*
- Verified: typecheck + eslint + vitest (88) + production build green.

## v0.3.425 — PERMIT-CHECK: permit-submission readiness in one report (P3 №14)

- **New capability** (upgrade-plan P3 №14; cities are rolling out AI plan review in 2026 — applicants
  who arrive pre-checked win the queue). `permit_check.readiness` composes what the platform already
  computes into the intake report a permit tech would produce:
  - the **computed egress check** (IBC 1004/1005 from the model's spaces + doors — a shortfall is a
    plan-review *rejection*, ranked critical), the **approvability pre-flight** (≥80% bar), and the
    **code-analysis summary** (occupancy group + construction type declared, jurisdiction-adopted
    edition resolved);
  - the **drawing register's required sheet series** (G code analysis · A · S · M · E · P) — each
    present/missing with counts.
- Output: an intake **checklist** (requirement · satisfied · evidence), the **deficiency list** ranked
  critical → major → minor with concrete actions, readiness %, and a READY / NOT-READY verdict — with
  the not-a-certified-review disclaimer. `GET /projects/{pid}/permit/readiness`.
- Verified end-to-end: 409 without a model; a seeded 2-storey model + spaces produces the composed
  report; registering the six sheet series + declaring occupancy/type/jurisdiction flips the rows and
  raises readiness. Fixed en route: the engine takes an edition *year*, not a jurisdiction string (the
  test caught the misuse live). codecheck/approvability/code-analysis suites green.

## v0.3.424 — CARBON-EC3: compliance-grade embodied carbon off the model itself (P3 №13)

- **New capability** (upgrade-plan P3 №13; LEED v5 makes an embodied-carbon inventory **mandatory for
  projects registering after July 1, 2026**, and Buy Clean programs set procurement GWP limits). New
  `carbon_compliance` layer on the existing factor table:
  - **Per-element A1–A3** (`GET …/carbon/elements`) — material category matched from each element's
    name/type/material psets, quantity from its **own Qto sets** (volume→m³ else area→m²), carbon keyed
    by **GlobalId** so hotspots click through to 3D. Honest coverage %: a unit-family mismatch or an
    unmatched material is excluded and reported, never guessed. Storey + category rollups, intensity
    per m² GFA.
  - **Buy Clean check** — achieved factor vs representative program GWP limits per category; a fail on
    a default factor reads "obtain a product EPD below the limit" — exactly the procurement action the
    program forces.
  - **LEED-style A1–A3 inventory** (`GET …/carbon/compliance`) — category rows (quantity · factor ·
    source · share), intensity, coverage and a plain-language disclosure. Offline + deterministic;
    factors are labeled representative until a deployment supplies product EPDs.
- Hand-computed test (930 kg over a 6-element fixture with deliberate mismatch/unmatched cases, 60%
  coverage honesty, Buy Clean pass + fail directions, inventory shares = 100%); existing carbon suite green.

## v0.3.423 — SCHED-RISK: Monte Carlo schedule risk over the CPM network (P3 №12)

- **New capability** (upgrade-plan P3 №12; probabilistic forecasting is table-stakes in 2026 CM tools).
  `schedule_risk.simulate` runs a Monte Carlo over the existing FS network: per-activity
  **triangular(optimistic, most-likely, pessimistic)** durations — explicit `duration_optimistic` /
  `duration_pessimistic` fields honored, sensible fat-right-tail defaults otherwise — and reports
  **P10/P50/P80/P90** project duration (+ calendar finishes when the schedule carries a start date),
  the **P80 buffer** over the deterministic CPM date, an on-time probability, a duration histogram,
  the per-activity **criticality index** (share of iterations on the critical path — the near-critical
  work a single CPM pass hides), and a **delay-driver ranking**.
- **PPC calibration** — the team's own Last Planner reliability calibrates the default pessimistic
  tail (auto-pulled from the pull-plan board; 80% PPC = neutral, below widens, above narrows —
  explicit per-activity fields are never overridden). The calibration signal PPC theory says it carries.
- `GET /projects/{pid}/schedule/risk?iterations=&seed=&ppc=` — seeded runs reproduce exactly.
- Verified on a hand-checked diamond network (deterministic CP 40d; percentile ordering; A1/A4 100%
  criticality, long branch ≫ short branch; PPC-50 P80 > PPC-95 P80; degenerate triangle = deterministic;
  cycle + empty guards) + endpoint smoke; cpm/alerts/optimize/pull-plan suites green.

## v0.3.422 — README-TRIM: the README reads like a README again (P2 №10 — P2 docs complete)

- **README** 983 → 560 lines: the "Recent platform work" section keeps the five newest narrative arcs
  (v0.3.113 → v0.3.412) and replaces the ~430-line release-by-release history dump with a one-paragraph
  pointer to `CHANGELOG.md` + `docs/roadmap-completed.md` (which is where that record belongs).
- The five June point-in-time audit docs (`audit-2026-06`, `gc-tools-audit`, `ux-findings`, `ux-ia`,
  `phase2-large-models`) now carry a "superseded — kept for the record" banner so nobody mistakes them
  for current state.

## v0.3.421 — DEMO-REGEN: the Pages demo snapshot rejoins the present (P2 №9)

- The massing.build/app viewer-only demo serves a captured API snapshot — last regenerated at
  **v0.3.309**, ~110 releases ago, so every panel added since rendered empty in the public demo.
- `build_demo_data.py`'s crawl list extended with the v0.3.310–420 surfaces — model QA / health /
  export-QA, versions (+ element-level diff), the structural chain (lateral incl. the drift screen,
  solve, analytical), MEP sizing + sprinkler coverage, doc-graph, scene digest, collab + edit history,
  drawing-set issuances, per-discipline quantities, and the global discipline tree — and re-run against
  the current seed: **952 fixtures (908 KB)**. Pushing this redeploys the live demo via Pages.
- Verified: typecheck + production build green with the new snapshot bundled.

## v0.3.420 — TZ-UTC: one clock for due-date & aging math (P1 №8 — P1 complete)

- **Bug fix** (upgrade-plan P1 №8, the last P1): overdue/aging computations in the dashboard, BIM-KPI
  scorecard, CDE container aging, closeout punch aging, CMMS PM scheduling, EVM data-date and the
  document manager's naming date compared ISO-stored dates against the **server's local wall-clock** —
  "overdue" and "days open" drifted a day around midnight and changed with the host timezone
  (`benchmarking.py` already did this right).
- New `timeutil.utc_today()/utc_now()`; all seven engines now age on the UTC clock. The EVM and
  operations suites' expectations aligned to the same clock — they were computing planned-value /
  next-due on local-today and genuinely tripped the fix during a local evening past UTC midnight
  (the exact drift being fixed, caught live).
- Verified: dashboard / bim-kpi / cde / closeout / evm / operations / docmanager + cycle guard green.

## v0.3.419 — DOC-RACE: per-project locks on the sidecar indexes (P1 №7)

- **Bug fix** (upgrade-plan P1 №7): the document manager and the edit-history stack are
  read-modify-write cycles over a single JSON sidecar in object storage. FastAPI runs sync endpoints in
  a threadpool, so two concurrent uploads to the same project could interleave load→save — the second
  writer clobbered the first (its file's bytes orphaned in storage, invisible in the UI) and both could
  be allocated the same `f{seq}` id.
- New `pid_lock.mutating(pid)` serializes sidecar mutations per project; `docmanager.upload/move/delete`
  and `edit_history.push/undo/redo` now run under it (`@_locked`, zero body changes). Cross-worker
  serialization (`--workers >1`) is documented as the remaining shape needing storage CAS.
- Proven by a new concurrency test: **12 simultaneous uploads → 12 index entries, 12 unique ids**
  (pre-fix this loses entries); docmanager / edit-undo / cycle-guard suites green.

## v0.3.418 — WEB-LIVE + WEB-LEAKS: resilient live streams, no leaked listeners/geometry (P1 №5–6)

- **SSE resilience** (P1 №5): a new `liveStream` core behind `modelStream` / `notificationStream` /
  `pullPlanStream`. EventSource only auto-retries transient drops — a backend restart/deploy answered
  with an HTTP error killed the stream **permanently and silently** (stale notification badge, frozen
  pull-plan board, dead collab banner until a full reload). Streams now re-subscribe with bounded
  backoff (5s→60s) and surface status; the workspace tab dims its badge + explains "live notifications
  disconnected — reconnecting…"; the notification stream closes on `pagehide`.
- **Listener leak** (P1 №6): `nodeCanvas.makeDraggable` added two **permanent** window listeners per
  node (2×N handlers, all running on every pointer move, never removed). Listeners now attach only for
  the duration of a drag and detach on mouseup.
- **GPU leak** (P1 №6): a failed/errored draft publish orphaned the one-element preview Fragments model
  (unique id per attempt → repeated failures accumulated geometry). The preview is now disposed
  explicitly on every non-success outcome (`loader.disposeOne`).
- Verified: typecheck + eslint + full vitest (88) + production build green.

## v0.3.417 — SEC-MCP: membership authorization in the MCP tool dispatch (P0 №4 — P0 complete)

- **Security hardening** (upgrade-plan P0 №4, the last P0): `mcp_tools.dispatch` executed any tool
  against any caller-supplied `project_id` with no authorization — safe only as long as the MCP server
  stays local/stdio. Dispatch now resolves an effective identity (`user` arg → `AEC_MCP_USER` env → the
  historical admin api-key default) and, under RBAC, membership-scopes it: `list_projects` returns only
  member projects and any tool addressing a non-member `project_id` raises `PermissionError`
  (defense-in-depth if the server is ever bound beyond stdio; operators can pin a restricted identity
  via `AEC_MCP_USER`).
- `test_mcp_standards` extended: a no-membership identity sees an empty project list and is refused
  project tools; the api-key default stays unrestricted; existing dispatch/write-tool coverage green.

## v0.3.416 — SEC-GUARD: production safety guard beyond Postgres (P0 №3)

- **Security fix** (upgrade-plan P0 №3): `_production_guard` only enforced its boot checks (RBAC on,
  real `AEC_AUTH_SECRET`, no trusted X-User, non-default MinIO keys) when the database was Postgres. A
  real deployment on MySQL — or a small SQLite self-host — booted straight onto the public dev signing
  secret, making every auth token and signed download URL forgeable.
- The guard now triggers on **any non-SQLite DATABASE_URL or an explicit `AEC_ENV=production`** (so a
  SQLite self-host can opt into the same protection); dev/test SQLite is unchanged and
  `AEC_ALLOW_OPEN=1` remains the deliberate escape hatch.
- `test_prod_hardening` extended: Postgres AND MySQL both refuse without RBAC; `AEC_ENV=production` on
  SQLite refuses; the escape hatch and plain-SQLite dev still boot. api/security/localmode suites green.

## v0.3.415 — WEB-BOOT: a corrupted stored setting can no longer brick the app (P0 №2)

- **Bug fix** (upgrade-plan P0 №2): `main.ts` parsed `localStorage["aec-settings"]` at module top level
  with no guard — the single unwrapped `JSON.parse` in the app. Any invalid stored value (quota-truncated
  write, old-version value, extension tampering) threw during module evaluation → permanent blank screen
  until the user manually cleared storage. Now falls back to defaults.
- Also: the GeoJSON reference-file parse throws a friendly "not valid JSON" (was a raw SyntaxError
  bubbling from the drop handler), and the Responsibility panel's template loader gains its missing
  `.catch` (dropdown now says "Templates unavailable" instead of silently staying empty).
- Verified: typecheck + eslint + full vitest (88) + production build all green.

## v0.3.414 — SEC-TENANT: portfolio roll-ups scoped to the caller's projects (P0 №1)

- **Security fix** (upgrade-plan P0 №1): the cross-project roll-ups — `/benchmarks/costs`,
  `/benchmarks/response-rates`, `/benchmarks/pull-planning`, `/wip/portfolio`,
  `/contractor-statements/portfolio` — aggregated **every project in the database** while gating only on
  authentication. In a shared/multi-tenant deployment, any signed-in user could read every other tenant's
  job P&L, WIP cash positions and per-cost-code actuals. Each now takes the caller's
  `member_project_ids` (the `fca_portfolio` pattern) and the engines filter `project_id IN (…)`; RBAC-off
  dev and the admin api-key keep the unrestricted view.
- Also: the `/projects/{pid}/search` `limit` is clamped to 200 (was unbounded — an oversized SQL LIMIT
  fanned out per module), and `list_attachments` gains an explicit `project_id` predicate
  (defense-in-depth; the download route's membership check already guarded the bytes).
- **New `test_tenant_scoping.py`**: two tenants with distinct financial fingerprints under RBAC — each
  caller's portfolio/benchmarks contain ONLY their member project (admin sees both); limit clamp
  asserted. Wired into the gate; benchmarking / wip / portfolio / route-authz / pull-plan / attachments
  suites all green.

## v0.3.413 — docs & repo surface refresh + the 2026-07-17 upgrade plan

- Output of a four-lane audit (backend scan · web scan · docs/repo review · 2026 industry research):
  - **README** — the stale "current" marker (v0.3.341–371) replaced with a v0.3.372–412 summary
    (analytical chain incl. drift screen, MEP-SIZE/VIEW-RANGE/COVER-SHEET/EXPORT/TAKEOFF-2D, MODEL-DIFF /
    IFC-QA model-QA teeth, the dev-velocity program); clone-path case fix.
  - **Neutral wording** — third-party product comparisons removed from README/guide/index/status per the
    docs policy (drawing inference is now described by behavior).
  - **Status pages** — `docs/status.html` version badge is now the live release shield (was hard-coded
    v0.3.308/371); `docs/status.md` banner marks it a superseded point-in-time snapshot.
  - **Roadmap coherence** — intro updated to v0.3.412; the shipped v0.3.398–412 work archived into
    `roadmap-completed.md` (was stranded in the open file); "Current focus" rewritten now that the
    modularization program is complete.
  - **🎯 The upgrade plan** — a prioritized, research-cited plan added to `docs/roadmap.md`: P0 bugs &
    security (tenant-scoped portfolio rollups, settings-parse boot guard, production-guard breadth, MCP
    authz) → P1 reliability/perf (SSE resilience, listener/GPU leaks, sidecar-index race, UTC dates) →
    P2 docs/demo/surfacing → P3 2026 capabilities (Monte Carlo schedule risk, LEED v5/Buy Clean embodied
    carbon via EC3, permit pre-check, agentic drawing QA, robotic layout export, 5D element binding).
  - **Repo hygiene** — issue templates (bug/feature + Discussions/security links), a PR template
    mirroring the CONTRIBUTING gates, and a root `package.json` description that reflects the whole
    platform (authoring + docs + GC portal + proforma), not just a viewer.

## v0.3.412 — REL-3: split the enclosure recipes out of edit.py (façade) — edit.py under 800

- Fifth and final recipe-group split: the **enclosure/finish group** moves to a new leaf
  **`edit_enclosure.py`** — ceiling/floor coverings (`add_covering`), railings along a run
  (`add_railing`), footprint roofs (`add_roof`), and the wall-hosted opening + parametric door/window
  fill (`add_opening`: IfcRelVoidsElement + IfcRelFillsElement with the LOD-350 lining/panel generators).
- **`edit.py` 2127 → 761 across the six slices (−64%)** — what remains is the genuine engine core:
  spaces/types/query, placement, content, storeys, copy/move/rotate/delete, and the RECIPES registry +
  `apply_recipe`. Each recipe family (structural, MEP, enclosure, annotation, as-built) is now an
  independently evolvable leaf on the `edit_core` foundation, all behind the unchanged `edit.` façade.
- Verified: openings / curtain-wall / wave11-edges / representations suites + the cycle guard (**0
  cycles**, 336 modules), `ruff` clean.

## v0.3.411 — REL-3: split the 2D annotation recipes out of edit.py (façade)

- Fourth recipe-group split: the **drawing-annotation group** moves to a new leaf **`edit_annotate.py`**
  — text notes (`add_annotation`), dimension lines with computed labels (`add_dimension`), scalloped
  revision clouds with rev tags (`add_revision_cloud`), and element-aware tags (`add_tag`) — all authored
  as IfcAnnotation in the 2D Annotation subcontext so they render on the generated plans.
- Built on `edit_core` (annotation context / element-mark / storey lookup); `edit.py` re-exports every
  name. **`edit.py` 2127 → 911 across the five slices** — under 1000 lines for the first time; what
  remains is the engine core (spaces/types/query, placement, openings/coverings, RECIPES + apply_recipe).
- Verified: annotation + drawing suites (author-to-sheet loop intact), cycle guard **0 cycles** (335
  modules), `ruff` clean.

## v0.3.410 — REL-3: split the structural authoring recipes out of edit.py (façade)

- Third recipe-group split on the `edit_core` foundation: the **structural/enclosure group** moves to a
  new leaf **`edit_struct.py`** — sloped walls (`set_wall_slope`), extruded walls/slabs (`add_wall` /
  `add_slab`), concrete columns/beams, steel W-shapes (`add_steel_column` / `add_steel_beam` +
  `_tag_section`, via the `steel` catalog imported lazily), rebar runs and spread footings.
- Built entirely on `edit_core` primitives; `edit.py` re-exports every name (routers, RECIPES, tests,
  generators unchanged). **`edit.py` 2127 → 1103 across the four slices** — the worst file in the tree cut
  nearly in half, with each recipe group now an independently evolvable leaf.
- Verified across 9 suites (structural / wall-slope / steel-connections / rebar / struct-solve /
  wall-analytical / lateral / grid + the cycle guard: **0 cycles**, 334 modules), `ruff` clean.

## v0.3.409 — REL-3: split the MEP authoring recipes out of edit.py (façade)

- Second recipe-group split on the `edit_core` foundation — and the biggest: the **MEP group** (416
  lines) moves to a new leaf **`edit_mep.py`** — system assignment + predefined types
  (`set_system_predefined`), sized risers/runs (`add_riser` / `add_mep_run`), fittings with port counts
  (`add_mep_fitting`), terminals, fire / fire-alarm / comms devices, and the element-connection graph
  (`connect_mep` / `connect_elements` / `element_connections`).
- Built entirely on the `edit_core` primitives (contexts / profiles / storey lookup) — never on another
  recipe; all vendor-util imports were already function-local. `edit.py` re-exports every name (routers,
  RECIPES, nodegraph unchanged). **`edit.py` 2127 → 1378 across the three slices** (core → as-built → MEP).
- Verified across 7 suites (mep / mep-systems / mep-sizing / mep-families / element-connections /
  nodegraph + the cycle guard: **0 cycles**, 333 modules), `ruff` clean.

## v0.3.408 — REL-3: split the as-built / phase record writers out of edit.py (façade)

- First recipe-group split enabled by the `edit_core` foundation (v0.3.406). The element **record**
  writers — W10-8 phasing (`set_phase` / `phase_summary`), G1 field-verified as-built (`verify_asbuilt` /
  `asbuilt_summary`), G2 as-built dimensions (`record_asbuilt_dimension`), G3 manufacturer/serial
  (`set_manufacturer_info`), plus `set_element_pset` / `set_classification` / `_coerce` — move to a new
  leaf **`edit_asbuilt.py`**: no geometry, no placement, just GUID-keyed Pset/classification stamps (the
  LOD-500 reliability layer). Depends only on `edit_core._element` + ifcopenshell.api.
- `edit.py` re-exports every name, so the importers that reach these via `edit` (scene, ebc, detailing,
  the RECIPES registry) are unchanged. `edit.py` 2005 → 1781 (from the original 2127).
- Verified across 8 suites (phasing / lod500 / detailing / content / scene / ebc / verified-progress +
  the cycle guard: **0 cycles**, 332 modules), `ruff` clean.

## v0.3.407 — REL-3: split the raw vendor HTTP clients out of connectors.py (façade)

- Completes the `connectors.py` decomposition. The **outbound I/O half** — the raw Procore / Autodesk
  Construction Cloud / QuickBooks Online / generic-ERP REST clients (urllib GET/PATCH, token in → parsed
  JSON out) — moves to a new pure leaf **`connectors_vendors.py`** (json + urllib only; no DB, no app
  imports, no dispatch logic).
- The **overridable test seams** (`procore_rfis = …`, `acc_projects = …`, `qb_accounts = …`, `erp_read =
  …`) deliberately **stay on `connectors.py`** — tests monkeypatch them there
  (`connectors.acc_projects = fake`) and the per-vendor test/info dispatchers resolve them there, so the
  patchability contract is byte-for-byte unchanged. `connectors.py` 411 → 325 (from the original 495).
- Verified: `test_connections` green end-to-end (Procore two-way sync, ACC/QuickBooks/ERP reads — all
  through the monkeypatched seams), import-cycle guard **0 cycles** (331 modules), `ruff` clean.

## v0.3.406 — REL-3: extract the edit.py authoring primitives into a foundation leaf

- Foundation-first slice on the biggest file in the tree — `data/edit.py` (2127 lines), the GUID-stable IFC
  authoring engine. The nine low-level primitives every recipe builds on — context/profile/mesh/lookup
  helpers (`_body_context`, `_rect_profile`, `_first_storey`, `_box_mesh`, `_annotation_context`,
  `_element_mark`, `_wall_thickness`, `_fill_representation`, `_element`) — move to a new pure leaf
  **`edit_core.py`** that depends only on ifcopenshell, never on a recipe.
- `edit.py` re-exports every name, so the sibling authoring modules that already reach in for these
  (`connections`, `curtainwall`, `families` do `from .edit import _body_context …`) are unchanged.
  `edit.py` 2127 → 2005. The leaf imports nothing back, so no cycle (guard confirms 0 across 330 modules).
- This unblocks splitting the recipe *groups* (MEP, structural, as-built) off later — they can import the
  primitives from `edit_core` instead of dragging in the whole engine. Verified across 10 authoring tests
  (annotation / openings / mesh / content / curtain-wall / family-library / connections / detailing /
  edit-undo), `ruff` clean.

## v0.3.405 — REL-3: split the sheet renderers out of data/drawings.py (façade)

- Next façade extraction. The **paper-output half** of `data/drawings.py` — `render_sheet_svg` /
  `render_sheet_pdf` (turn a composed `layout` dict into an SVG string / PDF byte-stream) plus the shared
  `_dim_h` / `_dim_v` dimension primitives — moves to a new pure leaf **`drawings_render.py`** that imports
  no ifcopenshell / geometry / model code (just `layout`/`meta` dicts + reportlab in the PDF path).
- `drawings.py` re-imports all four (used internally: the renderers in `sheet()`, the dim primitives in the
  plan generator), so `drawings.render_sheet_svg` / `render_sheet_pdf` callers are unchanged. `drawings.py`
  941 → 788. The leaf imports nothing back from `drawings.py`, so no cycle.
- Verified: `test_sheetgen` / `test_pdfops` / `test_issuance` / `test_drawing` / `test_sections` green
  (sheets render through the façade), the import-cycle guard confirms **0 new cycles** (329 modules), `ruff`
  clean.

## v0.3.404 — REL-3: split the pure Procore field-mapping out of connectors.py (façade)

- First façade extraction since the cycle guards landed (which now catch any regression). The **pure
  data-transform half** of `connectors.py` — the dotted-path reader, default/override field maps, and the
  Procore payload↔record mappers — moves to a new pure leaf **`connectors_mappings.py`** (no network, no
  DB, no app imports). `connectors.py` re-exports every name, so callers of `connectors.map_procore` /
  `connectors.DEFAULT_MAPPINGS` are unchanged (zero public-API change). `connectors.py` 495 → 411.
- Verified: `test_connections` green (Procore→rfi/submittal/change_event sync through the façade), the
  import-cycle guard confirms **no new cycle** (328 modules, still 0), `ruff` clean.

## v0.3.403 — DEV-2 (web): runtime import-cycle guard for the viewer/portal

- Completes the DEV-2 import-cycle guard on the **web** side, mirroring the backend one — as a vitest test
  (`src/no-import-cycles.test.ts`), so it runs in the existing web CI job with **no new dependency** (no
  eslint-plugin-import, avoiding the pinned-eslint/Node-20 fragility).
- Asserts **no *runtime* circular imports** among the app's own modules via Tarjan SCC over the top-level
  import graph. `import type` / `export type` are excluded because tsc erases them — the portal's only
  "cycle" is exactly that PanelContext ⇄ PortalHost *type* seam, which emits no runtime import. Today:
  **0 runtime cycles across 92 modules / 162 runtime edges**; a genuine load-time cycle now fails the build
  with the exact path. Includes a self-test asserting the SCC detector catches a synthetic cycle.

## v0.3.402 — DEV-2: import-cycle guard (lock in the REL-3 façade layering)

- The REL-3 modularization repeatedly stalled on *false-positive* circular-import reports (imports that are
  actually function-local / deferred). New **`test_import_cycles.py`** locks in the real invariant: **no
  circular imports at module top level** across the first-party packages (`aec_api` + `aec_data`) —
  the kind that breaks at import time and blocks a clean façade extraction.
- Pure stdlib `ast` (no third-party linter added), runs inside the fast parallel gate. Builds the
  top-level import graph over all 327 first-party modules and fails loudly on any strongly-connected
  component (Tarjan SCC) — function-local/deferred imports are correctly ignored since they don't cycle at
  import time. Today: **0 cycles across 704 intra-package edges**; a regression now fails CI with the exact
  cycle path.

## v0.3.401 — IFC-QA: export round-trip fidelity check (does the export drop anything?)

- The #1 openBIM complaint is **silent loss on export** — entities dropped, GlobalIds churned, property
  sets lost when a model is serialized or pushed through a bridge. New `roundtrip_qa` engine catches it:
  - **`fingerprint(model)`** — a comparable summary of the invariants that must survive an exchange: IFC
    schema, project units, entity counts by class, the full GlobalId set, storey list, and the element
    property/quantity payload size.
  - **`compare(before, after)`** — diffs two opened models and returns two verdicts: **`identical`** (exact
    match — the target for a plain re-serialization) and **`lossless`** (nothing *dropped*: after ⊇ before,
    the bar a legitimate transform must clear), with per-dimension deltas and offender GUID samples.
  - **`roundtrip(model)`** — writes the model out to a temp IFC and reopens it, then compares — a pure
    serialization-fidelity check of the write path the edit recipes use to republish.
  - Exposed at `GET /projects/{pid}/models/export-qa` (409 without a source IFC). Pure + guarded; a
    write/reopen failure is itself reported as a fidelity failure rather than a 500.
- Test coverage: clean write→reopen is `identical`; a dropped wall is caught as EXPORT LOSS (GUID removed
  + IfcWall delta −1); a superset target reads lossless-but-not-identical.

## v0.3.400 — DRIFT: preliminary story-drift screen + torsional-irregularity flag (ASCE 7 §12.12 / §12.3.2.1)

- The lateral engine computed seismic ELF + wind base shear distributed to story forces, but had **no
  drift or torsion check** — the two limit states that most often govern a lateral system. Added, as an
  honest preliminary screen on top of the existing ELF story shears:
  - **`drift_check`** — the ASCE 7-22 §12.12.1 **allowable story drift** `Δa = coeff·hsx` per story (Table
    12.12-1, by Risk Category: 0.020 / 0.015 / 0.010 for I–II / III / IV). When a **story stiffness**
    (kip/in) or a **target elastic drift ratio** is supplied, it also computes the amplified **design
    drift** `Δ = Cd·δxe / Ie` (§12.8.6) and returns pass/fail per story plus the worst drift ratio.
  - **`torsional_check`** — the §12.3.2.1 horizontal-irregularity classifier from the two-end diaphragm
    displacements: `δmax/δavg` → **Type 1a** (> 1.2) / **Type 1b extreme** (> 1.4), with the §12.8.4.3
    accidental-torsion amplification `Ax = (δmax / 1.2·δavg)²` (capped at 3.0).
  - Wired into `lateral_from_model` (the Δa envelope is always emitted; demand + torsion when inputs are
    given) and the `GET …/structure/lateral` endpoint (`risk_category`, `cd`, `elastic_drift_ratio`).
- Still preliminary — real drift needs a member-stiffness model; every result carries the not-a-PE
  disclaimer. Hand-computed test coverage in `test_lateral.py`.

## v0.3.399 — FIN-TEST: lock in the untested lease + change-order money math

- Quality / debug pass from the codebase gap sweep. Two read-side money-computation engines had **no
  dedicated test** asserting their math — where a silent compounding/rounding/recovery bug is consequential.
  Now covered with hand-computed expectations:
  - **`test_leasemgmt.py`** — rent **escalation compounding** (`base·(1+esc)^y`, verified to 5-year), the
    portfolio-by-year sum (active-only), **CAM/expense recovery** (`psf×sf`, recovery ratio, over/under-
    recovery vs the opex pool, zero-pool guard), and **renewal at-risk rent** (expiry bucketing, holdover);
    plus empty/malformed-input robustness.
  - **`test_changeorders.py`** — the CO value pipeline by state (pending / approved / executed / rejected),
    **schedule-day exposure excluding rejected**, ball-in-court mapping, reason mix, and open-only
    change-event ROM exposure.
- The math was **already correct** — no product change; this is regression protection for the developer-
  finance surface. Both wired into the test gate.

## v0.3.398 — MODEL-DIFF: element-level revision diff (what actually changed)

- New capability from a codebase gap sweep. Model version diff previously compared only the GUID **set**
  (added / removed); a moved, resized, re-typed, re-leveled, or re-priced element on a GUID present in both
  revisions read as *"unchanged."* Now each version snapshot stores a per-element **fingerprint** (name ·
  IFC class · type · level · Pset-hash · Qto-hash), so `versions.diff` reports **modified** elements *and
  what changed* — `renamed` · `reclassified` · `retyped` · `moved to another level` · `properties changed`
  · `quantities changed`. The "what changed between Rev C and Rev D" coordination answer, made real by the
  GUID-stable model.
- `GET …/versions/diff` gains `modified[]` (guid · class · name · change labels), `modified_count`, and
  `modified_available` (older versions without fingerprints degrade to added/removed only). The viewer's
  **Version history** shows `+added / −removed / ~modified` and a click-to-select-in-3D list of the modified
  elements with their change labels. `ModelVersion.fingerprints` auto-migrates via `_ensure_columns`.
- Scope: pure rigid geometry *moves* aren't caught (geometry streams as Fragments, not the property index) —
  but a **resize surfaces via its Qto delta**, and all property/type/level/name/cost changes are detected.

## v0.3.397 — REL-3: extract the module registry foundation (modules_registry.py)

- Fourth modularization slice — the **foundation** extraction that unblocks all further `modules.py` splits.
  The registry + table base (the `module.json` REGISTRY, the per-module SQLAlchemy TABLES, the reverse-
  reference index, the field-type selectors, and the `_table` factory / `load_registry` / `get_module`)
  moves to **`modules_registry.py`** — a leaf that imports only `db.Base` + stdlib/sqlalchemy, nothing from
  `modules.py`. Now `modules.py`, `modules_search.py`, and any future `modules_*` layer can share the base
  without a cycle. The mutable globals are mutated in place (never reassigned), so every importer shares the
  one dict object; `modules.py` re-exports the names so `modules.get_module` / `.TABLES` / `.load_registry`
  are unchanged. `modules.py` 969→882.
- Zero behaviour change. Verified: module/schema/config/FTS/traceability/dashboard/imports tests green + the
  **full suite** (this is the app-wide-core engine), ruff clean, all consumers import.

## v0.3.396 — REL-3: extract computed schedules into a pure leaf (drawing_schedules.py)

- Third modularization slice. `data/drawing.py` (941 lines — footprint plans / sheets / PDF / schedules)
  had the **computed door/window/room schedules** (`schedules` / `schedule_csv` / `schedule_svg`) inline.
  They move to **`drawing_schedules.py`** as a **pure leaf** — they read values straight off the model
  elements with no dependency on the plan/section geometry helpers, so it imports nothing from `drawing.py`
  (no cycle). `drawing.py` imports `schedules` for its PDF path and re-exports the three public functions,
  so `drawing.schedules` / `.schedule_csv` / `.schedule_svg` are unchanged. `drawing.py` 941→821.
- Zero behaviour change. Verified: drawing / sections / sheetgen / drawing-set / project-package tests green,
  ruff clean, all consumers import.

## v0.3.395 — REL-3: extract module full-text search into a pure leaf (modules_search.py)

- Second modularization slice, on the biggest backend file. `modules.py` (1009 lines, the config-module
  engine) had its Postgres full-text-search infrastructure (`_is_postgres` / `_pg_tsquery` / `_pg_document` /
  the `LIKE`↔`to_tsvector` search predicate / the GIN-index DDL) inline. It moves to **`modules_search.py`**
  as a **pure leaf** — every function takes the SQLAlchemy `Table` as an argument (dependency injection), so
  it imports nothing from `modules.py` (no cycle). `modules.py` keeps the `fts_index_ddl(key)` /
  `ensure_fts_indexes(engine)` orchestration (which knows the `TABLES` registry) as thin injecting wrappers,
  and re-exports the query helpers so `modules._pg_document` / `modules._pg_tsquery` keep working.
- Zero behaviour change (search + index DDL identical). Verified: search/module tests green
  (fts-index / search-alerts / modules / module-schema / module-config / imports / distribution), full suite
  green, ruff clean, all consumers import. Also made `test_distribution` parallel-safe (stale-lock-tolerant).

## v0.3.394 — REL-3: modularize codecheck (egress engine → its own module, façade)

- First modularization slice. `codecheck.py` (502 lines) mixed two fully-decoupled domains — the free-text
  code-check assistant and the **computed occupancy-load + egress-capacity analysis** (W9-2). The egress
  half (~330 lines) moves to **`codecheck_egress.py`**; `codecheck.py` (now 184 lines) **re-exports** its
  public functions (`egress_analysis`/`code_analysis`/`approvability`/`egress_from_model`) as a façade, so
  every caller (`codecheck.approvability`, …) is **unchanged**. Zero behaviour change — pure structure.
- Verified: all codecheck-dependent tests green (codecheck / code_analysis / codes / approvability /
  rfi-readiness / readiness-bcf / ebc / model-health), ruff clean, all consumers import.

## v0.3.393 — DEV-1: parallel test gate (~30 min → ~11 min) + geometry worker cap

- **Dev-velocity, not a product change.** The API test gate (`run_tests.py`) ran ~180 self-contained
  `test_*.py` **sequentially** (~30 min) — the release bottleneck. It now runs them through a bounded
  `ThreadPoolExecutor` (each test is already an isolated subprocess with its own SQLite db + storage dir).
  `TEST_JOBS` overrides the worker count; `TEST_JOBS=1` restores sequential for debugging.
- **Geometry worker cap** — each geometry pass (`bake`/clash/export/edit) ran ifcopenshell's iterator across
  `cpu_count()-1` processes; under the parallel gate that oversubscribed the CPU (cpu × cpu). A new
  `aec_data.geomconf.geom_workers()` reads **`AEC_GEOM_WORKERS`** (the runner sets `=1`) so each test is
  single-threaded and the outer parallelism owns the cores. **Production default is unchanged** (`cpu-1`).
- Net: the full suite drops from **~30 min to ~11 min (2.7×)**, 250/250 green. Also fixed the runner's
  cp1252 output-capture (now `PYTHONUTF8=1` + utf-8 decode — no more spurious unicode-encode failures) and
  made `test_collab` tolerant of a stale locked db so the parallel run is deterministic.

## v0.3.392 — Analytical supports: fix the base nodes → a solvable model

- Completes the analytical model: the **`apply_structural_supports`** recipe fixes the **base**
  (lowest-elevation) analytical nodes as `IfcBoundaryNodeCondition` supports — **pinned** (translations
  fixed, rotations free) or **fixed** (all six DOF) — so the model is **statically stable and fully
  solvable** (members + loads + supports = a complete analytical model a solver can run).
- Idempotent (re-applying doesn't accumulate conditions), cleared by a re-derive, reported by `summary()`
  as `supports`. The viewer analytical panel gains an **"Add base supports (pinned)"** action and shows the
  support count; the analytical model reads **"solver-ready"** once it has both member loads and supports.

## v0.3.391 — Analytical shear walls: load-bearing walls → vertical surface members

- Completes the W10-7 analytical geometry. `derive_analytical` now idealises each **load-bearing (shear)
  wall** into a vertical `IfcStructuralSurfaceMember` at its mid-plane (a length×height `IfcFaceSurface`
  spanning the wall height), alongside the existing slab surface members. Non-bearing **partitions are
  skipped** (read from `Pset_WallCommon.LoadBearing`), so the analytical model carries the real lateral-
  force-resisting elements, not every wall.
- Idempotent (the `wall_surface_members` count is stable across a re-derive) and cleaned by the analytical
  purge; the derive result + `summary()` report the counts. Pure ifcopenshell topology — no geometry kernel.

## v0.3.390 — STRUCT-LOADS-IFC: write member load actions → a solver-ready analytical model

- The analytical model carried only a self-weight load *case*. The new **`apply_structural_loads`** recipe
  writes a real gravity line load onto **every analytical curve member** as an `IfcStructuralLinearAction`
  (applied `IfcStructuralLoadLinearForce`, global −Z at `(D+L) × 14593.9 N/m`), grouped under the analysis
  model's load group — so the analytical IFC is now **loaded and solver-ready**: SAP2000 / RISA / Robot
  import the actions with the geometry, not just bare members.
- Idempotent (re-applying refreshes the value; counts never accumulate) and cleaned by a re-derive (the
  analytical purge now removes load actions + applied loads with no orphans). `summary()` reports
  `load_actions`; the viewer analytical panel shows the solver-ready count + a **"Write member loads"**
  action. **Preliminary — service D+L only; final loads/combos are the engineer's.**

## v0.3.389 — STRUCT-LATERAL: ASCE 7 wind + seismic base shear → story forces

- The lateral complement to the gravity solve. **`GET /projects/{pid}/structure/lateral`** runs the two
  hand analyses an engineer does before sizing a lateral system:
  - **Seismic — Equivalent Lateral Force (ASCE 7-22 §12.8):** `Cs = SDS/(R/Ie)` with the §12.8-3 upper
    bound + §12.8-5 floor, base shear `V = Cs·W`, vertical distribution `Fx = Cvx·V` (k from the
    approximate period `Ta = Ct·hn^x`), story shears + overturning.
  - **Wind — simplified directional MWFRS (Ch. 26–27):** velocity pressure `qz = 0.00256·Kz·Kzt·Kd·Ke·V²`
    (Kz by the exposure power law), net windward+leeward pressure → story forces, base shear + overturning.
  - The **governing** case is flagged; story weights estimated from floor area × a dead-load psf.
- **Viewer** — the Structural analytical panel gains a **"Lateral (wind + seismic base shear)"** action:
  governing case, both base shears, and the per-story force/shear table.
- Pure ASCE 7 arithmetic (hand-verified in tests). **Preliminary — not a full lateral design (no torsion,
  modal/response-spectrum, drift, or P-delta); must be stamped by a licensed professional engineer.**

## v0.3.388 — TAKEOFF-2D: quantity takeoff from a drawing → the 5D estimate

- The **drawings-only takeoff** the model takeoff misses. Upload a PDF-page image / scan, **calibrate the
  scale** (click two points at a known real distance), then trace regions — click polygon vertices or
  **one-click flood-fill** inside an enclosed area — and each region is measured + priced by assembly.
- **`POST /projects/{pid}/takeoff/2d`** — the deterministic measurement + pricing core: shoelace area /
  polyline length in pixels × the calibration → real m² / m, priced at per-assembly benchmark rates
  (floor slab · roofing · partitions · curtain wall · paving · linear walls/footings …), overridable per
  project vintage; returns per-region rows + per-assembly rollups + total, feeding the same 5D estimate.
- Viewer: a **📐 2D Takeoff** overlay (upload · calibrate · trace/flood-fill · quantify) in the turnover
  group. Preliminary — accuracy is trace/scale dependent; verify against the model takeoff where a model
  exists. (The measurement/pricing core is unit-tested; the canvas tracer is build-verified.)

## v0.3.387 — EXPORT: binary glTF (.glb) + first-class IFC re-export

- **`GET …/model/export.glb`** — the model geometry now exports as a **binary glTF (.glb)** — the compact
  single-file form Blender / three.js / game engines import directly — alongside the existing JSON `.gltf`.
  Same per-class meshes + colours; proper glTF-2.0 container (`glTF`/v2 header · 4-byte-padded JSON chunk ·
  `BIN` chunk). Tessellation runs off the event loop.
- **`GET …/model/export.ifc`** — a **first-class IFC re-export**: stream the project's current authored
  source IFC (edits republish it in place, so this is the live GUID-stable model) directly, not only inside
  the closeout bundle zip — the openBIM source of truth a coordinator can round-trip through any tool.
- **Viewer** — the Document/turnover group gains **Export IFC**, **Export 3D (.glb)**, and **Export 3D
  (.gltf)** actions beside the closeout package. (DWG + USD remain deferred — proprietary/heavy-dependency;
  the on-mission interchange path is IFC + glTF.)

## v0.3.386 — MEP-SIZE: velocity size checks elevate MEP from modeled to engineered

- **`GET /projects/{pid}/mep/sizing`** — over every authored MEP run carrying a design size + flow
  (`Pset_Massing_MEPSizing`), computes the **flow velocity** and checks it against accepted limits, pass/
  fail like the IBC checks: **air** `V = Q/A` vs the ASHRAE low-velocity commercial limit (~2500 fpm),
  **water** `V = 0.408·Q/d²` vs the erosion/noise limit (~8 ft/s), and **cable-tray** NEC 392 fill (≤ 50%,
  reported when a fill ratio is supplied). Undersized/over-driven runs are flagged with the fix ("increase
  the duct/pipe"); runs with no design flow return info. Limits are overridable per call.
- **Viewer** — the MEP system browser gains a **"MEP size check (velocity)"** action: pass/fail counts, a
  per-run table, an "isolate undersized runs in 3D" control, and the not-a-PE disclaimer.
- Physics only (velocity relations + limit values are facts — no license issue). **Preliminary — not a
  full hydraulic/thermal design (no pressure-loss balancing, diversity, or acoustics); all final MEP sizing
  must be stamped by a licensed professional engineer.**

## v0.3.385 — DISC-SSOT: sheet-series derives from the one discipline map

- Internal consolidation. Sheet-series (which drawing series a class belongs to — S/A/M/E/P/FP/FA/T…) was
  hand-maintained in **two** places (`sheetgen._CLASS_SERIES`, plus the cover's own series→name table)
  that could silently drift from the canonical discipline map. Series is now a **derived view** of the
  discipline map: `classification.series_of_ifc_class()` refines `discipline_of_ifc_class` only where a
  *distinct* series exists (fire-suppression → FP, fire-alarm → FA), and `sheetgen.detect_series` + the
  drawing-set cover both derive from it. Verified to reproduce the former hand-kept map **exactly** — no
  behaviour change, one source of truth.
- **Takt trade** (`fourd.TRADE_FOR_CLASS`) is documented as a deliberately separate build-sequence axis
  (a wall's trade is *Envelope*, its discipline *Architectural*), not folded into discipline/series.

## v0.3.384 — COVER-SHEET: rendered cover + discipline-grouped drawing index

- The compiled drawing set's cover was a flat text list. It is now a proper **cover sheet**: a title block
  with the project name, subtitle, **issue date**, and sheet count; a **key-plan thumbnail rendered from
  the model** (the ground-plan footprint, real linework — not text); and a **drawing index grouped by NCS
  discipline** (General · Civil · Structural · Architectural · Fire Protection · Fire Alarm · Plumbing ·
  Mechanical · Electrical · Telecom …) with section headers, bound in the same order a set is issued.
- The index **paginates** — a large multi-discipline set flows onto continuation pages instead of
  truncating at the page bottom (the old cover silently dropped sheets past the first ~90). Backward-
  compatible: short sets still produce a single cover page, so `/drawing-set/compiled.pdf`,
  `/project-package.pdf`, and the issuance flow are unchanged in page count for typical models.

## v0.3.383 — VIEW-RANGE: plan view-depth so foundations show below the cut

- **`GET /projects/{pid}/drawings/plan.svg?view_depth=<m>`** — a plan is no longer a single horizontal
  cut plane. Pass a **view depth** (metres below the cut) and the plan additionally draws the **footprint
  of anything under the cut but within that depth** — foundations / footings / pile caps that a single
  cut plane never intersects — as **dashed light hidden lines**, with a "below cut (view depth)" legend.
  This is the Revit **Top / Cut / Bottom / View-Depth** model rather than one `cut_z`.
- Each below-cut element is sectioned through its own mid-height for a representative outline; the below
  linework shares the plan extent (so it is never clipped) and the class filter scopes it. The cut
  linework, dimensions, room tags, callouts, and titleblock cut-AFF are unchanged when `view_depth` is
  omitted — fully backward-compatible.

## v0.3.382 — STRUCT-SOLVE: apply gravity loads + solve statics on the analytical frame

- **`GET /projects/{pid}/structure/solve`** — closes the biggest analysis gap: the W10-7 analytical model
  carried only self-weight and the ASCE 7 load engine sat isolated. This **applies a gravity load case**
  (dead + live by occupancy) to the analytical curve members and runs a **determinate, member-by-member
  statics solve** — each horizontal member as a simply-supported beam under a uniform line load:
  end **reactions** (`wL/2`), max **shear** (`wL/2`), max **moment** (`wL²/8`), an indicative
  **deflection** vs the L/360 limit, and sampled **shear / moment / deflection diagrams**; vertical
  members carry a tributary **column axial** (from the gravity takedown). Factored member forces use the
  governing ASCE 7 LRFD combination. The beam line load is taken directly (kip/ft) or derived from floor
  pressures over a tributary strip; occupancy live loads come from the ASCE 7 table.
- **Viewer** — the Structural analytical panel gains an **"Apply loads + solve statics"** action: the
  load case, the governing beam (reaction · Vmax · Mmax · deflection check), inline shear + moment
  diagrams, and the column axial, each with the not-a-PE disclaimer.
- **Honest scope:** every member is solved in isolation as a determinate element (the hand-check before
  sizing) — **not** a coupled stiffness (FEM) frame analysis, no lateral (wind/seismic) member solve,
  deflection indicative (assumed E·I). Read-only; nothing is written back to the IFC. Preliminary only —
  all sizing and final design must be performed and stamped by a licensed professional engineer.

## v0.3.381 — PREFLIGHT: one-click "ready to issue?" gate

- **`GET /projects/{pid}/preflight`** — a single **PASS / HOLD** verdict + a pre-issue checklist, the
  pyRevit "run the pre-flight before you publish" moment. Composes the shipped model-health lenses
  (hygiene · clash coordination · code/permit readiness · verified-as-built), adds the one missing lens —
  **discipline-classification completeness** (elements that don't map to the tree can't be scheduled /
  priced / drawn by discipline) — and folds in **open high-priority issues** as a hard blocker. Checklist
  is ordered blockers → warnings → passes; each item carries a status, detail, and (where relevant) the
  offending GUIDs. Reuses the existing engines — no duplicate logic.

## v0.3.380 — KEYS: Revit-style keyboard shortcuts for drawing

- Type a **2-letter code** (no modifier) in the viewer to arm a draw tool, Revit-style, then click to
  place — **WA** wall · **CL** column · **BM** beam · **SL** slab · **RF** roof · **RA** railing · **SC**
  steel column · **SB** steel beam · **RB** rebar · **FT** footing · **DU** duct · **PI** pipe · **CT**
  cable tray · **WR** wire. **Esc** disarms; **?** shows the shortcut list. A small HUD echoes the code as
  you type. Shortcuts are suppressed while typing in any input/textarea, so text fields are unaffected.
  Makes Revit-trained users productive without hunting the tool rail.

## v0.3.379 — fix 3 CodeQL ReDoS alerts (codecheck free-text parser)

- Cleared the 3 open **`py/polynomial-redos` (HIGH)** CodeQL alerts in `codecheck._detect` — the free-text
  code-description scanner used unbounded quantifiers (`[\d,]+`, `\d+`, `\s*`) under `re.search`, which
  re-scans and is polynomial-time on a crafted long string. Bounded the quantifiers (`{1,n}`) and capped
  the input to 20 000 chars; a 100 k-digit crafted input now parses in ~40 ms (was the ReDoS vector).
  Detection of area / stories / occupant-load on real inputs is unchanged.

## v0.3.377 — shareable project package (show someone the whole project)

- **`GET /projects/{pid}/project-package.pdf`** — one bound PDF a GC or architect hands to a client: a
  **cover / contents**, a **visual overview** (plan · section · elevation composed on one sheet), the
  **compiled drawing set**, and a **cost & feasibility** summary (the model-takeoff estimate by discipline
  + the developer budget's capital stack — hard / soft / debt / equity). `…/project-package/contents`
  pre-flights what's available. Composes the existing drawing, estimate, and proforma engines — the
  "show someone the design, drawings, cost, and proforma" deliverable that had no single home before.

## v0.3.376 — model estimate → developer proforma (5D→underwriting)

- **`POST /projects/{pid}/dev-budget/sync-from-model`** ties the developer underwriting to the **real
  model takeoff** instead of a flat `GFA × $/sf` assumption. One click runs the IFC quantity estimate
  (priced through the project's pinned cost vintage) and replaces the budget's **hard** cost with
  **per-discipline** "model takeoff" lines (S/A/M/E/P/…) that reconcile to the estimate total; soft /
  acquisition / contingency are untouched. Closes the ★5 gap where the proforma and the model quantities
  were two disconnected worlds — the deal number now flows from the design.

## v0.3.375 — compiled drawing-set PDF (the whole set, one file)

- **`GET /projects/{pid}/drawing-set/compiled.pdf`** — the whole drawing set bound into **one multi-page
  PDF**: a cover / sheet-index, a floor plan per storey (A-1xx), and the door/window/room schedules
  (A-601). Reuses the proven single-sheet renderers and merges with pypdf. A tall tower samples storeys
  evenly (capped by `max_sheets`) so the set stays a reasonable size; schedules toggle off. The single-file
  handover deliverable a GC or architect issues — closes the gap where the platform could render one sheet
  at a time and a transmittal *cover*, but never the bound set. (Verified on the 30-storey Quay tower.)

## v0.3.373 — reliability: openModule O(n·m) fix + import-cycle verification

- **Perf (REL-4):** the portal's `openModule` built its visible columns with a per-column
  `m.fields.find(...)` linear scan — O(colNames × fields). Now an O(1) `Map` lookup built once per open.
- **Import cycles (REL-1/2) verified false positives** — the flagged web-portal cycle
  (`panelContext ↔ portal`) is entirely `import type` (stripped at build, no runtime cycle), and the API
  `db.py` cycle isn't real (`db.py` has no back-edge; `models.py→db.py` is one-way; `distribution.py→
  modules.py` is a deferred function-local import). Documented in the roadmap; no refactor needed.

## v0.3.371 — security hardening pass (audit + fixes)

- **XXE fix (HIGH):** the Primavera P6 XML (PMXML) schedule-import parser now uses **defusedxml**, so a
  malicious upload can't trigger XML external-entity / entity-expansion attacks (verified: a `file://`
  XXE payload is rejected, valid P6 XML still parses).
- **Weak-hash flags cleared (HIGH×3):** the SHA-1 calls in `clash_intel` (clash identity) and
  `model_capabilities` (model signature) are non-crypto fingerprints — marked `usedforsecurity=False`.
- **Dependency CVEs:** pinned `pillow>=12.3.0` (reportlab's transitive image dep — floors over 8 CVEs in
  12.2.x) and added `defusedxml>=0.7` to the data requirements.
- Audit run across ecosystems: `npm audit` 0 vulns (web), `bandit` HIGH findings now **0**, `pip-audit`
  reviewed (remaining setuptools advisories are build-time only), secret scan of the source tree clean.
  Outbound `urlopen` sites are fixed/configured hosts (Procore) or scheme-validated admin webhooks.

## v0.3.370 — UX-1: lifecycle ribbon tabs over the tool rail

- A **ribbon tab-strip** (All · Build · Analyze · Coordinate · Document · Data) at the top of the model
  tool rail filters the accreted tool sections to one lifecycle phase at a time — so the ~7-section,
  ~90-tool rail reads like a Revit-style task ribbon. A thin nav layer over the existing `section()`s
  (matched off each group's title); the active tab persists. Verified live: Build → only the 3 Build
  sections show, the rest hide.

## v0.3.369 — UX-4: Project-Browser spine (views/sheets/schedules)

- The model-browser panel now opens with a **Project browser** nav strip — quick links to *Plans & views*,
  *Sheets*, and *Schedules* (deep-linking the Drawings workspace) above a labelled *Model* element tree —
  so the browser reads as a full project index (à la a Revit Project Browser), not just a class list.

## v0.3.368 — UX-3: Library filter operators + Recent bucket

- The unified **Library** palette gains scoped search operators — `type:` (name/key), `class:` (IFC
  class), `category:`/`cat:`, and `discipline:`/`tag:` (full-text) — combinable with free terms
  (e.g. `class:ifccolumn`, `category:furniture`). And a **Recent** bucket: the last six placed items
  surface at the top of the list (per-project, in localStorage) for quick re-placement.

## v0.3.367 — AUTH-VS: visual node-authoring canvas

- A **visual node-graph editor** (Build → Advanced authoring → *Visual node authoring*) over the
  recipe-graph engine. Drop recipe nodes from a palette (wall / column / beam / slab / base plate /
  curtain wall / derive-analytical), **drag** them around, and **wire** one node's output ● into another's
  input ○ — the wire auto-injects the `{"$from": "<node id>"}` reference into the target's params so the
  upstream GUID threads through. **Run graph** executes the whole thing as one GUID-stable pass
  (`POST /edit/graph`), republishes, and reloads. Plain DOM + one SVG edge layer; no new deps.

## v0.3.366 — viewer: live co-editing (presence + reload banner)

- The viewer now subscribes to the **COLLAB-1 model-edit stream**: the live-presence roster refreshes
  instantly (not just the 20 s poll), and when **another user publishes a new model version** a "a
  collaborator updated the model — Reload" banner appears. Your own publishes never nag (the loaded
  version re-syncs on every model load). The `EventSource` closes on unload.

## v0.3.365 — viewer: Ask-the-model box + structural analytical panel

- The **Analyze & Coordinate** rail section gains two tools that surface the frontier backends:
  - an **Ask the model** box (RFI-0 NL-QA) — type a plain-language question ("what governs this element?",
    "what's blocking approval?") and get a cited answer, with a one-click *isolate the cited elements*.
  - a **Structural analytical model** tool (W10-7) — shows the derived analysis-model summary (curve /
    surface members · nodes · load case) and a *derive/refresh from the physical model* action.

## v0.3.364 — web client: typed bridge to the new engines

- Typed client methods for the frontier backends shipped this cycle, so the app (and future UI) can reach
  them: `docGraph` / `elementSources` (W9-4 cited sources), `rfiQa` (RFI-0 NL-QA), `analyticalSummary`
  (W10-7), `collabSnapshot` + `modelStream` (COLLAB-1 live co-editing, an `EventSource` wrapper), and
  `editGraph` (AUTH-VS recipe-graph). Typecheck + production build green.

## v0.3.363 — AUTH-VS: recipe-graph execution engine

- New **visual node authoring** backend. A *recipe graph* — authoring-recipe nodes wired by data
  dependencies — runs as one GUID-stable pass: `nodegraph.execute_graph` topologically orders the nodes
  (Kahn sort over the edges; array order when unwired) and threads each node's output into downstream
  params via `{"$from": "<node id>", "key"?: "<field>"}` references (a column node's GUID feeds the base
  plate that sits on it). Over the same `RECIPES` registry as the AI command bar — the no-code sibling.
- Served at `POST /projects/{pid}/edit/graph` (body `{graph, publish?, base_source?}`), versioning the IFC
  like `/edit` and honoring the COLLAB-1 optimistic lock. Bad graphs (unknown recipe/id, cycle, dangling
  ref, duplicate id) are rejected 400.

## v0.3.362 — COLLAB-1: optimistic edit-lock (no silent overwrite)

- `POST /projects/{pid}/edit` accepts an optional **`base_source`** — the model signature the client last
  loaded (from `GET .../collab`). If another user has published since, the edit is rejected **409** ("the
  model changed — reload") instead of silently overwriting their work. Backward-compatible: omitting
  `base_source` keeps the prior fire-and-forget behavior.

## v0.3.361 — COLLAB-1: live co-editing awareness (model stream)

- First slice of **real-time multiplayer co-editing**. A project's *model signature* bumps on every
  authoring publish; `GET /projects/{pid}/collab` bundles it with the live presence roster, and
  `GET /projects/{pid}/model/stream` (SSE) re-emits that snapshot whenever the model version **or** the
  set of present users (and where each is looking) changes — so a second open viewer live-reloads the
  geometry after another user's edit and shows who's in the session. Reuses the existing presence + SSE
  primitives; in-model comments already ride the GUID-anchored Topic/Comment model.
- *Next: per-user cursors/selection overlays and optimistic edit-locks (409 on a stale write).*

## v0.3.360 — RFI-0: NL-QA with cited sources

- **Natural-language QA** over the model, grounded in citations — the read/QA sibling of the AI authoring
  command bar, and the payoff of the doc-graph. `POST /projects/{pid}/rfi/qa` with `{question}` routes to
  the right substrate and answers with sourced facts:
  - *"what governs \<element/GUID\>?"* → element provenance (spec section · detail sheet · level),
  - *"what's blocking approval?"* → ranked decision-readiness gaps + fixes,
  - *"what is spec section 05 12 00?"* → the elements it governs,
  - anything else → a model overview pointing at how to ask a sourced question.
- Fully **deterministic** — the cited facts are the answer, so it works with no API key. Every claim
  carries its source (GUID · spec section · document sheet · readiness check).

## v0.3.359 — W9-4: document / specification graph (cited sources)

- New **doc-graph** layer — the cited-source half W9-4 left open. `docgraph.build` folds two node kinds
  onto the model graph: **spec sections** (an element's classification code → the governing MasterFormat/
  UniFormat section) and **documents** (attached detail/cut-sheets with their derived sheet reference),
  each linked to the elements they govern (`specified_by` / `documented_by`). Served at
  `GET /projects/{pid}/doc-graph`.
- `element_sources(guid)` returns one element's **cited provenance** — its spec sections, attached
  documents (with sheet refs), and spatial container, every fact tagged with its source. Served at
  `GET /projects/{pid}/elements/{guid}/sources`. The substrate the RFI-0 NL-QA layer answers from.

## v0.3.358 — W10-7: analytical surface members (slabs)

- `derive_analytical` now idealises **slabs / roof decks** into `IfcStructuralSurfaceMember`s (SHELL): a
  planar `IfcFaceSurface` bounded by an `IfcEdgeLoop` at the deck footprint, thickness carried, linked
  back to the physical slab. Handles both arbitrary-polygon and rectangle slab profiles. The analytical
  model now spans the frame **and** the floor/roof plates; `GET .../analytical` reports `surface_members`.

## v0.3.357 — W10-7: structural analytical model (frame)

- New **structural analytical model** layer alongside the physical (LOD 300) model. `derive_analytical`
  builds an `IfcStructuralAnalysisModel` from the physical frame: each column/beam → an
  `IfcStructuralCurveMember` (an `IfcEdge` topology) tied at shared `IfcStructuralPointConnection` nodes,
  each analytical member linked back to its physical element (`IfcRelAssignsToProduct`), plus a
  permanent-G self-weight `IfcStructuralLoadCase` + load group. Pure topology — no geometry kernel.
- Re-derive is **idempotent** (purges prior analytical entities via `remove_deep2`, no accumulation, no
  orphan topology). Exposed as the `derive_analytical` edit recipe; read the model back at
  `GET /projects/{pid}/analytical` (analysis models, curve/surface members, nodes, load cases).
- *Slice 1 = the frame. Surface members (slabs/walls → `IfcStructuralSurfaceMember`) and per-member load
  activities are next.*

## v0.3.356 — W10-6: room schedule quantity depth

- The computed **room schedule** now carries `IfcElementQuantity` depth — **Perimeter (m)** and
  **Volume (m³)** columns read from `Qto_SpaceBaseQuantities` alongside floor area. Flows through every
  schedule surface (CSV / SVG / PDF) since they render generically by column.

## v0.3.355 — W10-4: MEP design flow rate on segments

- `add_mep_run` (duct/pipe/cable) and `add_riser` accept an optional **design flow rate** (`flow` +
  `flow_unit`), written to `Pset_Massing_MEPSizing` alongside the nominal size. The flow unit defaults by
  system when omitted — CFM for ducts, GPM for pipes, A for cable — so schedules, QTO, and sizing
  pre-checks read design flow without a geometry parse. Exposed on the `add_duct`/`add_pipe`/
  `add_cable_tray`/`add_wire`/`add_riser` recipes.

## v0.3.354 — D5: detail callouts on the PDF sheet + real sheet refs

- Detail callouts now render on the **PDF** sheet path (`sheet_pdf`), not just SVG — an NCS divided-circle
  bubble (detail number over sheet ref) with a leader to the element, plus a **DETAILS** legend below the
  keynotes.
- The divided-circle bubble carries a **real sheet reference** (bottom half) instead of a placeholder "—":
  the attached document's `Identification` (e.g. `A-541/3`), else the sheet number derived from its
  `Location` basename (`details/S-501.pdf` → `S-501`). `attach_document` no longer leaves the placeholder
  `Identification` that shadowed the derived ref.

## v0.3.353 — DISC-cw: curtain-wall parts read Architectural

- Framing/glazing parts (`IfcMember` mullions/transoms, `IfcPlate` glazing) aggregated under an
  `IfcCurtainWall` or `IfcRoof` now classify as **Architectural**, not Structural — context wins over the
  bare-class default (a façade mullion is enclosure, not frame). The properties index records each
  element's aggregating **host** class, and `discipline_of_ifc_class` consults it. Without a host, parts
  stay Structural.

## v0.3.352 — discipline coverage report

- `GET /projects/{pid}/elements/by-discipline` now returns a **coverage** view over the discipline
  tree: every standard NCS discipline is marked present/absent with its element count, plus
  `disciplines_covered` / `disciplines_total` and a `missing` list. A completeness lens for the model
  — which disciplines are actually populated vs. still empty — computed from the property index with no
  geometry parse.

## v0.3.351 — W10-6: schedule CSV export

The computed door/window/room schedules now export to **CSV** (`GET /projects/{pid}/drawings/schedule.csv?kind=`
for one, or omit for all three) for spreadsheets / procurement / submittals — finishing the schedule views
into the export pipeline alongside the existing SVG/PDF. `drawing.schedule_csv`.

## v0.3.350 — W9-6b: FF&E bill of materials

A new **FF&E / furnishings bill of materials** from the model's placed furniture — `content.furniture_bom`
counts each item (by name) with its IFC class and the levels it appears on, composing `IfcFurniture` /
`IfcFurnishingElement` / `IfcSystemFurnitureElement` (the classes `place_content` + `furnish` author). An
owner/vendor order + procurement starting point. Served on `GET /projects/{pid}/ffe-bom`.

## v0.3.349 — W10-4: nominal-size psets on MEP segments

Authored MEP segments (`add_mep_run` / `add_riser`) now carry a **`Pset_Massing_MEPSizing`** with the
**nominal size (mm)**, shape, and length — so schedules, QTO, and sizing pre-checks can read the size
directly instead of re-deriving it from geometry (nominal sizing normally lives on the IfcType/profile,
which our on-the-fly segments don't carry). Best-effort; never blocks authoring.

## v0.3.348 — UX-4: "Script this" — the recipe interface, made discoverable

A new **⌨ Script this** toolbar button surfaces the app's **scriptable, GUID-safe recipe interface** as a
first-class resource (UX-4 goal). Type a command in plain English and it shows the **exact recipe plan** it
maps to — e.g. *add a 3m wall from 0,0 to 5,0* → `add_wall({"start":[0,0],"end":[5,0],"height":3,
"thickness":0.2})` — the same verbs the AI command bar and the sandboxed `ifcopenshell` runner drive, then
**applies** it (non-destructive plans). Makes the code/authoring layer visible instead of a hidden
power-user path.

## v0.3.347 — Composed sheet: cap plans + per-level sheets (fixes tower timeout)

The composed **key-plan sheet** (`sheet.svg`/`sheet.pdf`, S-101) rendered a plan panel for **every** storey
— on the 30-storey tower that **timed out** (30+ full-model geometry cuts) and crammed 30 illegible plans on
one A3. It now **caps to a few representative levels** (sampled evenly across the building) and takes an
optional **`storey`** to render exactly one level's sheet. On the tower: the key-plan sheet now renders in
~20 s (was ∞) and a single-level sheet in ~12 s, each with the titleblock + per-panel scale + section +
elevation. `GET /projects/{pid}/drawings/sheet.{svg,pdf}?storey=Level%204`.

## v0.3.346 — UX-4: always-visible Info-Box on the 3D canvas

A compact **Info-Box** strip now sits on the 3D view (bottom-left) showing the **selected element's key
facts** — name · IFC class · level · discipline (with the discipline's colour dot from the unified tree) —
**regardless of which rail tab is open** (ArchiCAD's Info-Box pattern). Previously the identity header lived
only inside the Properties tab, so you lost sight of what was selected while on Tools/Tree/Library. Updates
on selection, clears on deselect. First component of the UX-4 designer-workspace shell.

## v0.3.345 — Plan fix: per-level room tags + titleblock / scale / notes

Two fixes to the drawing-set plans. **(1) Room labels no longer stack across levels.** The plan cut its
*geometry* at the level elevation but tagged **every** `IfcSpace` (and door/window callout) in the model —
so a Level 4 plan drew the cellar, lobby, apartment, and amenity room names all on top of each other (every
floor shares the footprint). `space_tags`/`element_callouts` now take the cut plane and label **only the
elements that level's cut passes through**. **(2) Plans now carry a real sheet frame** — a titleblock band
with the sheet title, a compact titleblock box (title · scale · cut-plane AFF · grid), a true **graphic
scale bar** (correct at any zoom), a **north arrow**, and a **general-notes** block. Room names are XML-
escaped so a name with `&`/`<` can't break the SVG.

## v0.3.344 — CODE-3: detail-rule citations follow the resolved edition

The Track-D detail-rule engine seeds its flashing/keynote citations against **IBC 2021**. `apply_rules` now
takes an **`ibc_edition`** so those citations reword to the project's **resolved adopted edition** — an
exterior window in a 2024-adopting jurisdiction cites *IBC 2024 §1404.4* rather than the seed's 2021. Only
the edition year in a citation changes (facts of law); the seed content is untouched. Threaded through the
`apply_detailing_rules` recipe (`ibc_edition` param).

## v0.3.343 — UX-3: unified, searchable Library palette

The 📚 Library now opens **one browsable palette** that unifies the **content catalog** (CONTENT-1 — site
logistics / furniture / landscaping) and the **family types** (W10-1) in a single filterable list —
previously the content parts and the type/family system were separate surfaces. A **search box** filters
across name / IFC class / category / phase as you type; each row shows its class + category; clicking places
the item at an **E,N** point (defaulting to the last picked point). Mesh import (glTF/OBJ/STL → auto-
classified) stays inline. First slice of UX-3 — thumbnails, `tag:`/`type:`/`discipline:` operators, a Recent
bucket, drag-to-place, and appendable IFC libraries follow.

## v0.3.342 — UX-1b: dedicated Annotate + Library tool groups

The interactive **annotation** tools (Add note · Dimension · Revision cloud · Tag) and the **content
library** were buried inside the "Advanced fabrication tools" fold. They're now surfaced as their own
labelled **✍ Annotate** and **📚 Library** groups in the model rail — the two capabilities the UX-1 research
flagged as under-exposed. The Advanced fold keeps the LOD-350/400 fabrication/detailing tools.

## v0.3.341 — UX-1: model tools grouped by lifecycle (ribbon, first slice)

The model rail's tool sections are now labelled and ordered by the **modeling lifecycle** instead of the
seven accreted names — the first slice of the UX-1 task ribbon. Sections read **Data ·** Models / Working
origin · **Build ·** Draw elements / Grids & levels / Advanced authoring, annotate & library · **Analyze &
Coordinate ·** clash / QA · **Document ·** Exports & issue, and the "More tools" group now flows Build →
Analyze/Coordinate → Document. A one-line intro names the lifecycle. (Follow-up UX-1b: split the combined
authoring section into dedicated **Annotate** and **Library** groups.)

## v0.3.340 — CODE-5: applicable code requirements as buildingSMART IDS

The code-analysis engine can now **emit the machine-checkable subset of the applicable code requirements as
a buildingSMART IDS 1.0 file** — so the same jurisdiction-resolved rules validate an IFC in *any* IDS
checker (extends the IDS→BCF pipeline). `codecheck.code_ids(description, edition)` composes the fired code
rules (which requirements apply for this occupancy / size) with the standard IFC common-property IDS specs:
a fire-resistance-rated occupancy (R/A/H/I, or ≥4 stories) pulls in the rated-element groups (wall / door /
slab / column / beam `FireRating`), plus space area/reference (occupant load) and envelope U-value (IECC).
`GET /codes/ids?description=…&edition=…` returns the fired topics + `ids_xml`; `&download=true` returns the
`.ids` attachment. Property requirements (facts of law), never code prose; the AHJ makes the determination.

## v0.3.339 — EST-1 5D: crew-days → schedule duration

The productivity/labour estimate already turned quantities into man-hours → crew-days → cost; now it turns
the crew-days into a **schedule duration** (the 5D loop). Per-line crew-days roll up by **trade group**
(Earthworks · Concrete · Masonry · Structural Steel · MEP · Finishes) into a **working-day** and
**calendar-day** duration — each trade's duration = its crew-days ÷ the number of **parallel crews** of that
trade (a new `crews` control that shortens the trade), and the project duration assumes trades run
sequentially (a conservative critical path; overlap only shortens it). Flows through `labor_estimate` →
`full_estimate` → `from_model`; `GET /projects/{pid}/estimate/labor?crews=N` returns the `schedule` block
(per-group breakdown + working/calendar days) alongside the cost.

## v0.3.338 — COST-DB: the model estimate prices through the pinned vintage

Closes the reproducibility loop (build-order step 8). The model estimate endpoints —
`GET /projects/{pid}/estimate/from-model` and `GET /projects/{pid}/qto/by-floor` — now price the
takeoff **through the project's pinned cost vintage** (its `cost_dataset_id`, else the latest installed),
applying that vintage's `{ifc_class: rate}` map as the rate overrides and returning the `cost_vintage` it
priced with. So a 2024-pinned project's estimate stays on 2024 rates after newer vintages land — defensible
and reproducible. Falls back to the shipped benchmark rates when no vintage is installed.

## v0.3.337 — COST-DB: vintage-versioned cost database (offline first slice)

First slice of the cost-database plan ([cost-db-import-plan.md](docs/cost-db-import-plan.md)) — the
**versioning backbone** so a project's estimate is reproducible against the exact cost vintage it was built
on. New `cost_datasets` + `cost_items` tables (every priced row hangs off a dataset); a **`cost_dataset_id`**
pin on the project; and an **offline `PublicDataImporter`** (`cost_db.py`) that builds a `public_local`
vintage from the app's shipped benchmark rates (one MasterFormat-coded `CostItem` per rate, linked to its IFC
class so the model takeoff prices straight through) — **no network, no subscription**. A vintage **resolver**
(latest · exact year · `nearest`/`strict` fallback) and `is_latest` management round it out.

Endpoints: `GET /cost/datasets` (installed vintages + what the public importer offers), `POST
/cost/datasets/import` (`{vintage, quarter, source}`; a `source:"cloud"` request with no subscription warns +
falls back to the public build), and `GET`/`POST /projects/{pid}/cost-vintage` (pin a project to a vintage;
null = follow latest). The `massing.cloud` subscription importer (signed-bundle download), real public-source
ingest (BLS/FRED/DoD/Census), location factors, and PPI escalation-forward are later build-order steps.

## v0.3.336 — RFI-0: missing-dimension detection in the decision-readiness audit

The decision-readiness / RFI-prevention audit gains a fifth gap source — **missing dimensions**, the
proactive inverse of the classic "what size is this?" RFI. It scans the model for elements a builder or
estimator **can't size, order, or take off** because a dimension the drawings should carry is absent:
doors/windows with no `OverallWidth`/`OverallHeight`, and rooms with no floor area
(`Qto_SpaceBaseQuantities`). Each surfaces as a ranked, GUID-anchored gap (category `dimensions`) with a fix,
alongside the existing code / detail / data / coordination gaps — and rides the same
`POST /rfi/readiness/bcf` promotion to BCF.

## v0.3.335 — One canonical discipline source across both engines

New low-level module **`aec_data/disciplines.py`** holds the shared discipline data — the CSI MasterFormat
division master (`MF_DIVISIONS`) and the discipline colour palette (`DISCIPLINE_COLORS` / `SERIES_COLORS` /
`discipline_color()`). It lives in the geometry engine on purpose: `aec_api` can import `aec_data` but not
the reverse, so anything both need has to sit there. `aec_api.classification` now **imports** these instead
of defining its own copies, and `aec_data.specmanual` drops its duplicate `_DIVISIONS` map — so the project
manual's CSI divisions and the estimate/sheet/viewer vocabularies are literally the same objects. One source
of truth for the division titles and discipline colours across the API and the IFC engine (DISC-3b).

## v0.3.334 — Estimate rolls up by real discipline (not IFC class)

The model estimate's `by_discipline` was a misnomer — it grouped by raw **IFC class**, so a "discipline"
breakdown listed `IfcColumn`, `IfcSlab`, `IfcPipeSegment` … rather than Structural / Plumbing / …. Now each
priced class line carries its **discipline** (name + code + color from the unified tree), and a genuine
**`by_discipline_rollup`** sums the lines into NCS disciplines — so the estimate reads as
Structural $X · Architectural $Y · Mechanical $Z · …, colored to match the viewer. The per-class detail is
kept as `by_class` (and `by_discipline` stays as an alias for backward compatibility). First slice of
folding the data engines onto the one spine (DISC-3).

## v0.3.333 — Tool buttons for Fire Alarm + Telecom; upgraded demo tower

- **🔔 Fire-alarm device** and **📶 Telecom device** tool buttons in the modeling rail (next to
  🧯 Fire-protection), so the DISC-4a recipes are one click at the last-picked point — pick the device kind
  (smoke/heat detector, pull station, horn-strobe, bell, FACP · MDF/IDF/switch/WAP/data outlet) and it's
  authored on the Fire Alarm / Telecommunications system.
- The demo **30-storey tower** is regenerated with a proper building-element breakdown so every discipline
  is represented: a **unitized `IfcCurtainWall`** facade (4 full-height assemblies — 152 mullions/transoms +
  720 glazing panels — replacing the old thin glazed walls + punched windows); **fire-rated construction**
  (286 walls: 2-hr core/shaft enclosure + 1-hr dwelling-unit demising, via `Pset_WallCommon.FireRating`);
  a **roof assembly** (`IfcRoof` over the structural deck); **90 smoke/heat detectors + 61 alarm devices**
  (pull stations / horn-strobes / FACP) on a **Fire Alarm** system; and **37 telecom devices** (MDF/IDF/WAP)
  on a **Telecommunications** system. The model now spans Structural / Architectural / Mechanical / Plumbing /
  Electrical / Fire Protection / Fire Alarm / Telecom — each colored distinctly by the discipline tree.

## v0.3.332 — Fire Alarm + Telecom as first-class authorable systems

Two building disciplines that were previously only reachable as raw IFC classes are now first-class
authoring recipes, mirroring how fire *protection* became first-class (v0.3.311):

- **`add_fa_device`** — a fire-alarm / life-safety device: smoke/heat/duct **detector** (`IfcSensor` with
  `SMOKESENSOR`/`HEATSENSOR`), **manual pull station** / **horn-strobe** / **strobe** / **bell** / **FACP**
  (`IfcAlarm`), enrolled on a named **Fire Alarm** distribution system. Fire alarm is its own discipline
  (the FA sheet series), distinct from fire protection (sprinklers/standpipes).
- **`add_comms_device`** — a telecom / low-voltage device: **MDF/IDF rack**, **network switch**, **wireless
  access point** (`IfcCommunicationsAppliance`) or **data outlet** (`IfcOutlet`), on a **Telecommunications**
  system (discipline **T**).

Both classify correctly under the unified discipline tree — comms → Telecommunications (purple), fire-alarm
devices → Electrical/FA — so they color and group distinctly in the viewer + model browser. Invokable via
`POST /edit` and the AI authoring command bar.

## v0.3.331 — Color-by-discipline in the viewer

The IFC-classes panel gains a **Color by** toggle (IFC class ↔ Discipline). In discipline mode every
class swatch takes its **discipline's canonical color** from the served tree (v0.3.330) — fire = red,
plumbing = green, mechanical = amber, electrical = yellow, structural = blue, architectural = grey — and
a **discipline color legend** appears showing exactly which disciplines are in the model. A **Paint model**
button pushes the current scheme onto every element in the 3D view, the way Navisworks/Revit color a
federated model by discipline. Unmapped classes keep their stable hashed hue.

The model browser now **consumes the same served IFC-class → discipline map** (`setDisciplineLookup`)
instead of its own regex — one shared vocabulary, so "By discipline" grouping and the viewer colors always
agree. `IfcReinforcingBar`/mesh/tendon now classify to Structural (were falling to the default).

## v0.3.330 — Unified discipline tree: colors + full IFC coverage

The Discipline Spine (`classification.py`) gains the two things it was missing to be the app's single
source of truth for *how a discipline looks and what rolls up to it*:

- **A canonical per-discipline color palette** (`DISCIPLINE_COLORS` + `discipline_color()`) — one hex per
  NCS discipline, chosen for perceptual separation and common coordination conventions (fire = red,
  plumbing = green, mechanical = amber, electrical = yellow, telecom = purple, structural = blue,
  civil = earth). Fire Alarm carries its own swatch so it reads apart from Fire Protection red. This is
  net-new — the viewer previously hashed class names to arbitrary colors and no shared palette existed.
- **Full IFC-class → discipline coverage** (`_IFC_DISCIPLINE`) for the MEP / fire / electrical / telecom
  distribution entities the MasterFormat estimate map never enumerated (`IfcSprinkler`→Fire,
  `IfcAlarm`/`IfcSensor`→Electrical, `IfcCommunicationsAppliance`→Telecom, `IfcTransformer`/switchgear→
  Electrical, `IfcPump`/`IfcTank`→Plumbing, `IfcBoiler`/`IfcCoolingTower`/`IfcFan`→Mechanical, …), so
  every element in a real model classifies to a discipline instead of falling to the default.

New `discipline_tree()` composes it all — per discipline: color, MasterFormat divisions (+titles),
UniFormat II groups (+titles), NCS sheet series, and the IFC classes that roll up to it — plus an
`ifc_class_discipline` lookup and a `colors` map. Served on `GET /reference/disciplines` (`tree` key) so
the viewer, plan/PDF poché, sheet generator, and model browser can all color/group by one shared
vocabulary rather than each re-encoding its own. First step of unifying the discipline tree across every
module and engine.

## v0.3.329 — QTO: derive length for linear elements so they price non-zero

Fixes a $0 in the model estimate. Linear elements (`IfcPipeSegment` / `IfcDuctSegment` /
`IfcCableCarrierSegment` / `IfcRailing`) are modelled as swept solids with **no Qto length**, so the
geometry takeoff returned `length = 0` and the per-metre MEP/railing rates (added v0.3.326) totalled them
at **$0**. `aec_data.qto` now derives a `length` in its geometry fallback as the **longest bounding-box
dimension** of the meshed solid — robust whether the run is the extrusion depth (vertical pipe/cable riser)
or lies in the profile plane (a railing extruded to rail height). On `quay_tower.ifc` the 36 pipe segments
now take off 1,153 m ($207,540), the cable riser 100.5 m ($22,110), and railings 112 m ($13,440) — all
previously $0. `test_massing.py` extended (cored-model pipe/duct risers assert metre-scale, non-zero length).

## v0.3.328 — UX-2: element-aware tags

New `add_tag` recipe places an **element-aware tag** — an `IfcAnnotation` (ObjectType "tag") whose label
is **auto-read from the host element** (its Name → a Pset `Reference`/`Tag`/`Mark` → its type name → the
IFC class short-name), positioned at the host's plan centroid and **assigned to it**
(`IfcRelAssignsToProduct`), so the tag tracks the element it describes. `text` overrides the auto-read
label. Renders on the generated plan (via the v0.3.327 annotation pass). New **🏷 Tag selected element**
tool (uses the current selection) + `addTag` client method. This is the "live element-aware tags" slice of
UX-2; only inference-snapped placement remains.

## v0.3.327 — UX-2: revision clouds + view-placed annotations on the plan

Closes the annotation author→sheet loop. Two parts:
- **`add_revision_cloud` recipe** — authors an `IfcAnnotation` (ObjectType "revision") as a **scalloped
  closed polyline** around a region (two opposite [E,N] corners, or ≥3 boundary points) + an optional
  revision tag (`IfcTextLiteral`). GUID-stable, guarded, reachable via `POST /edit`. New **☁ Revision
  cloud** two-corner tool + `addRevisionCloud` client method.
- **Annotations now render on the generated plan** — `drawing.plan_svg` reads view-placed
  `IfcAnnotation`s (from `add_annotation` / `add_dimension` / `add_revision_cloud`) and draws them:
  text notes, element tags, dimension lines + labels, and revision clouds + rev-tags. Previously
  annotations round-tripped as IFC but never appeared on the drawing — the baked-SVG path couldn't
  show model-authored markup. The count is returned as `annotations` and flows through the sheet
  composer, so issued sheets carry them too.

## v0.3.326 — Estimate: price MEP, fire-protection & plant equipment

The model estimator's `DEFAULT_RATES` covered structure + architecture only, so a fully-serviced
building's mechanical/electrical/plumbing scope fell through to *unpriced* — understating the
conceptual total. Added unit rates for MEP distribution (pipe/duct/cable-carrier per metre, fittings
per count), terminals & fixtures (sprinkler heads, air/sanitary terminals, light fixtures, outlets,
switches), and plant equipment (pumps, boilers, tanks, transformers, cooling towers, chillers,
switchgear, unitary equipment, fans) plus steel-connection assemblies. `IfcReinforcingBar` is
intentionally *not* priced separately — the concrete volume rates are quoted in-place incl. rebar, so
pricing it again would double-count; LOD-400 rebar stays a takeoff-only detail. Surfaced on a
2,750-element authored tower whose 232 sprinkler heads, risers and cellar plant returned $0.

## v0.3.325 — Fix: whole-model re-upload served stale from the IFC cache

`ifc_loader.open_model` cached opened models by **path alone** (`@lru_cache`), so re-publishing a
**replacement** model to the same `source.ifc` path returned the *previous* model — reindex, the
scene digest, drawings, schedules and every analysis kept reading the old geometry until the process
restarted. Now keyed by `(path, mtime_ns, size)`: an unchanged path still hits the cache (fast), but a
file **re-written in place** reloads fresh. The `/edit` path was never affected (it writes a new
timestamped file); whole-model replacement to a fixed path was. Regression test `test_ifc_cache.py`
added to the gate. Surfaced while validating a 2,750-element authored tower whose newly-added
architectural finishes (ceilings, floor finishes, unit doors, railings) were invisible until the fix.

## v0.3.324 — Interactive dimensions (UX-2, next slice)

Extends the in-view annotation tool with **dimensions**. New `add_dimension` recipe authors an
`IfcAnnotation` between two [E,N] points — a dimension line (`IfcPolyline`) plus the **measured distance**
as an `IfcTextLiteral` at the midpoint (auto-labelled `5.00 m`, or a custom label), in the Annotation
context; round-trips as real IFC and feeds the drawing generator. New **📐 Dimension** tool with a two-click
flow (first point → second point → measured dimension). The E8 guardrails already validate the two points
(finite + distinct → zero-length rejected). `addDimension` client + `test_annotation.py` extended (a 3-4-5
span → `5.00 m`, custom label, zero-length rejection). *Next: inference-snapped dimension placement + tags
that read a live IFC property.*

## v0.3.323 — Interactive annotation: place notes/tags as IfcAnnotation (UX-2, first slice)

The first slice of the UI/UX Master Pass's annotation gap: annotation existed **only** baked into generated
plan SVGs — now you can place it *in the model*. New `add_annotation` recipe authors an **`IfcAnnotation`**
with an `IfcTextLiteral` (an `Annotation2D` representation in the Annotation context) at an [E,N,z] point —
a note / tag / callout that round-trips as real IFC (and can feed the drawing generator, unlike the baked
SVG path). New **🏷 Add note / annotation** tool places one at the last-clicked point (text + kind prompt);
`addAnnotation` client. Empty text rejected. `test_annotation.py` (authors + round-trips through a written
IFC). *Next (UX-2): dimensions snapped by the E1 inference engine, element-aware tags, revision clouds; and
the UX-1 ribbon consolidation + UX-3 Library palette (best built with a live 3D session to verify the look).*

## v0.3.322 — Scene digest: an LLM-grounding model summary (A4)

A compact, one-glance summary of *what's in the model* — and the grounding the AI command bar was missing.
New `scene.digest(model)` composes the shipped summaries (element counts by class, storeys, spaces, MEP
systems + disciplines, phasing, LOD, model hygiene) into a small dict plus a one-paragraph `prose` overview,
degrading gracefully on a bare model. New `GET /projects/{pid}/scene-digest` + a **🔎 Model digest** tool
(counts, MEP disciplines, phasing, hygiene at a glance). Crucially, `POST /ai/author` now injects the digest
prose into the planner's system prompt, so Claude authoring is **grounded in the current model** ("N walls,
2 storeys, a fire-protection system…") instead of planning blind. `sceneDigest` client + `test_scene.py`.

## v0.3.321 — Mesh→IFC asset import: bring in detailed parts, auto-classified (CONTENT-1 remaining)

The other half of the content library: **import a well-detailed mesh and place it as the *right* IFC**, not
a random shape. New `content.parse_mesh` loads a glTF / GLB / OBJ / STL / PLY (trimesh) into recentred,
metre-scaled verts + faces (glTF Y-up → IFC Z-up; a face-count cap; `scale`), and `content.detect_category`
guesses the catalog category from the filename (`office-chair.glb` → `chair`; `Porta-John.stl` →
`sanitary_unit`; longest synonym wins). New `POST /projects/{pid}/content/import` (multipart) parses the file,
auto-detects (or takes `category=`), and authors it via the `place_content` recipe — correct IFC class +
phase + Uniclass/OmniClass classification — versioned, undo-able, republished. The 🏗 Site content library
tool gains an **⬆ Import mesh** picker (drops the asset at the last-clicked point). License-vet the source
before import. `importContent` client + `test_content_import.py`. Builds on the B4 mesh hatch + the CONTENT-1
catalog. *Next: a curated CC0 seed library + a browsable thumbnail palette (folds into the UX-3 Library pass).*

## v0.3.320 — Element-to-element connections (B5)

The LOD-350 coordination primitive: which elements are physically connected. New `connect_elements` recipe
records an `IfcRelConnectsElements` between two building elements (a beam framing into a column, a brace to a
gusset, a hanger to a slab) — distinct from the MEP port link (`connect_mep`). Idempotent per ordered pair,
rejects self/missing. New `element_connections` read-back reports the connected pairs (with class +
description) and each element's connection **degree**, served at `GET /projects/{pid}/element-connections`;
`connectElements` / `elementConnections` clients. Guarded (needs both GUIDs). Reachable via the AI command
bar; authored edges export for structural-analysis / coordination tools. `test_element_connections.py`.

## v0.3.319 — Vertical MEP risers (standpipes / stacks / vents)

MEP runs could only be drawn horizontally (`add_mep_run` sweeps in plan); a multi-story **riser** was
impossible. New `add_riser` recipe sweeps an `IfcPipeSegment` **vertically** (world +Z) from `bottom_z` to
`top_z` at an [E,N] point, with a port at each end, enrolled on a distribution system — the vertical
complement to `add_mep_run`, for **fire standpipes**, plumbing **stacks**, and **vents**. New **⭱ Vertical
riser** tool places one at the last-clicked point over a bottom→top elevation range. Verified
deterministically (ExtrudedDirection = +Z, Depth, base elevation) and by standalone tessellation (a real
cylinder spanning the height). `test_mep_systems.py` extended; zero/negative height is rejected.

## v0.3.318 — O&M / warranty document refs on the as-built model (G3 follow-up)

Completes the LOD-500 turnover trio (verify · dimensions · manufacturer) with **operation & maintenance /
warranty documents** bound to the physical asset. New `attach_om_document` recipe (a purpose-tagged
`attach_document` — `OPERATION_MAINTENANCE` or `WARRANTY`) associates a manual/warranty reference (name +
link) with the selection via `IfcRelAssociatesDocument`; `asbuilt_summary` now reports `with_om_docs`
(elements carrying an O&M/warranty document, detected by the document's `Purpose`) + the distinct document
names. The ✅ As-built (LOD 500) tool gains an **📄 Attach O&M / warranty doc** control and shows the O&M-doc
count in the readiness line. Guarded (needs a selection) + an `attachOmDocument` client. `test_lod500.py`
extended (2 O&M + 1 warranty doc → `with_om_docs` = 3).

## v0.3.317 — Deeper authoring guardrails (E8)

The pre-apply guardrails now catch more classes of broken edit before they touch the model. `guards.precheck`
gains: nested type **`dims`** validation (each value finite; dimension keys must be positive — mirrors the
top-level rules, non-dimension keys only finite-checked), **`points`** footprint arrays (every vertex a
finite [E,N] pair; ≥2 vertices), **sloped-wall heights** (`start_height`/`end_height` finite ≥ 0),
**procedural-mesh** `verts`/`faces` (non-empty), and new **reference requirements** — `connect_mep` needs
both `guid_a` + `guid_b`, `set_system_predefined` needs a `system`. Still fast, deterministic, params-level
(no I/O); errors block, suspicious-but-legal values warn. `test_guards.py` extended. This closes the E8
"deepen" follow-up (the first slice shipped earlier).

## v0.3.316 — Sprinkler coverage pre-check (NFPA-13-informed)

New `mep.sprinkler_coverage(model, hazard)` counts the SPRINKLER heads and compares against the number
NFPA 13 would require for the model's protected floor area (summed IfcSpace `Qto_SpaceBaseQuantities.
NetFloorArea`) at the hazard class — max protection-area-per-sprinkler is **200 / 130 / 100 ft²**
(light / ordinary / extra), a fact of the standard (copyright-safe; the text stays in NFPA 13). Returns head
count vs required, adequacy + shortfall, and area unknown → `adequate: null` when no spaces are measured. New
`GET /projects/{pid}/mep/sprinkler-coverage?hazard=` + a **🧯 Sprinkler coverage** button in the MEP tool
(shown when a fire-protection system exists). A planning assist — not a hydraulic calc, spacing check, or
obstruction review. `test_mep_systems.py` extended (2 heads / 400 m² → 22 required at light hazard; ordinary
requires more; empty model → n/a).

## v0.3.315 — Fire-protection equipment: hose reel / FDC / hydrant / fire pump (MEP-FP next slice)

Fleshes out the fire-protection system with real devices, not just piping. New `add_fire_equipment`
recipe authors a **sprinkler head**, **hose reel**, **fire-department (siamese) connection**, **hydrant**
(all `IfcFireSuppressionTerminal` subtypes with the right `PredefinedType` — HOSEREEL / BREECHINGINLET /
FIREHYDRANT / SPRINKLER) or a **fire pump** (`IfcPump`), each placed on the `Fire Protection` distribution
system (discipline = fire, so it rolls up in the MEP browser). New **🧯 Fire-protection equipment** tool
places the chosen device at the last-clicked point (mirrors the door/window place flow). `test_mep_systems.py`
extended (hose reel + FDC + fire pump land as the right IFC classes on the fire system). *Next: sprinkler
coverage/spacing check + standpipe risers.*

## v0.3.314 — Full cost estimate: labour + material + equipment (EST-1 next slice)

The model-driven estimate goes from labour-only to a fuller **5D cost**. `productivity.py` gains a
**material $/unit** (`MATERIALS`) and **equipment/plant $/unit** (`EQUIPMENT`) benchmark layer beside the
man-hours rates, and a new `full_estimate` augments each line with `material_cost` / `equipment_cost` /
`line_total` plus `total_material_cost` / `total_equipment_cost` / `total_cost`. `from_model(..., full=True)`
and `GET /projects/{pid}/estimate/labor?full=true` return it; the catalog now carries the unit material +
equipment costs too. The 💰 tool (renamed **Cost estimate — labour · material · equipment**) shows the
labour / material / equipment / total breakdown and a per-line total. Still excludes overhead / profit /
markup; all rates are editable benchmarks. `test_productivity.py` extended (concrete: $130/m³ material +
$15/m³ equipment; masonry $30/m² material, no equipment; totals reconcile).

## v0.3.313 — Decision-readiness gaps → BCF (RFI-0 next slice)

The decision-readiness audit (v0.3.307) now **rounds its gaps to trackable BCF issues**. New
`POST /projects/{pid}/rfi/readiness/bcf` runs `rfi_prevention.decision_readiness` and promotes every gap —
failed code checks, missing details/keynotes, model-data holes, open clashes — to a `type="readiness"` BCF
`Topic`: GUID-anchored (a 3D pin from the gap's first element), category-labelled, priority from the gap's
severity (high → high). Idempotent — re-running clears the prior readiness topics so they never pile up
(mirrors the W9-2b egress→BCF pattern). The 🚫 Decision-readiness tool gains a **📌 Promote N gaps to BCF
issues** button, so the "what's missing before we issue?" list becomes a resolvable, round-tripping issue set
in the Issues panel. New `rfiReadinessBcf` client. `test_readiness_bcf.py` (integration: 9 gaps → 9 topics,
409 without a source IFC, idempotent re-run).

## v0.3.312 — Security: Capacitor 6 → 7, clears the transitive `tar` advisories (SEC-DEP-1)

Dependency-hygiene release. The mobile shell's `@capacitor/*` packages (`android`, `cli`, `core`, `ios`)
move from `^6.2.1` to `^7`, pulling `@capacitor/cli@7.6.8` and its transitive `tar@7.5.20` (was `tar@6.2.1`).
That clears **7 Dependabot alerts** (6 high / 1 medium) — all node-tar extraction-time symlink/hardlink
path-traversal advisories (GHSA-9ppj-qmqm-q256, GHSA-qffp-2rhf-9h96, GHSA-83g3-92jg-28cx, GHSA-34x7-hfp2-rc4v,
GHSA-r6q2-hw4h-h46w, GHSA-8qq5-rm4j-mr97, GHSA-vmf3-w455-68vh) that entered **only** through `@capacitor/cli@6`.
The fix needs `tar ≥ 7.5.16`, but `tar@7` is ESM-only and Capacitor 6's CLI is CJS, so a bare npm override would
break `cap` (`ERR_REQUIRE_ESM`) — hence the full Capacitor 7 bump. Real exploit risk was nil (the CLI extracts
only its own trusted platform templates during a developer-run `cap sync`, never untrusted input, never in CI or
at runtime); this is security-tab hygiene, not an urgent patch. `capacitor.config.ts` needed no v7 changes; no
native `android/`/`ios/` projects are checked in, so there was no Gradle migration. Verified: `npm ls tar` resolves
`tar@7.5.20`, `npm run build` (Node 20) passes, and `cap sync` succeeds.

## v0.3.311 — Fire protection as a first-class distribution system (MEP-FP)

MEP systems now carry a **discipline**, so fire protection stands beside HVAC / plumbing / electrical
instead of being folded into a generic "MEP" group. `IfcDistributionSystem`s are stamped with a
`PredefinedType` (`FIREPROTECTION` / `VENTILATION` / `DOMESTICCOLDWATER` / `ELECTRICAL`…): `add_mep_run` /
`add_mep_fitting` / `add_mep_terminal` take a `discipline` (the segment/fitting/terminal recipes default to
their natural discipline), a new `set_system_predefined` recipe (re)types an existing system, and a new
**`add_sprinkler`** recipe authors an `IfcFireSuppressionTerminal` sprinkler head on the `Fire Protection`
system. The system browser (`mep.mep_summary`) now reports each system's **discipline** + PredefinedType, a
**by-discipline rollup**, and a `has_fire_protection` flag; fire-suppression terminals are counted and are
port-connectable, so the W10-4 connectivity check covers sprinkler runs too. The 🔀 MEP systems tool shows a
discipline rollup (with a "no fire-protection system yet" nudge) and a per-system discipline label. The
discipline is inferred from member classes when a system carries no explicit type, so existing models
classify correctly. `test_mep_systems.py` extended (fire-protection system + sprinkler heads +
`set_system_predefined` retag). *Next: sprinkler coverage/spacing + standpipe/fire-pump equipment.*

## v0.3.310 — Existing-building code: IEBC scope-of-work classifier (CODE-EBC)

Unlocks renovation / adaptive-reuse projects, which are governed by the **International Existing Building
Code**, not the new-construction path. New `ebc.py` (data side, facts-of-law like the CODE-1/2/3 engine —
owns the classification decision tree + published section/chapter numbers, never the copyrighted prose)
classifies a scope of work under the **Work Area Compliance Method**: **Repair · Alteration Level 1 / 2 / 3
· Change of Occupancy · Addition**. `classify(...)` is a pure, deterministic decision tree — a Level-2
trigger (space reconfiguration, adding/removing a door or window, reconfiguring/extending a system, added
equipment) becomes **Level 3** when the work area exceeds 50% of the building (IEBC §505), an addition or
change of occupancy governs as primary while co-occurring alterations still apply, and each result carries
the driving citations (§502–§507 + the requirements chapter), the applicable nested levels, and the
jurisdiction's adopted IEBC edition. `from_model(...)` first-guesses the scope from the model's **phasing**
(existing vs new/demolish → an alteration with a rough work-area estimate) which explicit flags override.
New `GET /codes/ebc/pathways` (reference catalog) + `GET /projects/{pid}/codecheck/ebc` (with `infer=true`
for the phasing-derived guess), an `ebcClassify`/`ebcPathways` client, and a **🏚 Existing-building code
(IEBC scope)** tool in the code-intelligence cluster. Preliminary classification — the AHJ makes the
determination. `test_ebc.py` (16 hand-worked IEBC scenarios + the phasing inference).

## v0.3.309 — Docs + marketing refresh: catch the user-facing surface up to the authoring wave

Non-code release. The README, in-app guide, and GitHub Pages landing had drifted ~14 releases behind
(last refreshed at v0.3.294) and named none of the authoring wave. All three now cover **model undo/redo**,
**SketchUp-style drawing inference**, **sloped-top walls**, **procedural mesh**, the **sandboxed
`execute_ifc_code`** escape hatch, the **site content library** (logistics/furniture/landscaping,
auto-classified), **MEP port-to-port connectivity**, **edition-aware code checks**, **detail callouts**,
the **decision-readiness (RFI-prevention)** audit, the **productivity-rate labour estimate**, and
**field-verified as-built dimensions** — with the new API surface (`/rfi/readiness`, `/mep/connectivity`,
`/estimate/labor*`, `/content/catalog`, `/edit/{undo,redo,history}`, `/authoring/capabilities`). Added a
shareable **current-status page** (`docs/status.html`) that snapshots what the platform does end to end,
and refreshed `docs/marketing-copy.md` with the authoring-stack feature lines. Regenerated the viewer demo
snapshot (`demoData.json`). Competitor-name-free throughout, per the standing directive.

## v0.3.308 — Productivity-rate labour cost + duration estimate (EST-1)

The estimating link from *quantities* to *schedule + 5D cost*. New `productivity.py` holds a
**man-hours-per-unit** rate library (earthworks / concrete / masonry / steel / MEP / finishes) with typical
crew sizes + condition **loading factors** (highrise / remote / summer / congested / night-shift).
`labor_estimate` turns a quantity of work into **man-hours → crew-days → labour cost**; `from_model` derives
a rough takeoff straight from the model (walls → masonry face area, slabs/columns → concrete volume) and runs
it. New `GET /estimate/labor/rates` (catalog) + `GET /projects/{pid}/estimate/labor?loading=&rate=` and a
**💰 Labour estimate** tool showing man-hours / crew-days / cost per activity. Editable benchmarks, labour
only (add materials/equipment/overhead for a full cost). `test_productivity.py`.

## v0.3.307 — Decision-readiness audit: RFI-prevention (RFI-0)

The proactive inverse of the RFI — every RFI is a decision made without the needed information, so this
surfaces the **information gaps a builder would otherwise have to ask about** *before* the set goes out. New
`rfi_prevention.decision_readiness` composes the checks that already ship — the approvability pre-flight
(failed code checks), the Track-D detail-rule validator (elements missing their detail/keynote),
model-hygiene (`model_qa`: orphaned / unenclosed / unnamed / duplicate), and clash coordination (open
clashes) — into one **ranked resolve-before-issue list**, each gap with a category, severity, and a concrete
fix. New `GET /projects/{pid}/rfi/readiness` and a **🚫 Decision-readiness (RFI-prevention)** tool that lists
the gaps and isolates the flagged elements in 3D. A pre-check assist — not a promise of zero RFIs.
`test_rfi_readiness.py`.

## v0.3.306 — Site content library: logistics / furniture / landscaping, auto-classified (CONTENT-1)

Place real-world parts into the **right** IFC place, not as random shapes. New `content.py` catalog maps ~20
categories — **site logistics** (tower/mobile crane, hoist, fencing, sanitary unit, site office, laydown,
gate, dumpster), **furniture** (desk/chair/sofa/table/bed/cabinet), and **landscaping** (tree/shrub/planter/
bollard) — each to its correct IFC class + project phase + classification. New `place_content` recipe authors
an item at an [E,N] point from a supplied detailed mesh **or** a category-sized placeholder box, then sets
the phase (logistics = **temporary**, so it time-phases on the 4D logistics slider) and the classification
(Uniclass/OmniClass). Logistics land as proxies, furniture as `IfcFurniture`, landscaping as
`IfcGeographicElement` (proxy fallback on older schemas). New `GET /content/catalog` + a **🏗 Site content
library** palette tool. Builds on the B4 mesh hatch; content is imported/authored per-asset with license
vetting (the catalog records the intended license tier; geometry is supplied, never bundled unvetted).
`test_content.py`.

## v0.3.305 — Procedural-mesh escape hatch (B4)

Author an element from a **raw triangle mesh** for geometry the parametric recipes can't express. New
`add_mesh_representation` recipe builds an `IfcTriangulatedFaceSet` (Tessellation body) from `verts`
(`[[x,y,z]…]` metres) + `faces` (`[[i,j,k]…]` 0-based), with index/degeneracy validation. GUID-stable,
versioned/undo-able. New **△ Add mesh** tool (JSON input) in the Advanced cluster; also directly callable
by the AI command bar / `execute_ifc_code`. Verified objectively — `test_mesh.py` tessellates a pyramid and
confirms the extents (2×2 base, apex 2 m, ≥6 triangles), and the output round-trips through the real
web-ifc → Fragments converter into a valid fragment.

## v0.3.304 — Sloped-top walls: parapet slope / shed / gable (B3)

Walls can now have a **sloped top**. New `set_wall_slope` recipe rebuilds the selected wall's Body as a
**trapezoidal side profile extruded across the thickness** — a plain `IfcExtrudedAreaSolid` (no boolean, so
every geometry engine renders it), with the top rising from `start_height` (at the wall's start point) to
`end_height`. GUID-stable, versioned/undo-able. New **⟋ Slope wall top** tool (Advanced cluster). Verified
objectively, not by eye: `test_wall_slope.py` tessellates the result (`ifcopenshell.geom`) and confirms the
start end sits at ~2 m and the far end at ~4 m (a real rising slope, base at Z = 0), and the output was
round-tripped through the actual web-ifc → Fragments converter into a valid fragment (it renders). This was
the last item on the Master-Builder order of attack.

## v0.3.303 — Fix: `test_edit_undo` CI failure (read-only `/app`)

The S4 undo test (v0.3.298) failed the CI API gate with `PermissionError: /app` — it drives `/model/blank`,
which writes the source IFC under `IFC_DIR` (defaults to `/app/ifc`, read-only in the container). The test
now points `IFC_DIR` at a writable scratch dir (and cleans it up), per the container-readonly-`/app` gotcha.
Test-only change; no product code affected.

## v0.3.302 — Field-verified as-built dimensions + variance (G2)

Completes the LOD-500 data layer. New `record_asbuilt_dimension` recipe stamps a **field-measured**
dimension on the selection, the **design** value (if given), the **variance** (measured − design), and
whether it's **within tolerance** — into `Massing_AsBuilt​Dim` (`{Dimension}_Measured/_Design/_Variance` +
`WithinTolerance`). `asbuilt_summary` now also reports `with_dimensions` and
`dimensions_out_of_tolerance`, surfaced in the ✅ As-built (LOD 500) tool alongside a measure form. With
G1 (verify) and G3 (manufacturer/serial), the model can carry the full field-verified as-built record for
turnover. `test_lod500.py` extended.

## v0.3.301 — SECURITY: close an RCE escape in the A1 sandbox

An adversarial review of v0.3.300 proved the AST sandbox was escapable to full RCE **when the flag is on**:
exposing the real `ifcopenshell` module let a snippet reach its transitive imports as plain (non-dunder)
attributes — `ifcopenshell.os.system(...)`, `ifcopenshell.api.importlib.import_module('subprocess')`,
`ifcopenshell.api.inspect.builtins.eval(...)`, etc. Fixed by **never exposing a module**: the snippet now
gets a minimal **facade** carrying only the intended authoring callables (`ifcopenshell.api.run`,
`ifcopenshell.guid.new`) — bound functions with no attribute path back to a module. Added an
attribute-name **denylist** (defense-in-depth) that also blocks the `str.format`/`format_map` dunder-read
bypass and `model.wrapped_data`. `test_sandbox.py` now asserts all 12 proven escape payloads are blocked
while the legitimate `ifcopenshell.api.run` authoring path still works. (The feature remains off by default.)

## v0.3.300 — Sandboxed `execute_ifc_code` escape hatch (A1)

The unbounded authoring escape hatch — run a small ifcopenshell snippet against the model for what the fixed
recipe registry can't express. Defense-in-depth, treating this as arbitrary-code territory:
**off by default** (raises unless the operator sets `AEC_ALLOW_IFC_CODE=1`, thereby accepting the risk); an
**AST allowlist** that rejects `import`, `def`/`class`/`lambda`, `while`/`with`/`try`, `del`, decorators,
dunder access (`__class__`/`__globals__`), and reflection/IO builtins (`open`/`eval`/`exec`/`getattr`/
`__import__`/`type`…) before anything runs; and a **curated namespace** exposing only `model`, `ifcopenshell`,
and a small safe builtin set. New `sandbox.py`, an `execute_ifc_code` recipe (runs through the versioned,
undo-able, audited `/edit` path), a `GET /authoring/capabilities` probe, and an **⚡ Run IFC code** tool in
the Advanced cluster. `/edit` now returns clean 403 (disabled) / 400 (rejected) instead of 500.
`test_sandbox.py` covers ~18 rejection cases + the flag gate + a real authoring snippet.

## v0.3.299 — SketchUp-style drawing inference (E1)

Free-hand drawing now lands clean lines automatically. A new `inference.ts` module infers, as you place a
point, an on-axis (±X / ±Z), **parallel**, or **perpendicular** direction from the previous point (and the
previous edge) and snaps the point onto that inference line when the cursor is within ~6° — no need to hold
Shift. A hard geometry-vertex snap always wins, and Shift stays the manual hard ortho-lock. Pure,
unit-tested math (`inference.test.ts`, 7 cases). Builds on the existing endpoint/edge and grid snapping.

## v0.3.298 — Model undo / redo (S4)

Authoring now has a real undo stack. Every `/edit` already wrote a new versioned source IFC and left the
prior versions on disk, so undo is just restoring a prior version + republishing — GUID-stable, so
pins/RFIs/clashes survive. New `edit_history` sidecar stack (no schema change), `POST /edit/undo`,
`POST /edit/redo`, and `GET /edit/history`; the restored path is verified to exist and stay inside the
project's IFC directory. **↶ Undo / ↷ Redo** buttons in the Model tools rail reflect the server-side history
depth and republish on click. A fresh edit invalidates the redo stack. `test_edit_undo.py`. (The
`/edit-preview` ghosting half of S4 already ships.)

## v0.3.297 — MEP port-to-port connectivity + validation (W10-4)

Turns a pile of MEP segments/fittings into a connected logical network. New `connect_mep` recipe wires two
elements **port-to-port** (`IfcRelConnectsPorts`, using the first free port on each; raises when none is
free). New `mep.connectivity` validation report — ports connected vs open, port-to-port link count, and the
**dangling** (floating) elements whose ports are all unconnected — served at `GET /projects/{pid}/mep/
connectivity`. The 🔀 MEP systems tool now shows the connectivity summary, a two-step **Connect** flow (pick
one element → connect to a second), and isolates floating elements in 3D. `test_mep_systems.py` extended.
*Next: flow/sizing psets + coincident-port auto-connect.*

## v0.3.296 — Detail callouts on the plan (D5)

Closes the attach-a-detail → callout-on-the-drawing loop. The plan generator now draws an **NCS-style detail
callout** (a divided circle with a leader) on every element that carries an attached detail drawing
(`IfcRelAssociatesDocument`), plus a **DETAILS legend** keyed to each detail — distinct from the keynote
bubbles (which reference spec/classification codes). `drawing.plan_svg` gains a `details` toggle and returns
a `details` count; the callouts flow through to the issuable SVG sheet automatically. So: attach a detail in
the 🏷 Detailing tool → generate the plan → the referencing callout appears. `test_drawing.py` extended.

## v0.3.295 — Edition-scoped occupant-load factors (CODE-2)

The egress computation is now edition-aware, not just the citations. `egress_analysis`/`egress_from_model`
take an IBC `edition` and apply edition-scoped occupant-load factors — the one well-established Table 1004.5
change: **Business areas are 100 gross ft²/occ in IBC 2012/2015 vs 150 gross in IBC 2018+**. `code_analysis`
resolves the jurisdiction's adopted edition first and threads it in, so a project in a 2015-edition
jurisdiction computes a *higher* occupant load (and required egress width) than the 2021 baseline, exposed
through the existing Jurisdiction field. The egress result carries `code_edition`; the default (no
jurisdiction) keeps the current-edition factor. Facts of law only. `test_code_analysis.py` extended.

## v0.3.294 — Docs, landing page & demo refreshed to the current product

Housekeeping so the outward-facing surfaces match what shipped. The **README**, the **in-app guide**
(`docs/guide.html`), and the **Pages landing** (`docs/index.html`) are reframed around the current
end-to-end capability — model from scratch → generate a permit-ready construction-document set → pre-check
code → hand over field-verified as-built data — with new sections/tutorials for the CD set, code &
permit-readiness, and LOD-500 turnover. Pre-existing competitor comparisons were removed (capabilities are
described directly); interop/connector/standard names kept. The **Pages demo snapshot** (`demoData.json`)
was regenerated against the current API (932 fixtures). The **roadmap** was re-archived: this session's
shipments moved to `roadmap-completed.md`, active roadmap re-prioritized (CODE-2 → D5 → W10-4 → …).

## v0.3.293 — Model Health scorecard gains a Code & permit-readiness lens

The composite **Model Health** scorecard now includes a fifth lens — **Code & permit readiness** — sourced
from the D8 approvability pre-flight (egress, door widths, occupancy classification, substantiated rated
assemblies). It scores by the pre-flight pass rate and headlines the checks still to fix, so the single
"is my project healthy?" number now reflects permit-readiness alongside integrity, ISO-19650 information,
clash coordination, and verified-as-built. Weights rebalanced to include it; the lens shows n/a (excluded
from the mean) when no gating checks apply. `test_model_health.py` updated.

## v0.3.292 — Fix two debug-audit findings in the D6 manual + D8 pre-flight

A post-release debug audit caught two wrong-result bugs (no crashes), now fixed with regression tests:
- **Project manual (D6) missed layer-set materials.** `specmanual._element_materials` (was `_element_material`)
  now resolves an `IfcMaterialLayerSetUsage` → `IfcMaterialLayerSet` → its layer materials (and profile /
  constituent sets + material lists), so a real wall's materials actually reach Part 2 Products instead of
  silently yielding nothing. Returns all distinct names, not one.
- **Approvability (D8) occupancy check always passed.** It counted a space's free-text `LongName` (which our
  own `add_spaces` always sets to "Room NN") as evidence of occupancy classification, so it could never fail.
  It now gates strictly on `Pset_SpaceOccupancyRequirements.OccupancyType`.

## v0.3.291 — Manufacturer / serial for the O&M / turnover layer (G3)

Completes the LOD-500 data layer. New `set_manufacturer_info` recipe stamps the standard IFC
`Pset_ManufacturerTypeInformation` (Manufacturer / ModelLabel / ProductionYear) and
`Pset_ManufacturerOccurrence` (SerialNumber / BarCode) on the selection — the data that round-trips to
COBie and asset/CMMS systems for O&M and turnover. Only non-empty fields are written; GUID-stable; a bad
GUID never aborts the batch. `asbuilt_summary` now also reports `with_manufacturer` / `with_serial` counts,
and the ✅ As-built (LOD 500) tool gains a manufacturer/serial stamp form. `test_lod500.py` extended.

## v0.3.290 — Approvability pre-flight: is the model permit-ready? (D8)

A plan-reviewer pre-flight checklist over the model, mirroring what a reviewer checks first. New
`codecheck.approvability` runs five cited checks — egress capacity (IBC 1005.3), egress door clear width
≥32 in (IBC 1010.1.1 / A117.1), two-exits-where-load>49 (IBC 1006.2), occupancy classification on spaces
(IBC Ch.3), and fire-rated assemblies substantiated by a UL/GA classification or attached detail (IBC Table
721) — returning pass/fail/na/info per check plus a readiness score. New
`GET /projects/{pid}/codecheck/approvability` and a **✅ Approvability pre-flight** viewer tool that lists
the checks and isolates flagged elements in 3D. A pre-check assist — not a certified review or a guarantee
of approval. `test_approvability.py`.

## v0.3.289 — 3-part MasterFormat project manual — the spec book (D6)

Closes the loop from "classify an element + attach its detail" to "a spec section writes itself." New
`specmanual.py` groups the model's elements by their MasterFormat work-result classification into CSI
**divisions → sections**, each framed in SectionFormat 3-part shape: **Part 1 General**, **Part 2 Products**
(the element types + materials actually in that section), **Part 3 Execution** (the installation
instructions attached via `IfcRelAssociatesDocument`, or a manufacturer-instructions fallback). New
`GET /projects/{pid}/spec/manual` (structured) + `/spec/manual.txt` (downloadable outline) and a **📖 Project
manual** viewer tool. A pre-check starting point — the real manual is authored by the spec writer.
`test_specmanual.py`.

## v0.3.288 — Clear the critical dev-dependency advisories (vitest 3, happy-dom 20)

Bumped the two dev/test dependencies carrying critical Dependabot advisories — `vitest` ^2.1.9 → ^3.2.6
(resolved 3.2.7) and `happy-dom` ^15.11.7 → ^20.8.9 (resolved 20.10.6) — clearing 4 critical + several high
alerts. Both are test-only (the runner and its DOM), never shipped to production, so real-world exposure
was low; this is hygiene. Verified the full web test suite (13 files / 79 tests) still passes on the new
majors, plus typecheck + build + bundle budget. (Remaining Dependabot items are transitive build tooling —
`tar`/`esbuild`/`glib` — for a follow-up.)

## v0.3.287 — Harden download filenames (defense-in-depth)

A security pass over this session's new endpoints came back clean; this applies its one hardening note.
The DXF/PDF drawing endpoints interpolate user-supplied `axis`/`direction`/`number`/`sheet` into the
`Content-Disposition` filename. Those are now whitelisted to `[A-Za-z0-9._-]` (`_safe_name`/`_safe_filename`)
so a crafted value can't break out of the filename quoting. Self-reflected only (no cross-user/stored
vector) and the response bodies are inert data files — this is precautionary, not a fix for an exploit.

## v0.3.286 — Edition-aware code analysis: cite the jurisdiction's adopted IBC (CODE-3)

The code-analysis summary now uses CODE-1: pass a `jurisdiction` (US state) and it resolves the adopted
**IBC edition** and names it throughout — the headline badge shows "IBC 2021", the citations read "IBC 2021
Table 506.2 …", and the disclaimer records the code context ("IBC 2021 (CA adoption, as-of 2024)"). With no
jurisdiction it uses the national baseline and prompts for one. The 🏛 Code-analysis tool gains a
**Jurisdiction** field that re-checks edition-aware in place. `GET /codecheck/analysis?jurisdiction=…`. Still
a pre-check assist — verify the edition in force with the AHJ.

## v0.3.285 — Jurisdiction code context: adopted-edition catalog (CODE-1)

The substrate for edition-aware code checking. New `codes.py` encodes only facts of law + published-edition
metadata: the model-code **families** (IBC/IRC/IECC/IFC/IPC/IMC/IEBC/IgCC/A117.1) and their editions (the
I-Codes publish on a fixed 3-year cycle), plus `resolve(jurisdiction)` → the adopted editions for a US
state, falling back to a documented national baseline when not seeded. Every result carries a mandatory
**"verify with the AHJ"** note and an as-of year — the shipped seed is a dated starting point to extend from
authoritative sources, never an authority (adoptions change each cycle and by local amendment). New
`GET /codes/families`, `/codes/adoptions?jurisdiction=…`, `/codes/seeded`, and an **Adopted codes** lookup
in the 🏛 Code-analysis tool. Copyright-safe by design: facts and section numbers only, no code prose. This
unlocks the later edition-aware citation work (thread `code_ctx` through the checks).

## v0.3.284 — Authoring guardrails: reject broken edits before they touch the model (E8)

The reliability edge — a novice can't produce invalid IFC. New `guards.py::precheck` runs params-level,
name-based rules over any recipe: coordinates must be finite [E,N] pairs, a line's endpoints must differ
(no zero-length walls), physical dimensions must be positive and finite, integer counts ≥ 1, LOD-stage in
range, and required host/target references present. **`apply_recipe` now enforces the gate** — a broken
edit raises a clear message and never writes a file (verified against 49 recipe-exercising tests; it
rejects nothing legitimate). Errors block; suspicious-but-legal inputs (an implausibly large dimension →
likely unit slip, a non-standard phase) surface as **warnings**. New `POST /projects/{pid}/edit/precheck`
lets the UI warn *before* committing, and the AI command bar now prechecks each step (blocks on errors,
confirms through warnings). `test_guards.py` covers the rules and the enforcement path.

## v0.3.283 — Progressive-disclosure toolbar: fabrication tools behind an "Advanced" toggle (E4)

Lowering the barrier to entry: the Model tools rail now shows only the everyday authoring + drawing tools
by default (rooms, furnish, types, groups, phasing, query, LOD, as-built, plans/sheets/schedules/sections).
The LOD-350/400 **fabrication + detailing** tools — steel base plates & shear tabs, rebar cages, MEP
fittings, curtain wall, and the detailing/auto-detail tools — tuck behind a **🔧 Advanced fabrication
tools** toggle. A first-time modeler sees a simple toolset; the choice persists in localStorage, so power
users keep their fabrication tools open.

## v0.3.282 — Schedules on an issuable PDF sheet (finishes the CD set)

The computed door/window/room schedules now lay out on an issuable **ARCH-D sheet** (border + titleblock)
and render to PDF — the tabular half of the construction-document set as a submittable sheet, next to the
plan/section/elevation sheets. New `drawing.schedule_pdf` (columns per schedule, row truncation guard),
`GET /drawings/schedule.pdf?kinds=…`, and a **⤓ Schedules sheet (A-601 PDF)** viewer tool. The titleblock
draw was factored into a shared `_titleblock_pdf` helper reused by the plan and schedule sheets. With DXF
(v0.3.281) this completes the near-term CD-set slices.

## v0.3.281 — DXF export for plans, sections & elevations (CAD interchange)

The drawing set now exports to **DXF** so the linework opens in any CAD tool. A hand-written, dependency-free
R12 DXF writer (`dxf.py` — POLYLINE entities, no library, no license exposure) serialises the same
world-placed polylines the SVG views use: `plan_dxf` / `section_dxf` (auto-centred cut) / `elevation_dxf`
on named layers (PLAN / SECTION / ELEVATION). New `GET /drawings/plan.dxf`, `/section.dxf`, `/elevation.dxf`
endpoints and **⤓ DXF** buttons alongside each view in the Sections & elevations tool. `test_dxf.py` covers
the R12 envelope, closed-loop detection, degenerate-skip, and world placement.

## v0.3.280 — Fix: S3 structured-output schema (LLM authoring path) + apply-all recovery

Two follow-ups to the S3 command bar. (1) The plan schema declared each step's `params` as an open
`{type: object}`, which Anthropic's strict structured outputs reject (every object must set
`additionalProperties: false`) — so a keyed request would 400 and silently fall back to the keyword
baseline, meaning Claude multi-step planning never actually ran. `params` is now a JSON **string** the
model fills and `_coerce_params` parses (tolerant of both string and dict, so the keyword path and tests
are unaffected); every object in the schema is closed. (2) **Apply-all** now recovers from a mid-chain
failure: because earlier edits already advance the source IFC but defer their republish to the last step,
a failure part-way used to strand them unpublished — it now republishes what applied and reports
"stopped after N/M steps" instead of leaving the model in a committed-but-unconverted state.

## v0.3.279 — LOD-500 as-built verification (G1)

BIMForum defines LOD 500 as a *field-verified as-built* reliability attribute — with **no** geometric
requirement — so we support it as a data layer over the geometry. New `verify_asbuilt` recipe stamps
elements with `Massing_AsBuilt` (Status=VERIFIED + VerifiedBy / VerifiedDate / Method / Note provenance),
and `asbuilt_summary` reports **LOD-500 readiness** (share of elements field-verified, broken down by
method: field-measure / laser-scan / total-station / photo / submittal / inspection). New
`GET /projects/{pid}/lod500` endpoint and a **✅ As-built verify (LOD 500)** viewer tool — stamp the
selection, watch readiness climb. GUID-stable, round-trips as a Pset. `test_lod500.py` covers the stamp,
method fallback, bad-GUID skipping, and readiness math.

## v0.3.278 — AI command bar S3: Claude multi-step authoring + one-click Apply all

The natural-language command bar ("type what to build") now plans with Claude when an Anthropic API key
is set — a single instruction like *"a 5×4 m room at 0,0"* becomes an ordered **multi-step plan** (four
walls), and *"add three columns along the north wall"* resolves without exact coordinates. New
`nl_ai.plan()` builds the plan against the shared `RECIPE_SPECS` schema and **re-validates every step**
through the same `validate_call` guardrail as the keyword path before it reaches you — the model never
writes anything, never invents GUIDs (host/target elements come from the current selection), and
destructive recipes are withheld from it entirely. No key → the deterministic keyword baseline, unchanged.
Multi-step plans get a **✓ Apply all N steps** button that chains the edits and republishes the model
once instead of per step. The paid path is rate-limited; any LLM hiccup falls back to keyword parsing,
never an error. New `test_nl_ai.py` covers the plan assembly, context-fill, and fallback.

## v0.3.277 — Fix: align room tags & callouts with the world-placed drawing linework

Follow-up to v0.3.276. The bake fix moved section/plan linework into world coordinates, but the two
annotation builders — `space_tags` (room tags) and `element_callouts` (door/window callouts) — still
read element geometry in *local* coordinates, so their label centroids collapsed onto each element's
own origin and no longer sat on the linework (every off-origin room tag stacked at 0,0). Factored the
world-coords setup into a shared `_world_settings()` helper and applied it to both builders, so tags and
callouts land on the elements they label. Regression coverage added to `test_sections.py` (off-origin
model: tags/callouts must fall within the linework bounds, not at the origin).

## v0.3.276 — Sections & elevations in the UI + world-placement fix for all drawings

The section and elevation SVG generators existed server-side but were unreachable — added a **📐 Sections
& elevations** tool to the viewer's drawing rail: cut sections (X–X / Y–Y) and projected N/S/E/W
elevations, true linework from the model geometry. The section cut now **auto-centres** on the model
(`section_svg(offset=None)`) so it lands through the building instead of the world origin — no coordinate
to guess.

**Fix (affects every drawing):** the geometry bake fed the plan/section/elevation/sheet generators
element meshes in *local* coordinates — each element's ObjectPlacement wasn't applied, so anything not
authored at the origin collapsed onto (0,0) and overlapping elements stacked. `bake()` now sets
`use-world-coords`, so all 2D output places elements where they actually are. Plans, sections, elevations,
and composed sheets of any real (off-origin) model are now correct. New `test_sections.py` guards the
auto-centre + world placement.

## v0.3.275 — Fix: code-analysis occupancy group now resolves for every occupancy label

The v0.3.274 code-analysis summary looked up the occupancy group in an exact-match dict keyed on
`"Business"`/`"Assembly"`/…, but the space-mix labels carry qualifiers and synonyms
(`"Assembly (unconcentrated)"`, `"Educational (classroom)"`, `"Industrial"`, `"Parking"`, the
`"Business (assumed)"` default) — so 6 of 13 labels silently fell through to group **"—"**. Replaced the
exact dict with an ordered **substring** matcher (`_occ_group`) so those resolve to A/E/F/S/B correctly;
accessory/utility spaces (no standalone group) still return blank by design. Regression coverage added.

## v0.3.274 — Code analysis: permit-set G-series code summary

The IBC **code-analysis summary** a permit set carries on its G-series code sheet — now computed straight
from the model. `codecheck.code_analysis()` assembles occupancy classification (inferred from the space
mix or set explicitly), construction type, gross area + story count, the **computed occupant load + egress**
(reused from the occupancy/egress pre-check), and the governing sections for allowable area/height
(Table 506.2, §504, §506.3) and element fire ratings (Table 601/602). New `GET /projects/{pid}/codecheck/
analysis` endpoint (occupancy_group / construction_type / sprinklered inputs) and a **🏛 Code analysis**
tool in the viewer's QA rail that lays it out as a code-sheet block. Pre-check assist that cites sections —
verify allowable area with the AHJ; not a certified review.

## v0.3.273 — Security: ReDoS-harden the NL command-bar regexes

CodeQL flagged 5 `py/polynomial-redos` alerts in the natural-language authoring parser (unbounded `\d+` /
`\s*` runs in `nlauthor.py`). Bounded every quantifier (`\d{1,9}(?:\.\d{1,6})?`, `\s{0,6}`) so the parse
is linear on any input — no catastrophic backtracking. Parsing behaviour unchanged (`test_nlauthor.py` green).

## v0.3.272 — Fix: IFC2x3 MEP browser crash + degenerate-input guard

From the post-release debug worktree:

- **IFC2x3 MEP browser crash.** `mep_summary` called `model.by_type("IfcDistributionSystem")`, which *raises*
  on an IFC2x3 model (that class is IFC4+) — and legacy MEP models are commonly IFC2x3. It now degrades to an
  empty result via a schema-safe `_by_type` helper (matches the `energy.py` pattern).
- **Coincident start/end points** in `add_wall`/`add_beam`/`add_rebar`/`add_mep_run`/`add_railing`/
  `add_curtain_wall` produced an opaque "only finite values are allowed" placement crash (zero-length axis).
  They now raise a clear `ValueError("start and end points must differ")`.

Guarded by additions to `test_mep_systems.py` (IFC2x3) and `test_curtainwall.py` (zero length).

## v0.3.271 — Natural-language authoring command bar (the low-barrier way in)

**Type what you want to build.** A new **✨ command bar** at the top of the Author panel turns plain English
into modelling — "add a 3 m wall from 0,0 to 5,0", "put a window in the selected wall", "steel column W14x30
at 6,6", "set LOD 350 on the selection", "add 6 rooms". The instruction is mapped to a **validated plan** of
`{recipe, params}` and shown for **confirmation** — nothing is written until you click Apply, and each step
runs through the normal GUID-stable `/edit` path (audited, undoable). Destructive ops (delete) require a
second confirm.

This is the deterministic **no-API-key baseline** (regex + keyword matching, unit-normalized dimensions
mm/cm/ft/in → metres, coordinate + section/LOD/phase parsing, selection + active-storey context) — so it
works for everyone with zero setup. It's also the foundation (shared `RECIPE_SPECS` table + `validate_call`
guardrail) for the LLM tool-use path next, and the first slice of the AI-authoring moat validated by the
Nonica/Arcol competitor research. Engine `nlauthor.py` (`interpret` / `validate_call` / `RECIPE_SPECS`);
`POST /projects/{id}/ai/author` (interpret-only). `test_nlauthor.py` green.

## v0.3.270 — Wave 11 · B6: curtain-wall systems

Completes the B6 domain-geometry catalog. **🪟 Curtain wall** authors an `IfcCurtainWall` along a line that
**aggregates** a real framing grid: vertical **mullions** + horizontal **transoms** (`IfcMember`, MULLION)
bounding **glazing panels** (`IfcPlate`, CURTAIN_PANEL) on a bays×rows layout — one LOD-350/400 assembly,
contained in the storey, GUID-stable. Oriented to the wall axis; profile dims are unit-scale-correct
(verified identical real sizes on metre **and** millimetre models). Engine `curtainwall.py::add_curtain_wall`;
`add_curtain_wall` recipe + viewer tool. `test_curtainwall.py` green.

## v0.3.269 — Fix: authoring correctness on non-metre models + egress door width

Bug fixes from a parallel correctness-audit worktree (verified against real ifcopenshell):

- **HIGH — profile geometry on millimetre/imported models.** `geometry.add_profile_representation` SI-converts
  only the extrusion *depth*, not the profile — so profile dims must be authored in **file units**
  (metres ÷ unit_scale). `_rect_profile`, `connections._circle`, `steel.i_profile`, `rebar._swept_bar`, and the
  inline builders in `add_spaces`/`add_slab`/`add_mep_run`/`add_rebar`/`add_roof`/`add_covering` wrote raw
  metres — making every wall/column/beam/slab/MEP/rebar **1000× too thin** on a mm model (ifcopenshell's
  default and most imported IFCs). Our own blank models are metre-based (scale=1) so tests never caught it.
  Also fixed `add_rebar_cage` hard-failing ("cover too large") and `add_spaces` double-scaling its placement,
  both consequences on mm models.
- **MED — egress door width always 0.** `codecheck._door_width_m` read `Pset_DoorCommon.Width`, but authored
  doors store width in the `OverallWidth` **attribute** — so `provided_width_in` was 0 and egress adequacy
  meaningless. Now reads `OverallWidth` (unit-scaled).
- **MED — copies re-parented to the wrong storey.** `copy_element` (used by arrays) put every copy in the
  *lowest* storey; now inherits the source element's container.

New `test_unit_scale.py` authors into a forced-millimetre model and asserts column/wall/steel/duct/slab/rebar
carry correct **real** sizes + rebar no longer crashes + egress width > 0. All metre-model tests unchanged
(scale=1 makes every ÷scale a no-op).

## v0.3.268 — Wave 11 · B6 MEP fittings + edge-hardening

**MEP fittings & system browser.** `add_mep_fitting` authors an elbow (`BEND`), tee/cross (`JUNCTION`), or
size change (`TRANSITION`) as an `IfcDuctFitting`/`IfcPipeFitting`/`IfcCableCarrierFitting` at a point — with
the right number of connection **ports** and assignment to a named `IfcDistributionSystem` — the LOD 350/400
detailing that turns loose runs into a real system. A new **🔀 MEP systems** tool browses each
`IfcDistributionSystem` (segment/fitting/terminal counts + a connectivity signal: elements with unconnected
ports, plus anything unassigned), and **🔀 MEP fitting** places a fitting at the last-clicked point. Engine
`edit.py::add_mep_fitting` + `mep.py::mep_summary`; recipe + `GET /mep`. `test_mep_systems.py` green.

**Edge-hardening (parallel bug-audit worktree).** Fixed a real crash — `drawing.sheet_svg` raised
`KeyError('paper')` on an empty model / bogus storey (the empty-geometry branch of `plan_svg` omitted the
`paper`/`inner` keys `sheet_svg` reads); it now composes a border+titleblock sheet instead. Added
`test_wave11_edges.py` — ~30 edge/error-path assertions across all 8 Wave 11 modules (families, groups, rebar,
connections, drawing, detailing, rules, representations): bad-dims/blank-name raises, array-detach invariant,
keynote priority, rule idempotency + untested facets, LOD int-coercion, and the `sheet_svg` regression guard.

## v0.3.267 — Security: CodeQL remediation pass

Hardening from the GitHub CodeQL scan. Genuine fixes:

- **Open redirect (SAML ACS)** — `RelayState` now must be a *same-site absolute path*; protocol-relative
  (`//evil.com`) and backslash (`/\evil.com`) forms — which browsers resolve cross-origin — are rejected.
- **Authenticated arbitrary-file read (federated clash)** — the `disciplines` map may now only *select* from
  the project's own registered model paths (source IFC + appended discipline models); a client can no longer
  point it at an arbitrary server path.
- **Path-traversal defense-in-depth** — a `storage.safe_seg()` whitelist guards every `pid`/`mid` segment used
  to build a filesystem path (upload/publish/models/import), and `LocalBackend` now rejects `..`/absolute/NUL
  keys up front + requires the resolved path to stay under the storage root (`is_relative_to`).
- **ReDoS (SCIM filter)** — the `userName eq "…"` parser drops the ambiguous `\s*…\s*` and uses a bounded
  `[^"]*`, eliminating catastrophic backtracking.
- **DOM-XSS / sanitization** — escape the user-influenced label in the place-family status line; make the nav
  label escape global (`/&/g` + `<`).
- **Stack-trace exposure** — the readiness probe logs the DB error server-side and returns a generic
  "database unavailable" instead of the exception text.
- **Least-privilege CI** — `permissions: contents: read` added to the CI, lockfile, and Rust workflows.

Remaining CodeQL alerts are triaged false-positives (HMAC-SHA256 *token signing* — passwords use
`pbkdf2_sha256`; the signed-token cookie; the intentional admin-only **read-only** SQL console; the trusted-
HTML `resultNote` helper whose callers `escapeHtml` untrusted data; `DOMParser` XML that is never injected;
a `blob:` object URL) and are dismissed with justification.

## v0.3.266 — Wave 11 · B6: rebar cages + research-inbox roadmap

**Reinforcement detailing (LOD 400).** A new **🪝 Rebar cage** tool builds a real reinforcement cage in the
selected concrete column: **4 longitudinal corner bars + stirrups** at a spacing, offset by concrete cover,
as **swept-disk `IfcReinforcingBar`s** (a disk of the bar radius swept along its centreline — the correct way
to model reinforcement; straight for the bars, closed-rectangle for the ties), grouped with the column into an
`IfcElementAssembly`. Engine `rebar.py::add_rebar_cage`; `add_rebar_cage` recipe. `test_rebar.py` green.

**Roadmap — future research inbox.** Folded a 6-source research round (building codes, Unreal, and the
arcol/atomatiq/nonica competitor scan) into a new **🔮 Future** section as parked items: a copyright-safe
**jurisdiction-aware building-code library** (own the rules/facts + deep-link; license prose later), **Unreal
as an optional paid viz bridge only** (glTF export + three.js PBR are the on-mission wins), and competitor-
informed items led by an **MCP server over our edit-recipe engine** (validates Track A), real-time
multiplayer, and auto site/zoning ingestion.

## v0.3.265 — Wave 11 · B6: structural steel connections (LOD 350/400)

Bare steel members become **fabrication assemblies.** Two connection recipes turn LOD-300 members into
LOD-350/400 shop assemblies, on the selected element:

- **🔩 Base plate (steel column)** — an `IfcPlate` base plate + up to 4 anchor bolts (`IfcMechanicalFastener`,
  ANCHORBOLT) authored under the column, then grouped **with the column** into an `IfcElementAssembly`.
- **🔩 Shear tab (steel beam)** — a shear-tab plate + bolts at the beam end, assembled with the beam (a simple
  beam-to-column shear connection).

Each is real IFC geometry, GUID-stable, sized/placed from the member's own placement. This is the first
domain-catalog slice of Track B6 (steel connections → rebar cages → MEP fittings → curtain-wall). Engine
`connections.py` (`add_base_plate` / `add_shear_tab`); `add_base_plate` / `add_shear_tab` recipes.
`test_steel_connections.py` green.

## v0.3.264 — Wave 11 · C4: computed schedules (door / window / room)

The tabular half of a CD set — **schedules computed straight from the model.** A new **📋 Schedules** tool
lists the **door**, **window**, and **room** schedules (marks, widths/heights, types, levels, areas), pulling
values directly from the elements (door/window `OverallWidth`/`OverallHeight`, space `NetFloorArea`, the
containing level). Each is also a standalone SVG table for a schedule sheet. Engine `drawing.py::schedules` /
`schedule_svg`; `GET /projects/{id}/drawings/schedules` (JSON) + `/drawings/schedule.svg?kind=doors|windows|rooms`.
`test_drawing.py` extended (door 0.90 m / window 1.50 m captured, table SVG with header + grid, bad-kind 400).

## v0.3.263 — Wave 11 · C3b: sheet PDF export (the submittable deliverable)

**The payoff of the whole chain: a PDF you can submit to the AHJ.** A new **⤓ Sheet PDF (A-101)** tool renders
the issuable sheet — ARCH-D border + titleblock + plan **poché** + overall dimensions + keynote legend —
**directly to PDF** via `reportlab` (BSD, already a dependency; no SVG→PDF converter, no AGPL). Everything on
the sheet comes from the model: geometry from the authored profiles, keynotes from the Track-D spec codes.

Model → author → auto-detail (IBC flashing rules) → **PDF construction sheet**, all in the browser, offline,
GUID-stable, no Revit/Autodesk. Engine `drawing.py::sheet_pdf`; `GET /projects/{id}/drawings/sheet.pdf`.
`test_drawing.py` verifies valid PDF bytes (`%PDF`/`%%EOF`, non-trivial size, empty-storey safety). Next:
computed schedules on the sheet, sections/elevations, per-GUID cache.

## v0.3.262 — Wave 11 · C3: issuable sheets + titleblock

The plan becomes a **sheet you can issue.** A new **📄 Issue sheet (A-101)** tool composes an **ARCH-D
(36×24″) sheet**: a border, a **titleblock** (MASSING mark, project name, sheet title, sheet number, scale,
north arrow), and the plan placed in a **scaled viewport** (aspect-preserving) inside the drawing area. The
sheet title/number track the active level. This is the construction-document deliverable format — the same
sheet the door/window/room schedules and detail callouts will land on next.

Engine `drawing.py::sheet_svg` (plan refactored to expose its inner content + paper size for composition);
`GET /projects/{id}/drawings/sheet.svg?storey=&scale=&number=&title=`. `test_drawing.py` extended. Pure SVG,
no new deps; **PDF/DXF export is the next C-slice** (permissive svglib+reportlab — reportlab is already
present, BSD-licensed).

## v0.3.261 — Wave 11 · C2: dimensions & keynotes on the plan

The plan drawing now **reads the model's intelligence.** `plan_svg` gains two layers:

- **Dimensions** — overall width &amp; height dimension strings (witness ticks + metric text), so the plan
  carries real measurements, not just linework.
- **Keynotes** — every drawn element carrying a **Track-D classification code** (MasterFormat/UniFormat) gets
  a numbered keynote bubble, and a **keynote legend** maps each number to its code + title. The keynotes are
  generated *directly from the codes the Auto-detail rule engine attaches* — so the loop closes: place a wall
  → it gets a spec code → the plan shows the keynote and legends it. Both layers toggle off.

The 🖨 Generate plan tool automatically produces the richer sheet (dimensions + keynote legend). Pure
computation from the authored geometry + classifications — no geometry kernel. `test_drawing.py` extended
(dimension strings, keynote bubbles + legend from 04 20 00 / 05 12 00). Next C-slices: sections/elevations,
sheets + titleblocks, PDF/DXF.

## v0.3.260 — Wave 11 · C1: plan-drawing generator (SVG)

The first slice of the **construction-document set** — generate a schematic **plan drawing** (SVG) straight
from the model. A new **🖨 Generate plan (SVG)** tool (Grid &amp; Levels) opens a 1:100 plan of the active level:
walls/columns/slabs/roofs/spaces drawn as **class-styled poché** (a CSS class per IFC class controls
linework/fill), correctly scaled to paper millimetres with a viewBox and a title.

Because our geometry path is web-ifc→Fragments (ifcopenshell's OpenCASCADE engine produces no mesh here), the
generator takes the research-recommended optimization: it derives each footprint **directly from the authored
extruded-profile geometry** (profile polygon × placement × solid position) — deterministic, no geometry kernel.
Engine `drawing.py` (`plan_svg`); `GET /projects/{id}/drawings/plan.svg?storey=&scale=`. `test_drawing.py`
green. Next C-slices layer on dimensions, keynotes (from the Track-D codes), sheets/titleblocks and PDF/DXF.

## v0.3.259 — Wave 11 · D3+D7: the detail-rule engine + IBC window-flashing case

The brain that turns model state into construction-document content — and the headline worked case. A new
**✨ Auto-detail (rules)** tool (Grid &amp; Levels) runs an **IDS-shaped condition→content rule library** over
the model:

- **Rules** = an `applies` block (IFC entity, predefined type, a property on the element, or a
  relationship-context facet like "fills an opening in an **exterior** wall") + an `attach` block (the
  content bundle — classification codes + detail/instruction documents), written through the Track-D
  carriers, GUID-stable.
- **The worked case (D7):** a window in an exterior wall auto-gets the **IBC 2021 §1404.4 / ASTM E2112 /
  AAMA 711 flashing detail** (sill-pan → jamb → head shingle-lap sequence, as an installation instruction)
  + **MasterFormat 08 51 00** + **UniFormat B2020**. An interior-wall window gets nothing. Exterior doors get
  their sill-pan/jamb flashing (08 11 00); fire-rated walls get an assembly keynote (09 21 16, tag UL/GA no.).
- **The same rules validate as IDS QA** — a missing-keynote pre-flight lists elements that match a rule but
  lack their required code (author-time attach, QA-time check). Shown before/after in the tool.

Engine `rules.py` (`apply_rules` / `validate_rules` + seed rule library); `apply_detailing_rules` recipe +
`GET /detailing/rules/validate`. `test_rules.py` green. Pure ifcopenshell; code citations are facts.

## v0.3.258 — Wave 11 · Track D carrier layer: codes & detail documents

The join layer between the model and the construction documents — attach **keynote/spec codes** and
**detail/instruction documents** to elements, IFC-natively. A new **🏷 Detailing** tool (Grid &amp; Levels)
on the selected element:

- **Classification codes** — `IfcRelAssociatesClassification` for **UniFormat** (element → keynote),
  **MasterFormat** (work result → spec section), **OmniClass** (product), Uniclass. One element carries
  all three; each code is the join key a keynote, a schedule row and a spec section share.
- **Documents** — `IfcRelAssociatesDocument` → `IfcDocumentReference` → `IfcDocumentInformation` attaches a
  **detail drawing + installation instruction** (name, detail no. like `A-541/3`, URI). Deduped by
  identification so re-attaching a shared detail reuses one record.
- A **detailing inspector** reads an element's codes + documents back.

This is exactly what the (next) detail-rule engine writes when "exterior window → IBC §1404.4 flashing
detail + ASTM E2112 instruction + spec 08 51 00" fires, and what keynote/schedule/spec/drawing generation
will read. Engine `detailing.py` (`classify` / `attach_document` / `element_detailing`); recipes +
`GET /detailing/{guid}`. `test_detailing.py` green.

## v0.3.257 — Wave 11 · B2: parametric door & window generators

Doors and windows now get **real lining, frame and panel geometry** from IfcOpenShell's built-in parametric
generators (`geometry.add_door_representation` / `add_window_representation`) instead of a single flat box
proxy — a LOD 300→350 jump for near-zero geometry code. Every existing **◧ Add door** / **◨ Add window** tool
benefits automatically (parametric is the default); the recipes also accept an `operation` type
(`SINGLE_SWING_LEFT`, `DOUBLE_DOOR_SINGLE_SWING`, window `SINGLE_PANEL`, …). Lining depth is sized from the
host wall's thickness. The host is properly voided (`IfcRelVoidsElement`) and the door/window fills the
opening (`IfcRelFillsElement`); a generator failure falls back to the box proxy so authoring never breaks.
This is the real door/window geometry that the Wave 11 detail-rule engine will hang the IBC/ASTM flashing
detail + keynote + spec off. Engine in `edit.py`; `test_openings.py` green.

## v0.3.256 — Wave 11 · F0: the representation/LOD spine (foundation)

The architectural foundation the rest of Wave 11 hangs off — **one GUID-stable element that can carry
several view-keyed representations, plus an explicit LOD stage**. A new **📶 Level of Development** tool
(Grid &amp; Levels):

- **⚙ Establish drawing contexts** — `ensure_contexts` finds-or-creates the full view-keyed context tree:
  Model + **Plan** roots and the `Body`/`Axis`/`Box`/`Annotation`/`FootPrint` subcontexts (each tagged by
  `TargetView`) that construction-drawing generation and coarse↔fine display need. Idempotent.
- **LOD stage** — tag the selected element or a saved selection set **100 → 500** (`Pset_MassingLOD.Stage`).
  LOD is element *maturity*, not a geometry mode: the same GUID-stable element carries it as its geometry
  and data are refined. Advancing updates in place (no duplicate pset); a distribution overview shows the
  model's maturity at a glance.

Engine `representations.py` (`ensure_contexts` / `set_lod` / `lod_summary`); `ensure_contexts` + `set_lod`
recipes + `GET /lod`. `test_representations.py` green. This is track **F0** — everything downstream (parametric
door/window generators, the SVG drawing generator, detail-follows-LOD) keys off this spine.

## v0.3.255 — Wave 11 · power selection (IfcOpenShell selector DSL)

The first foundation piece of Wave 11 (LOD-400/500 authoring): a **🔎 Query (selector)** tool that runs the
IfcOpenShell **selector query language** over the model — `IfcWall` · `IfcWall, IfcDoor` ·
`IfcWall, Pset_WallCommon.FireRating=2HR` · `IfcElement, material=concrete`. Matches can be **isolated in 3D**
or **saved as a reusable selection set**. This is the power-selection primitive that bulk edits, schedule
scoping, and (next) rule-driven detail/spec attachment all build on. Engine `query_elements` in `edit.py`;
`GET /projects/{id}/query`. `test_selector.py` green (class, multi-class union, pset-value filter, limit
truncation, invalid-query 400).

## v0.3.254 — Wave 10 · W10-8: element phasing

The renovation / demolition-sequencing dimension needed for as-built and phased models. A new **🕐 Phasing**
tool (Grid &amp; Levels) tags elements **new · existing · demolish · temporary** — writing the widely-used
`Massing_Phasing.Status` code (NEW/EXISTING/DEMOLISH/TEMPORARY) so it colours, filters, and round-trips:

- Tag the selected element, or bulk-tag any saved selection set, from a one-click phase palette.
- A phase-distribution overview (counts + bars per status, plus unphased).
- **Isolate a phase in 3D** — pick a status to isolate just those elements.

Re-tagging updates the status in place (no duplicate pset); stale GUIDs are skipped; all GUID-stable. Engine
`set_phase` / `phase_summary` in `edit.py`; `set_phase` recipe + `GET /phasing`. `test_phasing.py` green.
(Design options reuse the W9-3 IFC5 property-override layers already shipped.)

## v0.3.253 — Wave 10 · W10-3: groups, assemblies & arrays

Three IFC-native ways to compose placed elements, all GUID-stable, via a new **🧩 Groups &amp; arrays** tool
(Grid &amp; Levels):

- **Group** (`IfcGroup`) — a named, non-geometric *set* of elements (a saved selection / system you can name,
  isolate, schedule). Members keep their own spatial containers; re-using a name adds to the group. Build one
  from any saved selection set; right-click an existing group to dissolve it (`ungroup`, members untouched).
- **Assembly** (`IfcElementAssembly`) — a real *part-of* whole: a named element that aggregates its parts
  (a braced frame, a curtain-wall unit, a pre-cast panel). The assembly is spatially contained; its parts hang
  under it via `IfcRelAggregates`.
- **Array** — rectangular parametric duplication: copy the selected element on an nx × ny grid at a fixed
  pitch (a bay of columns, a run of fixtures) in one action. Arrayed copies are independent occurrences —
  they don't silently swell the source's group or double-aggregate its assembly.

Existing groups/assemblies are listed with member counts; clicking one **isolates its members** in 3D. Engine
in `groups.py`; `create_group` / `create_assembly` / `array_element` / `ungroup` recipes + `GET /groups` and
`/groups/{guid}` inspectors. `test_groups.py` covers the relationships, inspectors, and recipe path.

## v0.3.252 — Wave 10 · W10-1: first-class type/family system

The box-only type path is now a real **family type system** — the Revit "type properties" surface, IFC-native.
A new **🧱 Family types** tool (Grid &amp; Levels) browses every `IfcTypeProduct` with its placed-occurrence
count, and lets you:

- **Create a custom type** — any type class, an optional sized box, a PredefinedType, and type-level
  property sets (`create_type`). Idempotent by (class, name).
- **Edit a type's size** — and the change flows to **every placed occurrence at once**. Occurrences share
  the type's `RepresentationMap` (via `IfcMappedItem`), so `edit_type_params` mutates the one box solid in
  place — GUID-stable, no re-placement, no lost pins/RFIs.
- **Assign a material layer set** — an ordered `IfcMaterialLayerSet` (name + thickness per layer) that
  occurrences inherit through the type (`assign_material_set`); re-assigning replaces cleanly.
- **Inspect** a type — class, PredefinedType, box dims, type Psets, material layers, and its occurrences.

All three edits run through the versioned, GUID-stable `/edit` recipe path and reconvert. This deepens the
existing `families.ensure_type`/`place_type` spine (shared box-representation builder) into the foundation the
rest of Wave 10 (parametric generators, groups, MEP systems, schedules) stands on.

## v0.3.251 — Wave 9 · W9-2b: round-trip code findings to BCF

The computed occupancy/egress findings can now become **trackable BCF issues** — a "📌 Promote to BCF
issues" button in the Occupancy &amp; egress result turns each below-min door, egress shortfall, and
two-exits-required space into a `codecheck` **BCF topic** (anchored at the element / building, so it shows
in the Issues panel and round-trips via `.bcfzip` with other openBIM tools). Idempotent — re-running a
review replaces the prior code findings rather than piling up. `POST /codecheck/egress/bcf`. Verified
live: an egress-shortfall finding becomes an anchored topic in the Issues list. (Completes W9-2's
"round-trip to BCF"; fire-separation between occupancies still needs space-boundary geometry and stays a
follow-up.)

## v0.3.250 — Wave 9 · W9-5: site logistics on the 4D timeline (first step)

SYNCHRO-style **site logistics** without leaving openBIM. New **🏗 Site logistics** tool places temporary
construction resources — cranes (with a reach ring), hoists, laydown yards, gates, fencing, haul routes,
trailers, parking — in project coordinates, each with a **schedule window**. They render as lightweight
3D glyphs and **time-phase on the timeline**: pick a date and only the resources active then are shown,
so the site plan becomes a constructability + safety rehearsal. `logistics.py` (`state_at` + `summary`) +
`Project.site_logistics` + `/logistics` (GET/PUT) + `/logistics/state` + a `LogisticsOverlay` +
`test_logistics.py`. Verified live: 3 resources → all active mid-schedule, only the open-ended gate after
the crane/laydown windows close; overlay renders glyphs + time-phases visibility. (The static, time-phased
first step; smooth **motion along paths** + swept crane-reach clash is the deferred follow-up.)

## v0.3.249 — Wave 9 · W9-6: generative fit-out (auto-furnish)

Generative design extends from massing into **fit-out**. New **🪑 Furnish spaces** tool (Tools ▸ Grid &
Levels) grids real furniture (`IfcFurnishingElement`) into every `IfcSpace`'s footprint with aisle
clearances — pick a template (desk / table / bed / sofa) and a per-room cap (0 = fill the footprint). It
reads each room's actual geometry, places items on a clearance-aware grid, and contains them in the right
storey, so the furniture is real openBIM that flows into QTO / BOM / COBie. `furnish_spaces` recipe +
`test_fitout.py`. Verified live: a blank 2-storey model → 8 rooms → 432 desks placed end-to-end. (The
headcount-program office space-planning generator is a documented follow-up.)

## v0.3.248 — Wave 9 · W9-4: semantic model graph (v1)

The property index answers attribute lookups ("this door's width"); it can't answer **relational**
questions. New **🕸 Related elements** tool builds a typed graph straight from the model's own IFC
relationships (`contained_in` · `aggregates` · `bounds` · `has_opening` · `fills` · `serves`) and, for
the selected element, returns its **multi-hop neighbourhood with cited relationship paths** — e.g. a wall
→ its level → everything else on that level. Click any related element to select it in 3D. `graph.py`
(`build` + `neighbors`) + `/graph` (stats) + `/graph/neighbors` + `test_graph.py`. Verified live: 117
nodes / 116 edges on a federated model; a wall reaches 38 related elements within two hops. (First,
model-half slice — spec/code-document ingestion and NL→graph query are a deliberate follow-up.)

## v0.3.247 — Wave 9 · W9-3: IFC5-style property-override layers

Brings IFC5's compositional model to the data layer **today**, without waiting on the upstream geometry
alpha. New **🧬 Property layers** tool: build an ordered stack of named, non-destructive **overlay
layers** (base → discipline → coordination → override), each carrying `{guid, pset, prop, value}`
overrides added from the selected element. They **compose over the model without mutating the IFC** — the
strongest enabled layer wins, disagreements surface as **conflicts** (the data-world twin of clash
detection, with provenance and both values), and **Resolve** shows the effective value + what it
overrides. **Bake** flattens the composition into a new GUID-stable IFC version (so pins/RFIs/clashes
survive) and republishes. `layers.py` engine + `Project.prop_layers` column + `/layers` (GET/PUT),
`/layers/resolve`, `/layers/bake` + an `apply_layers` recipe + `test_layers.py`. Verified live: a two-layer
FireRating conflict resolves to the coordination layer's "2HR" and bakes onto the wall.

## v0.3.246 — Wave 9 · W9-2: occupancy load + egress capacity (computed)

Code-checking goes from *presence* to *computation*. New **🏛 Occupancy & egress** tool (Coordination &
QA) computes, straight from the model's IfcSpaces + IfcDoors: **occupant load** per space (IBC 1004.5
area-per-occupant factors by occupancy — Business 1:150, Assembly 1:15, Residential 1:200, …) and the
building total; **required egress width** (occupant load × 0.15 in, IBC 1005.3) vs the **provided**
egress-door width, with an adequate / short verdict; a **32 in minimum clear door** check (IBC 1010.1.1)
with click-to-isolate; and a **two-exits-when-load->49** flag (IBC 1006.2), all with cited sections. It's
a **pre-check / design assist**, not a certified review (thresholds are encoded, not ICC prose; travel
distance is out of scope). `codecheck.egress_analysis` + `codecheck.egress_from_model` +
`/codecheck/egress` + `test_codecheck.py` extended. Verified live on a 40-space model (344 occupants,
required 51.6 in egress).

## v0.3.245 — Wave 9 · W9-1: property mapping / normalization

The missing **transform** verb between IDS-validate and COBie-export. Federated models name the same
concept differently (`Pset_WallCommon.FireRating` vs a vendor's `Fire_Rating`); IDS flags the mismatch
but nothing fixed it. New **🔧 Normalize properties** tool (Coordination & QA): **detect** every
pset/property actually on the model (with counts + samples), build remap **rules** (source Pset.Prop →
target Pset.Prop, with type coercion and move/copy semantics), **preview** the match counts (dry-run),
then **apply** — a GUID-stable `map_properties` edit recipe rewrites the IFC and republishes, so pins /
RFIs / clashes survive. `propmap.py` engine + `/propmap/detect` + `/propmap/plan` endpoints +
`test_propmap.py`. Verified live: `Pset_WallCommon.ThicknessMm` → `Qto_WallBaseQuantities.Width` across
12 walls (source removed, target written, GUIDs preserved). First item of the Wave 9 research scan.

## v0.3.244 — Mobile UX polish (phone-viewport touch targets + nav)

Tuned the header for phones (≤560px): the workspace switcher becomes its own **horizontally-scrollable
row** (five tabs no longer wrap onto two cramped lines), header controls get **tappable ~36–40px touch
targets** (were 22–28px), and the ~200px project-name switcher is **clipped with an ellipsis** so the
project actions pack onto one line. Net: fewer, bigger, easier-to-hit controls and a cleaner nav — the
topbar drops from six cramped rows to five tappable ones, with no horizontal overflow. The verifiable
web/PWA slice of the mobile track (native iOS/Android builds still need a macOS+Xcode / Android-SDK CI
pipeline — see docs/mobile.md).

## v0.3.243 — RVT→IFC (APS) bridge hardening

The paid Autodesk Revit→IFC bridge is hardened: the `/import/rvt` endpoint now **validates input before
the cost gate** — a non-`.rvt` file or an empty upload is rejected with a 400 rather than proceeding
toward a billed conversion — and a new **`test_aps.py`** locks the full gate order (501 bridge-off →
400 wrong-type → 402 unconfirmed-cost → 400 empty → 502 stub-activity). The conversion itself remains a
correctly-gated stub: it can't be implemented generically (the Design Automation WorkItem arguments
depend on the operator's provisioned Activity), so it raises a clear "provision your Activity" error
instead of faking output. The free path (export IFC from Revit, or the pyRevit **Publish to Massing**
button) stays the recommended route.

## v0.3.242 — Command-center density toggle (compact / comfortable)

The role home dashboards (GC executive band, Developer/Finance/Design command centers) get a
**⊞ Comfortable / ⊟ Compact** toggle. Compact tightens card padding, grid gaps and KPI type so more of
the dashboard fits on one screen — no information is removed, just the whitespace. The choice persists
globally (a personal viewing preference, like the per-stage nav collapse memory). Clears the last
open item in the roadmap's UX/nav-density bucket.

## v0.3.241 — Modeling program, phase 5: edit-in-place (drag-to-move gizmo)

Elements can now be **moved by dragging**, not just by typing an offset. Turn on **Edit in place** (◈
in the model toolbar), select an element, and a Blender/Revit-style **transform gizmo** appears on it
with X / Y / Z handles; a translucent amber **ghost box** follows the drag for instant feedback, and a
live ΔE / ΔN / ΔZ readout shows the move. On release the world-space delta is mapped to the GUID-stable
`move_element` recipe and the model republishes — so the moved element keeps its identity and every link
(RFIs, issues, verifications) to it survives. Grid-snap applies to the drag; the gizmo re-attaches to the
element after the move so you can nudge it again. Camera orbit is suspended while a handle is dragged.

Verified live against the loaded federated model: the gizmo constructs, attaches its ghost, cleans up on
hide/dispose, and the world→recipe axis remap is correct (Δx→E, −Δz→N, Δy→Z). This completes the
in-browser modeling initiative's tracked backlog (P1–P6 + model browser, manage levels, selection sets,
and edit-in-place). Stretch/resize of parametric geometry remains a future enhancement.

## v0.3.240 — Modeling program: manage levels + named selection sets

Two model-management tools land in the rail. **Manage levels** (Tools ▸ Grid & Levels) lists every
storey with editable **name** and **elevation** fields — Save re-authors the IFC through the GUID-stable
`rename_storey` / `set_storey_elevation` recipes and republishes, so levels are finally editable, not
just addable. The storey listing now carries each level's **GUID** so edits target the right storey.

**Named selection sets** (Layers panel, the Navisworks / Bluebeam "search set" pattern) let you save a
search — by name, IFC class, type, discipline, or level — as a named set and **isolate** it in one click;
"Show all" clears the isolation. Sets persist per-project in the browser (a personal view aid, they never
touch the model). Verified live on a 108-element federated model: a "structural" set resolves to 75
elements, all 75 map to loaded fragment geometry and isolate, and show-all restores visibility.

## v0.3.239 — Modeling program: model-browser groupings + search

The model tree is now a proper **model browser**. A toolbar adds a **group-by** switch — **By level**
(the spatial default), **By discipline** (A/S/M/P/E/FP, using the index's own discipline classification
with an IFC-class fallback), **By IFC class**, and **By type / family** (instances under their type, the
Revit Project Browser view) — and a **search box** that filters every leaf by name, GUID, class, type,
or discipline across all groups, auto-expanding the branches that match so hits are visible without
hunting. Each group header shows its element count; clicking a leaf still selects by GUID.

Verified live against a 108-element federated model: all four groupings render with correct counts
(Structural 75 · Mechanical 24 · Plumbing 6 · General 3), searching "duct" narrows to the 6 matching
segments and auto-expands, clearing restores the full tree, and leaf clicks fire the GUID selection.

## v0.3.238 — Modeling program, phase 6d: docked Properties panel (Revit-style)

Properties used to appear in a **floating** aside on selection; it's now a **docked rail panel** — its own
📋 **Props** toggle in the Author cluster — the way Revit's Properties palette works. The panel leads with a
**Revit-style identity header**: the element name, its **Type** (the family/type it's an instance of), and
its class + level, above the instance parameters and property sets (attributes / quantities / editable
Psets / classification, all unchanged). When nothing is selected it shows a clear "select an element" prompt.
Esc / the ✕ clears the selection.

Verified live: the Props toggle appears in the Navigate / Author / Coordinate rail, the panel docks and
shows its empty-state, no console errors. Completes the rail's Author cluster (Tools/Draft + Properties).
Part of the left-rail redesign; the model-browser groupings, level rename, selection sets, and edit-in-place
are still open (see the roadmap).

## v0.3.237 — Modeling program, phase 6c: cluster the rail Navigate / Author / Coordinate

The left rail's toggles are now grouped into the three workflow clusters every reference tool uses (Revit,
BlenderBIM/Bonsai, Bluebeam): **Navigate** (Tree · Layers) · **Author** (Tools) · **Coordinate** (Clash ·
Issues), with a subtle divider/label between them (a thin rule in icon mode, the cluster name when the rail
is expanded). Each toggle's aria-label is prefixed with its cluster for screen readers. This completes the
core of the rail redesign — the model workspace now reads as a modeling+coordination cockpit rather than a
flat list of panels. Verified live: the three cluster labels render and grouping is correct.

## v0.3.236 — Modeling program, phase 6b: a dedicated Clash & coordination toggle

The clash/coordination engine was genuinely strong but **buried** inside a "Coordination & QA" accordion in
the Tools panel. It's now a **first-class rail toggle** (💥 Clash), modeled on Autodesk Model Coordination —
the left rail is now Tree · Layers · Tools · **Clash** · Issues.

The panel surfaces tools that already ship: **Run clash — all disciplines** (federated cross-discipline
across the layered models, with coordination KPIs — new / active / resolved / % reduction), a
**single-model check** (structure ✕ MEP/walls) for a model without appended disciplines, a **clash list**
where clicking a clash selects + zooms to it in 3D, **Coordination metrics** (open/closed, resolution rate,
by-discipline-pair, by-severity, reappearance), and **Open in Issues (BCF)** — every clash promotes to a
tracked issue. Backed by `/clash`, `/clash/federated`, `/clash/metrics`.

Verified live end-to-end: the Clash toggle appears, the panel builds, and a single-model check on a
framed+cored model found **1,422 clashes and created 200 BCF issues**. Phase 6b of the left-rail redesign;
next: a docked Properties panel (Revit-style type/instance) and Navigate/Author/Coordinate icon clustering.

## v0.3.235 — Modeling program, phase 6a: cut the duplicative rail sections

Starting the left-rail redesign (a modeling+coordination cockpit, grounded in how Revit, BlenderBIM/Bonsai,
and Bluebeam lay out their panels). The Model workspace's "Tools" panel had become an 11-section dumping
ground, four sections of which **re-plotted whole other workspaces**: Cost/Pay Apps, Schedule, Drawings (2D),
and Energy & MEP. A modeler coordinating geometry shouldn't scroll past pay-app tables to reach a tool.

Removed those four from the model rail — and deleted ~700 lines of their now-duplicate builder code — leaving
a compact **deep-link row** (💰 Cost → Construction · 📅 Schedule → Construction · 📐 Drawings → Drawings ·
⚡ Energy → Design) so they're one click away without cluttering the modeling surface. Nothing is lost from
the product; each still owns its real workspace. The rail now keeps only model-native tools: the Draft
authoring palette, Grid & Levels, Working origin, Models (federation), round-trip authoring, Coordination &
QA, and Exports.

Next in the redesign: a dedicated **Clash** toggle (surfacing the existing clash/coordination engine), a
docked **Properties** panel (Revit-style type/instance split), and re-clustering the rail icons
Navigate / Author / Coordinate.

## v0.3.234 — Modeling program, phase 3: author rooms/spaces

The backend `add_spaces` recipe (grid IfcSpace rooms over each floor's footprint) had no UI — you could
author walls and columns but not the **rooms** that drive the space schedule, COBie, gbXML, and area
take-offs. Added an **"➕ Add rooms / spaces"** button to the Grid & Levels section (next to the existing
"➕ Add level"): pick rooms-per-floor + ceiling height and it authors a real space schedule into the model.
Verified live: `add_spaces` authored 8 IfcSpace rooms (4 per floor × 2 floors) on a generated shell. With
level-add already present, the datum/space authoring gap the modeling audit flagged is now covered in the
UI. (Level rename / set-elevation deferred — they need per-storey GUID plumbing.) Phase 3 of the modeling
upgrade; next: edit-in-place (drag/stretch).

## v0.3.233 — Modeling program, phase 4: author-ready starting templates

The old sample models were three static `.frag` files you could only *look at* — they load without a
project, so authoring is impossible on them. The "New model from scratch" flow now opens a **template
picker** with four **author-ready** starting points, each opening as a real, editable IFC project in the
Model workspace with the Draft tools ready:

- **▦ Blank canvas** — 3 levels + a ground datum; draw everything from scratch.
- **🏢 Office bay** — a small framed structural bay (columns + beams + envelope) over 3 levels.
- **🏠 Residential floor** — one floor, double-loaded corridor with unit demising walls.
- **🏭 Warehouse shell** — a large single-storey enclosed clear-span shed to fit out.

Blank uses `…/model/blank` (P1); the rest are presets through the existing massing generator, so they
produce real geometry you then edit — not a locked demo. The picker is an accessible dialog (focus-trapped,
Esc). Verified live: the picker shows all four; the office-bay template generates a published, framed
3-storey editable model in ~1 s. (The static School/BasicHouse samples stay in the Open menu as view-only
reference.) Phase 4 of the modeling upgrade; next: grid/level/space authoring UI and edit-in-place.

## v0.3.232 — Modeling program, phase 2: remove the redundant authoring buttons

Killing the "excess buttons" from the audit. The viewer toolbar had **two ways to place the same element** —
the parameter-driven, snapping, per-level **Draft panel** (the real one) *and* an older click-to-place set
of toolbar buttons (Add wall / Add column / Add beam / Place family) that popped `prompt()` dialogs for
dimensions. The toolbar four were a redundant, clunkier duplicate of what the Draft panel does better, so
they're removed along with their whole legacy code path — `setPlaceMode`, `capturePlacePoint`,
`openFamilyPicker`, and the generic `pickFromList` picker (~90 lines). The Draft panel is now the single
authoring surface (as of P1 it opens front-and-centre on a new model).

The genuinely useful **selection-based** edit buttons stay (delete · add door/window to a selected wall ·
move · rotate · edit property · copy) since the Draft panel doesn't cover those. Net: fewer buttons, one
clear way to draw, no behaviour lost. Verified live: the four place buttons are gone, the selection-edit
buttons remain, and authoring via the Draft panel is unchanged. Phase 2 of the modeling upgrade; next: an
explicit Author/Review tool grouping, then grid/level/space authoring UI.

## v0.3.231 — Modeling program, phase 1: start a model from scratch

**A direction change: the web app becomes a real modeling tool, not just a viewer.** The audit was blunt —
the Model workspace was ~80% viewer/analysis, authoring was buried in an edit-gated Tools-rail sub-panel,
and there was **no way to start a model from nothing** (authoring required an existing IFC). The engine was
never the problem — the backend already has a ~30-recipe GUID-stable IFC authoring API (walls, columns,
steel, rebar, MEP, coverings, families, storeys, spaces, transforms). This ships the missing foundation.

- **Blank model from scratch.** New `generate_blank_ifc` + `POST /projects/{pid}/model/blank` author a
  minimal valid IFC — project/site/building, N **levels** (the datum you draw against), and a thin
  **ground-reference slab** for scale — with no building geometry. `POST` sets it as the source IFC and
  publishes it, so authoring works immediately.
- **"✏️ New model from scratch" flow.** One action creates a project, authors the blank model, lands you in
  the Model workspace, and **auto-opens the Draft/authoring panel** (`viewer.openAuthoring()`) so the
  drawing tools are front-and-centre instead of hidden. In the Open menu.
- Verified end-to-end against a live backend: new model → blank IFC published in ~1 s → Draft panel opens
  with the full element palette → an `add_wall` recipe authors a real wall with a stable GlobalId.

`CLAUDE.md` updated to make in-browser authoring a first-class goal (Blender/Bonsai becomes optional/interop,
not the required editor). This is phase 1 of a multi-release modeling upgrade — next: declutter the toolbar
into Author vs Review modes and remove the redundant legacy buttons; grid/level/space authoring UI;
author-ready templates; and edit-in-place (drag/stretch). Test: `test_generate` (blank model → 4 levels at
the requested height, ground datum only, valid spatial structure to author into).

## v0.3.230 — Collapsible nav stages with per-workspace memory

The left-nav destination rail groups first-class destinations by lifecycle stage (Plan & derisk · Build ·
Turn over · …). Those stage headers are now **collapsible** — fold a stage you don't use and it **stays
folded** next time you're in that workspace (persisted per `workspace:stage` in localStorage), so the rail
stays scannable as destinations keep growing. Each stage is a `<details>` with a disclosure caret; the
stage that owns the active destination always stays open regardless of the saved state, so you never lose
your place. Verified live: folding a stage persists and restores on return to that workspace, and other
stages are unaffected.

*(The "denser multi-card dashboard summary" half of this nav-density item remains a smaller follow-up.)*

## v0.3.229 — Accessibility pass on the new panels

An a11y audit of the panels added this cycle — the Finance command-center home, the module-relations
graph, the material editor, and the takt actual-vs-plan card — closing the gaps that screen-reader and
keyboard users would hit:

- **Named the graphics.** The module-relations SVG and the takt line-of-balance chart now carry
  `role="img"` + an `aria-label` (and the graph a `<title>`) describing the content — e.g. "Module-relations
  graph: 124 modules, 111 links" — instead of being an unlabeled blob. The Finance capital-stack bar gets an
  `aria-label` with the debt/equity split.
- **Labeled every form control.** The material editor's per-class colour, transparency, and name inputs and
  the graph's workspace filter now have `aria-label`s (previously anonymous); the material and takt data
  tables use `scope="col"` headers.
- Added a reusable `.sr-only` utility for visually-hidden accessible text.

All controls were already native buttons/inputs/selects (keyboard-reachable) — the gap was accessible
*names*, which are now present. Verified live: the graph SVG and all material inputs expose their labels.

## v0.3.228 — Finance home: a command-center landing for the finance persona

The Finance workspace opened straight into the proforma editor; now it lands on a **command center** —
the same pattern the Design and Developer personas already have. A new default **Home** tab (alongside
Proforma and Portfolio) summarizes the deal's financial picture: the returns from the latest saved
scenario (equity IRR — tinted good/warn by threshold — equity multiple, project IRR, yield on cost, NPV),
a **capital-stack bar** (senior debt vs equity with the split and a sources-≠-uses warning when it doesn't
balance, from Sources & Uses), and quick-launches to the Proforma editor, the Portfolio roll-up, and the
investor **memo** and **pitch-deck** PDFs. Everything degrades to a clear empty state before a scenario is
solved.

With this, all three non-GC personas have a role-tailored landing (Design = model-health/phase-progress,
Developer = real-estate register + deal returns, Finance = returns + capital + investor docs); the GC keeps
its on-schedule/on-budget PX dashboard.

New `listScenarios(pid)` client method + `openFinanceHomeTab()` in `main.ts`; a Home fintab in the finance
workspace. The home renders its **shell synchronously** (header, KPI placeholders, and the quick-launch
buttons) before the returns/capital data loads — so the panel is never blank even if the data request is
slow, offline, or fails; the returns and capital stack fill in afterward. Verified live: the shell appears
immediately, the capital stack renders from project Sources & Uses, the empty-state shows before a
scenario, and the quick-launches switch tabs / open the PDFs.

## v0.3.227 — Investor pitch deck, expanded: exec summary + capital stack + business plan

The generated investment **pitch deck** (`/investment-deck.pdf`) grew from 6 to **9 slides** toward a real
investor deck, all from the same live project data. Three new slides: an **Executive summary** (the thesis
in prose — total capitalization, the equity ask, the underwritten IRR/multiple over the deal horizon — plus
three headline metrics and highlights); a **Capital stack** (a stacked bar of senior debt vs equity with
loan-to-cost and the equity check, a clearer read than the Sources & Uses table); and a **Business plan &
value creation** slide that frames the **development-margin thesis** — build yield-on-cost vs the exit cap,
with the spread in bps as the value the development creates — followed by the entitle → build → stabilize →
exit strategy. Everything degrades gracefully when no proforma scenario is saved.

The deck now runs: title · exec summary · deal-in-numbers · market & positioning · Sources & Uses · capital
stack · development timeline · business plan · returns & the ask. Landscape, big-number slides, with site
photos from project attachments on the cover.

`report.investment_deck_pdf` in `report.py`. Test: `test_dev_budget` — the deck renders and now has 9
slides (was 6). Completes the §B6 developer-deliverable item (the memo + deck already shipped; this deepens
the deck to the roadmap's 10–20-slide investor-deck target).

## v0.3.226 — Module-relations graph: see how the ~180 config modules wire together

The config-driven modules form a data model; now you can see its shape. New `module_graph.build(registry)`
reads the module registry back as a graph — one node per module, one edge per cross-module link — where
edges come from **reference** fields (a record points at another module's record) and **rollup** fields (a
module aggregates a numeric field from records that point at it). Each node carries its in/out degree, and
the result surfaces the **most-referenced hubs** (the cost code tops it, referenced by ~23 modules) and the
**orphans** with no links. A `workspace` filter keeps a workspace's modules + the targets they reference so
the full ~180-node graph stays legible. Pure over the registry — no database.

Endpoint `GET /modules/graph?workspace=` returns the graph. A **🕸 Module Relations** destination in the
Design workspace renders it as an SVG: nodes on a ring laid out by workspace/section, sized by in-degree so
hubs stand out, reference edges solid and rollup edges dashed, hubs labelled, with a workspace filter and a
most-referenced summary. Hover any node for its links.

Engine `module_graph.py`; `routers/modules.py` endpoint; `portal/panels/moduleGraph.ts`. Tests:
`test_modules` — every module is a node, cost-impact reference edges target cost_code, cost_code tops the
in-degree ranking and its node degree matches its edges, workspace scope is a subset, only reference/rollup
edge kinds. **Completes the §M rendering/computational-depth bucket** (material editor v0.3.225 + this).

## v0.3.225 — Material editor: a per-project palette you can edit and re-apply

The M1 material/colour assignment (each IFC element class → an IfcMaterial + IfcSurfaceStyle colour, so
the model renders in real materials instead of flat grey) is now **editable per project**. New palette
helpers — `materials.palette_to_json()` / `palette_from_json()` / `merge_palette()` — expose the built-in
per-category table as JSON and let a project override any class's material name, category, colour, or
transparency; only the changed classes are stored, the rest fall back to the default.

Endpoints (design router): `GET …/materials/palette` returns the default table, the saved overrides, and
the **effective** merged palette; `PUT …/materials/palette` persists overrides to project storage; and
`POST …/materials/apply` loads the source IFC, re-runs the material/surface-style assignment with the
merged palette (in a tempfile — `/app` is read-only in prod), writes it back, and kicks the
convert→fragments reindex so the viewer shows the new colours. A **🎨 Materials** destination in the Design
workspace's Model & standards group renders the editable palette table (colour picker + transparency +
material name per class) with Save, Apply + republish, and Reset controls.

Engine `services/data/aec_data/materials.py`; `routers/design.py` endpoints; `portal/panels/materials.ts`.
Tests: `test_design_phase` — GET returns default + effective, PUT persists an override, GET reflects it
(unchanged classes keep the default), apply 400s with no source model.

## v0.3.224 — Actual-vs-takt production tracking: the LOB chart learns the real ascent

The line-of-balance takt plan (trades chasing floor-to-floor at a steady rate) now measures **actual
against plan**. New `takt.progress(plan, actuals)` compares each trade's actual floors-complete with the
floors it *should* have finished by that day, giving a **floor variance** (+ahead / −behind), the
**achieved production rate** (floors/week) vs the planned rate, and an on-takt / ahead / behind read for
each trade and the job overall. The lead trade's achieved rate vs the planned pace is the headline: is the
train ascending at takt? `takt_svg` gained an **actuals overlay** — each trade's real ascent drawn as a
dashed line against the solid plan, so plan-vs-actual reads at a glance.

Project endpoint `GET …/schedule/takt/progress` derives per-trade floors-complete from the GC
`schedule_activity` records (100% complete or an actual finish date), sizes the takt plan from the model's
storey count, and **bundles PPC** (Last-Planner reliability) so one payload drives a dashboard card showing
plan health + reliability together; `GET …/schedule/takt.svg` renders the overlaid chart; and a stateless
`POST /schedule/takt/progress` computes it from posted actuals. A **"Takt — actual vs plan"** card in the
Schedule panel shows the overlaid chart + a per-trade variance table (done/plan, variance, actual vs planned
floors/week) + overall status + PPC.

Engine `takt.progress()` + `takt_svg(actuals=…)`; `routers/research.py` endpoints; Schedule-panel card.
Tests: `test_research` — variance sign (ahead/behind/on-takt), achieved-rate math, overlay drawn, unknown
trades ignored, plus the project endpoint (floors-done from activities, clamped to storeys, PPC bundled) +
stateless endpoint. Closes the §R2/R4 production-analytics thread (planned LOB + JIT already shipped).

## v0.3.223 — Monte-Carlo the specialty risk discount → distribution of blended deal IRR

Closes the §U4 thread. The specialty **risk discount** (the U4 haircut that keeps a farm/energy operating
business from being underwritten like de-risked real estate) is now a **Monte-Carlo driver**, not a single
point. New `specialty.monte_carlo()` samples specialty params (`risk_discount`, produce prices, any dotted
path) across a distribution (normal / uniform / triangular, optionally clamped), blends each draw into the
deal's equity, and returns the **distribution of blended deal IRR and specialty-only IRR** — percentiles
(P5…P95), mean/std, P[metric ≥ target], and a histogram. It reuses the proforma Monte-Carlo sampler +
summary, so the readouts match the rest of the risk tooling, and it's reproducible under a fixed seed.

Answers the real question: *once the haircut and price volatility are uncertain, how much does the
farm/energy actually help — and how often does it hurt?* A harsher haircut band measurably lowers the
blended-IRR distribution. Endpoint `POST …/specialty/monte-carlo` (assumptions + variables + iterations +
targets); a **"Risk sim"** button in the Specialty panel runs 500 draws and shows the blended-IRR P5/P50/P95
+ P[≥15%] and the specialty-only spread.

Engine `specialty.monte_carlo()` (reuses `proforma.monte_carlo._sample`/`_summary` +
`proforma.sensitivity._set_path`). Tests: `test_specialty` — ordered percentiles + histogram, seed
reproducibility, target-probability readout, harsher-haircut → lower blended IRR, plus the endpoint
end-to-end. **The full §U underwriting-depth bucket (exit-cap comps · specialty P&L + ramp · blended IRR ·
Monte-Carlo risk) is now cleared.**

## v0.3.222 — Specialty assets modelled over time: multi-year P&L + production ramp + blended IRR

The on-site energy/vertical-farm business is now underwritten as an **operating business over time**, not
a single stabilised year. New `specialty.proforma()` runs a multi-year P&L where revenue and generation
**ramp** linearly from a start fraction to full output over `ramp_years`, while opex (grow-lights, labour)
runs at full load from year 1 — so the early years earn less, or lose money, before the business
stabilises (the honest picture of a startup ag/energy operation). It reports per-year rows (ramp %, revenue
+ offset, opex, net, cumulative), a **specialty-only IRR** (capex at t0, ramped nets, plus a terminal value
= stabilised net ÷ exit cap), and the payback year. All cash flows use the **risk-adjusted** (underwritten)
figures, so nothing is overstated.

New `specialty.blended_irr()` folds that business into the deal's **equity** cash flows and reports
**real-estate-only IRR vs blended IRR and the lift** — the answer to "does the farm/energy actually move
the deal return, net of its risk discount?" Endpoints `GET …/specialty/proforma` (query: years, ramp_years,
ramp_start, terminal_cap) and `POST …/specialty/blended` (solves the RE proforma from the posted
assumptions, then blends the saved specialty params). A **"P&L + ramp"** view in the Specialty panel charts
the year-by-year table, the specialty IRR/payback/terminal, and the blended-deal IRR lift.

Engine reuses the robust `proforma.returns.xirr`. Tests: `test_specialty` — ramp fractions + net rising to
the stabilised plateau, terminal = net ÷ cap, payback, slower ramp → lower IRR, blended lift + guards,
plus both endpoints end-to-end. *(Remaining §U4 thread: wiring Monte-Carlo sensitivity to the specialty
risk discount — next.)*

## v0.3.221 — Surface parking placed on the real parcel remainder (polygon-aware)

Generated surface parking now fills the **actual land the building doesn't use** instead of a fixed
strip stamped behind the plate. New pure `pack_parking(poly, bldg_w, bldg_d, n, …)` lays stalls in
double-loaded modules (two 5 m stall rows sharing a 7 m two-way drive aisle), sweeping the parcel's
bounding box and keeping a stall only when its whole rectangle is **inside the parcel polygon** (ray-cast
point-in-polygon) **and clear of the origin-centred building footprint** (plus a 2 m drive-apron buffer).
`generate_ifc` recentres the parcel on its bbox centre to share the building's frame, then places the
packed stalls as real `IfcSpace(PARKING)` on the Site Parking storey. On an irregular or tight parcel the
supply is now **parcel-bound** — you get the stalls the site can actually hold, not the number requested,
which is the honest feasibility answer. Rectangular-lot inputs with no polygon keep the legacy strip
(unchanged). Completes the A6 remainder (the shoelace footprint + inward setback offset shipped earlier).

Engine `massing.pack_parking()` + `massing._point_in_poly()`; wired through `routers/generate.py`
(passes `metrics["buildable_polygon"]`). Tests: `test_massing` — packer keeps stalls inside a 60×60
parcel and off the building box, supply is parcel-bound (asking for 100 000 returns what fits), triangular
parcel clips corners, degenerate inputs safe; plus an end-to-end `generate_ifc(parcel_polygon=…)` placing
stalls clear of the footprint.

## v0.3.220 — Generated frame follows the load path: per-floor column taper + lateral core

The structural advisor now shapes the *generated geometry* floor-by-floor instead of stamping one fixed
column everywhere. A column at level _i_ carries the floors above it, so its axial load — and thus its
cross-sectional area — grows toward the base; side length scales with **√(floors carried)**, floored at
400 mm and rounded to 50 mm zones (real frames taper in bands, not continuously). The advisor returns a
per-floor `column_schedule` (base = widest, top = narrowest) plus `base_column_mm`/`top_column_mm`, and
`generate_ifc` extrudes each storey's columns at that storey's section, so a tall building visibly narrows
its frame as it rises.

Alongside it, a **central lateral core**: when the recommended lateral system is a core (mid-rise and up),
the advisor sizes a reinforced-concrete core (~20 % of the floorplate, min 6 m) with wall thickness that
grows with height for drift control (250–900 mm), and the generator extrudes the service-core walls as
real shear walls at that thickness — not the thin default. Low-rise buildings (distributed shear walls /
braced bays) correctly get **no** central core. Sized on the real footprint at generate time. The proforma
massing summary now shows the taper (`cols taper 900→500 mm`) and the core (`6×6 m core, 400 mm walls`).

Engine `structure.column_schedule()` + `structure.lateral_core()`; wired through `routers/generate.py`
into `massing.generate_ifc(members=…)`. Tests: `test_structure` (taper monotonic base→top, √-load, 400 mm
floor, core thickens with height, 1-storey edge case), `test_generate` (endpoint returns the schedule +
core), `test_massing` (generated column X-extents taper 0.90→0.50 m; core walls extrude at 400 mm). Also
fixed a stale `test_massing` MEP assertion (the core adds a riser **and** a distribution main per floor).

## v0.3.219 — Desktop build: Windows installer (uvloop) — all three platforms now build

Final piece of the installer repair. With v0.3.218 the macOS + Linux installers built, but Windows
failed: `RuntimeError: uvloop does not support Windows`. `requirements.lock` is resolved on Linux (the
prod image + CI), so it pins the **Unix-only `uvloop`** (a `uvicorn[standard]` transitive) with no
platform marker — and it can't build on Windows. The desktop sidecar now installs the API deps from the
**unpinned `requirements.in`**, letting pip resolve per-platform: `uvicorn[standard]` drops uvloop on
Windows and keeps it on macOS/Linux. Prod reproducibility is unchanged — the hashed lock still governs
the API Docker image and the CI test gate; the desktop sidecar is a bundled per-platform binary. All
three installers (Windows `.msi`/`.exe`, macOS `.dmg`/`.app`, Linux `.AppImage`/`.deb`) now attach to
tagged releases.

## v0.3.218 — Desktop build: Python 3.12 to match the lock (completes the installer fix)

Second half of the desktop-installer repair. After v0.3.217 fixed the requirements *path*, the sidecar
step still failed: the workflow set up **Python 3.11**, but `services/api/requirements.lock` is
pip-compiled under **3.12** and pins `numpy==2.5.x`, which requires Python ≥3.12 — so 3.11 couldn't
resolve it (CI already uses 3.12, which is why CI stayed green). Bumped the desktop workflow's
`setup-python` to 3.12 to match CI and the lock. With v0.3.217's requirements-path fix, tagged releases
now build the Windows/macOS/Linux installers and attach them to the release.

## v0.3.217 — Fix the desktop-installer build (releases were empty drafts)

**Ops fix — restores the signed desktop installers on tagged releases.** The Desktop-release workflow's
"Build the backend sidecar" step still installed `services/api/requirements.txt`, which was renamed to
`requirements.lock` during the hashed pip-compile work (v0.3.198). Every tag since then failed that step
on all three platforms, so no Windows/macOS/Linux installers were built and each GitHub Release stayed an
**empty draft**. Fixed to install the hashed lock (`pip install --require-hashes -r requirements.lock`,
matching CI) and the un-hashed data reqs **separately** (pip forbids mixing hashed + un-hashed files in
one invocation). Also fixed the report-only `security.yml` pip-audit, which pointed at the same missing
file and so wasn't auditing the API dependencies at all. Tagged releases now produce installers again.

## v0.3.216 — Underwriting realism: validate the exit cap against sale comps

Deepens the underwriting guardrails (roadmap ① / §U). A going-out cap tighter than the market supports
silently inflates the reversion (value = NOI ÷ cap) and the whole IRR — the most common way a proforma
"pencils" on paper but not in reality. `underwrite.guardrails(result, comps=…)` now derives the
**cap-rate band from the deal's own `comparable` sale records** and flags the exit cap against it:
**high** when >50 bps below the tightest comp, **med** when below the band, **info** when inside it (and
silent when at/above the comp median — the conservative case). The solve result now surfaces `exit_cap`
in `returns`, and a new project-scoped **`POST /projects/{pid}/proforma/solve`** runs the comp-aware
guardrails; the Finance panel calls it automatically when a project is open, so the exit-cap flag appears
in the underwriting guardrails alongside the IRR/EM/spread/DSCR checks. Pure/backward-compatible: the
stateless `/proforma/solve` and no-comps projects are unchanged. `test_specialty` covers the band math
(high/med/info/silent), the rent-comp exclusion, and the end-to-end project-scoped endpoint.

## v0.3.215 — Test Fit yield optimization: plate-depth sweep + core-efficiency

Deepens the generative Test Fit optimizer (roadmap ① — deepest, highest-value bucket). **Plate depth is
now an optimize dimension.** `test_fit.optimize(…, depths=[…])` (or `targets.sweep_depth=True` for an
auto ×0.6–1.4 range) sweeps unit-mix × parking **× plate depth** and returns a **`depth_curve`** — the
best yield-on-cost, daylight efficiency, and core efficiency at each depth, plus the `best_depth_m` where
daylight-limited yield peaks **before a dark interior core starts eating rentable area** (Willis, *Form
Follows Finance*). New **`core_efficiency`** metric on every layout (share of the gross plate not lost to
the daylight-dark core — 1.0 on a shallow plate, falling as depth pushes area past the ~9 m daylight
reach), distinct from `efficiency` which also nets out the corridor. The Finance **📐 Test Fit** panel
gains a **"sweep plate depth"** toggle that renders the depth curve with the peak depth starred. Backward-
compatible: with no sweep the optimizer is unchanged (15 schemes, single depth). `POST /test-fit/optimize`
accepts `depths`; `test_testfit` covers the sweep, the curve, `core_efficiency`, and the shallow-beats-deep
daylight ordering.

## v0.3.214 — In-browser E57 reality-capture reader + roadmap consolidation

**In-browser E57 (ASTM E2807) reader.** E57 previously required an optional server-side `pye57`
conversion; now `.e57` laser scans decode **fully in the browser, offline** — honoring the
"viewer runs fully offline" non-negotiable. New `viewer/e57.ts` parses the 48-byte header, strips the
CRC-paged logical stream, reads the XML `Data3D` prototypes, and decodes the CompressedVector binary
for the common encodings (**Float single/double + ScaledInteger XYZ with optional RGB**, across one or
more data packets), centring on the bbox midpoint and stride-decimating to the render budget like the
LAS/LAZ path. Anything it can't decode raises a typed `E57Unsupported`, and `main.ts` **falls back to
the proven server converter** — so worst case is today's behavior, best case is no round-trip. Wired
through `referenceLoader` (new `e57` branch) and the Open menu. `e57.test.ts` builds synthetic E57
files (single-page, multi-page CRC-stride, ScaledInteger+RGB, Float) and round-trips them through the
reader. Closes the last data-layer item that was tagged "upstream-blocked."

**Roadmap consolidation.** `docs/roadmap.md` is now lean — the banner + a single, re-ranked
**"What's left"** master backlog (① generative-design depth · ② UX/perf · ③ interop spikes · ④
upstream-blocked · ⑤ deferred-by-decision · ⑥ non-goals), sweeping up every open item from every
archive/parking-lot section (A/U/R/M/L/D + each "*Next:*" sub-note). All shipped history moved to a new
**`docs/roadmap-completed.md`** so *what's left* is never buried under *what's done*.

## v0.3.213 — Two deferred items closed: capital-markets syndication connector + IFC5/IFCX write path

**(1) IFC5 / IFCX write path.** The IFC5 read path shipped earlier (tolerant JSON→element-index parser);
the write path was deferred as "waits on web-ifc / Fragments." That dependency only blocks *geometry*
authoring — the **data** layer (elements + property sets) is plain JSON and tractable now. New
`aec_data/ifc5_writer.py` inverts the reader: it serializes the model index to **ifcJSON**
(buildingSMART `{"type":"ifcJSON","data":[…]}`, full-fidelity — guid/class/name/type/storey + property
groups round-trip exactly) or **IFCX** (the OpenUSD-style node list; USD attributes are flat so property
groups collapse to one attribute set, values preserved). `GET …/model/export.ifcx?flavor=ifcjson|ifcx`
streams it; `openbim` now advertises **IFC5 in `ifc.write`** (not just read). `test_ifcx_write` round-trips
both flavors back through the reader and asserts the registry change. Geometry authoring still lands
upstream — this is the data write path, the inverse of what already reads.

**(2) Capital-markets syndication connector (ledger sync — never moves money).**
Closes the last deferred capital-markets item as a **flagged data connector** (the parcels/APS pattern):
export the investor cap table to a securitization / investor-management platform, without rebuilding the
regulated issuance stack. New `securities_bridge` serializes `capital.cap_table` into a neutral
**syndication package** (`schema: massing.syndication.v1` — fund summary + per-investor positions +
disclosures), served at `GET …/securities/package` and **always available offline** regardless of the
connector. When configured (`SECURITIES_PLATFORM_URL` + `SECURITIES_API_KEY`, admin-editable in
Settings), `POST …/securities/syndicate` pushes the package to the platform over stdlib `urllib` (a
generic authenticated REST target is implemented; named platforms raise an actionable error until wired).
**Scope guard — this connector never moves money:** it syncs the *ledger* (positions, ownership %,
recorded contributed/distributed totals) so the external platform's records match ours; capital calls,
distributions and transfers are executed by the licensed platform, not here. Every response carries
`moves_money: false` and the package a disclaimer. The Investors tab (proforma) gains a **Capital-markets
syndication** card: download the package JSON, see connector status, and sync when enabled. Status gate
uses `current_user`; the push requires **admin**. `test_securities_bridge` covers the disabled export,
the actionable 422, a stubbed generic push (positions only), and the unimplemented-target error.

## v0.3.212 — Cross-workspace deep-link (element → linked records) + FF&E classification
Two roadmap items. **(1) Reverse deep-link — element → linked records.** The portal already had the
forward direction (a record's "👁 Show in model" selects its tagged elements); the reverse was missing.
New `traceability.element_records(db, pid, guid)` scans every **pinnable** module and returns the records
tied to an element by GlobalId (its `element_guids` tag or `data.guid`) — RFIs, coordination issues,
change orders, field verifications, schedule activities, etc. — grouped by module. `GET
…/elements/{guid}/records`; the viewer's on-selection inspector now shows a **🔗 Linked records (N)**
section beside the 5D cost breakdown, so selecting an element in 3D surfaces every record that touches it.
Completes the record↔element round-trip. **(2) FF&E classification** (from the pics8 field scan): the
furnishing IFC classes (`IfcFurniture`, `IfcFurnishingElement`, `IfcSystemFurnitureElement`) now classify
to **MasterFormat Division 12 (Furniture / Furnishings — FF&E)**, so furniture takes off and procures
correctly — additive, no discipline-taxonomy change. `test_element_records` covers the cross-module
reverse lookup (a field-verification + an RFI on one element found across both modules) + the FF&E mapping.

## v0.3.211 — Model Health: one composite score over every model-quality check
The model-quality checks were spread across the Model Tools rail — Data QA, ISO 19650 KPIs, clash
coordination, verified-as-built — so a coordinator had to open four tools to know where the model stands.
New `model_health.py` **composes** them (it re-implements nothing) into a single **0–100 composite
score** with four graded lenses, each linking to the tool that acts on it: **integrity & hygiene**
(`model_qa` — duplicate GUIDs, overlaps, orphans, unenclosed, blanks, wrong-storey), **information &
delivery** (`bim_kpi` ISO 19650 KPI health %), **coordination** (`clash_intel` resolution rate), and
**verified as-built** (`verified_progress` verified-in-place % + trust gap). The composite is a weighted
mean over the lenses that have inputs; a lens with no inputs shows **n/a** and is excluded rather than
guessed, so the score is honest. New `GET …/models/health` (opens the source IFC for the hygiene lens
when present; the other lenses score from records + the published index, so it works without a parsed
model); a viewer tool **🩺 Model Health (all checks, one score)** heading the model-quality group with the
composite band + per-lens breakdown; and a Report Center **Model Health Scorecard** (PDF/Excel, health-by-
lens chart). `test_model_health` covers the composite math, the clean-model = hygiene-100 case, the
n/a-lens exclusion, and the HTTP endpoint. (Part C "first-class Model Health surface" — see `docs/roadmap.md`.)

## v0.3.210 — Wave 8 ③(b): schedule-linked verified-as-built progress (the trust gap)
Closes the last buildable Wave 8 item. Instead of trusting a self-reported "% complete", Massing now
rolls **element-level field verification** up to each schedule activity and surfaces the **trust gap** —
where the claimed percentage runs ahead of what has actually been verified in place (the OpenSpace /
Disperse / Buildots value proposition, done as pure software over the model we already hold). New:
- **`field_verification` module** — one GlobalId-anchored record per element, workflow = the verification
  state (`captured → verified / deviated → resolved`), with deviation (mm), method, photo and a link to
  its schedule activity.
- **`verified_progress.py` engine** — maps every element to the activity that builds it (the same hard-tie
  or class→trade→floor resolution as the 5D map), then computes per-activity **verified-in-place %** vs
  **claimed %** and the trust gap, worst-over-claim first, plus overall coverage. `seed_from_layout` turns
  an as-installed `layout.verify` result straight into verification records (in-tolerance → verified,
  out-of-tolerance → deviated); `layout.verify` now also returns the full per-point deviation list.
- **Endpoints** `GET …/verified-progress` + `POST …/verified-progress/from-layout`; a viewer tool
  **✅ Verified-as-built progress** (verified % vs claimed, trust gap, per-activity breakdown); a Report
  Center report **Verified-as-built Progress** (PDF + Excel, verified-vs-claimed chart). `test_verified_progress`
  covers the rollup math (claimed 80 % but 2/4 verified → 50 % verified, +30 trust gap), the class→trade
  fallback, the layout seeding, and the HTTP endpoint.

## v0.3.209 — Docs: Wave 8 in the in-app tutorial + the guide
Now that the Wave 8 field upgrades have shipped, the onboarding and guide teach them. `docs/guide.html`
gains **Tutorial 🛰️ · Coordinate, lay out & walk the as-built** (six steps: coordinate clashes into
grouped BCF issues, model-driven field setout CSV/DXF, the preliminary load takedown, the wrong-storey
model-QA check, the Construction Execution Plan, and the Gaussian-splat reality overlay) plus a nav link.
The in-app first-run **tour** copy is refreshed: the Open-model step now mentions point-cloud / GIS /
reality-capture overlays, and the Tools step names the field toolkit (coordinate clashes, field layout,
load takedown). Docs/tutorial only — no behavior change.

## v0.3.208 — Wave 8 ③(a): Reality-capture walkthrough (3D Gaussian splats) in the viewer
Walk the as-built reality against the design. The viewer now loads **3D Gaussian-splat** captures
(`.splat` / `.ksplat`, plus splat-PLY auto-detected by header) as a **view-only overlay** beside the BIM
model — the on-site phone/drone photogrammetry → splat that the 2026 reality-capture wave produces, co-
registered with the IFC and the LAS/LAZ point clouds we already read. Built on `@mkkellogg/gaussian-
splats-3d` (MIT): its `DropInViewer` drops into the existing three.js scene as a `THREE.Group` and self-
sorts each frame via `onBeforeRender`, so no render-loop changes were needed; it flows through the same
"open reference model" path (extensions + `accept` filter + federation registry), and its sort worker +
GPU buffers are torn down when the overlay is removed. **Offline-first** (our non-negotiable): the library
and its **inline-blob sort worker** are bundled — no CDN — and the scene parses from an in-memory object
URL, never the network. The library is **lazy-loaded as its own chunk** (252 KB / 66 KB gzip), fetched
only when a user actually opens a capture, so the eager app shell stays within budget (179.7 KB < 220 KB).
`SharedArrayBuffer` is off (no COOP/COEP header requirement); CPU sort for widest device support. Note: the
blob-URL worker needs `worker-src blob:` if the opt-in strict CSP is enabled. `splat.test.ts` covers the
splat-PLY detector. Part (b) — schedule-linked verified-as-built progress — remains on the roadmap.

## v0.3.207 — Wave 8 ⑥: Construction Execution Plan (CEP) generator
The GC counterpart to the BEP: a produced governance document that states **how the project is built**,
assembled live from the construction modules and summary engines rather than a stale Word template. New
`_cep` report builder emits a **ten-section CEP** — (1) project organization & authorities (standard
appointment roles + the awarded subcontractors as appointed trade parties), (2) scope & work breakdown
by bid package, (3) master schedule & key milestones, (4) procurement & subcontracting (prequalified +
executed subs, insurance/bond), (5) cost management & change control (CO totals from the change-order
engine), (6) safety plan (OSHA metrics), (7) quality plan (inspections / NCRs / first-pass yield), (8)
submittal & RFI procedures, (9) permits & regulatory, (10) closeout & turnover (punchlist / commissioning
/ warranties / O&M). Every data pull is guarded — a missing engine or empty module degrades to a
placeholder row, never a 500. Registered in the report catalog (group *Quality*), so it **auto-surfaces
in the Report Center** with PDF / Excel / markup buttons — no frontend change. Covered by the existing
`test_reports` catalog loop (52 reports each render a valid PDF + Excel; dispatch-parity enforced). ISO
21502 / CMAA practice areas paraphrased in original prose (no copyrighted text, no competitor names).
(Wave 8 ⑥ of 7 — see `docs/roadmap.md`.)

## v0.3.206 — Wave 8 ⑤: wrong-storey model hygiene + green CI (in-memory model tests)
Completes the Wave 8 model-hygiene track and fixes the API test gate. `model_qa.py` gains a sixth
integrity check — **wrong storey**: an element assigned to level A but physically placed at level B's
elevation (the classic "wrong level" authoring mistake), flagged only when the placement sits clearly
closer to another storey (1 m margin) and guarded so a malformed storey set degrades to "couldn't check"
instead of 500ing. `test_model_qa` now exercises a positive case (a wall assigned to L1 but placed at
L2's elevation is caught and anchored to its GlobalId). **CI fix:** `test_layout` and `test_loads`
opened `samples/*.ifc` on disk, but `samples/` is gitignored — a fresh CI checkout has no model, so the
API test gate went red on v0.3.204/205. Both now **build their IFC in-memory** (`ifcopenshell.file` — a
64-column grid for the layout points, a 3-storey/12-column stub for the load takedown), matching the
pattern the other model tests already use. No behavior change to the layout/loads engines.

## v0.3.205 — Wave 8 ④: Preliminary gravity load takedown + ASCE 7 load combinations
A defensible, **non-FEA** structural sanity-check from the model — the tributary-area "load takedown"
every engineer runs before sizing columns. New `loads.py`: dead (slab self-weight from thickness × concrete
density + superimposed) + live (ASCE 7-22 Table 4.3-1 by occupancy, with the **§4.7 live-load reduction**
closed form) → tributary area per column → **accumulate storey-by-storey down to the footing** → **ASCE 7
load combinations** (LRFD §2.3 + ASD §2.4) → governing factored axial. Output: per-storey rows + the typical
interior column / footing service & factored loads. New `GET …/loads/defaults` (reads storey + column counts
off the IFC) + `POST …/loads/takedown` (explicit storeys or auto-built uniform); client `loadsDefaults`/
`loadsTakedown`; a viewer tool prompts for floor area/occupancy and shows the column + footing loads with the
governing combinations. `test_loads` checks the ASCE 7 combos (1.2D+1.6L governs; 1.4D dead-only), the §4.7
reduction (50→24.36 psf), and the takedown arithmetic (3×120 psf×1000 sf = 360 kip dead/column, factored
~509 kip). **Preliminary only — no lateral (wind/seismic), and not a substitute for a licensed structural
engineer** (the caveat ships in the API, the UI, and the output). Pure `ifcopenshell` + arithmetic; optional
PyNite/sectionproperties (MIT) tier noted for later. (Wave 8 ④ of 7 — see `docs/roadmap.md`.)

## v0.3.204 — Wave 8 ②: Model → field layout (PENZD/PNEZD CSV + DXF) + as-built verification
The smallest-surface, highest-field-utility Wave 8 item — export the setout that the 2026 field-robotics
wave consumes, straight from the IFC. New `layout.py`:
- **Setout points** — grid intersections (`IfcGridAxis`) + column / footing / opening / wall object
  placements, in **real-world E/N/Z** (the `IfcMapConversion` is applied, so points land on the
  surveyor's grid), each carrying its **IFC GlobalId in the Description** for the round-trip.
- **PENZD / PNEZD CSV** (configurable column order + delimiter) — the near-universal total-station /
  marking-robot interchange (Trimble/Leica/Hilti).
- **Layered DXF** (`ezdxf`, MIT) — points + labels, a layer per element type — for floor printers
  (Dusty-style).
- **As-built verification** — upload the as-installed total-station shots, match by point number, and
  get per-point 3-D deviation with out-of-tolerance flagged and anchored to the element GlobalId.
New endpoints `GET …/layout/{points,points.csv,layout.dxf}` + `POST …/layout/verify`; client
`layoutPoints`/`layoutCsvUrl`/`layoutDxfUrl`/`layoutVerify`; a viewer tool exports CSV/DXF and explains
the stake → shoot → verify loop. `test_layout` runs against a real IFC (208 setout points on
`maple_tower`; PENZD+PNEZD+tab CSV; layered DXF; the 100 mm-off point flagged at 20 mm tolerance; the
IFC2X3 no-map-conversion path degrades gracefully). Pure `ifcopenshell` + `ezdxf`; permissive. (Wave 8 ②
of 7 — see `docs/roadmap.md`.)

## v0.3.203 — Wave 8 ①: Clash Coordination Intelligence (grouping · severity · reconcile · KPIs)
The management layer on top of geometric clash *detection* — the strongest signal from the 2026 field
scan (4 of 14 sheets), built the way Navisworks / Autodesk Model Coordination / Solibri / Revizto do it.
New `clash_intel.py` turns a raw clash result set into **tracked coordination issues**:
- **Grouping** — greedy by-element set-cover: a duct crossing 12 joists becomes **one** issue
  ("relocate this duct"), not 12 clashes (the industry's order-of-magnitude reduction).
- **Severity** — a discipline matrix (structural pairs weigh most) × penetration volume × group size →
  a 0-100 score + Low/Medium/High/Critical band.
- **Stable identity + reconcile** — a `group_hash` (dominant GlobalId + the other discipline) survives
  re-runs, so a federation cycle auto-marks issues **resolved** (gone) and auto-**reopens** them
  (reappeared) *without losing comment history* — the classic Navisworks pain point, handled.
- **KPIs** — status mix, worst discipline pairs, severity, open-issue aging, per-run burn-down +
  reappearance rate.
Issues are created as `coordination_issue` records (already **BCF-native + pinnable + GlobalId-anchored**),
so everything round-trips with any BIM tool. New endpoints `POST …/clash/{coordinate,analyze}`,
`GET …/clash/metrics`, and `coordinate=true` on `POST …/clash/federated`; a `clash_run` module persists
run snapshots; the viewer's federated-clash tool now runs the coordination pass (reduction + new/active/
resolved/reappeared + severity + a KPIs view). `test_clash_intel` covers grouping, severity, and the
resolve→reappear→reopen loop across three runs. Pure Python; no new dependency. (Wave 8 ① of 7 — see
`docs/roadmap.md`.)

## v0.3.202 — Fix: metadata-only project no longer hangs the viewer on "Loading model"
A project with an uploaded **property index but no published `.frag`** (geometry never converted) spun the
viewer's **"Loading model"** overlay forever, and because the auto-load never returned, the Construction /
Finance **portal never mounted** ("No project open"). The backend correctly **404s** `model.frag` for such
a project — that path was already handled — but the degenerate variants weren't: an **empty 200 body**, or a
**non-`.frag` payload** (e.g. a proxy / SPA host that rewrites a 404 into a 200 HTML page) reached the
Fragments worker, which can **hang** (not reject) on input it can't parse, so `withLoading`'s `finally` never
fired. `loadProjectModel()` now fails open to the same graceful no-model state a brand-new project takes:
skip an empty body, and wrap `loadFragments` so unparseable bytes fall through instead of stalling. New
`apps/web/src/ui/autoload.test.ts` covers 404 / empty-200 / non-`.frag` / valid-`.frag`. Verified: backend
`model.frag` 404 + `model_kind: None` confirmed against the API; typecheck + lint clean; full web suite green.

## v0.3.201 — UI cohesion: wire the approval-gated journal batch into the General Ledger panel
A UI/UX cohesion pass over the recent finance work found the v0.3.199 **journal export batch** had shipped
backend-only — its client methods (`createJournalBatch`/`journalBatchExportUrl`) had no surface, so the
approval gate was unreachable from the app. The **General Ledger** panel now carries a **Journal export
batches** section: **Freeze current books into a batch** (period + memo via an accessible modal → draft),
a list of batches with **state badges** (draft / submitted / approved / exported) and frozen Dr/Cr totals,
inline **workflow actions** driven by each record's `available_actions` (submit → approve → reject), and
**GL-CSV / IIF download** links that appear only once a batch is approved. Same GlobalId-keyed data, one
click from the ledger the figures come from. (The v0.3.200 model-WIP cross-check was already wired into the
WIP panel; the only remaining finance client method with no panel — `wipModelProgress` — stays a public
API for embeds, its data already surfaced via the WIP `model` block.) Verified: typecheck + lint clean,
production build green; endpoints exercised live.

## v0.3.200 — Model-quantity-derived WIP %: an independent progress signal that cross-checks cost POC
Roadmap item ②, part 2 (closes item ②). Cost-to-cost percentage-of-completion can mislead — a cost
overrun makes a *behind* job look *ahead*, and front-loaded billing hides under-production. So WIP now
derives a second, **physical** progress signal straight from the model: **installed model elements ÷
total, keyed by IFC GlobalId** (the "units-installed" output method — ASC 606 output measure / EVM
units-completed), optionally weighted by an IFC base quantity (e.g. `NetVolume`). "Installed" = an
element whose field-`verification` status is `installed`/`verified`, so this ties revenue recognition
back to what's actually built in the field, not just what's been spent — and survives re-conversion
because it's GlobalId-keyed. `wip.py` gains `model_progress()`; `schedule()` gains a `method`
(`cost-to-cost` default | `units-installed`) and always carries a `model` block cross-checking physical
vs cost % with a divergence flag (`cost-ahead` = the classic front-loaded-billing signal). New `GET
…/wip/model-progress` + `method=` on `GET …/wip`; client `wip(pid, method)` + `wipModelProgress`; the
WIP panel shows a model cross-check card. Portfolio roll-up skips the per-project model scan (stays
fast). `test_wip` extended (count 50% / NetVolume-weighted 30%; aligned → physical-ahead; units-installed
drives earned 500k → 750k; unavailable with no model).

## v0.3.199 — Accounting interop depth: approval-gated journal export batch
Roadmap item ②, part 1. A **journal batch** freezes the current books — flattened GL + balanced
double-entry journal + trial balance — into an auditable snapshot (`journal_batch` config module) that
moves `draft → submitted → approved → exported`; the config engine gates each transition by party, and
`audit.py` records it. Export (GL-CSV or QuickBooks-IIF) emits from the **frozen snapshot**, and is
**409 until the batch is approved** — so the accountant imports exactly the figures that were reviewed
and signed off, and nothing posts to the books without passing the gate. `accounting.py` gains
`snapshot`/`create_batch`/`export_batch`; new `POST /accounting/journal-batch` + `GET
…/{id}/export?fmt=gl|iif` endpoints + client methods. `test_accounting` extended (freeze → export-409 →
submit+approve → frozen CSV/IIF still balances at 125000; 422 on missing period, 404 on unknown batch).
(Part 2 — model-quantity-derived WIP % — is the remaining half of item ②.)

## v0.3.198 — Supply chain (B2): hash-pinned Python lockfile, generated in the prod interpreter
Closes the last deferred hardening item. Top-level runtime deps now live in `services/api/requirements.in`;
a new `lockfile.yml` CI job runs `pip-compile --generate-hashes --allow-unsafe` **inside `python:3.12-slim`**
(the exact prod base image) and uploads the compiled `requirements.lock` (2,061 lines, every wheel pinned
+ sha256-hashed) — so the resolution always matches production, never a dev box. The API Dockerfile's
build stage and the CI test gate now `pip install --require-hashes -r requirements.lock`, which **rejects
any substituted or tampered wheel** (defends against dependency-confusion / registry compromise). One lock
covers the data-service deps too (a strict subset) and `psycopg[binary]`, so it replaced the two prior
unpinned installs. `lockfile.yml` also gates pushes: it fails if `requirements.in` changed without
regenerating the lock. Verified end-to-end by CI (test gate runs the full backend suite against the pinned
tree; the api image builds from it).

## v0.3.197 — Docs: consolidate + reprioritize the open roadmap into one section
Roadmap cleanup — pulled *every* not-yet-done item (previously split across a "Deferred" block and a
"Feature backlog") into a single prioritized **"What's left"** section: ① actionable next = B2 hashed
pip lockfiles (env-blocked here → a CI `pip-compile --generate-hashes` job in python:3.12-slim);
② optional feature depth = accounting-interop journal export + the exploratory parking lot; ③ upstream-
blocked = IFC5/IFCX write-path, native mobile (Capacitor) shell; ④ intentional non-goal = the A4/A5
portal-core split (deliberately coupled). Refreshed the header to v0.3.196, updated the intro (both the
feature roadmap and the Waves 1–7 hardening initiative are cleared), and corrected stale "in progress"
markers in the archive (Sources & Uses shipped as `proforma/sources_uses.py`; EVM E1–E7 and model
authoring P0–P6 shipped).

## v0.3.196 — Docs: Wave 7 (T5/T6/B3) shipped; only B2 remains deferred
Roadmap updated — the code-quality initiative's Wave 7 (TS strictness + Docker hardening) is now shipped
and CI-green (v0.3.193–195), leaving **only B2** (hashed pip-compile lockfiles) deferred, with the precise
reason: a correct hashed lock must be generated in the prod interpreter (Linux/py3.12) via
`pip-compile --generate-hashes` in a CI/Docker job — this dev sandbox has no Docker, and a Windows/py3.10
lock would pin the wrong wheels. (A4/A5 portal-core splits remain intentionally-not-done: coupled
orchestration where extraction adds indirection over value.)

## v0.3.195 — Docker/build hardening (B3): multi-stage API image + reproducible web npm ci
**API image** — split the Python install into a `pybuild` stage: the build toolchain (`build-essential`,
`python3-dev`) compiles any source-only wheel there, then only the installed packages are copied into the
runtime stage (`pip install --prefix=/install` → `COPY --from=pybuild /install /usr/local`). The runtime
image now carries **no compiler/headers** — smaller, and a reduced attack surface (already ran non-root +
healthcheck). **Web image** — `npm install` → `npm ci` against the workspace-root lockfile (exact, locked
tree; fails on drift) for reproducible builds; removed the vestigial `packages/shared-types` phantom
workspace (no package.json, no imports) so the root install is clean, and regenerated the lockfile.
Added a root **`.dockerignore`** (keeps host `node_modules`/`dist`/`.venv`/`.git`/`.env`/`*.db` out of
every build context). Verified locally: lockfile regenerates clean, web build + ESLint + Vitest (66) all
green; the Dockerfile builds themselves are validated by CI's container matrix. (The nginx web runtime
ships no node deps, so dev-toolchain `npm audit` advisories don't reach production.)

## v0.3.194 — Lint (T6): typed no-floating-promises + 45 unhandled-promise fixes
Enabled type-aware ESLint (`parserOptions.projectService`) scoped to the two promise-safety rules only —
deliberately NOT the full `recommendedTypeChecked` set (which would flood on the intentional `any` at the
IFC/three/@thatopen boundaries). `no-floating-promises` (error) flagged **45** fire-and-forget async calls
that swallow rejections; all fixed with `void` (each verified to be a self-handling navigation/render
method, not a raw `fetch`/`import`, with `errorReporting.ts`'s global `unhandledrejection` handler as
backstop). `no-misused-promises` is scoped to `checksVoidReturn:false` so it catches genuinely-dangerous
promise-in-conditional/spread misuse (0 found) without churning ~90 idiomatic async event handlers. tsc
(251-guard T5 intact) + ESLint + Vitest (66) + build all green.

## v0.3.193 — Type safety (T5): enable noUncheckedIndexedAccess + 251 real guards
Turned on `noUncheckedIndexedAccess` in the web tsconfig — every array/record index access is now typed
`T | undefined`, forcing an explicit check. Fixed all **251** resulting violations across 25 files with
*real* guards (destructure-with-check, `?? <default>`, early-return/`continue`, optional chaining) — not
blind `!`. Non-null assertions were used only where an index is provably in-bounds (right after a
`.length` check or a literal-tuple index), each annotated `// safe: <reason>` (34 total); **zero**
`as any` / `@ts-ignore` / `eslint-disable` escapes. The sweep caught real latent crashes now hardened:
empty-selection `Object.entries(sel)[0]` in `createRfiFromSelection`, malformed-frag-pair `.replace()`,
a `selectedIndex === -1` throw, `CAP_RANK[role]` defaulting unknown roles to rank 0 (correctly denies
review/edit/admin), and malformed-GeoJSON/GeoTIFF coordinate handling (skip vs crash). Money math kept
`?? 0` on numerators/display only, never divisors (no new NaN paths). tsc + ESLint + Vitest (66) + build
all green.

## v0.3.192 — Docs: close out the Code quality & hardening initiative
Roadmap updated to reflect that Waves 1–6 of the four-domain audit all shipped CI-green (v0.3.177–191):
observability, perf/scale, the type boundary (OpenAPI types + `ui/dom.ts`), modularization
(`model_index.py`, `report_builders/`, `httpCore.ts`, `portal/prefs.ts`), and reproducibility/ops
(fragments single-source, fail-closed secrets, Rust PR CI, Trivy split, `money.py`). Four items are
recorded as **deferred with measured blockers** rather than forced: T5 `noUncheckedIndexedAccess`
(251 real violations → per-module, not one sweep), T6 typed-lint (same class), B2 pip lockfiles (must
resolve in prod Linux/py3.12, not this dev box), B3 Docker `npm ci` (CI-only verify, low value).

## v0.3.191 — Add Decimal money helpers money.py (P6)
Float money math drifts at the cent: `round(2.675, 2)` is `2.67`, and a naive `round()` three-way split
of $100 sums to 99.99. Added `aec_api/money.py` — `q2()` (round-half-up to cents), `to_cents()`, and a
penny-accurate `allocate()` (largest-remainder split that always sums to the total). Returns plain
floats/ints so engines can adopt them incrementally without signature changes. New `test_money` suite
registered in the gate. (Additive — existing `round(x, 2)` sites are unchanged; adoption is opt-in.)

## v0.3.190 — Add typed DOM helpers ui/dom.ts (T4)
`document.createElement(...)` + a run of property assignments is the single most-repeated pattern in
the UI (255× in portal.ts alone). Added a thin, dependency-free `ui/dom.ts`: `el(tag, props, children)`
(typed props — `class`/`text`/`style`/`dataset` plus any element property like `onclick`/`type`),
`frag()`, `clear()`, and a typed `readForm<T>()`. Ships with a 7-case Vitest suite and is adopted in the
portal catalog as a first use; available for incremental adoption elsewhere. Vitest now 66 tests; tsc +
ESLint + build green.

## v0.3.189 — Refactor (T3): extract portal preferences into prefs.ts
The portal's favorites/recents and the per-persona "which nav sections open first" map were private
`PortalUI` methods, read by both the nav rail and the module catalog. Pulled them into a small
`portal/prefs.ts` (localStorage-backed, pure functions) so the two consumers share one source of truth
instead of reaching into the class. Verified: `tsc`, ESLint, Vitest (59), Vite build all green.
(portal.ts and viewer/app.ts already received their principled decomposition in earlier releases —
portal→panels/ + PanelContext, viewer→ViewerContext/install modules; the remaining catalog↔nav
orchestration is intentionally coupled, so this pulls out the cleanly-separable preferences only.)

## v0.3.188 — Refactor (T2): extract the API-client transport core into httpCore.ts
The web `ApiClient` mixed its transport plumbing (base URL, bearer token, `json`/`_pdfPost`/`url`/
`health`) in with ~200 typed domain methods in one 2,760-line file. Pulled the transport into a small
`HttpCore` base class (`api/httpCore.ts`); `ApiClient extends HttpCore` and keeps only the endpoint
surface. Every `api.method()` call site is unchanged (facade preserved). Verified: `tsc --noEmit`,
ESLint, and Vitest (59 tests) all green; production Vite build succeeds. (A full sub-client split was
weighed and rejected — it would churn 200+ call sites for no behavioural gain; transport/domain
separation is the value that carries low risk.)

## v0.3.187 — Refactor (A3): shared open_source_ifc() helper for the analysis endpoints
Three analysis endpoints (`models/georeferencing`, `models/qa`, `scan/deviation`) each hand-rolled the
same "resolve the project's source IFC → 409 if missing → ifcopenshell.open → 400 if unreadable" dance.
Added `deps.open_source_ifc(db, pid)` — one resolve-then-open path with consistent 4xx handling — and
converged the three sites onto it (georeferencing + models/qa now one-liners; scan/deviation reuses the
409 resolver, keeping its threadpool open). Behaviour identical; verified via test_georef, test_model_qa,
test_scan_deviation, test_ai_readiness.

## v0.3.186 — Refactor (A2): decompose reports.py into a report_builders/ package
The Report Center's builder module was a 1,436-line god-file holding ~50 per-report builder functions
alongside the catalog + dispatch. Split the builders into a `report_builders/` package — one module per
domain (`finance`, `construction`, `precon`, `bim`, `operations`) over a shared `_common` helper — so
`reports.py` is now a 176-line dispatch layer (the REPORTS catalog, the key→builder registry, and
`build()`). Public API is byte-identical: `reports.build`, `reports.catalog`, `reports.Report`,
`reports.to_pdf/to_sheets` all unchanged. Verified: all 8 report-exercising suites green (test_reports
builds every one of the 51 reports to PDF + Excel); ruff clean whole-tree.

## v0.3.185 — CI: split Trivy into a CRITICAL gate + non-blocking HIGH report
Following v0.3.184: scoping the API scan past npm's bundled tooling wasn't enough — the **web** image
(final stage `nginx:alpine`) carries its own rolling set of fixable HIGH CVEs in its apk packages, which
a shared skip-dir can't cover. Both base images churn fixable HIGHs outside our control, so a blocking
HIGH gate keeps the pipeline red on upstream timing, not on our code. Resolution: **CRITICAL findings
still block the publish**, and a **second, non-blocking Trivy step prints fixable HIGH CVEs every build**
so they're surfaced (not shipped silently) for a human to act on the ones in our own deps — without
base-image noise gating the release. Restores green container publish; keeps O4's real deliverables
(Rust PR CI + fail-closed prod secrets + CLI/dep guards) intact.

## v0.3.184 — CI hotfix: scope Trivy HIGH past npm's bundled build tooling
The v0.3.183 Trivy bump to HIGH immediately flagged **12 HIGH CVEs — all in npm's own vendored
node_modules** (cross-spawn / glob / minimatch / tar, DoS/regex issues) that the `node:20-slim` layer
carries; they're build-time tooling, not runtime attack surface, and can't be pinned by us (they track
the base image). The scan now `skip-dirs` npm's bundled tree, so real HIGH/CRITICAL CVEs in **our**
fragments/web-ifc + Python deps still block the publish, without base-image tooling noise. (The API test
gate, web build, and full backend suite were already green on v0.3.183 — this only unblocks the container
publish.)

## v0.3.183 — Ops/build hardening (Wave 1/6: O3 · O4 · B4) + A1 lint fix
Cross-cutting hardening + a follow-up to v0.3.181.
- **O3 — fail-closed prod secrets.** The prod compose overlay now sets `POSTGRES_PASSWORD` (postgres +
  the API's `DATABASE_URL`) and `S3_SECRET_KEY` (minio + the API) via `${VAR:?}`, so the stack **refuses
  to start** without real credentials instead of silently inheriting the dev `bim`/`minioadmin` defaults.
- **O4 — Rust PR CI + Trivy HIGH.** New `rust-ci.yml` runs `cargo clippy -D warnings` + `cargo fmt
  --check` on the Tauri shell, path-filtered to `apps/web/src-tauri/**` (no cost on unrelated PRs) — it
  previously only compiled at release time. The container scan now gates on **HIGH + CRITICAL** fixable
  CVEs (was CRITICAL-only).
- **B4 — converter CLI + Dependabot.** `cli.mjs` no longer clobbers its input when the file lacks an
  `.ifc/.rvt` extension (appends `.frag` instead); the Dependabot npm ecosystem points at the repo root
  (where the workspace `package-lock.json` actually lives) so it can open working PRs.
- **A1 fix.** Import-sort (ruff I001) slip in `evm.py` from the v0.3.181 `model_index` rename — the only
  thing that had gone red (lint, not tests). Whole-tree ruff is green again.

## v0.3.182 — Single-source the fragments/web-ifc version (Wave 6, B1)
Closes the version-coupling landmine CLAUDE.md warns about. `@thatopen/fragments@3.4.5` +
`web-ifc@0.0.77` were hardcoded in **three** independent places — the web client parser
(`apps/web/package.json`, the source of truth) and the two server-side `.frag` producers
(`services/api/Dockerfile`, `services/converter/Dockerfile`) — with nothing keeping them in lockstep, so
a client bump could silently leave the server emitting fragments the browser can't parse. The Dockerfiles
now take the versions as build ARGs (self-documenting, overridable), and a new
`scripts/check-fragments-version.mjs` (wired into the CI **web-build** job) fails the build if either
Dockerfile drifts from the `package.json` pins. `package.json` is now the one source of truth; CI enforces
agreement.

## v0.3.181 — Extract the model-index engine (Wave 5, A1)
Fixes the worst dependency inversion in the backend. The in-process **property index**
(`pid → {guid → record}`) and the model-version-keyed **scan-result cache** lived as private globals
inside `routers/properties.py`, yet five engines (`bim_kpi`, `energy`, `evm`, `mcp_tools`, `reports`)
reached in with `from .routers.properties import _INDEX, _ensure_loaded` — engines depending on an
HTTP-layer module's internals. Moved to a new `model_index.py` engine with a public API
(`ensure_loaded` / `get_index` / `get_meta` / `load` / `scan_cached`); the router now imports from it
(keeping its endpoints), and the five engines import the engine instead of the router. Compatibility
aliases (`_INDEX`/`_ensure_loaded`/`_scan_cached`) preserve behaviour exactly — same cache objects, so
in-place mutation stays shared. No API or runtime change; the dependency arrow now points the right
way and the index is testable/reusable without importing FastAPI. `test_scan_cache` updated to the new
module.

## v0.3.180 — OpenAPI-generated TypeScript types (Wave 4, T1 foundation)
Establishes a compiler-checked contract to the backend. `openapi-typescript` now generates
`apps/web/src/api/schema.d.ts` (types-only — erased at build, no bundle cost) from the FastAPI
`/openapi.json`, and a thin `openapiTypes.ts` seam re-exports `paths`/`components`/`operations` plus
`Schema<K>` / `OkJson<Op>` / `ReqJson<Op>` helpers so endpoints can adopt generated request/response
types. Regenerate with `npm run gen:api-types` (the intermediate `openapi.json` is gitignored;
`schema.d.ts` is committed). **Scope note, honestly stated:** the backend returns raw dicts on most
endpoints — only ~11 of ~540 declare a response model — so today the generated types are precise for
request bodies, path/query params, the 134 input schemas, and those typed responses; the hand-written
DTOs in `types.ts` remain the source for untyped responses. Coverage grows automatically as backend
endpoints adopt `response_model=` (a follow-on track). tsc/eslint/vitest green; bundle size unchanged.

## v0.3.179 — Scale: SQL-aggregate the portfolio & related-record hot paths (Wave 3)
Removing the linear-in-project-size loads. **P3 — WIP portfolio N+1:** the WIP schedule loaded up to
100k owner-invoice rows into Python *per project* to sum billed-to-date, and the portfolio roll-up runs
that for every job — the worst scale hazard in the codebase. Added a portable
`modules.sum_field(db, key, pid, field)` (SQL `SUM` over the JSON column: Postgres `->>`+cast,
SQLite `json_extract`) and pointed the WIP billed-to-date total at it. **P4 — dashboard timesheet
hours:** the safety-metrics endpoint summed `timesheet.hours` by loading every row; now a single SQL
sum (the manpower log stays row-wise because it needs the headcount→hours fallback). **related_records:**
the per-record detail view full-scanned each reverse-referencing module and filtered the match in Python;
the reference match is now pushed into SQL via the existing `_json_text` extraction (mirrors `_rollup`).
Identical output, far less work at scale. *(The schedule/CPM/gantt `list_records` loads were reviewed and
left as-is — they legitimately need every activity row. The ref-uniqueness DB backstop is deferred as
low-value/higher-risk.)*

## v0.3.178 — Perf & concurrency hardening (code-quality Wave 2)
Applying the audit's highest value-to-effort fixes. **P1 — event-loop stall:** the
`POST /scan/deviation` endpoint was `async` but ran `ifcopenshell.open` + full tessellation and the
point-cloud parse synchronously, stalling every other request on the worker for the duration of a large
scan; all three now run in `run_in_threadpool` (mirroring `run_validate`). **P2 — uncached hot scans:**
the model **data-QA**, **code-readiness**, and **by-discipline** viewer scans recomputed `O(n·psets)`
on every request while their siblings (facets/color-by) were cached; they now go through the same
model-version-keyed `_scan_cached` (Redis-backed, auto-invalidated on republish) — repeat loads are
served from cache. **P5 — concurrency/scale hardening:** a composite `(project_id, ts)` index on
`record_activity` turns the frequently-polled notifications feed from an index-scan-plus-filesort into
one ordered range scan (auto-backfilled on existing DBs); and the in-process property index
(`_INDEX`/`_LRU`) — mutated from multiple threadpool threads — is now guarded by a lock so an eviction
can't fire mid-populate and drop a live project. No API shape changes; behaviour identical, just faster
and safer under load.

## v0.3.177 — Error-log observability (see when things break)
The first wave of the code-quality/hardening initiative: a **background place to see failures** instead
of them dying in a server's stdout. A global exception handler + request-id middleware now catch every
**unhandled server error**, record it (with traceback, route, user, and a correlation id) to a new
`error_log` table, and return a clean `500 {detail, request_id}` — and every response carries an
**`X-Request-ID`** header so a user-reported failure maps straight to its logged row. **Browser errors**
are captured too: a `window.onerror` / `unhandledrejection` hook (throttled + deduped) posts to
`POST /client-errors`, landing in the same feed tagged `source:"web"` — so a viewer crash or a failed
upload is finally visible. Admins get an **Errors** console (account menu → Errors) with source/level
filters, a totals header, expandable tracebacks, and a prune button; the log is **retention-capped**
(rows + age, env-tunable) so it can't grow unbounded on the read-only prod tree. Engine `errorlog.py`,
`routers/observability.py` (`GET/DELETE /admin/errors`, admin-gated), `ErrorLog` model,
`errorReporting.ts`. Test `test_errorlog.py` covers the engine, the 500 handler end-to-end, the intake,
and the admin feed. In-house only — no external APM, consistent with the offline mandate.

## v0.3.176 — 2D → BIM raise (DXF floor plan → IFC model)
The complement to scan-to-BIM: where deviation checks the *built* result against the model, this
raises design intent *up* from flat 2D CAD into one. Upload a **DXF floor plan** and get a real,
GUID-keyed **IFC4 model** — an `IfcWall` extruded from each line-work segment (auto-detecting "wall"
layers, falling back to all line-work) and an `IfcSpace` (with its floor area in the Qto) from every
closed room polygon. Drawing units are read from the DXF `$INSUNITS` header and normalised to metres.
The raised model is registered as a **"2D Raise"** discipline model, so it opens in the viewer and
takes part in federated clash immediately. A `preview` mode returns the detected wall/room counts
without writing anything. Engine `plan_to_bim.py` (ezdxf for the CAD read — MIT, no AGPL; ifcopenshell
for the model, same wall/space patterns as the massing generator), endpoint
`POST /projects/{pid}/raise-plan` (multipart; temp-dir scratch, never the read-only tree), a client
method, and a **🏗 Raise 2D→BIM** viewer tool. Test `test_plan_to_bim.py` round-trips the IFC.

## v0.3.175 — Scan-to-BIM deviation (as-built QA/QC)
Close the reality-capture loop: upload an as-built **point cloud** (ASCII XYZ / CSV / PTS) from a laser
scan or photogrammetry survey and compare it against the model surface to see **where the built work
departs from the design beyond tolerance** — the QA/QC check after a pour or a steel erection. For every
scan point we take the nearest distance to the model's triangulated surface (a KD-tree over the model
vertices), then summarize: **% within tolerance**, mean / 95th-percentile / max deviation, an
out-of-tolerance count, and a **deviation histogram** banded in multiples of the tolerance — the numbers
behind a red/green deviation heatmap. Engine `scan_deviation.py` (numpy + scipy cKDTree; model surface
pulled via `ifcopenshell.geom`, capped so a huge model can't blow memory), endpoint
`POST /projects/{pid}/scan/deviation?tolerance=` (multipart upload; 409 without a source IFC), a client
method, and a **▦ Scan-to-BIM deviation** viewer tool that renders the summary + histogram. All units in
metres; GUID-keyed model geometry, fully offline. Test `test_scan_deviation.py`.

## v0.3.174 — AI / data-readiness scorecard
Roadmap item from the "hidden bottleneck of agentic AI" research: the blocker to AI isn't the model,
it's the **data**. A new scorecard grades a project **0–100 on four measurable dimensions** — **single
source of truth** (a GUID-keyed IFC + federated models), **information completeness** (CDE metadata +
core requirements), **model integrity** (the model-QA defect ratio, when an IFC is loaded), and
**governance** (requirement traceability + a responsibility matrix, on top of always-on RBAC/audit) —
with a per-dimension recommendation and a **ready / partial / not-ready** verdict. Answers "can an agent
act on this project's data yet, and if not, what to fix first?". Engine `ai_readiness.py`, endpoint
`GET /projects/{pid}/ai-readiness`, an **AI / data-readiness** card atop the CDE / Standards panel, and
`test_ai_readiness`. Honest heuristic — a readiness indicator, not a guarantee.

## v0.3.173 — PM: portfolio prioritization matrix
Roadmap **PM artifacts #2.** The Portfolio view now ranks every project you can see with a
**prioritization matrix** — each scored **0–100** on four criteria (financial **return** / equity IRR,
**on-budget** / CPI + variance, **on-schedule** / SPI + % complete penalized for late milestones, and
**delivery-risk** / status) into a weighted composite, ranked best-first with a color-graded score per
criterion. Reuses the executive-portfolio rows (and their membership scoping), so no double-counting.
New engine `prioritization.py` (pure, weight-configurable), endpoint `GET /portfolio/prioritization`,
a ranked card in the Portfolio panel, and `test_prioritization`. Answers "where do capital and attention
go across the book?"

## v0.3.172 — PM: stakeholder register + power/interest analysis
Roadmap **PM artifacts #1** (from the PM-template research). A new **Stakeholders** module (under Project
Controls) registers each party — organization, role, category, power/influence, interest, stance,
engagement strategy. A `stakeholder.py` engine turns the register into the **Mendelow power/interest
grid** — *manage closely* (high/high), *keep satisfied* (high power), *keep informed* (high interest),
*monitor* (low/low) — with a stance tally and, crucially, the **high-power blockers** to address. Exposed
as `GET /projects/{pid}/stakeholders/analysis` and a **Stakeholder Analysis** report (power/interest
quadrants + roster + blockers) in the Report Center, exportable to PDF/Excel. New `test_stakeholder`.

## v0.3.171 — Model QA: integrity / hygiene checks
Roadmap **Model-QA** (from the second research batch's "common modelling mistakes"). Complementing the
LOIN/IDS *data-quality* checks, a new **🩺 Model QA** tool scans the source IFC for the defects a
coordinator catches by eye: **duplicate GlobalIds**, **orphaned elements** (not placed in any storey),
**overlapping duplicates** (same class stacked at one spot), **unenclosed spaces** (an IfcSpace with no
boundaries — the classic "Room is not enclosed"), and **blank element names**. Each check returns a
count + a sample of offenders and a clean/not-clean verdict. New engine `model_qa.py`, endpoint
`GET /projects/{pid}/models/qa`, and `test_model_qa` (builds an IFC in-memory with every defect and
checks each is caught). ifcopenshell only, no new deps.

## v0.3.170 — Coordination: shared coordinates / BIM-to-field setout
Roadmap **Phase C** (from the second research batch's BIM Control Stack). The alignment report only read
a model's eastings/northings; this reads the **full survey basis**. A new **📍 Georeferencing** model
tool reports the complete `IfcMapConversion` — eastings/northings/height, the **true-north bearing**
(derived from the X-axis rotation), and scale — plus the `IfcProjectedCRS` (EPSG name, geodetic/vertical
datums, map projection + zone), and a site lat/long fallback. It grades the model with a **LoGeoRef
level** (0 → 50) so a coordinator sees at a glance how well-referenced it is — the basis federation and
**BIM-to-field layout/setout** both depend on. New engine `georef.py`, endpoint
`GET /projects/{pid}/models/georeferencing`, and `test_georef` (builds a georeferenced IFC in-memory and
checks the bearing/CRS/level). Permissive: reads via ifcopenshell, no new deps.

## v0.3.169 — openBIM: ISO 19650-6 exchange acceptance
Roadmap **Phase A #3.** Distinct from the project-level handover gate, this reviews **each exchanged
container** (anything past Work-in-Progress) against the four ISO 19650-6 acceptance criteria —
**completeness** (type/discipline/originator set), **suitability** (a suitability code), **authorization**
(published/archived, not merely shared), and **traceability** (a revision) — and flags the ones **not yet
acceptable** before the next decision point. Reuses the container data already tracked; no new module.
`cde.exchange_acceptance()`, endpoint `GET /projects/{pid}/cde/exchange-acceptance`, and an **Exchange
acceptance** card (per-criterion % + non-conformances) in the CDE / Standards panel. Extends `test_cde`.
Completes the ISO 19650 delivery-checklist "exchange assurance" step.

## v0.3.168 — openBIM: LOIN + MIDP/TIDP delivery plan
Roadmap **Phase A #2** (from the second research batch). Two ISO 19650 depth items on information
requirements. **LOIN** — each requirement now records its **Level of Information Need** per EN 17412-1 /
ISO 7817: the required depth of **geometry**, **alphanumeric** data, and **documentation** (three
ordered selects), so an EIR states *how much* information a deliverable needs, not just that it's needed.
**MIDP / TIDP delivery plan** — a new engine (`cde.delivery_plan()`) lays the requirements out against
their **programme dates**: each gets an overdue / due-soon / scheduled / issued status, a per-milestone
(due-month) roll-up, the next deliverable, and **LOIN coverage** (the share that actually state a level).
Surfaced as a **Delivery plan (MIDP/TIDP)** card in the CDE / Standards panel with overdue/due-soon
flags. Endpoint `GET /projects/{pid}/info-requirements/delivery-plan`; extends `test_cde`. Ties every
information exchange to a milestone — the "align exchanges with programme dates" step of the ISO 19650
delivery checklist.

## v0.3.167 — openBIM: information-requirement flow-down (ISO 19650 cascade)
Roadmap **Phase A #1.** The requirements register listed OIR/AIR/PIR/EIR/BEP/MIDP/TIDP but nothing tied
a requirement to the higher-level one it flows down from — so there was no actual traceability. Each
Information Requirement now has a **Derives from** link (to another requirement), and the CDE / Standards
panel shows a **Requirement flow-down** card: how many requirements trace up (OIR → PIR/AIR → EIR →
MIDP/TIDP), which ones **don't** (orphans that don't reach organizational intent — a broken cascade),
and any links pointing the **wrong way** (to an equal-or-lower tier). Engine `cde.cascade()`, endpoint
`GET /projects/{pid}/info-requirements/cascade`, extends `test_cde`. The link is set/edited inline with
the relational grid (v0.3.159). This is the openBIM information-delivery moat: intent traced from the
client's organizational requirements down to what each task actually delivers.

## v0.3.166 — Estimating: quantity takeoff from 2D CAD (DXF)
Roadmap **Phase B #4.** Estimating no longer needs an IFC model — a new **▤ DXF takeoff** model tool
takes an uploaded **.dxf** drawing and measures it **by layer**: linear metres (walls, pipe/conduit
runs), enclosed area (rooms, slabs — closed polylines + circles), and **block counts** (doors, fixtures,
devices), converting to metres from the drawing's own units. Built on **ezdxf** (MIT, pure-Python — no
AGPL); DWG converts to DXF first (external, optional). The upload is parsed in a temp file and
discarded, never written to the source tree; a non-DXF file returns a clean 400. New engine
`dxf_takeoff.py`, endpoint `POST /projects/{pid}/takeoff/dxf`, and `test_dxf_takeoff`. Estimators who
live in 2D CAD can now get measured quantities without a full BIM model.

## v0.3.165 — Estimating: labor demand by trade (estimate → staffing)
Roadmap **Phase B #3.** The resource estimate now rolls its crew-hours **up by trade** — total hours
and cost per trade (carpenter, ironworker, cement-mason…), sorted biggest-first — so the model answers
"how many carpenter-hours does this building need?", the input a scheduler or PM uses to staff and load
the schedule. The engine's `labor_demand()` can also imply an **average crew size** to finish in a given
number of weeks (hours ÷ weeks ÷ 40). Shown as a "Labor demand by trade" table in the 🧱 Resource
estimate model tool. Extends `test_assemblies`. This is the bridge from the estimate's L/M/E split to
resource loading — the point of computing crew-hours in the first place.

## v0.3.164 — Estimating: resource estimate in the viewer (labor · material · equipment)
Roadmap **Phase B #2** — surfaces v0.3.163's engine. The model tools now have a **🧱 Resource estimate**
button next to the blended "Estimate from model": it prices the takeoff by building each element up from
a crew and shows the **labor / material / equipment split** (with % of total), **total crew-hours**, and
a per-assembly breakdown (quantity, built-up unit cost, hours). Where the blended estimate answers "how
much," this answers "made of what" — the split a real estimate carries and the crew-hours that feed
resource loading. Unmapped element classes are noted, not hidden.

## v0.3.163 — Estimating: resource-based (assembly) cost build-up
Roadmap **Phase B #1.** Model-based estimating used a single blended $/unit per element class. Real
estimators build a unit cost **up** from a crew: labor hours × rate + materials × quantity + equipment
× hours. A new engine (`assemblies.py`) does exactly that — a catalog of labor/material/equipment
**resources** and **assemblies** (recipes like "cast-in-place wall" = concrete + rebar + formwork +
cement-mason + laborer + pump). Pricing any quantity now returns the **labor / material / equipment
split**, the built-up unit cost, **and total crew-hours** — the last of which can drive resource loading
and the schedule, not just a dollar figure. Two endpoints: `GET /estimate/resources/catalog` (the
reference book, each assembly with its built-up unit cost) and `GET /projects/{pid}/estimate/resource-based`
(prices the IFC takeoff by mapping each element class to an assembly; unmapped classes are surfaced, not
silently dropped). Backend-only this release; a UI to compare blended-vs-resource follows. New
`test_assemblies` (build-up math, L/M/E split, crew-hours, takeoff) — full suite green.

## v0.3.162 — Data-grid UX: choose which columns show
Roadmap **Track X #3.** A module list showed a fixed set of columns (whatever the module defined), so
wide record types either hid fields you needed or you scrolled past ones you didn't. A new **⚙ Columns**
button opens a checklist of every field — tick the ones you want as columns and they render in field
order; **Reset to default** returns to the module's built-in set. The choice is remembered per module on
this device, and the button highlights when a custom set is active. Ref, Title, Assignee, Ball-in-court
and Status always frame the row. Pairs with inline edit / paste so you can shape a wide table down to
just the columns you're working in.

## v0.3.161 — Relational fabric: "referenced by" now reads distinctly on a record
Roadmap **Track R #3.** A record's Related section already listed both the records it points to and the
records that point back at it — but with one identical icon and no labels, so you couldn't tell the two
directions apart. It's now split into two counted groups: **References (n)** — what this record points
to — and **Referenced by (n)** — its dependents, e.g. the change orders raised against a budget line —
each with its own direction icon and a one-line caption. Also hardens the section: linked-record titles
(user text) are now HTML-escaped rather than injected raw. Completes the record-level relational view
alongside the grid's clickable links (v0.3.157) and inline linking (v0.3.159).

## v0.3.160 — Data-grid UX: paste rows straight from Excel
Roadmap **Track X #2.** Getting a batch of records in used to mean saving a spreadsheet and uploading
it. Every module list now has a **⎘ Paste** button: copy a block of cells from Excel or Google Sheets,
paste them in, and the pasted table flows into the **same import step you already know** — column
mapping, preview, then commit. No file, no new code path: paste is converted to CSV and handed to the
existing importer, so it inherits its validation and field-mapping. Keep the header row and map each
column once. Rounds out in-grid data entry alongside inline edit (v0.3.158) and inline linking (v0.3.159).

## v0.3.159 — Relational fabric: link records inline from the grid
Roadmap **Track R #2** (extends v0.3.158's inline edit). In **✎ Edit inline** mode, a reference cell
now becomes a **record picker** — a dropdown of the linked module's records reading as *ref · title* —
so you set or change what a record points at without opening its form. Options come from the data
already fetched for the relational links (no extra requests); a current link that sits outside the
loaded window is preserved so toggling edit mode never drops it. Saves on change with the same green
flash. Read mode still shows the clickable link (v0.3.157). Together with v0.3.158 the whole row —
data fields and relationships — is now editable in place.

## v0.3.158 — Data-grid UX: inline-edit cells for fast bulk entry
Roadmap **Track X #1.** Editing many records meant opening a form for each one. Every module list now
has an **✎ Edit inline** toggle: data cells become inputs (text / number / date / dropdown / checkbox)
you edit straight in the table, and each change **saves automatically** with a brief green flash — no
form round-trip. Enter or blur commits a cell. Works across all 120 config modules and composes with
the existing filter / sort / bulk-select / templates. Reference cells stay as their new relational
links (v0.3.157); the inline record-picker for references comes next. Opt-in — the read view is
unchanged until you toggle it on.

## v0.3.157 — Relational fabric: reference cells become clickable links
Roadmap **Track R #1.** The 120 tools are deeply relational, but in a module's list a reference field
(a commitment's cost code, an RFI's spec section, a change event's PCO…) showed only a truncated id.
Now every reference cell resolves to the **linked record's ref + title** and is a **link** — one click
opens that record in its own module. The list pre-fetches each referenced module once (one lookup per
reference column, not per cell), so it stays fast; unresolved ids fall back to the short id. Applies
automatically to all 120 config modules. Foundation for the record-picker + inline-edit grid to come.

## v0.3.156 — Responsibility matrix (RACI / DACI) — roadmap Phase A, item 1
The role-clarity that ran through the field research (PM vs Superintendent, PM vs CM, RACI vs DACI)
had no home in the app. New **Responsibility** destination (under Plan & Derisk for the GC, and under
Model & Standards for the design seat, where it doubles as the ISO 19650 MIDP/TIDP task-team
responsibility view): an editable grid of activities × project roles, each cell an assignment letter.
- **RACI** (Responsible / Accountable / Consulted / Informed) or **DACI** (Driver / Approver /
  Contributor / Informed) — one-click toggle that remaps the doer letter across the matrix.
- **Live validation** enforces the rules that make a RAM useful: exactly one Accountable per row, at
  least one Responsible — flagged inline as you edit.
- **Starter templates** (design delivery, buyout, construction, closeout) seed a valid matrix in a
  click; add/rename/remove role columns and activities; export to CSV.
- Built on the config-module engine (new `responsibility` module + `responsibility.py`) so every row
  gets CRUD, RBAC, audit and search for free; the panel degrades to a clean empty state offline.

## v0.3.155 — Enterprise: SAML 2.0 single sign-on
Massing can now sit behind a corporate IdP over SAML (Okta, Azure AD/Entra, OneLogin, ADFS,
Shibboleth), alongside the existing OAuth providers. A new SP surface: **`GET /auth/saml/metadata`**
(SP metadata to register), **`GET /auth/saml/login`** (SP-initiated redirect, HTTP-Redirect binding),
and **`POST /auth/saml/acs`** (Assertion Consumer Service). A verified email maps to an
auto-provisioned free-tier user (honoring the same `AEC_OAUTH_ALLOWED_DOMAINS` / no-autoprovision
gates as OAuth); `/auth/providers` now reports `saml: true` when configured.

Verification is the whole game, so it's done carefully (`saml.py`, using `signxml`): the IdP signing
cert is **pinned** from config (never trusted from the message's KeyInfo); identity is read **only
from the cryptographically-verified subtree**, defeating XML Signature Wrapping; and the signed
assertion's **Conditions** (validity window ± a small clock-skew, AudienceRestriction == our SP) and
**SubjectConfirmation Recipient** (== our ACS) are enforced. `test_saml` drives real signed assertions
through the ACS and proves tampered, unsigned, wrong-key, expired, and wrong-audience responses are
all rejected (403). Enabled only when the IdP entityID + SSO URL + cert are set.

## v0.3.154 — Enterprise: SCIM 2.0 user provisioning
Enterprises can now automate account lifecycle from their IdP (Okta, Azure AD/Entra, OneLogin,
JumpCloud) instead of managing users by hand. A new **`/scim/v2`** surface (RFC 7643/7644) implements
the Users resource: **create** (provision), **read / filter** (`userName eq`), **PUT / PATCH**
(including both the Okta `path:active` and Azure `value:{active}` deactivation shapes), and
**DELETE** (de-provision). Provisioned accounts are SSO-only (a random, unusable password — they sign
in via OAuth/SAML), and **deactivation revokes any live token immediately** (bumps the session
watermark), not just at expiry; DELETE is a soft-delete so the audit trail and record authorship
survive, and a later re-provision reactivates (rehire). The whole surface is gated by a single
constant-time bearer token (`AEC_SCIM_TOKEN`); unset ⇒ 503 (disabled), so it can't be probed open.
Adds `User.external_id` (IdP correlation) + `User.provisioned` (additive schema sync).

## v0.3.153 — Search: GIN index behind module full-text search (Postgres)
Module full-text search already used Postgres `to_tsvector(...) @@ to_tsquery(...)`, but nothing
indexed that document — so every search recomputed `to_tsvector` for **every row** (a sequential
scan, brutal past ~100k records). `init_db` now creates a **GIN expression index** on the exact same
`to_tsvector(ref + title + data)` document the query matches (built from the shared `_pg_document`
helper, so the index and the query can't drift). Postgres-only and idempotent
(`CREATE INDEX IF NOT EXISTS`); a **no-op on SQLite** (dev/CI use the substring-LIKE fallback, which
needs no index). The regconfig is rendered as a literal so the expression is index-safe.

## v0.3.152 — Web: decompose the two remaining god-files (client.ts / portal.ts)
No behavior change — the two largest web modules are split along their existing seams:
- **`api/client.ts` 2905 → 2612**: the ~300 lines of DTO `interface`/`type` declarations move to a new
  **`api/types.ts`**; the client re-exports them (`export * from "./types"`) so every
  `import { … } from "../api/client"` site across the app keeps resolving unchanged.
- **`portal/portal.ts` 2816 → 2302**: the GMP **Budget** dashboard and the unified **Schedule** views
  (pull-plan board, lookahead, milestones, CPM, EV, baseline/variance, Gantt/LoB) extract to
  **`portal/panels/budget.ts`** and **`portal/panels/schedule.ts`** via the established `PanelContext`
  seam (the 11 panels already living there); the class keeps one-line delegators.

## v0.3.151 — Web: global keyboard focus indicator (WCAG 2.4.7)
Keyboard users had no consistent visible focus ring — many interactive controls relied on the browser
default, which the app's custom control styling suppressed in places. A single `:focus-visible` rule now
draws a 2px accent outline (with offset) on every focusable control — buttons, links, inputs, selects,
textareas, `summary`, and anything with `tabindex` — **only** for keyboard/AT focus, so mouse clicks
don't get the ring. Meets WCAG 2.4.7 (Focus Visible). CSS-only, no markup or behavior change.

## v0.3.150 — Report dispatch: data-driven registry (replaces the 90-line if/elif ladder)
`reports.build()` chose a builder through a ~90-line `if report == "…"` ladder. It's now a
`_BUILDERS` dict (key → builder) + a `_LOGS` dict for the module-log reports — adding a report is one
registry line, and the dispatch can no longer silently drift from the `REPORTS` catalog. `test_reports`
gains a parity assertion (`REPORTS` keys == builders+logs) so a new report without a builder (or vice
versa) fails the gate. No behavior change — all 50 reports still render.

## v0.3.149 — Primavera P6 **XML (PMXML)** import (alongside the existing XER)
The schedule importer now accepts both Primavera P6 export formats, auto-detected from the content.
- **`schedule.parse_pmxml`** reads a P6 XML (PMXML) export into the same activity rows
  (id / name / planned-or-actual start+finish) as the XER parser — namespace-agnostic (the P6
  namespace varies by version, so it matches on local tag names). **`parse_schedule`** dispatches
  XER vs PMXML by sniffing the first non-space character.
- The existing **`POST /projects/{pid}/schedule/import-xer`** now upserts activities from either
  format (same re-import idempotency, milestone tagging, and 4D date window); the web import button
  and file picker accept **.xer / .xml**.
- `test_research` extends to import a PMXML export end-to-end.

## v0.3.148 — Webhook hardening: HMAC signing + retry/backoff + delivery log
Makes the outbound webhooks (module transitions → external automation) production-grade.
- **HMAC signing** — when `AEC_WEBHOOK_SECRET` is set, every delivery carries
  `X-Massing-Signature: sha256=HMAC(secret, "<timestamp>." + body)` + `X-Massing-Event-Timestamp`, so
  a receiver can verify authenticity and reject replays (the timestamp binds the signature).
- **Retry with exponential backoff** — a failed delivery retries up to `AEC_WEBHOOK_RETRIES` (default
  3) with `AEC_WEBHOOK_RETRY_BASE`-second backoff (0.5s, 1s, 2s…) before giving up. Still fail-open —
  a broken endpoint never blocks the transition.
- **Delivery log** — a bounded, process-local ring of recent attempts (url, event, ok, status,
  attempts, error), surfaced to platform admins at **`GET /webhooks/deliveries`** with the signing
  state — "did my hook fire?" observability.
- `test_webhooks` extends to pin the signature, the retry (2 fails → 3rd ok) + log, and the admin gate.

## v0.3.147 — openBIM: IFC4.3 infrastructure discipline + full ISO 19650 suitability codes
Closes the openBIM standards remainder.
- **IFC4.3 infrastructure entities** (`IfcAlignment`, `IfcRoad`, `IfcRailway`, `IfcBridge`,
  `IfcMarineFacility`, `IfcTunnel`, `IfcCourse`, `IfcPavement`, earthworks, …) now classify to the
  **Civil (C)** discipline instead of being lost to the default — their MasterFormat divisions (34
  Transportation / 35 Marine) sit outside the building divisions, so they're mapped directly.
  `classification.is_infra_class()` exposes the set. (`IFC4X3` was already a supported read schema.)
- **CDE suitability codes** — the information-container vocabulary now carries the higher ISO 19650
  codes **S5 (manufacture/procurement), S6 (PIM authorization), S7 (AIM authorization)** alongside
  the existing S0–S4 / A / B / CR / AB.
- `test_disciplines` pins the infra→Civil mapping.

## v0.3.146 — fix: `test_stored_ids` must set `IFC_DIR` (the actual red-CI cause)
`test_stored_ids` uploads a source IFC via `/source-ifc`, which writes to `IFC_DIR` (default
`/app/ifc`, read-only on CI/in the container). Sibling upload tests set `IFC_DIR` to a writable path;
this one didn't, so the upload — not the `/validate` temp write fixed in v0.3.145 — was what reddened
CI. Test now sets `IFC_DIR=./test_ifc_stored_ids`. (The v0.3.145 tempdir fix remains a valid
defense-in-depth for the `/validate` path.)

## v0.3.145 — fix: `/validate` wrote its temp IDS into the read-only container path
The stored-IDS validation (v0.3.143) wrote the temporary `.ids` next to the source tree
(`_DATA_SRC.parent`), which is writable locally but **read-only (`/app`) in the deployed container** —
so `POST /validate` with an uploaded or pinned IDS raised `PermissionError` in production (and reddened
CI once `test_stored_ids` first exercised that path). Now writes to the OS temp dir via
`tempfile.mkstemp`. No API change.

## v0.3.144 — openBIM: COBie Contact / Zone / System tabs
Rounds out the COBie handover workbook with the three tabs owners most often flag as missing, all
derived from the model.
- **Contact** — the people/organizations behind the model (keyed by email), from
  IfcPersonAndOrganization / IfcPerson / IfcOrganization, deduped.
- **Zone** — spatial groupings of spaces (IfcZone) with their member space names.
- **System** — functional groupings of components (IfcSystem / IfcDistributionSystem) with their
  member component names + predefined type.
- The COBie export now **merges** same-named sheets across sources instead of clobbering — so the
  model-derived System and the commissioning-derived System land in one tab; `_rows_to_sheet` takes
  the **union** of columns so no source loses a field.
- `test_cobie` (synthetic IFC) pins the extraction; `test_closeout` asserts the tabs + the merge.

## v0.3.143 — openBIM: pin a project IDS + validate against it
A project can now **pin the information-delivery specification (IDS)** its model must satisfy — the
EIR/BEP-mandated one — so validation runs against it every time without re-uploading.
- **`PUT/GET/DELETE /projects/{pid}/ids`** store, inspect (`?download=1` streams it), and clear the
  pinned IDS (object storage; editor to change, viewer to read). Store/clear are audit-logged.
- **`/validate` precedence**: an uploaded `.ids` still wins; otherwise `ids=auto` (default) uses the
  pinned IDS when present, else the built-in QA specs. `ids=stored` forces the pinned one (404 if
  none); `ids=default` forces the built-ins. Both JSON summary and the BCF punch list honor it.
- **Web**: the IDS Requirements panel gains a **"📌 Pin as project IDS"** action (builds the selected
  use-case IDS and pins it) with live status + unpin; `client` gets `pinProjectIds`/`projectIdsStatus`/
  `unpinProjectIds`/`idsBuildBlob`.
- Fixed a latent shared-temp-file collision in `/validate` (per-project temp name now).
  `test_stored_ids` pins the full lifecycle + precedence end-to-end (real IFC + real IDS engine run).

## v0.3.142 — openBIM: real bSDD linked-data alignment
Turns the bSDD story from "is it classified?" into "is it *linked* to a buildingSMART Data
Dictionary?" — genuine linked-data alignment, building on the v0.3.137 bSDD client + registry.
- **`bsdd.is_bsdd_uri()` / `parse_uri()`** recognize and decompose real bSDD class URIs
  (`identifier.buildingsmart.org/uri/<org>/<dictionary>/<version>/class/<code>`).
- **Alignment scoring** now reports two honest tiers — `classified` (has any type/classification)
  vs **`bsdd_linked`** (classification is an actual bSDD URI) — plus the distinct dictionaries the
  model references (Uniclass, IFC, an EIR-mandated one…), so a reviewer sees *which* it aligns to.
- **JSON-LD export** emits a bSDD-classified element's URI as a resolvable `@id` classification node
  (`"classification": {"@type": "@id"}` in the context), so the model graph is true linked data that
  resolves against bSDD — not just a bag of local codes.
- `test_bsdd` extends to pin URI recognition/parse, the two-tier alignment, and the JSON-LD linkage.

## v0.3.141 — Enterprise auth: TOTP two-factor authentication
Optional time-based one-time-password MFA, stdlib-only (no new dependencies) — a second factor at
sign-in for accounts that opt in.
- **`totp.py`** implements HOTP/TOTP (RFC 4226 / 6238) with HMAC-SHA1, a ±1-step skew window, an
  `otpauth://` provisioning URI for any authenticator app, and salted one-time recovery codes. The
  crypto is pinned to the published RFC test vectors.
- **Enrollment**: `POST /auth/mfa/setup` issues a secret + QR/manual key; `POST /auth/mfa/enable`
  confirms with a live code and returns 10 one-time **recovery codes** (shown once; only hashes are
  stored). `GET /auth/mfa/status`; `POST /auth/mfa/disable` requires password **and** a live code.
- **Login becomes two-step** when MFA is on: password → a short-lived challenge ticket, then
  `POST /auth/mfa/verify` with a TOTP *or* a (single-use) recovery code → session. Accounts without
  MFA are unchanged.
- **Web**: account-menu "Two-factor auth…" (enroll with key + code, view recovery status, disable)
  and a sign-in challenge step; `askText` gains a masked-`password` option.
- Additive schema sync adds `mfa_secret/mfa_enabled/mfa_recovery`. `test_mfa` pins RFC vectors + the
  full enroll → challenge → recovery → disable flow. Enable/disable/recovery-use are audit-logged.
  (SAML 2.0 SP + SCIM 2.0 remain — they need a live test IdP.)

## v0.3.140 — Enterprise auth: session revocation ("sign out everywhere")
Bearer tokens can now be revoked before they expire — closing a real gap where a leaked token
stayed valid for its full 7-day life even after the password was changed.
- **Token epoch** — every auth token carries an issued-at (`iat`); each account has a `token_epoch`
  watermark. The RBAC gate rejects any token issued before the watermark, so revocation is immediate
  (no session table needed). Additive schema sync adds the column to existing DBs.
- **Password change now revokes other sessions** — changing your password (or an admin resetting it,
  or a reset-token redemption) bumps the watermark, invalidating every other outstanding token. The
  current tab is handed a fresh token so it stays signed in.
- **"Sign out everywhere"** — a new account-menu action (`POST /auth/logout-all`) revokes all other
  sessions after a suspected token leak. Admins get a per-user **Revoke sessions**
  (`POST /auth/users/{u}/revoke-sessions`) for offboarding / lost devices — distinct from
  deactivation (revoke lets them sign in again; deactivate blocks re-login).
- All revocation events are audit-logged. `test_sessions` pins the contract end-to-end.
  (SAML/SCIM and TOTP MFA are the next enterprise-auth increments.)

## v0.3.139 — Web lint gate (ESLint, flat config) wired into CI
Adds static analysis to the web app so genuine defects (unreachable code, bad awaits, dead
expressions) are caught in CI alongside the strict `tsc` typecheck and the Vitest suite.
- **ESLint 9 flat config** (`apps/web/eslint.config.js`) with a pragmatic, low-noise ruleset:
  real-bug rules stay errors; patterns this codebase adopts on purpose (`any` at IFC/three/@thatopen
  boundaries, non-null assertions, `const self = this` closure capture in object-literal getters) are
  off or warnings, so the signal isn't drowned out. New `npm run lint` / `lint:fix` scripts.
- **CI gate** — a Lint (ESLint) step runs before the Vitest job in the web workflow.
- **Baseline cleaned to zero** — the 70-file baseline surfaced only 3 errors + 1 warning, all in
  `portal.ts`/`proforma.ts`; fixed by converting two side-effecting ternaries to `if/else` and one
  `let`→`const`. No behavior change.
- **Single, pinned toolchain** — a root `eslint` pin + override collapses the dependency tree to one
  ESLint (9.39.5), so `npm ci` is deterministic and the CLI resolves the same version everywhere.

## v0.3.138 — Security: pin the auth path fail-closed (regression guard)
Audited the whole auth/authz path for fail-open behavior and confirmed it is already **fail-closed** —
`verify_token` / `verify_password` / `signing.verify_path` all return a deny value (None/False) on any
malformed input or exception, never an allow, and the RBAC middleware denies anonymous callers under
RBAC. To keep it that way, `test_security` now pins the contract: a garbage / undotted / **tampered**
bearer token is rejected (401/403) by the gate and `verify_token` returns `None` for it, while the
genuine token still resolves — so a future edit can't silently turn an auth error into access.

## v0.3.137 — openBIM: version-pluggable standards registry + BCF 3.0 + bSDD; money-math tests
Makes the platform's open-standard support **pluggable to any version**, widens interoperability, and
pins the most error-prone financial math.
- **Money-math correctness tests** — the **equity waterfall** (`proforma/waterfall.run_waterfall`:
  pref accrual → return-of-capital → IRR-hurdle promote tiers) and the **GL trial balance** were only
  exercised indirectly. `test_waterfall` pins them to hand-computed numbers (72 pref + 428 RoC = 500 to
  the LP, 472 unreturned) plus hard invariants: dollar conservation across arbitrary multi-period cash,
  full return of capital before promote, the promote actually promoting the GP, and European style
  withholding promote until the LP is whole. `test_accounting` now asserts the double-entry invariant —
  trial balance debits == credits (== 125000) and the GL columns balance.
- **openBIM version registry** (`openbim.py`) + **`GET /openbim/capabilities`** — one source of truth
  for which open standards the platform speaks (IFC, BCF, IDS, bSDD, COBie, ISO 19650 CDE) and, per
  standard, which versions it **reads** and **writes**. The version lists are **derived from the live
  engines** (BCF versions from `bcf_io`, IFC schemas from `model_capabilities`) so the matrix can't
  drift from what's actually implemented, and adding a future version (IFC5, BCF 3.x, IDS 2.0) is a
  registry entry + an adapter rather than scattered `if version ==` edits. `supports(standard, version,
  mode)` answers "do we read/write X vN?" for guards and agents. `test_openbim_registry`.
- **BCF 3.0 read/write.** `bcf_io.py` (previously 2.1-only) now writes **BCF 3.0** on request and
  auto-detects the version on import. In 3.0 the `<Comments>` and `<Viewpoints>` move inside `<Topic>`
  and `<Labels>` become a `<Labels><Label>…</Label></Labels>` group — so a 3.0 file from a newer
  BIMcollab / ACC no longer silently loses its comments and labels on import. Both BCF export endpoints
  (`GET …/bcf/export` and `GET …/modules/{key}/bcf/export`) take `?version=2.1|3.0` (2.1 remains the
  default); import auto-detects. `test_bcf` gains a 3.0 round-trip + a crafted-3.0-file read.
- **bSDD lookup.** New `bsdd.py` — a thin, cached client for the buildingSMART Data Dictionary
  (`api.bsdd.buildingsmart.org`): `GET /bsdd/search?q=` finds classes, `GET /bsdd/class?uri=` resolves
  a class's canonical URI + property set. Fixed trusted host (no SSRF surface), 8s timeout, graceful
  502 on outage. Turns the classification alignment proxy into a path to real dictionary URIs.
  `test_bsdd` mocks the HTTP (no live network) — search/class parse, cache-hit, defensive parse, 404/502.

## v0.3.136 — openBIM: IDS validation failures export as a BCF punch list
Closes the model-QA loop. `POST /projects/{pid}/validate?format=bcf` now returns a **.bcfzip** of the
IDS non-conformances — one topic per failing specification, with that spec's failing elements selected
as the topic's components — so an IDS audit round-trips into Solibri / ACC / BIMcollab exactly like any
coordination issue, and a coordinator can jump straight to the offending elements. `format=json`
(default) is unchanged. Reuses the existing IDS validator (`aec_data.validate`) and BCF writer
(`bcf_io.export_records_bcfzip`); the new pure `validate.failures_to_bcf_records()` does the mapping.
`test_ids_authoring` covers the conversion + a real round-trip through `parse_records_bcfzip`.

## v0.3.135 — Accessibility: every native prompt/confirm replaced with keyboard-navigable modals
Removes the last blocking `window.prompt()`/`window.confirm()` dialogs from the app — 42 call sites
across the viewer, portal, drawings, connections, account, finance, and PDF-takeoff flows now use the
shared accessible modal helpers (`confirmModal` / `askText` / `promptModal`), which trap focus, close
on Esc/backdrop, restore focus on close, and carry `role="dialog"` + `aria-modal`. Destructive actions
(delete/remove/untie) get a red-styled confirm button. Behavior and every message string are unchanged;
only the dialog is now navigable and screen-reader friendly. (The remaining `window.prompt` in the
built bundle lives inside the third-party @thatopen viewer library, not our code.)

## v0.3.134 — Accessibility: reduced-motion support + screen-reader announcements
P2 a11y quick wins (Section 508 / WCAG 2.1 — often a procurement gate), no functional change.
- **Reduced motion:** a global `@media (prefers-reduced-motion: reduce)` rule near-instantly completes
  every transition/animation (toast slide-ins, spinner, panel fades) for users who set that OS
  preference — state still changes, just without the motion. Leaves the 3D viewer's own render loop
  alone (that's content, not decoration).
- **Screen-reader announcements:** the toast host is now a polite `aria-live` region (`role="status"`),
  so notifications are announced instead of being silently invisible to assistive tech; **error** toasts
  use `role="alert"` for immediate (assertive) announcement. The loading overlay is likewise a
  `role="status"` live region that announces its label (incl. download progress), with the spinner
  marked `aria-hidden`.

## v0.3.133 — P1 hardening: audit the contractual mutations + count without loading + CI test guard
Follow-on to the v0.3.132 P0 block — enterprise-readiness P1 items, all behavior-preserving.
- **Audit-log coverage for contractual mutations:** module workflow **transitions** (RFI answered,
  CO approved — `module.transition:<key>:<action>`, with actor, record id, and the resulting state),
  record **deletes** (`module.delete:<key>`), and **bulk** actions now write to the append-only
  `audit_log` (readable at `GET /audit`). Previously only project/member/user/settings/contract/IFC
  events were audited; the config-engine state changes — the ones an owner or auditor most needs to
  reconstruct — were not. `test_audit_coverage`.
- **Executive report counts via SQL aggregate:** the executive summary tallied open/total RFIs,
  submittals, change orders and incidents by loading every record (up to 100k per module) into memory;
  it now uses a single `GROUP BY workflow_state` per module (`state_counts`), which is hardened to
  return `{}` for an unknown module and key a NULL state by `""`. `test_search_alerts` covers it.
- **CI test-manifest guard:** `run_tests.py` now fails the gate if any `test_*.py` on disk isn't
  registered in its hand-maintained `TESTS` list — a test nobody runs can no longer slip in silently.
- **Green CI restored (bundle-budget false positive):** the app-shell size guard filename-matched every
  `index-*.js` chunk, so it wrongly counted the lazy **pdf.js** vendor chunk (its source module is
  `index.js`, ~163 KB, loaded only when a PDF opens) as part of the eager shell — pushing the reported
  shell to 330 KB and failing the build on every push. It now derives the true entry from
  `dist/index.html` (entry chunk + CSS + the split `app-*` chunk); the real first-party shell is 166 KB,
  well within the 220 KB budget.

## v0.3.132 — P0 security: close cross-tenant access + gate SSO + atomic refs
The must-fix block from the enterprise-readiness audit — no data-shape or workflow change, pure hardening.
- **Cross-tenant access closed:** every `/projects/{pid}/…` route now enforces **project membership**
  via `require_role` (reads→viewer, writes→reviewer/editor) — 59 routes that authorized on identity
  alone (incl. full model exports and financial reads) are gated. A new **CI guard** (`test_route_authz`)
  enumerates all 381 project routes and fails the build if any lacks a membership check, so it can't
  regress. `require_role` is tagged (`_role_gate`) for detection.
- **Portfolio roll-ups scoped to memberships:** the cross-project proforma / construction / executive /
  FCA roll-ups now return only the caller's projects (`rbac.member_project_ids`), never every tenant's
  GMP / EAC / IRR / equity.
- **SSO provisioning gated:** OAuth self-provisioning honors `AEC_OAUTH_ALLOWED_DOMAINS` (and an optional
  `AEC_OAUTH_NO_AUTOPROVISION=1` invite-only mode). The production boot guard now also refuses to start
  on Postgres when `AEC_TRUST_XUSER=1` (impersonation) or when `S3_ENDPOINT` is set with default
  `minioadmin` credentials.
- **Atomic human refs:** record refs (RFI-001…) now come from a per-(project,module) counter row taken
  under a row lock — concurrent creates can't collide, and deleting a record no longer lets a later
  create reuse a ref (the old `COUNT(*)` scheme did). `test_ref_counter`.

## v0.3.131 — Unified sheet view: PDF-editor markups appear on the SVG sheet (shared coordinates)
Completes the 2D convergence with a **shared coordinate space**. Every takeoff markup now stores a
page-normalized (0..1) anchor when saved from the PDF editor, so the SVG drawings viewer renders those
markups **on the same sheet** alongside its native pins — one place to see everything on a drawing.
- **PDF editor** (`pdfTakeoff`): the ⭳ Save-to-sheet path computes each markup's normalized anchor from the
  PDF page dimensions and persists `data.nx/ny`.
- **SVG sheet viewer** (`drawings.ts`): loads both its pins and the PDF-editor's takeoff markups, placing the
  latter by `nx/ny × content-box` (a distinct amber ◆ badge showing the measurement). They're the same
  `drawing_markups` rows, so they promote to RFI / delete right from the SVG view.
- No schema change (nx/ny ride in the existing `data` JSON). Web-only.

## v0.3.130 — One 2D markup model: takeoff markups persist to the sheet + promote to RFI
Converges the two previously-disconnected 2D markup systems onto one server-side store. The pdf.js
takeoff editor's structured markups (distance / area / count / rect / text / stamp) now persist into the
same `drawing_markups` table as the SVG sheet pins — so they reload on reopen and can be **promoted to an
RFI** exactly like a pin, instead of only flattening to a throwaway PDF.
- **Backend** (additive, no migration tool): `drawing_markups` gains `kind` + `data` (JSON geometry).
  New `POST /projects/{pid}/drawings/markup/bulk` saves a whole sheet's scene (`replace` clears the
  caller's own prior unpromoted markups — anything promoted to an RFI is kept). RFI promotion now carries
  the markup's measurement into the issue.
- **2D editor**: opening a drawing sheet's PDF binds it to the sheet — it **loads** existing markups and a
  new **⭳ Save to sheet** button persists them. The SVG pin view is untouched (PDF markups live in their
  own coordinate namespace on the shared store). `test_markup`.

## v0.3.129 — The 2D editor everywhere + save generated PDFs to Documents + pin perf
Optimizes the two editors and uses them to best intention throughout (from an audit of both):
- **Save generated PDFs to Documents** — a marked-up report / pay app / statement / drawing sheet can now
  be filed into the Document Manager (a folder picker → real, versioned revision) via a shared
  `saveToDocuments` helper, not just downloaded.
- **The 2D editor replaces native PDF tabs throughout** — the sheet **PDF markup** button in the drawings
  editor, the viewer's **Compose sheet (PDF)**, **G702/G703 pay app**, **lien waivers**, the project
  **status report**, **investment memo / pitch deck**, the **G702 draw package**, and **WH-347** now open in
  the in-app 2D editor (measure / mark up / save) instead of the browser's native PDF tab.
- **3D pin-overlay perf** — the BCF/RFI pin overlay reprojected every marker every frame; it now skips the
  reprojection + DOM writes unless the camera moved, the viewport resized, or the pin set changed (a still
  scene with many pins costs ~nothing).

## v0.3.128 — Every PDF opens in the in-app viewer, marks up, and saves back
Closes the gap where only local files reached the markup viewer and annotations only downloaded. The
takeoff/markup viewer (`pdfTakeoff.ts`) now opens a PDF from a **server URL** (fetched with auth), not
just a local `File`, and takes an optional **save-back callback** — with a new **⭱ Save to source**
toolbar button that flattens the markups and posts them back. A shared `openPdfUrl(api, url, name, opts)`
helper (`drawings/openPdf.ts`) is the single entry every surface routes through:
- **Record attachments** — a stored PDF attachment now opens in the viewer (📄 tile) instead of a bare
  link; the marked-up copy saves back as a new attachment on the record.
- **Document manager** — each PDF gets a **✎** action: open in the viewer, mark up, and **save as a new
  revision** (docmanager versioning/supersede).
- **Contracts / change orders** — "🖊 View & markup" now saves the redlined copy back as an attachment
  (previously the annotations were lost on download).
- **Module record PDF** — a **🖊 Markup** button opens the generated record PDF in the viewer and saves
  the marked-up copy back as an attachment.
- **Report Center** — a **🖊 Markup** button opens any report in the viewer; **PDF tools** gained
  **👁 Open & mark up…** so any PDF (including a downloaded generated one) can be viewed/marked up in-app.

## v0.3.127 — A/E/C stamps & professional seals (submittal review + PE/RA seal)
Real construction/design stamping on PDFs — the two legally distinct classes, done properly.
- **Stamp template library** (server = source of truth, `stamps.py` + `GET /stamps/library`): submittal
  **review** (both **EJCDC** — Approved / Approved as Noted / Revise and Resubmit / Rejected, and **CSI**
  — No Exceptions Taken / Make Corrections Noted / Amend and Resubmit / Rejected / For Record Only),
  **inspection** (Pass / Partial / Fail), and **status** (For Construction / Void / As-Built …). Review
  stamps carry reviewer, firm, in-responsible-charge, submittal no., spec section, date — and bake in the
  standard **design-conformance disclaimer** (review is only for general conformance with the design
  concept; the contractor keeps responsibility for quantities, dimensions, means/methods, coordination).
- **Professional seal + signature** (`POST /pdf/seal`): renders a *visible* PE/RA seal + signature/date
  block, then applies a **tamper-evident PAdES digital signature LAST** so any later change is detectable.
  Honest about compliance — the self-signed platform certificate is demonstration / tamper-evidence, not
  board-accepted sealing; configure the licensee's own certificate (`ESIGN_P12`) for regulatory use.
- **UI**: a **🏛 Stamp & seal PDF** tool — pick a PDF, choose a template, fill fields / disposition, place,
  and download the stamped or sealed PDF. Client methods `stampLibrary` / `pdfStamp` / `pdfSeal`.
- Rendering is reportlab overlay + pypdf composite (permissive licenses; **no PyMuPDF**). `test_stamps`.

## v0.3.126 — PDF markup: stamps + tool sets + server merge/split/rotate (phases 2–3)
Completes the PDF markup/manipulation stack — interactive stamps/text + reusable tool sets on the
client, and server-side page ops via pypdf. Still permissive-only (no PyMuPDF/AGPL).

- **Text + dynamic stamps** in the PDF takeoff — a 𝗧 Text tool and a 🔖 Stamp picker with dynamic
  stamps (APPROVED / REVIEWED / FOR CONSTRUCTION / VOID / AS-BUILT / `{{user}} · {{date}}` …) whose
  `{{user}}/{{date}}/{{time}}/{{file}}` fields resolve at placement. They render on the overlay and
  **flatten into the exported PDF** (stamps in a red box).
- **Tool sets** — 💾 Save / 📂 Load the whole markup scene (calibration + all markups) as JSON, so a
  set of stamps/measurements is reusable and shareable across sheets (the Bluebeam Tool Chest idea).
- **Server PDF ops (`pdfops.py`, pypdf)** — `POST /pdf/{info,merge,split,extract,rotate}`: merge a
  drawing set into one file, split to one-PDF-per-page (zip), extract a page range (`1,3,5-7`), rotate
  by 90°. A **🗂 PDF tools** launcher (merge/split/rotate/extract uploaded PDFs). Non-PDF uploads 422.

Verified: `test_pdfops` (engine + HTTP merge/split/extract/rotate + non-PDF reject); web typecheck +
build + 59 vitest.

## v0.3.125 — PDF markup: flatten to a real PDF (markup stack, phase 1)
First phase of a Bluebeam-Revu-style PDF markup/manipulation stack (three decoupled layers: PDF.js
render · interactive markup · pdf-lib/pypdf persistence). Built on the existing PDF takeoff.

- **Flatten markups into a downloadable PDF** — the ⤓ PDF button in the PDF takeoff burns every markup
  (distance, area, count, rectangle + label/quantity) into a real PDF via **pdf-lib** (MIT), so a
  marked-up drawing round-trips as a PDF, not just CSV. Handles the PDF.js(top-left)→PDF(bottom-left)
  Y-flip; markups are page-tagged so multi-page sets export to the right page (also fixes cross-page
  overlay bleed).
- pdf-lib is code-split (dynamic import) — no cost to the main bundle until you export.

Deliberately **permissive-only**: pdf-lib (client) + pypdf (server, already a dep) — **no PyMuPDF**
(AGPL, incompatible with a proprietary product without a paid Artifex license). Next phases: Fabric.js
interactive stamps + tool sets, and server-side pypdf merge/split/rotate.

Verified: web typecheck + build (pdf-lib bundles) + 59 vitest.

## v0.3.124 — Drawing revisions, sealed issuances, title blocks (AIA completion)
Completes the AIA drawing-issuance chain from v0.3.123 — revision deltas, digital seals, and title-block
metadata.

- **Revision / delta register**: `POST /projects/{id}/drawings/{drawing_id}/revise` records a delta on a
  sheet (rev, date, description) and can cite the driving change instrument (**ASI / CCD / Addendum /
  Bulletin**); it appends to the sheet's revision block and bumps the current revision.
  `GET …/drawing-set/revisions` is the cross-sheet register (newest first) with a by-instrument rollup —
  the "what changed, when, and why" log a set carries.
- **Sealed issuances (PAdES)**: `GET …/drawing-set/issuances/{iid}/sealed.pdf` returns the issuance
  transmittal **digitally sealed** by the professional of record via the existing e-sign — the
  tamper-evident electronic seal jurisdictions require for permit/IFC submittal (unsealed with
  `X-Sealed: false` when e-sign isn't configured).
- **Title-block completeness**: generated sheets (`sheet.svg`/`sheet.pdf`) now carry **ISSUED FOR** +
  **REV** in the title block (`?purpose=&rev=`).
- Web: a revision register + 🔏 sealed-PDF links on the Drawing-set register; `reviseDrawing` /
  `drawingRevisions` / `issuanceSealedUrl` client methods.

Verified: `test_drawing_revision` (deltas cite ASI, register rollup, sealed PDF) + `test_preview`
(title-block change safe); ruff clean; web typecheck + build.

## v0.3.123 — AIA drawing issuance: per-discipline sheet set + issuance register
Turn the model into a full, correctly-numbered 2D drawing set, then release it the way an A/E office
does — dated issuances for a purpose, with the sheet-index × issuance matrix the standards expect.

**Discipline sheet-set generation.** **`sheetgen.py`** generates a standard set — **G-** General ·
**C-** Civil · **L-** Landscape · **S-** Structural · **A-** Architectural · **FP-** Fire Protection ·
**FA-** Fire Alarm · **P-** Plumbing · **M-** Mechanical · **E-** Electrical · **T-** Telecom — each a
cover/notes sheet, one plan **per building level** (S-101…S-1NN), and the usual elevations/sections/
details/schedules, numbered per NCS (`M-101` = Mechanical / Plans / 01). **Fire Alarm (FA-)** is a
distinct series from Fire Protection (FP-) in the vocabulary, `parse_sheet_id`, naming validation and
the `drawing` module. `GET …/drawing-set/plan` (preview) + `POST …/drawing-set/generate` (auto-detects
disciplines from the model, or `{all:true}`/explicit list; idempotent). **Mass-ready**: bulk-inserts in
one transaction — a 50-storey, 9-discipline set (532 sheets) generates in ~0.1s (was ~11s).

**Drawing issuance register (AIA/CD).** New **`issuance.py`** + `drawing_issuance` module: issue the
current set for a **purpose** (SD/DD/CD/Issued-for-Permit/Bid/Construction/Addendum/Conformed/Record),
snapshotting every sheet + its revision. `POST …/drawing-set/issue`, `GET …/issuances` (history),
`GET …/issuance-matrix` (the **sheet-index × issuance grid** — each sheet's revision in each issue),
per-issuance transmittal PDF stamped with the purpose. A **📤 Issue set** control + issuance table +
matrix on the Drawing-set register.

Verified: `test_sheetgen` + `test_issuance` (issue snapshots, matrix reconstructs which sheet went in
which issuance, per-issuance transmittal, AIA purposes); mass test 532 sheets / 0.1s; ruff clean; web
typecheck + build clean.

## v0.3.122 — Battle-tested for mega-project scale (200k+ records)
Load-tested every heavy read path against a seeded ~220k-record project (research-sized for a $500M+
job: ~10k RFIs, 20k cost lines, 12k punchlist, 15k timesheets, …) and fixed what didn't hold up.

- **my-work** was returning **every** actionable row across all modules — a ~25 MB, 4 s response on a
  mega project. Now a bounded to-do queue: newest-N per module (indexed) + a 500-item cap, lean columns
  only (no JSON blob). 25 MB → ~100 KB, 4 s → ~0.5 s.
- **BCF export** ran a per-record `get_record` (comments/timeline/rollups it never uses) — an N+1 that
  took ~12 s on an 8k-issue module. `list_records` already returns every column BCF needs, so it's one
  query now (~1 s) with a 25k-record cap (logged when hit).
- **Dashboard** loaded the JSON `data` of the entire non-terminal tail of all 118 modules just to check
  due dates. Now it reads JSON only for modules that have a due-date field and pulls action items from a
  bounded, state-filtered query. 3.8 s → ~1.2 s.
- **Indexes**: added `(project_id, created_at)` — every list does `ORDER BY created_at`, previously a
  filesort — and `(project_id, assignee)` for the work queues. Backfilled on existing DBs at startup.
- **Connection pool** is now sized from the environment (`AEC_DB_POOL_SIZE`/`_MAX_OVERFLOW`/`_RECYCLE`/
  `_TIMEOUT`) instead of SQLAlchemy's 5+10 default, which starves a multi-worker API under load.
- New reusable harness: `seed_scale.py` (bulk-seeds every module at configurable volume) +
  `loadtest.py` (per-endpoint latency + concurrency), and a `test_scale` regression that locks in the
  pagination clamp, bounded my-work, single-query BCF, and index presence.

Verified: full backend suite green (incl. `test_scale`); ruff clean; security review clean.

## v0.3.121 — Cost traceability by IFC GlobalId (model → cost → GL)
Closes the moat of the resourcing/accounting plan — cost and billing tied to the actual model elements
they pay for, by GlobalId. A cost-code-only ledger can't answer "what did *this* column cost?"; this can.

- **`traceability.py`** walks every cost line (budget / commitment / direct cost / sub invoice) that
  carries `element_guids` and computes **coverage** — the share of job cost tied to real model elements —
  overall and **per cost code**, plus `element_costs(guid)` for "what did this element cost?" (by kind).
- Endpoints `GET /projects/{pid}/cost/traceability` and `GET /projects/{pid}/elements/{guid}/costs`.
  A **🔗 Cost Traceability** panel: coverage KPIs (color-banded), a GlobalId lookup, and a
  per-cost-code coverage table. `costTraceability` / `elementCosts` client methods.

Verified: `test_traceability` (coverage 93.3%, element→cost by GUID and by kind, untagged→0); ruff clean;
web typecheck + vitest + build.

## v0.3.120 — General ledger: balanced double-entry journal + trial balance + chart of accounts
Closes A2 of the resourcing/accounting plan — the posting bridge to the accounting system of record.

- **`accounting.py`** gains a standard construction **chart of accounts** (AR, contract asset/liability,
  AP, contract revenue, construction costs) and a **balanced double-entry journal** posted from job cost
  (Dr Construction Costs / Cr AP), owner billing (Dr AR / Cr Revenue) and the **WIP percentage-of-completion
  adjustment** (under-billing → Dr Contract Asset / Cr Revenue; over-billing → Dr Revenue / Cr Contract
  Liability) — so Contract Revenue nets to **earned**. Plus a **trial balance** (debits = credits, per account).
- Endpoints `GET /accounting/chart-of-accounts`, `/accounting/journal-entries`, `/accounting/trial-balance`
  (the GL-CSV + QuickBooks-IIF exports already existed). A **📒 General Ledger** panel (trial balance +
  journal + CSV/IIF export). `journalEntries` / `trialBalance` client methods.

Verified: `test_wip` extended (journal balanced, trial balance ties, revenue nets to earned, over-billing
posts to contract liability) + `test_accounting`; ruff clean; web typecheck + vitest + build.

## v0.3.119 — Contractor financial statements (POC income statement + contract position)
The construction-only statement lines a generic P&L / balance sheet miss — the balance-sheet twin to the
WIP schedule (A2 of the resourcing/accounting plan).

- **`contractor.py`** — from the WIP: a **percentage-of-completion income statement** (revenue = earned,
  not billed; cost of revenue = cost-to-date; gross profit + margin) and a **contract-position** section
  (**contract asset** = under-billings, **contract liability** = over-billings, **retainage receivable**,
  **accounts payable** from unpaid sub invoices, and **net contract working capital** = under-billings +
  retainage − over-billings − AP). Company-wide roll-up too.
- Endpoints `GET /projects/{id}/contractor-statements` + `/contractor-statements/portfolio`; a
  **Contractor Financial Statements** report; the statements render on the WIP panel + a second PDF link.
- `contractorStatements` client method.

Verified: `test_wip` extended (POC income statement, contract asset/liability, net working capital,
portfolio, both report PDFs); ruff clean; web typecheck + vitest + build.

## v0.3.118 — WIP schedule: percentage-of-completion + over/under-billing
The defining construction-accounting artifact, and the accounting twin to the earned-value module —
built on the job cost that already exists, no new cost model.

- **`wip.py`** — percentage-of-completion (**cost-to-cost**: cost-to-date ÷ total estimated cost) →
  **earned revenue** = % complete × contract value → compared to billed for the contract position:
  **over-billing** (billings in excess of costs & earnings — a **liability**) or **under-billing** (costs
  & earnings in excess of billings — an **asset**, and the classic cash drag on profitable jobs). Plus
  retainage, cost-to-complete, gross profit/margin, profit-to-date and backlog.
- Endpoints `GET /projects/{id}/wip` and `GET /wip/portfolio` (one row per job, worst cash position
  first). A **📄 WIP Schedule** panel (KPIs + a colour-coded over/under-billing callout + contract-position
  table + portfolio roll-up) and a signed PDF report. Client `wip` / `wipPortfolio`.
- Contract value comes from the prime contract + approved COs (falling back to the SOV); billings from
  owner invoices; retainage from the G703 — all reused from `cost.py`.

Verified: `test_wip` (POC 50%, under-billed 200k asset flips to over-billed 200k liability, gross profit
+ margin, backlog, retainage, portfolio + PDF); ruff clean; web typecheck + vitest + build. Demo shows a
39%-complete job under-billed ~$7.8M — the profitable-but-cash-short story.

## v0.3.117 — Resource loading, made real: cost-loaded, relational, with leveling
Promotes resource loading from a flat crew-count (and no UI) to a relational, cost-loaded engine with a
panel — tying the schedule to resources and cost codes.

- **`resource_assignment` model** — ties a resource (Labor / Equipment / Material, with a rate) to a
  **schedule activity** and a **cost code**. That's the schedule ↔ resource ↔ cost join; the cost also
  rolls up onto the cost code (`resource_budget`).
- **Cost-loaded engine** — `resource_loading.py` now spreads assignment units + cost across each week
  into a **manpower histogram** (by trade / type) and cumulative **unit + cost S-curves**, with
  over-allocation flags against an availability cap. Falls back to activity `crew_size` when no
  assignments exist, so the classic curve still renders.
- **Leveling advisory** — `GET /schedule/resource-leveling?cap=` lists over-allocated work that still
  has **CPM total float** and can be smoothed (shifted within float) to shave the peak without moving the
  finish; critical-path work is reported as locked. Advisory only.
- **UI** — a `👷 Resource loading` panel (Schedule stage): editable availability cap, stacked-by-trade
  histogram, cost S-curve, KPIs (peak / total cost / over-allocated weeks) and the leveling table, plus a
  PDF report. Demo seeds six crews so the sample shows a real peak + leveling candidates.

Verified: `test_resource_loading` (cost-loaded histogram + S-curves, over-allocation, `resource_budget`
rollup, leveling picks the float-bearing work, crew_size fallback, PDF) + the module-contiguity gate;
ruff clean; web typecheck + vitest + build.

## v0.3.116 — Portfolio CPI (cost efficiency) in the executive roll-up
The cross-project executive dashboard already showed SPI + EAC + variance-at-completion per project;
it now also shows **CPI** — cost efficiency (EV ÷ AC) — so the "which jobs are bleeding money?"
question is answerable at the portfolio level alongside schedule.

- `px.summary()` gains a `cpi` in its budget block (EV/AC, the same numbers the project dashboard
  uses); surfaced per-project in `/portfolio/executive` and as a new **CPI** column (green ≥ 0.95,
  red below) next to SPI in the executive table.

Verified: `test_dashboard`; ruff clean; web typecheck + vitest + build. (Additive field — no
behaviour change to existing rows.)

## v0.3.115 — EVM charts: CPI–SPI quadrant + captured-snapshot performance trend
Two earned-value visualizations that make cost/schedule performance readable at a glance, plus the
persisted snapshots that back a real historical trend.

- **CPI–SPI quadrant (the "bullseye")** — a new `scatterQuadrant` chart plots the project and every
  control account on the cost × schedule plane, split at 1.0: upper-right is under budget + ahead,
  lower-left is trouble. Built from the existing EVM snapshot — no extra query.
- **Persisted EVM snapshots** — a new `evm_snapshot` module + `POST /projects/{id}/evm/snapshot`
  captures the current state (CPI/SPI/SPI(t)/EAC/% complete) as a dated baseline. `GET …/evm/trend`
  returns them oldest-first, and the dashboard shows a **CPI/SPI performance-index trend** (a falling
  line = efficiency slipping) with a 📸 Capture-snapshot button. The trend line also renders in the
  EVM PDF report once ≥ 2 snapshots exist.
- **Sample model** now seeds six weekly snapshots so the demo trend tells a real "schedule slipping"
  story out of the box.

Verified: `test_evm` (capture → trend, quadrant data, PDF with trend) + `charts` (scatterQuadrant plots
+ escapes) ; ruff clean; web typecheck + vitest + build.

## v0.3.114 — Element property + classification editor; sample model refreshed
Closes the model-authoring loop and brings the demo sample in line with everything shipped this cycle.

- **Structured property + classification editor** — selecting an element in the viewer now offers an
  **✎ Edit / Classify** form: set a Pset property (typed str/float/int/bool) and attach a
  **classification reference** (Uniclass 2015 · OmniClass · Uniformat II · MasterFormat), replacing the
  old free-text prompt. Backed by the `set_element_pset` and new **`set_classification`** edit recipes
  (GUID-stable; reuses one `IfcClassification` source per system so tags don't duplicate). Each edit
  re-publishes and the panel re-reads the element.
- **Model-based EV, no false alarms** — `evm.model_ev()` now only flags a *front-loaded SOV* once field
  verification actually exists (`has_field_data`); an un-surveyed job no longer reads as a distortion.
- **Sample model refreshed** — the Pages demo model now carries the full Draft-family set (steel
  columns/beams, rebar, footings, duct/pipe/cable-tray runs, ceiling + floor coverings, railing,
  electrical panel + sanitary terminal), realistic **EVM data** (cost-coded activities with EV methods +
  actuals → CPI/SPI, S-curve, Earned Schedule, model-EV) and a derived grid — surfaced across Model
  Analysis, Earned Value and the drafting refs.

Verified: `test_authoring_props` (Pset + classification round-trip) + `test_evm`; the model-authoring
+ structural/MEP/architectural/grid suites; typecheck + vitest (58) + build; ruff clean.

## v0.3.113 — Earned Value Management, E7: model-based EV (module complete)
The differentiator — earn value off the **physically installed model**, not a billing SOV — completes
the EVM module (E1–E7).

- **Model-based EV** (`evm.model_ev()` + `GET /projects/{id}/evm/model-ev`) — EV grounded in
  field-verified installed model elements (the install-coverage engine): **model % complete = installed
  elements ÷ total × BAC**, the units-complete method sourced from the model. It's independent of the
  schedule/billing %, so it **cross-checks the schedule EV**: when reported EV runs materially ahead of
  physical installation, it flags a likely **front-loaded SOV** — the exact distortion the research warns
  about. Surfaced on the EVM dashboard (with a ⚠ when divergent).
- With this the EVM module is complete: unified metrics + control accounts (E1), forecast family (E2),
  Earned Schedule (E3), S-curve + dashboard + report (E4/E5), EV measurement methods + stage-adaptive
  forecast (E6), and model-based EV (E7).

Verified: `test_evm` (model-EV graceful with no index + structure) + the full E1–E6 checks; typecheck +
vitest (56) + build; ruff clean.

## v0.3.112 — Earned Value Management, E6 + adaptive forecast
EV measurement rules of credit + the stage-adaptive forecast guidance from the construction-forecasting
research.

- **EV measurement methods** — `schedule_activity` gains an **EV method** (percent · **0-100** ·
  **50-50** · **units** · milestone · **LOE**) + units-complete/units-total. The engine honours the rule
  of credit: 0/100 earns nothing until complete; 50/50 earns half once started; units earns
  units_complete/units_total; **LOE earns exactly its planned value (EV=PV)** so it can't distort the
  schedule variance. Applied consistently in the metrics, S-curve, and Earned Schedule.
- **Stage-adaptive forecast guidance** — the forecast now flags the project **stage** and which forecast
  to trust: **early/mid → Earned Schedule (SPI(t))** is most accurate (cost EAC is volatile), **late
  (≥55%) → cost-efficiency (BAC/CPI)** firms up. Straight from the study finding that no single EAC
  formula is best at every stage. Shown on the EVM dashboard forecast card.

Verified: `test_evm` extended (0/100 → EV 0, 50/50 → 50k, units 3/4 → 75k; stage recommendation) +
`test_modules` (new fieldset passes the contiguity gate) + typecheck + vitest (56) + build; ruff clean.

## v0.3.111 — Earned Value Management, E4+E5: S-curve + EVM dashboard
Makes the EVM engine **visible** — an **📊 Earned Value** destination in the construction workspace.

- **S-curve** (`evm.scurve()` + `GET /projects/{id}/evm/scurve`) — cumulative **PV** (full planned
  baseline) plus **EV** and **AC** to the data date, over week/month buckets, drawn as the classic
  three-line performance chart (EV/AC lines end at the data date while PV runs to the planned finish). EV
  is reconstructed from each activity's actual window; AC from dated direct costs.
- **EVM dashboard** (`portal/panels/evm.ts`) — an indices dashboard (**CPI · SPI · SPI(t)** with health
  bands, CV/SV/SV(t)), the **forecast panel** (EAC family, ETC, VAC, TCPI + warning), the **S-curve**,
  the **Earned Schedule** summary (forecast finish + days-late), and the **control-account (cost code)
  table** — worst variance first.
- **EVM report upgraded** — the `evm` report now emits CPI/SPI/SPI(t), the full performance + forecast
  tables, Earned Schedule, control accounts, and the PV/EV/AC S-curve (was SPI + a cash curve).

Verified: `test_evm` extended (S-curve PV-full / EV-AC-to-date shape; upgraded report PDF renders) +
typecheck + vitest (56) + build; ruff clean.

## v0.3.110 — Earned Value Management, E3: Earned Schedule
Adds the modern **time-based** EVM extension that fixes the well-known defect where dollar SV/SPI decay
to $0 / 1.0 at project end regardless of lateness.

- **`evm.earned_schedule()` + `GET /projects/{id}/evm/earned-schedule?period=week|month`** — builds the
  time-phased **PV baseline curve** from the schedule, then projects current EV onto its time axis:
  **ES = C + (EV−PV_C)/(PV_{C+1}−PV_C)**, and from it **SV(t) = ES−AT**, **SPI(t) = ES/AT**, and
  **IEAC(t) = PD/SPI(t) → forecast finish date** (+ days-late). Included in the `/evm` snapshot too.
- SPI(t) stays meaningful right through completion, so a superintendent gets "**4 weeks behind, forecast
  finish 2026-XX-XX**" instead of a dollar SV that quietly returns to zero. The PV curve it returns is
  the same one the S-curve dashboard (E4/E5) will draw.

Verified: `test_evm` extended — a 40-week job at 40% complete in week 20 yields **ES ≈ 16 wk, SPI(t) ≈
0.80, forecast finish beyond plan** — plus the E1/E2 checks; typecheck + vitest (56) + build; ruff clean.

## v0.3.109 — Earned Value Management, E1+E2: unified engine + forecast family
Research-backed (PMI/ANSI-EIA-748 + a construction-forecasting study) EVM. The app had two disconnected
halves — schedule earned value (no Actual Cost) and cost actuals by cost code (heuristic forecast). This
**joins them by cost code (the control account)** into one standards-aligned metric set.

- **`evm.py` + `GET /projects/{id}/evm`** — PV, EV, AC, BAC; **CV = EV−AC, SV = EV−PV, CPI = EV/AC,
  SPI = EV/PV**, % complete, % spent, with **health bands** (good ≥1.0 · acceptable ≥0.95 · concerning
  ≥0.90 · critical). A **per-control-account (cost code) table** joins schedule EV/PV with cost AC, so you
  see which cost codes are over budget vs behind schedule.
- **Forecast family** — the four canonical **EACs** (BAC/CPI · AC+(BAC−EV) · AC+(BAC−EV)/(CPI×SPI)),
  a working EAC, **ETC**, **VAC**, and **TCPI** to BAC and to the working EAC — with the **>1.10
  structural-warning** flag. Shown together, because the best EAC is stage-dependent, not one formula.
- A `data_date` cut-off parameter for period reporting.

This is phase 1 of a full EVM module; Earned Schedule (SPI(t)), the time-phased S-curve + dashboard, EV
measurement methods, and **model-based EV from IFC quantities** follow.

Verified: `test_evm` (BAC 200k / EV 75k / PV 150k / AC 80k → CV −5k, SV −75k, CPI 0.938, SPI 0.5; the full
forecast family + TCPI warning; control-account join) + typecheck + vitest (56) + build; ruff clean.

## v0.3.108 — Model authoring: incremental preview fragments + MEP fittings
Completes the draft-performance work and rounds out MEP.

- **Incremental preview fragment** — `POST /projects/{id}/edit-preview` authors *just the placed element*
  into a minimal one-element IFC at the target level's elevation (`aec_data/preview.py`) and converts
  only that to a fragment, which the viewer loads immediately as real geometry — so the whole-model
  reconvert no longer gates what you see. Fully **fail-open**: if the source or converter is unavailable
  the viewer just keeps the optimistic amber proxy and waits for the normal publish. The preview is
  auto-disposed when the full model re-streams.
- **MEP fittings** — duct/pipe **elbows** and **tees / junctions** (`IfcDuctFitting` / `IfcPipeFitting`
  with BEND / JUNCTION predefined types) join the MEP palette, to detail the runs.
- **Testing & debug pass** — the new `test_preview` plus a regression sweep across the authoring and
  generate paths (`test_generate` / `test_estimate` / `test_engines` and the four model-authoring
  suites) all green, confirming the `edit.py` refactor (optional `profile` arg + the new recipes) didn't
  regress existing authoring.

Verified: `test_preview` (one-element metre model at the target level carrying the steel profile) + the
model-authoring + regression subset + web typecheck / vitest (56) / build; ruff clean.

## v0.3.107 — Model authoring, P6: optimistic draft placement
Drafting now gives **instant feedback** instead of a blank wait while the server authors and re-streams.

- **Optimistic proxy** (`viewer/draft/draftProxy.ts`) — the moment you place an element, a lightweight
  amber proxy (box for equipment, line for a wall/beam/duct/pipe/rebar/railing, polygon outline for a
  slab/roof/covering) appears exactly where it will land, at the active level. When the server finishes
  authoring the real IFC and the fragment is re-streamed, the proxy clears and the real geometry takes
  its place (proxies also clear on failure).

This is the client half of the draft-performance work; the server-side **incremental single-element
fragment** append (converting just the new element instead of the whole model) is the remaining
optimization and is tracked for a follow-up, since it touches the IFC→fragments publish pipeline.

Verified: web typecheck + vitest (56) + build.

## v0.3.106 — Model authoring, P3: architectural finishes (ceilings · tile · wood · cladding · railings)
Interior/finish elements complete the discipline set the Draft palette can author.

- **Coverings** (`IfcCovering`) drawn as a polygon: **ceiling** (hung near the top of the storey),
  **floor tile** (FLOORING + a ceramic-tile material), **wood flooring** (FLOORING + a Wood material),
  and **wall cladding** (CLADDING) — each by PredefinedType with an optional finish **material** and
  `Pset_CoveringCommon`.
- **Railings** (`IfcRailing`) drawn between two points at a set height.
- New `edit.py` recipes `add_covering` / `add_railing`; Architectural Draft entries for the four
  coverings + railing. Placement uses the P1 grid snap + active level.

With this the Draft palette spans all three disciplines (Architectural · Structural · MEP) — from grid
and levels to steel, rebar, MEP runs and equipment, and now finishes.

Verified: `test_architectural` (ceiling at 2.7 m, wood flooring material, cladding, railing) + typecheck
+ vitest (56) + build; ruff clean.

## v0.3.105 — Model authoring, P5: MEP families (HVAC · plumbing · electrical · fire · telecom)
The biggest discipline slice — draw distribution runs and drop equipment, authored as real IFC MEP.

- **Distribution runs** you draw as a segment: **duct** (`IfcDuctSegment`), **pipe** (`IfcPipeSegment`),
  **cable tray / conduit** (`IfcCableCarrierSegment`), and **cable / wire** (`IfcCableSegment`). Each is
  a swept section (round, or rectangular for tray) with two **connection ports** and assignment to a
  named **`IfcDistributionSystem`** (HVAC Supply / Domestic Water / Power).
- **Point equipment** you click to place: **electrical panel** (`IfcElectricDistributionBoard`),
  **outlet** (`IfcOutlet`), **light** (`IfcLightFixture`), **air diffuser** (`IfcAirTerminal`), **floor
  drain** (`IfcWasteTerminal`), **plumbing fixture** (`IfcSanitaryTerminal`), **fire alarm**
  (`IfcAlarm`), **smoke detector** (`IfcSensor`), and **data/telecom outlet**
  (`IfcCommunicationsAppliance`) — each with the correct IFC class + PredefinedType.
- New `edit.py` recipes `add_duct` / `add_pipe` / `add_cable_tray` / `add_wire` / `add_mep_terminal`;
  MEP entries fill out the Draft palette's MEP discipline. Placement uses the P1 grid snap + level.

Verified: `test_mep_families` (four run types + named systems + round/rect sections; seven point-
equipment classes with PredefinedType preserved) + typecheck + vitest (56) + build; ruff clean.

## v0.3.104 — Model authoring, P4: structural steel + rebar + footings
Real structural members in the Draft palette — authored as native, standards-compliant IFC.

- **Steel W-shapes** — `steel.py` holds the AISC W-shape table (W8×31 … W24×76, dimensions re-keyed as
  facts, [attributed](docs/ATTRIBUTIONS.md)); `add_steel_column` / `add_steel_beam` author an `IfcColumn`
  / `IfcBeam` with a **native parametric `IfcIShapeProfileDef`** (no imported geometry), with the section
  name stamped on `Pset_*Common.Reference`. A **Section** picker in the Draft form.
- **Rebar** — `add_rebar` authors a straight **`IfcReinforcingBar`** (circular section swept along the
  bar) sized by US bar designation (#3–#11) with `NominalDiameter` + `BarLength`.
- **Pad footings** — `add_footing` authors an `IfcFooting` pad below the level.
- Draft catalog gains a **`select`** parameter type (for the section / bar-size pickers); placement uses
  the P1 grid snap + active level.

Verified: `test_structural` (W-shape table inches→m; steel column → native IfcIShapeProfileDef W14×30 +
section on Pset; steel beam; #5 rebar nominal diameter + circular section; footing) + typecheck +
vitest (56) + build; ruff clean.

## v0.3.103 — Model authoring, P1: grid + levels as drafting references
The drafting reference frame — so placement lands on a grid and the right level, not free space.

- **Grid & Levels panel** in the Model tools rail. **Load grid + levels** reads the project's grid
  (`services/data/.../grid.py`): real **`IfcGrid`** axes (U/V + bubble tags) when present, else a grid
  **derived from `IfcColumn` centres** (numbered 1,2,3… / lettered A,B,C…). Axes render in 3D with
  bubbles; Draft placement now **snaps to grid intersections**.
- **Editable levels.** An active-level selector sets the **work-plane** (Draft points project onto the
  level's elevation) and passes the storey to every authoring recipe, so elements land on the chosen
  level. New `edit.py` recipes **add / rename / move** a storey (`add_storey`, `rename_storey`,
  `set_storey_elevation`) — authoring real `IfcBuildingStorey` levels.
- New endpoint `GET /projects/{id}/model/grid` (grid axes + snap intersections + storey levels).

Verified: `test_grid` (derived grid from 4 columns → axes 1/2/A/B + 4 intersections snapping to column
centres; add/rename/move-storey recipes) + web typecheck + vitest (56) + build; ruff clean.

## v0.3.102 — Model authoring, P0: the Draft panel (parametric family/element placement)
First slice of the "true model-creation program" upgrade — foundations for a full BIM family library
authored in the browser (intent) and written as real IFC on the server (source of truth), then
re-streamed as fragments.

- **Draft panel** in the Model workspace tools rail (`viewer/draft/`) — a discipline-grouped palette
  (Architectural · Structural · MEP · Site) of parametric elements and the server family catalog, each
  with a **named parameter form** (height, thickness, width, …). Pick an element, set parameters, arm
  **Place**, then click in the model: the server authors the IFC (walls, slabs, columns, beams, roofs,
  and any catalogued family) and streams it back. **Replaces the old `prompt()`-per-dimension flow** —
  no more native prompts for wall height/thickness. Supports point, two-point, and **polygon** (double-
  click to close) placement, with grid/vertex snap, ortho lock (Shift), and Esc to cancel.
- This is additive: the existing authoring recipes (`edit.py`) and the `/families/catalog` + `/edit`
  round-trip are unchanged; the Draft panel is a cleaner front-end over them. Structural depth (steel
  profiles + rebar), then MEP, then architectural coverings/finishes follow in subsequent releases,
  alongside real grid/level drafting refs.

Verified: `draftCatalog.test.ts` (recipe-param mapping for every element + family) + web typecheck +
vitest (56) + build green.

## v0.3.101 — Market intelligence & cost escalation + AI concept-render bridge
Two additions from an industry-research pass:

- **Market Intelligence & cost escalation** (`market_intelligence.py` + `market_assumption` module +
  `/market/*` endpoints + 💹 **Market Intelligence** panel in the developer workspace). A regional table
  (annual escalation %, average labour US$/hr, location index) plus a **two-speed warm/cold** demand
  signal by sector (tech-led sectors — data centres, advanced manufacturing — running hot; residential /
  commercial cold). The engine **escalates a base cost to the midpoint of construction** in the project's
  region — not just "next year" — reading a project's adopted `market_assumption` (region · sector ·
  construction start · duration) or query-param overrides. The **conceptual estimate now carries a market
  block** (regional labour + sector temperature + escalation-to-midpoint), and there's a **Market
  Intelligence & Escalation report**. Seed defaults are the **public headline figures** from Turner &
  Townsend's *Global Construction Market Intelligence 2026* — illustrative, **editable** defaults
  (attributed, not their dataset); a deployment overrides them with its own current rates.
- **AI concept-render bridge** (`render_bridge.py` + `concept_render` module + `/concept-render/*`
  endpoints + 🖼 **Concept Renders** panel in the design workspace). Like the CV-progress and RVT / payment
  bridges, it's **feature-flagged and off by default** (`AEC_RENDER_BRIDGE`): the platform builds a
  **grounded prompt** from the project's space program + massing and hands it to a connected image service,
  then ingests returned image references as reviewable `concept_render` records. When the flag is off, the
  endpoints report the bridge unavailable and **fabricate nothing** — no placeholder images. Reference
  adapter in `docs/render-bridge.md`.

Verified: new `test_market` (escalation-to-midpoint math, warm/cold signal, `market_assumption`-driven
context + escalate, conceptual-estimate market block, report PDF; bridge off fabricates nothing / on
builds a clamped grounded prompt + requires `image_url`) + full suite green, ruff clean; web typecheck +
build green.

## v0.3.100 — Close the two deferred perf items: compressed color-by + cross-worker scan cache
The two follow-ups the audit deferred are now done:

- **Compressed `color-by` + compact `ids=false` mode** — the viewer's colour-by needs the full
  GUID→bucket mapping (inherently O(elements)), so instead of capping it (which would break colouring) the
  large payload is now **gzipped on the wire** (`Content-Encoding: gzip`, transparently decompressed by
  the browser). A new **`?ids=false`** returns just labels + counts — a compact distribution for a legend
  or picker with no per-element payload.
- **Cross-worker scan cache** — the per-model-version cache for the hot `facets-list` / `color-by` scans
  is now **shared via Redis** (gzip+JSON values, TTL `AEC_SCAN_CACHE_TTL`, default 1 h) when
  `AEC_REDIS_URL` is set, so one worker's scan is reused by every other; **fail-open** to the in-process
  cache on any Redis error, matching `model_events` / the rate-limiter. Single-worker / no-Redis is
  unchanged.

Verified: new `test_scan_cache` (gzip round-trip, Redis fail-open, `ids=false`) + full suite green, ruff
clean. This closes every item from the four-dimension code audit.

## v0.3.99 — Audit follow-through (Batch 3): cache the hot model scans + windowed portfolio query
The deep-performance items from the audit — attacking the "recomputed on every request" cost of the
property-index scans:

- **Per-model-version scan cache** — the two hottest read scans (`elements/facets-list`, the O(n·psets)
  distinct-value scan, and `elements/color-by`) are now memoised keyed on the **model version**
  (`model_events`, bumped on publish). Repeated analytics requests for an unchanged model are served from
  cache instead of re-scanning every element × every property; the cache invalidates automatically when a
  new model is published, and evicts LRU-style (bounded).
- **Windowed portfolio scenario query** — `executive_portfolio` fetched **every** scenario's full result
  JSON across all projects just to keep the latest per project; it now uses a windowed
  `GROUP BY project → MAX(created_at)` join to load only the latest scenario per project.

(`color-by` still returns the full GUID→bucket mapping — the 3D viewer needs it to colour — so its payload
size is inherent; a compact run-length encoding is a tracked follow-up rather than a break-the-viewer cap.)

Verified: affected suites (analytics / portfolio / dashboard / api) green, ruff clean. Frontend bundle was
already healthy (code-split + Brotli budget) — no change. This completes the four-dimension audit
follow-through (Batch 1 perf/UX/analytics · Batch 2 demo data · Batch 3 deep perf).

## v0.3.98 — Audit follow-through (Batch 1): perf quick-wins, Documents a11y, surfaced analytics
A four-dimension code audit (wiring, UI/UX, sample data, performance) found the platform structurally
sound — **zero broken wiring** (46/46 routers, 47/47 reports, 32/32 module refs), all panels reachable.
This ships the low-risk quick wins from it:

- **Performance:** dashboard/AI-ask/closeout counts now use a SQL `COUNT` (`count_records`) instead of
  materialising whole JSON tables just to call `len()`; `properties/index` upload parses off the event
  loop (`run_in_threadpool`) and stores the received bytes verbatim (no redundant re-serialize); the
  document-manager `tree()` computes its active-file set once instead of per folder node.
- **Documents file manager (a11y + UX):** the folder tree is now keyboard-operable (`role`/`tabindex`/
  Enter-Space) instead of mouse-only; delete uses the app's accessible modal instead of the native
  `confirm()`; the two-pane layout wraps to stacked on narrow viewports; a **role filter** (PM /
  Superintendent / Architect / Engineer / QS) and a **phase-gap check** (AIA SD/DD/CD/CA/CLOSEOUT) are
  now surfaced (they reuse the by-role and phase-gaps endpoints that were built but unwired).
- **Surfaced built-but-invisible analytics:** the 🔬 Model Analysis panel now shows the **fast STEP model
  summary** (entity-type histogram, no full parse — G3), the **columnar interning efficiency** stat + an
  **EAV `params.parquet`** download (G1), and a **VIM / G3D inspect** control (G2); export links are gated
  on a loaded model (no raw 409s), and Documents + Model Analysis are now reachable from the **developer**
  workspace too.
- **A11y polish:** `th scope="col"` + `aria-label`s on the Model Analysis tables/selects.

Verified: full backend suite green, web typecheck + vitest 49/49, ruff clean.

## v0.3.97 — Ara3D-inspired efficiency track: columnar BIM data, BFAST/VIM reader, fast STEP scan
Three efficiency/interop wins drawn from a review of the [Ara3D SDK](https://github.com/ara3d/ara3d-sdk)
(MIT; see [ATTRIBUTIONS](docs/ATTRIBUTIONS.md)) — ported/adapted where it added value, skipped where our
numpy/trimesh/ifcopenshell stack already wins.

- **Columnar / interned BIM data layer** (`bim_columns.py`, inspired by Ara3D `BimOpenSchema`) — a
  **string/number-interned columnar** view of the property index + an **EAV parameter table** exported as
  **Parquet** for DuckDB/pandas/Polars analytics. Psets repeat the same keys/values across thousands of
  elements, so interning cuts RAM sharply (a small 4-wall fixture already shows ~3.4× string dedup). New
  endpoints: `/model/columnar/stats` (dedup ratio + estimated bytes saved), `/model/columnar/aggregate`
  (group-by via pyarrow compute — no Python row loop), `/model/export/params.parquet`.
- **BFAST / G3D / VIM reader** (`aec_data/bfast.py`) — a pure-Python reader/writer for the BFAST container
  + summarisers for G3D geometry (vertex/index counts + bbox) and VIM files (schema/version, buffer
  inventory, geometry stats). Opens `.vim` / `.g3d` offline via `POST /convert/vim/inspect`. Independent
  re-implementation of the public format; no Ara3D code copied.
- **Fast STEP metadata scanner** (`aec_data/step_scan.py`) — a streaming line-scan of an IFC-SPF file for
  its header + **entity-type histogram** without a full `ifcopenshell` parse (milliseconds, bounded
  memory). `GET /model/step-summary` for an instant "what's in this IFC" on large files.

Also reviewed the OpenAEC-BIM-validator repo — no integration needed: we already validate IFC against IDS
via `ifctester` (per-spec pass/fail + failing GUIDs + BCF) in `aec_data/validate.py`. Verified: new
`test_bim_columns` / `test_bfast` / `test_step_scan` + full backend suite green, web build green, ruff clean.

## v0.3.96 — Document Control: a role-based standard file manager over the project
A first-class **📁 Documents** workspace — an elFinder-style two-pane file manager (folder tree + file
list) built on a **standard, role-based project folder taxonomy** so every project is organised the same
way and required documents are never missing.

- **Standard taxonomy** (`folder_template.py`) — the industry `01_Contract Documents … 11_Final Account`
  tree with sub-folders, each node tagged with an **owner role** (PM owns the business — contracts,
  payments, variations, procurement; the **Superintendent** owns field execution — site instructions,
  inspections, NCRs, daily reports, photos; the **Architect/Engineer** own the drawing set), a discipline
  (NCS), a default **CDE state** (ISO 19650 WIP/Shared/Published) and a **required** flag.
- **Document manager** (`docmanager.py`) — bytes in object storage (`{pid}/docs/<folder>/<name>`) with a
  per-project sidecar index. Uploads **auto-name to the information standard**
  (`Type_Discipline_Description_Revision_Date`) and **never overwrite**: a new upload of the same document
  supersedes the prior revision (P01→P02…), the old one archived for audit. Move, soft/hard delete,
  download, per-folder counts that roll up to parents, and required-doc **gap** flags.
- **Role-based views** — a `by-role` endpoint and owner-role chips per folder, so a PM / Superintendent /
  architect sees the folders they own.
- **Document-Control health** — a Report Center report (naming compliance, required-folder coverage,
  revision control, CDE-state spread, orphans) + AIA **phase-gap** checks (SD/DD/CD/CA/CLOSEOUT flag the
  documents a phase is missing, e.g. a CD set lacking structural drawings).
- **Web**: the 📁 Documents destination in the Construction and Design workspaces — clickable folder
  tree, upload (auto-named, supersede-aware), download, move, delete, and a health strip.

Reuses the discipline spine (NCS), the ISO 19650 CDE states, the naming validator, and the storage
backend already in place. Verified: new `test_docmanager` + full backend suite green, web typecheck +
vitest 49/49, ruff clean.

## v0.3.95 — Close the five deferred slices: Parquet + glTF export, CV bridge end-to-end, live 2D propagation, IFC5 data reads
The items previously scoped as "needs a dependency / external service / upstream support" are now shipped
as far as each honestly can be:

- **Parquet export** — added `pyarrow`; `GET /model/export.parquet` writes a Snappy-compressed columnar
  file (DuckDB / pandas / Polars), alongside the existing CSV + JSON-LD. Returns a clean 503 (never a
  500) if the optional dep is absent.
- **glTF geometry export** — `GET /model/export.gltf` triangulates the model with the same
  `ifcopenshell.geom` iterator the section/clash tools use and writes a **self-contained glTF 2.0**
  (binary buffer embedded as a data-URI), meshes merged per IFC class with per-class colours, Z-up→Y-up.
  The viewer still streams Fragments — this is the portable geometry-*out* path (Blender / Three.js /
  any DCC). Honest scope: triangulated meshes + flat colours, no PBR/textures.
- **CV site-progress bridge, end-to-end** — the feature-flagged bridge now resolves an activity by **id
  or name**, accepts a **batch** (`/cv-progress/ingest-batch` — the per-photo-sweep shape), and writes
  straight to `schedule_activity.percent`. A runnable **reference adapter** ([docs/cv-bridge.md](docs/cv-bridge.md))
  documents the HTTP contract so any vision service wires in. Still no bundled model — that stays external
  by design — but the entire integration surface is complete and tested.
- **Live 2D propagation** — a per-project **model version** bumps whenever a new model is published;
  `GET /drawings/sync-status` surfaces it and `GET /drawings/stream` (SSE) **pushes** the change, so open
  on-demand 2D views regenerate themselves. Single-worker uses an in-process registry; **multi-worker
  shares it via Redis** (atomic `HINCRBY`, keyed off `AEC_REDIS_URL`) so a publish on any worker reaches
  a stream on any other — fail-open to in-process if Redis blips, matching the rate-limiter/lockout.
- **IFC5 / IFCX / ifcJSON data reads** — a tolerant JSON reader parses these into the same element-index
  shape a STEP model produces, so analytics, LOD/naming/envelope audits and CSV/JSON-LD/Parquet export all
  work on an IFC5 file **now**. Capabilities report it as `ifc5: data` (geometry rendering still lands
  upstream when web-ifc / Fragments add it).

Web: the 🔬 Model Analysis panel gains an **Export** row (CSV / JSON-LD / Parquet / glTF) and reflects the
IFC5 data-read distinction. Verified: 6 new/extended backend suites green, web typecheck + vitest 49/49,
ruff clean.

## v0.3.94 — Model Analysis panel: the new model-reading tools, first-class in the UI
A consolidated **🔬 Model Analysis** destination in the Design workspace surfaces the model-reading
endpoints that previously had no bespoke UI (the register-backed features already had module CRUD +
Report Center reports): **IFC capabilities** (supported schemas + the loaded model's detected schema,
IFC5/IFCX reported), a **model query** (saved views — count by discipline / class / storey / type),
**LOD coverage**, **envelope code compliance**, **MEP counts off the model**, and **naming compliance**.
Each section loads independently and degrades gracefully when no model is published. New client methods
wrap the endpoints; the panel follows the extracted-panel (`PanelContext`) pattern. Verified: web
typecheck clean, vitest 49/49, build green, **and live** — booted the full dev stack (API on :8093 +
Vite), navigated to Design → Model Analysis; all six sections render with zero console errors, and IFC
capabilities correctly detected the loaded model as IFC4.

## v0.3.93 — Deferred-item slices: model-driven MEP, staleness, schema detect, CV write-path
The tractable slice of each remaining backlog item (the fuller versions need infrastructure noted below).
- **Model-driven MEP extraction (C1x)** — `mep.extract_from_model` reads MEP elements off the loaded
  model by IFC class (ducts / pipes / terminals / equipment / electrical), counted by class + discipline.
  `GET /mep/model-extract`, and the MEP Equipment Schedule report now shows model counts beside the register.
- **Model-staleness signature (B2x)** — `GET /drawings/sync-status` returns a cheap fingerprint of the
  loaded model (element count + GlobalId hash); the client compares it across renders to know when the
  on-demand 2D is stale. The tractable slice of live-2D propagation, without an event bus.
- **IFC schema detection + capabilities (D4x)** — `GET /model/capabilities` sniffs the source model's
  header, reports the detected schema (IFC2X3 / IFC4 / IFC4X3), and **detects IFC5/IFCX (JSON) and says
  plainly it's not yet parsed** rather than failing cryptically. The read path still lands upstream.
- **CV bridge write-path (E2x)** — with `AEC_CV_BRIDGE` on, `POST /cv-progress/ingest` now **writes the
  estimate to the named schedule activity's percent** (a bad id is handled, not a 500). A real CV service
  now has a working endpoint to drive progress; the vision model remains external.

Still genuinely deferred (need infra, not effort): **Parquet export** (needs the `pyarrow` dependency —
a decision, not built by default), **glTF geometry export** (needs the geometry pipeline), a **real CV
model** (external service), and **full auto-propagate-on-edit** (needs an event bus). Backend 129/129,
ruff clean.

## v0.3.92 — Field AI: labor productivity + CV progress bridge (Phase E)
The final phase of the upgrade initiative.
- **Field labor productivity (E1)** — a new `productivity_log` register (quantity installed · workers ·
  hours) + `productivity.py`: **units per man-hour** per entry, rolled up by trade, with an overall rate.
  `GET /productivity/summary` + a **Field Labor Productivity** report. The field-productivity signal
  Rhumbix-style tools surface, on the same project record.
- **Computer-vision site-progress bridge (E2)** — real CV % complete needs an external vision model, so
  this is a **feature-flagged bridge** (like the RVT and money-processor bridges): with `AEC_CV_BRIDGE`
  off (default) the endpoints report the bridge as unavailable and **fabricate nothing**; an operator
  enables the flag and connects a CV service that POSTs estimates to `/cv-progress/ingest` (clamped
  0–100). `GET /cv-progress/status` documents the contract.
Backend 128/128, ruff clean. **The A–E upgrade initiative (authoring depth · design engine · engineering
depth · interoperability/analytics · field AI) is complete** — 16 items across v0.3.87–v0.3.92.

## v0.3.91 — Interoperability & analytics: model query + data export + envelope compliance (Phase D)
The ifc-lite-inspired items, on our server-Fragments architecture.
- **Model analytics query (D1)** — `model_query.py` + `GET /model/query`: group elements by any
  attribute (ifc_class / discipline / storey / type / `Pset::Property`) and **count** them or **sum a
  quantity** from the IFC quantity sets, with filters and four saved views. The "ask the model a
  question" analytics without shipping the model to the browser.
- **Model data export (D2)** — `GET /model/export.csv` (columnar, one row per element) and
  `GET /model/export.jsonld` (a JSON-LD graph, bSDD-style vocab, GlobalId as `@id`). No external
  dependency. (Parquet + glTF geometry export remain future items.)
- **Envelope code-compliance (D3)** — new `envelope_assembly` register + `envelope.py`: opaque
  assemblies checked against IECC 2021 minimum R-values and fenestration against maximum U-factors by
  climate zone. `GET /envelope/{audit,check}` + an **Envelope Code Compliance** report. A first-pass
  screen, not a stamped energy model.
- **IFC5 / IFCX (D4)** — tracked as a watch-item; the read path lands when web-ifc / Fragments ship
  IFC5 support.
Backend 127/127, ruff clean. Phases A–D of the authoring/design/engineering/interop initiative complete.

## v0.3.90 — Engineering depth: MEP sizing/schedules + resource-loaded scheduling (Phase C)
- **MEP engineering (C1)** — a new `mep_equipment` register (equipment schedule) + `mep.py` with
  deterministic first-pass calculators: **duct sizing** (equal-velocity), **pipe sizing** (velocity
  method → nominal pipe size), **cooling load → tonnage** + a block-load rule-of-thumb, and
  **hanger/support spacing** (SMACNA for duct, MSS SP-58 for pipe). `GET /mep/schedule` rolls the
  equipment up per system; `GET /mep/size` is a stateless sizing calc. An **MEP Equipment Schedule**
  report with sizing reference tables. Extends the D5 parametric MEP (which lays the geometry) with the
  numbers behind it.
- **Resource-loaded scheduling (C2)** — schedule activities gain a **crew_size**; `resource_loading.py`
  buckets every week an activity spans and sums concurrent crew into a **resource histogram** (by trade
  + total), a cumulative **man-week S-curve**, **peak manpower**, and **over-allocation** flags against
  an optional `?cap=` availability. `GET /schedule/resource-loading` + a **Resource-Loaded Schedule**
  report (histogram + S-curve charts). Rides on the existing CPM schedule.
Backend 125/125, ruff clean.

## v0.3.89 — The design engine: options / variants + standards ruleset (Phase B)
Design-side depth so a project can carry, compare and standardize schemes.
- **Design options / variants (B1)** — a new `design_option` register (program + economics per scheme)
  and `GET /design/options/compare`: options compared apples-to-apples with **best-in-class per metric**
  (lowest cost/sf, lowest EUI, highest IRR, largest area, highest efficiency), deltas vs the **selected**
  option, and a state rollup (proposed → shortlisted → selected → rejected). A **Design Options
  Comparison** report (PDF + Excel).
- **Selected-option → drawing linkage (B2)** — each option references a `drawing_set`; the selected
  option's set is the project's current documentation. The 2D drawings (plan / section / elevation /
  sheet) already **generate on demand from the live model**, so they reflect the current state whenever
  requested. (Full auto-propagate-on-every-edit — Higharc-style instant regeneration — remains a future
  item; it needs event wiring on top of the parametric model.)
- **Design standards ruleset (B3)** — a new `design_standard` register (approved / preferred /
  prohibited assemblies, materials, products) with `GET /design/standards` + `GET /design/standards/check`:
  the loaded model is audited against the ruleset — elements are flagged when their type/material matches
  a **prohibited** standard, or (when an approved set is declared) match nothing approved. Keyword-based on
  the openBIM property data the model already carries. A **Design Standards Compliance** report.
Both registers get CRUD via the module engine; both reports surface under a new **Design** group. Backend
123/123, ruff clean.

## v0.3.88 — Authoring depth: LOD matrix + naming-convention validator (A2 + A3)
Completes the authoring-depth phase.
- **LOD matrix & coverage (A2)** — a new `lod_target` register (stage × discipline × element-category →
  LOD 100–500; RIBA/AIA stage defaults when empty) plus an **achieved-LOD assessment** of the loaded
  model. Achieved LOD is *inferred* from the same LOIN facet completeness the quality scorecard scores
  (geometry/type/classification/properties/quantities) and capped at LOD 400 — LOD 500 is a verified
  as-built assertion, not a model read. Endpoints `GET /lod/matrix` + `GET /lod/assessment`, and a
  **LOD Matrix & Coverage** report (target matrix + achieved distribution + per-discipline average).
- **Naming-convention validator (A3)** — validates document/container filenames against
  `Type_Discipline_Description_Revision_Date` (revision-controlled) and drawing sheet numbers against
  the **NCS Sheet ID** grammar (reusing the D3 parser). `GET /naming/{conventions,validate,audit}` and
  a **Naming Convention Compliance** report that audits the CDE containers + drawing register with
  compliance % and a violation list.
Both surface automatically in the Report Center (Quality group, PDF + Excel); the LOD targets get CRUD
via the module engine. Backend 122/122, ruff clean.

## v0.3.87 — BEP generator: the ISO 19650 BIM Execution Plan as a produced document (A1)
The first of an authoring-depth initiative (informed by an industry-practice scan). We already held the
information-requirements register (EIR/BEP/AIR), the CDE, the discipline vocabulary and the delivery
register — now they **assemble into a produced BIM Execution Plan**. A new Report Center entry (**Quality**
group, PDF + Excel) composes the ISO 19650 BEP: an information-requirements register, a **roles,
responsibilities & authorities** matrix (appointing party / lead appointed party / information manager +
an authoring lead per discipline), the **Level of Information Need** targets by delivery stage (LOD
200→500), the **information-delivery schedule** (from the drawing/delivery sets), **information standards
& naming** (NCS sheet IDs + `Type_Discipline_Description_Revision_Date` + MasterFormat/Uniformat
classification), the **CDE workflow** (WIP→Shared→Published→Archived with revision/approval coverage), and
the **model-coordination & QA** process — with core EIR/BEP/AIR coverage flagged. No new data entry: it
reads the registers you already keep. Next in the phase: a per-element **LOD matrix** (A2) and a
**naming-convention validator** (A3).

## v0.3.86 — Code standards S3: lint lock-in (consistency enforced in CI)
The final phase of the standards initiative — the PEP 8-aligned rules the S1 pass satisfied are now
**enforced in CI**, so they stay satisfied. Ruff's rule set expands from correctness-only
(`F`, `E9`, `B`) to add:
- **`I`** — import ordering (isort), with `aec_api`/`aec_data` pinned as first-party.
- **`UP`** — pyupgrade: modern syntax for the Python 3.10+ target.
- **`C4`** — flake8-comprehensions: no needless comprehensions or collection calls.

Nine residual violations (unnecessary comprehensions, `%`-format strings, a redundant `dict()` call)
were cleaned up by hand — all behaviour-preserving. Deliberately **not** enforced, with the rationale
recorded inline in `ruff.toml`: line-length (`E501`) and one-statement-per-line (`E702`), because the
codebase intentionally uses compact one-liners and dense table/PDF/SVG builders; and `RUF100`, because
it would strip the intentional `# noqa: BLE001` annotations that document the logged fail-open idiom.
**120/120 backend suites pass**; no runtime change.

## v0.3.85 — Code standards S1: safe PEP 8-aligned auto-fixes
A mechanical, behaviour-preserving compliance pass across the Python backend (`services/api` +
`services/data`) — the first of a phased standards initiative. Ruff's **safe** auto-fixes only:
- **Import ordering** (isort / PEP 8) — imports sorted into stdlib / third-party / first-party groups.
- **pyupgrade** — deprecated import paths, quoted annotations, and old-style `%` formatting modernized.
- **Comprehension simplifications** — unnecessary `dict()`/`list()` comprehensions and calls collapsed.
- **`contextlib.suppress`** in place of `try/except/pass`.
~200 fixes across 52 files. No behaviour change (**120/120 backend suites pass**, imports clean). The
codebase's deliberate compact idiom (compact one-liners, unused FastAPI-DI args, typographic unicode) is
intentionally preserved. Line-length wrapping (S2) and CI lock-in (S3) follow.

## v0.3.84 — Discipline Spine D5b: parametric MEP generation (spine complete)
The generator now produces real **parametric MEP distribution**, so a generated building reads as a
layered structural / architectural / **MEP** model — completing the five-phase Discipline Spine.
- Beyond the two core risers, each floor gets a **supply-air duct main** and a **domestic-water main**
  at ceiling height plus **ceiling diffusers on a ~bay grid** (`IfcFlowTerminal`, air-terminal). Fully
  parametric — the mains span the plate and the diffuser count scales with the floor size and bay.
- The new elements classify to the right disciplines automatically (D2): ducts + diffusers →
  **Mechanical**, pipes → **Plumbing** — so colour-by-discipline and the `?discipline=` filter show the
  MEP layer, and the takeoff/spine pick it up. Verified: a 7-floor model generates 14 duct segments,
  14 pipe segments and 112 diffusers, correctly disciplined.

**Discipline Spine complete (D1→D5):** shared NCS/MasterFormat vocabularies → discipline-tagged elements
→ discipline sheets + sets → connected spec/bid/cost-code traceability → discipline-aware generation
with parametric MEP. The model, the documents and the money are one traceable thread. (A true multi-file
federation split of the generated model — separate STR/ARCH/MEP IFCs sharing one grid — and a first-class
`IfcGrid` remain as optional model-realism follow-ups; the layered reading already works via the
discipline tagging.)

## v0.3.83 — Discipline Spine D5a: generation seeds a connected spine
Generating a project now produces a **fully-connected discipline spine** out of the box, not just a
model + budget. The GC-portal seeder that already creates cost codes now also seeds a **bid package per
discipline** (Structural / Architectural / Mechanical / Electrical), each linked to its cost code, and a
**spec section per division** linked to that package — so a freshly generated project is **100%
traceable model → specs → bid packages → cost codes → budget** the moment it exists.
- Discipline budgets are computed from the same hard-cost division fractions (Structural, Architectural,
  Mechanical, Electrical), so the seeded packages reconcile with the GMP.
- `test_disciplines` extended: a generated project shows 100% specs-packaged / packages-costed /
  spec-to-budget and every spec fully linked. Reuses the D1 classification vocabulary + the D4 links.
- First half of D5 (discipline-aware generation); D5b adds a real `IfcGrid` + parametric MEP depth.

## v0.3.82 — Discipline Spine D4: connect the procurement chain (traceability)
The payoff phase — the model, the documents and the money are now one connected thread, with the broken
links surfaced so scope can't fall between them.
- **Links wired**: `spec_section` gains **`bid_package`** (which package procures this spec) + a
  discipline field; `bid_package` gains a **`cost_code`** reference + discipline. Spec→bid is N:1, the
  correct direction — a package's specs are all the specs pointing to it.
- **`spine.py` traceability engine** + `GET /projects/{id}/spine/traceability` — traces
  **discipline → sheets → specs → bid packages → cost codes → budget**, with per-discipline rollups
  (sheets/specs/packages/cost-codes/budget) and **coverage bars** for each join (sheets→spec,
  specs→package, packages→cost-code, spec→budget). Discipline is resolved consistently — from the field,
  else derived from the MasterFormat division or the NCS sheet number.
- **Coverage gaps** list the broken links: unpackaged specs, unbudgeted packages, un-specced sheets.
- New **🔗 Discipline Spine** panel (Design workspace): coverage bars, budget-by-discipline chart,
  the gap lists, and the spec→package→cost-code trace. `test_disciplines` extended. Fourth of five phases.

## v0.3.81 — Discipline Spine D3: discipline-tagged drawing sheets + sets
Drawing sheets now read as a proper **discipline-ordered set**, and each sheet links to the specification
and drawing set it belongs to — the documentation layer of the spine.
- **NCS Sheet ID parsing** (`drawingset.parse_sheet_id`) — `A-101` → discipline **A** (Architectural),
  sheet type **1** (Plans), sequence **01**. The drawing-set register now carries the parsed sheet ID on
  every sheet, derives the discipline from the sheet number when the field is blank, and **orders the
  sheet index the way a set is bound** — by NCS discipline (General → Civil → Structural → Architectural
  → MEP), then sheet number.
- **`drawing_set` module** — named issued sets (Schematic Design / Permit / Bid / Issued for Construction
  / Record) with discipline, issue date and purpose.
- `drawing` gains **`drawing_set`** and **governing `spec_section`** references (the sheet→spec link that
  feeds D4) plus issued-date / revision-purpose fields.
- `test_disciplines` extended. Third of five phases (D1→D5).

## v0.3.80 — Discipline Spine D2: discipline-tagged model elements
Every model element now carries its **NCS discipline**, derived from its IFC class through the D1
MasterFormat map — so the model reads as layered structural / architectural / MEP even from a single
federated file, with no republish and no extra scan (pure function of the already-indexed IFC class).
- `GET /projects/{id}/elements?discipline=S` (accepts an NCS code **or** name) filters the property
  index; every element is returned with its derived `discipline`.
- `GET /projects/{id}/elements/by-discipline` — model composition: element count + IFC-class breakdown
  per discipline, in NCS sheet order (Structural → Architectural → MEP).
- **Discipline** is now a first-class **colour-by facet** — it appears automatically in the viewer's
  "Colour by…" picker and buckets the model by discipline in 3D (no client change needed).
- `test_disciplines` extended. Second of five phases (D1→D5) of the model→sheets→specs→bid→budget spine.

## v0.3.79 — Discipline Spine D1: shared classification vocabularies
The foundation for representing a project as layered **structural / MEP / architectural** models whose
sheets, specs, bid packages and budget all thread through two shared, validated vocabularies (rather
than free text). Based on the US National CAD Standard discipline designators + CSI MasterFormat.
- **Discipline vocabulary** (`classification.py`) — the NCS discipline designators (**A** architectural ·
  **S** structural · **M** mechanical · **E** electrical · **P** plumbing · **F** fire · **C** civil ·
  **T** telecom · **G/L/Q**), each with its default MasterFormat divisions + Uniformat groups.
  Derives an element's discipline from its IFC class (via the existing MasterFormat map), and normalizes
  legacy free-text values (e.g. "MEP" → M, "Geotechnical" → C).
- **MasterFormat division master** (25 divisions) + the **Uniformat II ↔ MasterFormat crosswalk** that
  migrates a concept-phase budget into the procurement budget.
- `GET /reference/disciplines` serves all three catalogs (drives the selects + the spine joins).
- Converted the free-text `discipline` (drawings) and CSI `division` (cost codes, spec sections) fields
  to validated **selects**. `test_disciplines`. Deterministic, no new deps. First of five phases
  (D1→D5) building the model→sheets→specs→bid→budget spine.

## v0.3.78 — Performance: trim the physical-climate-risk fan-out
Tightens the scans behind the physical-climate-risk rollup that feeds the ESG scorecard.
- The rollup previously ran the full weather engine — including a scan of `schedule_activity` (one of
  the larger tables) — even though it only needs the site-weather register and the logged delay days.
  Split out a `_weather_exposure` helper so `climate_risk` (and therefore every **ESG summary** load)
  no longer scans `schedule_activity` at all.
- Made `climate_risk` composable: the resilience **report** now passes in the flood / stormwater /
  exposure it already computed instead of recomputing those scans a second time.
- No behaviour change (rollup output is byte-identical); verified. Backs the config-module engine that
  already ships every tool's CRUD, CSV export, kanban board and workflow-flowchart for free.

## v0.3.77 — Real-time collaborative pull board (M3)
The Last Planner pull board becomes a live, multi-trade workspace — every stakeholder edits the same
board and sees each other's changes as they happen, without a page refresh.
- **Live board** — a lightweight Server-Sent-Events stream (`GET /projects/{id}/pull-plan/stream`)
  polls a cheap board change-signature (row count + latest `modified_at`) server-side and pushes it
  when it moves, so the board auto-refreshes the moment any trade adds or moves a sticky note. A
  **🟢 live** indicator sits in the board header.
- **Presence** — reuses the existing presence infra: a heartbeat marks who else is on the board and
  renders **👤 peer chips** in the header (self-cleans when you leave the view).
- **Edit locks / no silent overwrite** — records now expose `modified_at`, and the record editor sends
  it back as an optimistic lock: if someone changed the record while you had it open, the save returns
  **409** (rather than clobbering their edit) and the editor reloads the latest with a *"re-apply your
  edit"* nudge. Opt-in and backward-compatible — an un-locked write still succeeds.
- Reuses the SSE + presence primitives already in the codebase — **no new dependencies**, no CRDT.
  `test_pull_realtime`; the lock is generic (available to every module, not just the pull board).

## v0.3.76 — Climate resilience: weather-sequenced construction + physical-risk rollup (W3–W4)
Extends the **🌊 Climate Resilience** panel from the design phase into construction and up into ESG.
- **Weather-sequenced construction (W3)** — a `weather_sensitivity` flag on schedule activities (rain /
  wind / freeze / heat) so exposed work can be sequenced out of the wet/freeze season, plus a new
  `climate_site_risk` register (hazard type, exposure season, severity, controls) for standing
  site-weather hazards. **Weather-delay days** roll up automatically from the daily reports'
  weather-impact field. Reachable in the construction **Build** stage as well as design/developer.
- **Physical climate-risk rollup (W4)** — a scored **Low / Moderate / High / Severe** rating that
  folds flood-plain exposure, assets below the Design Flood Elevation, open site-weather hazards and
  logged weather delays into one number with its driving factors — and feeds the **ESG scorecard**
  (`physical_risk`).
- Endpoints `GET /projects/{id}/resilience/weather` + `/resilience/climate-risk`; the Resilience
  report gains the rating, the site-weather register and the risk factors; `test_resilience` extended;
  demo seeded. Deterministic — no new deps, no external calls.

## v0.3.75 — Climate & water resilience: flood + stormwater (W1–W2)
Treat rainfall and flooding as **quantifiable design parameters** — a new **🌊 Climate Resilience**
panel in the Design (and Developer) workspace.
- **Flood risk (ASCE 24 / FEMA)** — a `flood_risk` assessment (FEMA zone, Base Flood Elevation, Flood
  Design Class, freeboard) computes the **Design Flood Elevation** (DFE = BFE + freeboard, ASCE 24
  minimum by class) and runs the **flood-proof-MEP check**: any Asset Register item whose new
  *Installed Elevation* is below the DFE is flagged to be elevated or flood-proofed. Flags whether the
  site is in a Special Flood Hazard Area.
- **Stormwater (Rational Method)** — a `drainage_area` (catchment) module → peak runoff **Q = C·i·A**
  (runoff coefficient × rainfall intensity × area), composite C, and a first-order detention volume,
  so drainage is sized against a real design storm rather than guessed.
- Endpoints `GET /projects/{id}/resilience/flood` + `/resilience/stormwater`; a Report Center entry
  (flood + stormwater, PDF/Excel); `test_resilience`; demo seeded. Deterministic — no new deps, no
  external calls.

## v0.3.74 — Docs + hardening pass (M1/M2 consolidation)
- **Docs**: README (operations + schedule) and the in-app guide now cover the Facility Condition
  Index and the pull-planning reliability analytics.
- **Security**: reviewed the new operations/schedule endpoints — authorization matches the existing
  patterns (`current_user` for the cross-project roll-ups, `require_role("viewer")` for project-scoped
  reads); no money movement (facility-condition is cost *estimation* only); no new dependencies or
  outbound calls. Bandit + ruff clean (tightened the portfolio roll-up's defensive catch to log
  rather than swallow). Full backend suite (117) + web typecheck green; live console clean across the
  new panels.

## v0.3.73 — Pull-planning reliability analytics (M2)
Deeper Last Planner metrics on the pull-plan board — the learning-loop signals a team improves week
over week, beyond a single PPC number.
- **`pull_plan.metrics()`** — **Tasks-Made-Ready %** (are constraints cleared ahead of the work?),
  **make-ready runway** (weeks of ready work staged), **perfect-handoff %** (predecessor done and
  successor ready ÷ hand-offs), **PPC trend by week**, and the **variance-reason Pareto** (why
  commitments miss). Endpoint `GET /projects/{id}/pull-plan/metrics`.
- **Cross-project benchmark** — `benchmarking.pull_planning()` + `GET /benchmarks/pull-planning`:
  the PPC and TMR distribution across every project vs the ≥80% target, so a plan is judged against
  the team's own portfolio.
- **Board Analytics view** — a 📊 Analytics toggle on the Pull Planning card renders the reliability
  chips (PPC / TMR / perfect hand-offs / runway), the PPC-trend and variance-Pareto charts, and the
  portfolio benchmark. Test coverage extended; demo seeded.

## v0.3.72 — Facility Condition Assessment + FCI (operations phase, M1)
A facility-condition capability for the operate phase: assess building elements, price their
deficiencies, and score the asset's condition — the metric owners and facility managers use to
prioritize capital.
- **`fca_element` module** (Operations; construction + developer) — one record per building element:
  UNIFORMAT II group, linked building system, condition rating (1 Excellent…5 Critical), install /
  expected-life / replacement cost, deficiency + repair cost, recommended year, photo. Workflow
  identified → planned → funded → resolved (resolved leaves the backlog).
- **`fca.py` engine** — **Facility Condition Index** = (deferred maintenance + capital renewal) ÷
  current replacement value, with the band (Good <5% · Fair 5–10% · Poor 10–30% · Critical >30%), the
  deferred/renewal split, and breakdowns by UNIFORMAT group, condition, worst elements, and
  recommended-year forecast. A **portfolio** roll-up ranks buildings worst-first for capital
  prioritization. FCA deficiency costs now also feed the **reserve study** (condition-based, not just
  age-based).
- Endpoints `GET /projects/{id}/fca/index` + `/fca/portfolio`; a **Report Center** entry (FCA / FCI,
  PDF + Excel); a **🏥 Facility Condition** panel in the Operations stage (FCI + band, deferred vs
  CRV, by-UNIFORMAT table, recommended-spend chart, worst-elements, portfolio card). `test_fca`;
  demo seeded.

## v0.3.71 — Nav polish: fix garbled icons + a naming collision surfaced by the Design workspace
Cleanup found while reviewing the new Design nav.
- **Fixed 5 corrupted module icons** — `daily_report`, `incident`, `inspection`, `ncr`, and `permit`
  carried double-encoded (mojibake) icon glyphs from a past edit; they rendered as garbage (e.g.
  "â–£ Permitting"). Restored to their intended symbols (☼ ⚑ ✓ ⚠ ▣).
- **Renamed the drawing register "Drawings & Specs" → "Drawings"** — its fields are all
  sheet-index data (number, revision, discipline, sheet number); the "& Specs" was a misnomer that
  collided with the real **Specifications** register (`spec_section`, the CSI spec book that drives
  the submittal log). The two are now clearly distinct in the nav.
- **`engines: node >=20`** added to the web package so `npm` warns when an older Node is on PATH (the
  production build's post-step needs the global `crypto`, stable since Node 19).

## v0.3.70 — A Design workspace for the architect & engineer, and role-based tool placement
The platform now has a home for the **design phase**. A new **Design** workspace sits between
Drawings and Construction — the architect/engineer's seat (AIA SD/DD/CD · RIBA stages 2–4) — and the
design tools that were scattered across the GC and developer portals now live there. This is a
methodical placement pass so every tool shows in the view(s) whose role owns it; see
[docs/roles-views.md](docs/roles-views.md) for the full role→view map.
- **Design workspace** — nav grouped by design stage: **Brief & program** (Space Program · Project
  Lifecycle) and **Model & standards** (IDS Requirements · CDE / Standards · BIM KPIs · **Model
  Health**). The Model-Health launcher deep-links to the model-QA checks in the Model **Tools** rail
  (Data QA, code-readiness, clash, IDS validate — they run on the loaded geometry). A design
  command-center dashboard (phase, standards, and register tiles) is the landing page.
- **Registers move to their owner** — Space Program, Project Lifecycle, design reviews, selections,
  information requirements/containers, coordination issues, and the design document register are now
  Design-workspace registers.
- **Shared tools show in both workspaces** — a register can now belong to more than one workspace, so
  the A/E↔GC workflows (RFIs, submittals, drawings, transmittals, meetings, permits, specs) appear by
  default in **both** Design and Construction without duplicating records. The GC's Construction view
  is unchanged; the architect/engineer get a focused Design view.
- **Role routing** — the architect and engineer personas now home into Design; every role can still
  reach every register via **Show all modules** or **⌘K**.

## v0.3.69 — Pull planning: the Last Planner phase board
Collaborative pull planning next to the schedule views — the Last Planner System level that sits
between the master schedule and the weekly work plan. The team pulls a phase backward from a
milestone; every trade posts its own tasks and the hand-offs between them; the lookahead makes work
ready by removing constraints; commitments are scored by PPC.
- **`pull_plan_task` module** (Schedule, construction workspace) — a sticky note per task: milestone,
  trade, responsible party, duration, planned week, **predecessor** (the hand-off), and the
  **constraints** that keep it from being ready (design/RFI, submittals, materials, labour,
  equipment, prerequisite work, permits/inspections, space/access, information). Workflow:
  pulled → made ready → committed → done, with a **missed** state gated on a variance reason, and
  paths to reconstrain or recommit.
- **Phase board** — a trade-swimlane × week matrix built over those records, with the hand-off
  sequence, a make-ready log of open constraints, and readiness / commitment / **PPC** (Percent Plan
  Complete = completed ÷ committed). Rendered at the top of the **📅 Schedule** panel with a
  milestone filter, an inline editor (every trade edits its own notes), and a printable **PDF** of
  the board — the hand-out a pull-planning session runs from. Feeds the existing weekly-plan PPC
  analytics rather than replacing them.

## v0.3.68 — Concept space programming: the adjacency graph (standards C8 of 8)
The front of the lifecycle — programming a building before it's massed — closing the eight-release
standards + AI track. The platform now spans land acquisition → programming → design (ISO 19650) →
construction → turnover → operations.
- **`space_program` module** (Programming, developer workspace) — program spaces as nodes: name,
  use type, target area, quantity, level preference, and **“should be adjacent to”** (the edges).
- **`adjacency.py`** (`GET /projects/{pid}/program/summary`) — the program as a graph: total/net/
  gross area, use mix, the node/edge adjacency graph with **unmet preferences** flagged, an
  efficiency %, and the **massing hints** (gross area + use mix) that feed the zoning→massing
  generator and the proforma.
- **“🧩 Space Program” panel** (Design & build) — area KPI cards, the use-mix table, adjacency chips
  (unmet flagged), and the massing hand-off line.
- **Docs** — README + roadmap now describe the full span (acquisition → programming → ISO-19650
  design → construction → turnover → twin/ESG operations) and the C1–C8 track.
- Verified live (4 nodes, 38,700 sf gross / 35,500 net, 91.7% efficiency, Lobby→Retail unmet) +
  `test_program`. Typecheck + 49 vitest + Pages build green.

## v0.3.67 — Drawing-sheet extraction (standards C7 of 8)
Reading a drawing set into structured data — offline-first and honest, never inventing a sheet.
- **`sheet_extract.py`** (`POST /projects/{pid}/extract/sheets`) — parses an uploaded PDF's text
  layer (pypdf) or a pasted sheet index into `{number, title, discipline}`, inferring the discipline
  from the sheet prefix (A→Architectural, S→Structural, M/E/P→MEP, C→Civil…). Deterministic; an
  image-only scan with no text layer returns nothing and says so (set an Anthropic key to read page
  images). With `create=true` the extracted sheets become **Drawing records** in one step.
- **“🗂 Sheet index” tab** in AI Assist — upload a PDF or paste a list, preview the extracted table,
  optionally create the drawing records.
- Verified live (paste → 3 sheets extracted with disciplines) + `test_sheet_extract` (9-sheet index
  parsed, noise ignored, 9 drawing records created). Typecheck + 49 vitest + Pages build green.

## v0.3.66 — Procurement compliance gate (standards C6 of 8)
Turns the platform's existing COI / prequal / subcontract / lien-waiver records into an enforceable
compliance posture — the “can this sub bid or bill yet?” gate, plus the outbound nudge list.
- **`procurement_gate.py`** — per-vendor readiness from the compliance records:
  - `GET /projects/{pid}/procurement/gate?vendor=` → **can bid** (approved prequalification + active
    insurance) and **can bill** (executed subcontract + active insurance) with the specific blockers;
    reports the COI status/expiry, prequal status, subcontract execution, and whether a waiver is on file.
  - `GET /projects/{pid}/procurement/compliance-feed` → the outbound nudge list: every vendor with an
    expiring / expired / missing COI or an unapproved prequal, so the GC chases the paperwork before it
    blocks a bid invitation or a pay application.
- **Procurement-compliance-gate card** in the ⚖️ Risk & Cost panel (flagged vendors, issues, bid/bill
  status). Money movement stays behind the flagged licensed-rail bridge — this gates on paperwork only.
- Verified live (Bedrock flagged: expired COI + unapproved prequal → can't bid/bill; Acme clears) +
  `test_procurement_gate`. Typecheck + 49 vitest + Pages build green.

## v0.3.65 — Digital-twin readiness + Digital Product Passport (standards C5 of 8)
Deepens the two KPI categories that were placeholders — the data a building needs to run as a digital
twin, and the emerging EU product-passport requirement.
- **`building_system` module** — the HVAC / electrical / plumbing / fire / vertical-transport / BMS
  systems an asset belongs to, with the BMS integration protocol (BACnet, Modbus, KNX, MQTT…).
- **Asset register gains a “Digital Twin” fieldset** (link to a building system + sensor/telemetry
  point ID + sensor type) and a **“Product Passport” fieldset** (GS1 Digital Link ID, EPD/
  environmental reference, manufacturer-data URL).
- **`twin.py`** (`GET /projects/{pid}/twin/readiness`) — asset↔system linkage %, sensor-mapping %,
  a combined twin-readiness score (ISO 23247), the building-system graph with BMS-integration count,
  and **DPP completeness** (honest about the passport being an emerging 2028-30 EU requirement).
- The BIM KPI scorecard’s **Digital Twin Readiness** and **Construction Data Readiness** categories
  now read these richer signals (system-linked + sensor-mapped; product data + DPP).
- **Digital-twin readiness card** in the 🔧 Operations panel.
- Verified live (25% twin-ready on the seeded assets, DPP note) + `test_twin` (66.7% linked / 33.3%
  sensored → 50% twin-ready; DPP 33.3%; KPI reflects both). Typecheck + 49 vitest + Pages build green.

## v0.3.64 — AI over the model: MCP server + standards experts (standards C4 of 8)
Two ways an AI works *with* a project — both offline-first and grounded in real data, never a model
guessing from memory.
- **Standards-compliance experts** (`standards_expert.py`, `GET /projects/{pid}/standards/check?
  standard=iso19650|cobie|ids|uniclass`) — run the named standard against the project's own CDE,
  requirements register, asset data and model-quality index; return findings each with the **clause
  it references** and a recommendation, plus a 0–100 readiness score. Fully deterministic, no key.
  Surfaced as a **Compliance check** card (four standard buttons) in the CDE / Standards panel.
- **MCP server** (`mcp_server.py` + `mcp_tools.py`, `GET /mcp/tools`) — exposes the project to
  external AI agents (Claude Desktop, Cursor) as callable tools: project snapshot, list records, CDE
  status, BIM KPI scorecard, openBIM quality, standards check, and **create RFI** (a write tool).
  Tool logic reuses the same engines the HTTP API does, so an agent's reads/writes pass the exact
  same validation and workflow gates as the UI. The MCP SDK is an **optional** dependency (offline-
  first); the stdio server prints install guidance if it's absent. [docs/mcp.md](docs/mcp.md).
- Verified + `test_mcp_standards` (catalog exposes 8 tools; dispatch runs snapshot/records/CDE and
  creates a real RFI; unknown tool raises; experts return clause-referenced findings). Live:
  compliance card renders ISO 19650 findings with clauses. Typecheck + 49 vitest + Pages build green.

## v0.3.63 — BIM KPI scorecard + handover acceptance (standards C3 of 8)
The information-management scorecard the industry runs on — ten categories, graded from data the
platform already holds, with a formal owner's-acceptance gate at handover.
- **`bim_kpi.py`** (`GET /projects/{pid}/bim-kpi/scorecard`) — the ten categories graded
  good/warn/poor/**n-a**: Information Requirements, Model Authoring Quality, openBIM Exchange,
  Coordination Control, Issue Resolution, CDE Discipline, Asset Data Readiness, Construction Data
  Readiness, Handover Assurance, Digital Twin Readiness. Each rolls up existing data — the CDE
  (C1), model quality (C2, when a model is loaded), and the RFI / coordination / asset / closeout
  records — and shows **n/a rather than a guess** when its inputs are absent. Overall health %.
- **Handover data-drop acceptance gate** (`GET …/handover/acceptance`) — the owner's checklist
  against the AIR: requirements issued, assets tagged for CMMS (≥90%), as-builts, O&M, accepted
  completion certificate → one accept/not-ready verdict.
- **“📊 BIM KPIs” panel** (Plan & derisk) — health + grade-count cards, the acceptance banner, and
  the traffic-light category table. **Report Center: “BIM KPI Scorecard (ISO 19650)”** (PDF/Excel).
- Verified live (health %, 🟢🟡🔴⚪ grades, handover checklist) + `test_bim_kpi` (empty → 10 n/a;
  populated → info-reqs/CDE/asset/handover good; report PDF). Typecheck + 49 vitest + Pages build green.

## v0.3.62 — openBIM model-quality scoring (standards C2 of 8)
Turns the loaded IFC model into measurable buildingSMART quality signals — the layer that makes IDS
authoring (already shipped) actionable, and feeds the coming BIM KPI scorecard.
- **`openbim_quality.py`** (`GET /projects/{pid}/openbim/quality`) — pure scoring over the model's
  property index:
  - **LOIN per element** (Level of Information Need, the ISO 19650 successor to "LOD") — each element
    scored across geometry / type / classification / properties / quantities; reports average score,
    the “coordinated” share (≥4 of 5 facets), and per-facet coverage.
  - **IDS rule-compliance %** — pass `?use_case=` (fire & life safety, handover COBie, energy,
    quantities) and every applicable element is scored against its IDS spec (must carry every
    required property) → per-spec and overall compliance %.
  - **IFC export health** — proxy/untyped share, type coverage, property coverage graded pass/warn/
    fail (the authoring-export defects that quietly break QTO, carbon and IDS).
  - **bSDD / classification alignment %.**
- Surfaced as an **openBIM model-quality card** in the CDE / Standards panel (degrades to a
  “load a model” hint when none is open).
- Verified + `test_openbim_quality` (LOIN distribution, IDS walls 2/3 → 66.7%, export-health proxy
  flag, bSDD %) over a synthetic index — no live model needed. Typecheck + 49 vitest + Pages build green.

## v0.3.61 — ISO 19650 information management: CDE + requirements register (standards C1 of 8)
Opens a standards-alignment track (grounded in ISO 19650, buildingSMART, and the industry BIM-KPI
frameworks). First: formal information management, replacing scattered document status with a proper
Common Data Environment.
- **`information_container` module** — deliverables (models, drawings, docs) move through the ISO
  19650 CDE states **Work-in-progress → Shared → Published → Archived**, carrying a
  **suitability/status code** (S0–S4 shared, A published-for-construction, CR/AB record) and a
  **revision**. Sharing requires a suitability code; publishing requires a revision (the review gates).
- **`info_requirement` module** — the requirements register: OIR/AIR/PIR/**EIR**/**BEP**/MIDP/TIDP
  with appointing / lead-appointed / appointed parties, `draft → issued → superseded`.
- **`GET /projects/{pid}/cde/status`** (`cde.py`) — container state distribution, suitability
  spread, and the three **CDE-discipline** metrics (revision control %, approval-status coverage,
  metadata completeness) that feed the forthcoming BIM KPI scorecard.
- **`GET /projects/{pid}/info-requirements/register`** — requirements by type + **core-document
  coverage** (flags a missing EIR/BEP/AIR).
- **“🗂 CDE / Standards” panel** (Plan & derisk) — container-state cards, CDE-discipline table,
  requirements register with the core-coverage banner.
- Verified live (panel shows 2 WIP / 1 Published, discipline metrics, missing-AIR flag) +
  `test_cde` (WIP→Shared→Published gated on suitability then revision; core-coverage). Typecheck green.

## v0.3.60 — Navigation at scale + a current demo
The panel list had outgrown a flat sidebar. Research pass over the published evidence on
information architecture for feature-dense products (navigation-depth studies, journey-based
step navigation, design-system shell-capacity guidance, and how large platforms restructured
around starred/recent + curated workspaces) — recorded in [docs/ux-ia.md](docs/ux-ia.md) with
the rules for future features (no new top-level items; two disclosure tiers max).
- **Lifecycle-stage navigation** — the portal's first-class destinations are grouped under stage
  headers instead of one flat list. Construction: *Plan & derisk → Build → Turn over & operate*;
  Developer: *Acquire → Design & build → Operate*; both end with *Across projects* (Portfolio,
  Benchmarks). Journey-based IA, matching how AEC teams already think in phases.
- **🕘 Recent** — the last five opened registers surface automatically at the top of the module
  list (below the opt-in ★ Favorites) — zero-setup wayfinding for ~100 registers.
- **⌘K taught in context** — a persistent "Jump anywhere: Ctrl/⌘+K" hint anchors the nav; the
  command palette is the long-tail navigator.
- **Pages demo brought current** — the captured massing.build/app snapshot pre-dated v0.3.49;
  every newer panel (Lifecycle, Turnover, Diligence, Operations, Energy, Asset Mgmt, ESG & POE,
  Risk & Cost, Benchmarks) rendered empty. The demo project now runs the full lifecycle (DD +
  entitlements, design gates, PM-generated work orders, 6 months of meter readings, reserve/CIP,
  leases + CAM, POE) and captures all engine endpoints — 608 fixtures, verified with a full
  two-persona walkthrough and a clean console.
- **Guide updated** — new "Tutorial 7 · Operate it" (diligence go/no-go, PM work orders, EUI,
  reserve study, CAM statements, ESG/POE) + ten plain-English glossary entries (EUI, CAM
  gross-up, Scope 1/2, POE, …).

## v0.3.59 — ESG rollup + post-occupancy evaluation (lifecycle R7 of 7)
The final lifecycle release: the asset's sustainability scorecard and the feedback loop from measured
performance back to design — all computed locally from the platform's own data.
- **ESG rollup** (`esg.py`, `GET /projects/{pid}/esg`) — metered energy (EUI via energy.py),
  **operational GHG Scope 1/2** from a transparent local factor table (on-site fuel vs purchased
  energy; set `AEC_GRID_KGCO2E_PER_KWH` to the local grid subregion factor), GHG intensity, water +
  intensity, and certification tracking (LEED credits targeted vs achieved). Nothing fetched,
  nothing fabricated.
- **`poe` module** — post-occupancy evaluations at levels 1 (indicative) / 2 (investigative) /
  3 (diagnostic) with occupant-satisfaction score, design EUI, findings and feed-forward lessons;
  workflow `planned → fieldwork → reported` (report requires findings). The rollup compares
  **design EUI vs metered actual** and reports the gap.
- **“🌱 ESG & POE” developer panel** — EUI/GHG/water/cert KPI cards, scope split with the factor
  note, latest-POE card with the vs-design gap, one-click PDF.
- **Report Center: “ESG / Sustainability Summary”** — PDF/Excel with GHG table, POE comparison,
  and data-coverage caveats.
- **Docs** — README + roadmap now describe the full span: land acquisition → due diligence &
  entitlements → design → construction → turnover → operations (CMMS, energy, reserves/CIP, CAM,
  ESG/POE). Lifecycle releases R1–R7 complete.
- Verified live (panel + PDF; grid-factor override changes Scope 2) + `test_esg`; typecheck +
  49 vitest + Pages build green.

## v0.3.58 — Capital planning + CAM reconciliation (lifecycle R6 of 7)
Hold-phase capital stewardship: will the reserves cover the roof in 2031, and did tenants pay their
fair share of operating expenses this year?
- **Reserve study** (`reserve.py`) — the asset register grows Reserve Study fields (expected life,
  replacement cost); `GET /projects/{pid}/reserves/study` projects recurring component replacements
  plus open capital-plan items over a 20–40 yr horizon (inflation-escalated), runs the year-by-year
  reserve balance, flags the **first underfunded year**, and solves the **suggested level annual
  contribution** that keeps the fund solvent.
- **`capital_plan` module (CIP)** — capital items with planned year, cost, priority
  (critical/recommended/discretionary), funding source and ROI note; workflow
  `proposed → approved → funded → complete`. Open items ride the reserve projection.
- **`cam_expense` module + CAM true-up** (`cam.py`) — operating-expense lines by standard category
  (janitorial, R&M, utilities, security, admin, management, insurance, taxes) with budget/actual and
  variable/recoverable flags. `GET …/cam/reconciliation`: recoverable pool with **variable-only
  gross-up** to a stated occupancy (fixed expenses pass at actual), each tenant's pro-rata share vs
  estimated payments (lease `recovery_psf` × sf), balance due or credit.
- **Per-tenant statement PDF** — `GET …/cam/statement/{lease}.pdf`: expense pool by category, the
  tenant's share, estimated payments, true-up balance.
- **Finance ▸ “Asset Mgmt” tab** — reserve-study runner (balance / contribution / horizon /
  inflation inputs, funding banner, replacement schedule), CIP table, CAM reconciliation with
  per-tenant statement downloads.
- Verified live (underfunded banner + suggested $/yr, escalated recurring events, CAM table w/ PDF
  served) + `test_reserves_cam`; typecheck green.

## v0.3.57 — Operations: CMMS + metered energy (lifecycle R5 of 7)
The biggest post-turnover gap: ~80% of a building's lifetime cost is operations. Adds the CMMS loop
(preventive maintenance before failures) and utility metering (EUI benchmarking) — fully offline.
- **`work_order` / `pm_schedule` modules** (Operations section) — corrective/preventive/emergency
  work orders with asset refs, priority, labor hours and cost; workflow
  `open → assigned → in_progress → completed → verified` (completion requires a completed date).
  PM schedules carry a task list, frequency and next-due date.
- **PM generation + KPIs** (`cmms.py`) — `POST /projects/{pid}/cmms/generate-pm` turns every due,
  active PM schedule into a preventive work order (idempotent per cycle; advances next-due).
  `GET …/cmms/kpis`: open by priority/type, overdue backlog, **PM compliance %**, **MTTR** (days).
- **`meter` / `meter_reading` modules** — electric/gas/water/steam/chilled-water meters with dated
  consumption + cost readings, entered manually or CSV-imported via the generic module import.
- **Metered energy rollup** (`energy.py`) — `GET …/energy/actual`: site kBtu by utility (standard
  conversion factors), monthly trend, water (tracked in gallons, not energy), utility cost, and
  **EUI (kBtu/sf/yr)** annualized over covered months using the model's GFA (or `?gfa_sf=`).
  Distinct from the design-model simulation at `GET …/energy`.
- **Benchmarking bridge** (`energy_star_bridge.py`, feature-flagged) — reports honestly that no
  provider is configured until a deployment sets `ENERGY_STAR_*` credentials; never fabricates a
  score. Local EUI/trends need no account.
- **“🔧 Operations” + “⚡ Energy” construction panels** — maintenance KPI cards, one-click PM
  generation, open-WO table; EUI/energy/cost/water cards, monthly trend chart, by-utility table.
- Verified live (both panels with seeded meters/readings/schedules; PM generation created WOs and
  was idempotent on re-run) + `test_operations`; typecheck + 49 vitest green.

## v0.3.56 — Pre-acquisition: due diligence + entitlements (lifecycle R4 of 7)
Fills the pre-construction gap the lifecycle research surfaced — the 6–36 months of study and
approvals between site control and capital commitment (grounded in institutional due-diligence
practice: ALTA/ASTM E1527 categories and the standard entitlement pipeline).
- **`due_diligence` module** (Acquisition, developer workspace) — study items by category
  (Title/ALTA survey, Phase I ESA (ASTM E1527), Phase II, Geotechnical, Utility capacity, Traffic,
  Wetlands/species, Zoning verification, Tax/legal) with consultant, findings, risk level, study cost
  and ordered/due/received dates. Workflow `open → in_review → cleared | flagged` — a report can't be
  submitted without findings, and flagging requires a risk level.
- **`entitlement` module** — applications (Rezoning, Site plan, CUP, Variance, Plat, Comp-plan
  amendment, Environmental review, Annexation) with agency, submitted/hearing/decision dates, a
  public-meeting/opposition log, conditions imposed, and **approval expiration**. Workflow
  `draft → submitted → hearing → approved | denied → appealed → hearing`; revisable for resubmittals.
- **Go/no-go rollup** — `GET /projects/{pid}/diligence/readiness`: DD by category
  (cleared/flagged/open), high-risk findings, the entitlement pipeline by state, and approvals
  expiring within 180 days → one `go` flag. New **“📜 Diligence & Entitlements”** developer panel
  (readiness banner, high-risk card, category table).
- Verified live (panel renders the NOT-READY banner, high-risk card, category rollup) +
  `test_diligence` (workflow gates + rollup), typecheck + 49 vitest green.

## v0.3.55 — UX, accessibility & front-end performance (readiness R3 of 7)
- **`prompt()` fully retired from the portal** — a new accessible `promptModal` (on the shared
  modalShell: role=dialog, focus trap, Esc/backdrop close, Enter submits, required-field validation)
  replaces all ten remaining `window.prompt()` calls: lifecycle **gate sign-off**, turnover
  **G704 certify** (both fields in one dialog), save view, templates (apply/save), add enum option,
  quick-create reference records, send-for-signature, and reassign.
- **Accessibility** — all **53** portal table headers now carry `scope="col"`; verified the viewer
  toolbar's icon buttons already ship `aria-label`s.
- **Performance measured** — the portal ships in the main `index` chunk at **92 KB Brotli** (shell
  budget 156/220 KB) — under the lazy-split threshold, so no code-motion was needed; recorded so
  future growth has a baseline.
- Verified **live**: certify flow end-to-end through the new dialog (open → validate → certify →
  “Architect certified” + G704 download), 375 px mobile viewport with no horizontal scroll, zero
  console errors; 49 vitest + typecheck + Pages build + budget green.

## v0.3.54 — Production hardening: ops & supply chain (readiness R2 of 7)
The deployment/ops half of the production-readiness plan — making "did we configure it right?"
a runnable gate and the supply chain deterministic:
- **Runnable go-live gate** — new [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) +
  `scripts/validate_prod_config.py` preflight (asserts RBAC, real secrets, secure cookies, CSP/HSTS,
  Redis-when-multi-worker, non-default DB/MinIO credentials; exit 0 = go). Referenced from deploy.md.
- **Supply chain** — Dependabot across pip/npm/cargo/actions (the viewer's pinned three/@thatopen pair
  moves as a group); CI now **builds the api+web images, scans them with Trivy (CRITICAL+fix = fail),
  and publishes to ghcr** with immutable `:sha` tags; a one-shot workflow generates + commits
  **Cargo.lock** so desktop builds stop floating transitive Rust deps.
- **Desktop trust** — the PyInstaller backend **sidecar is now Authenticode-signed** alongside the
  Tauri shell when a certificate is configured (SmartScreen inspects it separately).
- **Guardrails** — `seed_demo.py` refuses to run against an instance that already has projects
  (`--force` for labs); Host-header pinning via `AEC_ALLOWED_HOSTS` (TrustedHostMiddleware, opt-in);
  `/metrics` gains `http_responses_by_class_total` (2xx/4xx/5xx) for one-label alerting.
- Verified: preflight self-test (bad env → exit 1 with 4 failures; good env → exit 0), metrics smoke,
  all workflow/compose YAML parse, ruff clean.

## v0.3.53 — Production hardening: backend blockers (readiness R1 of 7)
From a full production-readiness audit (code + docs + deployment). Fixes the findings that make the
difference between "works in dev" and "safe under load, multi-worker, and misconfiguration":
- **Fail-fast production guard** — booting on **Postgres** without `AEC_RBAC=1` or with the default
  auth secret now **refuses to start** (explicit `AEC_ALLOW_OPEN=1` escape hatch). A forgotten env var
  is a loud crash at boot, not an open platform discovered later. CRITICAL log when the rate limit is
  on with multiple workers but no shared Redis counter.
- **Project list scales + doesn't leak** — `GET /projects` filters membership in SQL (join) instead of
  loading every project then running one role query each (N+1), and is paginated.
- **Bounded loads everywhere** — kanban `board()` returns capped per-state cards plus TRUE counts from
  a GROUP BY (was: materialize up to 100k records per request); CSV export **streams** page-by-page;
  the list `?limit=` param is clamped; Procore sync reads only the `procore_id` column via SQL json
  extraction (was: `limit=1_000_000` full-record load).
- **Observability** — fragment-conversion and publish failures now `logging.exception` (they were
  visible only in a status JSON nobody polls); auto-sync schedule failures log at WARNING.
- **Multi-worker autosync** — a Postgres advisory lock elects one runner per tick, so N workers no
  longer each pull the same external records.
- **Uploads & traversal** — the properties-index upload is size-gated (413 over `AEC_PROPS_MAX_MB`,
  default 100); attachment filenames explicitly collapse `..` sequences (belt on top of the existing
  storage containment guard).
- **Complete project deletion** — deleting a project now removes the **whole `{pid}/` storage prefix**
  (source-IFC copies, props index, publish status — not just the model tile) via a new
  `storage.delete_prefix` on both local and S3 backends.
- **Rate limiter** — evicts oldest buckets under IP churn instead of clearing all state at once.
- Verified: new `test_prod_hardening` + adjacent regressions (modules/rbac/security/connections/api/
  bcf) green, ruff + bandit clean.

## v0.3.52 — Architect sign-off + G704 substantial completion + record turnover (lifecycle track 4 of 4)
The final track closes the loop to turnover: the **Architect certifies substantial completion**, signs
off the punch list, and the as-built **record model** is stamped for handover.
- **`turnover.py` + `/turnover/*` endpoints** — `readiness` (punch rollup + latest model version; a
  G704 certifies *with* an open punch list, so the gate is that a punch list is prepared), `certify`
  (Architect certifies on a `completion_certificate` record: records the **Architect (certifying) +
  Owner + Contractor** signatures, stamps the current model version as the record model, issues the
  certificate), and `status` (signed cert + record-model summary).
- **G704 Certificate of Substantial Completion** generator in `contracts.py` — attaches the punch-list
  summary, the record-model version, and the occupancy date; reachable via
  `…/contracts/completion_certificate/{rid}/document.pdf?doc=g704`. The **Architect** is now a signatory
  on the G701 change order too.
- **Turnover package** — `closeout/package.zip` gains `turnover/status.json` (readiness + signed
  substantial-completion cert + record model version) alongside the as-built model, COBie and closeout
  manifest. `completion_certificate` gains occupancy-date / record-model-version / punch-% fields.
- **UI** — a **"🏁 Turnover"** construction-workspace panel: punch readiness, architect certification
  (with signatories), and one-click **G704** download.
- Verified: ruff + bandit clean, backend gate (new `test_turnover` — gate refuses with no punch list;
  architect certifies + Owner/Contractor sign; G704 renders; status reflects the signed cert) +
  `test_contracts`/`test_closeout` regressions, web typecheck + 49 vitest + Pages build + budget green.

**This completes the architect/engineer design-to-turnover lifecycle upgrade (4 tracks, v0.3.49–52).**

## v0.3.51 — Design-change instruments: ASI / Bulletin / Sketch (lifecycle track 3 of 4)
The standard AIA construction-phase change instruments, wired into the existing change chain.
- **New modules `asi`, `bulletin`, `sketch`** (Change Management section, config-driven CRUD + workflow):
  - **ASI** (AIA G710) — the Architect issues a supplemental instruction; **no cost/time**; the
    Contractor acknowledges (`issued → acknowledged → closed`).
  - **Bulletin** — a formal design revision; when it carries cost/time it links to a `change_event`
    (→ `pco_request → cor`) for pricing (`draft → issued → priced → closed`).
  - **Sketch (SK)** — a clarification sketch that attaches to an ASI / Bulletin / RFI / drawing.
- **Document generation** — G710 ASI + Bulletin cover-sheet + **G714 Construction Change Directive**
  (rendered from a `directive` record) added to `contracts.py`; all reachable through the existing
  `GET /projects/{pid}/contracts/{key}/{rid}/document.pdf?doc=asi|bulletin|ccd`. `directive` is the
  platform's CCD (G714) instrument.
- Verified: ruff + bandit clean, `test_change_instruments` (ASI issue→ack no cost; Bulletin cost impact
  links a change_event; SK attaches; ASI/Bulletin/CCD render as PDFs) + `test_contracts` regression,
  web typecheck green.

## v0.3.50 — IFC family library (lifecycle track 2 of 4)
The "families" folder now ships real `.ifc` content and a browsable library, fully offline.
- **Generated parametric core library** — `build_family_library.py` writes the whole catalog to a
  shippable **`services/data/families/library.ifc`** (46 families, each a GUID-stable `IfcTypeProduct`
  with mapped geometry, IFC4). The catalog gained **openings** (single/double door, fixed/sliding
  window), **enclosure** (interior partition, exterior wall, curtain-wall panel), and **concrete
  columns/beams** on top of the existing furniture / sanitary / appliance / lighting / MEP /
  structural / transport / plant families.
- **Family-library server** — `GET /families/library` (generated catalog grouped by category +
  the generated library + any curated external files) and `POST /projects/{pid}/families/place`
  (place a library family, GUID-stable, via the `add_family` recipe). The viewer's **Furnish & equip**
  picker now reflects the full library and its family count.
- **Curated external** — `services/data/families/external/` with a `SOURCES.md` of vetted free openBIM
  sources (buildingSMART samples, opensourceBIM/IFC-files, NBS National BIM Library, bSDD); drop an
  `.ifc` there or use `POST /families/import` to bring in manufacturer content. No third-party binaries
  are bundled without explicit review.
- Verified: ruff + bandit clean, backend gate (new `test_family_library` — library builds + reopens +
  place-from-library), web typecheck + 49 vitest + Pages build + budget green.

## v0.3.49 — Design-phase spine + itemized soft costs (lifecycle track 1 of 4)
Makes the architect/engineer design lifecycle explicit. Grounded in the RIBA Plan of Work 2020 (stages
0–7) mapped to the AIA design phases (Schematic Design → Design Development → Construction Documents →
Construction Administration), ISO 19650 information stages, and standard development soft-cost / design-
fee breakdowns.
- **`design_phase.py` + `project_phase` module** — the eight RIBA/AIA phases as **formal gates**. Each
  phase carries its deliverables, A/E design-fee %, and ISO-19650 status (S0→AM); the gate advances only
  when the **Architect + Owner** sign it off (`approve_gate` transition, requires a signer). Generating a
  project now seeds the eight phases automatically.
- **`soft_costs.py` — itemized, phase-aware soft costs** — the flat "soft = 25% of hard" is replaced by
  a transparent taxonomy (architecture & engineering fee, permits/entitlements, legal, financing &
  interest, insurance & bonds, developer fee, FF&E, marketing/lease-up, soft contingency). Totals are
  unchanged by default, but the **A/E design fee is drawn down across SD/DD/CD/Bid/CA** per standard
  splits. The generate seed (`_seed_dev_budget`, `_proforma_seed`) now emits itemized soft-cost lines.
- **Endpoints** `GET /projects/{pid}/lifecycle` (phases + gate state + soft-cost allocation + current
  stage), `POST …/lifecycle/seed`, `GET /lifecycle/reference`. New **"🧭 Project Lifecycle"** developer-
  workspace panel: the phase rail with deliverables, fee %, ISO status, gate sign-off, and the itemized
  soft-cost table.
- Verified: ruff + bandit clean, backend gate (new `test_design_phase`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.48 — Hardening, accessibility & documentation pass
A quality pass over the recently-shipped features: debug + full test sweep, a security-hardening
review, accessibility on the new UI, and a documentation refresh.
- **Security — outbound-URL guard.** New `net.py` `validate_outbound_url()` gates the bridges that
  fetch an **operator-configured** URL — **webhooks**, the real-estate syndication bridge, and the
  e-sign bridge — rejecting non-http(s) schemes (blocks `file://` / `gopher://` local-file-read + SSRF
  vectors) with an opt-in private-host check. The fixed-provider fetches (Autodesk, Google/Microsoft
  OAuth, Procore) and the already-guarded Speckle bridge were reviewed and left as-is.
- **Accessibility.** The new **Land Screening**, **IDS Requirements** and **conceptual-estimate**
  forms had placeholder-only inputs; every field now carries an `aria-label` so screen readers
  announce it. All new destinations confirmed reachable from the workspace nav (native `<button>`s,
  keyboard-operable).
- **Tests.** New `test_net`; backend gate now **97/97** suites. Web typecheck + 49 vitest + Pages
  build + bundle budget (156 KB shell < 220 KB) all green. `ruff` + `bandit` clean.
- **Docs.** Competitive/vendor comparison removed from the documentation set (README, the public
  landing page, the lifecycle graphic, roadmap/audit notes) in favor of neutral capability language;
  integration/connector references (Procore SSO + sync, ACC, QuickBooks/Sage) are retained as the
  factual product features they describe. README "Recent work", CHANGELOG and the GitHub About refreshed
  to current state; stale internal links removed.

## v0.3.47 — Land parcel screening + data connector
Land acquisition screening. The nationwide parcel dataset is a licensing play, so it's a
feature-flagged connector; the pure-software win — which plays to our GIS + feasibility + proforma
engines — is **screening**.
- **`parcels.py`** — screen a parcel set (imported GeoJSON / entered) by **size, zoning, flood zone,
  sewer/water, price**, and **rank by max-buildable opportunity**: each parcel gets a max envelope
  (area × FAR) and a **conceptual cost** (via `conceptual_estimate`), plus **land cost per buildable SF**
  — a screen → envelope → proforma chain that runs before acquisition, not just after.
- **`parcels_bridge.py`** — nationwide parcel/ownership/comps data is an optional paid connector
  (`PARCEL_PROVIDER`, Regrid/ATTOM/CoreLogic pattern) that raises rather than shipping fake data; the
  screening engine works on parcels you supply without it.
- Endpoints: `POST /parcels/screen`, `GET /parcels/data-status`. A **🗺️ Land Screening** developer-
  workspace panel (paste parcels → set criteria → ranked buildable-opportunity table).
- Verified: ruff clean, 96/96 backend suites (new `test_parcels`), web typecheck + 49 vitest + Pages
  build + budget green.

**This completes the second capability round (4 tracks, v0.3.44–47) on top of the code-quality gate
(v0.3.43).**

## v0.3.46 — Conceptual estimating + AI IFC classification
Two model-native intelligence features that leverage our IFC/massing strengths.
- **`conceptual_estimate.py`** — a parametric **$/SF** cost from building type + GFA + units at the
  massing stage (on-brand for a product called Massing): a low/base/high range **escalated for region
  and year**, with derived $/SF, $/unit and $/key for the proforma before there's a detailed takeoff.
  Built-in cost-per-SF table (16 building types) + regional index + ~4.5%/yr escalation, all overridable.
- **`ifc_classify.py`** — a transparent rules classifier that suggests the right **IfcClass** for
  `IfcBuildingElementProxy`/generic or mis-named elements (a proxy gets no quantity or carbon factor, so
  this directly improves **QTO + embodied carbon** accuracy). Every suggestion carries its reason;
  human-approved — reads the loaded property index or a posted element list.
- Endpoints: `GET /estimate/conceptual/catalog`, `POST …/estimate/conceptual`, `POST …/ifc/classify`.
  Surfaced in the **🛡 Risk & Cost** panel (a $/SF estimate mini-form + a model-classification summary).
- Verified: ruff clean, 95/95 backend suites (new `test_conceptual`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.45 — Materials procure-to-pay: quote leveling + 3-way match
The materials buying loop — distinct from sub-bid leveling. Deterministic/offline on top of the
modules we already have (`commitment` = PO, `delivery`, `sub_invoice`).
- **`procurement.py` — quote leveling** — normalize competing supplier quotes into an apples-to-apples
  grid with the low price per line item, the best-value supplier, per-supplier totals, and line-by-line
  savings (handles split awards where the cheapest supplier differs per item).
- **3-way match** — reconcile each PO against its deliveries and invoices, flagging **over-billing**
  (invoiced > PO), **pay-before-receipt** (invoiced with nothing received), and **un-invoiced
  deliveries**. Surfaced in the **🛡 Risk & Cost** panel.
- **`procurement_bridge.py`** — RFQ dispatch to suppliers is a feature-flagged stub (`RFQ_PROVIDER`)
  that raises rather than pretending to send; the *quote leveling* and *3-way match* work without it.
- Endpoints: `POST /projects/{pid}/procurement/level-quotes`, `GET …/three-way-match`, `/procurement/rfq-status`.
- Verified: ruff clean, 94/94 backend suites (new `test_procurement`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.44 — IDS authoring + EIR
Closing the BIM-standards loop upstream. We already *validate* models against an IDS; the demand is
upstream of that — **authoring** the requirements in the first place.
- **`ids_authoring.py`** — a starter requirements template library (what data each element type should
  carry: walls → FireRating/LoadBearing/…, doors, windows, slabs, spaces, columns, beams — from the
  standard `Pset_*Common` sets), bundled into **use cases** (handover/COBie, fire & life safety, energy,
  quantities). `build_ids()` emits a **standards-valid buildingSMART IDS 1.0** file via `ifctester` that
  **round-trips through our own validator**, and `eir_markdown()` generates an **EIR** (Exchange
  Information Requirements) document for the BIM contract.
- Endpoints: `GET /ids/templates`, `POST /ids/build` (→ downloadable `.ids`), `POST /ids/eir` (→ EIR.md).
  Model compliance-checking stays the existing `/validate` endpoint — closing the spec → implement →
  validate loop.
- **UI:** a **📋 IDS Requirements** portal panel — pick a use case, preview the required properties,
  download the IDS + EIR.
- Verified: ruff clean, 93/93 backend suites (new `test_ids_authoring` round-trips the IDS through
  ifctester), web typecheck + 49 vitest + Pages build + budget green.

## v0.3.43 — Code-quality gate (ruff + bandit in the loop) + BCF XXE fix
Applying the "enterprise-quality code with AI agents" discipline — verification *in the loop*, not after.
- **Static-analysis gate (ruff)** — a tuned config (`services/api/ruff.toml`) enforces the high-signal
  rules that catch real defects and dead code (pyflakes `F`, syntax `E9`, bugbear `B`) while respecting
  the codebase's deliberate idioms (compact `;` one-liners; the logged fail-open `except Exception`
  pattern is *not* linted). Wired into CI as a **blocking** step. Fixed everything it found: **14 unused
  imports + 2 unused variables** (dead code removed) and a **loop-variable closure bug** in the BCF
  camera parser.
- **Security scan (bandit)** — added to the report-only security workflow and run before shipping. It
  surfaced a real one: **`bcf_io.py` parsed untrusted uploaded BCF XML with the vulnerable stdlib
  parser (XXE / billion-laughs vector)** — now uses **`defusedxml`**, the same hardening already applied
  to CityGML import. Fixes an actual vulnerability on the BCF import path.
- `ruff` + `bandit` added to `requirements-dev.txt`; `CONTRIBUTING.md` documents the local gates.
- Verified: ruff clean, 92/92 backend suites, bandit XXE finding resolved.

## v0.3.42 — Tiers 2 & 3: fintech depth + differentiated (carbon, code, pricing)
The rest of the capability roadmap. Every engine is offline/deterministic (AI only where it helps),
source-linked, and never fabricates; money movement and live pricing are feature-flagged bridge stubs
that raise actionable errors rather than faking a result.
- **Subcontractor prequalification** — a transparent Q-score (safety/EMR, financial, experience, rating,
  currency = 100 pts, every point traceable) + a **COI-expiry** feed. A single sub default costs a GC
  1.5-3× the subcontract, so this is a core risk gate before award.
- **Pay-app ↔ lien-waiver reconciliation** — matches what was **paid** (`sub_invoice`) against **waivers**
  on file (`lien_waiver`, conditional vs unconditional) and surfaces per-vendor **lien exposure**. Massing
  never moves money: a `payments_bridge` stub disburses only through a licensed processor and refuses
  release while exposure remains.
- **Accounting export** — double-entry **GL CSV** + **QuickBooks IIF** bills from the cost records, so
  finance stops re-keying. (Live two-way sync remains the connection framework's job.)
- **Embodied carbon (A1-A3)** — computed from `production_quantity` × a built-in EPD factor table with
  unit conversion, rolled up by material + cost code. Zero of this existed before, and it plays to our
  IFC/quantity strength as embodied-carbon reporting goes mandatory on public work.
- **Code-compliance assistant** — describe a project → applicable **IBC/ADA/IECC** sections with citations
  (Claude when keyed; a deterministic IBC checklist triggered by occupancy/area/stories otherwise).
- **Takeoff pricing** — reconcile the takeoff to a built-in unit price book (+ a `pricing_bridge` stub for
  a live supplier/RSMeans feed) with **variance vs the estimate**.
- **UI:** a **🛡 Risk & Cost** portal panel (prequal scores, COI expiry, lien exposure, carbon, priced-
  takeoff variance, GL/IIF export) and a **Code check** tab in AI Assist.
- Verified: 92/92 backend suites, web typecheck + 49 vitest + Pages build + bundle budget all green.

## v0.3.41 — Tier 1: AI drafting, bid leveling, cross-project benchmarking
Market-driven upgrades. Each AI engine mirrors the existing
`review.py`: Claude when `ANTHROPIC_API_KEY` is set, a deterministic **offline fallback** otherwise,
every output **source-linked**, never fabricated; heavy calls run off the event loop and are throttled.
- **AI drafting** (`drafting.py`, **AI Assist** panel) — turn a note or a PDF into an editable
  first-draft **RFI**, **submittal summary**, or trade **scope of work** with page citations, so teams
  stop retyping from documents (the report's "18% of project time is spent searching for data").
  Human-in-the-loop: nothing is created until you click **Create**.
- **Bid leveling** (`bid_leveling.py`) — level a package's `bid_submission` records into an
  apples-to-apples grid: base-bid stats + >25% **outlier** flags, a **scope matrix** (who includes/
  excludes each item), **scope-gap** detection, and a **scope-adjusted low** recommendation (a low bid
  missing scope others carry is flagged). Optional AI canonicalizes free-text scope phrases.
  `GET /projects/{pid}/bids/leveling/{package_rid}`; shown as a grid in the AI Assist panel.
- **Cross-project benchmarking** (`benchmarking.py`, **Benchmarks** panel) — your own history across
  every project: actual **cost distribution** (low/p25/median/p75/high) per cost code, and RFI/submittal
  **turnaround + overdue %** (ball-in-court accountability). Answers the survey's "76% aren't realizing
  their data's potential." `GET /benchmarks/costs`, `/benchmarks/response-rates`.
- **Test-gate fix:** `run_tests.py` used a hardcoded list that silently skipped 12 on-disk suites
  (this session's throttle/route-order/module-schema/interop + pre-existing review/gbxml/analytics/
  discipline/module-config). All are now wired in — the gate runs **86 suites** (was counting 74).
- Verified: 86/86 backend suites, web typecheck + 49 vitest + Pages build + bundle budget all green.

## v0.3.40 — P2: Pydantic module-schema layer (single source of truth for module.json)
- **`module_schema.py`** — a Pydantic `ModuleSchema`/`FieldDef`/`Workflow`/`Transition` layer that
  formalizes what a valid `module.json` is. The config test and the runtime loader now validate against
  the *same* definition: `test_module_config` asserts every shipped module passes it (authoritative,
  fails the build); `load_registry` runs it at startup and logs a warning for a malformed module rather
  than crashing (advisory). New `test_module_schema` proves the layer catches each misconfig class
  (dup fields, unknown types, select-without-options, bad reference target, bad title_field /
  list_column / workflow state / transition / requires) and stays quiet on valid input.
- **Record value validation** (`validate_record`) at create/update: rejects a non-numeric value in a
  numeric field (`number`/`currency`/`percent`) with a 422 before it can land in the JSON `data` blob.
  Select `options` are treated as *suggestions*, not a closed enum (the system routinely stores
  free-form values a picklist didn't anticipate), so membership is deliberately not enforced.
- Fixed the `party` transition key to accept a bare string as well as a list (matches
  `rbac.party_allowed`), and corrected the module-authoring guide's workflow example (`action`, not
  `label`; `party`; convention-based due dates; derived terminal states).

## v0.3.39 — P1: don't block the event loop on heavy IFC/convert/AI work
- **Async offload of blocking work** (P1 from the review). Several `async` endpoints ran CPU/network-
  bound work directly on the event loop, stalling *every* other request on that worker for its whole
  duration. Each now runs in a threadpool (`run_in_threadpool`):
  - `POST …/validate` — `ifcopenshell.open` + IDS validation (seconds+).
  - `POST /convert` — the APS RVT→IFC `subprocess.run` (up to a 30-minute block!) and the E57
    point-cloud decode.
  - `POST /convert/citygml` — CityGML XML parse.
  - `POST …/review/{contract,scope,ask}` — server-side PDF text extraction and the LLM calls.
- **Model load progress** was already real (streamed % + MB with a graceful fallback when the server
  sends no `Content-Length`) — verified, no change needed.

## v0.3.38 — P0 hardening: SQL aggregates, SSRF guard, per-endpoint throttle, bounded property cache
Quick, safe, high-value fixes from the code/UX/perf/security review (Cesium globe deferred — the
recommendation is to adopt the OGC **3D Tiles** format into the existing three.js viewer if geospatial
demand arises, not build a bespoke globe).
- **Performance — SQL aggregates over full-table Python scans.** `due_feed` now filters unfinished,
  soon-due records in SQL (JSON due-date `< horizon` + state `not in` terminal) instead of loading
  every module row + JSON blob; `project_pins` prunes un-anchored rows in SQL; the construction
  **portfolio** dashboard loads only open/mitigating risks and counts open RFIs with a SQL `COUNT`
  rather than three `limit=1_000_000` full scans per project. (`my_work` was already SQL-filtered.)
- **Security — SSRF guard on the admin-settable Speckle URL.** The Speckle server URL comes from the
  Settings UI (untrusted), so `speckle_bridge` now requires `https://` and refuses hosts that resolve
  to private / loopback / link-local / cloud-metadata addresses before any request — closing an
  internal-network / metadata-probe vector. A self-hosted LAN server can opt back in with
  `SPECKLE_ALLOW_PRIVATE=1`.
- **Security — per-endpoint rate limiting for expensive ops** (`throttle.py`). The AI **review**
  endpoints (LLM per call) and the **convert** endpoints (subprocess / paid APS cloud translation)
  now get an always-on per-caller cap independent of the opt-in global limiter; tune or disable per
  bucket via `AEC_THROTTLE_<BUCKET>_RPM`. The "Test connection" AI probe is bounded to a 10s timeout
  with no retries so it can't hang a worker.
- **Perf/memory — bounded property cache.** The in-process element index (`properties.py`) is now an
  LRU capped at ~16 projects/worker (`AEC_PROPS_CACHE_PROJECTS`); evicted projects reload transparently
  from storage — a busy worker no longer holds every project's full element list forever.
- **UX — discoverable command palette.** Added a visible **🔍 Search ⌘K** button in the header so the
  palette isn't hidden behind a keyboard shortcut. Backend suite + web typecheck green.

## v0.3.37 — Design tokens: theme-aware modal error text
- Modal/error message colors across the Account, Connections, and Settings dialogs now use the
  theme-aware **`--err`** token instead of a hardcoded red, so they read correctly in light mode too
  (completing the v0.3.23 status-token pass). The remaining literal colors are intentionally raw:
  canvas drawing colors (takeoff/markup — canvas can't read CSS variables) and already-tokenized
  `var(--status-*, #fallback)` uses. Web typecheck + production build clean.

## v0.3.36 — Module-config validator + forms/CRUD audit
- **Forms/CRUD audit** across all 85 modules — found + fixed a broken list view: `asset_register`
  listed a `warranty_expiry` column that didn't exist (the field is `warranty_expires`).
- **`test_module_config.py`** now validates every `modules/*/module.json` on each test run and fails the
  build on: duplicate field names, `reference` fields with a missing/non-existent target module,
  `select`/`multiselect` with no options, unknown field types, `title_field` or `list_columns` pointing
  at non-existent fields, and workflow `initial`/transition states or `requires` that reference
  unknown states/fields. Prevents the whole class of config-driven-CRUD misconfig going forward.

## v0.3.35 — Frontend load speed: code-split the secondary workspaces
- **~24% smaller initial shell** — the **Finance (proforma)** and **Drawings** panels are now
  code-split and load on first open instead of shipping in the startup bundle. Initial `index` chunk
  **646 kB → 535 kB (139 → 106 kB gzip)**; proforma (77 kB) + drawings (8.8 kB) are separate chunks.
  The default **Construction/Developer** portal stays eager; the 3D viewer engine (@thatopen, ~6 MB)
  and **Studio** were already lazy. Verified live: Finance + Drawings load on first switch with no
  errors; web typecheck + production build clean.

## v0.3.34 — Security hardening: gate the conversion + interop endpoints
- **Auth gap closed.** `POST /convert` (RVT/DWG/NWC bridge) and `POST /convert/citygml` were reachable
  anonymously — they now require an authenticated identity (`current_user`), and `/convert` + `/interop`
  were added to the RBAC middleware's protected-prefix list (defense-in-depth when `AEC_RBAC=1`).
  Combined with the earlier defusedxml + body-cap hardening, the CityGML endpoint is now auth-gated,
  XXE-safe, and size-bounded.
- Web dependency audit clean (`npm audit --omit=dev`: 0 vulnerabilities); Python dep scan runs in CI.

## v0.3.33 — Discipline quantities: rebar tonnage + MEP runs (C)
- **🔩 Discipline quantities** in the viewer's Exports — a quantity roll-up straight from the IFC:
  **reinforcement tonnage** (from `NetWeight`, or estimated from volume × steel density when bars
  aren't weighed), **MEP linear runs** (duct / pipe / cable metres + segment & fitting counts), and
  **structural element volume**. Backs the rebar-viz / MEP-takeoff use case (Koh · WithRebar).
- New `aec_data.qto.discipline_summary` (reuses the QTO quantity reader + geometry fallback) +
  endpoint `GET /projects/{pid}/quantities/disciplines`. `test_discipline.py` covers weights (modelled
  vs volume-estimated), MEP runs, and structural volume; verified live against a real IFC. Typecheck clean.

## v0.3.32 — gbXML energy-model export (B4)
- **↓ gbXML (energy model)** in the viewer's Exports — exports the model to **Green Building XML** for
  OpenStudio / EnergyPlus / IES / DesignBuilder. Spaces carry **area + volume + occupancy from the real
  IFC geometry**, plus building-level **exterior envelope** surfaces (wall + window opening / roof /
  ground slab) with areas from geometry. Valid gbXML 6.01.
  - Honest scope: a **simplified early-design (shoebox) model** — building-level envelope, not a full
    per-space surface-boundary thermal model (that needs IfcRelSpaceBoundary geometry). It seeds an
    energy tool with the spaces/areas/volumes rather than replacing detailed energy modelling.
  - New `aec_data/gbxml.py` (reuses the space schedule + envelope-area extractors) + endpoint
    `GET /projects/{pid}/exports/model.gbxml`. `test_gbxml.py` validates the structure; verified live
    against a real IFC (72 spaces). Web typecheck clean.

## v0.3.31 — Settings: "Test connection" per integration
- Every integration in **Settings ▸ Integrations & API keys** gets a **Test** button with instant
  ✓/✗ + message, so a non-technical admin knows a key actually works before relying on it:
  - **AI** — validates the Anthropic key with a 1-token call.
  - **Email** — connects + STARTTLS + login (no send).
  - **Speckle** — live GraphQL `serverInfo` connectivity check.
  - **Autodesk APS** — 2-legged OAuth (validates client id/secret).
  - **SSO** — confirms client id/secret are present (full sign-in still completes from the login page).
  - **Licence** — key-format check.
- New `conntest.py` dispatcher + `POST /settings/integrations/test` (admin-only). `test_interop.py`
  covers the dispatcher; suite + web typecheck green.

## v0.3.30 — Settings: add all API keys in the UI (no code/env editing)
- **Speckle** and **Autodesk APS** are now in the **Settings ▸ Integrations & API keys** panel, joining
  AI (Anthropic), Email (SMTP), SSO (Google / Microsoft / Procore), and licensing. A non-technical
  admin pastes keys and hits **Save** — no editing `.env` files or code. Secrets stay **write-only**
  (the catalog reports only whether a key is configured, never the value).
- The Speckle and APS bridges now read config via the settings store (DB-saved UI value wins, else the
  env var), so keys entered in the app take effect immediately — same pattern as the AI key.
- Clarified the admin hint: "add API keys here — no code or config files to edit."
- `test_interop.py` asserts the catalog exposes Speckle/APS with write-only secrets; suite + typecheck green.

## v0.3.29 — Federation alignment report + security hardening
- **Model alignment check** (Coordination) — a lightweight companion to federated clash: do a
  project's discipline models share the same **storey scheme** and **georeferenced origin**? Reads each
  model's storey elevations + IfcMapConversion and flags mismatched storey counts/elevations (different
  datums) and survey-origin offsets — the #1 coordination problem. New endpoint
  `/projects/{pid}/models/alignment` + a "📐 Alignment check" viewer action beside Federated clash.
- **Security hardening** of this session's new upload/parse surfaces:
  - CityGML parsing now uses **defusedxml** → XXE / billion-laughs / external-entity bombs are
    rejected (`EntitiesForbidden`) instead of expanding, so a tiny malicious file can't exhaust memory.
  - The contract/spec review engine caps analysed text (~800k chars) so a huge PDF can't drive the
    regex scan unbounded (the global 1 GB body cap still applies to the upload itself).
  - `pypdf` + `defusedxml` pinned in `requirements.txt`.
- `test_interop.py` extended (XXE bomb → 422, alignment → 409); backend suite + web typecheck green.

## v0.3.28 — Interoperability: Speckle bridge + CityGML site-context import
- **Speckle bridge** (Interoperability) — optional, open-source & self-hostable data exchange with the
  wider AEC ecosystem (Rhino/Grasshopper, Revit, Blender, web). Off unless `SPECKLE_SERVER` +
  `SPECKLE_TOKEN` are set; when on, `status()` verifies live connectivity (GraphQL `serverInfo`).
  IFC/Fragments stay the source of truth. Endpoints `/interop/speckle/status` + `…/send` (the chunked
  object upload runs in your credentialed deployment — it never fabricates a commit).
- **CityGML → GeoJSON site context** (GIS & Site) — import CityGML (the OGC standard behind the 3D City
  Database / Cesium city tiles) via **Open mesh / point cloud / GIS…**; the server extracts building
  footprints (with heights) → GeoJSON that renders in the existing GIS reference layer. Namespace-
  agnostic (CityGML 1.0–3.0), fully offline. Endpoint `/convert/citygml`; `.gml/.citygml` accepted.
- `test_interop.py` (Speckle gating + CityGML parse/422) green; web typecheck clean.

## v0.3.27 — Code-readiness check (Safety & Compliance)
- **🏛 Code-readiness check** in the viewer — does the model carry the *data* a plan review needs?
  A property-level rule engine (not a certified geometric code review) checks: egress door width
  recorded (≥ 0.813 m, IBC 1010.1.1), fire rating on walls (IBC Table 601/602), spaces carry floor
  area (IBC 1004.5) + occupancy classification (IBC 1004), egress stairs modelled (IBC 1011), and
  elements typed/classified. Returns a readiness %, a per-rule table with code references, and a
  one-click **3D highlight of the elements to review**. New endpoint `/elements/code-check`.
- Extends the v0.3.25 Data-QA into rule-based checks (Kestrel-style). Rules target IFC classes,
  try several attribute/pset keys, and check presence or a numeric minimum. `test_analytics.py`
  covers it; web typecheck clean.

## v0.3.26 — Preconstruction intelligence: contract risk review + scope-gap + doc Q&A
- **Risk Review** (new Construction-workspace destination — preconstruction intelligence, inspired by
  the AI pre-con review category). Upload a contract/spec PDF (or paste text) and:
  - **Contract risk review** — flags risky clauses by severity (high/med/low) with rationale + a
    suggested redline: pay-if-paid, no-damage-for-delay, broad indemnity, termination-for-convenience,
    sole discretion, lien waivers, LDs, backcharges, retainage, etc. One click adds a finding to the
    **Risk Register**.
  - **Scope-gap detection** — surfaces ambiguous/missing scope in specs & drawing notes ("by others",
    "N.I.C.", "TBD", "as required", "or equal", "match existing"…).
  - **Ask a document** — answers a question grounded in the uploaded doc with **page citations**.
  - New `review.py` engine + `/projects/{pid}/review/{contract,scope,ask}` endpoints. Uses Claude when
    an Anthropic key is set; otherwise a **deterministic clause/marker library** so it works fully
    offline and never fabricates (only flags language actually present).
- **Risk register depth** — the `risk` module gains **response strategy** (Avoid/Transfer/Mitigate/
  Accept), **trigger / warning signs**, and **contingency (Plan B)** to match risk-register best practice.
- Backend suite green (+ test_review, test_analytics); web typecheck clean.

## v0.3.25 — Thematic "Color by property" + BIM data-QA (built-world analytics)
- **Color by any property.** Generalized the 5D heatmaps into a thematic override: pick any IFC
  attribute (class, storey, type, name) or pset/qto property and the model recolours by value —
  numeric ranges get a blue→red ramp, categorical values distinct hues, with a live legend and an
  "N unset" count. New endpoints `GET /projects/{pid}/elements/facets-list` (the picker) and
  `…/color-by?prop=` (server-side bucketing over the property index — scales to large models).
- **BIM data-QA (completeness).** A validation pass over the property index: for each element,
  which required (Name / IFC class / Storey) and recommended (Type / property sets) attributes are
  present vs missing → a headline compliance %, a per-rule table, a one-click **3D highlight of the
  non-compliant elements**, and a CSV export. Endpoint `GET /projects/{pid}/elements/qa`.
- Inspired by computational-AEC data-viz/asset-data workflows; both reuse the existing viewer
  colorize/selection plumbing. Backend 75/75 + web typecheck green.

## v0.3.24 — Construction ↔ Developer split + role-geared dashboards
- **Workspace split.** The oversized single "Construction" portal is now two role-scoped workspaces
  driven by a new `workspace` tag on every `module.json`: **Construction** (the GC build lifecycle —
  Engineering, Preconstruction, Field, Cost, Change Management, Quality, Contracts, Safety, Closeout,
  BIM, Schedule, Resources, Sustainability) and **Developer** (real estate — **Feasibility** `zoning`,
  **Market & Sales** `comparable`/`listing`, **Capital** `investor`, **Operations** `lease`, plus the
  proforma via a one-click **Underwriting →**). A **Show all modules** toggle keeps every register one
  click away for every role — everyone still has access to all data.
- **Role-geared dashboards.** The Developer workspace opens on a real-estate command center (deal
  returns · listings · comps · capital · leases · feasibility) instead of the GC KPIs. The GC
  dashboard now orders its KPI cards by role: the **superintendent** leads with the field
  (punchlist/safety/quality), the **project manager** with controls (RFIs/COs/overdue). Same cards,
  role-appropriate emphasis.
- **Top header.** The role picker is now labeled **👤 Viewing as** and grouped by function
  (Real estate · Construction office · Construction field · Design), set off with a divider.
- **Deeper registers.** `comparable` rebuilt into a full appraisal-grade sales/rent comparison grid
  (comp type, $/unit, NOI, GBA, units, land area, year built, occupancy, condition, distance to
  subject, net adjustment, adjusted price, source + a recorded→verified→excluded workflow);
  `investor` gains ownership %, preferred return %, and commit date. Backend 74/74 + web typecheck green.

## v0.3.23 — Design tokens: theme-aware status colors
- Extracted the hardcoded traffic-light status colors (green/amber/red — 43 occurrences across the
  portal dashboard + proforma) into CSS variables (`--status-good/warn/crit`, `--err`) defined for
  both dark and light themes. Previously the dark-mode hexes bled into light mode; now status colors
  adapt to the theme and there's a single place to tune them. Web typecheck + 49 tests green.

## v0.3.22 — Speed: rollup fields filter in SQL (no more full-table scan per read)
- **Rollup fields** (e.g. a cost code's committed/budgeted/direct totals, a COR's PCO sum) previously
  loaded *every* source-module record for the project and matched the reference in Python on each
  `get_record` — O(N) per rollup, amplified by rollup-heavy dashboards. Now the reference match runs
  **in SQL** via portable JSON extraction (Postgres `->>` / SQLite `json_extract`), so only the
  matching rows are fetched. Same values, far less data scanned/shipped as record counts grow.
  Backend 74/74 (rollup-exercising tests unchanged).

## v0.3.21 — Forms/CRUD accuracy pass (field types, required flags, itemized costs)
- Audited all ~80 module forms against construction best practice and fixed the concrete, verified
  issues:
  - **Currency types**: material/equipment/labor unit rates and `budget.budget` / `budget.forecast`
    were plain numbers — now `currency` (proper `$` formatting, consistent with the rest of the budget).
  - **Required flags** where the field is genuinely mandatory: `submittal.type`,
    `inspection.inspection_type`, `ncr.disposition` — the form now blocks submit + the API validates.
  - **Itemized change-order cost breakdown**: `cor` gains Labor / Material / Equipment / Overhead &
    profit currency fields backing the total (standard COR format).
  - **Process fields**: `permit.applied_date` (processing time), `incident.reported_date` (OSHA
    reporting window), `daily_report.crew_by_trade` (manpower breakdown).
- Demo seed + test updated to supply the newly-required fields. Backend 74/74; web typecheck + 49
  tests green. (Riskier dedup/reference-type findings from the audit are deferred pending consumer
  analysis.)

## v0.3.20 — Command palette (⌘K / Ctrl-K)
- A global **command palette** (Cmd/Ctrl-K from anywhere) — the fast way to reach any workspace,
  module, action, or record without hunting through menus. Fuzzy-ranked, keyboard-first (↑/↓, Enter,
  Esc), with live **record search** (matches ref/title/data via the search endpoint) appended as you
  type. Commands cover the 5 workspaces, shell actions (new project, open IFC/mesh, Report Center,
  save, help), and every construction module (jump straight to its register). First of the Tier-1
  UX-2.0 upgrades from the audit; new `ui/palette.ts` + `PortalUI` open-by-key/record hooks.
- Verified live: opens on Ctrl-K, "fin"→Finance ranks first, Enter navigates; no console errors.
  Web typecheck + 49 tests green.

## v0.3.19 — Fix: attachment images / thumbnails not loading (route collision + COEP/CORP)
- **Portal record images now load.** Three compounding bugs, found by driving the app + reading
  network traces:
  1. **Route collision** — bim.py's `GET /attachments/{id}/download` (the `Attachment` table,
     registered first) shadowed the module-record handler (`RecordAttachment` table), so every
     module attachment 404'd. Moved module attachments to a distinct `/module-attachments/{id}/download`.
  2. **Bad auth gate** — that handler used `require_role("viewer")`, which reads the project id from
     the path; with no `pid` in the path FastAPI demanded it as a query param → 422. Now authenticated
     like bim's download: `current_user` + the attachment's own project (+ signed-URL support).
  3. **COEP blocked the `<img>`** — the SPA is cross-origin isolated (`require-corp`, for the viewer's
     SharedArrayBuffer WASM), which blocks cross-origin image subresources without a
     `Cross-Origin-Resource-Policy` header. Added `CORP: cross-origin` to the module-attachment
     download and to `range_response` (so BIM/topic attachments **and** `model.frag` embed cross-origin too).
- Verified live: an uploaded photo renders on the record (decodes, `naturalWidth>0`, no COEP block).
  Backend 74/74 (new `test_attachments`: distinct path 200 + bytes + `inline` + CORP; old path 404s);
  web typecheck + 49 tests green.

## v0.3.18 — Security: fix stored XSS in portal record rendering
- **Stored-XSS fix (high severity)**: record list cells, the record-detail title/fields, the
  cross-module search results, action-item / due / notification feeds, and the portfolio table all
  rendered user-entered values (titles, field data, project names) via `innerHTML` without escaping —
  a malicious record title like `<img src=x onerror=…>` executed for every user who viewed it. List
  cells now use `textContent`; every remaining `innerHTML` interpolation of record/user data is passed
  through `escapeHtml()`. Verified live: a hostile-title RFI renders as literal text on both the list
  and detail pages, injects no elements, and does not execute. (Found in a full-codebase UI/UX audit.)
- Web typecheck + 49 tests green.

## v0.3.17 — Saved-search alerts + Postgres full-text search
- **Saved-search alerts**: every saved view now tracks a `last_seen_at`, and the portal home shows a
  **🔔 Saved searches with new matches** band — each saved view with its **new-since-you-last-opened**
  count (a never-opened view counts all matches as new). Click a chip to open that filtered list; it
  clears the count. New `GET /projects/{pid}/views/alerts` + `POST …/views/{vid}/seen` + a
  `count_records` engine helper. Opening a view from the dropdown also marks it seen.
- **Postgres full-text search**: cross-module + in-module search is now **dialect-aware** — on Postgres
  it uses `to_tsvector` + a safe **prefix `to_tsquery`** (`conc beam` → `conc:* & beam:*`, so partial
  words and multi-term queries match) ranked by **`ts_rank`**; SQLite (dev) keeps the substring-LIKE
  fallback. No new service (per the earlier no-Elasticsearch decision) and no schema change — the FTS
  is a query-time expression. (For very large prod tables, a GIN index on the tsvector is the natural
  follow-up.)
- Additive migration adds `saved_views.last_seen_at` on startup (nullable ADD COLUMN). Backend 73/73
  (new `test_search_alerts`: alert lifecycle + prefix-tsquery builder + SQLite search); Postgres FTS
  SQL compile-verified (`to_tsvector @@ to_tsquery` + `ts_rank`); web typecheck + 49 tests green.

## v0.3.16 — Bulk-action pickers replace raw prompts (data-entry polish)
- The list bulk-action bar no longer uses `prompt()` for **Assign** / **Transition**: Transition is
  now a dropdown of the module's valid workflow actions + Apply, and Assign is an inline input + Apply
  (Delete stays behind a confirm). Faster, less error-prone bulk edits on a selection — the last
  rough edge from the CRUD/UX audit. Web typecheck + 49 tests green.

## v0.3.15 — Paginated module lists (large registers stay snappy)
- Module list views now **page** the records (100/page) with **‹ Prev / Next ›** controls and a
  position indicator, instead of fetching and rendering every record at once. A register with
  thousands of RFIs/issues/cost codes no longer stalls the browser on open; filter/search/state
  changes reset to the first page. Uses the list endpoint's existing `limit`/`offset` (fetches one
  extra row to detect "more"), so no API change — the pager only appears when the list spills past a
  page. Completes the data-entry UX upgrade set (import → validation → search → pagination).
- Backend 72/72 (limit/offset assertions added); web typecheck + 49 tests green.

## v0.3.14 — Data-entry UX upgrade Phases 2–4: form validation, searchable pickers, faster search
- **Form validation (buy-in + clean data)**: create/edit forms now enforce **required fields
  client-side** — offending inputs get outlined, the first is focused, and submit is blocked with a
  clear "Please fill required field(s): …" message instead of a silent server 422. If the server does
  reject (`missing required field(s): …`), the exact fields are parsed out and highlighted; the form
  keeps all entered values.
- **Searchable reference picker (ties everything together at scale)**: a reference field with more
  than 8 options gets a type-to-filter box, so picking e.g. a cost code stays fast when a project has
  hundreds — the "＋ Add new" inline-create still works.
- **Server-side search (easy to access, scalable — no Elasticsearch)**: the module list/search `q`
  filter now runs in **SQL** (`ref`/`title`/`data`-as-text `LIKE`, applied before `LIMIT`) instead of
  loading a page of rows and scanning JSON in Python — so a search returns the right matches across the
  whole module, not just those on the first page, and scales. Portable across SQLite (dev) and
  Postgres (prod); the JSONB/`tsvector` + GIN upgrade is a clean future step on the same query.
- Backend 72/72 (search assertions added to `test_imports`); web typecheck + 49 tests + Pages build green.

## v0.3.13 — Generic Excel / CSV import for any module (Phase 1 of the data-entry UX upgrade)
- **The #1 data-entry / adoption lever**: every module now has an **⤓ Import** button that bulk-loads
  records from an Excel (.xlsx) or CSV file. New `imports.py` + endpoints
  (`/modules/{key}/import/preview`, `/modules/{key}/import`, `/modules/{key}/import-template.csv`).
- **Two-step, mapping-driven UX**: pick a file → the server sniffs the header row and **auto-maps
  columns to fields** by name/label → a mapping screen lets you adjust each column (or skip), warns
  about unmapped required fields, and shows a sample → import. Type coercion (currency `$1,250` →
  1250.5, dates → ISO, multi-select split); rollup/computed fields excluded. A **blank template**
  download seeds the right headers.
- **Robust + safe**: required-field validation per row (a bad row is reported, never aborts the
  batch), 10k-row import cap, editor-gated + audit-logged. Answers "how do I create a new cost code" —
  the ＋ New form, the inline "＋ Add new" on a reference field, or now a spreadsheet import.
- Verified live: 3 cost codes imported from a CSV via the mapping UI, no console errors. Backend
  72/72 (new `test_imports`); web typecheck + 49 tests green.
- Decision (researched): **no Elasticsearch** — a self-hosted/offline app on Postgres should use
  built-in full-text search; a portable search upgrade lands in a follow-up phase.

## v0.3.12 — UI/UX + security pass over recently-added features
- Consolidated review of four features (site feasibility, feasibility scenario compare, clash-report
  import, BCF viewpoint fidelity).
- **Security**: hardened the clash-report XLSX import against oversized sheets — caps imported issues
  at 5,000 rows and scanned rows at 200,000 (surfacing a `truncated` flag), on top of the existing
  request body-size limit; `read_only` streaming keeps memory bounded. Audited RBAC on every new
  endpoint (feasibility / compare → viewer; clash import → editor + audit log) and confirmed the BCF
  XML parse path uses stdlib ElementTree (no external-entity expansion → not XXE-exploitable).
- **UI/UX**: verified all three new Report-Center tool launchers render and function live against a
  real backend (feasibility envelope, scenario ranking with deltas, clash-report file import), with
  graceful empty states and no console errors.

## v0.3.11 — BCF viewpoint fidelity: orthographic cameras + per-element coloring
- BCF viewpoints now round-trip the **full camera**, not just the view point: camera direction
  (derived from position→target when absent), up-vector, and field-of-view for perspective — plus
  **OrthogonalCamera** (view point + direction + up + view-to-world-scale) so section/elevation
  viewpoints from Solibri / ACC / BIMcollab survive the round-trip instead of collapsing to a bare
  point. Shared helpers (`_camera_xml`/`_parse_camera`) used across every export/import path.
- **Per-element coloring** in viewpoints (`<Coloring><Color><Component/>`) now exports and imports —
  the "the clashing beam is red" emphasis state carries through BCF. Imported viewpoints (incl.
  orthographic + coloured) are re-materialised as `Viewpoint` rows, not just the pin anchor.
- Viewer `captureViewpoint()` now records the projection (perspective/orthographic) + FOV, and
  `jumpToViewpoint()` restores the projection — shared/presence and saved views recreate the actual
  camera. Closes the fidelity gap flagged in the arsray146/ifc-bcf-viewer review.
- Backend 71/71 (BCF test extended with perspective + orthographic + coloring round-trips and an
  end-to-end orthographic-camera import); web typecheck + 49 tests green.

## v0.3.10 — Feasibility scenario comparison (test schemes side by side)
- **New `GET /projects/{pid}/feasibility/compare`** + `feasibility.compare()`: rank every zoning
  scheme (one `zoning` record = one scheme, e.g. "Scheme A · FAR 6" vs "Scheme B · FAR 8") by
  buildable yield — units then GFA — with the binding constraint and Δ-units / Δ-GFA vs. the top
  scheme. The Giraffe-style "test 20 scenarios in the time others analyze one," on the feasibility
  engine shipped in v0.3.8.
- `api.feasibilityCompare()` client + a "▟ Compare feasibility scenarios" tool launcher.
- Backend 71/71; web typecheck + 49 tests green.

## v0.3.9 — Import Solibri / Navisworks clash reports (XLSX → coordination issues)
- **New `clash_import.py` + `POST /projects/{pid}/coordination/import-xlsx`**: drop in a Solibri or
  Navisworks (or any tabular) clash/coordination report `.xlsx` and each row becomes a tracked
  **coordination issue** — which already round-trips to BCF and drops a model pin. GCs receive these
  reports constantly from the BIM coordinator; this turns the spreadsheet into model-anchored issues
  with no re-keying.
- Tolerant parser: sniffs the header row (skips title/preamble rows), maps a wide set of column
  aliases (Solibri Name/Description/Severity/Ruleset/Component-GUID/Location; Navisworks
  Clash-Name/Status/Grid-Location/Item 1/Item 2) by best whole-word match, maps severity → priority
  (Critical/High/Medium/Low), and extracts IFC GlobalIds from one or more component columns into
  `element_guids` so issues anchor on the model.
- `api.importClashXlsx()` client + an "⤓ Import clash report" tool launcher. Inspired by the
  arsray146/ifc-bcf-viewer + addd.io reviews (Solibri/QA-report ingest).
- Backend 71/71; web typecheck + 49 tests green.

## v0.3.8 — Site feasibility / zoning envelope (Giraffe-style) + live-demo fix
- **Fixed the broken live demo**: `massing.build/app/` was 404'ing — GitHub Pages had been switched to
  the legacy branch source (`/docs`), which serves the landing page but not the viewer and conflicts
  with the `pages.yml` Actions deploy. Restored Pages to the "GitHub Actions" source so `/app/`
  deploys again; regenerated the demo snapshot.
- **New `zoning` module + `feasibility.py` engine + `GET /projects/{pid}/feasibility`**: a site
  feasibility / zoning-envelope study (the "Massing" feasibility tool, inspired by Giraffe). From site
  area + zoning controls (FAR, height, floor-to-floor, lot coverage, setbacks, open space, parking,
  unit size) it computes the **maximum buildable GFA as the binding minimum of the FAR cap vs. the
  physical envelope** (footprint × floors), then net buildable area, **unit yield**, parking demand and
  required open space — and **reconciles allowed GFA against the model's actual GFA** (FAR used,
  % of allowed, headroom, over/under) when a source IFC is present.
- New **Site Feasibility / Zoning Envelope** report (Report Center) + a "▟ Site feasibility" tool
  launcher + `api.feasibility()` client method. Demo seeds a zoning record so it's demonstrable.
- Reviewed giraffe.build, synaps.app, addd.io and arsray146/ifc-bcf-viewer; most of their AEC
  capabilities are already covered (clash/BCF, IFC takeoff, dashboards, ask-the-model, reports). Site
  feasibility was the clearest on-brand gap; shipped first.
- Backend 70/70; web typecheck + Pages build green; demo verified live.

## v0.3.7 — Specifications → submittals: spec register, spec-driven submittal log, AI extraction
- New `spec_section` module — the project manual / specification register (CSI MasterFormat section
  number + title, division, the Part 1 "Submittals" article text, Part 2 products, responsible party;
  issued/under-revision/void workflow).
- **Spec-driven submittal log** (`specs.py` + `GET /projects/{pid}/specs/submittal-log`): derives the
  required submittals per spec section from the SectionFormat Part 1 Submittals article (typed via a
  submittal-type classifier — Shop Drawing, Product Data, Sample, Mock-up, Certificate, Test Report,
  Calculations, O&M, Warranty), reconciles them against the submittals actually logged (matched by
  MasterFormat section number), and surfaces **missing submittals** per section with a coverage %.
- **AI/rules submittal extraction** (`ai.extract_submittals` + `POST /specs/extract-submittals`):
  paste spec text → a typed submittal list (Claude when configured, deterministic rules fallback
  offline); `create=true` logs each item as a `submittal` and records the `spec_section`, building the
  log straight from the spec book.
- New **Spec-Driven Submittal Log** report (KPIs, by-type chart, by-section table flagging gaps);
  two tool launchers (spec submittal log; extract submittals from a spec) + client methods.
- Backend 69/69; web typecheck + 49 tests + Pages build green.

## v0.3.6 — Preconstruction depth: decision log, assumptions, VE cycle + alignment dashboard
- New `decision` (cross-stakeholder decision log: rationale, alternatives, cost/schedule impact,
  Aligned/Pending/Disputed) and `assumption` (assumptions & clarifications register with allowance
  exposure) modules. `precon.py` rollups + `GET /precon/decisions` and `/precon/assumptions`:
  open counts, disputed, open cost & schedule exposure, by category.
- **VE cycle** analytics on the existing `value_engineering` module — `GET /precon/ve?target=`:
  proposed/accepted/rejected savings + gap-to-close against an over-budget target.
- **Calibrate-style alignment dashboard** — `GET /precon/alignment`: per-domain RAG (estimate vs budget,
  VE coverage of the gap, decisions, assumptions) + an alignment score. New reports: Decision Log,
  Assumptions & Clarifications, Preconstruction Alignment; tool launchers + client methods.
- Completes the preconstruction-depth parity vs Concntric (estimate continuity + decisions + assumptions
  + VE + alignment). Backend 68/68; typecheck + build green.

## v0.3.5 — Preconstruction estimate continuity (Concntric-style design-phase cost tracking)
- New `estimate_set` module (snapshot tagged by design **milestone** — Concept/SD/DD/CD/IFC/GMP/Award —
  with total, gross SF, basis, source) + `precon.py` engine + `GET /projects/{pid}/precon/estimate-continuity`:
  per-milestone **$/SF**, **milestone-to-milestone cost drift**, first→latest drift, and the **gap vs the
  project budget/GMP** (over/under). A one-click `POST /precon/snapshot?milestone=` prices the current
  model (IFC takeoff) and saves it as an estimate set.
- An **Estimate Continuity** report (PDF/Excel) + Report Center tool launcher; client `estimateContinuity`
  + `preconSnapshot`. Closes the design-phase cost-tracking gap vs Concntric, built on Massing's existing
  estimate/budget primitives. Backend 68/68.

## v0.3.4 — Optional licence enforcement (off by default)
- Licence entitlements can now be **enforced**, but it's **opt-in and OFF by default** — the app stays
  fully open and a licence is optional (no registration) until the operator sets `MASSING_LICENSE_ENFORCE=1`
  (Settings ▸ Massing licence). In open mode every `allows()/require()` gate is a no-op.
- When enabled, gates bite by tier: **IFC export** (`GET /source.ifc`) needs Commercial+ (402 otherwise),
  and **programmatic publishing via the REST API key** (e.g. the pyRevit bridge) needs Commercial+ —
  while interactive "Open IFC…" by a signed-in user stays free on any plan. `require()/require_export()`
  helpers + `_MIN_TIER` upgrade messaging; `/license` + `/capabilities` report `enforced`.
- Settings shows an **"open mode — licence optional"** status when enforcement is off (no nagging).
  Backend 67/67 (open mode grants all; enabling gates IFC/API by tier and clears on upgrade).

## v0.3.3 — Help surfaces the Revit add-in
- The in-app **"Import from Revit for free"** dialog now leads with the one-click **Massing for Revit**
  pyRevit add-in (Publish to Massing), then the free manual IFC-export path and batch pyRevit export,
  with a direct link to the add-in. The docs guide FAQ ("Do I need Revit?") lists the same three paths.
  Keeps the help current with the v0.3.2 bridge + licensing.

## v0.3.2 — Massing for Revit (free pyRevit bridge)
- New **pyRevit extension** (`integrations/pyrevit/Massing.extension`) — a free, open **Revit → Massing**
  bridge that needs no paid Autodesk APS bridge. A **Massing** tab with **Publish to Massing** (exports
  the active model to IFC via Revit's built-in exporter, uploads it, runs the server-side Fragments
  conversion, opens the web viewer), **Open in Massing**, **Sync Issues (BCF)** (RFI/clash/punch
  round-trip over BCF, keyed by IFC GlobalId), and **Settings**.
- `lib/massing_api.py` — a std-lib REST client (works on pyRevit's IronPython 2.7 + CPython 3 engines,
  no `requests`): find/create project → upload `source-ifc` → poll `publish/status` → BCF in/out.
  Covered by `test_revit_bridge.py` (67/67). Built on the LearnRevitAPI StarterKit conventions; uses
  the REST API, so it's a Commercial-plan (and up) path while manual IFC export stays free on any plan.

## v0.3.1 — Massing licensing in Settings
- New `licensing.py` engine + `GET /license`: records the workspace's **Massing licence key**
  (`MASS-XXXX-XXXX-XXXX-XXXX`) and **plan tier** (Free · Home · Commercial · Enterprise) and exposes the
  per-tier feature entitlements (export formats, REST API, SSO, Navisworks) per massing.cloud/docs.
- **Settings** gains a "Massing licence" group (paste key + set plan) and a licence-status line showing
  the active plan, masked key, what it unlocks, and a link to manage at massing.cloud. The key format is
  validated on save (malformed keys / unknown plans are rejected); the key is **masked and never echoed
  back**. `/capabilities` now reports `license_tier`. Backend 66/66.

## v0.3.0 — Massing milestone (analytics + RE/capital depth, hardened, rebranded)
First minor release on the Massing brand — marks a coherent, production-ready milestone after the
0.2.x line: the full **construction-analytics suite** (quality · RFI · submittal · T&M · field-log ·
OSHA safety · closeout) stitched into an executive **project-health rollup**; **real-estate / capital
depth** (lease management, equity-waterfall distributions, investor-portal signed statements, comps
import, WPRealWise/MLS syndication); **production hardening** (non-root API container, `/metrics`,
empty-project + malformed-input regression tests); and the **Massing rebrand** end-to-end. All verified
live in the browser. Backend 65/65; web typecheck + vitest (49) + Pages build green; `npm audit` clean.
- Polish: Excel-export buttons alongside the PDF ones on the rent-roll and cap-table Finance cards
  (backend already served `.xlsx`); optimized the social `og-image.png` (674 KB → 94 KB, palette PNG).

## v0.2.16 — Rebrand to Massing (massing.build)
- Renamed the product from "AEC BIM Platform / ModelMaker" to **Massing** across the app, docs, and
  packaging: window title + PWA name, README/CHANGELOG/SECURITY/guide/roadmap/capability-matrix, the
  Pages landing page (canonical + OG → massing.build), and backend report/branding strings.
- New brand assets — Massing isometric-massing logo + icon (`favicon.svg` / `icon.svg`, header logo,
  landing hero, `docs/img/massing-*`).
- GitHub repo renamed to **ibuilder/massing**; GitHub Pages now serves at **massing.build** (CNAME),
  with `VITE_BASE` switched to root `/app/`. Desktop bundle identifier kept (`com.ibuilder.aecbim`) so
  existing installs keep auto-updating; the updater endpoint follows the renamed repo.
- No functional change — backend 65/65, web typecheck + build green; verified live (title/header/favicon).

## v0.2.15 — Wrap-up: reachability, docs & GitHub refresh
- UI reachability audit of the whole v0.2.x arc — all new features confirmed reachable; closed the one
  gap by folding the **T&M-by-change-event** breakdown into the T&M rollup tool (was PDF-only).
- Docs refreshed to current: README "Recent platform work" now leads with the construction-analytics
  suite + RE/capital depth + production hardening; `SECURITY.md` documents the second signed-anonymous
  surface (investor `statement.public.pdf`) and the non-root API container; GitHub About updated.
- Verified green: backend 65/65, web typecheck + vitest (49) + Pages build, `npm audit` 0 vulnerabilities.

## v0.2.14 — Production hardening: non-root API container + observability test
- The API image now runs as a **non-root user** (`appuser`, uid 10001) — `/app` and the `ifc-data`
  volume path are chowned before mount so the named volume inherits writable ownership; added a
  container-level `HEALTHCHECK` for bare `docker run` (compose already health-gates the stack).
- New `test_metrics.py` (65 suites) locks the `/metrics` Prometheus surface: text exposition with
  `http_requests_total` + latency summary + in-flight gauge + uptime, counted by route template and
  incrementing across requests.
- Closes the production/ops phase — backup/restore runbook, `/metrics`, full healthchecks +
  depends-on conditions, rate-limit env knobs, and the Caddy HTTPS overlay were already in place.

## v0.2.13 — Polish & harden: empty-project robustness + a11y
- New `test_empty_project.py` (64 suites): every analytics / RE surface (14 endpoints + 13 PDF/XLSX
  reports) must return 200 with a sane zeroed structure on a brand-new project — guards the "no data
  yet" path against 500s and blank crashes.
- **Hardened** the equity-waterfall scenario: with no investors in the cap table it now returns a clean
  zeroed result + an explanatory note instead of phantom LP/GP splits; the UI surfaces the note.
- Accessibility: `aria-label`s on the new Finance inputs (capital-call amount, waterfall exit/years,
  comparables CSV textarea + file upload).

## v0.2.12 — Comparables import automation (CSV / RESO) — completes RE/capital depth
- New `comps.py` + `POST /projects/{pid}/comparables/import`: bulk-load comparables from **CSV**
  (`{csv}`) or a **RESO array** (`{reso|rows}`) into the `comparable` module, feeding the
  sales-comparison appraisal. Forgiving header mapping (case/space/underscore-insensitive; accepts
  human headers *and* RESO field names like `UnparsedAddress`/`ClosePrice`/`ClosePricePerSquareFoot`);
  coerces `$1,250,000`/`5.5%`; rows without an address are skipped.
- Appraisal tab: an **Import comparables** card (paste CSV or upload a file → recomputes the sales
  approach); client `importComparables`. Backend 63/63.
- **Milestone:** completes the real-estate / capital depth phase (syndication bridge, lease management,
  equity-waterfall scenarios, investor-portal sharing, comps import). Next: polish & harden, then production/ops.

## v0.2.11 — Investor-portal document sharing (signed statement links)
- `POST /projects/{pid}/investors/{iid}/share` mints a signed, expiring (default 30-day) link to an
  investor's capital-account statement, and `GET …/statement.public.pdf` serves it behind HMAC sig
  verification — the investor opens their statement with **no login** (the private analog of the public
  listing). Forged/absent signatures → 403; reuses `signing.py`, so the RBAC posture is unchanged.
- Finance ▸ Investors: a **🔗** button per cap-table row mints the link and shows a QR/share modal;
  client `shareInvestorStatement`. Backend 63/63 (signed link passes, forged/absent → 403).

## v0.2.10 — Equity-waterfall distribution scenarios (cap-table-tied)
- New `distwaterfall.py` + `POST /projects/{pid}/waterfall`: model a distribution / exit through the
  equity waterfall (preferred return → return of capital → IRR-hurdle **promote tiers**, reusing the
  proforma `run_waterfall`), then **allocate each side's take pro-rata across the actual investor
  records** by commitment. Body: `{exit_amount, contribution_date, exit_date}` or `{distributable[],
  dates[]}`; pref/tiers/style default from the latest proforma scenario, overridable. Returns LP/GP
  totals, IRR & equity multiple, period splits, and the per-investor allocation.
- Finance ▸ Investors gains a **Distribution waterfall (scenario)** card (exit $ + years → LP/GP +
  per-investor); client `waterfallScenario`. Backend 63/63 (waterfall clears to the exit, GP earns
  promote, LP split 2:1 by commitment).

## v0.2.9 — Lease-management depth (renewals · escalations · CAM recovery)
- New `leasemgmt.py` + `GET /projects/{pid}/leases/management`: the **renewal/expiration pipeline**
  (leases expiring ≤90/180/365 days, holdover, options outstanding, rent-at-risk), a forward
  **rent-escalation schedule** (each active lease compounded by its `escalation_pct`, plus the
  portfolio base-rent curve by year), and **CAM / expense-recovery reconciliation** (recoverable
  income = `recovery_psf × rentable_sf` for NNN/recovery leases; pass `?recoverable_opex=` for the
  recovery ratio + over/under-recovery gap).
- A **Lease Management** report (PDF/Excel) + a lease-management card under Finance ▸ Operations
  (expiry buckets, escalation step, CAM recovery); client `leaseManagement`. Backend 63/63.

## v0.2.8 — Real-estate Phase 4: WPRealWise / MLS listing syndication + marketing flyer
- New `re_bridge.py` — a feature-flagged outbound syndication bridge (off unless `REALWISE_URL` +
  `REALWISE_API_KEY` set), mirroring the APS / e-sign bridges. `GET /re-syndication/status` reports
  config; `POST /projects/{pid}/listings/{lid}/syndicate` serializes the listing via `marketing.to_reso()`
  and **upserts it into WPRealWise** (`/wp-json/realwise/v1/listings`, Bearer auth, keyed by `ListingKey`
  so re-pushes update not duplicate). Unconfigured → actionable 422; the RESO export endpoint still works.
- Disposition tab gains **⤴ Syndicate to WPRealWise** (bridge-aware) and a **Marketing Flyer** report
  (`marketing_flyer`, PDF/Excel) alongside the fact sheet. Client `reSyndicationStatus` + `syndicateListing`.
- This completes Phase 4 of docs/realestate-marketing.md (the only deferred real-estate item). `.env.example`
  documents the bridge. Backend 63/63 (test_marketing extended: gate-off 422 + stubbed push asserts
  RESO + ListingKey + Bearer); typecheck + vitest (49) + build green.

## v0.2.7 — Field-capture depth (GPS geotag, offline-queue review, PWA shortcut)
- Field capture now **geotags** records: a "📍 Tag GPS location" one-shot fix stores `gps_lat`/`gps_lon`/
  `gps_accuracy_m` on the captured record (online + queued offline).
- New **offline-queue review** sheet: list pending captures (photo/note + geotag), **Sync now**, or
  discard individual items — reachable from the capture sheet (shown when the queue is non-empty).
- **PWA app shortcut** "Field capture" (manifest `shortcuts`) + a `?capture=1` deep link that opens the
  capture sheet on load — long-press the installed icon to snap a jobsite photo in one tap.

## v0.2.6 — Opt-in self-hosted basemap tiles (GIS)
- New `gis.loadBasemap` + **Open → "Add basemap (self-hosted tiles)…"**: lays a Web-Mercator XYZ raster
  tile grid on the ground as a georeferenced reference overlay (focus lat/lon + zoom; tiles placed at
  their projected metric positions, North → −Z). Lists in the federation panel (align ⛭ / remove) via a
  new `viewer.addReferenceObject`.
- **Offline-first / honors CLAUDE.md:** nothing loads unless the operator supplies a tile-URL template
  (e.g. their own/self-hosted `https://tiles.internal/{z}/{x}/{y}.png`) — no public CDN default.

## v0.2.5 — E57 point-cloud import (server-side, optional pye57)
- New `e57.py` + `POST /convert` (`.e57`) / `GET /convert/e57/status`: converts E57 laser-scan files
  to a decimated `.xyz` (x y z [r g b], capped at 2M points) **server-side**, since there is no viable
  in-browser E57 parser. Optional, dependency-flagged on `pye57` (heavy/native, not a default dep) — the
  status/gate is testable without it and the convert returns an actionable 503 until `pip install pye57`.
- The viewer's **Open mesh / point cloud / GIS…** now accepts `.e57`: it routes the file through the
  converter and loads the resulting point cloud as a reference overlay (federation list, align, remove).
  Clients `e57Status`, `convertE57`. Backend 63/63.

## v0.2.4 — Live e-signature bridge (DocuSeal, self-hosted OSS)
- The feature-flagged 3rd-party e-signature bridge (`esign_bridge.py`) now **implements DocuSeal
  end-to-end** over its REST API (stdlib `urllib`, no SDK): create a template from the rendered PDF →
  open a submission with the signers → return submission id + per-signer signing URLs.
- New `POST /projects/{pid}/contracts/{key}/{rid}/send-for-signature` (renders the doc, routes it,
  stores `data.esign_submission`, audited) + a **"Send for signature"** action in the contract record
  tools; `POST /esign/webhook` reflects provider completion. `GET /esign/status` now reports whether the
  configured provider is `implemented`. Off unless `ESIGN_PROVIDER=docuseal` + `ESIGN_API_KEY`/`ESIGN_BASE_URL`.
- Clients `esignStatus`, `sendForSignature`; transport is monkeypatchable + unit-tested (gating 409,
  template+submission shaping, stored submission, webhook parse). Other providers keep an actionable
  stub. Backend 62/62.

## v0.2.3 — Change-order log + meeting action-item tracker (analytics suite rounded out)
- New `changeorders.py` + `GET /projects/{pid}/change-orders/log`: the **CO value pipeline**
  (pending / approved / executed / rejected), reason mix, schedule-day exposure, ball-in-court, plus
  the upstream **change-event ROM exposure** (potential cost not yet a CO).
- New `actions.py` + `GET /projects/{pid}/action-items/tracker`: **action items** open / overdue /
  by assignee & priority, completion %, and the **meeting log** (by type, last meeting).
- Two new reports — **Change-Order Log** and **Meeting Action-Item Tracker** (PDF/Excel) — plus tool
  launchers; clients `coLog`, `actionTracker`. Backend 62/62.

## v0.2.2 — Executive health banner on the GC dashboard
- The GC dashboard now leads with a **project-health banner** driven by `GET /projects/{pid}/health`:
  a 0–100 score, overall green/amber/red, open/overdue totals, a per-domain RAG chip strip (hover for
  each domain's headline), and the top ranked attention items — the executive rollup surfaced
  first-class instead of only in a tool modal.

## v0.2.1 — Closeout dashboard + project-health executive rollup
- New `closeout.py` engine + `GET /projects/{pid}/closeout/summary`: **punchlist completion &
  ball-in-court** (open=Subcontractor, ready=GC-verify, verified; % complete, overdue, open-cost,
  by trade/priority), **commissioning pass rate** (by result & test type), **completion certificates**,
  **warranty expirations** (active / expiring-90d / expired), and **O&M-manual turnover** (% accepted).
- New `projecthealth.py` engine + `GET /projects/{pid}/health`: an **executive rollup** that stitches
  the seven analytics domains (RFIs, submittals, quality, safety, T&M, field reporting, closeout) into
  per-domain green/amber/red status, an overall 0–100 health score, open/overdue totals, and a ranked
  list of attention items.
- Two new Report-Center reports — **Closeout Dashboard** and **Project Health (Executive)** (PDF/Excel) —
  plus "Project health" (top of tools) and "Closeout dashboard" launchers; clients `projectHealth`,
  `closeoutSummary`. Verified live over HTTP against the preview DB (endpoints + all 6 new PDFs). Backend 62/62.

## v0.2.0 — Safety dashboard (OSHA TRIR / DART) + construction analytics suite complete
- New `safety.py` engine + `GET /projects/{pid}/safety/summary`: **OSHA incident rates** — TRIR,
  DART, LTIFR, and severity rate on the 200,000-hour base, computed from the incident module's
  classification / osha_recordable / lost-days / restricted-days fields. Worker-hours are taken from
  `?hours=`, else estimated from daily-report manpower (man-days × 8h). Also rolls up the
  **safety-observation leading-indicator mix** (safe vs at-risk, safe:at-risk ratio, close-out %),
  **toolbox-talk coverage** (talks + attendees), and the **safety-violation log** (open / overdue / by severity).
- A **Safety Dashboard (OSHA)** report (PDF/Excel) — distinct from the existing simple Safety/Incident
  Log — plus a "Safety dashboard (OSHA)" tool launcher; client `safetySummary`. Backend 62/62.
- **Milestone:** this completes the construction analytics suite — every core field log (submittals,
  RFIs, T&M, quality, daily reports, safety) now has a first-class rollup, exportable report, and tool launcher.

## v0.1.99 — Field-log rollup (daily reports → manpower / weather / coverage)
- New `dailylog.py` engine + `GET /projects/{pid}/daily-reports/summary`: **manpower trend**
  (total / avg-per-day / peak with date, preferring the manpower_log rollup over the typed count),
  **weather-impact lost-day equivalents** (Minor 0.1 / Half 0.5 / Full & Stoppage 1.0), **delay days**,
  and **reporting coverage** (logged days vs the date span), with by-weather & by-impact breakdowns.
- A **Field-Log Rollup** report (PDF/Excel) in the Report Center + a "Field-log rollup" tool launcher;
  client `fieldLogSummary`. Backend 62/62.

## v0.1.98 — RFI register / log analytics
- New `rfi.py` engine + `GET /projects/{pid}/rfi/register`: **ball-in-court** (draft→GC, open→Consultant,
  answered→GC-accept, closed/void), **overdue** (date-required passed while awaiting a response),
  **response turnaround**, and **cost/schedule-impact exposure**, with by-discipline & by-priority breakdowns.
- An **RFI Register** report (PDF/Excel) in the Report Center + an "RFI register" tool launcher;
  client `rfiRegister`. Backend 62/62.

## v0.1.97 — Quality dashboard (inspections / NCR loop / deficiency ball-in-court)
- New `quality.py` engine + `GET /projects/{pid}/quality/summary`: **inspection pass-rate KPIs**
  (pass rate = pass+conditional / decided, first-pass yield = clean pass / decided, by type & result,
  agency count); the **NCR disposition→corrective-action→close loop** (by state/disposition/severity,
  overdue, undispositioned, avg days-to-close); and the **deficiency ball-in-court rollup**
  (open=Subcontractor, corrected=GC-verify, closed; by trade & severity, overdue).
- A **Quality Dashboard** report (PDF/Excel) in the Report Center + a "Quality dashboard" tool
  launcher; client `qualitySummary`. Backend 62/62.

## v0.1.96 — T&M → change-event tie
- eTickets gain a **change_event** link; `tm.by_change_event` rolls up field T&M by the change event
  it belongs to (`GET /tm-by-change-event`), with linked vs unassigned totals — closing the chain
  field T&M → change event → CO → SOV → AIA billing (G702/G703 already in `cost.py`). The T&M Log
  report gains a "T&M by change event" table. Backend 62/62.

## v0.1.95 — RFI/submittal distribution lists
- RFIs & submittals gain a **Distribution (CC)** field; `distribution.py` resolves it (names or emails,
  comma/semicolon/newline-separated) against the **Contact directory** into recipients + emails.
- `GET /projects/{id}/modules/{key}/{rid}/distribution` returns the resolved list; the resolved emails
  now ride the **record.transition webhook** (`distribution: [...]`) so a listener can notify the CC list.
- Tests in `test_distribution.py` (backend 62/62; rfi/submittal fieldsets kept contiguous).

## v0.1.94 — drawing transmittals + issuance diff
- The drawing-set register now classifies each current sheet as **new** vs **revised** (issuance diff)
  and reports `new_count` / `revised_count`.
- **Drawing transmittal PDF** (`GET /drawing-set/transmittal.pdf?to=…&note=…`): the controlled current
  set grouped by discipline with current revision + New/Revised status, recipients and a note — a ⬇
  Transmittal button in the drawing-set view. Backend 61/61.

## v0.1.93 — construction depth: T&M rollup + submittal register
- **T&M / eTicket cost rollup** (`tm.py`): aggregates eTickets into labor/material/equipment totals,
  by status, with **billed vs unbilled**; `GET /tm-summary` + a T&M / eTicket Log report.
- **Submittal register** (`submittals.py`): spec-section-organized log with **turnaround**
  (received→returned), **ball-in-court**, and **overdue** flags (required-on-site passed, not closed);
  `GET /submittals/register` + a Submittal Register report.
- Both auto-list in the Report Center (PDF/Excel) and have interactive launchers in "Project tools &
  analytics". Tests in `test_construction_depth.py` (backend 61/61).

## v0.1.92 — capital calls & distributions now post to the cap table
- `POST /capital-call` and `/distribution` accept `persist: true` — posting each allocation to the
  investor's **contributed** / **distributed** running total, so the cap table's contributed /
  distributed / unreturned (and the statement PDF) track over time instead of being preview-only.
- Investors tab: **Preview** vs **Record** buttons; recording refreshes the cap table live.
- Backend 60/60 (incl. a persisted-call assertion).

## v0.1.91 — dedicated Operations & Investors tabs + investor statements
- Finance gains two first-class sub-tabs: **Operations** (the hold-phase rent roll — occupancy, WALT,
  in-place income, value-from-rent-roll) and **Investors** (cap table, capital-call/distribution
  tools, per-investor downloads) — moved out of the Valuation tab so each has a clean home.
- **Per-investor capital-account statement PDF** (`GET /projects/{id}/investors/{iid}/statement.pdf`):
  commitment, ownership, contributed/distributed, unreturned + unfunded — a ⬇ per row on the cap table.
- Verified live (both tabs render with seeded data; statement link present); backend 60/60.

## v0.1.90 — accessibility pass: every feature reachable in the UI
A UX audit found seven computed features were API/report-only (no buttons). All are now wired in:
- **Finance ▸ Valuation tab** gains a **Rent roll** card (occupancy/WALT/in-place income + "value
  from rent roll"), an **Investor cap table** card with **capital-call / distribution** tools, and
  the existing appraisal/disposition cards.
- **Report Center ▸ Project tools & analytics** adds launchers for the **Project assistant**,
  **WH-347 certified payroll** (week picker + preview), **Drawing-set register**, **ITB coverage**,
  and **Field-verification coverage**. (The rent_roll/cap_table/appraisal/listing reports already
  auto-list there.)
- **Login** now shows an "SSO available — set `AEC_OAUTH_*`" hint when no providers are configured,
  instead of silently hiding sign-in options.
- Verified live (all surfaces render, console clean), authz re-audited (every new endpoint
  `require_role` + project-scoped; financial writes = editor), `npm audit` 0 vulns, and the new
  tables (`mod_lease`, `mod_investor`, `element_verifications`) confirmed to migrate on **Postgres**.

## v0.1.89 — operate, capital, payroll, drawing-set, assistant & ITB
Six capability gaps closed across operations, capital, payroll, drawing-set control, the project
assistant, and invitation-to-bid.
- **Operating asset mgmt (rent roll):** a `lease` module (Operations) + `rentroll.py` — occupancy,
  WALT, lease-expiration schedule, in-place income; `GET /rent-roll` + a Rent Roll report. The
  appraisal income approach can value off the actual roll: `GET /appraisal?rentroll=1`.
- **Investor / LP capital:** an `investor` module (Capital) + `capital.py` — cap table by commitment,
  pro-rata **capital-call** & **distribution** allocation; `GET /cap-table`, `POST /capital-call`,
  `POST /distribution` + a Cap-Table report. Data-room reuses the document module + attachments.
- **Certified payroll (WH-347):** `payroll.py` aggregates timesheets × labor rates into a weekly
  Davis-Bacon certified-payroll PDF (straight/OT split, prevailing-wage flags); `GET /payroll`,
  `GET /payroll/wh347.pdf`.
- **Drawing-set register:** `drawingset.py` derives the controlled current set from `drawing`
  records (latest revision per sheet = current, earlier = superseded) + sheet index + discipline
  rollup; `GET /drawing-set`.
- **Project assistant:** `assistant.py` extends "ask" from the BIM index to the whole project
  (module tallies, schedule, budget, risk, rent roll); `POST /assistant` (+ `/assistant/snapshot`),
  AI-optional (returns the snapshot without a key).
- **ITB tracking:** `itb.py` rolls up bid packages vs submissions (invited / responded / bonded /
  low bid / coverage gaps); `GET /bidding/itb` + `POST /bidding/packages/{id}/invite`.
- Tests: `test_operate_capital`, `test_payroll_drawings`, `test_assistant_itb` (backend 60/60).

## v0.1.88 — model intelligence, field verification & embeddability
Three features adapted from a scan of **Argyle** (AR field verification) and **Flinker** (OpenBIM in
M365) — built to Massing's open, self-hosted, $0 identity (no AR hardware, no MS-365 lock-in).
- **Ask the model** — `POST /projects/{id}/ask` answers plain-English questions ("how many fire-rated
  doors on L3?", "total curtain-wall area") grounded in a snapshot of the property index (counts by
  class/storey, Psets, facets). Uses the configured AI provider; **degrades to the data snapshot**
  when no key is set. A "✦ Ask" button in the Model workspace.
- **Field verification + install coverage** — mark elements **installed / verified / deviation**
  against design (keyed by GUID, photo-anchored) from the element panel; a coverage summary
  (`GET …/verification/coverage`, % verified/installed of the model total) + a **deviation log** for
  the verified-handover to operations. Argyle's core value, no AR hardware. New `ElementVerification`
  table + `routers/verification.py`.
- **Embeddable viewer + outbound webhooks** — `?embed=1` renders a chrome-less, read-only viewer for
  an `<iframe>` / web-component / Teams tab; module transitions fire **outbound webhooks**
  (`AEC_WEBHOOK_URLS`, fail-open) so Power Automate / Zapier / a custom listener can react. New
  `webhooks.py`.
- Tests: `test_ask.py`, `test_verification.py`, `test_webhooks.py`. Verified live (Ask snapshot,
  embed chrome-less, webhook dispatch + fail-open).

## v0.1.87 — workflow engine upgrades
Cross-cutting upgrades to the config-driven modules engine — each lights up across all ~75 modules,
drawn from construction-management workflow best practice.
- **Transition field-gating** — a workflow transition can declare `requires: [field, …]` that must be
  filled before it fires (RFI can't be *Answered* without an answer). `available_actions` advertises
  it; the action button disables with a "(needs …)" hint until satisfied. Generalizes the attachment
  evidence-gate.
- **Company / Contact directory + first-class lookups** — new `company` + `contact` modules; vendor /
  sub / contact fields become `reference` lookups into the directory (`subcontract.vendor_company`),
  with the picker, resolution and reverse links for free.
- **Due dates / SLA feed** — `GET /projects/{pid}/due-feed` + a "⏰ Deadlines" portal-home widget:
  open records past or near their due date (overdue / due-this-week), across the 11 modules with a
  due field; terminal/closed records excluded.
- **In-app workflow map** — the record view renders a compact state diagram (current state
  highlighted, reachable next-states emphasized). (Saved views already existed.)
- Tests: `test_workflow_gate.py`, `test_due_feed.py`, `test_directory.py` (backend 54 suites).

## v0.1.86 — disposition & valuation (real-estate marketing)
Close the development loop from build to **sell/lease** and **market value** — the two things only a
BIM-native platform can do, because Massing owns the model + proforma. (See
[docs/realestate-marketing.md](docs/realestate-marketing.md).)
- **BIM-native marketing kit** — a config-driven `listing` module (RESO-aligned fields + a workflow
  mirroring RESO `StandardStatus`) that **auto-fills from the project**: areas/unit-mix from the model,
  NOI/cap/asking price from the proforma. One click generates a **Listing Fact Sheet** PDF and a
  signed, expiring **public link + QR** to share a listing without a session (the only anonymous
  surface — token-scoped, read-only, rate-limited).
- **Tri-approach appraisal** — `appraisal.py` fuses the three classic approaches from data already
  in-system: **Cost** (replacement cost from the estimate + land − depreciation), **Income** (NOI ÷
  cap from the proforma), **Sales comparison** (adjusted $/SF from the `comparable` module),
  reconciled into an opinion of value with a range. New **Valuation** tab in Finance (three approach
  cards, editable reconciliation weights, value-by-approach chart) + a **Valuation report** (PDF/Excel).
- **RESO export seam** — `marketing.to_reso()` serializes a listing to RESO Data Dictionary fields, so
  a later bridge can push listings to WPRealWise / an MLS as a serialization, not a rewrite.
- Endpoints: `GET /projects/{pid}/listings/autofill`, `GET|POST /projects/{pid}/appraisal`,
  `GET …/listings/{lid}/reso`, `POST …/listings/{lid}/share`, `GET …/listings/{lid}/public`.
  Tests: `test_appraisal.py` (engine) + `test_marketing.py` (autofill → appraisal → reports → RESO →
  signed public link).

## v0.1.85 — production readiness
- **Readiness probe:** new `GET /ready` (and `/readyz`) pings the DB (`SELECT 1`) and returns `503`
  when it's unreachable, so a load balancer / orchestrator stops routing to a degraded instance;
  `GET /health` (`/healthz`) stays a cheap dependency-free liveness check. The ping runs under a hard
  wall-clock timeout (`AEC_READY_TIMEOUT`, default 3s) and the Postgres engine gets a connect timeout +
  TCP keepalives, so a *black-holed* DB (paused host / partition) yields a prompt `503` instead of
  hanging the probe — verified against a real paused Postgres.
- **Multi-worker login lockout:** the brute-force lockout now shares its counter across workers via
  `AEC_REDIS_URL` (atomic Redis `INCR`+`EXPIRE`), fail-open to the in-process counter — matching the
  per-IP rate limiter. The API runs multi-worker in production, so the lockout now actually holds.
- **Hardened-by-default deploy:** `docker-compose.prod.yml` now sets RBAC, `AEC_REQUIRE_SECRET`,
  HSTS, secure cookie, strict CSP, body cap, rate limit, and ships a `redis` service for the shared
  counters; `.env.example` documents every hardening flag (and how to generate a strong secret).
- **Schema migrations documented + tested:** the app uses an additive, dbDelta-style startup sync
  (fits the config-driven dynamic module tables) rather than Alembic; `SECURITY.md` documents the
  policy + the manual escape hatch for non-additive changes, and `test_migrate.py` proves a new
  nullable model column is ALTERed onto an existing DB and new indexes backfill (additive-only).

## v0.1.84 — security hardening
- **Access control:** RBAC defense-in-depth gate (anonymous blocked from project/finance/admin
  prefixes when `AEC_RBAC=1`), `require_role` on every project-scoped finance/data endpoint, attachment
  download IDOR fixed, projects list scoped to the caller's memberships.
- **Hardening headers** on every response (nosniff, frame DENY, referrer, CSP) + **opt-in strict CSP**
  (`AEC_CSP=1`); **request body-size cap** (`AEC_MAX_UPLOAD_MB` → 413).
- **Path traversal** closed at the storage layer (resolved-path containment) + upload-filename sanitization.
- **Auth:** login brute-force lockout (429), `Secure` auth cookie over HTTPS, fail-fast on a default
  signing secret (`AEC_REQUIRE_SECRET=1`).
- **Signed/expiring download URLs** for `model.frag` + attachments (HMAC, short-lived) — for QR share /
  worker fetch / deep links without a session.
- **Docs:** new `SECURITY.md` (disclosure policy, threat model, production env-flag checklist).
- Production npm dependencies carry no known vulnerabilities (CI runs `pip-audit` + `npm audit`).

## v0.1.83 — charts & graphs (construction + real-estate best practice)
- **Reusable SVG chart kit** (`ui/charts.ts`, dependency-free, theme-aware): multi-series line
  (S-curve), grouped/stacked bar, waterfall, tornado, histogram, donut, progress bar, sparkline.
- **Finance (proforma)** — Underwriting: a **capital-stack donut** (debt/LP/GP), a **JV-distributions
  donut**, equity cash-flow bars, and a one-way **IRR tornado** (derived from the 2-way matrix).
  Statements: **NOI vs net-income** line + **cash-flow-by-year** stacked bar.
- **Construction (GC portal)** — executive **progress bars** (% complete · bought-out · spent) and a
  **budget vs committed vs actual vs EAC** grouped bar by category.
- **Report Center** — charts embedded in the PDFs (cost bar, EVM cash-flow S-curve, financials
  NOI/net-income line) via reportlab's built-in graphics; Excel keeps the data tables for re-charting.

## v0.1.82 — financial statements & tax modeling
- **Three financial statements + tax** — the Finance proforma gains a **Statements** tab (and a
  Report-Center "Financial Statements" PDF/Excel) built on `financials.py`:
  - **Income statement** — stabilized operating P&L (Potential Gross Rent → vacancy/credit → Effective
    Gross Income → operating expenses → **NOI**; then interest, straight-line **depreciation**, income
    tax → **net income**) plus a year-by-year operating summary.
  - **Balance sheet** — Assets (land + improvements net of accumulated depreciation + capitalized
    financing + cash) = Liabilities (loan) + Equity (paid-in + retained); **balances every year**.
  - **Cash-flow statement** — GAAP three-section (Operating / Investing / Financing), indirect method.
  - **Tax** — 27.5-yr residential / 39-yr commercial straight-line (land non-depreciable), annual income
    tax with **passive-loss carryforward** (§469: loss years are suspended, offset later income, and the
    remainder releases against the gain at sale), and at sale **§1250 depreciation recapture** (≤25%)
    stacked on **capital gains** (+ NIIT) — driving an **after-tax** equity IRR / multiple. Institutional
    defaults, overridable via a `tax` block.
  - **Per-year columns** — columnar **balance sheet by year** (balances every column) and **cash flow by
    year** alongside the stabilized-snapshot cards.
  - **Two-sided budget** — the development budget as **Uses** (left) vs **Sources** (right); both tie.
  - Endpoints: `POST /proforma/financials`, `GET /projects/{pid}/financials`,
    `GET /projects/{pid}/budget/two-sided`.

## v0.1.81 — properties panel, multi-city permits, money + BCF hardening
- **Robust properties panel** — the element inspector is now structured (IFC-class badge, copyable GUID,
  collapsible **Attributes / Quantities / Property Sets** with counts), formats values (numbers,
  Yes/No, dashed empties, `{value,unit}`), and adds a live **filter**, per-row click-to-copy, and
  **Copy all**. Quantities (qtos) are shown for the first time; the no-backend fallback renders a
  collapsible tree instead of raw JSON.
- **Interchangeable multi-city permit open data** — a Socrata-based feed (NYC · SF · Chicago · LA ·
  Austin, one-entry to add a city) normalized to one record shape; query near a point/by text, a GeoJSON
  GIS overlay, and a **"Import from city open data"** action that seeds the GC `permit` log
  (source-tagged, deduped). From the github.com/ibuilder portfolio review.
- **Sources & Uses reconciles to the dollar** — line items now sum exactly to the totals and sources tie
  to uses (no per-line rounding drift); `balanced` is a strict check. (WPLedger money-handling review.)
- **BCF round-trip preserves pins** — project-Topic export/import now carry a pin's element GUIDs +
  anchor (previously dropped); 5 orphaned test suites wired into CI; empty/cyclic-project edge cases and
  a 404 (not 500) for unknown modules. Backend suites: 47.
- **Schedule acceleration advisory** — rule-based crash / fast-track / near-critical levers off the CPM
  critical path; `GET /projects/{pid}/schedule/optimize` + an "Accelerate (advisory)" tool. Advisory only.
- **Project risk digest** — cost + schedule + open-items + safety drivers with a prioritized narrative;
  `GET /projects/{pid}/risk-digest` + a Report Center "Risk Digest" report.

### audit follow-ups (ties, queue-readiness, RFI triage, schedule alerts)
- **Predictive schedule alerts** — `GET /projects/{pid}/schedule/alerts` (+ a section in the Executive
  report): overdue work, late / at-risk starts (incomplete predecessor), behind-schedule SPI, and a
  procurement-risk proxy, from the cost-loaded schedule + CPM.
- **AI RFI triage** — categorize + ball-in-court + draft response (see e-sign/AI sections).
- **Relationship ties** — COR ⤳ SOV line, awarded bid ⤳ subcontract conversions; cor→change_event ref.
- **Queue-readiness (no Celery)** — IFC publish extracted to a worker-callable `run_publish(pid)` +
  interrupted-job recovery; rationale in docs/audit-2026-06.md.

### PDF digital signatures (PAdES) + e-sign options
- **Digitally sign (PAdES)** — a contract/CO can be signed with a certificate-based **PAdES** digital
  signature (Bluebeam's model) via **pyHanko**: the document is rendered, signed (tamper-evident,
  self-validating), attached, and the signer + cert **fingerprint** recorded. Uses a self-signed
  platform certificate by default (offline, no cost); set `ESIGN_P12` to sign with your own / a CA cert.
- **3rd-party bridge (feature-flagged)** — `esign_bridge.py` + `GET /esign/status` scope DocuSign /
  Dropbox Sign / self-hosted DocuSeal·Documenso for legally-binding multi-party signing (off until
  `ESIGN_PROVIDER` is configured). Decision write-up in **docs/esign-options.md** (electronic vs
  digital vs SaaS vs OSS; eIDAS / ESIGN Act / UETA; recommendation).

### Report Center (detailed, exportable reports)
- **📊 Report Center** — a catalog of detailed reports, each downloadable as **PDF or Excel**:
  **Executive Summary** (CPI/SPI/EAC, % complete, open RFIs/submittals/COs, safety), **Cost Report**
  (budget/committed/actual/forecast/variance by category), **EVM / S-Curve** (SPI, EAC, cash-flow
  curve), and operational logs (Change Order / RFI / Submittal / Daily / Safety) + **Contracts &
  Signatures**. Built from the existing px / budget / module engines (`reports.py`); endpoints
  `GET /reports` + `GET /projects/{pid}/reports/{report}.{pdf,xlsx}`. Opens from the 📊 toolbar button.

### contract & change-order document lifecycle
- **Generate contract documents** — from a contract record: **Prime Contract**, **Subcontract**
  (AIA A401-style), and **Change Order** (AIA G701-style, showing original → revised contract sum)
  PDFs, merged with project/contract data (`contracts.py`, reportlab).
- **Exhibit generator** — **Compose Exhibit A — Scope of Work** from an editable clause/scope library
  (`scope_library.py`: general/supplementary conditions + per-CSI-division scopes with `{{merge}}`
  tokens); pick clauses → exhibit PDF, attachable to the record.
- **View & markup** — open any generated contract/CO in the PDF markup overlay to redline
  before signing.
- **Signatures & approval** — capture per-party typed signatures (`POST …/contracts/{key}/{rid}/sign`,
  one per party, audited) that render into the document; route/approve via the existing party-gated
  workflow. Endpoints: `GET /scope-library`, `GET …/contracts/{key}/{rid}/document.pdf?doc=&clauses=&attach=`.

### AI estimate (text → BOQ)
- **Draft a Bill of Quantities from a description** — the conceptual-estimate tool gains
  **✨ Draft BOQ from description**: type the scope and the AI returns priced line items
  (description / qty / unit / rate / CSI division) with a rolled-up total. Reuses the existing
  Anthropic provider + `ai_enabled()` gate; degrades to a clean stub (no fabricated numbers) when no
  API key is configured. Endpoint `POST /projects/{pid}/ai/estimate`.

### regional classification standards + GAEB export
- **Regional classifications** — map the model estimate's IFC-class line items to **DIN 276** (DACH),
  **RICS NRM 1** (UK), or **CSI MasterFormat** (US/CA) via `GET /classifications` + a built-in code
  table (`classification.py`).
- **GAEB DA XML (X83) export** — `GET /projects/{pid}/estimate/gaeb.x83?system=…` exports the
  estimate as a GAEB 3.2 Bill of Quantities (the DACH tender standard); the conceptual-estimate
  result now has **↧ GAEB · DIN 276 / NRM 1 / MasterFormat** download buttons.

### PDF takeoff & markup
- **PDF takeoff** — **Drawings → 📄 PDF Takeoff** opens a PDF drawing (pdf.js, offline worker),
  lets you **calibrate the scale** (draw a line, enter its real length), then **measure distance /
  area**, **count** items, and drop **rectangle** annotations directly on the sheet — with a running
  Σ length / area / count panel, an editable measurement list, and **CSV export** of the takeoff
  lines. Coordinates are stored in PDF user-space so measurements stay correct as you zoom.

### GIS / topography layer
- **Import GIS & topography** — **Open ▾ → Open mesh / point cloud / GIS…** now also opens
  **GeoJSON** (parcels, contours, site vectors → points/lines/filled polygons) and **GeoTIFF DEMs**
  (→ a hypsometric terrain mesh displaced by elevation). Layers are georeferenced (lon/lat projected
  to metres; projected coords pass through), list in the federation panel, and align with the same
  ⛭ transform / working-origin as other reference models. Offline (`geotiff` + `earcut`, no CDN).

### model federation, alignment & federated clash
- **Navisworks-style model layering** — each reference overlay (mesh / point cloud) now has a ⛭
  transform panel in the federation list: X/Y/Z offset, a **Z-up → Y-up** flip, uniform scale,
  **Move to picked point**, and Reset — so you can align several models in one space.
- **Multi-discipline models** — append discipline IFCs (STR / MEP / ARCH …) to a project via the
  Coordination panel's **＋ Add discipline IFC** (or `POST /projects/{pid}/models`); they layer in
  the viewer and join clash.
- **Federated (cross-discipline) clash** — **🔗 Federated clash** runs `detect_federated_files`
  across the project's layered models (primary source IFC + appended disciplines), excludes
  intra-model overlaps, lists clashes grouped by model-pair, and turns the top hits into BCF clash
  topics → pins / Issues. (Clash needs real IFC geometry — meshes/point clouds don't clash.)

### multi-format reference models + QR share
- **Open meshes & point clouds** — alongside IFC/Fragments, the viewer now opens **OBJ, STL, PLY,
  glTF/GLB** meshes and **PCD, XYZ, LAS, LAZ** point clouds as **view-only reference overlays** (IFC
  stays the source of truth). LAS/LAZ are decoded locally (offline) via a vendored `laz-perf` WASM;
  big clouds are decimated to stay responsive. Reference models list in the federation panel with
  visibility + remove. **Open ▾ → Open mesh / point cloud…**
- **QR share** — a toolbar **📱 Share via QR** shows a scannable deep link to open the project on a
  phone/tablet.
- **Faster Open IFC** — the native file dialog now appears instantly (the heavy 3D module warms in
  parallel); large IFCs (>~60 MB) route through the server pipeline and stream optimized fragments
  instead of parsing the whole file in-browser.
- **Live demo shows the full platform** — the GitHub Pages viewer-only build now bundles a read-only
  sample project so the GC portal, Budget/GMP, Schedule and Finance panels render with real data.

## v0.1.80 — multi-user persona views + optional paid RVT→IFC bridge
- **Membership shapes the view** — a project member's party role (GC / Owner / Consultant /
  Subcontractor) now auto-selects their persona on open, so they land in the right workspace set;
  capability role already gated edit controls. Members modal (add / role / party / remove) present.
- **Revit (.rvt) → IFC bridge (optional, paid)** — feature-flagged on `APS_CLIENT_ID/SECRET`, doubly
  gated: bridge off → 501 + the free IFC-export path; on → must `confirm_cost` (Autodesk bills per
  conversion). Real RVT→IFC runs Revit's exporter via APS Design Automation (`APS_DA_ACTIVITY`).

## v0.1.79 — 4D colour scrub + quantity takeoff by floor
- **Time-aware 4D scrub** — scrubbing the timeline paints the model green floor-by-floor (rest
  ghosted) with a live **cost-burn** readout from the cost-loaded cash-flow curve.
- **QTO by floor & discipline** — quantities + cost mapped to the storey they sit on, per-floor
  totals + a discipline (IFC class) roll-up.

## v0.1.77–78 — 5D element intelligence
- **Click an element → its 5D** — schedule activity (%-complete, dates, hard-tied vs by-trade) +
  cost-code budget vs committed vs actual. **Model heatmap** — colour by %-complete or cost variance.
- **One-click generate seeds the GC portal** — lot→building→deal also creates cost codes, a
  hard-cost-allocated budget, a GMP prime contract, and a cost-loaded schedule.

## v0.1.73–76 — dashboards + investor deliverables, one language
- **Developer Overview command center** + cross-pillar **Portfolio** (GC status *and* developer
  returns per project, blended IRR), one-click **Save scenario**, and a **Construction Status**
  section in the investor memo + deck. **PX executive band** — on-schedule next to on-budget.

## v0.1.67–72 — developer ↔ GC capital chain
- **GMP ↔ hard-cost reconciliation + one-click sync**, construction **draws** from the schedule, an
  **actuals loop** (owner invoices → re-forecast IRR), **construction-loan draws** (equity-first)
  with **interest accrual** + **per-cost-code composition**, and a **lender draw-request PDF**.

## v0.1.60–66 — GMP project budget (its own destination)
- **Budget** is a first-class destination: the agreed GMP broken to every cost code & bid package +
  General Conditions / Requirements (incl. **staffing** projections) + overhead / fee / contingency,
  each budget vs committed vs actual vs **EAC/ETC**. **Buyout savings**, **change orders → revised
  GMP**, owner **SOV from the budget**, a **cash-flow S-curve**, **baseline + variance** — reconciled
  to the developer proforma's hard cost.

## v0.1.53–59 — relational schedule, field/mobile, GC module depth
- **Relational scheduling** — `schedule_activity` drives the Gantt / Line-of-Balance / CPM **and**
  the 3D 4D model; editable P6 `.xer` import; **lookahead** + **milestone** schedules.
- **Field/mobile** — bulk photo + camera capture, photo-first records, offline upload queue;
  **coordination-issue BCF round-trip**.
- **GC module depth** — ball-in-court, super/PM personas, fieldsets, researched Tier-1/2/3 field sets
  across the 73 modules. **Release pipeline hardened** (version from git tag; single-draft publish).

## v0.1.52 — GC dashboard redesigned as a command center
- **Dashboard rebuilt around the new nav rail** — the redundant "All modules" catalog is gone (the
  persistent left rail owns navigation now), and the dashboard is a focused command center: **clickable
  KPI cards** that jump straight to the relevant filtered module (Open RFIs → RFIs · open), a risk
  summary, a prominent **"Ball in your court"** action list (with a caught-up empty state), a grouped
  **Project health** card (budget over/under + safety + lean PPC), trend charts, and Ask AI at the
  bottom — in a two-column layout that stacks on narrow screens.

## v0.1.51 — cost-code workflow: inline add + wider links (roadmap D1 + X1)
- **Inline "add new" from reference dropdowns (D1)** — every reference field (cost code, location, sub…)
  now has a "＋ Add new …" option that creates the record without leaving the form and selects it. So
  while coding a budget line you add the cost code on the spot. Falls back to the target module's
  required field, so a new Cost Code is created with its `code`.
- **Cost-code links on cost-impacting modules (X1)** — RFIs, CORs, change events, PCO requests and
  proposals gained a `cost_code` reference, so impacts tag a code and roll up to the budget (joining
  budget/commitment/direct-cost/timesheet). `/modules` now exposes `title_field`/`ref_prefix`.

## v0.1.50 — GC portal navigation rail + module improvement roadmap
- **Persistent left nav rail in the GC portal** — opening a module used to replace the whole panel, so
  moving between the 73 modules meant going "back" every time. Now a sticky left rail (Dashboard +
  filter + favorites + collapsible sections) stays visible and loads each module into a content pane —
  jump anywhere in one click, with the active module highlighted. (Stacks above the content on phones.)
- **GC module deep-dive roadmap** ([docs/gc-modules-roadmap.md](docs/gc-modules-roadmap.md)) — a
  field-by-field audit of all 73 modules against how large GCs run these workflows, with cross-cutting
  themes (cost-code links everywhere, ball-in-court
  /assignee, fieldsets, inline add-from-dropdown, super-vs-PM views, cross-module conversions) and
  tiered per-module priorities. How to **add cost codes**: Construction → Cost Codes (Resources) → + Add.

## v0.1.49 — left rail revamp (crisp icons + expandable labels)
- **Modernized the left icon rail** — the oldest piece of the UI. The cryptic `⌗`/`≣` Unicode glyphs
  are replaced with crisp inline **SVG icons** (hierarchy / layers / flag / gear), and the rail is now
  **expandable** (VS Code activity-bar style): a `‹`/`›` toggle widens it 46→150 px to show **Tree /
  Layers / Issues / Tools** labels beside each icon, persisted to localStorage. Structure unchanged
  (the four Model-workspace panels were already the right set); this is legibility + feel.

## v0.1.48 — closeout package reachable in the UI
- **Full turnover .zip now has UI access** — the `closeout/package.zip` deliverable (as-built IFC +
  COBie/QTO/space workbooks + status report + closeout records) worked via the API but had **no
  button anywhere**. Added it to **Save ▾ → Closeout package (.zip)** and the **Tools → Exports**
  panel (📦). Found by debugging every menu item against a real demo project. (The `.mmproj` bundle —
  geometry + full database + blobs, round-trips via Open/Save — was already wired.)

## v0.1.47 — end-to-end demo hardening (closeout filename + generate→finance)
Two real bugs found by a full login→closeout demo run (only surface with a realistic project):
- **Closeout package 500** on any project name containing a non-latin-1 char (em-dash, smart quote,
  accent, emoji): the name went into a `Content-Disposition` header, which HTTP encodes as latin-1 →
  crash. Fixed with a shared `safe_filename()` (also hardens the `.mmproj` bundle vs CJK/emoji).
- **Finance showed $0 right after generating a model**: generate didn't persist a cost budget, so
  Sources & Uses read the empty starter. Generate now seeds a `dev_budget` (land + hard from GFA×$/sf
  + soft) → Finance immediately shows the real deal ($21.2M uses on the demo).
Regression-locked: the closeout test now uses an em-dash project name; the generate test asserts
non-zero Sources & Uses. Full gate green (API 30/30).

## v0.1.46 — Studio UX hardening
- **Studio layout bug fixed** — `#panel-studio` carries both `.fullpanel` and `.studio`, and
  `.fullpanel.active{display:block}` was overriding `.studio{display:flex}`, so the node canvas grew
  to its full 1700 px content instead of filling the viewport. Now a higher-specificity rule forces
  the flex column; the canvas is viewport-bounded and **scrolls internally**.
- **Touch support** — node dragging uses pointer events (+ `setPointerCapture`, `touch-action:none`),
  so it works on tablets/phones, not just mouse.
- **Empty-state guidance** — an in-viewport hint ("add a node… then wire… Run", or "connect the API")
  when the canvas is empty.
- **Smarter node placement** — new nodes drop into the current scroll viewport (with a small cascade)
  instead of a fixed corner that overlapped after a few adds.

## v0.1.45 — custom unit-mix editor (A1b — Test Fit A-theme complete)
- **Define your own unit mix** — the Test Fit panel gains an editor to add/remove unit types
  (name · target SF · mix %), saved to localStorage. "Compare schemes" sends it with `with_defaults`
  so your mix is **ranked against the built-in presets**. Completes A1b — the Test Fit A-theme
  (A1–A6 + egress check + auto egress geometry) is now fully done.

## v0.1.44 — P6 .xer → 4D dates + auto code-positioned egress (A2)
- **Primavera P6 schedule → 4D dates** — `POST /projects/{id}/schedule/import-xer` parses a P6 `.xer`
  (TASK table) and stores it; the **4D scrub then reports real calendar dates** (`source:"p6"`, the
  project's start→finish window) instead of relative takt days. New "⬆ Import P6 schedule (.xer)"
  button beside the 4D tool; a 📅 line shows the imported range. `DELETE …/import-xer` reverts to takt.
  (Element build-order stays takt-derived — no per-activity element mapping is claimed.)
- **A2 — auto code-positioned egress geometry** — generated models with a service core now place
  **two means of egress**: the core stair plus a second "Egress stair 2" at the opposite corner
  (≥⅓-diagonal remoteness, IBC 1007.1.1). Completes the generative half of Test Fit A2 (the egress
  pass/fail check already existed).

## v0.1.43 — demo-aware empty states, mobile/PWA polish, P6 .xer import
- **Demo-aware empty states** — the GC portal & drawings no longer show a misleading "pick a project"
  in the viewer-only Pages demo (there's no backend there). A shared `noProjectHtml` explains it's the
  viewer demo + links to the full app; in the real app it gives an actionable "create/open a project"
  hint.
- **Mobile / PWA polish** — `touch-action:none` + `overscroll-behavior:none` on the 3D container so
  camera-controls own touch gestures (orbit/pan/pinch) instead of the page scrolling; PWA install meta
  (theme-color, apple-mobile-web-app-*, viewport-fit=cover); bigger tap targets for the rail + viewer
  tools on phones.
- **Primavera P6 .xer schedule import** — `schedule.parse_xer` reads the TASK table (planned→actual→
  early date fallback) into the activity rows the CSV mapping path consumes, so a P6 schedule can drive
  the 4D scrub. `.mpp` stays export-to-XML/CSV (proprietary binary). Gated in test_analysis.
- **Roadmap reconciled** — A-theme status clarified (A1/A3/A4/A5/A6 + egress check + parking geometry
  + polygon offset done; only unit-type presets + auto-placed egress geometry remain); schedule-import
  + "what else to import" + Revit/Navisworks-plugin + IFC5-alpha verdicts recorded.

## v0.1.42 — main.ts refactor round 2 (account/admin UI) + login on modalShell
- **Modularization** — the account / auth / admin surface (sign-in + SSO, reset, account menu,
  self-service password, admin user management, audit log, project-member management; ~330 lines)
  moves out of `main.ts` into `account/accountUI.ts` behind a small deps object. With round 1's
  connections extraction, **`main.ts` drops from 1205 → 657 lines**.
- **Login fix** — the sign-in dialog hand-rolled its own overlay and so lacked Esc-to-close, a focus
  trap and dialog ARIA. It's now built on the shared `modalShell` like every other modal — consistent
  look + behaviour + accessibility.

## v0.1.41 — main.ts modularization (round 1) + XSS hardening
- **Security (stored-XSS fixes)** — admin modals interpolated user/remote values straight into
  `innerHTML`. Now escaped via a shared `escapeHtml`: connection **name/type**, Procore **project ID**
  + sync info, **browsed DB** column names & cell values, and audit-log fields (the audit modal's
  weaker local escaper is replaced). No user- or database-controlled string renders as HTML anymore.
- **Modularization + perf** — the ~240-line admin **Data-connections UI** (list/add, Procore
  schedules + field-mapping, SQL browser) moved out of `main.ts` into `connections/connectionsUI.ts`,
  **lazily imported** so its ~13 kB leaves the initial bundle and loads only when an admin opens it.
  `main.ts` drops from ~1205 to 963 lines. Behavior unchanged; verified via the vite transform
  pipeline + typecheck + web unit tests.

## v0.1.40 — viewer camera fix + egress surfaced (UX verification pass)
- **Fix: NaN camera / broken 3D view** — loading a model while the Model workspace wasn't visible
  (e.g. a reload that restored the Finance/Drawings workspace, or opening a model from another
  workspace) created the viewer in a 0×0 container, making `camera.aspect` = 0/0 = NaN; the subsequent
  `fitToSphere` baked NaN into the camera position and the viewport showed nothing once you switched
  to Model. Now the fit is **deferred while the viewport is hidden** and run once it has real
  dimensions, the aspect is forced valid synchronously (OBC's ResizeObserver is async), and a
  hard camera reset recovers an already-NaN camera that `setLookAt` alone can't clear.
- **Egress / life-safety now reachable** — the deepened A2 check (occupant load, travel distance,
  required exits, exit separation) was computed but had no UI. `test-fit/compare` now returns the
  plate-level egress result and the Test Fit panel shows a ✅/⚠️ life-safety line with the figures and
  any code flags.
- Found during a full hands-on verification of everything built this session (viewer tools, Studio
  node editor, generate+parking, families/import, deck, lien waivers, COBie, dashboard, 4D) — all
  others confirmed working end-to-end.

## v0.1.39 — accessibility pass (tab semantics, labels, live region)
- **a11y** — the workspace switcher and finance sub-tabs now carry `role="tablist"`/`role="tab"` with
  `aria-selected` kept in sync as you switch (screen readers announce the active view); the role/persona
  picker gained an `aria-label`; and the status bar is a polite `role="status"` live region so status
  updates are announced. Builds on the existing landmarks (`main`/`nav`/`header`/`footer`), `lang`, and
  icon-button `aria-label`s.

## v0.1.38 — Redis rate limiting (multi-worker) + dashboard perf
- **Distributed rate limiter** — set `AEC_REDIS_URL` and the per-IP request limit is now shared across
  workers/processes via an atomic Redis `INCR`+`EXPIRE` (fixed 60s window), so the limit holds under a
  multi-worker deployment instead of being per-process. Fail-open: any Redis error falls back to the
  in-process bucket so limiter infrastructure can never take the API down; redis is imported lazily
  only when the URL is set (no new dependency for the single-worker/desktop build). New `test_ratelimit`
  gate covers the enforcement path (health/metrics exempt, 429 + Retry-After past the limit).
- **Dashboard perf** — the GC dashboard no longer loads and JSON-parses every record across all
  modules. Status tallies now come from a single indexed `GROUP BY workflow_state` per module (zero
  JSON), and the `data` blob is parsed only for the **active** (non-terminal) records that feed
  overdue + action-items — so completed-record-heavy projects build the dashboard far faster. Output
  is byte-for-byte identical (`test_dashboard` unchanged).

## v0.1.37 — COBie field depth (C2) + investment-deck market/timeline slides
- **COBie model-derived field enrichment (C2)** — the handover sheets gain the fields FM teams use:
  Space net/gross **area** + usable height (from Qto), Type **manufacturer / model / warranty /
  expected-life / replacement-cost / color / material**, Component **serial / install-date /
  warranty-start / tag / asset-id**, plus a new **Attribute** sheet that flattens every remaining
  property set (Name/Value/SheetName/RowName) so nothing is lost in handover.
- **Investment deck — Market & Timeline slides** — the pitch deck grows from 4 to 6 slides: a
  **Market & positioning** slide plotting the deal's yield/IRR/soft-cost against conceptual benchmark
  bands, and a **Development timeline** gantt bar (predev → construction → lease-up → stabilization →
  exit, durations from the saved scenario), plus a **site photo** on the cover from project attachments.

## v0.1.36 — printable statutory lien-waiver documents
- **Lien-waiver documents / PDFs** — pay-app accounting, lien-waiver *record tracking* and COBie
  enrichment already shipped earlier; this adds the piece they lacked: the actual **printable
  statutory waiver form**. `cost.lien_waiver` renders the four conditional/unconditional ×
  progress/final forms (Cal. Civ. Code §8132–8138 style) from a pay application — notice, body and
  amount (current payment due for progress, contract sum to date for final) — exposed as
  `GET /projects/{id}/cost/lien-waiver` (JSON) and `.pdf`, plus a "⚖ Lien waiver / release" action in
  the viewer cost panel. Complements the existing `POST /cost/lien-waiver` record-tracking endpoint.

## v0.1.35 — Test Fit depth (egress · parking · polygon footprint · proforma)
- **Deeper egress / life-safety check (A2)** — `test_fit.egress` now screens the big four IBC fails:
  max travel distance, **occupant load** & required **egress width**, minimum **number of exits**, and
  **exit separation** (½ diagonal / ⅓ sprinklered) — with per-check detail + flags (e.g. an assembly
  hall trips ≥4 exits). Back-compatible with the prior keys.
- **Parking as real IFC geometry** — `generate(..., parking=N)` lays out a surface lot of `N`
  IfcSpace `PARKING` stalls (2.5×5 m + drive aisles) on a dedicated *Site Parking* storey, each with
  area QTOs. Exposed on the generate API + a "Surface parking stalls" field in the proforma form.
- **True polygon-offset footprint** — for `lot_polygon` parcels the buildable footprint is now a real
  inward setback (`offset_polygon`, handles reflex vertices + over-collapse), surfaced as
  `buildable_polygon`, instead of a bounding-box approximation.
- **Optimize tied to the proforma** — the generative sweep's yield-on-cost + new **development
  spread** (bps vs exit cap) come from the canonical `proforma.returns` functions (with stabilized
  occupancy), so the quick screen matches the full underwriting; you can rank by `dev_spread_bps`.

## v0.1.34 — import external IFC families (M3) + visual node editor (M4 complete)
- **Import IFC type content** — bring manufacturer / 3rd-party families into a project from any IFC:
  `families.import_types_from_ifc` copies every IfcTypeProduct (with geometry) in via
  `project.append_asset` (deduped, idempotent), then they're placeable like the built-in catalog.
  New endpoint `POST /projects/{id}/families/import` + *"⇪ Import IFC families…"* in the authoring
  panel. Completes M3.
- **Studio — visual computational graph (M4)** — a new **Studio** workspace renders the Dynamo/
  Hypar-style compute engine as a node editor: drag node types from a palette, wire output→input
  ports (click-to-connect, SVG bezier edges), edit params inline, and **Run** to execute the graph
  server-side in dependency order with values flowing through the wires (zoning → cost → yield, etc.).
  Graph persists locally; shown for developer/architect/engineer personas. Completes M4 — the whole
  **M-theme (M1–M4) is now done**.

## v0.1.33 — material layer sets + family library (M3)
- **Layered construction assemblies** — generated models now carry real **IfcMaterialLayerSet**
  data on walls, slabs and roofs (e.g. exterior wall = brick · cavity · insulation · CMU · gypsum),
  the way Revit's compound structures work — attached via IfcMaterialLayerSetUsage and chosen from
  `IsExternal` / slab type. Feeds take-off, U-value and schedules.
- **Expanded parametric family library** — the placeable catalog grows from 16 to 37 entries across
  new **Lighting**, **MEP** (AHU, fan-coil, diffuser, electrical panel), **Structural** (steel
  column/beam) and **Transport** categories, plus more furniture/sanitary/appliances. Families are
  now **parametric**: pass `dims` to place a distinctly-named, correctly-sized **type variant**
  (Revit-style type families). New element classes get palette colours too.

## v0.1.32 — first-person walkthrough (M2 complete)
- **Walkthrough mode** (🚶 toolbar) — Matterport-style first-person navigation: drops to eye height
  (1.6 m), **W/A/S/D** to walk (locked horizontal so you stay on the floor) and drag to look around.
  Switches to a perspective view on enter and restores your prior camera on exit. Completes M2.

## v0.1.31 — sun & shadow study (M2)
- **Sun / shadow study** (☀ toolbar) — drive the render-mode sun by **date, time-of-day and
  latitude/longitude** with a live panel; shadows track the real solar arc (NOAA solar-position
  math), with warm low-angle light and a below-horizon night state. Opening it auto-enables render
  mode. Pure solar math is unit-tested.

## v0.1.30 — PBR materials + free Revit import
- **PBR pass (M2)** — render mode now upgrades plain lit surfaces to `MeshStandardMaterial`
  (roughness/metalness, keeps the M1 IFC colours) lit by an **IBL studio environment** for soft
  ambient + reflections, on top of the sun/shadows. Reversible; Fragments' own shader meshes are
  left untouched so the engine renderer is never at risk.
- **Free Revit → IFC path** — the Open menu now has *"Free: export IFC from Revit (no bridge)…"*:
  a guide to Revit's built-in IFC export + the free, open-source **pyRevit**, so getting a model in
  doesn't require the paid Autodesk bridge.
- **Docs** — library interoperability evaluation (roadmap §L: IFClite, pyRevit, FreeCAD, Pascal
  Editor) and ADR 0001 on dependency bundling & the signed-update policy (deps are pinned and ship
  inside the app update — never background-updated independently).

## v0.1.29 — render mode (M2 start)
- **Viewer render mode** (◓ toolbar) — a directional **sun with soft (PCF) shadows**, hemisphere
  sky/ground fill + fill light, **ACES tone mapping** and sRGB output, and a shadow-catching ground
  plane. Off by default (flat shading stays the cheap default); re-applies as new models load.
  First step toward Revit/Rhino/Matterport-style rendering.

## v0.1.28 — faster large-model loading
- **Download progress** — large models stream with a live "downloading N% (x/y MB) → preparing
  geometry" label instead of a generic spinner that looked frozen.
- **ETag revalidation** — `model.frag` now serves an ETag + `must-revalidate`: unchanged models
  re-open instantly via **304**, while a republished/edited model is always refetched (fixes a
  stale-cache bug where an immutable 1-year cache served the old geometry forever).

## v0.1.27 — computational graph (M4 start)
- **Dynamo-style node graph** over the pure engines: `GET /compute/nodes` (palette) and
  `POST /compute/graph` run a {nodes, edges} graph in dependency order (zoning → structure / takt /
  cost → yield-on-cost). Zero-touch: function params become input ports, dict returns become outputs.

## v0.1.26 — IFC materials & surface colours (M1 start)
- **Materials & surface styles** — generated/dome models get an IfcMaterial + IfcSurfaceStyle colour
  per element class (concrete, glazing, steel, vegetation…), so models carry real material data.

## v0.1.25 — gamified getting-started
- **Getting-started checklist** — a floating progress pill guides new users through the 6 core
  actions (load a model, generate, test-fit, budget, project, memo) with a progress bar + celebration.

## v0.1.22 — 4D & the vertical assembly line
- **4D construction sequencing** — map model elements onto a takt plan; **scrub the build sequence
  in the viewer** (a slider isolates what's built to date).
- **Takt / line-of-balance chart** (SVG) and an **egress check** (two means + travel distance).

## v0.1.21 — lean & multi-period billing
- **Lean / Last-Planner PPC** — a weekly-plan module + Plan-Percent-Complete analytics with reasons
  for non-completion.
- **Multi-period pay apps** — roll completed-to-date across successive draws; retainage release on
  the final application.

## v0.1.20 — underwriting realism (II)
- **Capital reserves above NOI**, **citable guardrail bands** (sourced from the benchmarks), and
  **Test Fit optimize seeded from the live project** (real land + cost budget).

## v0.1.19 — built-world techniques (Willis · Salvadori · CM/RE research)
- **Takt / line-of-balance** scheduling with a just-in-time delivery plan (R2).
- **Lean PPC** engine (R4) and citable **benchmarks + a comparables module** (R5).

## v0.1.18 — structural-system advisor (R3)
- Pick a plausible system by height/span (flat-plate · shear-core · outrigger) with rough member
  sizing + a load-path read — driving the generated frame (after Salvadori).

## v0.1.17 — form follows finance (R1)
- Generative massing / Test Fit reward **daylight-limited rentable depth** + core efficiency — the
  highest rentable yield wins, not max FAR (after Carol Willis).

## v0.1.16 — underwriting realism (I) + Finance revamp
- **Risk-adjusted** specialty/operating revenue + **guardrails** that flag returns outside market
  bands. Finance reorganized into sub-tabs with a sticky live-returns bar.

## v0.1.15 — pitch deck
- One-click **pitch-deck PDF** variant of the investment memo (B6).

## v0.1.14 — generative optimize + real parcels
- **Generative design** sweeps unit-mix × parking and ranks by yield-on-cost (A5); **real lot
  polygons** drive the program by shoelace area (A6).

## v0.1.13 — Test Fit + property/tax
- **Test Fit** — corridor unit-mix layout, parking solver, scheme compare (A1/A3/A4); **property &
  tax assumptions** feeding OPEX (B3).

## v0.1.11 — specialty assets
- On-site **energy** (solar/wind/battery/rainwater) and **vertical-farm (PFAL)** revenue flow into
  capex / revenue / opex (B4).

## v0.1.10 — developer cost portal
- Line-item **hard/soft cost budgets** (B1), **Sources & Uses** (B2), and a one-click **investment
  memo PDF** (B5).

## v0.1.6–0.1.8 — accounts, AI & hardening
- **SSO** (Google / Microsoft / Procore) + a no-admin free-tier model; first-run **onboarding + tour**.
- **"Ask AI"** project assistant over a live snapshot; AI risk summaries + drafted RFIs.
- **Field capture** (offline photo → punchlist/observation, syncs on reconnect).
- Production hardening — rate limiting, security headers, auth-secret fail-safe, takeoff caching.
- Full generative lifecycle from zoning (frame + units + envelope + core).

## v0.1.0–0.1.5 — foundation
- **BIM viewer** (Three.js + Fragments, offline WASM), federation, clash, IDS, 2D drawings/sheets,
  in-viewer authoring round-trip.
- **GC portal** — config-driven modules (RFIs, submittals, change-order chain, daily, QA, safety…),
  CPM, pay apps, dashboards.
- **Development proforma** — S&U with interest-reserve circularity, XIRR/NPV/EM, JV waterfall,
  sensitivity + Monte Carlo.
- **Generative massing + family library**; free single-project **desktop app** with signed,
  auto-updating releases.
