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
- **A6 — Site test-fit (urban/parcel).** Real lot polygon (not a rectangle) → place building
  footprint(s) + parking + drive aisles + setbacks on the actual parcel.

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

## C. Lifecycle / construction depth
- ✅ Field capture (offline), module-log PDFs, closeout package ZIP, auto-TRIR, subject alias.
- **C1 — Multi-period pay apps** (draws across periods, retainage release) + auto lien waivers.
- **C2 — COBie field-enrichment** (fold assets/warranties/commissioning into the COBie tabs) +
  warranty date tracking + O&M reminders.
- **C3 — 4D sequencing** from the CPM schedule against the model (timeline scrub).

## D. Platform / production
Tracked in [production-readiness.md](production-readiness.md): main.ts account/connections split,
dashboard JSON-extraction perf, Redis-backed rate limits (multi-worker), CI dependency scanning,
a11y pass. Plus: mobile (Capacitor) build hardening; RVT→IFC (APS) polish.

---

## Near-term execution order
**B2 Sources & Uses** → **B3 property/tax assumptions** → **A1 unit-mix configurator** →
**A3 parking solver** → **A4 yield compare** → **A5 generative targets**. Each ships independently
behind tests + a release.
