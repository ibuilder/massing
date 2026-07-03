# Massing — viewer · GC portal · proforma

![Massing — one IFC model from acquisition to turnover](docs/img/og-image.png)

[![CI](https://github.com/ibuilder/massing/actions/workflows/ci.yml/badge.svg)](https://github.com/ibuilder/massing/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ibuilder/massing?label=release&color=4a8cff)](https://github.com/ibuilder/massing/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ibuilder/massing/total?color=33d17a)](https://github.com/ibuilder/massing/releases)
![Platforms](https://img.shields.io/badge/desktop-Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-555)
![IFC-native](https://img.shields.io/badge/IFC-native-4a8cff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-in%20browser-33d17a)](https://massing.build/app/)

> **Open, self-hosted, IFC-native AEC platform.** A web **BIM viewer + modeling**, a **near-100-module
> GC portal** (RFIs, pay apps, CPM schedule, TRIR), and a **development proforma** — **one model, from
> land acquisition through operations.** Generate a building from a zoning envelope, then coordinate,
> draw, schedule, underwrite & operate it. Built on **That Open + IfcOpenShell**. **$0 to run.**

**What it is** — three pillars on one IFC-keyed model, switched by a Model / Construction / Finance bar:

- 🧊 **BIM platform** — stream + author IFC in the browser (That Open Fragments), QA, IDS, BCF, 2D drawings + **PDF takeoff** (calibrated measure / area / count); **layer & align multiple models** (Navisworks-style) with **federated cross-discipline clash**; also opens **meshes & point clouds** (OBJ/STL/PLY/glTF · PCD/XYZ/**LAS/LAZ**) and **GIS / topography** (**GeoJSON** vectors · **GeoTIFF** DEM terrain) as georeferenced reference overlays, with **QR sharing**
- 🏗 **GC portal** — config-driven modules: RFIs, submittals, change orders, pay apps (G702/G703), CPM schedule, safety/TRIR, closeout (COBie); **specification register → spec-driven submittal log** (AI/rules extraction of typed submittals from the spec book, with missing-submittal coverage); **contract & change-order documents** (AIA-style generate · Exhibit A scope · redline · per-party + **PAdES digital** e-sign); **Report Center** (executive / cost / EVM / logs → PDF + Excel)
- 💵 **Development proforma** — sources & uses, S-curve draws, XIRR/NPV, JV waterfall — seeded straight from the model

![Generate a building from a zoning envelope, then underwrite the deal](docs/img/generate-build.gif)

**[▶ Live demo](https://massing.build/app/)** · **[⬇ Download (Win/macOS/Linux)](https://github.com/ibuilder/massing/releases/latest)** · **[📚 Guides](https://massing.build/guide.html)** · **[📄 Project page](https://massing.build/)**

### Quickstart — self-host the full stack

```bash
docker compose --profile full up --build      # web → http://localhost:8080 · api → http://localhost:8000
docker compose --profile full --profile seed run --rm seed   # optional: a demo project across every module
```

Or install the signed desktop app (single-project, auto-updating) from the [latest release](https://github.com/ibuilder/massing/releases/latest).

**Built on** [That Open](https://github.com/ThatOpen) (Fragments + web-ifc, MIT) · [IfcOpenShell](https://ifcopenshell.org) (LGPL) · [three.js](https://threejs.org) · [FastAPI](https://fastapi.tiangolo.com) · [Tauri](https://tauri.app). IFC is the source of truth — no proprietary format, no per-seat license.

## The whole lifecycle, on one model

Most AEC software covers a single slice — feasibility, or BIM, or construction management. This
platform spans the **whole lifecycle on one IFC-keyed model**: acquisition → due diligence &
entitlements → feasibility → design → preconstruction → construction → turnover → **operations**
(CMMS, metered energy, reserves/CIP, CAM, ESG/POE), with every artifact (proforma, model, RFI,
pay app, COBie, work order, meter reading) tied to the same GlobalIds.

![Lifecycle coverage — one IFC model spans acquisition, feasibility, design, preconstruction, construction and turnover](docs/img/lifecycle.svg)

- **Pre-acquisition** — due-diligence studies (Phase I ESA, geotech, title…) + entitlement
  pipeline with a go/no-go readiness rollup.
- **Feasibility + underwriting** — proforma, sources & uses, investment memo.
- **Concept programming** — spaces as an adjacency graph (area × quantity → gross area + use mix
  that feeds the massing generator).
- **Generative massing + test fit** — zoning envelope → buildable program → real IFC building.
- **openBIM standards (ISO 19650)** — a Common Data Environment (WIP → Shared → Published →
  Archived), information-requirements register (EIR/BEP/AIR), model-quality scoring (IDS compliance,
  LOIN, export health, bSDD), a 10-category BIM-KPI scorecard, and standards-compliance checks.
- **BIM authoring + coordination** — in-viewer modeling, clash detection, IDS validation.
- **AI over the model** — an MCP server so external agents (Claude Desktop) can drive the project,
  drawing-sheet extraction, and grounded standards experts. Offline-first; nothing fabricated.
- **Construction management** — RFIs, submittals, change orders, pay apps, 4D/5D.
- **Turnover** — COBie, as-built, closeout, certified substantial completion (G704).
- **Operations** — CMMS work orders + preventive maintenance, utility meters → EUI, reserve
  study + capital plan, CAM reconciliation, ESG rollup (GHG Scope 1/2) + post-occupancy evaluation.
- **IFC-native, open, self-hostable** — no per-seat license; the desktop app is free.

## What it does

Highlights, all **built and verified** in this repo unless noted:

- **Web viewer** — Three.js + Fragments, streams large models, runs fully offline (local WASM).
- **Navigation & review** — select→properties, spatial tree, layers, isolate/hide, ghost,
  section planes, measure, color-by-data, set-origin/CRS.
- **Coordination** — model federation; **clash detection** (AABB broad phase + mesh
  boolean narrow phase, exact penetration volume) → BCF clash topics.
- **Issues** — BCF-modeled topics/RFIs/punch/clash, viewpoints, comments, attachments,
  pins; `.bcfzip` import/export (round-trips with Solibri/ACC/BIMcollab).
- **QA** — **IDS validation** (ifctester) with failing-element highlighting.
- **4D / 5D** — schedule↔element mapping; quantity takeoff + cost mapping (geometry fallback).
- **Data export** — QTO, COBie, space schedules → XLSX.
- **2D documentation** — dimensioned grid **plans** (grid derived from columns), **sections**,
  **elevations** (N/S/E/W) with level lines, and composed **PDF sheets** with title blocks.
- **Authoring round-trip (in-viewer modeling)** — a full toolbar of authoring ops, each a
  server-side `ifcopenshell` recipe → background republish (reconvert + reindex). GUID-stable,
  so pins/RFIs/clashes survive. **Create:** walls, slabs, columns, beams, roofs (sketch on the
  model/grid). **Openings:** doors/windows void the host wall + fill it. **Edit:** delete,
  move, rotate, copy, per-element Pset edit. **Drafting aids:** grid + corner snap, a 6-face
  section box, a storey-levels overlay. Verified live end-to-end (upload IFC → add wall →
  republish → updated `.frag` + reindex). Desktop GUI authoring is the Blender + Bonsai bridge.
- **Generative design — zoning → a fully-developed IFC building + proforma** — enter a municipal
  zoning envelope (lot, FAR, coverage, setbacks, height
  limit, floor-to-floor) and the platform computes the buildable program (footprint, floors, GFA,
  units, **binding constraint**) and **generates a real IFC4 model** in one call — optionally with a
  **concrete structural frame** (columns + beams on a bay grid), **per-apartment unit layout**, a
  **facade envelope** (walls + ribbon windows at a WWR, feeding the energy model), and a **service
  core** (elevator + stair + MEP risers) — then publishes it and solves a **starter acquisition
  proforma**. Because the output is openBIM, the generated building flows straight into the viewer,
  drawings, energy, QTO, the **assembly-based estimate** (+ GFA benchmark) and underwriting — one
  chain from lot → deal → turnover. Driven end-to-end through a full lifecycle harness (63/63).
- **Furnish & equip (starter IFC family library)** — a curated 16-family catalog (furniture /
  sanitary / appliances / plants) generated parametrically, placeable into *any* model (incl. a
  generated massing) as real, **GUID-stable, typed** IFC occurrences via `type.assign_type`.
- **Sign-in (SSO) + free tier, no admin** — log in with **Google / Microsoft / Procore** (OAuth2);
  SSO users are plain **free-tier** accounts and there's **no admin tier for end users** (project
  owners manage their own teams; platform config is ops/env). A `tier` seam (`entitlements.py`)
  makes the eventual paid plans a one-place change.
- **First-run onboarding + AI assistant** — a skippable welcome + coach-mark tour for new users, and
  an **"Ask AI"** box that answers natural-language questions about a project (open RFIs, overdue,
  cost) grounded in a live snapshot (Claude when keyed; graceful no-key fallback).
- **Field/mobile capture (offline-first)** — a mobile bottom-sheet quick-capture: snap a photo →
  punchlist / safety observation / progress photo in a couple taps. Captures queue offline (photo
  included) and **auto-sync on reconnect** (queued-count badge); pairs with the PWA/Capacitor build.
- **Turnover** — a one-click **closeout package** (`/closeout/package.zip`: as-built IFC +
  COBie/QTO/spaces + status PDF + closeout manifest), **module-log PDFs** (RFI/submittal/CO
  registers), **multi-period pay apps** (period advance + auto **lien waivers**), **COBie tabs**
  enriched with warranties/assets/commissioning, and **warranty-expiry** tracking.

## General Contracting Portal

A construction-management portal on top of the viewer — full writeup in
[docs/gc-portal.md](docs/gc-portal.md). Highlights:

- **Module engine** — every process (RFIs, Submittals, PCO/Change-Order chain, Daily
  Reports, …) is a `module.json` → its own auto-created table. **80 modules / 16 sections**,
  no per-module code. Each gets CRUD, role-gated workflow, comments, CSV/PDF, pins, timeline.
- **Two role dimensions** — capability roles (viewer→admin) + party roles
  (GC/Owner/OwnersRep/Consultant/Subcontractor) that gate workflow transitions.
- **Change-order chain** — PCO ▸ NOC ▸ Directive ▸ Proposal ▸ COR ▸ eTicket, linked and
  audit-logged; approved CORs flow into the contract sum.
- **Financials** — AIA **G702/G703** pay apps (+ PDF), **Cost Summary** roll-up, **eTicket
  T&M builder** priced from rate tables.
- **Schedule** — Gantt + Empire-State **Line-of-Balance** charts.
- **Role-tailored dashboard** — per-party KPIs + "ball-in-your-court" action items.
- **Model pins** — any anchored record (RFI/PCO/COR/punchlist/inspection/…) shows on the
  3D model; clicking selects the element and opens the record. Same GUID keys geometry,
  BCF, and GC records.

## Real-Estate Development & Feasibility (Finance workspace)

A developer/owner platform that goes **lot → building → deal → investor package**, all IFC-native.

**Generative design & Test Fit** (openBIM — every fit is a real IFC model):
- **Generate from zoning** — lot + zoning envelope (FAR, setbacks, height, coverage) → a buildable
  program + a from-scratch **IFC4** model (structural frame, per-unit spaces, facade + windows,
  service core) + a solved acquisition proforma, one click. Real **lot polygons** (shoelace area).
- **Test Fit** — fit a unit mix on a **double-loaded corridor** (real units + corridor), a **parking
  solver** (stalls/unit → count/area/cost), **scheme compare** (units/efficiency/NSF/parking ranked),
  and **generative optimize** that sweeps unit-mix × parking and ranks by **yield-on-cost** ("find the
  deal that pencils"). `POST /test-fit/{compare,optimize}`.

**Developer cost portal** — the institutional underwriting facets:
- **Line-item hard/soft cost budgets** (description × $/unit × qty + per-category contingency) that
  roll into the proforma cost tree.
- **Sources & Uses** — grouped uses vs sized senior debt (LTC capped by LTV/DSCR/debt-yield) + equity.
- **Property & tax assumptions** — parcel/areas/purchase + tax table → OPEX; per-SF ratios.
- **Specialty assets** — on-site **energy** (solar/wind/battery/rainwater → capex + energy offset) and
  **vertical-farm/PFAL** (tower count → produce revenue + lighting opex), flowing into the deal.
- **Investment memo (PDF)** — a confidential memorandum (exec summary, S&U, cost budget, returns,
  risk) generated from live project data: the "presentation with financials."

**Underwriting engine:**
- **Sources & uses** with construction-loan **interest-reserve circularity** solved to a fixed point.
- **S-curve draws**, **XIRR / NPV / equity multiple / yield-on-cost**, a **JV waterfall** (pref +
  promote tiers, American/European, clawback), **debt sizing** (LTC/LTV/DSCR/debt-yield), **sensitivity**
  tables and **Monte Carlo** risk.
- **Underwriting realism** — specialty/operating revenue is **risk-adjusted** (not booked as de-risked
  rent), and **guardrails** flag returns outside market bands (IRR / equity-multiple / dev-spread /
  DSCR) so the IRR is credible, surfaced on a sticky returns bar.
- **Actuals/draws bridge** → re-forecast IRR + AIA G702/G703 pay apps off the *same* cost tree.
- **Multi-deal portfolio** roll-up (true XIRR) and **LP-shared** read-only scenarios.

The Finance workspace is organized into sub-tabs — **Feasibility · Budget & Capital · Underwriting ·
Deliverables** — with a sticky live-solved returns bar.

## Recent platform work

- **Architect/engineer design-to-turnover lifecycle (latest, v0.3.49+)** — the classic design lifecycle
  made first-class, grounded in the RIBA Plan of Work 2020 (stages 0–7), AIA phases (SD/DD/CD/CA) and
  ISO 19650. A **"🧭 Project Lifecycle"** panel lays out the eight phases as formal **gates** — each with
  its deliverables, A/E design-fee share and ISO-19650 information status — that the **Architect + Owner**
  sign off before the project advances. Soft costs are now **itemized** (A/E fee, permits, legal,
  financing, insurance/bonds, developer fee, FF&E, marketing, contingency) with the design fee drawn down
  across the phases, instead of a flat percentage. A shippable **IFC family library** now backs the
  viewer's Furnish & equip picker — a generated `library.ifc` of 46 GUID-stable openBIM families
  (furniture, sanitary, appliances, MEP, structural, **doors/windows/walls**) plus a curated-external
  import path. The AIA construction-phase change instruments are now first-class — **ASI (G710)**,
  **Bulletin**, and **Sketch (SK)** modules wired into the change chain, with G710/Bulletin/G714 (CCD)
  document generation. And turnover is closed out: the **Architect certifies substantial completion**
  (**AIA G704**), signs off the punch list, and the as-built **record model** version is stamped and
  bundled into the signed turnover package — a **"🏁 Turnover"** panel drives it end to end.
- **AI + fintech + BIM-standards depth, then a code-quality & hardening pass (v0.3.41–v0.3.48)** —
  three rounds of capability depth, each engine offline/deterministic with AI only where it earns its
  place, always source-linked and never fabricating:
  - **AI assist** — draft RFIs / scopes / submittal summaries from a note or PDF, bid leveling, and
    auth-gated cross-project benchmarking (**AI Assist** panel).
  - **Fintech & risk** — subcontractor prequalification scoring + COI-expiry, pay-app ↔ lien-waiver
    reconciliation with per-vendor exposure, and GL/QuickBooks accounting export (**Risk & Cost** panel).
    Money movement stays behind a feature-flagged licensed-processor bridge — the platform never moves
    money itself.
  - **Model intelligence** — embodied carbon (A1-A3), model-grounded code-compliance Q&A, takeoff
    priced to a unit book, **conceptual $/SF estimating** at the massing stage, and **AI IfcClass
    classification** that lifts QTO + carbon accuracy.
  - **Materials procure-to-pay** — supplier quote leveling + **3-way match** (PO ↔ delivery ↔ invoice).
  - **BIM standards** — **IDS authoring**: emit a standards-valid buildingSMART IDS 1.0 file + an EIR
    contract document (**IDS Requirements** panel), closing the spec → implement → validate loop.
  - **Land screening** — screen a parcel set by size / zoning / flood / utilities → max-buildable
    envelope + conceptual cost (**Land Screening** panel); nationwide parcel data is an optional
    connector.
  - **Engineering quality** — a blocking `ruff` static-analysis gate + `bandit` security scan in CI, an
    outbound-URL guard on operator-configured fetches (webhooks / bridges), and a fixed BCF XXE. Backend
    gate: 97 suites.
- **Specifications → submittals · preconstruction depth (v0.3.7)** — the CSI
  spec-to-submittal workflow, end to end. A **specification register** (project manual) module
  (MasterFormat section, division, the Part 1 *Submittals* article, products, responsible party),
  a **spec-driven submittal log** that derives the *required* submittals per section — typed
  (Shop Drawing / Product Data / Sample / Mock-up / Certificate / Test Report / Calculations /
  O&M / Warranty) — and reconciles them against what's actually been logged to surface **missing
  submittals** per section with a coverage %, and **AI/rules submittal extraction**: paste a spec
  (or its Submittals article) → a typed submittal list (Claude when a key is set, a deterministic
  built-in parser offline), one click to log them and build the register straight from the spec book.
  New **Spec-Driven Submittal Log** report (PDF/Excel). Builds on the **preconstruction-depth** work
  (v0.3.0–v0.3.6): estimate-continuity across design milestones, decision log, assumptions register,
  value-engineering cycle, and a calibrate-style alignment dashboard.
- **Construction analytics suite · RE/capital depth · production hardening (v0.2.14)** — a
  read-side analytics layer over every core field log — **quality** (inspection pass-rate / first-pass
  yield, NCR disposition→close loop, deficiency ball-in-court), **RFI register** (ball-in-court /
  overdue / turnaround / cost-schedule impact), **submittal register**, **T&M** (with the
  field-T&M→change-event→CO tie), **field-log rollup** (manpower / weather lost-days / coverage),
  **OSHA safety** (TRIR / DART / LTIFR), and a **closeout dashboard** (punchlist ball-in-court,
  commissioning, warranties) — each a live tool + an exportable PDF/Excel report, stitched into an
  executive **project-health rollup**. Plus **real-estate / capital depth**: a feature-flagged
  **WPRealWise / MLS listing syndication** bridge (RESO), **lease management** (renewals · escalations ·
  CAM recovery), cap-table-tied **equity-waterfall distribution scenarios**, **investor-portal** signed
  statement sharing, and **comparables import** (CSV / RESO). Hardened for production: empty-project
  robustness (regression-locked), **non-root API container**, and a tested `/metrics` Prometheus surface.
- **Operate · capital · payroll · drawings · assistant · ITB (v0.1.89)** — six capability
  additions: an **operating rent roll** (leases → occupancy/WALT/expirations,
  feeding the appraisal income approach), an **investor cap table** with pro-rata capital calls &
  distributions, **WH-347 certified payroll** from timesheets, a controlled **drawing-set register**
  (current vs superseded revisions), a whole-project **AI assistant**, and **ITB** invitation/coverage
  tracking.
- **Model intelligence, field verification & embeddability (v0.1.88)** — **Ask the model** in
  plain English (`/ask`, grounded in the property index; degrades to a data snapshot without an AI key);
  **field verification** — mark elements installed/verified/deviation vs design (photo-anchored) with an
  **install-coverage** dashboard + deviation log for the ops handover; an **`?embed=1`** chrome-less,
  read-only viewer for `<iframe>`/Teams embeds; and **outbound webhooks** on workflow transitions
  (Power Automate / Zapier), all on the open, self-hosted posture.
- **Workflow engine upgrades (v0.1.87)** — config-driven modules engine gains **transition
  field-gating** (`requires: [field]` — RFI can't be Answered without an answer), a **Company/Contact
  directory** with first-class `reference` lookups (e.g. a subcontract's vendor), a cross-module
  **due/overdue SLA feed** ("⏰ Deadlines" on the portal home), and an **in-app workflow map** on the
  record view.
- **Disposition & valuation (v0.1.86)** — close the loop from build to **sell/lease**: a
  `listing` module that **auto-fills from the model + proforma** (areas/NOI/cap/asking price), a
  one-click **marketing fact sheet** + a signed **public link/QR** to share off-plan, and a
  **tri-approach appraisal** (cost + income + sales-comparison, reconciled) with a Valuation tab and
  PDF/Excel report. RESO-aligned so listings can later push to an MLS / the WPRealWise suite. See
  [docs/realestate-marketing.md](docs/realestate-marketing.md).
- **Production readiness (v0.1.85)** — a DB-pinging `/ready` (+ `/readyz`) readiness probe
  (503 when the DB is down) alongside the cheap `/health` liveness check; the login brute-force lockout
  now shares its counter across workers via `AEC_REDIS_URL` (the API runs multi-worker), fail-open to
  in-process; `docker-compose.prod.yml` is hardened by default (RBAC, require-secret, HSTS, secure
  cookie, strict CSP, rate limit + a `redis` service) and `.env.example` documents every flag; and the
  additive startup schema-sync (vs Alembic — it fits the config-driven module tables) is documented in
  [SECURITY.md](SECURITY.md) and covered by `test_migrate.py`.
- **Security hardening (v0.1.84)** — a defense-in-depth RBAC gate (anonymous blocked from
  project/finance/admin surfaces when `AEC_RBAC=1`) + `require_role` on every project-scoped endpoint;
  hardening response headers + opt-in strict CSP; request body-size cap; storage path-traversal +
  upload-filename sanitization; attachment-download IDOR fix + member-scoped project list; login
  brute-force lockout, `Secure` auth cookie, and fail-fast on a default signing secret; **signed/expiring
  download URLs** for `model.frag` + attachments. See [SECURITY.md](SECURITY.md).
- **Charts & graphs (v0.1.83)** — a dependency-free, theme-aware SVG chart kit drives
  construction/RE best-practice visuals: a **capital-stack** donut, **JV-distribution** donut, equity
  cash-flow bars and a one-way **IRR tornado** on the Underwriting tab; **NOI vs net-income** and
  **cash-flow-by-year** charts on Statements; **progress bars** + a **budget vs committed vs actual vs
  EAC** grouped bar in the GC portal; and charts embedded in the Report Center PDFs (cost bar, EVM
  S-curve, financials line).
- **Financial statements & tax (v0.1.82)** — the Finance proforma gains a **Statements** tab
  (and a Report-Center PDF/Excel): a stabilized **income statement** (PGR → EGI → NOI → depreciation →
  net income), a **balance sheet** that ties to the dollar every year, a GAAP three-section
  **cash-flow statement**, a **tax** schedule (27.5/39-yr straight-line depreciation, annual income
  tax, and at sale **§1250 recapture** + **capital gains** + NIIT → an **after-tax IRR**), and the
  development budget as a two-sided **Uses ∣ Sources** view. `POST /proforma/financials`,
  `GET /projects/{pid}/financials`, `GET /projects/{pid}/budget/two-sided`.
- **Inspection, intel & robustness (v0.1.81)** — a rebuilt **element properties panel**:
  structured **Attributes / Quantities / Property Sets** (IFC quantities now surfaced), value
  formatting, a live **filter**, click-to-copy + **Copy all**, and a collapsible-tree fallback.
  **Interchangeable municipal permit open data** — a Socrata feed across **NYC · SF · Chicago · LA ·
  Austin** (one entry to add a city), normalized to one shape; query near a site, a **GeoJSON GIS
  overlay**, and a one-click **import into the GC permit log** (source-tagged, deduped). A rule-based
  **schedule-acceleration advisory** (crash / fast-track / near-critical off the CPM critical path), a
  **project risk digest** (cost + schedule + open items + safety), a **Report Center** (every report →
  PDF **and** Excel), **PDF digital signatures (PAdES)** + AIA-style contract / exhibit / change-order
  documents, **GIS/topography** (GeoJSON + GeoTIFF DEM) · **PDF takeoff** · **GAEB X83** · **AI text→BOQ**,
  Navisworks-style **model federation** (per-model transforms + **federated clash**), **mesh + point-cloud
  (LAS/LAZ) reference overlays** with **QR share**, and reliability hardening — **Sources & Uses now
  reconciles to the dollar**, **BCF pins round-trip with their GUID tie + anchor**, and the backend suite
  grew to **47**. See the [CHANGELOG](CHANGELOG.md).
- **One relational model — schedule · budget · 5D · capital** — the GC `schedule_activity`
  records now drive the Gantt / Line-of-Balance / CPM **and** the 3D 4D scrub (per-activity dates,
  element/trade links), with **lookahead** + **milestone** views and editable P6 `.xer` import. On top
  sits a collaborative **pull-planning** board (Last Planner System): each trade posts its own
  `pull_plan_task` sticky notes across a trade-swimlane × week matrix, defines the hand-offs, and
  clears **constraints** to make work ready — scored by readiness and **PPC** (Percent Plan Complete),
  exportable as a **PDF** for the planning session. A
  first-class **Budget** destination assembles the agreed **GMP** from every cost code & bid package
  + General Conditions / Requirements (incl. **staffing** projections) + overhead / fee / contingency
  — each budget vs committed vs actual vs **EAC**, with buyout savings, change-orders→revised-GMP,
  owner **SOV from the budget**, a **cash-flow S-curve**, and a baseline; it reconciles to the
  developer proforma's hard cost. The capital chain closes the loop: **GMP↔hard-cost sync**, an
  **actuals loop** (owner invoices → re-forecast IRR), **construction-loan draws** (equity-first,
  interest accrual, lender draw-request PDF), a cross-pillar **Portfolio** (GC status + developer
  returns), and **on-schedule/on-budget** executive bands. **5D**: click an element → its activity +
  cost-code budget; colour the model by %-complete or cost variance; scrub the 4D timeline with live
  cost burn; **QTO by floor & discipline**. Plus **multi-user** (members → role-scoped persona
  views), bulk site-photo + camera capture, and an optional **paid Revit (.rvt)→IFC bridge** (APS,
  feature-flagged with a cost gate; IFC stays the source of truth). One click (lot→building→deal)
  seeds all three pillars. See the [CHANGELOG](CHANGELOG.md) (v0.1.53→v0.2.7).
- **Rendering, families & computational design (M-theme)** — a viewer **render mode** (directional
  sun + soft shadows, ACES/PBR, IBL), a NOAA **sun-&-shadow study** (date · time · lat/long), and a
  Matterport-style first-person **walkthrough**; Revit-style **`IfcMaterialLayerSet` assemblies** on
  walls/slabs/roofs; the family library grown to **37 parametric types** (Lighting/MEP/Structural/
  Transport added) with **type-variant sizing** and **import of external/manufacturer IFC families**
  (`project.append_asset`); and **Studio**, a visual **computational node graph** (Dynamo/Hypar-style)
  that runs the server compute engine — wire zoning → structure → schedule → cost → yield with no code.
- **Hardening & ops** — distributed **Redis-backed rate limiting** (multi-worker, fail-open), a
  faster **dashboard** (GROUP-BY counts, JSON parsed only for active records), an **accessibility**
  pass (tab roles/`aria-selected`, labels, live region), a **stored-XSS** sweep of the admin modals,
  and `main.ts` modularization (the connections UI is now a lazily-loaded chunk). COBie handover gains
  model-derived **areas / manufacturer / warranty / asset-id** fields + an **Attribute** sheet; the
  pitch deck gains **Market** + **Timeline** slides. Library interop evaluated (IFClite / pyRevit /
  FreeCAD / Pascal) — see `docs/roadmap.md` §L and the dependency/update ADR.
- **Built-world techniques (research-grounded)** — direction from Carol Willis (*Form Follows
  Finance*, *Building the Empire State*), Salvadori (*Why Buildings Stand Up*), and CM/RE research:
  **form-follows-finance** massing (daylight-limited rentable depth + core efficiency), a
  **structural-system advisor** (flat-plate · shear-core · outrigger by height/span + member sizing),
  **takt / line-of-balance** scheduling with a JIT delivery plan, **4D sequencing** with a viewer
  scrub, **lean / Last-Planner PPC**, and citable **benchmarks + comparables**.
- **Underwriting realism + Finance revamp** — specialty/operating revenue is now risk-adjusted before
  it hits the deal, and `underwrite.guardrails()` flags returns outside market bands (the
  vertical-farm scenario's once-inflated IRR is now credible). The Finance view is reorganized into
  sub-tabs with a sticky returns bar that carries a live guardrail badge.
- **Developer portal + Test Fit** — line-item hard/soft **cost budgets**, **Sources & Uses**,
  **property/tax** assumptions, **specialty assets** (on-site energy + vertical-farm revenue), an
  **investment-memo PDF**, plus **Test Fit** (corridor unit-mix layout, parking solver, scheme
  compare, generative yield-on-cost optimize) and **real lot polygons** — see the
  "Real-Estate Development & Feasibility" section. Each backed by tests in the CI gate.
- **AI assistant** — natural-language **"Ask AI"** over a live project snapshot (Claude when keyed,
  graceful rules fallback) alongside AI risk summaries + AI-drafted RFIs.
- **AI Assist + Benchmarks** — draft **RFIs**, **submittal summaries**, and trade **scopes of work**
  from a note or a PDF (editable, source-cited, human-in-the-loop before Create); **bid leveling** that
  normalizes a package's bids into an apples-to-apples grid with outlier + **scope-gap** detection and a
  scope-adjusted low recommendation; and cross-project **Benchmarks** — actual cost distribution per
  cost code (p25/median/p75) and RFI/submittal turnaround + overdue %. All offline-capable (Claude when
  keyed). Every AI engine ships with a deterministic fallback so nothing is fabricated.
- **Risk & Cost** — subcontractor **prequalification Q-score** + **COI-expiry** tracking, **pay-app ↔
  lien-waiver** reconciliation surfacing per-vendor **lien exposure** (payments run only through a
  licensed processor, gated on waiver coverage — Massing never moves money), **accounting export** (GL
  CSV + QuickBooks IIF), **embodied carbon** (A1-A3, from material quantities × EPD factors), a
  **code-compliance** assistant (IBC/ADA/IECC sections with citations), and **priced takeoff** with
  variance vs the estimate.
- **Accounts & onboarding** — **SSO** (Google / Microsoft / Procore), a no-admin free-tier model,
  first-run **welcome + skippable tour**, and **field capture** (offline photo → punchlist/observation,
  syncs on reconnect) for the mobile/jobsite path.
- **Generative massing + family library** — `aec_data.massing` turns a zoning envelope into a
  buildable program + a from-scratch **IFC4** model (`POST /projects/{id}/generate/massing`, plus a
  stateless `/generate/massing/preview`) and seeds a solved acquisition proforma; `aec_data.families`
  generates a 37-family parametric type library (`GET /families/catalog`) placed via the `add_family`
  authoring recipe. Both render in the viewer (fixed two web-ifc gotchas surfaced en route: generated
  models now use **metre** units, and every `IfcProfileDef` carries a `Position` — without it web-ifc
  silently skips the geometry). Gated by `test_generate` in the CI suite.
- **4-zone UI** (top chrome + Model/Construction/Finance workspaces + left icon rail + bottom
  settings bar) with a **lazy-loaded 3D viewer** — the ~6 MB three/@thatopen bundle loads only
  when the Model workspace opens, so portal/finance users get a ~16 KB-gzip first load.
- **Module relations** — `reference` fields + reverse lookups + numeric **rollups** wire the
  domain chains across the portal (RFI/Submittal→Drawing, RFI→ChangeEvent→PCO→COR→Subcontract,
  budget/SOV/timesheet→CostCode cost-coding, Meeting→ActionItems, Inspection→NCR/Deficiency,
  bidding, daily/field, closeout, …) — 44 references + 16 rollups, all config-driven so the
  form record-picker, "related" panel, and rollups come for free. Plus a **kanban board**,
  **cross-module search**, **bulk actions**, **inline list editing**, **saved views**, and
  real-time **SSE notifications** — all engine-level, so every module gets them.
- **Background conversion** — IFC convert/reindex runs off-thread; clients poll a publish status.
- **In-viewer modeling** — 18-tool authoring toolbar (walls/slabs/columns/beams/roofs,
  doors/windows, delete/move/rotate/copy, Pset edit) + grid/corner snap, section box, levels
  overlay — all server-authored via `ifcopenshell` and proven live.
- **Interoperability** — a data-source **Connections** framework: register external
  **Postgres/Supabase** (read-only table browse + a guarded SELECT console), **Procore**
  (two-way sync — import RFIs/submittals/change-events into the portal, push resolved RFI
  status/answers back, scheduled auto-sync), **Autodesk Construction Cloud** (project/issue read),
  and **accounting/ERP** — **QuickBooks** + generic-REST **Sage/Viewpoint** (read accounts /
  vendors / bills) — all behind one adapter pattern. An admin **field-mapping editor** remaps each
  external field → module field per connection; secrets are write-only and masked on read; admin-gated.
- **Construction & financial depth** — **CPM scheduling** (forward/backward pass, total+free
  **float**, critical path); **model-based estimating & takeoff** (IFC quantities × unit rates →
  priced estimate); **model→proforma** (areas seed hard cost + rent); **bid leveling**; a **risk
  register** + cross-project **construction program portfolio** with cost-overrun flagging;
  **TRIR/DART safety analytics**; **reusable templates** (save a module's records, apply to any
  project); and **model version history + diff** (GUID snapshot per publish). The GC portal +
  proforma run on a **blank project — no IFC required**; model-derived tools light up once an IFC
  is opened.
- **Free single-project desktop app (.exe)** — the whole platform in **one process** (FastAPI
  serving the API + SPA, SQLite + local files, single-operator local mode, no login), packaged
  self-contained with PyInstaller (`services/api/desktop.py`, `build-desktop.ps1`) — a
  Bluebeam-style local app; data lives under `%LOCALAPPDATA%\AEC-BIM`, uninstall = delete the
  folder. Projects are portable **`.mmproj` bundles** (geometry + all data + attachments) via the
  Open/Save menu. The Tauri 2 shell spawns this backend as a sidecar for a **native window**;
  mobile (Capacitor/Tauri-mobile) is next.
- **UX** — the ⚙ Tools panel is a collapsible, **persona-ordered**, state-aware accordion with
  **readable result modals** (cost/energy/IDS/clash); the **80-module portal catalog** gains ★
  favorites + collapsible persona-aware sections + a filter; the viewer toolbar is grouped. The
  project picker tags each project's model type (`.frag`/`.ifc`). (See `docs/ux-findings.md`.)
- **Installable + offline** — PWA (manifest + Workbox service worker; lean ~97 KB precache,
  viewer libs/WASM/tiles runtime-cached).
- **Authentication** — username/password accounts (PBKDF2-hashed) + signed bearer tokens
  (stdlib, dependency-free) at `/auth/{register,login,me}`. The token is the identity the RBAC
  layer trusts (replacing the dev `X-User` header); per-project authorization stays in
  `ProjectMember`. First account bootstraps as admin. Web app has a sign-in control + token
  store. Login also sets an **httpOnly cookie** so the SSE notification feed and
  direct-download links (which can't set a header) authenticate same-origin via the `/api`
  proxy; `/auth/logout` clears it. *(Dev cross-origin `:5173→:8000` uses the header path;
  the cookie applies to the deployed same-origin stack.)*
- **Identity & RBAC management** — admin user management (create / list / set role / activate /
  deactivate / reset password) with a last-active-admin guard; **self-service password reset**
  via an admin-issued single-use token (no email infra); deactivation invalidates existing
  tokens immediately. The web UI **gates per project role** — authoring tools, the authoring
  panel, "+ RFI", and the portal "+ New" hide above the caller's role (the API still enforces).
- **Risk + debt sizing (Proforma)** — **Monte Carlo** simulation (sample drivers → P5–P95,
  P[IRR ≥ target], histogram) alongside the deterministic sensitivity table, and debt sized to
  the lesser of **LTC / LTV / DSCR / debt-yield** constraints.
- **Drawings** — element **callouts with leader lines** on plans (doors/windows by default),
  complementing room tags (`plan.svg?callouts=true`).
- **Ops & observability** — `/metrics` (Prometheus: request counts/latencies by route template,
  in-flight, uptime) + structured JSON access logs; **email digests** of per-member work queues
  (stdlib SMTP, no-op-but-logged when unconfigured); a **backup/restore runbook** + scripts
  (`scripts/backup.sh` / `restore.sh`: pg_dump + MinIO/IFC volumes).
- **Desktop release CI** — tag-driven GitHub Actions builds signed Win/macOS/Linux Tauri
  installers (`.github/workflows/desktop.yml`); each runner first builds the Python backend
  sidecar (PyInstaller) so the installer ships the full app, not just the viewer. A viewer-only
  **GitHub Pages** demo deploys from `pages.yml`.
- **CI gate** — `services/api/run_tests.py` runs all Python suites (incl. interop/bundle/desktop/
  local-mode); GitHub Actions runs it + the web build (tsc + vitest + prod build).

## Gallery

**Generative design — lot → IFC model → acquisition proforma** (openBIM end to end): a zoning
envelope generates a real IFC massing you can then furnish from a starter
family library. (Vector renders of the redesigned UI; numbers are an actual solve.)

| Generate from zoning → IFC + proforma | Furnish & equip (starter IFC family library) |
|---|---|
| ![generate from zoning](docs/img/massing_generate.svg) | ![furnish library](docs/img/furnish_library.svg) |

Generated directly from the IFC by the data service (BIM), plus GC schedule charts:

| Dimensioned grid plan | Composed sheet (A3) | North elevation (HLR) | Room tags |
|---|---|---|---|
| ![plan](docs/img/plan_grid.png) | ![sheet](docs/img/sheet.png) | ![elevation](docs/img/elevation_north.png) | ![rooms](docs/img/room_tags.png) |

The dimensioned plan derives the structural grid from column positions (no `IfcGrid` needed),
adds numbered/lettered bubbles and grid-spacing dimensions; the sheet composes per-storey
plans + a section under a title block (also exported as PDF).

GC portal schedule visuals (from the `schedule_activity` module):

| Gantt | Line of Balance |
|---|---|
| ![gantt](docs/img/gantt.png) | ![lob](docs/img/lob.png) |

Platform interface (vector renders of the redesigned UI — see the [live demo](https://massing.build/app/) for the running app):

| Tools panel + readable results | 80-module portal catalog |
|---|---|
| ![tools panel](docs/img/ui-tools-panel.svg) | ![portal catalog](docs/img/ui-portal-catalog.svg) |

The ⚙ Tools panel is a persona-ordered, collapsible, state-aware accordion (secondary tools fold
under "More tools"; analysis opens in a readable modal); the GC-portal catalog tames 80 modules
with ★ favorites, collapsible persona-aware sections, and a filter.

## Architecture

```
            IFC  (source of truth)
   author ▲                       │ convert + tile
          │                       ▼
  Blender + Bonsai         services/converter (Node)   IFC → .frag tiles
  (Bonsai-MCP)                    │
  services/data (Python, ifcopenshell)                 props index · QTO/COBie/4D/5D ·
    clash · IDS · drawings/sheets · authoring recipes   exports · validation · 2D drawings
          │                       │
          └──────► services/api (FastAPI) ◄──────► apps/web (Vite + TS, Three.js + Fragments)
             BCF issues · pins · viewpoints · properties · exports · clash · validate ·
             drawings/sheets · edit/publish      (Postgres/SQLite + MinIO/local storage)
```

## Layout

```
apps/web/            Vite + TS viewer (Three.js + @thatopen/*), integrated app shell
apps/editor-bridge/  Bonsai-MCP config + authoring recipes (desktop path)
services/converter/  IFC→.frag (Node) + optional RVT→IFC via APS (paid, flagged)
services/api/        FastAPI: BCF, properties, exports, clash/validate, drawings, edit/publish,
                       GC portal (modules, cost, schedule, dashboard)
services/api/modules/  80 module.json definitions (GC portal — one table each)
services/data/       IfcOpenShell: index, QTO, COBie, spaces, schedule, clash, IDS, drawings, edit,
                       massing (zoning→IFC), families (starter IFC type library)
packages/            shared types
families/            IFC type libraries (versioned) — curated/manufacturer content drop-in
docs/                status, capability matrix, gc-portal, deploy, images
```

## Run the full stack (Docker — easiest)

```bash
git clone https://github.com/ibuilder/massing.git && cd Massing
cp .env.example .env            # set secrets + AEC_RBAC=1 for anything but local dev
docker compose --profile full up --build      # web → http://localhost:8080  (api → :8000)

# optional: fill a demo project across all relation chains
docker compose --profile full --profile seed run --rm seed
```

The web container reverse-proxies `/api` to the API (same-origin, no CORS), serves the
viewer with the cross-origin isolation web-ifc needs, and persists Postgres/MinIO/IFC volumes.
See [`.env.example`](.env.example) for every knob and [docs/roadmap.md](docs/roadmap.md)
for the desktop (Tauri/Electron) and mobile (Capacitor) packaging plan.

**Running it in production?** Start with the [operator runbook](docs/operations.md) (health probes,
env flags, backup/restore, common incidents), backed by [docs/deploy.md](docs/deploy.md) for the full
stack. **Adding your own record type?** No code needed — see
[Authoring a module](docs/authoring-modules.md). Every endpoint is live-documented at `/docs` on the
running API.

## Quick start (dev)

```bash
# 1. web viewer (offline; copies WASM automatically)
cd apps/web && npm install && npm run dev          # http://localhost:5173

# 2. backend API (prefer Python 3.11+; 3.10 works)
cd services/api && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn aec_api.main:app --reload    # http://localhost:8000

# 3. convert an IFC to Fragments (Node converter)
node services/converter/src/cli.mjs model.ifc model.frag

# 4. data exports / drawings (CLI)
cd services/data && pip install -r requirements.txt
PYTHONPATH=src python -m aec_data.cli qto model.ifc qto.xlsx
```

Seed a project, then the web app auto-connects: `POST /projects` with `source_ifc`, upload
the props index, and open the viewer. See [docs/status.md](docs/status.md) for the verified flow.

## API surface (selected)

```
POST   /projects                              create project (name, source_ifc, origin)
GET    /projects/{id}/elements[/{guid}]       properties index (Phase 1 data)
GET/POST /projects/{id}/topics ...            BCF topics/RFIs/pins, comments, viewpoints, attachments
GET/POST /projects/{id}/bcf/export|import     .bcfzip round-trip
GET    /projects/{id}/exports/{qto,cobie,spaces,schedule}.xlsx
POST   /projects/{id}/clash                   clash detection (→ BCF clash topics)
POST   /projects/{id}/validate                IDS validation
GET    /projects/{id}/drawings/{plan,section,elevation}.svg
GET    /projects/{id}/drawings/sheet.{svg,pdf}
POST   /projects/{id}/edit | /publish         authoring round-trip (recipes incl. add_family)
POST   /projects/{id}/generate/massing        zoning → IFC massing model + acquisition proforma
POST   /generate/massing/preview              stateless zoning → program + proforma (no model written)
GET    /families/catalog                      starter IFC family library (furnish & equip)

# GC portal (full list in docs/gc-portal.md)
GET    /modules                               module catalog
GET/POST /projects/{id}/modules/{key}[/{rid}] config-driven CRUD (+ /transition /link /comments /pdf /export.csv)
GET    /projects/{id}/module-pins             anchored records → viewer overlay
GET    /projects/{id}/cost/{g703,g702,summary} financials (+ g702.pdf, POST /cost/tm)
GET    /projects/{id}/schedule/{gantt,lob}.svg  Gantt + Line-of-Balance
GET    /projects/{id}/schedule/{cpm,alerts,optimize}  CPM · predictive alerts · acceleration advisory
GET    /projects/{id}/{risk-digest}           cost+schedule+open-items+safety risk digest
GET    /reports · /projects/{id}/reports/{report}.{pdf,xlsx}   Report Center (PDF + Excel; incl. appraisal · listing_factsheet)
GET    /opendata/permit-cities · /projects/{id}/opendata/permits[.geojson]   municipal permit feed
POST   /projects/{id}/opendata/permits/import   seed the GC permit log from a city's open data
GET    /projects/{id}/dashboard · /due-feed    role-tailored dashboard · cross-module due/overdue SLA feed
POST   /projects/{id}/ask · /assistant         Q&A over the model index · over the whole project (modules/schedule/budget)
GET    /projects/{id}/verification/coverage    install coverage (verified/installed %) + PUT .../{guid} · /deviations
GET    /projects/{id}/rent-roll · /cap-table   operating rent roll (occupancy/WALT) · investor cap table
POST   /projects/{id}/capital-call · /distribution   pro-rata investor allocations
GET    /projects/{id}/payroll[/wh347.pdf]      weekly certified payroll (WH-347) from timesheets
GET    /projects/{id}/drawing-set              controlled drawing set (current vs superseded revisions)
GET    /projects/{id}/bidding/itb · POST .../packages/{id}/invite   ITB coverage tracking · invite bidders
# disposition & valuation (real estate)
GET/POST /projects/{id}/appraisal             tri-approach valuation (cost · income · sales-comparison, reconciled)
GET    /projects/{id}/listings/autofill        listing fields pre-filled from the model + proforma
GET    /projects/{id}/listings/{lid}/reso      RESO Data Dictionary export (MLS / WPRealWise bridge seam)
POST   /projects/{id}/listings/{lid}/share · GET .../public   signed, read-only public listing link (QR share)

# interoperability + portability
GET/POST /connections[/{id}]                  data-source connections (Postgres/Supabase/Procore/ACC)
GET    /connections/{id}/tables | POST .../query   read-only browse + SELECT (SQL sources)
GET/PUT /connections/{id}/mappings            admin field-mapping editor (external → module fields)
POST   /projects/{id}/sync/procore[/push]     Procore import + two-way push (+ /sync/schedules)
GET    /connections/{id}/acc/projects/{pid}/issues   Autodesk Construction Cloud issue read
GET    /projects/{id}/bundle | POST /projects/import-bundle   portable .mmproj save / open
DELETE /projects/{id}                          delete a project (rows + geometry + attachments)
```

## Verification

Every feature here was run against the sample model. The latest end-to-end proof: IDS flagged
299 slabs missing `LoadBearing` → the authoring round-trip edited them → republish → IDS
re-validated **PASS (299/299)** with the slab's pin GUID unchanged. Regressions: web `tsc`,
API smoke test, and Python compile all green.

## Licensing

Open stack (That Open MIT-style, IfcOpenShell LGPL). The Blender + Bonsai desktop editor is
**GPL** — kept a separate process you *use*, not linked in. Optional Autodesk APS RVT→IFC is
paid/flagged. See [LICENSE-NOTES.md](LICENSE-NOTES.md).

## Author

Created by **Matthew M. Emma** — built with [Claude Code](https://claude.com/claude-code) as AI assistant.
