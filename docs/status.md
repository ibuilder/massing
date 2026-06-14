# Build status — verified vs. pending

Snapshot of what's been built and how far each piece is verified on this machine
(node 20.3.1, python 3.10.6, Windows). "Verified" = ran successfully against the real
sample model (`samples/school_str.ifc`, the That Open structural school, 8.6 MB, IFC4).

## Milestones
| ID | Goal | Status |
|---|---|---|
| **M0** | Load IFC → `.frag` → render → click → properties | ✅ **verified in browser** — model renders; raycast hit IFCSLAB localId 76489 / GUID 2UD3D7uxP8kecbbBCRtzEl with full attributes |
| **M1** | Large federated model: streaming + layers by discipline/storey | ✅ code complete (Fragments streaming + LayerManager); strategy in `docs/phase2-large-models.md` |
| **M2** | Full toolset: nav, tree, isolate/ghost, section, measure, set-origin | ✅ modules build + typecheck; **color-by-data verified in browser** (307 slabs highlighted) |
| **M3** | Pin an RFI, restore viewpoint, export `.bcfzip` | ✅ **verified** end-to-end (API smoke test) |
| **M4** | Export QTO/estimate, spaces, COBie; 4D timeline | ✅ **verified** (XLSX written; 5D = $2.38M from geometry fallback) |
| **M5** | Place a family/type via Bonsai, re-publish, pins survive | 📝 recipes + MCP config written; needs Blender to run |
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
