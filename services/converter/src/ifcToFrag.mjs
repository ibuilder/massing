// IFC → Fragments conversion (the open, main path). Runs in Node — "convert once,
// serve .frag forever" (guide §4a). Uses the same @thatopen/fragments IfcImporter and
// local web-ifc WASM as the browser, so server and client stay in lockstep.
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/** Locate the web-ifc package dir (handles workspace hoisting to the repo root). */
function findWasmDir() {
  const candidates = [
    join(here, "..", "..", "..", "node_modules", "web-ifc"), // repo-root hoist
    join(here, "..", "node_modules", "web-ifc"), // local install
  ];
  const dir = candidates.find((c) => existsSync(join(c, "web-ifc.wasm")));
  if (!dir) {
    throw new Error("web-ifc WASM not found. Looked in:\n  " + candidates.join("\n  "));
  }
  return dir;
}

/**
 * Convert IFC bytes to Fragments bytes.
 * @param {Uint8Array} ifcBytes raw .ifc contents
 * @param {(p:number)=>void} [onProgress]
 * @returns {Promise<Uint8Array>} .frag contents (write to object storage as <model_id>.frag)
 */
export async function ifcToFragments(ifcBytes, onProgress) {
  const { IfcImporter } = await import("@thatopen/fragments");
  const importer = new IfcImporter();
  // local WASM — keep the pipeline offline/self-hosted (CLAUDE.md non-negotiable).
  // Node loads web-ifc-node.wasm from this directory; absolute path so cwd doesn't matter.
  importer.wasm = { absolute: true, path: findWasmDir().replace(/\\/g, "/") + "/" };

  const frag = await importer.process({ bytes: ifcBytes, progressCallback: onProgress });
  return frag;
}
