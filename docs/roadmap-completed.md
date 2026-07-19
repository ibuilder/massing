# Roadmap — completed / shipped archive

Historical reference: everything **already shipped**. The single **open** backlog lives in
[roadmap.md](roadmap.md) ("What's left"). Nothing here is a to-do — it's the record of what was built,
wave by wave and track by track, so the working roadmap can stay lean. Sections are in rough
chronological / thematic order; ✅ markers and version tags are the source of truth for *when*.

---

## 🗓 Session v0.3.493–509 (2026-07-19) — the ★ execution-queue wave (audit-synthesized)

The R15 landscape + codebase + security/perf audit pass (task #445) produced a re-prioritized
execution queue; this wave executed items #0–16 top-down, every one a verified CI-green release,
CodeQL 0 open alerts throughout. **Recurring audit correction:** the "orphaned capability" counts were
materially overstated — the workflow state machine, 4D element-linking, temp site-logistics geometry,
and most SURF-3/4 candidates already existed under other names — so each item narrowed to its genuine
delta after verifying by feature/route, not wrapper name.

- **#0 SEC-XSS (493)** — attachment stored-XSS closed: raster-allowlist inline, everything else
  `attachment` + nosniff + CSP sandbox.
- **#1–2 PERF-1/2 (494)** — event-loop-blocking pdf/import/upload ops → `run_in_threadpool`;
  `drawings.bake()` memoized + `world_bounds()` AABB fast path; 2 frontend listener leaks fixed.
- **#3 PERF-3 (495)** — `discipline_summary_file` mtime-keyed cache (was re-tessellating per GET);
  `clash_detect` durable job kind (narrow-phase clash off the request path).
- **#4 PERF-4 partial (496)** — TEST-FASTPATH (fresh-DB init skips `_ensure_columns/_indexes`;
  suite ~780s→~525s) + PAYLOAD-CAPS (`/topics` limit/offset, `/pins` hard cap). DASH-UNION et al
  remain open (see queue).
- **#5 PANEL-LAZY (497)** — ~30 secondary portal panels dynamic-imported (per-file chunks) out of
  the eager shell.
- **#6 SURF-1 (498)** — Schedule toolbar: P6/MSP import, predictive alerts, earned schedule surfaced.
- **#7 SURF-2 (499)** — Budget "📐 Estimate from the model" card: conceptual, resource-based (L/M/E),
  QTO-by-floor, DXF takeoff.
- **#8 SURF-3 (verified 499)** — already done; the audit's orphan flag was a false positive (viewer
  dispatches recipes by name via `authorAndReload`, bypassing typed wrappers).
- **#9 SURF-4 (500)** — viewer "🔍 Data QA" surfacing `/elements/qa` completeness with
  click-to-select-missing. **(501)** — fix(sec): the SURF-2 card wrote a DXF filename + server/model
  free-text into `innerHTML` unescaped (CodeQL js/xss-through-dom); `esc()` exported from `ui/charts`
  and applied.
- **#10 WORKFLOW-ENGINE (502) + WFE-2 (503)** — audit premise corrected (the state machine already
  shipped); genuine gaps closed: `party_owner` now tracks ball-in-court on every transition
  (`court_party`), and `escalation.py` turns the due-feed into action (L1/L2/L3 ladder,
  `escalation:L{n}` timeline entries the notifications feed surfaces, `GET/POST /escalations`,
  idempotent `escalation_scan` job kind). 503 = the portal-home escalation surface with one-click
  "escalate & notify".
- **#11 SCHED-P6 (504)** — the export half of the round-trip: `GET /schedule/export?fmt=xer|msp`
  serializes the LIVE schedule keyed by activity code (`to_xer`/`to_mspdi`); import auto-detects
  MSPDI too (`parse_mspdi`); re-import matches by code, no GUID drift. Export buttons on the panel.
- **#12 FOURD-SIM core (505)** — the viewer 4D playback (`viewer/fourD.ts`): scrub/auto-play through
  construction days, built-so-far shown, not-yet-built hidden, the day's completions amber; reusable
  `LayerManager.colorGuids/resetColors`. (Linking + temp geometry already existed — W9-5.)
- **#13 QUERY-DSL (506)** — the selector grammar over the property index (`query_dsl.py`:
  parse/matches/select; ops `= != >= <= > < ~` + existence) + `GET /model/select` + the viewer
  "🔎 Query-select" isolate tool. The reusable scoping spine.
- **#14 RULE-LIB (507)** — user-authored parametric rules on QUERY-DSL (scope + require + severity;
  `rule_library.py`, `GET/PUT /rules` atomic-validated, `GET /rules/run`, viewer "✔ Rule check").
- **#15 RESOURCE-LEVEL named baselines (508)** — `schedule_baselines.py`: a library of named
  snapshots (GMP/Recovery/…) + variance vs any chosen baseline (`/schedule/baselines` CRUD +
  `/baselines/{id|latest}/variance`) + the "📌 Baselines" drawer.
- **#16 MODEL-CI core (509)** — the pluggable check-pack runner (`model_ci.py` + `POST /ci/run` +
  `GET /ci/latest`) → pass/warn/fail badge artifact, seeded with RULE-LIB + data-completeness gates;
  viewer "▢ Model CI" tool.

## 🗓 Sessions v0.3.457–492 (2026-07-18/19) — the P1 run + P2 ring (pre-queue)

The 2026-07-18 re-prioritization's P1 list ran to completion, then the P2 ring advanced
opportunistically. Every item live-verified where the preview allowed.

**P1 (all shipped):** COLLAB-CURSORS (458 — peer view-cones/name tags; COLLAB-1 complete) ·
PREFLIGHT (459 — composed gate over health/classification/keynotes/QA/IDS/BCF, gates
`/drawing-set/issue`) · SITE-1 first slice (460 — OSM buildings/roads/land-use, cached, ODbL) ·
UX-2 snap (461 — vertex/midpoint/corner/center snapping + rubber guides) · EST-1 (462 — labour
estimate prices the QTO; `/schedule/from-estimate` upserts crew-day CPM activities) · REL-4 leaves
(463 collab/presence · 467 KEYS+dyn-input · 468 reportCenter · 481 measureSection) · JOB-QUEUE
artifact pattern (464 `compiled_set_pdf` + artifact streaming; 487 `model_export` .glb/.gltf) ·
3D-HERO (465) · SHEET-LINK (466 — cover-index GoTo links + callout-bubble anchors).

**P2 ring (shipped through 492):** RISK-BOARD (470) · CODE-1/3 jurisdiction+edition (471) · S4 undo
grouping (471) · B1 sign-in-first + AI read tools (472) · PROFORMA-LIVE + E7 live schedules (473) ·
NL-QA recipes + READY-AGENT (474) · BOARDS + cost calibration (475) · ENV-1 wind screen + VIZ-1
parity (476) · MEP sizing (pressure-loss/tray-fill/thermal) + VIZ-2 SSAO/bloom + B2 tour + CODE-4
amendments (477) · W10-4 auto_connect_mep + A1/A2/C1 provider prominence + REL-6 webhook privacy
(478) · B3/B4/C2 onboarding + SpecLink + F0b representations (479) · D8 COMcheck approvability→BCF
(480) · REL-5 bridge dataclasses + measureSection (481) · E6 design-option branches + E8 model
guardrails (483) · W9-6b program_fit (484) · W9-5 logistics motion + swept crane clash (485) ·
W9-4 doc_text cited retrieval (486) · REL-8 docstrings enforced (487) · E3 sketch-to-BIM
extrude/pull (488) · B5 connection assemblies (490) · UX-1 full ribbon merge (491) · R14 ring
planned + doc_text ReDoS round 2 (492). DISC-poché (469).

## 🗓 Session v0.3.413–425 (2026-07-17) — the four-lane audit → prioritized upgrade cycle

A full-platform evaluation (four parallel audit lanes: backend bugs, web frontend, docs/repo surface,
2026 industry research) produced the **🎯 Upgrade plan** in [roadmap.md](roadmap.md), then executed it
in priority order — every item its own verified CI-green release, CodeQL 0 throughout.

- **413 — docs/repo surface**: README de-staled + neutral wording; status pages live-badged; roadmap
  coherence; issue/PR templates; the plan itself.
- **P0 security (414–417)**: **SEC-TENANT** (portfolio/benchmark roll-ups membership-scoped — was a
  cross-tenant P&L/WIP leak; + search limit clamp + attachment predicate; `test_tenant_scoping.py`),
  **WEB-BOOT** (corrupted `aec-settings` no longer bricks the app), **SEC-GUARD** (production guard on
  any non-SQLite DB or `AEC_ENV=production`), **SEC-MCP** (membership authz in MCP dispatch).
- **P1 reliability (418–420)**: **WEB-LIVE** (SSE re-subscribe + disconnected surface) + **WEB-LEAKS**
  (drag-listener + preview-GPU leaks), **DOC-RACE** (per-project sidecar locks, 12-thread proof),
  **TZ-UTC** (one UTC clock across 7 aging engines — the fix tripped its own drift live in tests).
- **P2 docs/demo (421–422)**: **DEMO-REGEN** (Pages snapshot recaptured, 952 fixtures — was ~110
  releases stale), **README-TRIM** (983→560) + June-audit supersede banners.
- **P3 2026 capabilities (423–425)**: **SCHED-RISK** (Monte Carlo P10/50/80/90 over the CPM network,
  criticality index, delay drivers, PPC-calibrated tail), **CARBON-EC3** (per-element A1–A3 off the
  model, Buy Clean limit check, LEED-style inventory — LEED v5 mandate effective 2026-07-01),
  **PERMIT-CHECK** (submission-readiness report over the code engines + drawing register).

*P3 continued (426–431):* **UI-SURFACE** (426, first slice — Monte Carlo card in Schedule; Carbon-
compliance + Permit-readiness in Risk & Cost; 429 added the acceleration-levers card) · **QA-AGENT**
(427 — `drawing_qa` sheet-cited set review) · **LAYOUT-EXPORT** (№16 found already shipped in Wave 8) ·
**5D-BIND** (428 — `element_5d` GUID-keyed live cost+carbon rows, reprice-on-edit).

**OpenAEC / Open CAD Studio study (2026-07-17)** → the 🧭 CAD-UX lessons in roadmap.md; shipped from it:
**CADCMD** (430 — a deterministic CAD command line, `cadCommands.ts`, over the edit recipes: WALL/COLUMN/
BEAM/SLAB/LEVEL/SPACE + aliases + history + spacebar-repeat, 11 pure-parser tests) and **AUTHOR-MATRIX**
(431 — `authoring_matrix`, a live 76-recipe/14-category coverage table from `edit.RECIPES`, served at
`/reference/authoring-matrix`, committed to `docs/authoring-matrix.md`, guarded by a completeness test).
Detail in memory [[openaec-study-2026-07-17]].

*Remaining open (roadmap.md §🎯 / §🧭): UI-SURFACE №11 tail (unused-method triage), the №18 later-bucket,
and the CAD-UX lessons SNAP-KIT / CLIENT-LIMITS / VIEWER-FUNNEL / PLUGIN-REGISTRY / MCP-PACK /
SHEET-VIEWPORTS.*

## 🗓 Session v0.3.398–412 (2026-07-17) — code-gap closeouts + the REL-3 leaf marathon

Two arcs in one session: the **code-gap sweep** (verifiable analysis/QA wins pulled forward while
modularization looked stuck) and then — once the DEV-2 import-cycle guards made façade extractions safe —
the **REL-3 leaf marathon** that decomposed the worst files in the tree. 254/254 suites green at the end;
CodeQL 0 open alerts throughout. Detail in memory [[gap-sweep-2026-07-17]].

**Code-gap closeouts (398–401):**
- **MODEL-DIFF (398):** per-element fingerprints on every version snapshot (name · class · type · level ·
  Pset-hash · Qto-hash); `versions.diff` now reports **modified** elements + what changed (renamed /
  reclassified / retyped / re-leveled / properties / quantities); `/versions/diff` + viewer Version history
  with click-to-select-in-3D; `ModelVersion.fingerprints` JSON column auto-migrates.
- **FIN-TEST (399):** `test_leasemgmt.py` (escalation compounding, CAM recovery + over/under, renewal
  at-risk) + `test_changeorders.py` (CO pipeline by state, schedule-days excl. rejected, ball-in-court,
  ROM exposure) — hand-computed; math was already correct, now locked.
- **DRIFT (400):** `lateral.drift_check` (ASCE 7-22 §12.12.1 allowable Δa by Risk Category; §12.8.6 design
  drift Δ=Cd·δxe/Ie with per-story pass/fail) + `torsional_check` (§12.3.2.1 Type 1a/1b + Ax), wired into
  `lateral_from_model` + the `structure/lateral` endpoint.
- **IFC-QA (401):** `aec_data/roundtrip_qa.py` — `fingerprint` / `compare` (identical + lossless verdicts,
  per-dimension deltas, offender GUIDs) / `roundtrip` (write→reopen); `GET …/models/export-qa`.

**DEV-2 cycle guards (402–403):** `test_import_cycles.py` (stdlib ast + Tarjan over `aec_api`+`aec_data`
top-level imports) and `apps/web/src/no-import-cycles.test.ts` (runtime import graph, `import type`
excluded — tsc erases it). 0 cycles both sides; no new deps; a regression fails CI with the cycle path.

