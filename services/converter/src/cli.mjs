#!/usr/bin/env node
// Usage: node src/cli.mjs <input.ifc> [output.frag]
import { readFile, writeFile } from "node:fs/promises";
import { basename } from "node:path";
import { ifcToFragments } from "./ifcToFrag.mjs";

const [, , input, output] = process.argv;
if (!input) {
  console.error("Usage: node src/cli.mjs <input.ifc> [output.frag]");
  process.exit(1);
}

const out = output ?? input.replace(/\.ifc$/i, ".frag");
const t0 = Date.now();

console.log(`[ifc2frag] reading ${input}`);
const ifcBytes = new Uint8Array(await readFile(input));

let lastPct = -1;
const frag = await ifcToFragments(ifcBytes, (p) => {
  const pct = Math.floor(p * 100);
  if (pct !== lastPct && pct % 10 === 0) {
    process.stdout.write(`\r[ifc2frag] converting ${basename(input)}… ${pct}%`);
    lastPct = pct;
  }
});

await writeFile(out, frag);
const secs = ((Date.now() - t0) / 1000).toFixed(1);
console.log(
  `\n[ifc2frag] wrote ${out}  (${(ifcBytes.length / 1e6).toFixed(1)}MB ifc → ${(frag.length / 1e6).toFixed(1)}MB frag in ${secs}s)`,
);
