# AEC BIM Platform + GC Portal

[![CI](https://github.com/ibuilder/ModelMaker/actions/workflows/ci.yml/badge.svg)](https://github.com/ibuilder/ModelMaker/actions/workflows/ci.yml)

A standalone, open, web-based **BIM viewer + data + coordination platform** for AEC firms,
built on the IfcOpenShell / That Open (Fragments) ecosystem, **plus a general-contracting
portal** (RFIs, change-order chain, pay apps, dashboards) whose records pin to the 3D model.
**IFC is the source of truth.** The browser viewer streams a fast tiled format; a Python
service does extraction, QA, clash, and 2D documentation; a FastAPI backend handles BCF
issues, the GC-portal module engine, and authoring on `ifcopenshell.api` (the engine Bonsai
drives) — no proprietary format, no per-seat license.

> Status: a working end-to-end vertical slice, verified against real models (the That Open
> "school" structural IFC + a 52 MB architectural Revit export). Two halves: the **BIM
> platform** (below) and the **[General Contracting Portal](docs/gc-portal.md)**.

## What it does (vs. Bonsai / Revit / Navisworks)

Full mapping in [docs/capability-matrix.md](docs/capability-matrix.md). Highlights, all **built
and verified** in this repo unless noted:

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
- **Authoring round-trip** — edit IFC via recipes (`set_pset`, `batch_tag`, `place_type`)
  → republish (reconvert + reindex). GUID-stable, so pins/RFIs/clashes survive. Desktop
  GUI authoring is the Blender + Bonsai bridge (driven via Bonsai-MCP).

## General Contracting Portal

A construction-management portal on top of the viewer — full writeup in
[docs/gc-portal.md](docs/gc-portal.md). Highlights:

- **Module engine** — every process (RFIs, Submittals, PCO/Change-Order chain, Daily
  Reports, …) is a `module.json` → its own auto-created table. **68 modules / 12 sections**,
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

## Gallery

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

> Live 3D-viewer UI captures (model + panels) can be added to `docs/img/` — the viewer is a
> WebGL app, so these are best grabbed from the running app (`apps/web`).

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
services/api/modules/  68 module.json definitions (GC portal — one table each)
services/data/       IfcOpenShell: index, QTO, COBie, spaces, schedule, clash, IDS, drawings, edit
packages/            shared types
families/            IFC type libraries (versioned)
docs/                status, capability matrix, gc-portal, deploy, images
```

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
POST   /projects/{id}/edit | /publish         authoring round-trip

# GC portal (full list in docs/gc-portal.md)
GET    /modules                               module catalog
GET/POST /projects/{id}/modules/{key}[/{rid}] config-driven CRUD (+ /transition /link /comments /pdf /export.csv)
GET    /projects/{id}/module-pins             anchored records → viewer overlay
GET    /projects/{id}/cost/{g703,g702,summary} financials (+ g702.pdf, POST /cost/tm)
GET    /projects/{id}/schedule/{gantt,lob}.svg  Gantt + Line-of-Balance
GET    /projects/{id}/dashboard               role-tailored dashboard
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