**REL-3 leaf marathon (404–412)**, each a leaf + façade re-export (zero caller change), each verified by
the guard + its suites: `connectors_mappings.py` (404, pure Procore field-mapping) · `drawings_render.py`
(405, sheet SVG/PDF renderers; `data/drawings.py` 941→788) · `edit_core.py` (406, the 9 authoring
primitives — the foundation that unblocked the recipe splits) · `connectors_vendors.py` (407, raw
Procore/ACC/QuickBooks/ERP HTTP clients; test seams stay on `connectors.py`; 495→325 total) ·
`edit_asbuilt.py` (408, phase/as-built/manufacturer/classification writers) · `edit_mep.py` (409, the
416-line MEP group) · `edit_struct.py` (410, walls/slabs/columns/beams/steel/rebar/footings) ·
`edit_annotate.py` (411, notes/dims/rev-clouds/tags) · `edit_enclosure.py` (412, coverings/railings/
roofs/hosted openings). **`edit.py` 2127→761 (−64%)**; remainder is the genuine engine core.

---

## 🗓 Session v0.3.393–397 (2026-07-17) — dev-velocity & modularization

The pivot from features to **making development faster + the codebase more maintainable** (the release cycle
was the bottleneck). Detail in memory [[weekend-push-2026-07-17]].

- **DEV-1 — parallel test gate (393):** `run_tests.py` runs the ~180 isolated `test_*.py` through a bounded
  `ThreadPoolExecutor` + a geometry worker cap (`AEC_GEOM_WORKERS=1` via new `aec_data/geomconf.py`, so each
  test is single-threaded and the outer parallelism owns the cores — no cpu×cpu oversubscription) +
  `PYTHONUTF8=1`/utf-8 capture. **~30 min → ~11 min (2.7×)**, 250/250 green, prod geom default unchanged.
- **REL-3 modularization — 4 clean slices**, each a leaf + façade re-export at the old path (zero caller
  change): codecheck egress → `codecheck_egress.py` (394, 502→184); module full-text search →
  `modules_search.py` DI leaf (395); computed schedules → `drawing_schedules.py` (396, `drawing.py` 941→821);
  **the registry+table foundation → `modules_registry.py`** (397, `modules.py` 969→882) — the enabling
  extraction that lets the CRUD/feed layers split without a cycle.
- Roadmap reorganized: dev-velocity/modularization made the top focus; large feature/infra bets tracked for
  later. The ruff-autofix hook fixed to use `$CLAUDE_PROJECT_DIR`.

## 🗓 Session v0.3.380–392 (2026-07-17) — analysis engines, deliverables, dev-tooling

The **complete W10-7 analytical model** + preliminary analyses, the top enterprise deliverable/cleanup gaps,
and the ruff-autofix dev hook. All direct-to-main, each CI-green + 0 CodeQL alerts. Detail in memory
[[weekend-push-2026-07-17]].

**Authoring UX** — **KEYS** Revit-style 2-letter draw shortcuts (380). **PREFLIGHT** one-click PASS/HOLD
issuance gate composing the model-health lenses + classification completeness + open blockers (381).

**Structural analysis (the analytical model is now complete + solver-ready):**
- **STRUCT-SOLVE** (382) — gravity load case → determinate member statics (reactions, shear/moment/deflection
  diagrams); `aec_api/struct_solve.py`, `GET /structure/solve`.
- **STRUCT-LATERAL** (389) — ASCE 7 §12.8 seismic ELF + simplified MWFRS wind → base shear + story
  forces/shears/overturning, governing flagged; `aec_api/lateral.py`.
- **STRUCT-LOADS-IFC** (390) — `apply_structural_loads` writes `IfcStructuralLinearAction` (D+L) onto every
  analytical member → loaded IFC.
- **Analytical shear walls** (391) — load-bearing walls → vertical mid-plane `IfcStructuralSurfaceMember`s.
- **Analytical supports** (392) — `apply_structural_supports` fixes base nodes (pinned/fixed
  `IfcBoundaryNodeCondition`) → a complete, solvable analytical IFC handed off to SAP2000/RISA/Robot.

**MEP** — **MEP-SIZE** (386) air/water velocity checks vs ASHRAE/erosion limits + NEC tray fill,
`aec_data/mep_sizing.py`, `GET /mep/sizing`.

**Construction docs / deliverables** — **VIEW-RANGE** (383) plan view-depth (foundations below the cut as
dashed lines); **COVER-SHEET** (384) rendered cover + key-plan thumbnail + discipline-grouped paginated
index; **EXPORT** (387) binary glTF `.glb` + first-class IFC re-export; **TAKEOFF-2D** (388) drawing-based
quantity takeoff → the 5D estimate.

**Code health** — **DISC-SSOT** (385) sheet-series is now a derived view of the one discipline map
(`classification.series_of_ifc_class`; `sheetgen`/cover private tables removed). Self-authored **ruff-autofix
PostToolUse hook** (`.claude/hooks/ruff_fix.py`, `$CLAUDE_PROJECT_DIR`).

## 🗓 Session v0.3.352–377 (2026-07-16/17) — frontier tracks, UX, hardening, deliverables

**Discipline / classification depth** — DISC-coverage report (`/elements/by-discipline` completeness view,
v0.3.352); DISC-cw context-aware curtain-wall/roof member classification via the index `host` field (353).

**Construction documents** — D5 PDF detail callouts + real sheet refs (354); W10-6 room-schedule
`IfcElementQuantity` depth (356); **compiled drawing-set PDF** — the whole set in one file (375);
**shareable project package** PDF — overview + drawings + cost + proforma (377).

**MEP / structural** — W10-4 MEP design flow-rate psets (355); **W10-7 structural analytical model** —
`IfcStructuralAnalysisModel` from the frame (curve members, 357) + surface members from slabs (358).

**RFI-0 / W9-4** — the **document/specification graph** + cited element provenance (359) and the
**NL-QA** cited-answer layer (360).

**COLLAB-1 real-time co-editing** — model-edit SSE stream + presence snapshot (361), optimistic edit-lock
(362), the viewer presence + reload-banner wiring (366).

**AUTH-VS visual node authoring** — the recipe-graph execution engine (363) + the draggable node canvas
(367).

**Web client + designer-workspace UX** — typed client bridge to the new engines (364); the Ask-the-model
box + structural-analytical panel (365); UX-3 Library search operators + Recent (368); UX-4
Project-Browser spine (369); UX-1 lifecycle ribbon tabs (370).

**Reliability / security / relationships** — security hardening pass (XXE-safe P6 parser, non-crypto hash
flags, pillow pin, clean audit — 371); openModule O(n·m)→Map + import-cycle false-positive verification
(373); **model estimate → developer proforma** hard-cost sync (376). Docs refreshed to v0.3.372.

---

## ★ Recent releases — v0.3.313–335 (discipline tree · UX-2 annotation · MEP-FP · CODE-EBC)

Moved out of the working roadmap so it holds only open items.

**🗂 DISC — unified discipline tree (v0.3.330–335).** One CSI-MasterFormat/UniFormat/NCS vocabulary + colour
palette across the viewer, model browser, estimate, and both packages.
- **DISC-1 (v0.3.330)** — canonical `DISCIPLINE_COLORS` + `discipline_color()` (fire=red…telecom=purple; FA
  swatch distinct from FP); full IFC-class→discipline coverage (`_IFC_DISCIPLINE`) for MEP/fire/electrical/
  telecom entities the MasterFormat map missed; `discipline_tree()` (colour + divisions + uniformat + sheet
  series + rolled-up IFC classes + `ifc_class_discipline`), served on `GET /reference/disciplines`.
- **DISC-2 (v0.3.331)** — a **Color by** toggle (IFC class ↔ Discipline) on the IFC-classes panel + a legend
  of disciplines present + a **Paint model** button; `tree.ts` consumes the served map (`setDisciplineLookup`)
  instead of its regex; rebar/mesh/tendon → Structural.
- **DISC-3a (v0.3.334)** — `estimate.by_discipline` (really per-IFC-class) now tags each priced line with its
  discipline + adds a true `by_discipline_rollup`; per-class detail kept as `by_class`.
- **DISC-3b (v0.3.335)** — new `aec_data/disciplines.py` holds the canonical `MF_DIVISIONS` + colour palette;
  `classification.py` imports them (drops copies) and `specmanual` drops its duplicate `_DIVISIONS` — one
  source across both packages (aec_api can import aec_data, not vice-versa).
- **DISC-4a (v0.3.332)** — `add_fa_device` (smoke/heat detector `IfcSensor`; pull-station/horn-strobe/bell/FACP
  `IfcAlarm`) on a **Fire Alarm** system; `add_comms_device` (MDF/IDF/switch/WAP `IfcCommunicationsAppliance`,
  data outlet `IfcOutlet`) on a **Telecommunications** system.
- **DISC-4b (v0.3.333)** — 🔔 Fire-alarm + 📶 Telecom tool buttons; demo tower rebuilt with a unitized
  `IfcCurtainWall` facade, 286 fire-rated walls (2-hr core / 1-hr demising), an `IfcRoof` assembly, 90
  detectors + 61 alarm devices, 37 telecom devices — all 8 disciplines colored distinctly.

**🏷 UX-2 — interactive annotation (v0.3.323–328).** `add_annotation` text notes (v0.3.323) · `add_dimension`
two-click dimensions (v0.3.324) · `add_revision_cloud` + **plan rendering of view-placed annotations**
(v0.3.327) · `add_tag` element-aware tags auto-read from the host, assigned via `IfcRelAssignsToProduct`
(v0.3.328). Closed the author→sheet loop the baked-SVG path couldn't.

**🧯 MEP-FP — fire protection as a first-class system (v0.3.311–319).** Discipline via `PredefinedType` +
`add_mep_*` discipline arg + `set_system_predefined` (v0.3.311) · `add_fire_equipment` sprinkler/hose-reel/FDC/
hydrant/pump (v0.3.315) · NFPA-13 `sprinkler_coverage` pre-check (v0.3.316) · `add_riser` vertical standpipes/
stacks/vents (v0.3.319).

**Other v0.3.313–329.** CODE-EBC IEBC Work-Area classifier (v0.3.310) · RFI-0→BCF decision-readiness promotion
(v0.3.313) · EST-1 material/equipment `full_estimate` (v0.3.314) · CONTENT-1 mesh import + auto-classify
(v0.3.321) · A4 LLM scene-digest (v0.3.322) · G3 O&M/warranty doc refs (v0.3.318) · the `open_model` stale-cache
fix keyed by (path, mtime, size) (v0.3.325) · QTO length derivation so linear MEP/railing prices non-zero
(v0.3.329) · Capacitor 6→7 clearing the tar CVEs (v0.3.312).

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

## ☆ Wave 8 — 2026 field-research upgrades (6 of 7 SHIPPED, v0.3.203–210)

> **Status:** ① clash-coordination intelligence (v0.3.203) · ② model→field layout (v0.3.204) · ④ load
> takedown (v0.3.205) · ⑤ model hygiene (v0.3.206) · ⑥ CEP generator (v0.3.207) · ③(a) Gaussian-splat
> reality capture (v0.3.208) · ③(b) verified-as-built progress (v0.3.210) — **all shipped.** Only ⑦
> (compliant syndication) is open, and it is **deferred by decision to a licensed-platform connector**
> (see the top "What's left" section). The per-track detail below is retained for reference.

**Field scan #2 — coverage validation (pics8, 2026-07).** A second 11-image industry-reference scan (LOD
100–500 ×3, IFC-vs-Shop-vs-As-Built drawings, PMBOK PM domains, the BIM 3D→7D master guide, the PM
strategy→benefits delivery workflow ×2, "one model, every discipline", the clash-resolution workflow, and
the 10-part CEP) was reviewed for new opportunities. **Result: no new tracks — every theme already ships**
(LOD matrix; submittals/drawing-set/as-built + verified-as-built; risk/stakeholder/quality/cost/schedule/
procurement/closeout; all 7 BIM dimensions incl. 5D cost + 6D carbon/ESG + 7D CMMS/twin; project-health +
portfolio; discipline spine + federation; Wave 8 ① clash coordination; Wave 8 ⑥ CEP). Shop drawings are
covered as a `submittal` type ("Shop Drawing"). The one micro-observation — **FF&E / furnishings** — was
folded in additively (v0.3.212): the furnishing IFC classes now classify to MasterFormat Division 12, so
FF&E takes off and procures correctly without a risky discipline-taxonomy change. Otherwise this scan is a
confirmation that platform breadth matches the reference material, not a backlog addition.

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
workflow**. The proven industry pattern (model-coordination platforms + the buildingSMART BCF
standard): a **two-layer model** — ephemeral `Clash` rows (thousands, regenerated per run) vs persistent
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
The BuiltWorlds Robotics-Top-50 sheet points at the 2026 field-robotics wave (floor-printing robots,
layout/drilling robots, robotic total stations). They all consume two open primitives from the model:
a **PENZD/PNEZD points CSV** (Point-№, Easting, Northing, Z, Description) and **DXF linework** (for floor
printers). Build a **`model → layout CSV`** exporter (grid intersections from `IfcGrid`, wall control
lines, MEP hanger/anchor points, sleeve/penetration centroids, column setout — Description encodes type +
IFC GlobalId; real-world E/N/Z via our set-origin handling) and a **`model → DXF`** layered drawing
(`ezdxf`, MIT). Close the loop: import measured total-station shots, match by Point-№/GUID, and write a
**BCF topic per out-of-tolerance point** — as-built verification becomes another BCF type on our existing
pin/RFI spine. Monetizes "IFC as the source of truth"; no new heavy deps.

