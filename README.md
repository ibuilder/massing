# Massing — in-browser BIM authoring · construction docs · GC portal · proforma

![Massing — one IFC model from acquisition to turnover](docs/img/og-image.png)

[![CI](https://github.com/ibuilder/massing/actions/workflows/ci.yml/badge.svg)](https://github.com/ibuilder/massing/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ibuilder/massing?label=release&color=4a8cff)](https://github.com/ibuilder/massing/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ibuilder/massing/total?color=33d17a)](https://github.com/ibuilder/massing/releases)
![Platforms](https://img.shields.io/badge/desktop-Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-555)
![IFC-native](https://img.shields.io/badge/IFC-native-4a8cff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-in%20browser-33d17a)](https://massing.build/app/)

> **Open, self-hosted, IFC-native AEC platform.** A genuine **in-browser BIM authoring tool** — model
> from scratch (blank or a template) and draw/drag-edit real IFC by GUID across architecture · structure ·
> MEP, **generate a permit-ready construction-document set** (plans, sections, elevations, schedules →
> SVG/PDF/DXF, issuable ARCH-D sheets, a 3-part MasterFormat spec manual), **pre-check code** (IBC
> occupancy/egress, jurisdiction-adopted editions, an approvability pre-flight), and **hand over
> field-verified as-built data** (LOD-500 + manufacturer/serial, COBie-ready). Plus a **near-100-module GC
> portal** (RFIs, pay apps, CPM schedule, TRIR) and a **development proforma** — **one model, from land
> acquisition through operations.** Generate a building from a zoning envelope, or model it by hand; then
> coordinate, schedule, underwrite & operate it. Built on **That Open + IfcOpenShell**. **$0 to run.**

> ### Making the most powerful thing in AEC feel like the simplest.
>
> Breadth is the asset; it is also the risk. **47%** of contractors name getting people to *use* new
> technology their single biggest challenge — ahead of cost or integration ([AGC, 2024](docs/internal/archive/design-audit.md)) —
> and **12%** of features carry 80% of daily use across 615 measured subscriptions (Pendo, 2019). So the
> design rule is **defer, never delete**: route each person to the ten things they touch today, keep the
> rest one keystroke away. See the [design audit & interface plan](docs/internal/archive/design-audit.md) and the **R24
> interface ring** in [the roadmap](docs/roadmap.md).

**What it is** — three pillars on one IFC-keyed model, reached through seven rooms — **Deal · Design · Planning · Schedule · Cost · Work · Operate** — that stay in the same place for every role:

- 🧊 **BIM platform** — a genuine **in-browser authoring tool** on That Open Fragments, from a blank model
  to a permit-ready set: draw/edit walls (incl. **sloped-top parapet/shed/gable**), columns, slabs,
  doors/windows, **curtain walls, steel connections, rebar cages and MEP** (with **port-to-port
  connectivity**) by **GUID-stable server-side recipe**, with **drag-to-move edit-in-place**, **model
  undo/redo**, automatic **drawing inference** (auto on-axis/parallel/perpendicular snap), a
  family/type system, groups/arrays, **phasing**, **LOD dialing (100→500)**, a **site content library**
  (logistics/furniture/landscaping, auto-classified), a **procedural-mesh** and an AST-**sandboxed
  ifcopenshell** escape hatch (feature-flagged), **authoring guardrails** that reject broken IFC, and an
  a **CAD command line** (AutoCAD-style `WALL 0,0 5,0 3` / `COLUMN 2,2` with aliases, history and
  spacebar-repeat) alongside an **AI command bar** (type what to build in plain English); **generate the construction-document
  set** — plans/sections/elevations/schedules → **SVG · PDF · DXF**, issuable ARCH-D sheets with titleblocks,
  and a **3-part MasterFormat project manual**; **code intelligence** — IBC code-analysis (G-series) summary,
  **edition-aware** occupancy-load + egress pre-check, jurisdiction-adopted code editions, an
  **approvability pre-flight**, a **detail-rule engine**, and a **decision-readiness (RFI-prevention) audit**;
  plus a **productivity-rate labour estimate**, QA, IDS, BCF, **PDF takeoff** (calibrated measure / area /
  count); **layer &
  align multiple models** with **federated cross-discipline clash**; **raise 2D → BIM** (DXF floor plan → IFC
  walls + spaces) and check the built result with **scan-to-BIM deviation** (as-built point cloud vs the model
  surface, % within tolerance + heatmap); also opens **meshes & point clouds** (OBJ/STL/PLY/glTF ·
  PCD/XYZ/**LAS/LAZ**) and **GIS / topography** (**GeoJSON** vectors · **GeoTIFF** DEM terrain) as
  georeferenced reference overlays, with **QR sharing**
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
- **BIM authoring + coordination** — from-scratch in-browser modeling (blank/template start, Draft
  toolkit, drag-to-move edit-in-place, manage levels, model browser with group-by/search, selection
  sets), clash detection, IDS validation.
- **openBIM data depth (Wave 9)** — **property mapping / normalization** (remap vendor psets onto an
  IDS/employer structure, the transform between validation and export); **IFC5-style property-override
  layers** (non-destructive composition with conflict detection + bake); a **semantic model graph**
  (multi-hop, cited IFC-relationship queries); **computed code pre-check** (occupancy load + egress
  capacity, IBC-cited); **generative fit-out** (auto-furnish spaces); and **site logistics on the 4D
  timeline** (schedule-windowed cranes/laydown/gates).
- **AI over the model** — an MCP server so external agents (Claude Desktop) can drive the project: read
  status/records, run schedule-risk, carbon, permit-readiness, drawing-QA and standards checks, and
  **author the model with GUID-stable recipes** — all through the same gated engines the UI uses, with a
  drop-in Claude skill pack (`docs/mcp-skills/`). Offline-first; nothing fabricated.
- **Construction management** — RFIs, submittals, change orders, pay apps, 4D/5D.
- **Turnover** — COBie, as-built, closeout, certified substantial completion (G704).
- **Operations** — CMMS work orders + preventive maintenance, utility meters → EUI, reserve
  study + capital plan, **facility condition assessment** (UNIFORMAT II elements → **Facility
  Condition Index** + portfolio prioritization, feeding the reserve forecast), CAM reconciliation,
  ESG rollup (GHG Scope 1/2) + post-occupancy evaluation.
- **Climate & water resilience** — flood risk (ASCE 24 / FEMA **Design Flood Elevation** + a
  flood-proof-MEP check flagging equipment installed below it), stormwater sizing (**Rational
  Method** Q = C·i·A peak runoff + detention volume), **weather-sequenced construction**
  (weather-sensitive activities + a site-weather-hazard register + weather-delay days from the daily
  reports), and a **physical climate-risk rating** that rolls up into the ESG scorecard — rainfall and
  flooding as quantifiable parameters across the lifecycle.
- **IFC-native, open, self-hostable** — no per-seat license; the desktop app is free.

## What it does

Highlights, all **built and verified** in this repo unless noted:

- **Web viewer** — Three.js + Fragments, streams large models, runs fully offline (local WASM).
- **Navigation & review** — select→properties, spatial tree, layers, isolate/hide, ghost,
  section planes, measure, color-by-data, set-origin/CRS.
- **Coordination** — model federation; **clash detection** (AABB broad phase + mesh
  boolean narrow phase, exact penetration volume) → BCF clash topics.
- **Issues** — BCF-modeled topics/RFIs/punch/clash, viewpoints, comments, attachments,
  pins; `.bcfzip` import/export (round-trips with any BCF-compatible openBIM tool).
- **QA** — **IDS validation** (ifctester) with failing-element highlighting.
- **4D / 5D** — schedule↔element mapping; quantity takeoff + cost mapping (geometry fallback).
- **Data export** — QTO, COBie, space schedules → XLSX.
- **2D documentation** — dimensioned grid **plans** (grid derived from columns), **sections**,
  **elevations** (N/S/E/W) with level lines, and composed **PDF sheets** with title blocks.
- **Authoring round-trip (in-browser modeling)** — a full toolkit of authoring ops, each a
  server-side `ifcopenshell` recipe → background republish (reconvert + reindex). GUID-stable,
  so pins/RFIs/clashes survive. **Start:** a blank model (levels + ground datum) or a starter
  template (office bay / residential floor / warehouse). **Create:** walls (incl. **sloped-top** —
  parapet-slope / shed / gable), slabs, columns, beams, roofs, rooms/spaces (sketch on the model/grid);
  **parametric doors/windows** (real lining/frame/panel) that void the host wall + fill it. Free-hand
  drawing lands clean lines automatically via **automatic axis inference** (auto on-axis / parallel /
  perpendicular snap within ~6°, no Shift needed). **Fabrication / LOD 350-400 (behind an "Advanced"
  toggle):** **curtain-wall systems** (mullions/transoms + glazing), **structural steel connections** (base
  plates, shear tabs + bolts as `IfcElementAssembly`), **rebar cages** (longitudinal bars + stirrups), **MEP
  fittings** (elbows/tees/transitions with ports + distribution systems) with **port-to-port connectivity**
  (`IfcRelConnectsPorts` + a dangling-element report), a **procedural mesh** (author an element from a raw
  triangle mesh → `IfcTriangulatedFaceSet`), and an AST-**sandboxed `ifcopenshell` escape hatch** (off by
  default, feature-flagged) for geometry the recipes can't express. **Site content:** a **content library**
  places logistics (cranes / hoists / fencing / sanitary units / laydown), furniture and landscaping, each
  auto-classified into the right IFC class + phase (logistics time-phase on the 4D slider) + Uniclass/OmniClass.
  **Edit:** **drag-to-move edit-in-place** (transform gizmo + ghost preview) with full **model undo/redo**
  (every edit is versioned, GUID-stable), plus typed delete / move / rotate / copy / per-element
  Pset edit, **groups & arrays**, and **phasing** (new / existing / demolish / temporary). **Organize:**
  a **power-selection query** (the IfcOpenShell selector DSL — by class, material, pset value) saved as
  reusable selection sets; **LOD dialing** (tag elements 100→500 on a view-keyed representation spine).
  **Levels:** rename + set-elevation. **Browse:** model tree grouped by level / discipline / class / type
  with search. **Drafting aids:** grid + corner snap, a 6-face section box, a storey-levels overlay.
  **Reliability:** **authoring guardrails** (`guards.py::precheck`) reject broken edits (zero-length walls,
  non-finite coordinates, bad dimensions) *before* they touch the model. **AI command bar:** type an
  instruction ("a 5×4 m room at 0,0", "steel column W14×30 at 6,6") — a deterministic keyword baseline
  works with zero setup, and an optional Claude multi-step planner turns one instruction into a validated,
  confirm-before-apply plan (it never invents GUIDs; every step re-validates through the same guardrail).
  Verified live end-to-end (new model → draw → edit-in-place → clash → export). Desktop GUI authoring is
  the optional Blender + Bonsai bridge.
- **Construction-document set (author → issuable sheet)** — generate a permit set straight from the
  authored geometry (deterministic, from extruded-profile footprints — no geometry kernel): **plans**
  (class-styled poché, dimensions, keynote bubbles + legend from the model's spec codes, and **NCS-style
  detail callouts** — a divided circle + leader on every element carrying an attached detail, with a keyed
  DETAILS legend), auto-centred
  **sections** (X-X / Y-Y) and projected **elevations** (N/S/E/W), and computed **door / window / room
  schedules** — each as **SVG**, laid out on an **issuable ARCH-D (36×24″) sheet** with a border +
  titleblock, and exported to **PDF** (via reportlab) and **DXF** (a dependency-free R12 writer for CAD
  interchange). Plus a **3-part MasterFormat project manual** — the model's elements grouped into CSI
  divisions → sections in SectionFormat shape (Part 1 General / Part 2 Products / Part 3 Execution) from
  their work-result classifications + attached detail documents. A **detail-rule engine** (IDS-shaped
  condition → content) auto-attaches keynotes, spec codes and installation details — e.g. a window in an
  exterior wall gets the IBC/ASTM/AAMA flashing detail + MasterFormat/UniFormat codes — and validates as
  author-time QA.
- **Code intelligence (pre-check, cites sections)** — a permit set's **G-series IBC code-analysis
  summary** computed from the model (occupancy classification, construction type, area + story count, the
  computed occupant load + egress, governing allowable-area/height + fire-rating sections); an
  **occupancy-load + egress pre-check** (per-space load, required vs provided egress width, 32-in door +
  two-exits-over-49 checks) whose **occupant-load factors are edition-aware** — a jurisdiction on an older
  IBC cycle (e.g. Business at 100 gross ft²/occ in 2012/2015 vs 150 in 2018+) computes a higher load and
  egress width than the current baseline; a **jurisdiction-adopted-edition catalog** (`codes.py` — the
  I-Code families + their 3-year editions, resolved per US state) so citations name the edition in force
  ("IBC 2021 Table 506.2 …"); an **approvability pre-flight** — a plan-reviewer readiness checklist (egress
  capacity, door clear width, two-exits, occupancy classification on spaces, substantiated rated assemblies)
  scored for permit-readiness; and a **decision-readiness (RFI-prevention) audit** — the proactive inverse
  of the RFI, composing failed code checks, elements missing a required detail/keynote, model-hygiene gaps
  (orphaned / unenclosed / unnamed / duplicate) and open clashes into one **ranked resolve-before-issue
  list** (category + severity + fix), isolating each flagged element in 3D. A pre-check assist that cites
  sections — not a certified review; verify with the AHJ.
- **LOD-500 / turnover (field-verified as-built)** — stamp elements **field-verified as-built**
  (`Massing_AsBuilt`: Status + VerifiedBy/Date/Method/Note provenance) with a **readiness** rollup by
  method (field-measure / laser-scan / total-station / photo / submittal / inspection); stamp
  **field-verified as-built dimensions** (`Massing_AsBuiltDim`: measured value, design value, the
  **variance**, and a within-tolerance flag — measured-vs-design capture, with an out-of-tolerance count);
  stamp **manufacturer/serial** data (`Pset_ManufacturerTypeInformation` + `Pset_ManufacturerOccurrence`)
  that round-trips to COBie and CMMS/asset systems; and a composite **Model Health scorecard** across five
  lenses — integrity, ISO-19650 information, clash coordination, verified-as-built, and **Code &
  permit-readiness** (from the approvability pre-flight).
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
  Reports, …) is a `module.json` → its own auto-created table. **130 modules / 16 sections**,
  no per-module code. Each gets CRUD, role-gated workflow, comments, CSV/PDF, pins, timeline.
- **Two role dimensions** — capability roles (viewer→admin) + party roles
  (GC/Owner/OwnersRep/Consultant/Subcontractor) that gate workflow transitions.
- **Change-order chain** — PCO ▸ NOC ▸ Directive ▸ Proposal ▸ COR ▸ eTicket, linked and
  audit-logged; approved CORs flow into the contract sum.
- **Financials** — AIA **G702/G703** pay apps (+ PDF), **Cost Summary** roll-up, **eTicket
  T&M builder** priced from rate tables, and a **WIP schedule** (percentage-of-completion) whose
  physical progress can be **cross-checked against the model** — installed elements ÷ total by IFC
  GlobalId, flagging cost running ahead of what's actually built.
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

Four constraints hold this together: elements are referenced by **IFC GlobalId** and never by a viewer
id; IFC is **pre-converted to Fragments server-side** and never parsed in the browser at runtime;
**geometry and metadata stay separate**; and the viewer **runs fully offline**.

Full detail — the repo layout, where each kind of work runs, the canonical "spines" to reuse rather than
rebuild, and the tests that hold each claim in place — is in
**[docs/reference/architecture.md](docs/reference/architecture.md)**.

## Install

```bash
git clone https://github.com/ibuilder/massing.git && cd massing
cp .env.example .env            # set secrets + AEC_RBAC=1 for anything but local dev
docker compose --profile full up --build      # web → http://localhost:8080  (api → :8000)

# optional: fill a demo project across all relation chains
docker compose --profile full --profile seed run --rm seed
```

The web container reverse-proxies `/api` to the API (same-origin, no CORS), serves the viewer with the
cross-origin isolation web-ifc needs, and persists Postgres/MinIO/IFC volumes. `.env.example` documents
every knob.

Prefer not to run a stack? Install the signed **desktop app** (single-project, auto-updating, free) from
[the latest release](https://github.com/ibuilder/massing/releases/latest).

Building from source needs **Node 24 and Python 3.12** — Node 18 does not build the web app. The dev
setup, the first-project walkthrough and the test commands are all in
**[docs/getting-started.md](docs/getting-started.md)**.

**Running it in production?** [Deployment](docs/deploy.md) → [go-live checklist](docs/PRODUCTION_CHECKLIST.md)
→ [operator runbook](docs/operations.md).

## Documentation

**[📚 docs/](docs/README.md)** is the index. The paths people usually want:

| | |
| --- | --- |
| **Install and first project** | [getting-started.md](docs/getting-started.md) |
| **Learn to use it** | [User guide](docs/user-guide/) — [the seven rooms](docs/user-guide/rooms.md), [authoring](docs/user-guide/authoring.md), [drawings](docs/user-guide/drawings.md), [records](docs/user-guide/modules.md), [files](docs/user-guide/files.md) |
| **See it demoed** | [walkthrough.md](docs/walkthrough.md) |
| **Something is broken** | [troubleshooting.md](docs/user-guide/troubleshooting.md) |
| **Call the API** | [reference/api.md](docs/reference/api.md), or `/docs` on a running instance |
| **How it is built** | [reference/architecture.md](docs/reference/architecture.md) |
| **Add a record type** | [authoring-modules.md](docs/authoring-modules.md) — no code required |
| **What is planned** | [roadmap.md](docs/roadmap.md) · [release history](docs/history/platform-history.md) · [CHANGELOG](CHANGELOG.md) |

## API surface

66 routers. The **live, authoritative reference is `/docs`** on any running instance — FastAPI generates
it from the code, so it cannot go stale. For the grouped map of what exists, see
**[docs/reference/api.md](docs/reference/api.md)**.

A taste of the shape:

```
POST   /projects/{id}/edit | /publish          authoring round-trip (GUID-stable recipes)
POST   /projects/{id}/generate/massing         zoning → IFC massing + acquisition proforma
GET    /projects/{id}/drawings/sheet.pdf       issuable ARCH-D sheet
POST   /projects/{id}/cost/estimate → /sov     price the model, then build the SOV from that estimate
GET    /projects/{id}/codecheck/occupancy      edition-aware occupancy + egress, IBC-cited
GET/POST /projects/{id}/modules/{key}          any of 133 registers, config-driven CRUD
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
