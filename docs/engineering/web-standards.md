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

- **Node 24 from Program Files locally** (`export PATH="/c/Program Files/nodejs:$PATH"` — the PATH
  Node 18 breaks the build); CI runs Node 24. Both manifests declare `"engines": {"node": ">=24"}`.
- Gate per release: `npm run typecheck` + `npm run lint` (eslint 10.8.0 — the 9.x pin was lifted once
  the local Node reached 24; `@eslint/js` is a *different* package and still on 9.x) + `npx vitest
  run` + `npm run build`. `lint:fast` (oxlint) is an additive pre-lint in CI.
  <!-- The versions in these two bullets are asserted against the manifests by
       apps/web/src/shell/toolchainDocs.test.ts. Both were wrong for weeks — an eslint major and a
       Node major behind — and nothing failed, because nothing reads prose. Change a manifest and
       this prose must follow. This note deliberately does NOT quote the old values: the gate cannot
       tell a historical example from a live claim, and quoting them here failed the gate on the very
       commit that added it. Same shape as the backtick rule in CLAUDE.md — an illustration written
       in the citation's own syntax IS a citation. -->
- Test counts are deliberately **not** quoted here. This bullet claimed "128 tests" long after the
  suite passed a thousand; an unattached number in prose is a claim nothing checks.
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