**③ Reality walkthrough + schedule-linked verified-as-built (high visual differentiation).**
**Part (a) SHIPPED v0.3.208.** From the `photosynth-to-massing` brief. Two parts: (a) a **3D Gaussian-splat
"reality" layer** in the viewer — photoreal, phone-captured, co-registered with the IFC + LAS/LAZ we
already load; delivered via `@mkkellogg/gaussian-splats-3d` (MIT), lazy-loaded as its own chunk (out of
the app-shell bundle), offline (bundled inline sort worker, in-memory object URL — no CDN), routed through
the existing reference-overlay flow (`.splat` / `.ksplat`, plus splat-PLY content detection) with worker
teardown on removal; the permissive capture path is `gsplat`/Nerfstudio (Apache-2.0) — *avoid the original
Inria 3DGS (non-commercial)*. **Part (b) SHIPPED v0.3.210** — `field_verification` module (per-element,
GlobalId-anchored, workflow = verification state) + `verified_progress.py` roll element verification up to
each schedule activity as **verified-in-place % vs claimed %** with the **trust gap** (the OpenSpace /
Disperse / Buildots value proposition, pure software for us); `seed_from_layout` turns an as-installed
`layout.verify` result into verification records; viewer tool + Report Center report. Original brief:
Turn our **deviation heatmap into progress** — per-element capture/verification state + % complete tied
to schedule tasks. Add **E57 polish** on the
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

**⑤ Model-hygiene checker (quick win). — SHIPPED v0.3.206.** The "Common Revit mistakes" sheet + the
Revit-MCP portfolio's *Model Checker / Duplicates Resolver*. `model_qa.py` now covers **geometric
hygiene**: duplicate GUIDs, overlapping duplicate elements, orphaned elements, unenclosed rooms/spaces,
blank names, and (new) **elements on the wrong storey** — GUID-anchored, guarded, scored, feeding the
Model-QA report/BCF issues.

**⑥ Construction Execution Plan (CEP) generator. — SHIPPED v0.3.207.** The 10-part "How to prepare a CEP"
sheet. `_cep` report builder assembles a 10-section CEP (org/RACI · scope/WBS · master schedule &
milestones · procurement/subs · cost & change control · safety · quality · submittal/RFI procedures ·
permits · closeout/turnover) live from the construction modules + summary engines, PDF/Excel via the
existing report stack, auto-surfaced in the Report Center (group *Quality*). ISO 21502 / CMAA practice
areas paraphrased in original prose. A CEP is the
*superset* of a BEP (the BEP governs the model; the CEP governs the work). We already hold the data:
section-templated generator (scope · stakeholder/RACI · site logistics · work packaging/pull-plan ·
resources · cost/schedule/risk + EVM · quality/ITP · HSE/resilience · procurement/subs · commissioning/
COBie-G704) auto-populated from existing modules, BEP linked as an appendix (not duplicated). Reuse the
report/PDF stack; cite ISO 21502 / CMAA practice areas in original prose (no copyrighted text, no
competitor names).

**⑦ Compliant syndication / investor-management depth — cap-table-first, token-last (strategic, legal-gated).**
From the two tokenization briefs. The validated best practice across regulated securities platforms and
the non-token fund-administration gold standards: a securities platform is **~80 % a regulated
investor-management system, ~20 % blockchain** — Postgres is the legal source of truth, the token an
optional mirror. We already have proforma, JV waterfall, LP portal, capital calls, cap-table.

**DECISION (revised) — integrate, don't build.** We will **not** build the securities/compliance stack
ourselves (KYC/accreditation, transfer-agent recordkeeping, Reg-D compliance engine, escrow, the token) —
that is licensed, counsel-gated, multi-year work and outside our risk appetite. Instead Massing stays the
**origination front-end** (the deal, the IFC model, the proforma, the JV waterfall, a read-only cap-table
view) and **hands the regulated pieces to a licensed platform via API** — the same "connectors OK, we
never move money" posture as our Procore / QuickBooks bridges. Confirmed integration path: **a licensed
securities platform** — an SEC-registered **transfer agent + broker-dealer/ATS** — exposing a **partner
connect API**, a **RESTful KYC/KYB/AML identity service**, and **Transfer-Agent-as-a-Service**; for the
non-token fund-admin route, hand off to a fund administrator (data export / referral). So the buildable work shrinks to a
**thin connector** (`connectors.py` already has the pattern): push deal + investor + distribution data to
the partner, pull back verified-KYC / holder-of-record status, deep-link investors into the partner's
onboarding, and show the partner's cap-table state in the LP portal. The token (ERC-3643) is the
partner's concern, not ours; its T-REX reference being **GPL-3.0** is now moot for us. ⚖️ *Not legal
advice; the partner is the licensed entity.*

