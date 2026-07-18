# Client vs server — where work runs, and why

Massing is a **thin, offline-capable client over a Python authoring/analysis service**, not a fat
in-browser CAD kernel. This is a deliberate boundary: the browser renders, selects, snaps, and drafts;
the server holds the IFC source of truth and does every geometry-mutating and analysis operation. This
doc records the split and the two hard platform limits that shape it — so a contributor doesn't try to
push work to the wrong side.

> Lesson banked from the OpenAEC / Open CAD Studio study (2026-07): a native+WASM CAD project documents
> exactly what the browser build *cannot* do. Ours is the inverse — an IFC-native web platform — but the
> same two WebGL2/wasm limits apply, and naming them prevents a class of dead-end work.

## The rule of thumb

| Concern | Runs where | Why |
| --- | --- | --- |
| Render meshes, camera, selection, section box, measure | **Client** (three.js / That Open Fragments) | interactive, GPU-bound, no source mutation |
| Snap / inference / dynamic input while drawing | **Client** | must be frame-rate immediate; needs no server |
| The CAD command line + AI command-bar *parse* | **Client** | `cadCommands.ts` is a pure parser; the AI plan is server-assisted |
| **Every geometry mutation** (draw/edit/delete a wall, column, MEP…) | **Server** (`ifcopenshell` recipes) | one GUID-stable source of truth; the client never writes IFC |
| Drawings, sheets, schedules, PDF/DXF | **Server** | derived from the authored IFC; heavy, deterministic |
| Code / structural / MEP / carbon / cost analysis | **Server** | reads the model index; pure Python, testable |
| The property/quantity index the panels read | **Server** (`properties_index` → JSON) | geometry streams as Fragments; data comes from the API |

The client holds **no authoritative model state** — it streams Fragments geometry (`.frag`) for display
and reads element data from the API. A refresh, a second viewer, or the desktop app all reconstruct the
same view from the same server source. This is what makes GUID-stable round-tripping and real-time
collaboration cheap: edits serialize through one server path.

## Two platform limits that shape the client

### 1. WebGL2 has no vertex-stage storage buffers

Custom rendering that needs per-vertex structured reads on the GPU (the classic case: hatch / linetype
pattern generation in a vertex shader) **cannot run on WebGL2** — only WebGPU exposes vertex-stage
storage buffers. Consequence for us: any 2D fill/pattern or custom line styling in the viewer must use
**triangulated geometry or a texture**, never a storage-buffer trick, unless it is explicitly gated
behind a WebGPU capability check. (Today our 2D output — plans, sections, hatches — is generated
**server-side as SVG/PDF**, which sidesteps this entirely; the note matters only if custom in-viewer
2D rendering is ever added.)

### 2. wasm is single-threaded without SharedArrayBuffer, which needs cross-origin isolation

That Open Fragments / web-ifc run as WebAssembly, and multithreaded wasm needs `SharedArrayBuffer`,
which the browser only exposes when the page is **cross-origin isolated** (COOP `same-origin` + COEP
`require-corp`). We satisfy this two ways:

- **Self-hosted / nginx**: `apps/web/nginx.conf` sets `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp` (at both the server and asset level).
- **GitHub Pages** (which can't set headers): `pages.yml` swaps in **`coi-serviceworker.js`**, which
  re-adds the isolation headers from a service worker so the WASM viewer works on `massing.build/app`.

The COEP `require-corp` fallout ripples: any cross-origin subresource the viewer embeds (e.g. an
`<img>` from the attachment-download route) must carry `Cross-Origin-Resource-Policy: cross-origin`, which
is why `download_attachment` sets that header. If you add a cross-origin asset to the viewer and it fails
to load, this is why.

Heavy client-side compute should therefore assume **single-threaded wasm** unless isolation is confirmed
— mirror the server's own `AEC_GEOM_WORKERS` discipline (a `par`-or-sequential abstraction) rather than
counting on threads.

## When to push work to the server instead

If a proposed client feature needs: (a) to mutate the IFC, (b) heavy geometry the main thread can't
afford, or (c) determinism/testability, it belongs on the server as an edit recipe or analysis function
— dispatchable from the CAD command line, the AI bar, the node canvas, or a panel, and covered by the
authoring matrix (`docs/authoring-matrix.md`) and the test gate. The client's job is to make that
server capability feel instant.
