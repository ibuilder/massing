/**
 * Local stand-in for `three/examples/jsm/loaders/TTFLoader.js`, aliased in by `vite.config.ts`.
 *
 * ## Why this file exists — a non-negotiable was being broken by a transitive import
 *
 * three's own `TTFLoader.js` begins:
 *
 *     import opentype from 'https://cdn.jsdelivr.net/npm/opentype.js@1.3.4/+esm';
 *
 * a **static import of a CDN URL**, which Rolldown cannot bundle and emits verbatim. Nothing in this
 * app imports `TTFLoader`; `@thatopen/components-front` does, for a `DrawingEditor` font loader we
 * never construct. But a static import is loaded whether or not it is used, and because
 * `components-front` pulls in `three`, that line landed at the **top of the `three-*.js` chunk** —
 * the chunk every 3D module depends on.
 *
 * The consequence is not a missing font. With no route to jsdelivr the chunk never evaluates, the
 * dynamic `import("./viewer/app")` rejects, and **the viewer does not appear at all** — measured in a
 * headless Chromium on 2026-08-27: `Failed to fetch dynamically imported module .../viewer/app.ts`,
 * and no `.canvas-tabs` ever rendered. Against the fourth non-negotiable in CLAUDE.md: *the viewer
 * must run fully offline (local WASM, self-hosted tiles)*.
 *
 * ## Why a stub rather than a bundled opentype.js
 *
 * Vendoring opentype.js would add a dependency to make a code path work that this app never enters.
 * `LengthMeasurement`, `AreaMeasurement` and `AngleMeasurement` are the only things imported from
 * `components-front` (`apps/web/src/tools/measure.ts`), and none of them loads a font.
 *
 * So the stub keeps the module's SHAPE and refuses at the point of use. If somebody later wires up
 * the drawing editor's text, they get a named error telling them what to do — not a silent blank
 * label, and not a CDN request that works on their machine and fails in an air-gapped deployment.
 */

const REASON =
  "TTFLoader is stubbed out: three's version statically imports opentype.js from a CDN, which breaks "
  + "the offline-viewer non-negotiable. Bundle a local font parser before using TTF fonts. "
  + "See apps/web/src/shims/TTFLoader.ts";

export class TTFLoader {
  /** Mirrors three's `Loader#load(url, onLoad, onProgress, onError)`. */
  load(
    _url: string,
    _onLoad?: (json: unknown) => void,
    _onProgress?: (e: ProgressEvent) => void,
    onError?: (err: unknown) => void,
  ): void {
    const err = new Error(REASON);
    // Report through the caller's channel when it has one — a loader that throws synchronously out
    // of `load()` crashes callers that expect the error on the callback. Rethrow only when there is
    // nowhere else for it to go, so it can never fail silently.
    if (onError) onError(err);
    else throw err;
  }

  parse(_buffer: ArrayBuffer): never {
    throw new Error(REASON);
  }
}

export default TTFLoader;