**Sequencing recommendation:** ① and ② are the near-term, highest-leverage, lowest-risk builds (both pure
software on existing seams). ③–⑥ are self-contained increments to schedule by customer pull. ⑦ is now a
**lightweight integration** (a licensed-securities-platform connector) rather than a build — pursue only
when a customer needs to actually raise/syndicate, and keep Massing out of the regulated path entirely.

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
ecosystems + interoperability (ongoing industry M&A). Our open, IFC-native, self-hosted, one-model
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
- **Custom Revit export plugin?** ❌ **Not needed (decided 2026-06).** Autodesk's
  [revit-ifc](https://github.com/Autodesk/revit-ifc) is the official, free, open-source, *certified*
  IFC exporter for Revit 2019+ (ships natively; an OSS override exists) — a custom plugin would just
  duplicate it. Coordination/review tools are not authoring apps and their IFC export is
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

---

## 🏗️ Wave 9–11 — authoring suite + Master Builder + AI-MCP (shipped)

The in-browser authoring push and everything downstream of it. Version tags + a one-line note per shipped
item; the still-open remainder of each track lives in [roadmap.md](roadmap.md).

### Model workspace → true in-browser authoring program (P1–P6, v0.3.231–241)
The 2026-07 direction change: the Model workspace became a genuine authoring+coordination program
(create from scratch → draw/edit by GUID-stable recipe → drag-to-move → clash/coordinate).
- **P1** blank model from scratch (`generate_blank_ifc` + `POST …/model/blank`) + first-class Author-mode surfacing (v0.3.231)
- **P2** removed redundant legacy place buttons + ~90 lines dead code — Draft panel is the single authoring surface (v0.3.232)
- **P3** room/space authoring UI (➕ Add rooms/spaces via `add_spaces`) (v0.3.234)
- **P4** author-ready **template picker** — blank + office bay / residential floor / warehouse (v0.3.233)
- **P6a** cut four duplicative rail sections → deep-links; removed ~700 lines (v0.3.235)
- **P6b** dedicated **💥 Clash & coordination** rail toggle (federated + single clash, list, metrics, promote-to-BCF) (v0.3.236)
- **P6c** rail re-clustered **Navigate / Author / Coordinate** (v0.3.237)
- **P6d** docked **📋 Properties** rail panel with a Type/Instance identity header (v0.3.238)
- **Model browser** — **group-by** (level / discipline / IFC class / type-family) + **search** across name·GUID·class·type·discipline, auto-expanding matches (v0.3.239)
- **Manage levels** — per-storey rename + set-elevation (`rename_storey`/`set_storey_elevation`; storey listing carries GUIDs) (v0.3.240)
- **Selection sets** — named saved searches you can isolate in one click, persisted per-project (v0.3.240)
- **P5 edit-in-place** — drag-to-move transform gizmo (ghost preview + ΔE/ΔN/ΔZ + grid-snap) via the GUID-stable `move_element` recipe (v0.3.241)

### Wave 9 — 2026-07 research scan (v0.3.245–251)
- **W9-1** property mapping / normalization — the **transform** verb between IDS-validate and COBie-export (`propmap.py`, `map_properties` recipe, `/propmap/detect`+`/plan`, 🔧 Normalize properties) (v0.3.245)
- **W9-2** computed **occupancy load + egress capacity** (IBC 1004.5/1010.1.1/1006.2; `codecheck.egress_analysis`, `/codecheck/egress`, 🏛 Occupancy & egress) (v0.3.246); **W9-2b** BCF round-trip (`POST /codecheck/egress/bcf`) (v0.3.251). *Fire-separation between occupancies still deferred (needs space-boundary geometry).*
- **W9-3** IFC5-style **property-override layers** — USD-like non-destructive overlays, strongest-wins, `bake` flattens to a GUID-stable IFC (`layers.py`, `/layers`+`/resolve`+`/bake`, `apply_layers`, 🧬 Property layers) (v0.3.247)
- **W9-4 v1** semantic **model graph** from IFC relationships — multi-hop cited neighbor queries (`graph.py`, `/graph/neighbors`, 🕸 Related elements) (v0.3.248). *Harder half (spec/drawing/code ingest + NL→graph) still open — see roadmap.md.*
- **W9-5 (M first step)** site logistics on the 4D timeline — temporary resources as first-class time-phased 3D glyphs (`logistics.py`, `/logistics`+`/state`, 🏗 Site logistics) (v0.3.250). *L part (motion along paths + swept crane-reach clash) still open.*
- **W9-6a** generative fit-out — **auto-furnish** grids real `IfcFurnishingElement` into every `IfcSpace` (`furnish_spaces` recipe, 🪑 Furnish spaces) (v0.3.249)

### ① Generative-design & analysis depth — DONE (v0.3.215–227)
- **Test Fit** — daylight-limited plate-depth **optimize** + `core_efficiency` (v0.3.215); polygon-offset buildable footprint + parcel-bound surface parking (v0.3.221)
- **Structural generative** — per-floor column taper by √(floors carried) + sized lateral RC core, extruded as real shear walls (v0.3.220)
- **Underwriting realism** — exit-cap-vs-comps guardrails (v0.3.216); specialty P&L + ramp + blended-vs-RE IRR (v0.3.222); Monte-Carlo the specialty risk discount → blended-IRR distribution (v0.3.223)
- **Lean / takt** — `takt.progress()` + actuals overlay (floor variance, achieved vs planned, PPC) (v0.3.224)
- **Rendering / computational** — material editor + per-project palette (v0.3.225); module-relations graph view (v0.3.226). *Heavier GPU work (real-time GI / baked AO / HDRI skies) is a documented web-viewer non-goal.*
- **Developer deliverable** — investment pitch deck expanded to 9 slides (exec summary, capital stack, business plan) (v0.3.227)

### ② UX / performance / productivity — DONE (v0.3.228–242)
- **Role landing dashboards** — tailored Design / Developer / Finance homes (v0.3.228)
- **Nav density** — per-stage collapse memory (v0.3.230) + command-center density toggle (⊞/⊟, persisted) (v0.3.242)
- **A11y** — audited this cycle's new panels (SVG accessible names, labeled controls, `scope` headers, `.sr-only`) (v0.3.229); ongoing as panels ship
- ⌘K, saved-views-per-role, cross-workspace deep-links (both directions), and the `portal.ts` per-domain split all shipped earlier

### ③ Interop / library evaluations (v0.3.243)
- **L1** `@ifc-lite/geometry` server-side converter spike — **EVALUATED → DEFER**: the current Fragments path converts a 1.6 MB IFC → `.frag` in ~1.1 s, no bottleneck at our model scale. *Re-trigger: a customer with ≳50 MB IFC where conversion latency bites.*
- **L4** FreeCAD headless engine — **EVALUATED → DEFER**: parametric families + 2D drawings are already covered by `ifcopenshell` recipes + `drawings.py` + `sheetgen.py`. *Re-trigger: a concrete parametric op `ifcopenshell` cannot express.*
- **glTF import overlay** — already ships (`referenceLoader.ts` parses `.gltf`/`.glb` into a view-only reference overlay)
- **pyRevit "Publish to Massing" macro** — already ships (`integrations/pyrevit/Massing.extension`: export IFC → upload → convert → open; no paid bridge)
- **RVT→IFC via the paid Autodesk bridge** — hardened (v0.3.243): a properly-gated Design-Automation stub + input validation + `test_aps.py` locking the gate order (501 → 400 → 402 → 400 → 502)

### Wave 10 — IFC authoring suite (shipped parts)
- **W10-1** real type/family system — `create_type`/`edit_type_params` (in-place shared-box propagation, GUID-stable)/`assign_material_set`, `type_detail` inspector, 🧱 Family types browser (v0.3.252)
- **W10-3** groups, assemblies, arrays — `create_group`/`ungroup`, `create_assembly`, `array_element`, 🧩 Groups & arrays viewer tool (v0.3.253)
- **W10-8** phasing — `set_phase` tags new/existing/demolish/temporary via `Massing_Phasing.Status`, `phase_summary`, 🕐 Phasing tool (v0.3.254). *Tying phase to the 4D slider remains a sub-item.*

### Wave 11 — The Master Builder (shipped parts, v0.3.255–279)
- **E9** selector DSL (`query_elements` + 🔎 Query + `GET /query`) + `geom.tree` spatial index (v0.3.255)
- **F0** the representation/context spine + LOD state — `ensure_contexts` (Model+Plan roots, Body/Axis/Box/FootPrint/Annotation subcontexts), `set_lod`/`lod_summary` (`Pset_MassingLOD.Stage` 100→500), 📶 Level of Development tool (v0.3.256). *F0b (derive Box/Axis/FootPrint from Body) still open.*
- **B2** parametric door/window generators — `geometry.add_door/window_representation` (real lining/frame/panels, wall-sized lining, box-proxy fallback) (v0.3.257)
- **D4** classification + document carriers — `classify` → `IfcRelAssociatesClassification` (UniFormat/MasterFormat/OmniClass/Uniclass), `attach_document` → `IfcRelAssociatesDocument`, `element_detailing` inspector, 🏷 Detailing tool (v0.3.258)
- **D3** IDS-shaped detail-rule engine — `apply_rules` (applicability facets → content bundle via the Track-D carriers), `validate_rules` (missing-keynote pre-flight), ✨ Auto-detail tool + seed library (v0.3.259); **D7** the window-flashing worked case ships in the seed library (exterior window → IBC §1404.4/ASTM E2112/AAMA 711 flashing + 08 51 00)
- **C1** plan-drawing generator — `drawing.py::plan_svg` derives footprints **directly from authored extruded-profile geometry** (no OCC), class-styled poché scaled to paper mm, storey-scoped, 🖨 Generate plan (v0.3.260)
- **C2** overall dimension strings + keynote bubbles & legend generated from each element's Track-D classification codes (v0.3.261)
- **C3** issuable ARCH-D **sheet + titleblock** (`drawing.py::sheet_svg`, 📄 Issue sheet) (v0.3.262); **C3b** the sheet rendered **to PDF** via reportlab — the submittable AHJ deliverable (`sheet_pdf`, ⤓ Sheet PDF) (v0.3.263)
- **C4** computed **door/window/room schedules** (`drawing.py::schedules`/`schedule_svg`, 📋 Schedules) (v0.3.264)
- **B6** domain-geometry catalog — steel connections (`connections.py::add_base_plate`/`add_shear_tab`, 🔩) (v0.3.265) · rebar cages (`rebar.py::add_rebar_cage`, 🪝) (v0.3.266) · MEP fittings + connected systems (`add_mep_fitting`, `mep.py::mep_summary`, 🔀) (v0.3.268; also fixed a `sheet_svg` empty-model crash + `test_wave11_edges.py`) · curtain-wall (`curtainwall.py::add_curtain_wall`, 🪟) (v0.3.270)
- **D1** code-analysis summary — `codecheck.code_analysis` (occupancy Ch.3, construction type + Table 601, allowable area 506.2/504/506.3, occupant load 1004.5 + egress Ch.10), 🏛 Code analysis QA tool, `/codecheck/analysis` (v0.3.274)
- **C5** sections & elevations reachable — 📐 Sections & elevations tool (cut X–X/Y–Y sections + projected N/S/E/W elevations from `drawings.py`, auto-centred cut); also fixed a world-placement bug so all 2D output places off-origin elements correctly (v0.3.276)
- **G1** LOD-500 verified-as-built — `verify_asbuilt` stamps `Massing_AsBuilt` (VERIFIED + provenance), `asbuilt_summary` → readiness % by method, `/lod500`, ✅ As-built verify tool (v0.3.279)

### AI-MCP / NL authoring (shipped, v0.3.271–278)
- **S1+S2** natural-language authoring over the edit-recipe engine — `nlauthor.py` (`RECIPE_SPECS` + `validate_call` guardrail + keyword `interpret`), `POST /ai/author` (interpret-only, confirm-before-apply), ✨ command bar. Deterministic no-API-key baseline (v0.3.271)
- **S3** multi-step LLM interpretation — `nl_ai.plan()` produces a structured JSON plan against `RECIPE_SPECS` ("a 5×4 m room" → 4 walls); every step re-validated by `validate_call`, GUIDs filled from selection (never fabricated), destructive recipes withheld, keyword fallback; ✓ Apply-all chains edits into one republish (v0.3.278)
- **S3 fix** — `_PLAN_SCHEMA` params were an open object (strict structured-output 400s); params now a JSON string parsed by `_coerce_params`; apply-all recovers from a mid-chain failure (republishes what applied, reports "stopped after N/M") (v0.3.280)

### Wave 11 — CD-set finish + code intelligence + LOD-500 turnover (v0.3.281–293)
- **C6 DXF export** — `dxf.py` dependency-free R12 writer; `plan_dxf`/`section_dxf`/`elevation_dxf` on named layers + `.dxf` endpoints + ⤓ DXF buttons (v0.3.281)
- **C6 schedules-on-a-PDF-sheet** — `drawing.schedule_pdf` lays the door/window/room schedules on an ARCH-D titleblock sheet; `GET /drawings/schedule.pdf`, 📋 Schedules sheet tool; titleblock factored to a shared `_titleblock_pdf` (v0.3.282). **The construction-document set is now complete** (plans/sections/elevations/schedules → SVG/PDF/DXF).
- **E4 progressive-disclosure toolbar** — everyday authoring + drawing tools visible; LOD-350/400 fabrication + detailing tools behind a persisted "🔧 Advanced fabrication tools" toggle (v0.3.283)
- **E8 authoring guardrails (first slice)** — `guards.py::precheck` enforced in `apply_recipe` (finite coords, no zero-length lines, positive dims, valid enums, required refs) + `POST /edit/precheck`; blocks broken edits, warns on unit-slip magnitudes; verified against 49 recipe-exercising tests (v0.3.284)
- **CODE-1 jurisdiction catalog** — `codes.py` code-family/edition catalog + `resolve(jurisdiction)` → adopted editions with a national-baseline fallback + mandatory verify-with-AHJ note; `GET /codes/{families,adoptions,seeded}`; copyright-safe facts only (v0.3.285)
- **CODE-3 edition-aware code analysis (first slice)** — `code_analysis` resolves the jurisdiction's adopted IBC edition and names it in the badge/citations/disclaimer; `?jurisdiction=` + a Jurisdiction field (v0.3.286)
- **Hardening** — whitelist Content-Disposition filename segments on the DXF/PDF drawing endpoints (defence-in-depth after a clean security review) (v0.3.287)
- **Dependency hygiene** — bump vitest 3 + happy-dom 20 to clear 4 critical Dependabot advisories (dev/test-only); full web suite re-verified (v0.3.288)
- **D6 3-part MasterFormat project manual** — `specmanual.py` groups elements into CSI divisions → sections, SectionFormat Part 1/2/3 (Part 3 Execution from attached install docs); `GET /spec/manual{,.txt}` + 📖 Project manual tool (v0.3.289)
- **D8 approvability pre-flight** — `codecheck.approvability` runs a plan-reviewer checklist (egress capacity, door clear width, two-exits, occupancy classification, substantiated fire-rated assemblies), each cited, with a readiness score; `GET /codecheck/approvability` + ✅ pre-flight tool that isolates flags (v0.3.290)
- **G3 manufacturer/serial (O&M/turnover)** — `set_manufacturer_info` stamps the standard `Pset_ManufacturerTypeInformation`/`Pset_ManufacturerOccurrence`; `asbuilt_summary` counts with_manufacturer/with_serial; stamp form in the as-built tool (v0.3.291)
- **Debug fixes** — a post-release audit caught two wrong-result bugs: `specmanual` layer-set materials never surfaced (now resolves `IfcMaterialLayerSetUsage` → layer materials); D8 occupancy check counted free-text `LongName` (now gates on `Pset_SpaceOccupancyRequirements.OccupancyType`); both regression-tested (v0.3.292)
- **Model Health — Code & permit-readiness lens** — the composite scorecard gains a fifth lens from the D8 pre-flight, so the single "is my project healthy?" number now spans integrity, ISO-19650, clash, verified-as-built, and permit-readiness (v0.3.293)

### Roadmap hygiene + docs (2026-07)
- Reorganized the roadmap so the active file holds only open work; moved every shipped item to this archive; removed all competitor name-drops from both files; refreshed README / in-app guide / Pages landing to the current end-to-end capability.



---

# Archived roadmap snapshot — 2026-07-18 (pre-reprioritization, at v0.3.456)

Everything below is the full roadmap as it stood after the v0.3.441–456 arc (audit remediation ·
GEN-SCORE · PLUGIN-REGISTRY · VIEWER-FUNNEL · perf · authoring split · JOB-QUEUE · SHEET-VIEWPORTS
server+editor · the Gate-A breakthrough — the "preparing geometry" fix — · SNAP-KIT completion ·
REL-4 slices 1–2). Every ✅/🟡-shipped entry here is the permanent completed record; the still-open
items were re-extracted into the rewritten, re-prioritized live [roadmap.md](roadmap.md).

# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.450** (the audit-remediation + roadmap-completion arc
v0.3.441–450: audit fixes, GEN-SCORE, PLUGIN-REGISTRY, VIEWER-FUNNEL, perf, the authoring split,
JOB-QUEUE, SHEET-VIEWPORTS server slice — every buildable open item shipped; the remainder is
explicitly gated in the ⛔ section below). Recent waves
(v0.3.393–431): the **dev-velocity & modularization program** — test gate parallelized ~30→~11 min,
backend + web **import-cycle guards** in CI, and the worst hotspots decomposed behind façades (`edit.py`
2127→761 via a foundation + five recipe leaves; `connectors.py` and the sheet renderers split the same
way) — plus the **code-gap closeouts**: element-level **MODEL-DIFF**, ASCE 7 **DRIFT** screen, **FIN-TEST**
money-math locks, and the **IFC-QA** export round-trip fidelity check. Full record in
[roadmap-completed.md](roadmap-completed.md).

> **This file holds only what is still OPEN.** Everything shipped — every wave, track, and release — lives in
> [roadmap-completed.md](roadmap-completed.md), so *what's left* is never buried under *what's done*. The
> Model workspace is a genuine authoring + coordination program (from-scratch models, GUID-stable
> draw/edit recipes, drag-to-move, model browser, levels, selection sets, the construction-document set, code
> intelligence, the discipline tree). What remains is **the UX consolidation of that capability** plus
> incremental depth, spikes, upstream-blocked work, and documented non-goals — nothing is blocking.

---

## 🚀 Current focus (2026-07-17)

Two big cycles **completed** and are archived in [roadmap-completed.md](roadmap-completed.md): the
**dev-velocity & modularization program** (v0.3.393–412 — parallel test gate, import-cycle guards, the
REL-3 façade decompositions, the MODEL-DIFF/DRIFT/FIN-TEST/IFC-QA closeouts) and the **four-lane audit
upgrade plan** (v0.3.413–428 — P0 security → P1 reliability → P2 docs/demo → P3 2026 capabilities). The
**OpenAEC / Open CAD Studio study** (v0.3.430–431) added the CAD command line + authoring matrix.

**What's still open** is consolidated in the two sections below — the 🎯 upgrade-plan remainder and the
🧭 CAD-UX lessons — plus the standing engineering backlog:

- **REL-4 — decompose the *web* hotspots** *(now live-verifiable — Gate A open)* — `viewer/app.ts` split
  by responsibility, leaf-by-leaf with live proof; `main.ts`; `portal.ts`.
  ✅ Slice 1 SHIPPED v0.3.455: envTools.ts (render/sun/walk/levels, 4,361→4,215) — all four tools
  exercised in the running viewer post-extraction.
  ✅ Slice 2 SHIPPED v0.3.456: fileIO.ts (open/import/export + Tauri dialogs, 4,215→4,044).
  Next candidates: the collab/presence block · the KEYS + dyn-input layer · measure/section tools.
- **REL-3 remainder** — `modules.py` CRUD/feeds (needs a DI pass, would cycle otherwise) · `main.py` ·
  rest of `data/drawings.py` / `drawing.py`. *(Diminishing returns — attack opportunistically.)*
- ✅ DEV-3 (partial, v0.3.450): **incremental tsc** — local `npm run typecheck` 67s cold → **9.4s warm**
  (buildinfo in `node_modules/.cache`, never committed; CI runs cold, unchanged there).
  DEV-2 evaluated & closed: coverage-upload deferred with rationale (the gate runs 265 suites as parallel
  subprocesses; cross-process coverage instrumentation costs ~30-50% wall on a ~10-min gate for a number
  nobody acts on) · hotspot docstrings — the split modules carry full module/endpoint docs. ·
  ✅ REL-5/7 — CLOSED by evidence (v0.3.441 audit): `errorReporting.ts` already wires window.onerror +
  unhandledrejection to the O1 error log, panel promises carry near-universal `.catch` coverage, and the
  caller scan found no zero-caller client methods — the "~1,075 dead lines" claim didn't survive proof,
  so nothing is deleted.
  ✅ COBie/parse robustness SHIPPED v0.3.442 (all 8 swallow sites → counted, logged skips).

Deferred bridges (deliberate 501s — money movement / KYC / paid APS) are a defensible pattern, not gaps.

