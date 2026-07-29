# Architecture

Four services on one IFC-keyed model. The boundaries are deliberate; the reasoning for the main one is
in [client-vs-server.md](../client-vs-server.md).

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

## The four non-negotiables

These are constraints, not preferences. Each exists because the alternative failed:

1. **Reference elements by IFC GlobalId, never by transient viewer id.** The only durable identity.
2. **Pre-convert IFC to Fragments on the server; never parse full IFC in the browser at runtime.** This
   is what lets a large model open on a laptop.
3. **Keep geometry and metadata separate** — geometry streams as `.frag`, data comes from the API.
4. **The viewer must run fully offline** — local WASM, self-hosted tiles, no CDN.

Two more that shape the data model:

- **Pins, RFIs and punchlist follow the BCF model**, so they round-trip with other openBIM tools rather
  than being trapped here.
- **Georeferencing preserves real coordinates for export while rendering near the scene origin.** Both
  are required, so both are handled rather than compromised.

## Where work runs

| Job | Runs in | Why |
| --- | --- | --- |
| Render, select, snap, draft | Browser | Latency. Interaction must not round-trip. |
| Write IFC | Python (ifcopenshell) | Correctness. One implementation, server-side, by named recipe. |
| Geometry conversion | Node (`services/converter`) | web-ifc is the same engine the browser uses. |
| Analysis (clash, IDS, QTO, drawings) | Python (`services/data`) | Needs the full model and real geometry kernels. |
| Persistence, auth, records | FastAPI (`services/api`) | One gate in front of everything. |

Massing is a **thin, offline-capable client over a Python authoring/analysis service** — not a fat
in-browser CAD kernel. That is the single most consequential decision in the codebase.

## Stack

- **Web** — Vite + TypeScript, `web-ifc`, `@thatopen/{fragments,components,components-front,ui}`, three.js.
  The `@thatopen/components` and `@thatopen/fragments` versions are **coupled**: pin a compatible pair.
- **Services** — Python, ifcopenshell, FastAPI, SQLAlchemy/Postgres, MinIO.
- **Desktop** — Tauri. **Mobile** — Capacitor ([plan](../mobile.md); no native CI build yet).
- **Optional editor** — Blender + Bonsai, driven over Bonsai-MCP. An advanced/interop path, not required.
  `execute_blender_code` runs arbitrary Python: gate it, save first, chunk large operations.
- **Optional** — Autodesk APS Model Derivative for RVT→IFC, behind a feature flag with a cost warning.

## Repository layout

```
apps/web/              Vite + TS app — viewer, authoring, shell (297 TS files, 77 vitest files)
apps/editor-bridge/    Bonsai-MCP config + authoring recipes (desktop path)
apps/web/src-tauri/    Desktop packaging
services/converter/    IFC→.frag (Node) + optional RVT→IFC via APS (paid, flagged)
services/api/          FastAPI — 66 routers: BCF, properties, exports, clash/validate,
                         drawings, edit/publish, GC portal, cost, schedule, dashboard
services/api/modules/  133 module.json definitions — one register each
services/data/         IfcOpenShell — index, QTO, COBie, spaces, schedule, clash, IDS,
                         drawings, edit, massing (zoning→IFC), families
packages/shared-types/ Types shared between web and services
families/              IFC type libraries — an empty drop-in point for curated content
samples/               Sample IFC models and .mass project containers
docs/                  Documentation + the GitHub Pages site (see docs/README.md)
plugins/               Plugin drop-in
integrations/          pyRevit and other external integrations
```

## Spines — reuse these, do not rebuild them

Several concerns have exactly one canonical implementation. Adding a second is how this codebase has
produced its worst drift:

| Concern | The one implementation |
| --- | --- |
| Element selection / scoping | `query_dsl.py` — the selector DSL. Reuse `select()`. |
| Room allocation | `rooms.py` — one `section→room` table. `/rooms` derives from it. |
| Module definition schema | `module_schema.py` — single source of truth for `module.json`. |
| Discipline classification | `classification.py`. `aec_api` may import `aec_data`, never the reverse. |
| Document control | `docmanager.py` sidecar index — *not* the module engine. |

## Build order

Phase 0 smoke tests → 1 conversion → 2 large-model → 3 viewer/tools → 4 API/BCF → 5 data export →
6 editor/families → 7 deploy.

## Verification, not documentation

Long-lived projects drift, and prose cannot fail. The countermeasure in this repo is **checks that
fail** rather than rules that are written down:

| Check | What it holds in place |
| --- | --- |
| `test_reachable.py` | Is a feature actually wired to a route? |
| `ties.test.ts` | Do the aliases agree? |
| `test_no_competitors.py` | Documentation policy. |
| `check_file_sizes.py` | Module size ceiling. |
| `parity.test.ts` | The room rail reaches every destination the catalog lists. |
| `spine.test.ts` | The client room list cannot drift from the server's. |
| `test_module_rooms.py` | Every module has a room; none is filed by guesswork. |
| `docsCurrent.test.ts` | The docs describe the app that exists. |
| `docsPublished.test.ts` | Internal notes stay off the published site. |

If a rule matters, it is a test. Anything held only as prose — including in this file — will drift.

## Related

- [client-vs-server.md](../client-vs-server.md) — the browser/Python boundary in detail.
- [api.md](api.md) — the endpoint surface.
- [engineering/](../engineering/) — backend, web and numeric-precision standards.
- [adr/](../adr/) — decision records.
- [deploy.md](../deploy.md) — how it is actually run.
