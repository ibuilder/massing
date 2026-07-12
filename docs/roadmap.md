# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.196**.

> **Both the product feature roadmap AND the code-quality/hardening initiative are effectively cleared.**
> Every headline feature theme shipped (generative design + Test Fit, developer/finance portal, full
> acquisition→turnover lifecycle, openBIM standards, AI-over-model, discipline spine, operations/
> resilience, scan-to-BIM + 2D→BIM), and the four-domain hardening audit shipped as Waves 1–7
> (observability, perf/scale, type boundary, modularization, reproducibility/ops, strictness + Docker).
> **The complete list of what remains — one env-blocked ops task, optional feature depth, and
> upstream-blocked items — is the single "What's left" section below.** Everything under "Shipped
> archive" is historical reference only.

---

## ★ Current initiative — Code quality & hardening (2026-07)

From a four-domain, file-grounded audit (Python architecture · Python performance/correctness ·
TypeScript · Rust/build-CI). The core is mature; this closes the specific remaining gaps and finishes
half-rolled-out patterns. Delivered as ordinary versioned, CI-green releases, safety-net first.
Full proposal (ranked, with file evidence): https://claude.ai/code/artifact/aabdff8f-e331-4f91-8961-09d0394be4d5

### ✅ Shipped — Waves 1–6 (v0.3.177–191)
- **Wave 1 — Observability (v0.3.177).** O1 server error-log feed (global 500 handler + request-id →
  `error_log` + admin `/admin/errors`, retention-capped) · O2 client-side capture + admin **Errors** panel.
- **Wave 2 — Perf quick-wins (v0.3.178).** P1 `scan_deviation` threadpool · P2 model-keyed `_scan_cached`
  · P5a `(project_id, ts)` index · P5b property-index lock.
- **Wave 3 — Scale (v0.3.179).** P3 `wip.portfolio()` N+1 → `sum_field` SQL aggregate · P4 dashboard/
  schedule routers off `list_records(limit=1e6)` → `count_records`/`func.sum`.
- **Wave 4 — Type boundary (v0.3.181, 190).** T1 OpenAPI-generated TS types (`openapi-typescript` →
  `schema.d.ts` + `openapiTypes.ts` seam) · T4 typed `ui/dom.ts` (`el()/frag()/clear()/readForm<T>()`)
  + Vitest suite.
- **Wave 5 — Modularization (v0.3.181, 186–189).** A1 `model_index.py` extraction (fixed the 5-engine
  dep inversion) · A2 `reports.py` 1,436 → 176-line dispatch + `report_builders/` package · A3 shared
  `deps.open_source_ifc()` · T2 `ApiClient` transport → `httpCore.ts` (`HttpCore`) · T3 portal
  favorites/recents/persona-sections → `portal/prefs.ts`.
- **Wave 6 — Reproducibility + ops (v0.3.182–185, 191).** B1 single-source fragments/web-ifc pair +
  CI guard · B4 converter CLI output-guard + Dependabot `directory:/` · O3 fail-closed prod secrets
  (`${VAR:?}`) · O4 Rust `clippy`/`fmt` PR CI (`rust-ci.yml`) + Trivy (CRITICAL gate + non-blocking HIGH
  report) · P6 `Decimal` money helpers (`money.py`: `q2`/`to_cents`/`allocate`).
- **Wave 7 — Strictness + Docker hardening (v0.3.193–195).** T5 `noUncheckedIndexedAccess` ON + **251
  real guards** across 25 files (no blind `!`; 34 justified `// safe:`; caught real latent crashes —
  empty-selection index, malformed frag pairs, `selectedIndex -1`, unknown-role rank, malformed
  GeoJSON/GeoTIFF) · T6 type-aware ESLint scoped to `no-floating-promises` (45 unhandled-promise fixes)
  + `no-misused-promises` (`checksVoidReturn:false`) · B3 API image multi-stage (build toolchain stays
  in `pybuild`, **no compiler in the runtime**) + web `npm ci` on the workspace lockfile + root
  `.dockerignore`; dropped the vestigial `packages/shared-types` phantom workspace.

---

## ⏳ What's left — the whole open roadmap, prioritized

Everything not shipped, in one place. The product features and the code-quality/hardening initiative
(Waves 1–7 above) are done; what remains is **one env-blocked ops task, optional feature depth, two
upstream-blocked items, and one intentional non-goal.**

**① Actionable next**
- ✅ **DONE — B2 hashed `pip-compile` lockfiles** (v0.3.198). `requirements.in` → `requirements.lock`
  (pinned + sha256-hashed) compiled by `lockfile.yml` inside `python:3.12-slim`; API Dockerfile + CI test
  gate install `--require-hashes` (rejects substituted wheels). One lock covers the data-service subset +
  `psycopg[binary]`; the workflow gates pushes on a stale lock.

**② Feature depth — pull up on a specific customer need (optional, not blocking)**
- ✅ **DONE — Accounting interop depth (the old "Interop-I").** Two halves, both shipped:
  **(1)** approval-gated journal export batch (v0.3.199) — freeze GL/journal/trial-balance into a
  `journal_batch` snapshot that moves `draft → submitted → approved → exported`; GL-CSV/IIF export is
  409 until approved. **(2)** model-quantity-derived WIP % (v0.3.200) — physical percent-complete from
  installed model elements ÷ total **by IFC GlobalId** (units-installed output method), optionally
  quantity-weighted; `wip.schedule` gains a `method` + a `model` cross-check block (physical vs cost POC
  divergence). Builds on `traceability.py` + `verification` install-coverage.
- **Exploratory parking lot.** Test Fit yield-optimization depth · underwriting realism · built-world
  construction techniques · materials/rendering & computational design. Detail preserved in the archive
  below; pull one up only if a customer need surfaces.

**③ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX write-path** — read path shipped; the write path waits on web-ifc/Fragments IFC5 support.
- **Native mobile shell** — a **Capacitor wrapper** (needs a macOS/Xcode + Android-SDK pipeline); the app
  already ships as an installable offline PWA with field capture. See [mobile.md](mobile.md).

**④ Intentional non-goal — documented rationale (not a gap)**
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled (favorites ↔ nav ↔
  persona events ↔ in-place DOM refresh); further mechanical extraction adds indirection over
  readability. The cleanly-separable pieces are already out (Wave 5).

---

## ☆ Wave 8 — 2026 field-research upgrades (proposed)

Sourced from a July-2026 field scan: 14 industry reference sheets (structural loads, LOD, BuiltWorlds
Robotics Top-50, PMO/EPMO, BIM Control Stack, Revit-mistakes, ISO-19650 delivery, a 4-part clash
workflow, planning-vs-controlling, a 10-part construction-execution plan) + three build briefs
(reality-capture→IFC twin; two real-estate-tokenization roadmaps) + VIM (vimaec.com) and a Revit-MCP
automation portfolio. Each track below was validated against **institutional references** and its
dependency licenses verified against our permissive mandate (no AGPL/GPL in the core). Ordered by
leverage. These **deepen existing seams** (clash+BCF, deviation heatmap, `structure.py`, report-gen,
cap-table) — none is a rebuild.

**① Clash Coordination Intelligence — the management layer on top of detection (highest leverage).**
The strongest signal (4 of the 14 sheets walk detect → filter/dedup → assign/resolve → validate/close).
We already *detect* federated clashes + import clash XLSX + speak BCF; the gap is the **coordination
workflow**. Proven pattern (Navisworks · Autodesk Model Coordination · Solibri · Revizto · buildingSMART
BCF): a **two-layer model** — ephemeral `Clash` rows (thousands, regenerated per run) vs persistent
`Issue` = one **BCF Topic** (tens). Build: (a) **grouping** — by-element set-cover + `DBSCAN` proximity +
grid/level bucketing → the industry's ~10:1–100:1 reduction; (b) **tolerance/matrix** — hard vs
soft/clearance + a discipline **clash matrix** (which pairs to test, per-cell severity) as the primary
false-positive control (research shows ~30–60 % of raw clashes are noise); (c) **severity score**
(matrix × penetration depth × group size × structural flag); (d) an **assign→in-progress→closed /
reopened** state machine mapped 1:1 to BCF `TopicStatus`; (e) a **stable `clash_hash`** (sorted GUID pair
+ snapped point) so re-runs auto-set *Resolved* / auto-*ReOpen* on reappearance without losing comments;
(f) **clash KPIs** (open/closed, aging, by-trade-pair, reappearance rate, burn-down). Pure Python over
our existing clash + `bcf_io.py`; GUID-keyed; zero license exposure.

