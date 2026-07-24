# Web engineering standards (Vite / TypeScript)

*R19 ENG-STD (2026-07-24). Codified from shipped practice in `apps/web`. Companion:
[backend-standards.md](backend-standards.md).*

## Architecture

- **API access only through `api/client.ts`** (typed methods; DTO types in `api/types.ts`). No
  fetch calls scattered in panels. New endpoints get a client method + a type in the same release
  as the backend route.
- **Panels compose through the `PanelContext` seam** (`portal.ts` → `panels/*.ts`); the viewer
  composes through `ViewerContext` + `install*` modules. New UI goes in a leaf module, not the
  god-files (REL-4 keeps shrinking them).
- **Geometry/metadata split is sacred:** geometry streams as Fragments; data comes from the API;
  the browser never parses IFC. Elements are addressed by GUID.
- Reusable UI primitives live in `ui/` (`charts.ts`, `result.ts`, chips); don't fork a second
  implementation of an existing primitive.

## Rendering & safety

- **`esc()` every file/server/model-derived free-text** interpolated into `innerHTML` (from
  `ui/charts`); viewer code uses `escapeHtml`. Numbers, `.toFixed`, and server-constant labels are
  exempt. CodeQL catches some sinks; the discipline catches the rest.
- Never `innerHTML +=` on a container with live listeners (it destroys them) — build nodes or
  re-render the container.
- Modal/panel tools with timers or visibility state take an `onClose` (the `showResult` pattern) —
  closing stops timers and restores state.
- Large lists are server-bounded (`truncated` flags); the DOM row cap is ~1000.

## Tooling & gates

- **Node 20 from Program Files locally** (`export PATH="/c/Program Files/nodejs:$PATH"` — the PATH
  Node 18 breaks the build); CI runs Node 22.
- Gate per release: `npm run typecheck` + `npm run lint` (eslint pinned 9.39.5 until the local Node
  bump) + `npx vitest run` (128 tests) + `npm run build`. `lint:fast` (oxlint) is an additive
  pre-lint in CI.
- Headless logic that can be unit-tested is extracted and vitest-covered (the `WalkController`
  pattern); DOM-coupled behavior is verified live where the preview allows, honestly flagged where
  the geometry stall prevents it (see the `verify-frontend` skill).
- Bundle budget: CI reads the eager shell from `dist/index.html` (lazy chunks don't count).
- Single-source version: `apps/web/package.json`; the desktop shell reads `tauri.conf.json` —
  bump both together.

## UX conventions

- Workspaces/personas filter destinations (`wsFilter`); new panels register a stage destination.
- Status/delta chips, KPI headers, and resolve-action buttons reuse the shared components
  (`resolve_hint.py` descriptors → `resolveActionButtons`); insights are template strings, never an
  LLM call.
- Every user-facing surface must degrade offline: no CDN fonts/scripts; WASM and tiles self-hosted.
