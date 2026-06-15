# AEC BIM Platform

A standalone, open, web-based **BIM viewer + data + coordination platform** for AEC firms,
built on the IfcOpenShell / That Open (Fragments) ecosystem. **IFC is the source of truth.**
The browser viewer streams a fast tiled format; a Python service does extraction, QA, clash,
and 2D documentation; a FastAPI backend handles BCF issues; and authoring runs on
`ifcopenshell.api` (the engine Bonsai drives) — no proprietary format, no per-seat license.

> Status: a working end-to-end vertical slice, verified against a real structural model
> (the buildingSMART/That Open "school" IFC, 8.6 MB, IFC4). See [docs/status.md](docs/status.md).

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

## Gallery

Generated directly from the IFC by the data service:

| Dimensioned grid plan | Composed sheet (A3) | North elevation |
|---|---|---|
| ![plan](docs/img/plan_grid.png) | ![sheet](docs/img/sheet.png) | ![elevation](docs/img/elevation_north.png) |

The dimensioned plan derives the structural grid from column positions (no `IfcGrid` needed),
adds numbered/lettered bubbles and grid-spacing dimensions; the sheet composes per-storey
plans + a section under a title block (also exported as PDF).

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
services/api/        FastAPI: BCF, properties, exports, clash/validate, drawings, edit/publish
services/data/       IfcOpenShell: index, QTO, COBie, spaces, schedule, clash, IDS, drawings, edit
packages/            shared types
families/            IFC type libraries (versioned)
docs/                status, capability matrix, phase notes, deploy, images
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