---

## 🎯 Upgrade plan (2026-07-17 audit) — mostly SHIPPED (archived in roadmap-completed)

The four-lane audit plan (P0 security · P1 reliability · P2 docs/demo · P3 2026 capabilities) executed
**v0.3.413–428** — full detail in [roadmap-completed.md](roadmap-completed.md). Shipped: SEC-TENANT ·
WEB-BOOT · SEC-GUARD · SEC-MCP (P0) · WEB-LIVE · WEB-LEAKS · DOC-RACE · TZ-UTC (P1) · DEMO-REGEN ·
README-TRIM · UI-SURFACE first slice (P2) · SCHED-RISK · CARBON-EC3 · PERMIT-CHECK · QA-AGENT ·
LAYOUT-EXPORT (found already shipped) · 5D-BIND (P3).

**Still open from the plan:**
- ✅ **UI-SURFACE №11 tail — CLOSED by the v0.3.441 audit**: the frontend audit's caller scan found no
  zero-caller exported client methods — the earlier flagged names were authoring recipes dispatched by
  string or variant-named surfaces, as suspected. Nothing to delete.
- **№18 later-bucket** *(P3, large)* — SOC 2 feature set (KMS/retention/residency) · IFCX server-side
  read/write + bSI Validation Service in CI · BMS/IoT telemetry (Brick/Haystack) · reality-capture
  progress quantification · viewer tile-streaming upgrade · multiplayer cursors · AR field overlay.
  - ✅ **GEN-SCORE (generative option scoring) SHIPPED v0.3.443** — `option_score.py`: a deterministic
    variant grid around a zoning envelope (`generate_options`, FAR-utilisation steps × building types)
    scored through the platform's own engines — conceptual $/SF (cost) · whole-building embodied-carbon
    benchmarks (carbon) · net sellable area (yield) · FAR/height zoning checks (compliance) — min-max
    normalized within the set, weighted composite, non-compliant options capped and never recommended.
    `POST /design/options/generate` + `/design/options/score`; ⚖ Score-options block on the conceptual
    estimator card (Analytics ▸ Risk & Cost). Deepen later with per-option 5D takeoffs + EPD carbon once
    options carry real models.

**Still open from the velocity program:** DEV-2 tail (CI coverage upload · hotspot docstrings) · REL-3
remainder (`modules.py` CRUD/feeds — needs a DI pass · `main.py` · rest of `data/drawings.py`/`drawing.py`;
✅ `routers/authoring.py` split SHIPPED v0.3.447 — 1350→1030 + docs/analysis/shared leaves, URLs unchanged)
· **REL-4** (decompose the web hotspots — `viewer/app.ts` worst, `main.ts`, `portal.ts`; tools-panel
verify) · REL-5/7 (error handling + verified dead-code) · DEV-3 (build/tsc speed) · COBie/parse robustness.

---

## ⛔ Blocked / gated — what remains and exactly what unblocks it (2026-07-18)

Every item still open after the v0.3.413–450 arcs carries a concrete gate. Nothing below is vague
backlog; each entry names the unblocking event.

**Gate A — live-viewer verification** *(the dev-preview geometry loader stalls at "preparing geometry",
so interactive viewer flows can't be honestly verified in this environment; unblocked by a session with
the viewer running against a live backend):*
- SNAP-KIT phase 2 (osnap glyphs + dynamic-input overlay on the cursor — the tested engine is ready)
- REL-4 (decompose `viewer/app.ts` 4,290 lines / `main.ts` / `portal.ts` — a blind refactor of the
  viewer entry is imprudent without runtime proof; pure-leaf extractions continue opportunistically)
- SHEET-VIEWPORTS interactive paper-space editor (drag viewports — the server endpoints are live)
- SITE-1 multi-scale composed BIM↔GIS UX (the overlay loaders ship) · viewer tile-streaming upgrade ·
  multiplayer cursors · AR field overlay

**Gate B — upstream dependencies:** IFC5/IFCX geometry **write** (web-ifc/Fragments write-path) ·
bSI Validation Service in CI (external service account).

**Gate C — paid/networked services:** COST-DB cloud ingest (massing.cloud subscription + signed
bundles; the custom + public importers ship) · APS RVT bridge beyond the shipped flag (paid Autodesk) ·
SOC 2 feature set (KMS/retention/residency — cloud infra) · BMS/IoT telemetry (needs a
Brick/Haystack-speaking building source).

**Gate D — large optional builds** *(complete prerequisites ship today; each is a deliberate,
multi-session build to start when wanted):* coupled-frame FEM solve (the analytical model is
solver-ready) · server-rendered 3D hero · VIZ-U1 Unity bridge · reality-capture progress quantification ·
the 🔮 frontier bets (PROFORMA-LIVE, COST-AGENT, BOARDS, ENV-1, READY-AGENT, RISK-BOARD).

## 🧭 CAD-UX lessons (2026-07-17, from the OpenAEC / Open CAD Studio study)

Open CAD Studio (Hakan Seven; native-DWG AutoCAD-workalike, Rust+iced+wgpu) and the OpenAEC Foundation
(~60 repos, Rust-core→WASM, Tauri, IFCX bet) are on adjacent paths. We're an all-in-one so we won't split
into micro-apps, but the **CAD authoring UX** and a few dev practices are worth adopting. Feasibility-ordered:

1. ✅ **CADCMD — a CAD command line over the viewer — SHIPPED v0.3.430; polar/relative coords v0.3.439** *(★★★★ · the user's top ask)* —
   a typed command bar in authoring mode driving the existing GUID-stable edit recipes: AutoCAD-style
   grammar (`WALL`, `COLUMN`, `SLAB`, `GRID`, `DIM`…) + single-letter aliases (L/C/M/Z) + spacebar-repeat
   + up-arrow history + prompt-driven flows ("Specify first point"). Every drafter already knows this;
   it's scriptable for free. Builds on the shipped AI command bar (reuse its input + recipe dispatch).
2. ✅ **SNAP-KIT — COMPLETE v0.3.453** *(★★★★)* — phase 1 (v0.3.434: pure engine + 45° polar tracking)
   + phase 2 (v0.3.453: **typed dynamic input** — `6` / `<30` / `6<30` mid-draw with a HUD, beats every
   automatic snap — plus snap-kind glyphs ◻/∠/◇/⌨ on each placed point). **Live-verified to the IFC**:
   a wall drafted with typed `8<60` landed at exactly 8.00 m @ 60.0° in the published model. The live
   loop also surfaced + fixed two interaction bugs (draft-beats-measure priority; raycast timeout).
3. ✅ **AUTHOR-MATRIX — SHIPPED v0.3.431 — a public authoring-coverage matrix** *(★★ · like OCS's COMMANDS.md)* — one markdown
   table (IFC classes × create/edit/delete/parametrize, implemented/partial/missing) in the repo + docs.
   Honest maturity signal for users, work-picker for contributors. Cheap; generate from `edit.RECIPES`.
4. ✅ **CLIENT-LIMITS — SHIPPED v0.3.433 — [`docs/client-vs-server.md`](client-vs-server.md)** *(★★)* — what runs in the browser vs the Python
   service and why. Bank OCS's two transferable landmines: **WebGL2 has no vertex-stage storage buffers**
   (custom hatch/linetype must use triangulation/textures or gate on WebGPU) and **wasm is single-threaded
   without SharedArrayBuffer** (already why the viewer needs coi-serviceworker). Doubles as arch docs.
5. ✅ **VIEWER-FUNNEL — SHIPPED v0.3.445** *(★ · positioning)* — the landing (massing.build) now names the
   demo a **free in-browser IFC viewer & model checker**: hero CTA + a dedicated section (open-your-IFC ·
   read-only model QA · "no signup, no install, no upload — your model never leaves your machine") with
   the upgrade path to the desktop app / full stack. Visually verified.
6. ✅ **PLUGIN-REGISTRY — SHIPPED v0.3.444 — manifest-gated recipe plugins** *(★★★)* — OCS's best design,
   adapted: a plugin is a directory with a `plugin.json` manifest (name/version/`api_version`) + a
   `register(api)` entry that adds **namespaced GUID-stable recipes** (`<plugin>.<recipe>`) into the same
   `edit.RECIPES` registry every authoring surface dispatches (POST /edit, CADCMD, AI bar, MCP
   `run_recipe`) — and they appear in the authoring matrix automatically. Three hard gates: **opt-in**
   (`AEC_PLUGINS_ENABLED=1` — plugins execute Python at load), **api-version MAJOR match** (refused with
   a reason otherwise), **collision refusal** (never overwrite). Idempotent reload; refusals are data +
   logs, never fatal. `plugin_registry.py` · `GET /plugins` + admin-gated `POST /plugins/reload` ·
   template + worked example at `plugins/`. *(Later: curated registry.json + process isolation.)*
7. ✅ **MCP-PACK — SHIPPED v0.3.435 — Massing MCP server + skill/docs pack** *(★★)* — the MCP catalog grew
   8→14: the authoring + analysis engines are now agent-drivable (`list_recipes`, `run_recipe`,
   `schedule_risk`, `carbon_report`, `permit_readiness`, `drawing_qa`), so an agent is a first-class
   *author*, not just a reader. The two write tools (`create_rfi`, `run_recipe`) carry the same editor-role
   gate as their HTTP routes. A drop-in Claude skill pack lives at `docs/mcp-skills/` (SKILL.md + draft-RFI /
   run-takeoff / drive-a-recipe playbooks). Builds on SEC-MCP (v0.3.417 authz).
8. ✅ **SHEET-VIEWPORTS — COMPLETE v0.3.454** *(★★★)* — server slice (v0.3.449: `sheet_layout.py` —
   fraction-rect viewports, fixed 1:N true paper scale with Liang-Barsky clipping, per-viewport class
   freeze, presets, shared titleblock SVG/PDF) + the **interactive editor** (v0.3.454: Drawings ▸
   ⊞ Paper space — preset picker, per-viewport controls, live server-composed preview with
   **drag-to-move viewport overlays**, PDF download). Live-verified: a pointer-drag moved a viewport by
   exactly its drag delta and the sheet recomposed; PDF downloaded through the real endpoint.

**Not adopting** (from the same study): the 25-micro-apps split (our all-in-one is stronger); a public
"everything production-ready by <date>" promise (ship dated releases, not dated promises); AI-velocity
without fidelity gates (our per-release suite + IFC-QA roundtrip is exactly the gate they lack); and
IFCX-as-foundation (IFC stays our source of truth; IFCX is a future *export*, tracked in №18).

**📦 Tracked for later — large / needs nimbleness (attack once the cycle is fast; some worktree-forkable):**
SITE-1 open-geodata BIM↔GIS view (🟡 the overlay half ships today — `viewer/gis.ts` loads GeoJSON
vector / GeoTIFF DEM / self-hosted XYZ basemap as georeferenced reference objects; the multi-scale
composed UX is viewer-gated, see ⛔) · ✅ **durable background-job queue SHIPPED v0.3.448** (`jobs.py`: DB-backed
queued→running→done|error rows, per-process worker with crash recovery — orphaned `running` re-queues,
idempotent-handler contract — a `register_kind` registry plugins can extend, `echo` + real `cobie_export`
kinds, enqueue/poll/list endpoints with cross-project 404s; heavy inline paths migrate onto it
opportunistically) · **server-rendered 3D hero** for the package · **COST-DB cloud ingest** (public-source + signed
bundles) · **coupled-frame FEM solve** (the analytical model is complete + solver-ready, so this is a big
optional build) · VIZ-U1 Unity bridge · IFC5 geometry write (upstream-blocked) · the frontier bets below
(PROFORMA-LIVE, COST-AGENT, BOARDS, ENV-1, READY-AGENT, RISK-BOARD). Detail in
[🔮 Frontier](#-frontier--2026-07-research-round-2--net-new-bets) + [🏗 Enterprise gaps](#-enterprise-gaps-audit-2026-07).

---

## 🎨 UI/UX Master Pass — the designer's modeling workspace

Research-backed (Bonsai/IfcOpenShell · Revit + Dynamo/pyRevit · SketchUp + 3D Warehouse · Tekla component
catalog · ArchiCAD GDL/Info-Box). **Why now:** the model rail has grown to **~97 tools across 7 loosely-named
collapsible sections**, organized by accretion, not by how a designer models. Two shipped capabilities are
under-surfaced: **interactive annotation** (the UX-2 recipes ship, but need the ribbon home) and the **content
library** (scattered across 🏗 CONTENT-1, the family catalog, the type browser rather than one palette).

**Transferable patterns adopted:** task-grouped ribbon left-to-right by lifecycle (Revit tabs); **type-first
"Add" flow** (Bonsai `+Add IfcWallType`, Revit Type Selector); **instance-vs-type split** in Properties; a
**Project-Browser tree** as the model spine; a **catalog content panel** with search + `tag:`/`type:` filters,
Recent, thumbnails, editable tags; a **pick content → pick host → auto-build** placement flow; a live
**inference/snap engine + typed dimensions** (builds on shipped E1 inference); an **Info-Box** contextual strip;
**UI as a thin wrapper over scriptable GUID-safe recipes**; an **appendable IFC-as-library** model.

- 🟡 **UX-1 (first slices) SHIPPED v0.3.341–342** — (a) tool sections labelled + ordered by the modeling
  lifecycle (Data · Build · Analyze & Coordinate · Document), "More tools" flowing Build → Analyze → Document;
  (b) the interactive annotation tools + content library surfaced as their own **✍ Annotate** and **📚
  Library** groups (out of the Advanced-fabrication fold). **Ribbon tabs SHIPPED v0.3.370** — a lifecycle
  tab-strip (All · Build · Analyze · Coordinate · Document · Data) filters the sections to one phase.
  **UX-1 remaining:** physically merging the Build sub-sections into one Build tab (vs. tab-filtering).
- **UX-1 — Ribbon consolidation** *(M · high)* — regroup the ~97 tools into a lifecycle task ribbon replacing
  the 7 accreted sections: **Build/Author** (grids·levels → walls·columns·slabs·roofs·families·MEP; sloped/
  mesh/sandbox under an "advanced" fold) · **Annotate** (UX-2) · **Library** (UX-3) · **Analyze** (code/EBC ·
  egress · decision-readiness · labour · model-health) · **Coordinate** (clash · IDS/BCF · MEP connectivity ·
  phasing) · **Document** (drawings · sheets · schedules · issuances) · **Data** (properties · classifications ·
  exports · connections). Keep the persona-primary/"More tools" collapse; re-key it to these groups. Reuses the
  `section()` helper in `viewer/app.ts`.
- **UX-2 (remaining) — inference-snapped annotation placement** *(M)* — the interactive `IfcAnnotation` tools
  (text notes ✅ · dimensions ✅ · element-aware tags ✅ · revision clouds ✅, all rendered onto the plan) ship;
  what's left is **SketchUp-style snap to endpoints/edges/midpoints as you place** (extends the shipped E1
  inference engine) + live guide-lines.
- 🟡 **UX-3 (first slice) SHIPPED v0.3.343** — the 📚 Library opens one **searchable unified palette** merging
  the CONTENT-1 content catalog + the W10-1 family types in a single filterable list (search across name /
  class / category / phase; click-to-place at E,N; inline mesh import). **Operators + Recent SHIPPED
  v0.3.368** — `type:`/`class:`/`category:`/`discipline:`/`tag:` scoped search + a per-project Recent
  bucket. **Remaining:** thumbnails, drag-to-place, pick-host→auto-build, appendable IFC libraries.
- **UX-3 — Unified Library palette** *(L · high)* — one browsable **content panel** unifying the W10-1
  type/family system + the CONTENT-1 catalog (logistics/furniture/landscaping) + external IFC/glTF import: a
  **thumbnail grid**, case-insensitive search with `tag:`/`type:`/`discipline:` filters, a **Recent** bucket,
  predefined groups, and **click/drag-to-place**. Hosted content uses **pick-item → pick-host → auto-build**
  (a door picks its wall; a steel connection picks its beams). **Appendable IFC libraries** — load types
  (+ profiles/materials) from any IFC file. New `library` client + a **Library** rail group. Folds in the
  CONTENT-1 remaining (curated CC0 seed + thumbnail palette) and H1 (CC0 furniture families + PBR materials).
- 🟡 **UX-4 (Info-Box) SHIPPED v0.3.346** — an always-visible **Info-Box** strip on the 3D canvas showing the
  selected element's name · class · level · discipline (with the tree colour dot), regardless of the active
  rail tab.
- 🟡 **UX-4 ("Script this") SHIPPED v0.3.348** — a ⌨ toolbar button that reveals the GUID-safe **recipe plan**
  behind a plain-English command (the verbs the AI bar + sandbox share) and applies it — the code interface
  made discoverable. **Project-Browser spine SHIPPED v0.3.369** — the model browser opens with a Views ·
  Sheets · Schedules nav strip above a labelled Model tree. **UX-4 remaining:** the type-library branch in
  the browser + assembling the full one-shell layout.
- **UX-4 — Designer workspace layout** *(M · high)* — assemble the four resources into one shell: a
  **Project-Browser spine** (spatial tree + views/sheets/schedules + the type library — extends the model
  browser), the docked **Properties** palette with the **instance-vs-type split** (extends P6d), the **Library**
  palette (UX-3), the **task ribbon** (UX-1), plus an **Info-Box** contextual strip and a visible **"Script
  this" affordance** that opens the command bar/sandbox on the same recipe verbs. A11y + mobile-viewport pass
  folded in.

*Sequence: UX-1 (reorg) → UX-3 (library) → UX-2 remaining (snap) → UX-4 (assemble). Each ships as its own
verified release.*

---

## 🧱 Wave 11 — Master Builder (remaining depth)

The architectural spine, guardrails, and drawing generator ship; these deepen geometry, drawings, and
code-intelligence.

**Construction documents**
- ✅ **Plan-render fix SHIPPED v0.3.345** — `drawings.plan_svg` room tags + door/window callouts filter to
  the cut level (no more cross-level label stacking), and plans carry a titleblock band (title box · graphic
  scale bar · north arrow · general notes; cut-plane AFF + grid). Room names XML-escaped.
- ✅ **Composed-sheet cap SHIPPED v0.3.347** — `default_sheet` no longer renders a plan per storey (30-storey
  tower timed out); caps to ~4 sampled levels + takes an optional `storey` for a single-level sheet.
  `sheet.{svg,pdf}?storey=…`.
- **C6 (remaining)** — reference-line datums (`IfcReferent`/`IfcVirtualElement`) + **"drawn detail follows
  LOD"** poché (representation selection + `IfcMaterialLayerSet` poché + annotation density → schematic
  single-line ↔ CD layered poché). Permissive libs only (no AGPL).
- **D2** — **routed egress / life-safety plans** (path-trace over the W9-4 semantic graph, not just tabulated).
- ✅ **D5 SHIPPED v0.3.354** — detail callouts render on the **PDF** sheet path (NCS divided-circle bubble +
  leader + DETAILS legend), and the bubble carries a **real sheet ref** (doc `Identification`, else the
  sheet number derived from the `Location` basename) instead of a placeholder.
- **D8 follow-ups** — wire COMcheck/energy-doc + A117.1 clearance checks into the approvability pre-flight and
  round its findings to BCF.
- **`Pset_Massing_SpecLink` breadcrumb** — the remaining Track-D carrier.

**Geometry depth → LOD 350/400**
- **F0b** — derive **Box / Axis / FootPrint** geometry on demand from `Body` (consumed by the C drawing gen).
- **B3 (remaining)** — wall **Axis** representation + arbitrary clip planes (gable peak mid-span).
- **B5 (next)** — fasteners/hangers as real assemblies + connection geometry (extends the shipped
  `connect_elements`/`element_connections`).

**Open-ended authoring (the moat)**
- **A2** — **RAG index** over ifcopenshell / IFC docs to ground code-gen (extends the shipped sandbox +
  scene-digest).

**Master-builder UX**
- **E2** — **type-a-dimension-while-drawing** (VCB). **E3** — **sketch-to-BIM push/pull** (2D profile →
  extrude). **E5** — **direct-manipulation parametric handles**. **E6** — **recipe-log design-option branches**
  (the recipe log *is* the undo stack; S4 undo/redo ships). **E7** — **live schedules / quantities as you
  model**. **E8 (remaining)** — model-aware guardrail checks (host is actually a wall, storey exists — needs
  the model at precheck time).

**Content library**
- **H1** — seed **CC0 furniture families + PBR materials** (CC0/CC-BY only — ambientCG, Poly Haven, Poly Pizza,
  Quaternius, Kenney, AMD MaterialX), attribution + license stored per asset. *Folds into UX-3.*

**License guardrails (firm):** `ifcopenshell` + geom serializers are **LGPL** — safe to depend on.
Reimplement drawing/annotation *techniques*, never vendor GPL code. SVG→PDF/DXF via permissive libs only
(**no AGPL** — no PyMuPDF). CC0 asset sources vetted per-asset. IDS is an open buildingSMART standard.

## 🤖 AI-MCP / NL authoring (remaining)

S1–S4 ship (deterministic baseline → multi-step LLM interpretation → confirm-before-apply → undo/redo).
- **S4 (next)** — multi-step **undo grouping** (one apply-all = one undo).
- **S5** — multi-turn **clarifying questions**.
- **Read tools** (quantities / schedules / clashes / violations) + an actual **MCP server surface**.

## 🏛️ Wave 10 — authoring-suite leftovers

- **W10-2** — **parametric family generators** (code-defined; typed params + optional formulas; profile library
  I/L/T/U/C/rect/circle + swept/boolean primitives so doors/windows/columns/casework are *generated*, not
  boxes). Freeform via an optional **build123d (Apache-2.0) / OCP (LGPL)** track. *Pure ifcopenshell for the core.*
- 🟡 **W10-4 sizing psets SHIPPED v0.3.349, flow SHIPPED v0.3.355** — `add_mep_run`/`add_riser` write
  `Pset_Massing_MEPSizing` (NominalSize_mm · Shape · Length_m · optional FlowRate/FlowUnit — default unit
  CFM/GPM/A by system) so schedules/QTO/sizing read size + design flow without geometry. *Remaining:
  coincident-port auto-connect.*
- **W10-5** — **annotation & tagging layer** — *largely delivered by UX-2 (notes/dims/tags/clouds on plans);*
  finish section/elevation annotation views.
- 🟡 **W10-6 schedule CSV SHIPPED v0.3.351, Qto depth v0.3.356** — door/window/room schedules export to CSV
  (`schedule.csv?kind=`); the room schedule now carries `IfcElementQuantity` depth (Perimeter + Volume from
  `Qto_SpaceBaseQuantities`). *Remaining: keynote-legend schedule view.*
- 🟡 **W10-7 frame SHIPPED v0.3.357** — **structural analytical model** (`IfcStructuralAnalysisModel`): the
  `derive_analytical` recipe idealises the physical frame (columns/beams) into `IfcStructuralCurveMember`s
  (IfcEdge topology) tied at shared `IfcStructuralPointConnection` nodes, linked back to the physical
  elements, with a permanent-G self-weight load case; idempotent; served at `GET .../analytical`.
  **Surface members SHIPPED v0.3.358** — slabs/roof decks → `IfcStructuralSurfaceMember` (planar
  `IfcFaceSurface`). **Wall surface members SHIPPED v0.3.391** — load-bearing (shear) walls → vertical
  mid-plane surface members (partitions skipped via `Pset_WallCommon.LoadBearing`). **Load activities
  SHIPPED v0.3.390** (`apply_structural_loads`). **Supports SHIPPED v0.3.392** (`apply_structural_supports`
  — pinned/fixed base `IfcBoundaryNodeCondition`). Members + loads + supports = a complete, solvable
  analytical model. *Remaining: coupled-frame (FEM) solve.*
- **W10-9** — **parametric constraints & dimensional locks (the hard one)** — no IFC representation; store in a
  sidecar, solve, bake to IFC. Start with 1D/alignment locks. **License:** FreeCAD's **planegcs (LGPL,
  extractable)**; avoid python-solvespace (GPL) and OpenSCAD (GPL).

## 🔬 Wave 9 — research-scan leftovers

- **W9-4 (harder half)** — ingest **specs / drawings / code documents** as graph nodes + **NL→graph query with
  cited sources** (GUID + spec page + code section) — the explainability substrate under W9-2 code-checks and
  the RFI-0 NL-QA layer.
- **W9-5 (L part)** — smooth **equipment motion along paths** as the 4D slider advances + swept crane-reach
  clash.
- 🟡 **W9-6b FF&E BOM SHIPPED v0.3.350** — `content.furniture_bom` counts placed furnishings by item + level
  (`GET /projects/{pid}/ffe-bom`) — the auto-BOM half. *Remaining: the procedural headcount-program →
  `IfcSpace` zones + auto-furnish generator.*
- **W9-7 — AI 2D-PDF auto-takeoff** *(optional / paid, flagged bridge)* — manual calibrated PDF takeoff ships;
  AI auto-extraction is a flagged bridge like the paid RVT path, never core.
- **W9-8 — NL imperative authoring** — folds into the AI-MCP track.

---

## 🔮 Frontier — 2026-07 research round 2 + net-new bets

Ranked most-actionable first. Competitor names kept out — capabilities described directly (standing directive);
interop targets / content platforms / open standards named where they're integrations.

### 📊 Estimating → 5D depth
- ✅ **EST-1 crew-days→duration SHIPPED v0.3.339** — the labour estimate now rolls per-line crew-days up by
  trade group into a **working/calendar-day schedule duration** (`crews` = parallel crews per trade shortens
  it; trades sequential = conservative critical path). Flows through `labor_estimate`/`full_estimate`/
  `from_model`; `?crews=N` on `/estimate/labor`.
- **EST-1 (remaining)** *(M)* — full **QTO integration** (drive the activity quantities from the real
  `aec_data.qto` takeoff, not just element dimensions) + wire the duration into the CPM/Gantt schedule.
- ✅ **COST-DB backbone SHIPPED v0.3.337** — `cost_datasets` + `cost_items` schema, project `cost_dataset_id`
  pin, an offline `PublicDataImporter` (`cost_db.py`) building a `public_local` vintage from the shipped
  benchmark rates, a vintage resolver (latest/exact/nearest-fallback/strict) + `is_latest` management, and the
  `/cost/datasets` + `/projects/{pid}/cost-vintage` endpoints.
