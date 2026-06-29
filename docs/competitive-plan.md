# Plan to compete (2026-06)

How Massing wins against the field, and the release motion behind it. Pairs with the
competitor landscape + gaps in [roadmap.md](roadmap.md).

## Positioning — one platform, open, IFC-native, no per-seat
Most competitors own one slice: Procore/ACC (GC PM), Mastt/PMWeb (owner controls), Buildertrend
(residential), Fieldwire (field/punch), Planera/P6 (CPM), Sage/STACK (precon), Viewpoint/CMiC
(ERP). We span **BIM viewer + 71-tool GC portal + development proforma in one app**, keyed off the
**IFC GlobalId** so geometry, issues, records, cost, and schedule stay in sync — and it's **open,
self-hostable, and free to run on one machine**. That combination is the wedge.

### The differentiators to lead with
1. **Model → money & schedule.** The IFC drives the build *and* the deal: takeoff → priced
   **estimate** → **budget**; areas → **proforma** hard cost/rent; activities → **CPM** float &
   critical path (a gap even Procore has). Competitors silo these.
2. **Free, offline, single-project `.exe`** (Bluebeam-style) — no Docker, no login, no per-seat.
   Lowers adoption to zero-friction; the paid tier is the cloud, not the app.
3. **Open + IFC-native + BCF round-trip** — no lock-in; coexists with ACC/Procore/Solibri via the
   Connections framework (Procore/ACC two-way, QuickBooks/Sage/Viewpoint ERP) instead of replacing.
4. **Owner / dev-manager angle** — risk register, construction **program portfolio** with
   cost-overrun flagging, and the proforma make us credible to owners/PM-consultants (Mastt/INGENIOUS
   territory) *and* the GC — one tool for both sides of the table.

## Target segments (initial wedge → expand)
- **Owner's-rep / development manager** — needs portfolio cost/risk + proforma + light GC oversight.
  We're uniquely whole-lifecycle here. **Primary.**
- **Small–mid GC** priced out of Procore's seat model — the free `.exe` + self-host is the hook.
- **Residential builder** — selections + client approval + AIA billing (Buildertrend overlap).

## Where we still trail (keep closing — from the roadmap)
- Deep **mobile field** app (Fieldwire/PlanGrid) — Capacitor wrapper is the next platform target.
- **Enterprise estimating/takeoff** depth (Sage/STACK) — we have conceptual model takeoff; assembly
  takeoff + rate libraries next.
- **ITB distribution + lead intelligence** (BuildingConnected/Dodge) — we have bid leveling; outbound
  invitations next.
- **Branded/signable PDFs** and **changed-geometry diff** — polish.

## Go-to-market & pricing
- **Free forever:** the local single-project `.exe` (full GC + proforma + viewer, offline).
- **Pro (paid cloud):** multi-project, hosted Postgres/MinIO, SSO, connectors (Procore/ACC/ERP),
  team RBAC, program portfolio, auto-update channel. Per-project or per-org, not per-seat.
- **Open core:** the platform stays open; the managed cloud + premium connectors are the revenue.
- **Distribution:** GitHub Releases (signed installers + auto-update) + the Pages landing page;
  the demo runs in-browser to remove the "book a demo" wall every competitor hides behind.

## Release motion (so a new `.exe` ships on demand)
- **Versioned, signed, auto-updating.** Bump `apps/web/package.json` + `src-tauri/tauri.conf.json`,
  tag `vX.Y.Z` → the **Desktop release** workflow builds signed Win/macOS/Linux installers + the
  in-app updater `latest.json`; installed apps self-update on launch (proven with v0.1.2).
- **Cadence:** cut a release whenever a user-visible batch lands (this session added CPM, estimating,
  ERP connectors, risk/selections/bid-leveling, TRIR, templates, version history → **cut v0.1.3**).
- **Quality gate:** `services/api/run_tests.py` (Python suites) + web tsc/vitest/build must be green
  before tagging; the in-app **update banner** also notifies users who can't auto-update.