**② Model → Field layout + verified as-built (smallest surface, immediate field utility).**
The BuiltWorlds Robotics-Top-50 sheet points at the 2026 field-robotics wave (Dusty FieldPrinter, Hilti
Jaibot/PLT, Trimble/Leica robotic total stations). They all consume two open primitives from the model:
a **PENZD/PNEZD points CSV** (Point-№, Easting, Northing, Z, Description) and **DXF linework** (for floor
printers). Build a **`model → layout CSV`** exporter (grid intersections from `IfcGrid`, wall control
lines, MEP hanger/anchor points, sleeve/penetration centroids, column setout — Description encodes type +
IFC GlobalId; real-world E/N/Z via our set-origin handling) and a **`model → DXF`** layered drawing
(`ezdxf`, MIT). Close the loop: import measured total-station shots, match by Point-№/GUID, and write a
**BCF topic per out-of-tolerance point** — as-built verification becomes another BCF type on our existing
pin/RFI spine. Monetizes "IFC as the source of truth"; no new heavy deps.

**③ Reality walkthrough + schedule-linked verified-as-built (high visual differentiation).**
From the `photosynth-to-massing` brief. Two parts: (a) a **3D Gaussian-splat "reality" layer** in the
viewer — photoreal, phone-captured, co-registered with the IFC + LAS/LAZ we already load; the permissive
path is **end-to-end** (`gsplat`/Nerfstudio Apache-2.0 for capture, `@mkkellogg/GaussianSplats3D` MIT web
viewer) — *avoid the original Inria 3DGS (non-commercial)*. (b) Turn our **deviation heatmap into
progress**: per-element capture/verification state + % complete tied to schedule tasks, emitted as BCF —
the OpenSpace/Disperse/Buildots value proposition, pure software for us. Add **E57 polish** on the
existing `e57.py`. Automated point-cloud→IFC (**Cloud2BIM is GPL-3.0**) stays an optional *out-of-process*
converter, never linked into the core.

**④ Preliminary gravity load takedown + ASCE 7 combinations (design-phase depth).**
The "Types of loads" sheet. Extend `structure.py` (today: system *recommendation* only) with a
**tributary-area gravity takedown** — dead (self-weight from `IfcMaterial` × geometry + SDL) + live (ASCE
7 Table 4.3-1 by `IfcSpace` occupancy, with the §4.7 live-load-reduction closed form) distributed by
tributary geometry and **accumulated storey-by-storey down each column line to the footings** — plus an
**ASCE 7 load-combination engine** (LRFD §2.3 + ASD §2.4; the coefficients are facts). Output per-column /
per-footing service + factored axial loads for preliminary sizing. **No FEA, no solver** — pure
`ifcopenshell` + arithmetic; optional **PyNite (MIT)** / **sectionproperties (MIT)** tier later for
continuous-member checks (**avoid anaStruct — LGPL-3.0**). Ships with the same PE/RA honesty caveat as our
stamp/seal path: *preliminary coordination estimate, not a substitute for a licensed engineer; lateral
(wind/seismic) out of scope*.

**⑤ Model-hygiene checker (quick win).** The "Common Revit mistakes" sheet + the Revit-MCP portfolio's
*Model Checker / Duplicates Resolver*. Extend our data-QA with **geometric hygiene**: duplicate/overlapping
elements, unenclosed rooms/spaces, elements on the wrong storey, and unresolved authoring warnings — a
scored report over the property index, GUID-anchored, feeding BCF issues.

**⑥ Construction Execution Plan (CEP) generator.** The 10-part "How to prepare a CEP" sheet. A CEP is the
*superset* of a BEP (the BEP governs the model; the CEP governs the work). We already hold the data:
section-templated generator (scope · stakeholder/RACI · site logistics · work packaging/pull-plan ·
resources · cost/schedule/risk + EVM · quality/ITP · HSE/resilience · procurement/subs · commissioning/
COBie-G704) auto-populated from existing modules, BEP linked as an appendix (not duplicated). Reuse the
report/PDF stack; cite ISO 21502 / CMAA practice areas in original prose (no copyrighted text, no
competitor names).

**⑦ Compliant syndication / investor-management depth — cap-table-first, token-last (strategic, legal-gated).**
From the two tokenization briefs. The validated best practice (Securitize, Tokeny, and the non-token gold
standards Juniper Square / Carta): a securities platform is **~80 % a regulated investor-management system,
~20 % blockchain** — Postgres is the legal source of truth, the token an optional mirror. We already have
proforma, JV waterfall, LP portal, capital calls, cap-table.

**DECISION (revised) — integrate, don't build.** We will **not** build the securities/compliance stack
ourselves (KYC/accreditation, transfer-agent recordkeeping, Reg-D compliance engine, escrow, the token) —
that is licensed, counsel-gated, multi-year work and outside our risk appetite. Instead Massing stays the
**origination front-end** (the deal, the IFC model, the proforma, the JV waterfall, a read-only cap-table
view) and **hands the regulated pieces to a licensed platform via API** — the same "connectors OK, we
never move money" posture as our Procore / QuickBooks bridges. Confirmed integration path: **Securitize**
— an SEC-registered **transfer agent + broker-dealer/ATS** — exposes a **Securitize Connect API**,
**Securitize iD** (RESTful KYC/KYB/AML), and **Transfer-Agent-as-a-Service**; for the non-token fund-admin
route, hand off to a fund administrator (data export / referral). So the buildable work shrinks to a
**thin connector** (`connectors.py` already has the pattern): push deal + investor + distribution data to
the partner, pull back verified-KYC / holder-of-record status, deep-link investors into the partner's
onboarding, and show the partner's cap-table state in the LP portal. The token (ERC-3643) is the
partner's concern, not ours; its T-REX reference being **GPL-3.0** is now moot for us. ⚖️ *Not legal
advice; the partner is the licensed entity.*

**Sequencing recommendation:** ① and ② are the near-term, highest-leverage, lowest-risk builds (both pure
software on existing seams). ③–⑥ are self-contained increments to schedule by customer pull. ⑦ is now a
**lightweight integration** (Securitize-style connector) rather than a build — pursue only when a
customer needs to actually raise/syndicate, and keep Massing out of the regulated path entirely.

---

<!-- ═══════════════════════════ SHIPPED ARCHIVE (historical reference) ═══════════════════════════ -->
## Authoring depth + the design engine — ✅ SHIPPED (v0.3.87–88+)

Sourced from a competitive/practice scan (18 industry reference sheets on BEP / LOD / BIM roles /
Revit MEP plant rooms / naming conventions / P6 scheduling / envelope assemblies / construction-tech
M&A) plus two products: **Higharc Studio** (AI-native generative home design — live model → 2D/BIM
auto-propagate, options/variants in one model, rules-based standards) and **ifc-lite** (LTplus-AG,
Rust+WASM browser IFC toolkit — columnar/DuckDB analytics, IFC5/IFCX, broad export). The scan confirmed
we already cover ~80% of professional BIM/PM practice; the real gaps are authoring depth, MEP/schedule
engineering depth, and Higharc-style live-design/options. Do **Phase A then Phase B**, sequentially.

**Phase A — openBIM authoring depth** (SHIPPED v0.3.87–88):
- **A1 — BEP document generator.** Compose a full ISO 19650 **BIM Execution Plan** PDF from the existing
  CDE / EIR / AIR / roles / LOIN / naming registers (objectives, roles-&-responsibilities matrix,
  LOD/LOIN table, information-exchange schedule, naming standards, model-coordination process, QA,
  deliverables). New `reports` builder — inputs already stored.
- **A2 — LOD matrix + element-level LOD.** A `lod_target` register (phase × discipline × element-category
  → LOD 100–500) + validate model elements against target; surface in the openBIM quality scorecard.
- **A3 — Naming-convention validator + document register.** Configurable metadata pattern
  (`DocType_Discipline_Description_Rev_Date`), validate drawing/upload names, master-folder structure in
  the CDE.

**Phase B — the design engine** (SHIPPED v0.3.89; Higharc-inspired):
- **B1 — Design options / variants.** A project carries N schemes; compare area / cost / energy / returns
  across them; promote one to "current." Extends test-fit scheme-compare to the whole project.
- **B2 — Live 2D propagation.** Make the 2D plan/section/elevation generator option-aware and re-run on
  model change (2D generation exists — make it *live-linked*).
- **B3 — Standards ruleset.** Allowed assemblies / materials / product selections the generator + in-viewer
  authoring honor.

**Later phases (backlog, not yet scheduled):**
- **C — engineering depth (SHIPPED v0.3.90):** MEP equipment schedules + pipe/duct sizing + load-calc→
  tonnage + hanger spacing + per-system summaries (extends D5 parametric MEP); resource-loaded scheduling
  + histograms + S-curve + over-allocation.
- **D — interoperability & analytics (SHIPPED v0.3.91; ifc-lite-inspired):** model analytics query layer
  (group-by + count/sum over the property index, saved views); data export (CSV + JSON-LD; Parquet/glTF
  future); envelope code-compliance checker (assembly R/U vs IECC 2021 climate-zone minimums); IFC5/IFCX
  read-path readiness (watch-item — lands when web-ifc/Fragments support arrives).
