// Copies the web-ifc WASM binaries into public/wasm/ so the viewer runs fully OFFLINE
// (no unpkg/CDN fetch at runtime). Re-run after bumping web-ifc. See CLAUDE.md non-negotiables.
import { mkdirSync, copyFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const dest = join(webRoot, "public", "wasm");

// resolve the web-ifc package dir — handles npm-workspace hoisting (root node_modules)
// or a local install. web-ifc blocks ./package.json in its exports map, so probe paths.
createRequire(import.meta.url); // (kept for potential future resolve use)
const candidates = [
  join(webRoot, "node_modules", "web-ifc"),
  join(webRoot, "..", "..", "node_modules", "web-ifc"),
];
const wasmSource = candidates.find((c) => existsSync(join(c, "web-ifc.wasm")));
if (!wasmSource) {
  console.error("[copy-wasm] could not find web-ifc package. Looked in:\n  " + candidates.join("\n  "));
  process.exit(1);
}

const files = ["web-ifc.wasm", "web-ifc-mt.wasm"];

mkdirSync(dest, { recursive: true });
for (const f of files) {
  const src = join(wasmSource, f);
  if (!existsSync(src)) {
    console.warn(`[copy-wasm] missing ${src} — skipped`);
    continue;
  }
  copyFileSync(src, join(dest, f));
  console.log(`[copy-wasm] ${f} -> public/wasm/`);
}
console.log("[copy-wasm] done");
