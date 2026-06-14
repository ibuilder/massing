# Web viewer (apps/web)

Vite + TS in-browser BIM viewer. Three.js + That Open Engine (Fragments). Runs **offline** —
web-ifc WASM and the Fragments worker are served from local assets, never a CDN.

## Verified compatible versions (Jun 2026)

Pinned as an installed, typechecked, build-passing set. The #1 risk in this project is the
`@thatopen/components` ↔ `@thatopen/fragments` ↔ `three` coupling — change one, re-verify all.

| Package | Version | Notes |
|---|---|---|
| @thatopen/components | 3.4.6 | peers: fragments ~3.4, three ≥0.182, web-ifc ≥0.0.77, camera-controls ≥3.1.2 |
| @thatopen/fragments | 3.4.5 | |
| @thatopen/components-front | 3.4.3 | front-end tools (Phase 3+) |
| @thatopen/ui | 3.4.3 | toolbar (Phase 3+) |
| three | 0.184.0 | |
| @types/three | 0.184.1 | |
| camera-controls | 3.1.2 | declares engine node ≥22 (warning only; runs in browser) |
| web-ifc | 0.0.77 | |
| vite | 6.4.3 (dev) | pinned to v6 — v7/v8 need node ≥20.19; this machine has 20.3.1 |
| typescript | 5.9.3 (dev) | |

If you bump node to ≥20.19 / 22 LTS, vite 7/8 become available.

## Offline assets

- `scripts/copy-wasm.mjs` copies `web-ifc.wasm` + `web-ifc-mt.wasm` into `public/wasm/`.
  Runs automatically via `predev` / `prebuild`. The IfcImporter is configured with
  `wasm = { absolute: true, path: "/wasm/" }`.
- The Fragments worker is imported locally as `@thatopen/fragments/worker?url` — **not** via
  `FragmentsManager.getWorker()`, which fetches from unpkg and would break offline use.

## Run

```bash
npm run dev      # http://localhost:5173  (copies wasm first)
npm run build    # tsc --noEmit + vite build
npm run typecheck
```

## M0 smoke test (Phase 0/1)

1. `npm run dev`, open http://localhost:5173.
2. Click **Open IFC**, pick a small `.ifc` (e.g. a buildingSMART sample).
3. The model converts in-browser to Fragments and renders.
4. Click an element → the **Properties** panel shows its attributes (incl. GUID) + Psets.

> Production note: in-browser IFC conversion is for the smoke test / small files only.
> Real models are pre-converted to `.frag` on the server (Phase 1) and loaded via **Open .frag**.

## Structure

```
src/
  viewer/   world.ts (scene+camera+renderer), loader.ts (FragmentsManager + IfcImporter)
  tools/    measure, section, isolate, layers, origin  (Phase 3)
  pins/     markup + pin overlay                        (Phase 4)
  tree/     spatial + classification tree               (Phase 3)
  api/      typed backend client                        (Phase 4)
```
