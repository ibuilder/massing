#!/usr/bin/env node
// Usage: node src/cli.mjs <input.ifc> [output.frag]
//        node src/cli.mjs --rvt <input.rvt> [output.frag]   (Revit via Autodesk APS — paid bridge)
import { readFile, writeFile } from "node:fs/promises";
import { basename } from "node:path";
import { ifcToFragments } from "./ifcToFrag.mjs";

const args = process.argv.slice(2);
const rvtMode = args[0] === "--rvt";
const [input, output] = rvtMode ? args.slice(1) : args;
if (!input) {
  console.error("Usage: node src/cli.mjs <input.ifc> [output.frag]  |  --rvt <input.rvt> [output.frag]");
  process.exit(1);
}

const out = output ?? input.replace(/\.(ifc|rvt)$/i, ".frag");
const t0 = Date.now();

let ifcBytes;
if (rvtMode) {
  const { rvtToIfc } = await import("./rvtToIfc.mjs");   // RVT → IFC via APS, then IFC → frag below
  console.log(`[rvt2ifc] translating ${input} via Autodesk APS (paid)…`);
  ifcBytes = await rvtToIfc(new Uint8Array(await readFile(input)), basename(input),
                            (s) => process.stdout.write(`\r[rvt2ifc] ${s}…            `));
  console.log(`\n[rvt2ifc] IFC received (${(ifcBytes.length / 1e6).toFixed(1)}MB) → converting to fragments`);
} else {
  console.log(`[ifc2frag] reading ${input}`);
  ifcBytes = new Uint8Array(await readFile(input));
}

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
// web-ifc / fragments keep a worker + wasm runtime alive, so the event loop never
// drains and the process hangs after writing. Force-exit so callers (the API's
// subprocess.run) don't block until their timeout.
process.exit(0);
