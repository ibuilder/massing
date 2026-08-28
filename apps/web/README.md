# Web viewer (apps/web)

Vite + TS in-browser BIM viewer. Three.js + That Open Engine (Fragments). Runs **offline** —
web-ifc WASM and the Fragments worker are served from local assets, never a CDN.

## Verified compatible versions (checked 2026-08-25 against `package.json`)

Pinned as an installed, typechecked, build-passing set. The #1 risk in this project is the
`@thatopen/components` ↔ `@thatopen/fragments` ↔ `three` coupling — change one, re-verify all.

**Six of the ten rows below were wrong until 2026-08-25**, and the way they were wrong is worth more
than the corrected numbers. The table was last touched at v0.3.1048, in a commit about colouring
plans by discipline — so it was *edited* while stale rather than left alone. Its `vite` row read
`6.4.3 (dev) — pinned to v6 — v7/v8 need node ≥20.19; this machine has 20.3.1`, which is a version,
a policy and a justification, and all three were false: the repo ships **vite 8.2.2**, requires
**node ≥24**, and CI pins 24. **A stale row that carries its own reasoning is worse than a stale
number**, because the reasoning is what stops the next reader from checking.

Regenerate these from `package.json` rather than editing them by hand — that is where the build
reads them from, and it is the only copy that cannot disagree with what installs.

| Package | Version | Notes |
|---|---|---|
| @thatopen/components | 3.4.8 | peers: fragments ~3.4, three ≥0.182, web-ifc ≥0.0.77, camera-controls ≥3.1.2 |
| @thatopen/fragments | 3.4.7 | |
| @thatopen/components-front | 3.4.4 | front-end tools |
| @thatopen/ui | 3.4.10 | toolbar |
| three | 0.185.1 | |
| @types/three | 0.185.4 | |
| camera-controls | 3.1.2 | declares engine node ≥22 (warning only; runs in browser) |
| web-ifc | 0.0.77 | |
| vite | 8.2.2 (dev) | v8 — Rolldown + Oxc underneath; needs node ≥22.12, and the repo requires ≥24 |
| typescript | 5.9.3 (dev) | |

**Node ≥24** is the supported baseline: both manifests declare `"engines": {"node": ">=24"}` and
every workflow that sets a version pins 24.

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
