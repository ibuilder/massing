# AEC BIM Platform

A standalone, web-based BIM viewer + data platform for AEC firms, built on the open
IfcOpenShell / Bonsai ecosystem, with an optional Autodesk bridge for `.rvt` files.

**IFC is the source of truth.** The browser viewer (Three.js + Fragments) is a different
stack from the desktop editor (Blender + Bonsai); they are connected by IFC plus a
conversion step that tiles IFC into a fast web format.

## Layout

```
apps/
  web/             Vite + TS web viewer (Three.js + @thatopen/*)
  editor-bridge/   Bonsai-MCP config + helper scripts (desktop editor)
services/
  api/             FastAPI: pins, rfis, punchlist, drawings, bcf, exports
  converter/       IFC→.frag tiling; RVT→IFC via APS; origin rebasing
  data/            IfcOpenShell: QTO, COBie, 4D/5D, space performance
packages/
  shared-types/    OpenAPI-generated TS types shared by web + api
families/          IFC type libraries (versioned)
```

## Build order (phases)

0. Prerequisites & smoke tests
1. Conversion service (IFC→Fragments; optional RVT→IFC via APS)
2. Large-model handling (streaming, culling, per-discipline tiles)
3. Web viewer & Autodesk-style toolset (nav, tree, isolate, section, measure, origin)
4. Backend API (pins/RFIs/punchlist/drawings, BCF round-trip)
5. Data extraction & export (QTO/5D, 4D, COBie, space schedules)
6. Editing with family libraries (Blender + Bonsai + Bonsai-MCP)
7. Hardening & deployment

## Quick start (dev)

```bash
# web viewer
cd apps/web && npm install && npm run dev

# services (Python) — prefer a 3.11+ interpreter
cd services/api && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
```

See `CLAUDE.md` for the project rules and non-negotiables.
