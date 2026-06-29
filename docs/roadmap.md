# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[capability-matrix.md](capability-matrix.md) (vs Bonsai/Revit/Navisworks),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[competitive-plan.md](competitive-plan.md), [ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.2.8**.

---

## ★ Active plan (sequenced — work top to bottom)

User-directed sequence as of v0.2.8. Carry this out in order; each item ships as its own release.

1. **Real-estate / capital depth**
   - [x] WPRealWise / MLS listing syndication bridge + marketing flyer (`re_bridge.py`) — **v0.2.8**
   - [x] Lease-management depth — renewals, rent escalations, CAM reconciliation (`leasemgmt.py`) — **v0.2.9**
   - [ ] Equity waterfall / distribution scenario modeling (tied to the investor cap table)
   - [ ] Investor-portal document sharing (signed statement/report links via the signed-URL infra)
   - [ ] Comps-import automation (bulk CSV / RESO → `comparable` module, feeds sales-comparison appraisal)
2. **Polish & harden existing** — UX consistency pass; empty/loading/error states; accessibility;
   perf on large models; broader test coverage of the newer analytics/RE surfaces.
3. **Production / ops** — deploy automation; backups/restore runbook; observability
   (metrics/healthchecks/logging); rate-limit tuning; container/image hardening.

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

## A. Model generation & **Test Fit** (TestFit-style)  ★ next major theme
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
- **B2 — Sources & Uses (first-class view).** ★ *in progress* — grouped Uses (from the cost budget +
  acquisition + financing) vs Sources (senior debt sized by LTC/LTV/DSCR/debt-yield, mezz, LP/GP
  equity); per-period draw spread feeding interest reserve. Endpoint + Finance S&U view + memo section.
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

## U. Underwriting realism  ★ next major theme
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

## R. Built-world techniques (research-grounded)  ★ next major theme
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
- ✅ **DONE — C4 workflow-engine upgrades / emanager parity** (v0.1.87; see
  [emanager-gap-analysis.md](emanager-gap-analysis.md)):
  - **Transition field-gating** — transitions declare `requires:[field]`; the engine refuses and the
    UI disables the workflow button until those fields are filled (e.g. RFI can't be Answered without an answer).
  - **Company / Contact directory + reference lookups** — first-class directory config modules with
    `reference` field lookups (e.g. `subcontract.vendor_company`).
  - **Due / overdue SLA feed** — `GET /projects/{id}/due-feed` scans all due-bearing modules into one
    ranked feed, surfaced by a **"Deadlines"** portal-home widget.
  - **In-app workflow map** — a state diagram of the module workflow on the record view (current state
    highlighted, gated transitions drawn as edges).

## M. Materials, rendering & computational design  ★ next major theme
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
  a one-click pyRevit macro that exports IFC **and uploads to a ModelMaker project** — convenience
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

## Status & what's left
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
