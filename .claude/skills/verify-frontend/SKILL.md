---
name: verify-frontend
description: How to verify Massing web/viewer UI changes given that the dev-preview geometry loader stalls. Invoke when you changed apps/web and need to prove it works. Covers typecheck/lint/vitest/build, the tools-panel force-build technique, and honest flagging of flows you couldn't exercise.
---

# Verify a Massing frontend change

> Standing directions for this repo: [docs/roadmap-directions.md](../../../docs/roadmap-directions.md). Read those first.

**The "preview stall" was diagnosed and FIXED in v0.3.703 — it was never the geometry loader.** Five
SSE endpoints polled the database inside `async def gen()`, blocking the event loop for every other
client; two open tabs left the server wedged and *every* request timed out, including the app's boot
`api.health()`. That left `projectId` unset, so the portal showed "No project open" while a model sat
rendered on screen. Fixed with `run_in_threadpool`; measured >8s timeouts → ~20 ms. **Full live
verification now works** — start both servers and drive the real app.

If the app ever looks stalled again, check the SERVER first (`curl /health` with a stream open), not
the geometry.

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
- Nothing, if both servers are current. **Start them yourself**: `.claude/launch.json` has `api`
  (:8093) and `web` (:5173) configs — use `preview_start` with `{name: "api"}` / `{name: "web"}`. A
  previous note here said a stale :8093 process was "the user's call"; there was usually **no process
  at all**, and the config to start one has always been in the repo. Check before assuming.
- Anything geometry-coupled (placing an element, section cuts, camera).

## Report
State exactly what was verified live vs. by typecheck/build vs. not exercised. Never claim an interactive viewer flow "verified" if the stall prevented it.

See memory: `tools-panel-verify-technique`, `web-build-needs-node-20`, `web-eslint-node-pin`, `dev-api-port`.
