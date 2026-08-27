#!/usr/bin/env node
// Fail the build if the shipped bundle imports anything over the network.
//
// The fourth non-negotiable in CLAUDE.md is that **the viewer must run fully offline** (local WASM,
// self-hosted tiles). Nothing enforced it, and on 2026-08-27 a headless-browser run found it broken:
// `three/examples/jsm/loaders/TTFLoader.js` statically imports
// `https://cdn.jsdelivr.net/npm/opentype.js@1.3.4/+esm`, Rolldown emitted the URL verbatim, and it
// landed on line 1 of the `three-*.js` chunk. With no route to jsdelivr the chunk never evaluates,
// the viewer's dynamic import rejects, and NOTHING renders — no error in the UI, just an empty
// canvas. `src/shims/TTFLoader.ts` is the fix; this is the thing that fails if it comes back.
//
// ## Why this greps the OUTPUT rather than reading the config
//
// `vite.config.ts` already carries the lesson in as many words: a vendor split that silently stops
// splitting still builds, still emits a chunk with the right name, and is wrong. An alias is the
// same shape — rename the upstream file, bump the dependency, and the alias quietly matches nothing.
// The bundle is the artefact that gets deployed, so the bundle is what gets checked.
//
// ## What counts as a violation
//
// A network URL in an *import position* — `import x from "https://…"`, `import("https://…")`, or a
// bare `require("http://…")`. A URL inside a string that is merely *data* (a docs link, an endpoint
// the app deliberately fetches, a CSP source list) is not a module the runtime must reach before
// evaluating the file, and is not flagged: this check is about what the bundle cannot START without.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const DIST = join(process.cwd(), "dist");

const PATTERNS = [
  /\bfrom\s*["'](https?:\/\/[^"']+)["']/g,
  /\bimport\s*\(\s*["'](https?:\/\/[^"']+)["']\s*\)/g,
  /\bimport\s+["'](https?:\/\/[^"']+)["']/g,
  /\brequire\s*\(\s*["'](https?:\/\/[^"']+)["']\s*\)/g,
];

function jsFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (/\.(js|mjs|cjs)$/.test(name)) out.push(p);
  }
  return out;
}

let files;
try {
  files = jsFiles(DIST);
} catch {
  console.error(`check-offline: ${DIST} not found — run \`vite build\` first.`);
  process.exit(2);
}

// Anti-vacuity. A check that scanned an empty directory would pass, and "0 remote imports" reads
// identically whether the bundle is clean or absent — the one-directional-gate shape this codebase
// keeps finding, where the population is filtered by the very thing under test.
if (files.length < 10) {
  console.error(`check-offline: only ${files.length} JS files under ${DIST} — that is not a built `
    + "bundle, and passing on it would be a false all-clear.");
  process.exit(2);
}

const hits = [];
for (const f of files) {
  const src = readFileSync(f, "utf8");
  for (const re of PATTERNS) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(src)) !== null) hits.push({ file: f.slice(DIST.length + 1), url: m[1] });
  }
}

if (hits.length) {
  console.error(`check-offline: ${hits.length} remote import(s) in the built bundle — the viewer `
    + "cannot run offline:\n");
  for (const h of hits) console.error(`  ${h.file}  imports  ${h.url}`);
  console.error("\nAlias the importing module to a local file (see src/shims/TTFLoader.ts and the "
    + "`resolve.alias` note in vite.config.ts), or vendor the dependency.");
  process.exit(1);
}

console.log(`check-offline OK - ${files.length} bundled JS files, no import reaches the network.`);
