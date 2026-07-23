# Build status — verified vs. pending

Snapshot of what's been built and how far each piece is verified on this machine
(node 20.3.1, python 3.10.6, Windows). "Verified" = ran successfully against the real
sample model (`samples/school_str.ifc`, the That Open structural school, 8.6 MB, IFC4).

**Point-in-time snapshot (v0.3.86, June 2026) — long superseded (the build has since passed v0.3.594; see [the changelog](../CHANGELOG.md) and [status.html](status.html) for current state).** The M0–M6 milestones below are the foundational viewer/portal/deploy
spine and remain accurate. Everything shipped on top of them since — the full lifecycle from
acquisition through operations (due diligence, ISO 19650 openBIM standards, the **Discipline Spine**
threading model → discipline sheets → specs → bid → budget, lean **pull-planning** with a real-time
board, **Facility Condition** / FCI, **climate & water resilience**, CMMS/reserves/ESG, and a Python
code-standards lint lock-in) — is catalogued release-by-release in [`../CHANGELOG.md`](../CHANGELOG.md)
and sequenced in [`roadmap.md`](roadmap.md). Backend suite: **306 test scripts, all green** (run via `run_tests.py`; count grows each release).

## Milestones
| ID | Goal | Status |
|---|---|---|
| **M0** | Load IFC → `.frag` → render → click → properties | ✅ **verified in browser** — model renders; raycast hit IFCSLAB localId 76489 / GUID 2UD3D7uxP8kecbbBCRtzEl with full attributes |
| **M1** | Large federated model: streaming + layers by discipline/storey | ✅ code complete (Fragments streaming + LayerManager); strategy in `docs/phase2-large-models.md` |
| **M2** | Full toolset: nav, tree, isolate/ghost, section, measure, set-origin | ✅ modules build + typecheck; **color-by-data verified in browser** (307 slabs highlighted) |
| **M3** | Pin an RFI, restore viewpoint, export `.bcfzip` | ✅ **verified** end-to-end (API smoke test) |
| **M4** | Export QTO/estimate, spaces, COBie; 4D timeline | ✅ **verified** (XLSX written; 5D = $2.38M from geometry fallback) |
| **M5** | Author/edit families server-side, re-publish, pins survive | ✅ **verified** — in-browser authoring ships as server-side ifcopenshell recipes (create/edit walls, columns, slabs, families, MEP by GUID-stable recipe; no Blender required). The Bonsai/Blender bridge is now an optional advanced-interop path, not required. |
| **M6** | Self-hosted, offline, authenticated deployment | ✅ docker/compose/Dockerfiles + optional API-key auth (verified 401/201); full stack not booted here |

## Verified by running
- **IFC→Fragments** (Node, local web-ifc WASM, offline): 8.6 MB → 630 KB `.frag`.
- **Properties index** (ifcopenshell 0.8.5): 1551 elements, 9 classes, 5 storeys → `props.json`.
- **Data exports** (XLSX): QTO 1541 elements; **5D estimate $2,381,748** via geometry fallback;
  COBie Facility/Floor/Type/Component sheets; 4D activity↔element mapping (A100→77 columns).
- **API** (FastAPI + SQLite): project→pin RFI→viewpoint→comment→attachment(download)→pins
  overlay→status workflow→**BCF export (markup.bcf + .bcfv)→import round-trip**→properties
  index upload + GUID lookup + class filter. Auth: 401 without key / 201 with key.
- **Web app**: `tsc --noEmit` clean; `vite build` passes; dev server serves page + local WASM.

## Pending (needs human / external accounts)
- Browser visual check of render + click→properties + tools (open the running viewer).
- RVT→IFC: `services/converter/src/rvtToIfc.mjs` is a documented skeleton — needs an Autodesk
  APS account (paid, per-translation cost).
- Blender + Bonsai + Bonsai-MCP run for M5 (recipes are written and compile).
- Boot the full docker-compose stack against Postgres + MinIO.

## Integrated application (verified live in browser)
The viewer is wired to the running API end-to-end (web :5173 ↔ api :8000), verified against
the seeded "School" project:
- **Tree** panel — 5 storeys → IFC class → element, click selects in 3D (green highlight).
- **Layers** panel — 9 IFC classes with visibility toggle, color swatch, isolate.
- **Issues** panel — RFI list; click restores the viewpoint (camera) + selects the element +
  shows API properties; "+ RFI from selection" creates a topic + viewpoint + pin.
- **Properties** — rendered from the Phase 1 index via the API (Psets formatted).
- **Pin overlay** — markers from `/pins`, click restores viewpoint.
- Known cosmetic nit: camera re-fit after isolate/show-all can over-zoom (functionality fine).

## Per-phase code map
| Phase | Location |
|---|---|
| 1 conversion | `services/converter/src/{ifcToFrag,rvtToIfc,cli}.mjs` |
| 1 properties index | `services/data/src/aec_data/properties_index.py` |
| 2 large models | `docs/phase2-large-models.md`, Fragments streaming + `tools/layers.ts` |
| 3 viewer tools | `apps/web/src/{viewer,tools,tree,pins}/` |
| 4 API / BCF | `services/api/src/aec_api/` |
| 5 data export | `services/data/src/aec_data/{qto,spaces,cobie,schedule}.py` |
| 6 editor | `apps/editor-bridge/{recipes.py,bonsai-mcp.config.json}` |
| 7 deploy | `docs/deploy.md`, `*/Dockerfile`, `docker-compose.yml`, `auth.py`, `LICENSE-NOTES.md` |
