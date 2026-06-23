# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[capability-matrix.md](capability-matrix.md) (vs Bonsai/Revit/Navisworks),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[competitive-plan.md](competitive-plan.md), [ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.1.11**.

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
- **A1b/A2 — Circulation & egress (full).** Define unit *types* (studio/1BR/2BR… target SF + mix %/count) and
  tile them along a **double-loaded corridor** on the floor plate (not a naive grid) — real unit
  modules + demising walls + corridor. Import/save unit presets.
- **A2 — Circulation & egress.** Auto corridors, egress stairs, elevators positioned for code
  (max travel distance, two means of egress); core placement from the unit layout.
- **A3 — Parking solver.** Surface / podium / structured parking to a target **stalls/unit** ratio,
  with drive aisles + ramps; auto stall count; parking as IFC spaces/slabs.
- **A4 — Yield metrics & scenario compare.** Live GSF/NSF, **efficiency (load factor)**, units,
  units/acre, parking ratio, FAR achieved, **yield-on-cost** — multiple fits compared side-by-side.
- **A5 — Generative design (targets).** Define targets/filters (FAR, parking ratio, yield-on-cost)
  → search massing/unit-mix/parking permutations and rank — "find the deal that pencils."
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
  total) → OPEX, purchase → acquisition line; per-SF ratios. *Next: appraisal/market comps section.*
- **B6 — Pitch-deck variant** of the memo (10–20 slides) + market/timeline sections, photos.

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
- **M2 — Photorealistic rendering** (Revit/Rhino/Matterport): a viewer **render mode** — PBR
  (MeshStandardMaterial) + environment/IBL lighting, **soft shadows + ambient occlusion**, a
  **sun/shadow study** by date/location, and a **Matterport-style first-person walkthrough**.
- **M3 — Family & material depth** (Revit-parity): **IfcMaterialLayerSet** wall/floor/roof assemblies
  (e.g. plasterboard · stud · plasterboard), an expanded parametric **family library** with materials,
  and **import of external IFC type content**.
- ✅ **DONE (M4 start) — computational graph** (Dynamo/Hypar-style, zero-touch). `compute_graph.py`
  exposes the pure engines as **nodes** (params→input ports, dict return→output ports) + an executor:
  `GET /compute/nodes` (palette) and `POST /compute/graph` run a {nodes, edges} graph in dependency
  order (zoning → structure/takt/cost → yield). After the Dynamo zero-touch primer. *Next: a visual
  node editor + the module-relations graph view.*

## D. Platform / production
Tracked in [production-readiness.md](production-readiness.md): main.ts account/connections split,
dashboard JSON-extraction perf, Redis-backed rate limits (multi-worker), CI dependency scanning,
a11y pass. Plus: mobile (Capacitor) build hardening; RVT→IFC (APS) polish.

---

## Status & what's left
The headline themes are **shipped** (v0.1.14): generative design + **Test Fit** (A1/A3/A4/A5/A6),
the **developer/finance portal** (B1 budgets · B2 Sources & Uses · B3 property/tax · B4 specialty ·
B5 investment memo), the full **lifecycle** (acquisition→turnover), **AI assistant**, **SSO**, and
the production-blocking hardening (see [production-readiness.md](production-readiness.md) — now
shippable). 26/26 CI gate + a report-only dependency scan.

Remaining = incremental depth (not blockers), in rough priority:
1. **Test Fit depth** — A2 egress/travel-distance, parking as real IFC geometry, true polygon-offset
   footprint on the parcel; tie optimize's yield-on-cost to the live proforma vs the proxy.
2. **Developer** — ✅ B6 pitch-deck (slide) variant shipped (`/investment-deck.pdf` + 📊 button);
   next: market/timeline sections, property photos.
3. **Construction** — C1 multi-period pay-app accounting + lien waivers; C2 COBie field-enrichment;
   C3 4D sequencing.
4. **Platform** — main.ts account/connections split; dashboard JSON-extraction perf; Redis-backed
   rate limits (multi-worker); a11y pass; mobile (Capacitor) build hardening; RVT→IFC (APS) polish.
