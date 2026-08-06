// Copies the web-ifc WASM binaries into public/wasm/ so the viewer runs fully OFFLINE
// (no unpkg/CDN fetch at runtime). Re-run after bumping web-ifc. See CLAUDE.md non-negotiables.
import { mkdirSync, copyFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { findPackageDir } from "./wasmSources.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const dest = join(webRoot, "public", "wasm");

// Resolve the package rather than guessing how far up `node_modules` is: the old two-candidate
// probe assumed the repo root was exactly two levels above `apps/web`, which is false in every
// git worktree and made `npm run build` fail there. See scripts/wasmSources.mjs.
const wasmSource = findPackageDir("web-ifc", webRoot);
if (!wasmSource || !existsSync(join(wasmSource, "web-ifc.wasm"))) {
  console.error(
    "[copy-wasm] could not find the web-ifc package.\n" +
    `  resolved to: ${wasmSource ?? "(unresolved)"}\n` +
    "  Run `npm install` at the repo root. From a git worktree this resolves the MAIN clone's\n" +
    "  node_modules by upward lookup, which is expected — worktrees do not get their own.",
  );
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

// laz-perf WASM (LAZ point-cloud decoding) — same offline-vendoring rule; loaded via locateFile.
const lazDir = findPackageDir("laz-perf", webRoot);
const lazSrc = lazDir ? [join(lazDir, "lib", "laz-perf.wasm")].find((p) => existsSync(p)) : undefined;
if (lazSrc) {
  copyFileSync(lazSrc, join(dest, "laz-perf.wasm"));
  console.log("[copy-wasm] laz-perf.wasm -> public/wasm/");
} else {
  console.warn("[copy-wasm] laz-perf.wasm not found — LAZ point clouds will be unavailable");
}

console.log("[copy-wasm] done");