- ✅ **COST-DB estimate integration SHIPPED v0.3.338** — the model estimate (`/estimate/from-model` +
  `/qto/by-floor`) prices the takeoff **through the project's pinned vintage** (its rate map as overrides) and
  returns the `cost_vintage` it priced with — reproducible estimates.
- ✅ **COST-DB localization + escalation SHIPPED v0.3.436** — `cost_db.rates_for_project` takes the pinned
  vintage's national-average rates and makes them project-real **offline**: × the project region's cost index
  and escalated from the vintage year to the construction midpoint (reusing the shipped market table +
  `market_intelligence.escalation_factor`). The takeoff (`/qto/by-floor`, `/estimate/from-model`) and the
  `/cost-vintage` endpoint carry the `cost_adjustment` (location index · escalation · combined factor); region
  & timeline come from the project's `market_assumption`. **Remaining build-order steps:** the `massing.cloud`
  CloudDatasetImporter (signed bundle), real public-source ingest (BLS/FRED/DoD/Census), per-county
  location-factor / PPI-index DB tables, delta sync, Ed25519 signatures.
- ✅ **COST-DB custom cost-book import SHIPPED v0.3.440** — a firm installs its **own** rates as a
  `custom`-origin vintage (`cost_db.import_custom_vintage` + `parse_cost_rows`): `POST
  /cost/datasets/import-custom` takes a flat `{ifc_class: rate}` map or `rows: [...]`, MasterFormat-codes
  any gaps off the classification spine, replaces the same (year, quarter) in place on re-upload, and sets
  it latest — so a project prices through the firm's negotiated/historical costs (localized + escalated
  like any vintage). Offline. This is the "+ import" the task title always implied.
- **COST-DB — vintage-versioned cost database + import** *(L · high)* — a local, **vintage-versioned (by year)**
  cost database populated from **either free public sources (BLS/FRED/DoD-UFC/Census — offline-first) or the
  `massing.cloud` subscription API**, behind one `DatasetImporter` interface. Projects **pin** to a specific
  vintage so every estimate is reproducible; import `latest` or a specific historical year with a configurable
  fallback (`strict`/`nearest`); cloud bundles are **checksum-/signature-verified** before a transactional
  upsert; older vintages **escalate forward** via stored PPI series. Feeds 5D cost / estimating / GC-portal
  budget / FCA / Last Planner through the pinned vintage. Open-source ships the **public importer + adapters
  only** — proprietary data (1build/RSMeans) arrives solely via the subscriber's authenticated cloud pull,
  never committed to the repo. Full spec + schema + build order: **[cost-db-import-plan.md](cost-db-import-plan.md)**
  (server side: `massing_cloud_plugin_plan.md`; location engine: `massing_location_cost_import_plan.md`).
  *Build order: schema → PublicDataImporter (offline spine) → vintage resolver + project pinning →
  CloudDatasetImporter (manifest/bundle/verify/upsert) → subscription detection + public fallback → delta sync →
  Ed25519 signatures → escalation-forward.*

### 🚫 RFI-prevention (the openBIM information-delivery moat)
- ✅ **RFI-0 missing-dimension detection SHIPPED v0.3.336** — a 5th gap source in `decision_readiness`:
  doors/windows with no `OverallWidth`/`OverallHeight` + rooms with no floor area → ranked `dimensions`
  gaps that ride the existing BCF promotion.