## OpenConstructionERP (datadrivenconstruction/OpenConstructionERP) — gap analysis (2026-06)
Open-source construction ERP (AGPL). We already match most of it: estimating/QTO from IFC/RVT/DWG,
4D/5D + EVM (SPI/CPI/EAC) + S-curve, bid leveling, **federated cross-discipline clash + BCF**,
punchlist, daily diary/HSE, property-development lifecycle, AI chat, self-hosted/offline.

**Added in response to the comparison:**
- **GIS / topography** — GeoJSON + GeoTIFF DEM as georeferenced overlays (their "Geo Hub", but in
  our existing viewer rather than a separate Cesium globe).
- **PDF takeoff & markup** — calibrated measure / area / count + annotations + CSV.
- **Regional classification standards + GAEB X83 export** — DIN 276 / NRM 1 / MasterFormat coding.
- **AI estimate (text → BOQ)** — describe scope → priced line items (reuses our Anthropic seam).

**Deliberately NOT cloned (disproportionate / low ROI for us):**
- 55,000-item CWICR cost database across 9 languages / 11 price regions — huge curated data asset,
  not code; we price via editable unit rates + (now) AI drafting.
- OCR/YOLO photo-&-PDF auto-takeoff (PaddleOCR/YOLOv11) — heavy ML pipeline + models.
- Accommodation / worker-camp module — niche.
- A separate Cesium 3D globe — we georeference in the main viewer instead.

## Argyle + Flinker scan (v0.1.88)

A scan of [Argyle](https://www.argyle.build/) (AR field verification for $100M+ industrial) and
[Flinker](https://flinker.app/) (self-hosted OpenBIM inside Microsoft 365). Massing already
overlaps Flinker heavily (self-hosted, IFC/IDS/BCF viewer, CDE-like store, dashboards, AI assists);
Argyle is a category we lacked (field verification). Built to our open, $0, no-AR-hardware identity:

- **Ask the model (A)** — Flinker "IFC Copilot" parity: `POST /ask` answers plain-English questions
  grounded in the property index; degrades to the data snapshot without an AI key.
- **Field verification + install coverage (B)** — Argyle's core value without AR: mark elements
  installed/verified/deviation vs design (photo-anchored), a coverage % dashboard + deviation log.
- **Embeddable viewer + outbound webhooks (D)** — Flinker SDK / Power Automate parity: `?embed=1`
  chrome-less viewer for `<iframe>`/Teams; module-transition webhooks for external automation.

**Deliberately skipped:** AR-headset overlay (Magic Leap/iPad — hardware-heavy; a phased WebXR phone
overlay is a future option) and MS-365-native packaging (Power BI visual / SharePoint tabs — cuts
against the framework-agnostic, self-hosted posture; the `?embed=1` iframe covers the Teams-tab case).

## Competitor + library scan (v0.1.89)

A web/GitHub scan vs OpenConstructionERP (AGPL, 111 modules), Procore/Autodesk ACC, Fieldwire/
Buildertrend, and RE asset-mgmt/syndication tools (Yardi, Agora, SyndicationPro, InvestNext).
Finding: Massing is broader than most; the genuine gaps were adjacent *phases* and depth, now built:
- **Operate/hold (G1)** — `lease` module + rent roll (occupancy/WALT/expirations → appraisal income).
- **Capital/investors (G2)** — `investor` cap table + pro-rata capital calls/distributions; data-room = document module.
- **Certified payroll (G3)** — WH-347 from timesheets × labor rates.
- **Drawing-set register (G5)** — controlled current vs superseded revisions from `drawing` records.
- **Project assistant (G4)** — "ask" extended from the BIM index to the whole project.
- **ITB tracking (G6)** — bid-package invited/responded/bonded coverage + invite endpoint.

**Reconfirmed right-to-skip:** embedded 55k-item cost DB and OCR/YOLO photo takeoff (OpenConstructionERP),
AR-headset overlay, MS-365-native packaging, Cesium globe, worker-camp module.
