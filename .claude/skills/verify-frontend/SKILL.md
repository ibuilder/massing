---
name: verify-frontend
description: How to verify Massing web/viewer UI changes given that the dev-preview geometry loader stalls. Invoke when you changed apps/web and need to prove it works. Covers typecheck/lint/vitest/build, the tools-panel force-build technique, and honest flagging of flows you couldn't exercise.
---

# Verify a Massing frontend change

The dev-preview geometry loader **stalls at "preparing geometry"** for all model sizes, which blocks `loadProjectModel` and therefore `buildPanels` (the `panel-tree` model browser). But `buildToolsPanel` (the rail tools) can be forced. Verify what you can; flag what you can't.

## Always
```
cd apps/web && export PATH="/c/Program Files/nodejs:$PATH"
npm run typecheck && npm run lint      # eslint pinned to 9.39.5; Node 20 (Node 18 breaks build)
npx vitest run <path/if/covered>
npm run build                          # strongest compile check; ~1 min
```

## Force the tools rail to build (verifies rail UI live)
The preview server is on :5173. In the running preview (via the browser tools), navigate to a project with a source IFC, then:
```js
window.dispatchEvent(new CustomEvent('aec:persona', { detail: 'all' }));  // forces buildToolsPanel + buildClashPanel
// then read #panel-tools — the tool-group sections, buttons, inputs all render even though geometry stalled
```
This verifies: new rail tools/buttons/inputs, the ribbon tabs, the Library palette, the node-canvas launcher, the KEYS shortcut layer (dispatch KeyboardEvents), the Ask/analytical boxes. Exercise handlers by `.click()`ing buttons and reading the result-overlay / DOM.

## What you CAN'T verify live (flag it honestly)
- `panel-tree` UI (the Project-Browser spine) — `buildPanels` never runs behind the stall. Verify its DOM-construction logic by reproducing it in the console instead, and say so.
- End-to-end calls to NEW API routes against the dev API on **:8093** — that server is often a **stale process** predating your new routes → 404 there even though the client hits the right URL. Confirm via `read_network_requests` that the URL/payload is correct; the backend itself is covered by CI. (Restarting :8093 is the user's call.)
- Anything geometry-coupled (placing an element, section cuts, camera).

## Report
State exactly what was verified live vs. by typecheck/build vs. not exercised. Never claim an interactive viewer flow "verified" if the stall prevented it.

See memory: `tools-panel-verify-technique`, `web-build-needs-node-20`, `web-eslint-node-pin`, `dev-api-port`.