- **E — field AI (SHIPPED v0.3.92):** field labor-productivity analytics (units/man-hour by trade);
  computer-vision % complete as a feature-flagged external bridge (AEC_CV_BRIDGE — fabricates nothing
  when off).

**Initiative complete (v0.3.87–v0.3.92):** Phases A–D shipped as full features; Phase E shipped
(productivity real + CV as a documented bridge).

**Deferred slices closed (v0.3.95):** the five items previously scoped as needing a dependency / external
service / upstream support are now shipped as far as each honestly can be — **Parquet** export (`pyarrow`;
`/model/export.parquet`); **glTF 2.0** geometry export (`ifcopenshell.geom` triangulation, per-class
meshes, `/model/export.gltf`); the **CV bridge end-to-end** (id-or-name resolution + batch ingest +
[reference adapter](cv-bridge.md), still externally-modelled by design); **live 2D propagation** (model-version
bump + `/drawings/stream` SSE, Redis-shared across workers via `AEC_REDIS_URL`, fail-open to in-process);
and **IFC5/IFCX/ifcJSON data reads** (tolerant
JSON→element-index parser; geometry rendering still lands upstream). Genuinely upstream-only remainder: IFC5
geometry *rendering* (web-ifc/Fragments) and a bundled/trained CV model.

**Earned Value Management — research-backed EVM module (SHIPPED E1–E7, v0.3.109+):** the app had
two disconnected halves (schedule EV without Actual Cost; cost actuals by cost code with a heuristic
forecast). `evm.py` joins them **by cost code (control account)** into one ANSI/EIA-748-aligned set:
PV/EV/AC/BAC, CV/SV/CPI/SPI + bands, per-control-account table, and the EAC/ETC/VAC/TCPI **forecast
family** (best EAC is stage-dependent per the construction-forecasting research, so all are shown).
Sequence: **E1+E2** engine+forecast (v0.3.109) → **E3** Earned Schedule shipped (ES/SV(t)/SPI(t)/IEAC(t) →
forecast finish; fixes the SPI→1.0 tail defect) → **E4+E5** shipped: 3-line S-curve + 📊 Earned Value dashboard + upgraded report
dashboard/report → **E6** EV measurement methods (0/100, 50/50, units-complete, milestone, LOE) + split
installed vs billed/stored/retained EV → **E7** shipped: model-based EV (installed-elements % × BAC from field verification — the
differentiator over P6/Procore-style EVM) + stage-adaptive forecast + earned duration.

