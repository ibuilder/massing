# Phase 2 — Large-model handling

Goal: open hundreds of MB / millions of elements smoothly on a laptop and on the web.

## What Fragments gives us for free
`@thatopen/fragments` (3.4.x) streams geometry off the main thread via the worker and culls
to the camera frustum. The viewer only uploads geometry for visible/requested items. We use
this directly — no custom LOD needed for typical AEC models.

## Serving
- Store `.frag` tiles in object storage (MinIO/S3) and serve over HTTP with **range
  requests** + CDN caching. Tiles are immutable per model version → cache forever.
- Serve the web-ifc WASM and the Fragments worker from our own origin (offline/self-host).

## Federation = separate files, toggled as layers
The realistic AEC pattern: a federated set arrives as **separate discipline IFCs**
(architectural, structural, MEP). Convert each independently (`services/converter`) to its
own `.frag`. The viewer loads them as separate models; the **LayerManager** (Phase 3)
toggles visibility/ghost/color per discipline and per storey. This keeps each payload small
and lets the user stream only what they need.

```
arch.ifc  ─┐
struct.ifc ─┼─ convert each ─► arch.frag / struct.frag / mep.frag ─► viewer loads on demand
mep.ifc   ─┘                                                          (layer = model + selection set)
```

## Keep geometry and data separate (non-negotiable)
Never ship full Psets inside the geometry payload. Geometry streams as `.frag`; element
metadata comes from the **properties index** (`props.json`, Phase 1) via the API. A click
raycasts to a GUID, then fetches Psets on demand.

## Performance budget guard
- Cap concurrent loaded models / fragments; show a streaming progress indicator
  (`IfcImporter` / `load()` expose `progressCallback` / `onProgress`).
- Split very large single-discipline models by storey at conversion time if one file is
  still too heavy.
- Prefer `Open .frag` (pre-converted) over `Open IFC` (in-browser convert) for anything
  beyond a smoke-test-sized file — in-browser conversion is single-threaded and slow.

## Verified locally
- 8.6 MB IFC → 630 KB `.frag` (structural school model), converted server-side in Node with
  local WASM. Properties index: 1551 elements extracted to `props.json` and served by GUID.
