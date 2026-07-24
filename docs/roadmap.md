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

**Status:** CodeQL 0 open alerts · full backend suite green (358 suites) · single-source version in
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

- **SPRINT A — ENERGY & DAYLIGHT (via the jobs lane).** *(L)* EnergyPlus (BSD) + Radiance (LBNL).
  **Phase 1 (no binaries):** the IDF/gbXML envelope export — model → surfaces/constructions/zones,
  mirroring the shipped FEM-EXPORT pattern. **Phase 2+:** solver binaries through the durable job queue.
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
