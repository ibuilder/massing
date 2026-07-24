# Roadmap

The single product roadmap — **open items only**, reconciled + re-prioritized **2026-07-24 at v0.3.647**
(the 07-24 external planning pack folded in as the 🏢 R19 ring; the 🧭 R17 backend wave, the 🏛 R18
completed items, and the 10/10 NOW list are **shipped and archived**). Everything ever shipped lives in
[roadmap-completed.md](roadmap-completed.md); per-release detail is in [CHANGELOG.md](../CHANGELOG.md).
Supporting detail: [production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[ops-dr.md](ops-dr.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** · **developer/finance**.
The R16/R17 rings are closed on the backend side, the R18 authoring-parity ring is down to its deeper
slices, and the current push is **enterprise + finance-platform readiness** — the programs and governance
layer that make the shipped engines defensible in enterprise diligence.

**Status:** CodeQL 0 open alerts · full backend suite green (363 suites) · single-source version in
`apps/web/package.json` · CI on Node 22 · vitest 132.

---

## 🏢 R19 — enterprise & finance-platform readiness (2026-07-24, from the external planning pack)

An external planning pack (07-24) laid out two planning portfolios: (a) **enterprise-readiness
programs** for the BIM platform — security/threat model, backend standards, reliability/observability,
compliance readiness, authoring gap analysis, interoperability — and (b) a **development-finance /
portfolio product frame** — deterministic financial engine, workflow governance, portfolio analytics,
data ingestion, compliance. **Analysis verdict:** the authoring gap analysis is DONE (that was R18);
the interop program is largely shipped (IDS→BCF · bSDD · COBie · BCF 3.0 · IFC4.3 · classifications);
and most of the finance engines already ship (the pure pro-forma pipeline — cost schedule → sources &
uses → construction loan → operations → reversion → returns → waterfall — plus XIRR/NPV/equity-multiple/
yield-on-cost, the sensitivity grid, Monte Carlo, distribution-waterfall scenarios, WIP/draws/reserve/
capital planning, and portfolio benchmarking). What remains is the **program-formalization + governance
layer** below. Competitor-matrix deliverables from the pack are deliberately **not adopted** (standing
directive: no competitor analysis in repo docs; the neutral external-scan practice covers the research
need).

**Enterprise track — ✅ COMPLETE (Sprint 1 v0.3.649 + INTEROP-RT v0.3.653):**
- ✅ **SEC-THREAT** *(v0.3.649)* — [threat-model.md](security/threat-model.md): STRIDE over the real
  surfaces + the control→evidence verification matrix + the gap backlog; gaps G-2 (SBOM CI artifact)
  and G-5 (the password deny-list, `test_password_policy`) closed in-sprint.
- ✅ **COMPLY-SOC2** *(v0.3.649)* — [soc2-readiness.md](compliance/soc2-readiness.md): the TSC
  control matrix (CC1–CC8 + A1 + C1) with evidence sources + the auditor-facing gap list.
- ✅ **OPS-OBS** *(v0.3.649)* — [runbooks.md](ops/runbooks.md): eight incident runbooks + reference
  SLOs + the correlation-ID triage spine (verified: request-id → OTel → error log).
- ✅ **ENG-STD** *(v0.3.649)* — [backend-standards.md](engineering/backend-standards.md) +
  [web-standards.md](engineering/web-standards.md): the actual conventions codified.
- ✅ **INTEROP-RT** *(v0.3.653)* — `aec_data/roundtrip.py`: serialize → reparse → compare
  (GUID/class/name/containment/type/psets, unmatched both ways, one `fidelity_ok` verdict);
  `GET /model/roundtrip` + `massing roundtrip --gate` + `test_roundtrip`. **The R19 ring is
  complete.**

**Finance track (Sprint 2 — ✅ SHIPPED v0.3.650):**
- ✅ **FIN-GOV** *(v0.3.650)* — `fin_gov.py`: the scenario review workflow (draft→in_review→
  approved→published, immutable once approved, changed-assumption paths audit-logged; Alembic
  `c6dcec8fe81d`) + locked reporting periods enforced in the modules ENGINE (409 on create/update/
  move/delete into a closed month; reaches imports too). `test_fin_gov`.
- ✅ **FIN-CALC** *(v0.3.650)* — `proforma/residual.py` residual-land inverse solver
  (`POST /proforma/residual-land`; honest "not achievable" on impossible targets) + the golden
  reference fixtures (`test_fin_calc`) + [calculation-precision.md](engineering/calculation-precision.md).
- ✅ **FIN-PORTFOLIO** *(v0.3.650)* — `GET /proforma/portfolio/compare` (latest scenario per
  project + governance state + best/worst spread) + the `investor_pack` Report-Center preset.
- ✅ **FIN-INGEST** *(v0.3.650)* — `fin_ingest.py`: `/finance/reconcile` (budget↔actuals both
  ways + uncoded rows) + `/finance/imports` lineage over audit-logged batches. `test_fin_ingest`.

## ▶ NOW — priority order (sprints of large chunks; one full-suite release per sprint)

1. ✅ **R19 Sprint 1 — enterprise readiness** *(shipped v0.3.649)*: SEC-THREAT · COMPLY-SOC2 ·
   OPS-OBS · ENG-STD + the G-2 SBOM and G-5 password-deny-list fixes.
2. ✅ **R19 Sprint 2 — finance platform** *(shipped v0.3.650)*: FIN-GOV · FIN-CALC · FIN-PORTFOLIO · FIN-INGEST.
3. ✅ **INTEROP-RT** *(shipped v0.3.653)* — the R19 ring is complete.
4. ✅ **R18 tail — authoring depth** *(② v0.3.651 · ③④ + wall joins v0.3.653)* — the R18 ring is
   complete.
5. **UX-POLISH sprint**: UX-CHIPS · UX-KPI · UX-DEMO + the demo/docs/Pages refresh.
6. ◧ **Carry-overs** *(3 of 5 shipped v0.3.654)*: ✅ VERSION-COMPARE per-property values ·
   ✅ IFCPATCH-LIB rebase / unit-convert / split *(merge deliberately skipped — federation covers
   multi-model work)* · ✅ BCF-API-SRV 3.0 shape + attachments-over-API. **Remaining:** SPRINT B
   phase-4b CPM crew shifts · NORM-VALID implementer-agreement depth.

7. ✅ **🏙 R20 — CRE deal-desk depth — COMPLETE** *(v0.3.657–660)*: Tier 1 (NER · comp tiers ·
   T-12 gate · rent scrub) · Tier 2 (covenants · authority · supply · committee gate) · Tier 3
   (IC memo · hold-sell · clause playbook).

*Then the viewer-coupled R17 tail (CITE-JUMP · 4D5D-VIEWER · WebXR · NODE-CANVAS · the clash
step-through UI · BCF-VIEWPOINT restore depth), flagged for the dev-preview geometry-stall
verification limit.*

## 🏛 R18 — authoring-platform parity ring (open remainder)

Completed items (SCHED-CALC · OPS-DR · AUTH-CONSTRAINTS ① · MODEL-PUBLISH · RULE-PACK FOLD ·
VIEW-TEMPLATES · FAMILY-DEPTH ① · SDK-VERSIONING · ADR-LITE) are archived. Remaining:

- ✅ **AUTH-CONSTRAINTS — COMPLETE** *(① v0.3.637 · ② v0.3.651 · ③ v0.3.653)* — the constraint
  checker, level-move re-derivation, and wall-join resolution (`wall_joins.py`: L/T detection +
  the idempotent `resolve_wall_joins` butt-join recipe; `test_wall_joins`).
- ✅ **FAMILY-DEPTH — COMPLETE** *(① v0.3.646 · ② v0.3.651 · ③④ v0.3.653)* — type catalogs,
  instance overrides, composite families (`COMPOSITES` under `IfcElementAssembly`;
  `test_composite_family`), and shared parameters (`shared_params.py` registry → schedule columns
  reachable by SCHED-CALC; `test_shared_params`). *Cross-project library versioning rides the
  existing `import_types_from_ifc` + MODEL-PUBLISH review states; a dedicated library-version
  registry is deferred until a customer needs multi-firm libraries.* **The R18 ring is complete.**

## 🏙 R20 — CRE deal-desk depth (2026-07-24, from a two-guide field review)

Two external field guides on running an AI assistant across commercial-real-estate and
ground-up-development workflows (48 mapped workflows / 9 developer systems; vendor names omitted
per the standing docs directive). **Read honestly, most of their content is *prompting technique*
for reading messy documents — which is our documented non-goal** (LLM/OCR reconstruction of
unstructured input; we take structured input through the shipped CSV/XLSX importer and the
connectors). What IS worth taking is the layer underneath: a set of **CRE domain disciplines that
are entirely deterministic**, that we mostly already hold the data for, and that sharpen the
developer/finance pillar. Each item below was checked against what ships before being listed.

The through-line matches our provenance thesis exactly: *every material number carries its source,
nothing reaches a decision-maker un-sourced, and a stale or missing input stops the workflow
instead of being filled in with something plausible.*

**Tier 1 — the data is already there, the discipline isn't (S/M each):**
- ✅ **CRE-NER — net effective rent** *(v0.3.657)*. `net_effective.py` + `GET /rent-roll/
  net-effective`: straight-line AND discounted NER per lease and portfolio-wide, concession load,
  worst face-vs-NER gaps first; leasing commission only when a rate is supplied, un-computable
  leases named not dropped, and the SAME active-lease filter as the rent roll so the two surfaces
  can never describe different portfolios. `test_net_effective`.
- ~~**CRE-NER (original spec)**~~ The `lease` module already stores `free_rent_months`,
  `ti_allowance_psf` and `recovery_psf`, but `rentroll.py` reports face rent only. Add NER — both
  the straight-line form (gross rent − landlord costs ÷ term) and the **discounted** form
  commercial underwriting actually uses — and carry it through the rent roll, the comps, and into
  the pro forma's revenue line. Concessions are deducted before effective gross income, the way
  agency underwriting does it. Deterministic arithmetic over data we hold.
- ✅ **CRE-COMP-TIER** *(v0.3.658)* — `comp_tier.py` + `GET /comps/tiered`: same-address comps
  resolved by tier (overruled values kept visible), every band reporting its weakest tier,
  unrecognized sources landing in the weakest tier. `test_cre_deal_desk`.
- ~~**CRE-COMP-TIER (original spec)**~~ `comparable` has a free-text `source`; make it a
  **ranked tier** (recorded sale > verified/confirmed > vendor estimate > listing > broker
  package). The tier decides which number wins when two comps disagree, and every derived figure
  (cap-rate band, $/SF) reports the **worst tier it depended on** — the CITED-ANSWER contract
  applied to market data.
- ✅ **CRE-T12** *(v0.3.658)* — `t12.py` + `POST /t12/normalize`: its own OPERATING chart of
  accounts, treatment classification, and the tie-out as a GATE (`stopped: true`,
  `adjusted_noi: null` when totals disagree) + run-rate view + add-back questions.
- ~~**CRE-T12 (original spec)**~~ Map an imported T-12 to the house
  chart of accounts (`accounting.COA` ships), classify each line recurring / one-time / capital /
  reclass, and compute run-rate vs trailing. **The gate is the feature:** income, expense and NOI
  must reconcile before *and* after mapping, or the engine stops and lists the reconciling items
  rather than publishing an adjusted NOI. Plus the standard owner-operated add-back checks
  (absent management fee, no payroll line, below-market R&M) surfaced as questions, never applied
  silently.
- ✅ **CRE-RRSCRUB** *(v0.3.658)* — `rent_scrub.py` + `POST /rent-roll/scrub`: seven checks at the
  5% threshold, each reporting `applicable: false` with what it needed rather than a silent pass.
- ~~**CRE-RRSCRUB (original spec)**~~ Cross-check two structured sources we
  already hold: scheduled rent vs gross potential rent (industry practice treats >5% as a
  diligence item), occupied units with no lease on file, rent ≠ executed lease terms, a vacant
  unit carrying a receivable, arrears rising monthly, bad debt rising against flat occupancy.
  Deterministic; composes with FIN-INGEST's reconciliation shape.

**Tier 2 — ✅ COMPLETE (v0.3.659):** CRE-COVENANT (`covenants.py` — day-count basis + clock start
first-class, due dates that show their work, untested ≠ passing, cure windows separate) ·
CRE-AUTHORITY (`deal_authority.py` — per-fact-type authority that GATES on missing/stale/superseded)
· CRE-SUPPLY (`supply_pipeline.py` — evidence-weighted units, rumored kept separate, weighted vs raw
months-of-supply) · CRE-DECISION-GATE (`decision_gate.py` — seven gates, unknown blocks, actions not
just failures). `test_cre_governance`.

*Original Tier-2 specs, kept for reference:*
- **CRE-COVENANT — loan covenant & reporting-obligation register.** Each covenant with its test,
  threshold, frequency and cure right; each reporting obligation with its **day-count basis
  (calendar vs business days), clock start (lender's notice vs our receipt) and deadline** — the
  two fields that cause missed filings — plus a forward calendar and an at-risk flag. Timing alone
  can breach a loan even with clean financials underneath. Nothing like it ships today.
- **CRE-AUTHORITY — deal-room authority table.** Per fact type (rent roll · T-12 · tax · insurance
  · offering package), which document is **authoritative**, its date, its freshness threshold, and
  what it supersedes — with a stale / missing / superseded report that **gates** downstream
  analysis. The CRE analogue of the model-authority discipline we already run, over docmanager and
  the golden thread.
- **CRE-SUPPLY — evidence-tiered competitive supply.** Sharpen the shipped ABSORPTION / LOT-SUPPLY
  engines: weight each pipeline project by *recorded evidence* (permit issued · GC mobilized ·
  construction loan recorded) rather than status labels, filter to the subject's
  delivery-and-lease-up window and competitive product type, and keep rumored supply visibly
  separate from permitted supply instead of blending them into one count.
- **CRE-DECISION-GATE — the pre-committee readiness gate.** A deterministic check before a deal
  package reaches a committee: every material number sourced (reuse CITED-ANSWER coverage), every
  comp tier-traced, every time-sensitive fact within its freshness policy, required exhibits
  present, named sign-off recorded. Blocks with a reason list rather than producing a
  confident-looking package. This is our provenance flagship pointed at the finance pillar.

**Tier 3 — ✅ COMPLETE (v0.3.660):** CRE-ICMEMO (the `ic_memo` Report-Center preset that refuses to
render on a missing basis/NOI/debt/equity/exit-cap, naming what is absent) · CRE-HOLDSELL
(`hold_sell.py` — incremental-cash-flow hold years against the proceeds declined today, explicit cap
drift, honest "no year clears the hurdle") · CRE-CLAUSE (`clause_playbook.py` — positions as data
with a REQUIRED red line per clause; unreviewed clauses reported, never assumed acceptable).
`test_cre_tier3`. **The 🏙 R20 ring is complete.**

*Original Tier-3 specs, kept for reference:*
- **CRE-ICMEMO** — an IC-memo Report-Center preset that **refuses to render** when price, NOI,
  debt, equity or exit cap is missing, rather than inventing one (the `investor_pack` pattern +
  CONCEPT-BUDGET's UNPRICED doctrine).
- **CRE-HOLDSELL** — hold-vs-sell: continue-and-sell-later IRR against net proceeds today, with
  the breakeven hold period. A composition over the shipped returns/reversion engines.
- **CRE-CLAUSE** — a clause-position playbook (accept / negotiate / refuse per clause, per
  contract type) plus a structured deviation record per reviewed document. The *reading* stays
  human/LLM and out of scope; the playbook and the deviation register are ours and deterministic.

**Verified as ALREADY SHIPPING (listed so nobody rebuilds them):** pipeline/deal tracking
(`listing`/`due_diligence` modules) · comp aggregation + appraisal (`comps.py`, tri-approach
report) · rent roll + WALT + renewals/escalations/CAM (`rentroll.py`, `leasemgmt.py`) · the whole
pro-forma pipeline with sensitivity, Monte Carlo and waterfalls · **residual land value**
(v0.3.650) · draw packages + G702/G703 + WIP · variance analysis + budget↔actuals reconciliation
with lineage (v0.3.650) · investor reporting pack + portfolio scenario compare (v0.3.650) ·
scenario governance with locked periods (v0.3.650) · zoning/entitlement feasibility + permit
timelines + absorption/lot-supply · escalation indices + market intelligence.

**SKIP (unchanged doctrine):** LLM/OCR extraction from offering memoranda, scanned T-12s, rent-roll
PDFs or leases — we ingest structured exports, and the deterministic engines above are what make
the numbers defensible. Prompt-library / workflow-count framing is a way of using an assistant,
not product surface. **INTEGRATE (flagged, offline-degrading, never a runtime dep):** paid comp /
market-data feeds and county-recorder pulls behind the existing `opendata.py` indirection.

## 🧭 R17 — viewer-coupled tail (gated on the dev-preview geometry stall)

- **CITE-JUMP** *(S)* — click-to-expand claims jump the viewer to the cited GUID (reuses BCF-VIEWPOINT
  restore) or open the cited record/sheet.
- **4D5D-VIEWER** *(M/L)* — schedule + cost bound to GUIDs → a 4D scrubber coloring by status/date with
  a running earned-value readout.
- **WALK-MODE WebXR pass** *(M)* — the `renderer.xr` headset half of the shipped desktop walk.
- **BCF-VIEWPOINT restore depth** *(S)* — restore section planes + visibility exceptions on reopen; the
  `toDataURL` snapshot thumbnail.
- **CLASH step-through UI** *(S)* — next/prev clash viewpoint + accept/reject marking.
- **FILL-MATRIX frontend** *(S)* — the one-click "fill the blanks" piping `blank_guids` + a value into
  the edit recipe.
- **NODE-CANVAS** *(L)* — the reusable connector/node canvas substrate for the graph-shaped features.

## 🎚 UX-POLISH — interaction-craft ring (open remainder)

- ◧ **UX-ACT** *(S; phase-1 shipped)* — extend the resolve-action descriptors to the `rule_library.py`
  violations and `schedule_options.py` conflict feeds.
- ◧ **UX-CHIPS** *(v0.3.652)* — ✅ `ui/chips.ts` (statusChip/deltaChip/kpiHeader/countNarrative,
  vitest-covered) + first consumers (the margin card's exposure flags). **Remaining:** roll out to
  DRAW-STATUS, the client-portal money cards, and the lifecycle feeds as they're touched.
- ◧ **UX-KPI** *(v0.3.652)* — ✅ the PX executive band's template-string one-line narrative.
  **Remaining:** the same header treatment on the developer/design homes.
- **UX-DEMO** *(S)* — one richly-threaded demo project across every screen (kills empty states).
- **COST-SPINE** *(M)* — one cost-code identity estimate→budget→invoice on the CBS spine (MARGIN-CBS
  follow-on).
- **UX-GANTT** *(M)* — weekly Gantt/calendar hybrid with inline % + crew coloring + a metric strip.
- **UX-VIEWED** *(S)* — ShareToken page view-timestamps → Sent/Viewed/Paid chips, self-hosted.
- **UX-AR** *(S)* — Sent→Approved→Paid manual status pipeline on invoices/bills (no payment rails).

## 🏔 BIG-TICKET SPRINTS — multi-release initiatives (open ONE track; slice + reassess)

- ◧ **SPRINT A — ENERGY & DAYLIGHT.** *(L)* ✅ **Phase 1 SHIPPED (v0.3.655)** —
  `aec_data/energy_export.py`: the IFC becomes a thermal model (zones · zero-thickness mid-plane
  surfaces, each tagged `exact`/`bbox` by checking the mesh against its bounding box ·
  constructions whose conductivities are back-derived from the platform's own R so the export
  can't contradict it) with **gbXML** and **EnergyPlus IDF** writers over one intermediate, both
  byte-deterministic; `GET /energy/model` + `/energy/export.gbxml` + `/energy/export.idf`;
  `test_energy_export`. **Phase 2+:** ship the EnergyPlus (BSD) / Radiance (LBNL) binaries through
  the durable job queue and parse results back onto the model — the remaining gated half.
- **SPRINT C — FIELD-PWA.** *(L, frontend)* Offline-first mobile PWA: service-worker sheet sync, auto
  slip-sheeting, hyperlinked callouts. *(Ships build/typecheck-verified under the preview-stall caveat.)*
- **SPRINT E — FAB-DELIVER phase-2 (GATED).** Byte-exact BVBS BF2D / DSTV-NC held behind the
  authoritative spec + a real importer/validator (a wrong file mis-bends real steel).
- **PHOTO-PIN** *(L)* — photo/360 pinning to plan locations + timeline compare. **CMMS-OPS** *(L,
  defer)* — preventive-maintenance plans + work orders on COBie assets.

## ⚙️ RUNTIME ring (open remainder; measured wins only)

- ◧ **RT-NODE-LANE** — CI is on Node 22; the **local** Node is still 20.3.1 (user action). Then unpin
  eslint (off 9.39.5), then Vite 6→7 behind a build benchmark; defer Vite 8/rolldown.
- **Still to measure:** **RT-BVH** (three-mesh-bvh for the raw-three raycast paths) · **RT-KNIP**
  (unused-export/dead-dep scan, feeds REL-7).

## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- **REL-3 remainder** *(M)* — `modules.py` DI split (unblocks its CRUD/feeds leaves) · `main.py` ·
  `codecheck.py` · `connectors.py` residue · `auth.py` · `data/drawing.py`/`drawings.py`/`massing.py` ·
  `bcf_io.py` · `routers/generate.py`.
- **REL-4 leaves** *(M)* — `portal.ts` next leaf + `viewer/app.ts` leaves.
- **WFE-3** *(M, deferred-by-choice)* — per-project configurable workflow transitions.
- **JOB-QUEUE PAdES** *(S, gated)* — PAdES sealing on the queue (needs a queued signing flow first).
- **REL-6 tail** — cargo-audit / gitleaks in CI when available. · **REL-7** — evidence-gated dead-code
  removal (RT-KNIP feeds it).

## 🧵 R15 / R14 tail

- **NORM-VALID** — the deeper implementer-agreement gauntlet (FILE_DESCRIPTION view-definition parse,
  unit-assignment completeness, relationship cardinality) if a customer needs it.

## 🎨 P2 — design & authoring depth (sequence opportunistically)

**Designer workspace:** UX-3 library depth (thumbnails · drag-to-place · pick-host→auto-build ·
appendable IFC libraries · CC0 seed/H1) · UX-4 one-shell layout (a11y/mobile pass).
**Construction documents (Wave 11):** C6 reference-line datums + LOD-following poché · D2 routed
egress/life-safety plans · B3 wall Axis + clip planes · E5 parametric handles · A2 RAG index over
ifcopenshell/IFC docs.
**Authoring depth (Wave 10):** W10-2 parametric family generators (profiles + swept/boolean) · W10-9
dimensional constraints (planegcs LGPL; sidecar-solved, baked to IFC) · W10-5 section/elevation
annotation views.
**Finance/frontier:** GEN-SCORE depth (per-option 5D takeoffs + EPD carbon) · SITE-1 remaining slices
(terrain DEM auto-fetch · parcel overlays) · COLLAB selection halos.

## P3 — gated (each entry names its unblocking event)

- **Upstream:** IFC5/IFCX *geometry* write (web-ifc/Fragments write path) · bSI Validation Service in
  CI (service account).
- **Paid / flagged (never core):** VIZ-U1/VIZ-3/VIZ-4 presentation/VR builds · W9-7 AI PDF
  auto-takeoff · CODE-6 licensed code prose · COST-DB cloud ingest (the offline importers ship) ·
  DWG (ODA) / USD (pxr) export.
- **Platform/pipeline:** native mobile Capacitor shell (needs macOS/Xcode; PWA ships) · SOC 2
  *cloud-infra* feature set (KMS/retention/residency — the readiness matrix is R19 COMPLY-SOC2) ·
  BMS/IoT telemetry (Brick/Haystack source required) · reality-capture progress quantification
  (capture data required).
- **Large optional builds (prerequisites complete):** coupled-frame FEM solve · viewer tile-streaming
  upgrade · AR field overlay · per-county location-factor/PPI DB tables.
- **Counsel-gated:** regulated syndication depth. ⚖️ Not legal advice.
- **Environment note:** headless/hidden panes stall the Fragments raycast + web-ifc import workers
  (vendor-level; the app-side timeout fallback ships). Verify those two paths in a visible tab.

## Non-goals (documented rationale — not gaps)

`.mpp` parsing (XML/CSV import is the path) · custom Revit plugin (certified `revit-ifc` covers it) ·
live ENERGY-STAR/BAS integrations (flagged stubs only) · CAFM/1031 tooling · scraping code prose ·
GPL/AGPL vendor code (reimplement techniques) · LLM/OCR reconstruction of unstructured docs · owning
capture hardware / photogrammetry pipelines / hosted digital-twin cloud · native VR-headset app +
cloud co-presence sync · payment execution + financing rails · consumer marketplaces · learned risk
forecasting (Monte Carlo covers it) · voice agents. Deliberate 501 bridges (money movement / KYC /
paid APS) are a compliance pattern, not gaps. Integrate-not-build: Cesium ion imagery · Speckle
Automate · iTwin REST · Autodesk APS · Pollination.

**INTEGRATE (optional, feature-flagged, offline-degrading — never a runtime dependency):**
higher-coverage permit backend · contractor license/history feed · permit-density market-activity ·
new-home starts/pricing feed · named BCF-hub connectors · national e-ID/e-sign · ERP connectors.

**License guardrails:** ifcopenshell/geom = LGPL (safe dep) · no AGPL (no PyMuPDF) · planegcs (LGPL,
extractable) over GPL solvers · CC0/CC-BY assets vetted per-asset · OSM = ODbL attribution as a
separate layer.