- 🟡 **W9-4 doc-graph SHIPPED v0.3.359** — the cited-source substrate: `docgraph.build` folds spec-section
  (classification code) + document (sheet-ref'd) nodes onto the model graph (`specified_by`/`documented_by`);
  `element_sources(guid)` returns one element's cited provenance (spec sections · documents · location).
  Served at `GET .../doc-graph` and `GET .../elements/{guid}/sources`.
- ✅ **RFI-0 NL-QA SHIPPED v0.3.360** — `POST /projects/{pid}/rfi/qa` routes a plain-language question to the
  doc-graph / decision-readiness and answers with cited sources ("what governs \<element\>?" → spec + detail
  + level; "what's blocking approval?" → ranked gaps + fixes; "what is spec section 05 12 00?" → governed
  elements). Deterministic (no API key needed); every claim carries its source.
  *Remaining depth: external spec/code-document text ingestion (page-level citations) + LLM rephrasing.*

### 🎮 Visualization — Unity as the optional bridge
- **VIZ-U1 — Unity/Pixyz IFC → WebGL presentation build** *(L · optional/paid/flagged)* — Pixyz imports **IFC
  natively** (GlobalId + metadata), Unity exports a **browser WebGL build** (no cloud-GPU stream) — a
  high-fidelity presentation mode as a browser build. Proprietary seat-licensed → optional, flagged, one-way
  (viz only), never the default viewer. The on-mission path stays glTF export (ships) + three.js PBR (VIZ-2).

### 🌍 BIM-GIS digital twin
- **SITE-1 — multi-scale BIM ↔ GIS view** *(M · ★★★★)* — a browser view composing the building IFC with its
  regional GIS context (parcel, zoning envelope, terrain, neighbours) from open geodata (GeoJSON / parcel APIs).
  Validated by an open-source (AGPL) BIM+GIS peer — reimplement techniques, never vendor AGPL code. Feeds
  authoring + the code/zoning engine + auto site-context ingestion (setbacks/height/FAR → buildable envelope).

### 🌦 Early-design environmental performance
- **ENV-1 — wind-comfort / microclimate at massing** *(M · med)* — beside the shipped solar-access analysis, a
  simplified pedestrian wind-comfort pass (prevailing-wind exposure, wind-shadow) for early "is this a wind
  tunnel?" feedback. Offline + approximate (not CFD); a CFD-grade version stays a flagged bridge.

### 🧩 Authoring surface parity
- ✅ **AUTH-VS — visual node-based authoring** *(L · parity)*. **Engine SHIPPED v0.3.363** +
  **canvas SHIPPED v0.3.367** — `nodegraph.execute_graph` runs a recipe graph (Kahn order + `{"$from": id,
  key?}` refs; `POST /edit/graph`), and the viewer ships a draggable node-graph editor (`nodeCanvas.ts`):
  palette → drop nodes, wire output●→input○ (auto-injects the `$from` ref), Run graph → one GUID-stable
  publish. Verified live: launcher, palette (7 recipes), add/drag/wire/ref-injection.

### 🚀 Model-authoring & collaboration frontier
- 🟡 **COLLAB-1** *(L · ★★★★★)* — **real-time multiplayer co-editing**. **Awareness slice SHIPPED v0.3.361**:
  a model-edit SSE stream (`GET .../model/stream`) + collab snapshot (`GET .../collab`) that live-reloads a
  second viewer after another user publishes and shows the presence roster; in-model comments already ride
  the GUID-anchored Topic/Comment model. **Edit-lock SHIPPED v0.3.362** — `/edit` takes an optional
  `base_source`; a stale write (another user published since) is rejected 409 instead of silently
  overwriting. *Remaining: per-user cursor/selection overlays and the client-side viewer wiring.*
- **PROFORMA-LIVE** *(M · ★★★★)* — tighten the **model↔proforma live loop**: yields/unit-mix/parking/efficiency
  + cost recompute **inline as you model**, not only in the portal.
- **COST-AGENT** *(M · ★★★★)* — an estimating agent that re-estimates on each geometry change + learns from
  historical cost data (companion to AI-MCP + estimating→5D).
- **BOARDS** *(M · ★★★½)* — a "Boards" presentation surface: styled design-option views, shadow studies,
  auto-generated stakeholder decks as first-class artifacts alongside sheets.
- **NL-QA** *(S · ★★★½)* — built-in NL QA recipes once AI-MCP matures ("audit issues + suggest fixes," "check
  room accessibility," "normalize inconsistent Psets"). Maps onto code-check + model-hygiene + RFI-0.
- *Validated / overlap (verify, don't rebuild):* bulk IFC Pset editor (⊂ override layers), manufacturer
  product-configurator → IFC type (⊂ families/types), in-context comments (⊂ BCF).

### 🗂 DISC — unified discipline tree (remaining, optional)
DISC-1…4b shipped (colour palette, full IFC coverage, `discipline_tree()` served, color-by-discipline viewer,
estimate discipline rollup, one canonical `aec_data/disciplines.py` source, fire-alarm + telecom recipes + tool
buttons, tower rebuilt with all 8 disciplines). Optional remnants:
- ✅ **DISC-coverage SHIPPED v0.3.352** — `/elements/by-discipline` returns a **coverage** view over the
  tree (every standard discipline present/absent + count, `disciplines_covered`/`_total`, `missing` list) —
  a completeness lens over the property index, no geometry parse.
- **DISC-poché** — an opt-in **colour-by-discipline mode** for the 2D plan/PDF poché (today the poché is
  deliberate per-class architectural convention).
- ✅ **DISC-cw SHIPPED v0.3.353** — context-aware curtain-wall member classification: an `IfcMember`/`IfcPlate`
  aggregated under an `IfcCurtainWall` (or `IfcRoof`) now reads Architectural, not Structural. The property
  index records each element's aggregating `host` class; `discipline_of_ifc_class(cls, host)` consults it.

---

## 🔐 Sign-in & first-run onboarding

**Goal:** make social sign-in the prominent default and sequence it into the tutorial — *without* a hard gate
(the app runs free/offline; a signup wall before the "aha" moment craters top-of-funnel). Google + Microsoft
OAuth, MFA, SSO/SAML/SCIM, and a first-run welcome modal + ≤5-step tour already ship. This is **prominence +
flow**, not new auth. Files: `apps/web/src/ui/onboarding.ts`, `apps/web/src/account/accountUI.ts`.

**First slice (one sprint):**
- **B1 — optional sign-in as the welcome modal's first panel** *(M)* — a headline + prominent **Continue with
  Microsoft/Google** (only configured providers, via `authProviders()`), a quiet "More options," and a visible
  **"Explore without an account →"** dropping to the quick-start cards. Prominent, never a wall.
- **B2 — sign-in → tour** *(S)* — after sign-in *or* "Explore without an account," auto-launch the tour and
  `markOnboarded()` once.
- **A1 — Google + Microsoft as co-equal visible defaults** *(S)*. **A2 — collapse everything else behind "More
  sign-in options"** *(S)*. **C1 — reorder the sign-in modal to lead with one big provider button** *(S)*.

**Fast-follow:** **B3 — role self-selection after sign-in** *(M)* · **B4 — keep the tour ≤5 steps** *(S)* ·
**C2 — value-moment "Sign in to save your work" prompt** *(S)*.

**Deferred (explicit triggers):** **A3 — Sign in with Apple** (only alongside a native iOS wrapper) ·
**A4 — skip Facebook/GitHub** (wrong audience; LinkedIn only on demand) · **B5 — persistent quick-start
checklist** *(L)*.

*Privacy/mission guardrails: keep the guest/offline path fully functional; no telemetry before consent; SSO
buttons stay config-gated.*

---

## 🏛️ Future inbox — building-code library (jurisdiction-aware)

The copyright-safe strategy: **own the rules, facts, and checks; deep-link out for prose; license prose later.**
**GREEN:** section numbers/titles/edition years, jurisdiction→adopted-edition adoption facts, numeric
thresholds/formulas (facts of law — what `codecheck.py` encodes), our own paraphrased rule content. **RED:**
scraping/redistributing ICC/ASTM verbatim prose. *(CODE-1 catalog, CODE-2 occupant-load, CODE-3 first slice,
CODE-EBC ship — see the archive.)*
- **CODE-1 follow-ups** — extend the per-state adoption seed (ICC adoptions DB + DOE energy-code status) + per-
  project jurisdiction storage.
- ✅ **CODE-3 SHIPPED v0.3.344** — `apply_rules(ibc_edition=…)` rewords the Track-D detail-rule citations to
  the project's resolved adopted IBC edition (an exterior window cites the actually-adopted §1404.4 edition);
  threaded through the `apply_detailing_rules` recipe. *Remaining: auto-resolve the edition from the project
  jurisdiction at the /edit call site.*
- **CODE-4** *(S)* — local-amendment overlay + manual-entry UI (store *our summary* + a link).
- ✅ **CODE-5 SHIPPED v0.3.340** — `codecheck.code_ids` emits the machine-checkable subset of the applicable
  code requirements as buildingSMART **IDS 1.0** (rated-element `FireRating` + space area + envelope U-value,
  driven by the fired code rules); `GET /codes/ids` (+ `.ids` download). Validates an IFC in any IDS checker.
- **CODE-6** *(L, flagged/paid)* — licensed prose integration behind a flag + cost warning; only after CODE-1–3
  prove demand.

## 🎮 Future inbox — viz export (one-way, never core)
- **VIZ-1** *(S · on-mission)* — glTF/`.glb` (+ optional `.udatasmith`) export. **Largely ships — confirm parity.**
- **VIZ-2** *(S/M · on-mission)* — **three.js PBR "presentation mode"** (IBL/HDRI, SSAO/bloom, baked lightmaps),
  offline + license-free.
- **VIZ-3** *(L · paid/flagged)* — pixel-streamed cinematic mode. **VIZ-4** *(L · paid/flagged)* — VR
  design-review bridge. Optional interop tiers, never the default viewer.

---

## 🔒 Security backlog

- ✅ **SEC-DEP-1 / SEC-DEP-2 resolved** (Capacitor 6→7 cleared the tar CVEs, v0.3.312; the glib/Tauri gtk3
  unsoundness dismissed `not_used` — Linux-desktop-only, no gtk3-compatible fix, we never call
  `VariantStrIter`). **Security tab: 0 CodeQL + 0 Dependabot alerts.** Detail in the archive. Continue CodeQL
  monitoring on each push.

---

## 🚧 Blocked, deferred & non-goals

**④ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX *geometry* write** — the **data** write-path shipped (v0.3.213); only geometry authoring waits
  on web-ifc / Fragments IFC5 support (still alpha). Track buildingSMART.
- **Native mobile shell** — a **Capacitor wrapper** of the offline PWA (needs a macOS/Xcode + Android-SDK
  pipeline separate from the Tauri desktop release). PWA "Add to Home Screen" ships; the native shell is the
  fast-follow. See [mobile.md](mobile.md).

**⑤ Deferred by decision — integrate, don't build (pursue on customer pull)**
- **Regulated syndication depth** — the licensed stack (KYC/accreditation, transfer-agent recordkeeping, Reg-D
  engine, escrow, the token) stays counsel-gated. Our origination-side **connector shipped v0.3.213**
  (`securities_bridge`, never moves money); build deeper only when a customer actually raises/syndicates.
  ⚖️ *Not legal advice; the partner is the licensed entity.*

**⑥ Intentional non-goals — documented rationale (not gaps)**
- **In-browser IFC authoring** — **REVERSED (2026-07): now a first-class, shipped capability.** Blender/Bonsai
  remains an *optional* advanced/interop editor. **`.mpp` (MS Project) parsing** — proprietary OLE binary; path
  is *Save As XML/CSV → import*. **Custom Revit plugin** — the certified `revit-ifc` exporter covers it.
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled; further extraction trades
  readability for indirection.
- **Out-of-scope-by-design operations integrations** — live ENERGY STAR / BAS / BMS (flagged stubs only), full
  institutional reporting packs, space/move management (CAFM), 1031 tooling, JWT-revocation blacklist + Redis-
  backed presence (known limits, tracked in PRODUCTION_CHECKLIST).

---

## 🔎 Research-2 additions (2026-07)

From the 2026-07 research round (pics12 images + 9 web sources: DDS-CAD, OpenTakeoff, Geopogo, Fieldwire,
BuildPass, pyRevit patterns, the BIM+GIS infographic). Only genuinely on-mission, feasible items kept;
license notes inline. Skips: AutoCAD-LISP repos (DWG-bound, low value), weld-symbols (unlicensed niche),
Geopogo-as-product (closed Unreal — its *context-ingest* idea folds into SITE-1), full mobile field app.

**Authoring & drawings (highest value):**
- **KEYS — Revit-style keyboard shortcuts** *(S/M · ★★★★★)* — 2-letter authoring shortcuts (WA/CL/DR/CS/…)
  over the recipe+tool actions so Revit-trained users are instantly fast. *(IMG_0259 shortcut cheat-sheet.)*
- ✅ **VIEW-RANGE — plan view-depth — SHIPPED v0.3.383** — `plan.svg?view_depth=<m>` shows foundations/
  footings below the cut as dashed hidden lines (`below_footprint_baked`); the Top/Cut/Bottom/View-Depth
  model vs. one cut_z. *Remaining: per-plane visibility control + the footprint sheet/PDF path.* *(IMG_0247.)*
- **PREFLIGHT — model-health / QA issuance gate** *(S/M · ★★★★)* — one-click audit (orphaned GUIDs · missing
  classifications · unplaced elements · open BCF · param completeness) as an issue-the-set gate. *(pyRevit.)*
- **SHEET-LINK — hyperlinked callouts across the sheet set** *(S · ★★★)* — clickable detail/section bubbles
  cross-link sheets in the PDF/SVG viewer. In-house on sheetgen + markup. *(Fieldwire plan-hyperlinking.)*

**Estimating & engineering:**
- **TAKEOFF-2D — PDF/scan quantity takeoff** *(M · ★★★★)* — browser flood-fill "one-click area" tracer on
  uploaded drawings → feeds the existing 5D estimate; covers the drawings-only case model-takeoff misses.
  *License: OpenTakeoff is Apache-2.0 — vendor or reimplement freely (same Vite/pdf.js/pdf-lib stack).*
- ✅ **MEP-SIZE — MEP engineering checks — SHIPPED v0.3.386** — `GET /mep/sizing` computes flow velocity in
  each authored duct/pipe from size + design flow (`Pset_Massing_MEPSizing`) and checks it pass/fail vs
  accepted limits (ASHRAE ~2500 fpm air, ~8 ft/s water, NEC 392 tray fill); viewer surfaces it with isolate-
  in-3D. *(DDS-CAD technique.)* *Remaining: pressure-loss balancing, thermal load, per-conductor tray fill.*
- **STRUCT-LOADS — load cases + static analysis** *(L · ★★★★)* — extend W10-7 with dead/live/wind/seismic
  `IfcStructuralLoadCase`s + per-member load activities, and lightweight beam/column static
  (shear/moment/deflection) diagrams. *(IMG_0250 structural-analysis primer.)*

**Site / GIS (folds Geopogo + the BIM+GIS infographic into SITE-1):**
- **SITE-1 first slice — open-geodata site context** *(M · ★★★★)* — use the existing georeference to drop the
  model onto a real basemap with **OSM footprints + parcels + terrain DEM + neighbouring-building extrusions**
  as a separate context layer; GeoJSON→extruded blocks. *License: OSM=ODbL (attribution, keep it a separate
  layer), CityJSON/OGC open, Cesium/Google 3D-tiles optional online-only enhancement (viewer stays offline
  per the non-negotiable). No GPL/AGPL/paid-SDK lock-in.* Later: CityGML/CityJSON LoD1–2 read; a full IFC↔
  CityGML *semantic* harmonization is L and deferred.

**Lower-priority / conceptual:**
- **READY-AGENT** *(M · ★★★)* — extend RFI-0 into a proactive agent that surfaces missing approvals /
  unresolved clashes / handover-blockers with cited evidence. *(BuildPass agent pattern.)*
- **RISK-BOARD** *(S/M · ★★★)* — a project-risk register unifying the "hidden" risks (data-quality gaps,
  coordination debt, schedule compression, cost escalation) already computed by hygiene/clash/estimate/schedule
  into one dashboard. *(IMG_0251 construction-iceberg framing.)*
- Market note *(IMG_0258 "Top 20 BIM firms")*: the target audience is infrastructure-heavy (AECOM/Jacobs/WSP/
  Arup…) → reinforces **IFC4.3 infrastructure** depth + **SITE-1** as strategically important, not net-new.

## 🔧 Reliability & hardening (REL)

From a static-analysis pass (blast-radius / churn / coupling). Findings are **leads to verify, not commands** —
ground each in the real code before editing. Ship phases in order; each an independent PR; keep the suite green.
Refactor rule: **no public-API/behavior change** except the (shipped) security phase. Prefer structural fixes
(extract leaf module / invert dependency / DI) over deferred function-local imports.

- ✅ **REL-1 — web portal "cycle" = FALSE POSITIVE (verified 2026-07)** — both legs are `import type`
  (`panelContext.ts:2` imports `PortalHost`, `portal.ts:7` imports `PanelContext`) — stripped at build, so
  there is **no runtime cycle**. The recommended fix (type-only import) is already in place. No change needed.
- ✅ **REL-2 — API `db.py` "cycle" = FALSE POSITIVE (verified 2026-07)** — `db.py` imports neither `modules`
  nor `models`, so it has **no back-edge**; `models.py→db.py` is a clean one-way dep (needs `Base`); and
  `distribution.py→modules.py` is a **deferred function-local import** (the suspected false edge, confirmed —
  it's a lazy import, not a load-time cycle). No module-load cycle exists. No change needed.
- **REL-3 — modularize oversized API/data modules** *(L–XL, one PR each, façade at old path)* — `main.py`→~4,
  `modules.py`→~6 (relieves REL-2), `codecheck.py`→~3, `connectors.py`→~6, `auth.py`→~5, `data/drawing.py`→~4,
  `data/massing.py`→~3, `data/drawings.py`→~5, `bcf_io.py`→~3, `routers/generate.py`→~5. **`ruff`+`pytest`
  green after each.**
- 🟡 **REL-4 — decompose web hotspots** *(L–XL, one PR each)* — `viewer/app.ts` (worst file) split by
  responsibility (render setup / event wiring / data load / UI glue); `main.ts` extract large methods + flatten
  nesting; `portal.ts` split; `api/client.ts` — if generated, fix the generator/config not the output. **Must
  be tested + debugged after each** (perf-sensitive; the geometry preview stall means verify via typecheck/
  lint/vitest + tools-panel technique). **`openModule` O(n·m) fix SHIPPED v0.3.373** — the per-column
  `m.fields.find` linear scan is now an O(1) `Map` lookup.
- **REL-5 — error handling & I/O-in-loop** *(behavior-affecting)* — handle unhandled promise rejections in
  `main.ts`; `errorReporting.ts::installErrorReporting` must not throw during install; batch FS calls out of
  loops in `vite.config.ts::writeBundle` + `scripts/bundle-budget.mjs`; `bridge.py::execute` → dataclass; dedupe
  DRY in `recipes.py`/`vite.config.ts`.
- ✅ **REL-6 — security hardening — SHIPPED v0.3.371** — XXE-safe P6 parser (defusedxml), non-crypto SHA-1
  flags cleared, pillow≥12.3 pin; audit run (npm 0 vulns · bandit HIGH→0 · secret-scan clean). *Remaining:
  optional private-IP/metadata blocking on admin webhook URLs; `cargo audit` (tauri) + `gitleaks` full-history
  scan in CI when those tools are available.*
- **REL-7 — verified dead-code cleanup** *(LAST, small batches)* — ~139 findings / ~1,075 lines. Prove
  unreferenced across the repo **and** out-of-band entry points (pyproject/package.json scripts, CI,
  Dockerfiles, pyRevit `.pushbutton` manifests, dynamic imports) before deleting. Start with unused
  exports/internals; be skeptical of `e2e_*.py`, `loadtest.py`, `routers/{scim,saml}.py`, converter/pyrevit.
- **REL-8 — lock in gains** *(ci)* — CI cycle check (`import-linter` / `eslint-plugin-import` no-cycle); upload
  coverage from CI; module-header docs on refactored hotspots (bus factor 1).

## 🏗 Enterprise gaps (audit 2026-07)

From a codebase audit for enterprise-grade CAD + analysis readiness. **What's already strong** (don't
rebuild): model versioning/diff, audit trail, RBAC + SAML/SCIM, portfolio rollups, and a strong 5D
cost↔GUID linkage (`cost.element_5d`, `estimate.estimate_from_model`). The enterprise gap is concentrated
in **deliverables, engine relationships, and analysis depth** — the top items, with the ones already
closed this session marked:

- ✅ **Compiled drawing-set PDF** — SHIPPED v0.3.375 (`/drawing-set/compiled.pdf`).
- ✅ **Model-estimate → proforma link** — SHIPPED v0.3.376 (`/dev-budget/sync-from-model`).
- ✅ **Client project package** — SHIPPED v0.3.377 (`/project-package.pdf`).
- ✅ **Rendered cover sheet / index** — SHIPPED v0.3.384 (`drawingset._cover_pdf`): title block + key-plan
  footprint thumbnail + discipline-grouped, paginated drawing index.
- ✅ **Structural analysis: apply loads + solve** — SHIPPED v0.3.382 (`/structure/solve`): gravity load
  case applied to the analytical members + a determinate member-by-member statics solve (reactions, shear/
  moment/deflection diagrams, column axial). *Remaining: lateral solve · load activities written to the IFC ·
  coupled-frame FEM.*
- ✅ **Single discipline/class source of truth** — SHIPPED v0.3.385: sheet-series derives from the one
  discipline map (`classification.series_of_ifc_class`); trade stays a separate build-sequence axis.
- 🟡 **Broader CAD/geometry export** — **binary glTF (.glb) + first-class IFC re-export SHIPPED v0.3.387**
  (`/model/export.glb`, `/model/export.ifc`) beside DXF R12 + `.gltf`; viewer has Export IFC/.glb/.gltf.
  *Remaining (deferred — proprietary/heavy deps): DWG (ODA/Teigha), USD (pxr).*
- **Durable background-job queue** *(★3 · M)* — geometry export, PAdES sealing, and large set generation run
  **inline** (`run_in_threadpool`); no durable queue/worker. Fine for demos, fragile under real load. Touch
  `main.py` + a worker/queue; migrate `generate.py`/`drawings.py`/`exports.py` heavy paths.
- **Server-rendered 3D hero** *(★3 · M)* — geometry streams client-side, so the project package has no 3D
  render (only a composed plan/section/elevation overview). Add a client screenshot-capture → upload path,
  or a headless render, to drop a hero image into the package.