**Model authoring — true model-creation program (SHIPPED P0–P6, v0.3.102+):** upgrading the Model
workspace from shallow prompt-driven placement into a real drafting tool with a full BIM family library.
Architecture (research-confirmed): the **browser captures intent** (family + parameters + placement),
the **server authors real IFC** via `ifcopenshell.api` (source of truth), and re-streams fragments — no
browser CAD kernel (ThatOpen Fragments editing can't create elements/write IFC). No permissive pre-built
IFC family catalog exists, so families are **generated procedurally**, seeded from permissive sources
(buildingSMART Community-Sample-Test-Files CC-BY-4.0, re-keyed AISC/Eurocode profile tables, bSDD for
Uniclass/OmniClass + Psets). Sequence: **P0 Draft panel** (`viewer/draft/`, parametric palette + named
params, v0.3.102) → **P1** grid + levels drafting refs (`grid.py` IfcGrid/derived reader + snap +
editable-storey recipes + Grid & Levels panel, v0.3.103) → **P4** structural (steel.py AISC W-shapes as
native IfcIShapeProfileDef + rebar IfcReinforcingBar + IfcFooting, v0.3.104) → **P5** MEP (duct/pipe/
cable-carrier/cable runs w/ ports + IfcDistributionSystem + point equipment: panel/outlet/light/
diffuser/drain/fixture/alarm/sensor/comms, v0.3.105) → **P3** architectural (IfcCovering
ceiling/tile/wood/cladding + IfcRailing, v0.3.106) → **P6** draft perf — optimistic local proxy
(v0.3.107) **+ incremental one-element preview fragment** (`preview.py` + `/edit-preview`, v0.3.108) so
real geometry appears without the whole-model reconvert; plus **MEP fittings** (elbows/tees). **Complete
(P0–P6):** the Draft palette spans all three disciplines with grid/level snapping and instant real-
geometry feedback. Follow-ups if wanted: element property editor (structured Pset editing) +
classification (Uniclass/OmniClass via bSDD) tagging. Earlier placeholder: **P4-cont/**
structural (steel parametric profiles + rebar) → **P5** MEP (duct/pipe runs, electrical, fire/telecom) →
**P3** architectural (coverings/ceilings/tile/wood) → **P6** draft perf (optimistic + incremental
fragments); standards (PredefinedType + classification + Psets at the type level) woven throughout.

**Market intelligence + concept-render bridge (v0.3.101):** from an industry-research pass. A regional
market table (escalation % · labour US$/hr · location index) + a two-speed warm/cold sector signal
(`market_intelligence.py` + `market_assumption` module + `/market/*` + 💹 panel), escalating a base cost
to the **construction midpoint** by region — feeding the conceptual estimate's new market block + a
report. Seed defaults are public T&T GCMI 2026 headline figures (editable, [attributed](ATTRIBUTIONS.md)).
Plus a feature-flagged **AI concept-render bridge** (`render_bridge.py` + `concept_render` module +
🖼 panel, `AEC_RENDER_BRIDGE` off by default): grounds a prompt from the program/massing, ingests returned
images as reviewable records, fabricates nothing when off ([docs/render-bridge.md](render-bridge.md)).

**Code-audit follow-through (v0.3.98–v0.3.100):** a four-dimension audit (backend wiring, UI/UX, sample
data, performance) found the platform structurally clean (46/46 routers, 47/47 reports, 32/32 module
refs). Shipped in three batches + the two deferred items: perf quick-wins (`count_records`, off-loop index
upload, docmanager `tree()` hoist), Documents a11y/responsive + role/phase-gap views, surfaced the
columnar/VIM/STEP analytics, a populated Pages demo (seeded model → Model Analysis + Document Control,
~826 fixtures), a **per-model-version scan cache** (Redis-shared across workers, fail-open) for the hot
colour-by/facets scans, **gzipped colour-by** (+ compact `ids=false`), and a windowed portfolio scenario
query. Audit fully closed.

**Ara3D-inspired efficiency (G1–G3, v0.3.97):** columnar/string-interned property index + EAV Parquet
export for DuckDB analytics (`bim_columns.py`, from Ara3D BimOpenSchema); pure-Python BFAST/G3D/VIM reader
(`aec_data/bfast.py`) opening `.vim`/`.g3d` offline; a fast streaming STEP metadata/entity-histogram scan
(`aec_data/step_scan.py`) with no full parse. MIT-attributed ([ATTRIBUTIONS](ATTRIBUTIONS.md)); the rest
of the Ara3D SDK (geometry/SIMD/collections) was intentionally not ported — numpy/scipy/trimesh already
cover it. Reviewed OpenAEC-BIM-validator: no integration needed (we already do ifctester IDS validation +
BCF).

**Document Control (F1–F6, v0.3.96):** a role-based standard file manager — a fixed project folder
taxonomy (`01_Contract Documents … 11_Final Account`) with each folder owned by a role (PM = business,
Superintendent = field, Architect/Engineer = drawings), ISO 19650 CDE state, and required flags; a
document manager over object storage that auto-names uploads to the information standard and supersedes
(never overwrites) revisions; an elFinder-style two-pane Documents panel; a Document-Control health report
+ AIA phase-gap checks. Reuses the discipline spine, CDE states, naming validator and storage backend.

**Strategic read:** the construction-tech trend is platform consolidation + AI agents + connected
ecosystems + interoperability (Procore/Autodesk/Trimble M&A). Our open, IFC-native, self-hosted, one-model
posture with an MCP server for AI agents + connectors is well-aligned — lean into interoperability
(import/export breadth) and AI-over-the-model.

---

## Active plan (sequenced) — ✅ SHIPPED archive

User-directed sequence (historical, as of v0.2.8; superseded by later themes below — latest **v0.3.86**).
Carry this out in order; each item ships as its own release.

1. **Real-estate / capital depth**
   - [x] WPRealWise / MLS listing syndication bridge + marketing flyer (`re_bridge.py`) — **v0.2.8**
   - [x] Lease-management depth — renewals, rent escalations, CAM reconciliation (`leasemgmt.py`) — **v0.2.9**
   - [x] Equity waterfall / distribution scenario modeling (`distwaterfall.py`) — **v0.2.10**
   - [x] Investor-portal document sharing (signed statement links via `signing.py`) — **v0.2.11**
   - [x] Comps-import automation (bulk CSV / RESO → `comparable`, `comps.py`) — **v0.2.12** ✅ phase complete
2. [x] **Polish & harden existing** — empty-project robustness (regression-locked), malformed-input
   safety, waterfall no-investor guard, a11y labels on new inputs — **v0.2.13**.
3. [x] **Production / ops** — non-root API container + `/metrics` test — **v0.2.14**; backup/restore
   runbook, healthchecks + depends-on conditions, rate-limit env knobs, Caddy HTTPS overlay already shipped.

Construction-depth analytics (the prior theme) shipped fully in v0.2.0–v0.2.7 (6-log suite,
closeout dashboard, executive project-health rollup, e-sign bridge, E57 import, GIS basemaps,
field-capture PWA).

---

## Shipped (highlights)
- **Viewer** — Three.js + Fragments, offline WASM; tree/layers/isolate/section/measure; federation;
  clash (AABB + mesh boolean → BCF); IDS validation; 2D plans/sections/elevations + PDF sheets.
- **Authoring round-trip** — server-side `ifcopenshell` recipes (walls/slabs/columns/beams/roofs,
  openings, edit/move/copy, Pset) → background republish; GUID-stable. Family/type library.
- **Generative massing** — zoning envelope → massing + structural frame + per-unit spaces + envelope
  (facade + windows) + service core (elevator/stair/MEP risers), one click. (Test Fit extends this — §A.)
- **GC portal** — config-driven modules (RFIs, submittals, CO chain, daily, QA, safety, closeout…),
  role-gated workflow, relations/rollups, kanban, search, pay apps (G702/G703), CPM, bid leveling,
  dashboards, **field capture** (offline photo→record), module-log PDFs, closeout package ZIP.
- **Developer/finance** — proforma (S&U w/ interest reserve, XIRR/NPV/EM, JV waterfall, sensitivity,
  Monte Carlo), **line-item hard/soft cost budgets**, **specialty assets** (on-site energy +
  vertical-farm/PFAL revenue), **investment-memo PDF**, model→proforma seeding.
- **AI** — "Ask AI" over a live project snapshot; AI risk summary; AI-drafted RFIs.
- **Platform** — SSO (Google/Microsoft/Procore), no-admin model, onboarding + tour, connectors
  (Procore/ACC/QuickBooks/Sage/Viewpoint/SQL), PWA + signed auto-updating desktop app, rate limiting,
  security headers, takeoff caching. Full lifecycle verified acquisition→turnover (E2E 63/63).

---

## A. Model generation & **Test Fit**  — archive / parking-lot
We have generative *massing*; Test Fit is the optimization layer above it — making the program
actually **fit** the site/floor-plate and **optimizing yield**, with side-by-side scenarios. Our
edge stays IFC-native (every fit is real openBIM, flowing into drawings/QTO/estimate/proforma).
Grounded in [TestFit Site Solver](https://www.testfit.io/product/site-solver),
[Parking Solver](https://www.testfit.io/product/parking-solver),
[Generative Design](https://www.testfit.io/blog/unleash-boundless-building-optimization-with-testfit-generative-design).

- ✅ **DONE — generative massing** (zoning → massing/frame/units/envelope/core).
- ✅ **DONE — A1 unit-mix configurator + corridor layout.** `test_fit.layout()` tiles a unit mix on a
  double-loaded corridor (units both sides) → placed rects + yield; `generate_ifc(unit_layout=
  "corridor")` builds real corridor + unit IfcSpaces. "Double-loaded corridor" toggle on the form.
- ✅ **DONE — A3 parking (lite) + A4 yield compare.** `test_fit.parking()` (stalls/unit ratio →
  count/area/cost) and `compare()` rank schemes; `POST /test-fit/compare` + a "📐 Test Fit" Finance
  panel (units/efficiency/avg-SF/NSF/stalls, best ★). *Next: parking as real IFC geometry, egress.*
> **A-theme status (reconciled 2026-06):** A1/A3/A4/A5/A6 are **done** (see the ✅ entries); the
> egress *analysis* (occupant load · travel · exits · separation), **parking as real IFC geometry**,
> and the **polygon-offset footprint** all shipped in the Test-Fit-depth pass. The bracketed entries
> below are the *original* aspirational specs kept for reference — only two pieces remain genuinely
> open: **(A1b)** named unit-*type* presets (studio/1BR/2BR target-SF + mix) you can save/load, and
> **(A2-geometry)** auto-*placing* code-positioned egress **geometry** (corridors/stairs/elevators as
> IFC, not just the pass/fail check). Both are deeper generative-design work, not blockers.
- ✅ **DONE — A1b unit-type presets.** The Test Fit panel has a **custom unit-mix editor** (add/remove
  types with name · target SF · mix %, saved to localStorage); "Compare schemes" sends it with
  `with_defaults` so **your mix is ranked against the presets**. **The Test Fit A-theme is now fully
  complete (A1–A6 + egress check + egress geometry).**
- ✅ **DONE — A2 egress geometry.** `generate_ifc(core=True)` now places **two means of egress
  positioned for code** — the core stair plus a second **"Egress stair 2"** at the opposite corner
  (≥⅓-diagonal remoteness, IBC 1007.1.1) — alongside the elevator + MEP risers, on the double-loaded
  corridor. (The egress pass/fail *check* was already in `test_fit.egress`.) *Remaining ref:* A1b
  unit-type presets.
- ✅ **DONE — A3/A4 parking + yield compare** (parking lite + real IFC stalls; `compare()` ranks fits).
- ✅ **DONE — A5 generative design (targets).** `test_fit.optimize()` sweeps unit-mix × parking
  presets, scores yield-on-cost, filters by targets (units/efficiency/parking/YoC), ranks. `POST
  /test-fit/optimize` + "⚡ Optimize" button. *Next: tie YoC to the live proforma vs the proxy.*
- ✅ **DONE — A6 (lite) real lot polygons.** `compute_massing(lot_polygon=[[x,y],…])` — shoelace
  area drives the program (L-shaped parcels yield less than their bbox). *Next: true polygon-offset
  footprint + parking/drive-aisle placement on the parcel.*

## B. Developer / finance portal
Grounded in an institutional model (M. Emma thesis) + CRE practice (hard 70–80% / soft 20–30%,
contingency 5–10%; Uses = Acquisition + Hard + Soft + Financing; Sources = Debt + Equity).
- ✅ **DONE — B1 line-item hard/soft cost budgets** (`dev_budget.py`, Finance budget panel).
- ✅ **DONE — B4 specialty assets** (energy + vertical-farm revenue → capex/revenue/opex).
- ✅ **DONE — B5 investment memo PDF** ("presentation with financials").
- ✅ **DONE — B2 Sources & Uses (first-class view)** (`proforma/sources_uses.py`, `solve_sources_uses`).
  Grouped Uses (cost budget + acquisition + financing) vs Sources (senior debt sized by
  LTC/LTV/DSCR/debt-yield, mezz, LP/GP equity); per-period draw spread feeding interest reserve.
- ✅ **DONE — B3 property & tax assumptions.** `dev_property.py` + GET/PUT `/projects/{id}/property`
  + "🏢 Property & tax" Finance panel: parcel/areas/purchase + tax table (school/county/town/fire →
  total) → OPEX, purchase → acquisition line; per-SF ratios. ✅ **DONE — appraisal/market comps** (see B7).
- **B6 — Pitch-deck variant** of the memo (10–20 slides) + market/timeline sections, photos.
- ✅ **DONE — B7 disposition & marketing kit** (v0.1.86). A RESO-aligned `listing` config module that
  **auto-fills from the model + proforma** (`marketing.py`), a BIM-native **Listing Fact Sheet PDF** +
  a **signed public listing link/QR** (read-only — market a building off-plan), and a **RESO Data
  Dictionary** export seam. `GET /listings/autofill`, `POST /listings/{lid}/share`, `GET
  /listings/{lid}/public`, `GET /listings/{lid}/reso`. See [realestate-marketing.md](realestate-marketing.md).
- ✅ **DONE — B8 tri-approach appraisal** (v0.1.86). `appraisal.py` values the asset three ways —
  **cost + income + sales-comparison** (with comps) — and **reconciles** them into a final value;
  surfaced as a **Valuation** tab in Finance with a **Valuation report (PDF/Excel)**. `GET|POST
  /projects/{id}/appraisal`. See [realestate-marketing.md](realestate-marketing.md).

## U. Underwriting realism  — archive / parking-lot
The engine solves the math correctly, but it accepts un-risk-adjusted inputs — e.g. feeding
specialty *operating* revenue (a farm/energy business) straight in as if it were de-risked rent
produced an implausible ~71% IRR in the vertical-farm E2E. "Real underwriting" adds the discipline,
defaults, and guardrails that make the IRR credible. Grounded in CRE practice:
[NOI stress-testing](https://bsreconsulting.com/blog/noi-in-real-estate),
[capital reserves](https://www.adventuresincre.com/the-road-to-a-stabilized-noi-capital-reserves-case-study/),
[market vs contract rent](https://www.mmcginvest.com/post/market-rent-vs-contract-rent-normalizing-leases-in-real-estate-underwriting),
[reviewing assumptions](https://thefractionalanalyst.com/tfa-blog/3-steps-to-review-underwriting-assumptions),
[accurate pro formas](https://wiss.com/real-estate-pro-forma-projections/).

- ✅ **DONE (engine) — U1 revenue realism.** Lease-up curve + occupancy + credit loss already in the solve; market-vs-contract discipline is the remaining input-side note. Was: U1 — Revenue realism. Market-rent vs contract-rent (underwrite the **lower** for debt), a
  **lease-up / absorption curve** to stabilization, vacancy (5–7%), credit loss, and concessions —
  not a single flat "potential rent."
- ✅ **DONE — U2 capital reserves above NOI** (`operations.reserves_annual`, deducted before NOI in solve + a Reserves/yr driver). Was: U2 — Opex build + reserves. A real opex schedule (management ≈ 5% of EGI, utilities, insurance,
  R&M, payroll) + **capital reserves above NOI** ($/unit or $/sf), instead of a flat opex ratio.
- ✅ **DONE (partial) — U3** guardrails now cite `benchmarks` IRR/cap bands; Comparables module added. Next: validate exit cap vs comps. Was: U3 — Cap-rate & comp discipline. Stabilized vs value-add cap-rate bands (≈4–5.5% stabilized,
  5.5–7.5% value-add), an exit-cap **spread** over going-in, and a **Comparables** record (market
  rent/cap/$-per-sf) the deal is validated against (the thesis model has a Comparables tab).
- ✅ **DONE — U4 specialty risk discount.** `specialty.summarize()` now reports gross **and**
  risk-adjusted (underwritten) revenue/offset (default 35% haircut on produce, lighter on energy
  savings); `to_proforma_deltas` flows the **underwritten** figures into the deal so the blended IRR
  isn't overstated. *Next: full specialty P&L + ramp; report blended vs real-estate-only.*
- ✅ **DONE — U5 underwriting guardrails.** `underwrite.guardrails()` flags returns outside market
  bands (IRR >35% / EM >4× / negative or thin dev-spread / DSCR <1.2); `/proforma/solve` returns
  them and the Finance **sticky returns bar** shows a badge ("⚠ check assumptions"). *Next: wire
  Monte Carlo to specialty risk; validate vs Comparables.*
- ✅ **DONE — U6** Test Fit optimize accepts `pid` and seeds land (property) + hard $/sf (budget) from the live project. Was: U6 — Tie Test Fit optimize to the live proforma (vs the proxy) so generative yield-on-cost
  uses the real cost budget + underwritten NOI.

## R. Built-world techniques (research-grounded)  — archive / parking-lot
Lessons from the literature on how tall buildings are actually financed and built — to make the
generative + construction sides reflect real practice, not just geometry. Sources: Carol Willis,
[*Form Follows Finance*](https://archive.org/details/formfollowsfinan0000will) and
[*Building the Empire State*](https://wwnorton.com/books/Building-the-Empire-State/)
([Skyscraper Museum](https://skyscraper.org/empire-state-building-construction/)); Mario Salvadori,
[*Why Buildings Stand Up*](https://wwnorton.com/books/Why-Buildings-Stand-Up); and CM/real-estate
research at [VT Myers-Lawson](https://mlsoc.vt.edu/research.html) (lean construction),
[NYU Schack / PropTech](https://www.sps.nyu.edu/homepage/academics/executive-education/schack-institute-of-real-estate.html),
and ASU.

- ✅ **DONE — R1 form follows finance (daylight-limited leasable depth).** `test_fit.layout()` caps
  leasable depth at a daylight limit (~9 m / 25–30 ft from a window); space deeper earns no rent, so a
  too-deep plate loses rentable area to a dark core and its **daylight efficiency (rentable ÷ gross)**
  drops (verified: 40 m plate 43% vs 16 m plate 77%). Surfaced in the Test Fit compare table (Daylight
  column + ⚠ on deep plates). *Next: make it an optimize objective + sweep plate depth; core-efficiency
  for the elevator/stair core.*
- ✅ **DONE — R2 construction as a vertical assembly line.** `takt.plan()` + `POST /schedule/takt`:
  line-of-balance schedule where trades chase floor-to-floor at a steady takt (days/floor), with a
  **just-in-time delivery plan**, floors/week ascent rate, duration, and peak crew. *Next: takt UI/
  chart; tie to daily-report actuals.*
- ✅ **DONE — R3 structural-system advisor.** `structure.recommend(height, floors, span)` picks the
  system by scale — flat-plate (low) · flat-plate + shear walls (mid) · shear-core + frame (high) ·
  outrigger/tube (supertall) — with rough member sizing (slab ≈ span/30, beam ≈ span/16, columns grow
  with floors, capped 1200 mm), a load-path read, and span/slenderness flags. `POST /structure/
  recommend`; the **generated frame now uses these sizes** (vs the fixed 0.6 m/7.5 m frame) and the
  system shows in the massing result. *Next: per-floor column taper; lateral core geometry.*
- ✅ **DONE — R4 lean / PPC analytics.** A `weekly_plan` (Last Planner) module + `lean.ppc()` +
  `GET /projects/{id}/lean/ppc`: Plan Percent Complete + ranked reasons for non-completion + a
  rating (good ≥ 80%). *Next: surface on the dashboard; production-rate actual vs takt.*
- ✅ **DONE — R5 research-grade data & comps.** `benchmarks.py` + `GET /benchmarks` (citable cost/sf,
  cap-rate, soft-cost, productivity, PPC ranges, wired into the underwriting guardrails) + a
  `comparable` module for deal comps.

## C. Lifecycle / construction depth
- ✅ Field capture (offline), module-log PDFs, closeout package ZIP, auto-TRIR, subject alias.
- ✅ **DONE — C1 multi-period pay apps.** `cost.advance_period()` rolls completed-this → prev across
  SOV lines for successive draws; g702 `release_retainage` on the final app. *Next: auto lien waivers.*
- ✅ **DONE — C2 COBie field-enrichment** — Warranty / System / Asset / Document tabs fold closeout
  data into the COBie export.
- ✅ **DONE — C3 4D sequencing.** `fourd.timeline()` + `GET /projects/{id}/schedule/4d` maps elements
  onto the takt plan (trade × floor) → scrubable frames (cumulative % built/day), with a **viewer
  scrub** (the Schedule tools slider isolates built-to-date) + a takt **line-of-balance chart**.
- ✅ **DONE — C4 workflow-engine upgrades** (v0.1.87):
  - **Transition field-gating** — transitions declare `requires:[field]`; the engine refuses and the
    UI disables the workflow button until those fields are filled (e.g. RFI can't be Answered without an answer).
  - **Company / Contact directory + reference lookups** — first-class directory config modules with
    `reference` field lookups (e.g. `subcontract.vendor_company`).
  - **Due / overdue SLA feed** — `GET /projects/{id}/due-feed` scans all due-bearing modules into one
    ranked feed, surfaced by a **"Deadlines"** portal-home widget.
  - **In-app workflow map** — a state diagram of the module workflow on the record view (current state
    highlighted, gated transitions drawn as edges).

## M. Materials, rendering & computational design  — archive / parking-lot
Closing gaps vs Revit (families/materials), Rhino/Revit/Matterport (rendering), and Dynamo
(visual data/computational). Stays IFC-native + web-first (That Open / Fragments stores per-mesh
material info). Grounded in: [IfcMaterial layer sets](https://forums.buildingsmart.org/t/why-are-material-layer-sets-excluded-from-ifc4-reference-view-mvd/3638),
[three.js PBR](https://threejs.org/docs/pages/MeshStandardMaterial.html),
[Dynamo alternatives / Hypar](https://www.ebool.com/alternatives/dynamo-bim).

- ✅ **DONE (M1 start) — materials & surface styles.** `materials.apply_palette()` assigns an
  IfcMaterial + IfcSurfaceStyle colour per element class to generated/dome models (concrete, glazing,
  steel, vegetation…), so models carry real material data and render in colour. *Next: a material
  editor + per-project palette.*
- ✅ **DONE (M2) — render mode + PBR.** A viewer toolbar **render mode** (◓): a directional **sun
  with soft (PCF) shadows**, hemisphere sky/ground fill + a fill light, **ACES tone mapping** & sRGB
  output, and a shadow-catching ground plane. A **PBR pass** upgrades plain lit surfaces to
  `MeshStandardMaterial` (roughness/metalness, keeps the M1 IFC colours) lit by an **IBL studio
  environment** (RoomEnvironment via PMREM) for soft ambient + reflections — Fragments' own
  `ShaderMaterial` meshes are deliberately left untouched (they carry engine render hooks). Toggled
  on demand (flat stays the cheap default), reversible, re-applied as new models load. A **sun /
  shadow study** (☀) drives the render-mode sun by **date · time-of-day · latitude/longitude** (NOAA
  solar position), so shadows track the real sun arc live — including warm low-angle light and a
  below-horizon night state. A **first-person walkthrough** (🚶, Matterport-style) drops you to eye
  height (1.6 m) with **W/A/S/D** to walk (horizontal-locked, feet on the floor) and drag-to-look;
  toggling off restores the prior camera. **M2 is complete** — next rendering depth lives under a
  future theme (real-time GI / baked AO, exterior HDRI skies).
- **M3 — Family & material depth** (Revit-parity). ✅ **DONE (layer sets)** — `material_layers.py`
  attaches real **IfcMaterialLayerSet** assemblies (exterior wall = brick · cavity · insulation · CMU ·
  gypsum; interior partition; floor slab; flat roof) to every wall/slab/roof via an
  IfcMaterialLayerSetUsage, chosen from `Pset_WallCommon.IsExternal` and slab `PredefinedType`. Runs in
  the generation pipeline after the M1 palette; carries genuine compound-structure data for take-off,
  U-value and schedules. ✅ **Family library** also expanded — [families.py](../services/data/src/aec_data/families.py)
  now offers 37 placeable types across Furniture / Sanitary / Appliance / **Lighting / MEP / Structural /
  Transport** / Plant, each **parametric**: a `dims` override places a distinctly-named, correctly-sized
  **type variant** (Revit-style type families); new classes carry palette colours. ✅ **Import of
  external IFC type content** also shipped — `families.import_types_from_ifc` copies every
  IfcTypeProduct (with geometry) from an uploaded manufacturer/3rd-party IFC into the project via
  `project.append_asset` (deduped, then placeable); exposed at `POST /projects/{id}/families/import`
  and as *"⇪ Import IFC families…"* in the authoring panel. **M3 is complete.**
- ✅ **DONE (M4 start) — computational graph** (Dynamo/Hypar-style, zero-touch). `compute_graph.py`
  exposes the pure engines as **nodes** (params→input ports, dict return→output ports) + an executor:
  `GET /compute/nodes` (palette) and `POST /compute/graph` run a {nodes, edges} graph in dependency
  order (zoning → structure/takt/cost → yield). After the Dynamo zero-touch primer. ✅ **DONE — visual
  node editor** ([studio/nodeEditor.ts](../apps/web/src/studio/nodeEditor.ts)): a new **Studio**
  workspace with a palette, draggable nodes, click-to-connect ports (SVG bezier edges), live param
  fields, and **Run** (executes server-side, values flow through the wires). Graph persists to
  localStorage; persona-gated to developer/architect/engineer. **M4 complete.** *Next (optional): a
  module-relations graph view.*

## L. Library & interoperability evaluations  ★ research pass (2026-06)
Surveyed external libraries against the mission (IFC source-of-truth, server-side IFC→Fragments,
offline viewer, Blender/Bonsai as the *desktop* editor). Verdicts — adopt only what serves the
mission; see [adr/0001-dependencies-and-updates.md](adr/0001-dependencies-and-updates.md) for the
bundling/auto-update policy these feed into.

- **IFClite / `@ifc-lite/*`** (MPL-2.0, Rust+WASM, 25 npm pkgs — [ifc-lite](https://github.com/louistrue/ifc-lite)).
  Claims ~5× faster geometry than web-ifc and, crucially, **IFC5 / IFCX (JSON) support**. *Verdict:
  evaluate — but do **not** swap the browser engine* (our non-negotiable is "never parse full IFC in
  the browser at runtime"; ThatOpen pin coupling). Two useful, contained spikes: **(L1)** trial
  `@ifc-lite/geometry` (the "ifclite-geom" tessellator) as a faster **server-side** converter behind
  the existing convert API; **(L2)** track `@ifc-lite/parser` for **IFC5/IFCX readiness** so IFC
  stays the source of truth as the schema evolves. MPL-2.0 is compatible with our stack.
- **pyRevit** (free, open-source Revit add-in — [pyrevitlabs/pyRevit](https://github.com/pyrevitlabs/pyRevit)).
  *Verdict: adopt as guidance, not code.* ✅ **DONE (L3)** — Open menu now has *"Free: export IFC
  from Revit (no bridge)…"* documenting Revit's built-in IFC export + pyRevit batch export, so the
  free single-project promise is reachable without the paid Autodesk bridge. Not bundled (it runs
  inside desktop Revit; we never read .rvt offline).
- **Revit / Navisworks export plugin?** ❌ **Not needed (decided 2026-06).** Autodesk's
  [revit-ifc](https://github.com/Autodesk/revit-ifc) is the official, free, open-source, *certified*
  IFC exporter for Revit 2019+ (ships natively; an OSS override exists) — a custom plugin would just
  duplicate it. Navisworks is a coordination/review tool, not an authoring app; its IFC export is
  weak/third-party, so the correct workflow is **export IFC from each authoring source** (Revit native)
  and federate here. Our free pyRevit path (L3) already covers batch export. *Optional future nicety:*
  a one-click pyRevit macro that exports IFC **and uploads to a Massing project** — convenience
  only, not a mission requirement.
- **IFC5 / IFCX** — confirmed **alpha** (component-based + JSON serialization,
  [IFC5-development](https://github.com/buildingSMART/IFC5-development)); not production. L2 stays
  *track, don't adopt*; revisit when buildingSMART moves past alpha.
- **FreeCAD** (LGPL — [FreeCAD](https://github.com/FreeCAD/FreeCAD)). Scriptable, **headless-capable**
  via the same `ifcopenshell` we already run, with NativeIFC bidirectional linking + 2D drawing
  generation. *Verdict: evaluate (L4)* as an optional **headless server engine** for parametric
  family generation and 2D-drawing export — additive to our pipeline, no new client weight. Lower
  priority than L1/L2.
- **Pascal Editor** ([pascalorg/editor](https://github.com/pascalorg/editor), R3F + WebGPU, IFC
  importer). A browser **3D building editor**. *Verdict: reference only — out of scope.* The mission
  is explicit that **Blender/Bonsai is the desktop editor, not the web viewer**; in-browser authoring
  would contradict it. Keep as a UX reference for the existing edit-gated place-tools; do not adopt.

**Schedule import (P6 / MS Project)?** ✅ **.xer (Primavera P6) parsed + wired into 4D** —
`schedule.parse_xer` reads the TASK table (planned→actual→early date fallback); `POST
/projects/{id}/schedule/import-xer` stores it and the **4D scrub then reports real calendar dates**
(`source:"p6"`, the project's P6 start→finish), surfaced by an "⬆ Import P6 (.xer)" button next to
the 4D tool. Element build-order stays takt-derived (no per-activity element mapping claimed).
**.mpp (MS Project) intentionally not parsed** — it's a proprietary OLE-compound binary with no
reliable open-source reader; the standard path is *MS Project → Save As XML/CSV → import* (CSV mapping
already supported). **What else to import:** IFC (✅ source of truth), RVT/DWG/NWC via the paid APS
bridge or free Revit-IFC export (✅), BCF issues (✅ round-trip), data via connectors (Postgres/Procore/
QuickBooks/Sage/Viewpoint ✅). Candidate future imports: **E57/point clouds** (reality capture →
overlay) and **glTF** — both nice-to-have, neither blocking the IFC-source-of-truth mission.

**Do we need to create/import libraries to "run on its own"? Do they auto-update?** No new library is
required — the desktop build already runs standalone (Tauri shell + bundled PyInstaller FastAPI
sidecar + self-hosted web-ifc WASM), and the *whole app* auto-updates via signed GitHub releases.
Third-party geometry/WASM deps are **pinned and shipped inside that signed update**, never
background-updated independently (that would break the offline guarantee and the ThatOpen
`components`↔`fragments` version coupling). Policy recorded in the ADR above.

## D. Platform / production
Tracked in [production-readiness.md](production-readiness.md): main.ts account/connections split,
dashboard JSON-extraction perf, Redis-backed rate limits (multi-worker), CI dependency scanning,
a11y pass. Plus: mobile (Capacitor) build hardening; RVT→IFC (APS) polish.

---

## Status & what's left — ✅ archive (v0.1.87 reconciliation)
The headline themes are **shipped** (v0.1.87): generative design + **Test Fit** (A1/A3/A4/A5/A6),
the **developer/finance portal** (B1 budgets · B2 Sources & Uses · B3 property/tax · B4 specialty ·
B5 investment memo), the full **lifecycle** (acquisition→turnover), **AI assistant**, **SSO**, and
the production-blocking hardening (see [production-readiness.md](production-readiness.md) — now
shippable). **30/30 API suites + 3 data suites + 24 web unit tests** (incl. a Studio node-editor DOM
smoke test, an `escapeHtml` / connections stored-XSS lock, and a direct 4D-timeline-engine test) +
a report-only dependency scan.

Remaining = incremental depth (not blockers). **Reconciled against the actual codebase (2026-06)** —
several items the old list called "next" were already implemented; verified by reading source, not
the prior list. Status now in rough priority:

1. **Test Fit depth** — ✅ **DONE** (this pass). A2 egress deepened (occupant load, egress width, min
   exits, exit separation) **and surfaced** in the Test Fit compare UI as a ✅/⚠️ life-safety line;
   parking as real IFC geometry (`PARKING` IfcSpaces on a *Site Parking* storey); true
   **polygon-offset footprint** (`offset_polygon` → `buildable_polygon`); optimize's yield-on-cost +
   **dev spread** use the canonical proforma `returns` (with stabilized occupancy).
2. **Developer deck** — ✅ **DONE.** [report.py](../services/api/src/aec_api/report.py)
   `investment_deck_pdf` now has 6 slides: added **Market & positioning** (the deal's yield/IRR/soft-cost
   against conceptual benchmark bands) and a **Development timeline** (phased gantt bar from the saved
   scenario's construction/lease-up months), plus a **site photo** on the cover pulled from project
   attachments when present.
3. **Construction**
   - C1 pay-apps + lien tracking + COBie record-folding — ✅ done (`f0b1367`); printable statutory
     waiver **document/PDF** added v0.1.36 (`GET /cost/lien-waiver[.pdf]`).
   - **C2 model-derived COBie field depth** — ✅ **DONE.** [cobie.py](../services/data/src/aec_data/cobie.py)
     Space sheets now carry **net/gross area + usable height** (from Qto); Type sheets carry
     **manufacturer / model / warranty / expected-life / replacement-cost / color / material**;
     Component sheets carry **serial / install-date / warranty-start / tag / asset-id**; and a new
     **Attribute** sheet flattens every remaining pset (Name/Value/SheetName/RowName) so no model data
     is dropped in handover.
   - C3 4D sequencing — ✅ already done: [fourd.py](../services/api/src/aec_api/fourd.py) `timeline()`
     + `GET /schedule/4d` + a scrubber in the web portal; schedule viz (`gantt_svg` / `lob_svg`) too.
4. **Platform** — ✅ **Redis-backed rate limits** done: set `AEC_REDIS_URL` and the per-IP limit is
   shared across workers via an atomic Redis `INCR`+`EXPIRE` (fail-open to the in-process bucket on any
   Redis error; redis is lazily imported only when the URL is set), with a `test_ratelimit` gate.
   ✅ **Dashboard JSON-extraction perf** done: status counts via an indexed `GROUP BY` (no JSON), and
   the `data` blob parsed only for active (non-terminal) records — identical output, much less work on
   completed-record-heavy projects. ✅ **a11y pass** (first cut): workspace + finance tabs now expose
   `role="tab"`/`role="tablist"` with `aria-selected` tracking the active tab, the persona picker has an
   `aria-label`, and the status bar is a polite `role="status"` live region (existing landmarks/labels
   were already in place). ✅ **main.ts modularization (round 1)** + **security pass**: the admin
   **connections UI** (~240 lines) is extracted to a **lazily-imported** `connectionsUI.ts` chunk
   (main.ts 1205→963 lines; the 13 kB chunk loads only when an admin opens it), and real stored-XSS
   vectors (connection name, Procore ID, browsed DB cells, audit detail) are now escaped via a shared
   `escapeHtml`. ✅ **Round 2** done: the account/auth/admin UI (sign-in + SSO, reset, account menu,
   password, user management, audit log, project members — ~330 lines) extracted to
   `account/accountUI.ts` behind a small deps object; **main.ts is now 657 lines** (from 1205). Sign-in
   was also rebuilt on the shared `modalShell` (it had hand-rolled its own overlay, so it now gets
   Esc-to-close / focus-trap / dialog-ARIA like every other modal).
5. **Mobile** — framework + plan written ([docs/mobile.md](mobile.md)): the web app is already an
   installable offline **PWA** with the field-capture loop, so the native app is a **Capacitor wrapper**
   of the existing build (camera/GPS/push as capability-detected plugin swaps), not a rewrite. Native
   store builds need a macOS/Xcode + Android-SDK pipeline (separate from the Tauri desktop release);
   recommendation is to ship the PWA "Add to Home Screen" now and fast-follow the native shell.

**Net:** the reconciled roadmap is effectively cleared — every theme (M1–M4, Test Fit, Developer deck,
Construction C1–C3, Platform Redis/perf/a11y) is done except the low-value main.ts refactor and the
out-of-scope mobile app.

---

## Lifecycle completion + production readiness (v0.3.53–v0.3.59, Jul 2026)

Seven sequenced releases closed the production blockers and the two lifecycle gaps (pre-construction
and post-turnover operations) surfaced by the full-code + market audit:

1. **v0.3.53 — backend production blockers**: Postgres-without-RBAC boot guard, SQL-side project
   membership filtering, bounded board/CSV/sync loads, storage-prefix delete cascade, advisory-locked
   autosync, rate-limiter LRU.
2. **v0.3.54 — ops & supply chain**: runnable preflight (`scripts/validate_prod_config.py`) +
   PRODUCTION_CHECKLIST, Dependabot, container build + Trivy gate → ghcr, Cargo.lock workflow,
   sidecar signing, seed guard, TrustedHost.
3. **v0.3.55 — UX/a11y/perf**: promptModal retires every `prompt()`, table-header `scope`,
   mobile pass, perf baseline.
4. **v0.3.56 — pre-acquisition**: `due_diligence` (ASTM E1527-style categories) + `entitlement`
   modules with a go/no-go readiness rollup + 📜 panel.
5. **v0.3.57 — operations (CMMS + energy)**: `work_order`/`pm_schedule`/`meter`/`meter_reading`,
   PM generation + KPIs (PM compliance, MTTR), metered EUI + trends, flagged ENERGY STAR bridge,
   🔧 Operations + ⚡ Energy panels.
6. **v0.3.58 — capital stewardship**: reserve study (component replacements + funding adequacy +
   suggested contribution), `capital_plan` (CIP), `cam_expense` + CAM reconciliation with
   variable-only gross-up + per-tenant statement PDFs, Finance ▸ Asset Mgmt tab.
7. **v0.3.59 — ESG + POE**: GHG Scope 1/2 from a local factor table, water, certification tracking,
   `poe` module (actual-vs-design EUI gap), 🌱 ESG & POE panel + Report Center entry.

**Documented follow-ups (out of scope by design):** live ENERGY STAR/BAS/BMS integrations (flagged
stubs only), full institutional reporting packs, space/move management (CAFM), 1031 tooling, JWT
revocation blacklist + Redis-backed presence (known limits in PRODUCTION_CHECKLIST).

---

## Standards, KPIs & AI-over-model (v0.3.61–v0.3.68, Jul 2026)

Eight sequenced releases (a competitive scan of eight AEC products + the ISO 19650 / buildingSMART /
BIM-KPI frameworks) made the platform demonstrably standards-aligned across the lifecycle and added
the AI-over-model layer competitors lead with — all offline-first, money behind flagged bridges,
docs neutral:

1. **v0.3.61 — ISO 19650 CDE**: `information_container` (WIP→Shared→Published→Archived + suitability/
   revision codes + approval gates) + `info_requirement` register (OIR/AIR/PIR/EIR/BEP/MIDP/TIDP);
   CDE-discipline metrics; 🗂 CDE / Standards panel.
2. **v0.3.62 — openBIM quality** (`openbim_quality.py`): LOIN per element, IDS rule-compliance %,
   IFC export health, bSDD alignment — scored over the model property index.
3. **v0.3.63 — BIM KPI scorecard** (`bim_kpi.py`): the 10-category information-management scorecard
   (n/a when inputs absent) + a handover data-drop acceptance gate + Report Center entry; 📊 panel.
4. **v0.3.64 — AI over the model**: an **MCP server** (`mcp_server.py` + `mcp_tools.py`, SDK optional)
   exposing the project to external agents, plus grounded **standards-compliance experts**
   (`standards_expert.py`) referencing the clause behind each finding. [docs/mcp.md](mcp.md).
5. **v0.3.65 — digital twin + DPP** (`twin.py`, `building_system`): asset↔system linkage + sensor
   mapping (ISO 23247) + Digital Product Passport scaffolding (GS1/EPD/manufacturer).
6. **v0.3.66 — procurement compliance gate** (`procurement_gate.py`): per-vendor can-bid / can-bill
   from the COI / prequal / subcontract / waiver records + the outbound nudge feed.
7. **v0.3.67 — drawing-sheet extraction** (`sheet_extract.py`): parse a PDF text layer / pasted index
   into `{number, title, discipline}` → optionally create Drawing records (AI page-image path flagged).
8. **v0.3.68 — concept space programming** (`adjacency.py`, `space_program`): the program as a
   node/adjacency graph → gross area + use mix that feed the massing generator; 🧩 Space Program panel.

The platform now spans **land acquisition → programming → design (ISO 19650) → construction → turnover
→ operations (twin/ESG)** with standards alignment and an AI surface at each stage.

---

## Design workspace + role-based placement (v0.3.70)

Added a **Design** top-level workspace (between Drawings and Construction) as the architect/engineer's
design-phase seat, and did a methodical pass so every tool shows in the view(s) whose role owns it.
See [roles-views.md](roles-views.md) for the full role→view map.

- **Engine**: a module can now belong to more than one workspace (`workspace` is a `|`-separated list);
  shared A/E↔GC registers (RFI, submittal, drawing, transmittal, meeting, permit, spec) show in both
  Design and Construction without duplicating records.
- **Design nav**: Brief & program (Space Program · Project Lifecycle) + Model & standards (IDS · CDE /
  Standards · BIM KPIs · Model Health) — the design/standards destinations moved here out of the GC
  portal. A **Model Health** launcher deep-links to the model-QA checks in the Model Tools rail
  (they need the loaded geometry). Personas: architect/engineer home into Design.

## Part C — UX / performance / productivity backlog (approve item-by-item)

Candidate upgrades identified during the Design-workspace pass, not yet scheduled:

1. **Nav density** — the Construction portal + the multi-card panels (Schedule now stacks 6 cards) are
   getting dense; add per-stage collapse memory and a denser dashboard summary.
2. **Role landing dashboards** — every persona should open to a tailored command-center (the Design
   home sets the pattern; extend to Finance and Developer).
3. **Viewer-tool discoverability** — the model-health checks (Data QA, code-readiness, clash, IDS) are
   buried in the Model Tools rail; the Design **Model Health** launcher is step 1 — consider a
   first-class "Model health" surface with live scores.
4. **Front-end perf** — `portal.ts` is ~4,000 lines and eager; split per-workspace render bundles
   (dynamic import) so Design/Developer code loads on first open. Keep the Brotli shell budget gate.
5. **Cross-workspace deep-links** — RFI → drawing → model element; saved views per role; ⌘K scoped by
   the active workspace.
6. **A11y** — keep verifying new tabs/dashboards (roles, focus order, contrast) as workspaces grow.

---

## Operations depth — facility condition + pull-planning (v0.3.72+)

Rounding out the operate phase and the Last Planner board:
- **v0.3.72 — Facility Condition Assessment + FCI (M1, shipped)**: `fca_element` module + `fca.py`
  engine (FCI = deferred + renewal ÷ CRV, UNIFORMAT II, condition bands, portfolio roll-up), reserve-
  study integration, 🏥 Facility Condition panel + report.
- **v0.3.73 — M2 (shipped) — deeper Last Planner analytics**: Tasks-Made-Ready %, make-ready lead time, perfect-
  handoff %, PPC trend by week, variance-reason Pareto, and cross-project pull-planning benchmarks.
- **v0.3.77 — real-time collaborative pull board (M3, shipped)**: an SSE stream
  (`/pull-plan/stream`) over a cheap board change-signature live-refreshes the board as any trade
  edits; presence chips show who else is on it; and an opt-in optimistic lock (`expected_modified_at`
  → 409) stops silent overwrites — reusing the existing presence/notification-stream primitives, no
  new deps. The lock is generic (every module benefits, via the record editor).

---

## Climate & water resilience (v0.3.75+)

Rainfall and flooding as quantifiable design parameters, across the lifecycle:
- **v0.3.75 — W1+W2 (shipped)**: flood risk (ASCE 24 Design Flood Elevation + flood-proof-MEP check)
  and stormwater (Rational Method Q=C·i·A + detention) — `flood_risk`/`drainage_area` modules +
  `resilience.py` + 🌊 Climate Resilience panel + report.
- **v0.3.76 — W3+W4 (shipped)**: weather-sequenced construction — a `weather_sensitivity` flag on
  schedule activities + a `climate_site_risk` register (hazard/season/severity/controls) + weather-delay
  days rolled up from the daily reports (`resilience.weather`); and a physical climate-risk rating
  (Low/Moderate/High/Severe over flood exposure + at-risk assets + open site hazards + weather delays,
  `resilience.climate_risk`) folded into the ESG scorecard (`physical_risk`).

## The Discipline Spine — layered model → sheets → specs → bid packages → budget (v0.3.79+)

Represent a project as federated **structural / MEP / architectural** models whose discipline-tagged
sheets thread through specifications, bid packages and the budget — grounded in the US National CAD
Standard discipline designators + CSI MasterFormat, with the Uniformat↔MasterFormat crosswalk. Two
shared vocabularies (discipline + MasterFormat division) do the joining. Five phases:

- **v0.3.79 — D1 (shipped): shared vocabularies.** `classification.py` gains the NCS discipline
  vocabulary (A/S/M/E/P/F/C/T/G/L/Q with each discipline's default MasterFormat divisions + Uniformat
  groups), the MasterFormat division master (25) and the Uniformat↔MasterFormat crosswalk;
  `discipline_of_ifc_class`, `discipline_code` (legacy-alias normalization). `GET /reference/disciplines`.
  Free-text `discipline`/`division` fields → validated selects. `test_disciplines`.
- **v0.3.80 — D2 (shipped): discipline-tagged model.** Record which discipline model each GUID came from in the
  properties index (source-file = authoritative discipline tag); `GET /elements?discipline=`; persist
  per-model transforms; discipline layer toggles + colour-by-discipline in the viewer.
- **v0.3.81 — D3 (shipped): discipline sheets.** `drawing_set` module; parse the NCS Sheet ID (discipline +
  sheet-type digit + sequence) into structured fields; `revision_register` module; `drawing↔spec_section`.
- **v0.3.82 — D4 (shipped): connect the procurement chain.** `bid_package.spec_sections` TEXT → reference array;
  `cost_code` link + shared discipline on bid_package/spec_section/cost_code; a `spine.py` traceability
  engine (discipline → models → sheets → specs → bid packages → cost codes → budget + coverage gaps).
- **v0.3.83–84 — D5 (shipped): discipline-aware generation.** Extend `generate/massing` to emit separate STR / ARCH /
  parametric-MEP models sharing one origin + storeys + a real `IfcGrid`, auto-registered with discipline
  tags, and seed the spec/bid/budget skeleton per discipline from the mapping table.

## Resourcing + Accounting depth (v0.3.117+)
A research-backed plan to deepen resource loading and construction accounting, keyed on cost code and
reusing the config engine's reference/rollup relational spine.
- **R (shipped v0.3.117) — Resource loading, real + relational.** A `resource_assignment` model ties a
  resource (labor / equipment / material + rate) to a **schedule activity** and a **cost code**. The engine
  produces a cost-loaded manpower histogram (by trade/type), cumulative unit + cost S-curves, over-allocation
  vs an availability cap, and a **leveling advisory** that smooths over-allocated work within its CPM float
  (critical-path work stays locked). Wired to a `👷 Resource loading` panel; `cost_code.resource_budget`
  rollup; falls back to activity `crew_size`.
- **A1 (shipped v0.3.118) — WIP schedule.** `wip.py` on top of `cost.py`: percentage-of-completion
  (cost-to-cost) → earned revenue vs billed → over-billing (contract liability) / under-billing (contract
  asset), retainage, gross profit, backlog, plus a portfolio WIP sorted by cash risk — the accounting twin
  to the earned-value module. `GET /projects/{id}/wip` + `/wip/portfolio`, a `📄 WIP Schedule` panel + report.
- **A2 (shipped v0.3.119–120) — Statements + GL.** `contractor.py` — POC income statement + contract-
  position balance-sheet section (asset/liability, retainage, AP, net contract working capital), per-job
  + company-wide. `accounting.py` — a standard construction chart of accounts + a balanced double-entry
  journal (job cost / billing / WIP POC adjustment → revenue nets to earned) + trial balance; 📒 General
  Ledger panel + the existing GL-CSV / QuickBooks-IIF export.
- **Moat (shipped v0.3.121) — Cost traceability by GlobalId.** `traceability.py` — cost lines (budget /
  commitment / direct cost / sub invoice) carry `element_guids`; the engine computes coverage (share of job
  cost tied to real model elements) overall and per cost code, and answers "what did this element cost?" by
  GlobalId. `GET /projects/{id}/cost/traceability` + `/elements/{guid}/costs`, a 🔗 Cost Traceability panel.
  The end-to-end model → resource → cost → GL link a cost-code-only ledger can't make.
- **I (planned) — Interop.** Balanced cost-coded journal-entry export to the accounting system of record
  through an approval gate; then derive WIP % complete and resource curves from **model quantities by
  GlobalId** (the coverage index above is the foundation).
