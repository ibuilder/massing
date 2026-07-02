#!/usr/bin/env node
// Fail the build if the eager app *shell* grows past its budget. The shell is what every user
// downloads before anything is interactive; the heavy viewer libs (three/@thatopen), Studio, and the
// Finance/Drawings panels are code-split and lazy-loaded, so they're deliberately NOT counted here.
// We measure Brotli-compressed bytes — that's what a modern static server actually ships over the wire.
import { brotliCompressSync } from "node:zlib";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const DIST = join(process.cwd(), "dist", "assets");
// Budget in KB (Brotli). Set generously above the current shell so it catches regressions, not noise.
// Bump this deliberately (with a note) when the shell legitimately grows.
const BUDGET_KB = Number(process.env.BUNDLE_BUDGET_KB || 220);

// The eager shell = the entry chunk + the app chunk + the main CSS. Lazy chunks (three-*, thatopen-*,
// studio-*, panel-*) are excluded — they don't block first interaction.
const SHELL = [/^index-.*\.js$/, /^app-.*\.js$/, /^index-.*\.css$/];
const LAZY = /^(three|thatopen|studio|panel|viewer|charts|proforma)-/;

let files;
try {
  files = readdirSync(DIST);
} catch {
  console.error(`bundle-budget: ${DIST} not found — run \`vite build\` first.`);
  process.exit(2);
}

const shellFiles = files.filter((f) => SHELL.some((re) => re.test(f)));
if (!shellFiles.length) {
  console.error("bundle-budget: no shell chunks matched — did the entry/app chunk naming change?");
  console.error("  assets present:", files.filter((f) => /\.(js|css)$/.test(f)).join(", "));
  process.exit(2);
}

let total = 0;
const rows = [];
for (const f of shellFiles) {
  const br = brotliCompressSync(readFileSync(join(DIST, f)));
  total += br.length;
  rows.push([f, br.length]);
}

const kb = (n) => (n / 1024).toFixed(1);
console.log("App shell (Brotli):");
for (const [f, n] of rows.sort((a, b) => b[1] - a[1])) console.log(`  ${kb(n).padStart(7)} KB  ${f}`);
console.log(`  ${"-".repeat(28)}`);
console.log(`  ${kb(total).padStart(7)} KB  total  (budget ${BUDGET_KB} KB)`);

// Sanity: confirm the heavy libs really are separate lazy chunks, not folded into the shell.
const lazy = files.filter((f) => LAZY.test(f) && /\.js$/.test(f));
console.log(`Lazy chunks kept out of the shell: ${lazy.length}`);

if (total / 1024 > BUDGET_KB) {
  console.error(`\nbundle-budget: FAIL — shell ${kb(total)} KB exceeds ${BUDGET_KB} KB.`);
  console.error("Trim the eager path (lazy-load it) or bump BUNDLE_BUDGET_KB deliberately with a note.");
  process.exit(1);
}
console.log(`\nbundle-budget: OK — shell within ${BUDGET_KB} KB.`);
