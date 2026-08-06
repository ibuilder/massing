#!/usr/bin/env node
/**
 * R41-LICENCE-GATE — enforce the licence allowlist over the npm tree in CI instead of by reading.
 *
 * Runs in the WEB job, deliberately. `node_modules` exists there because that job runs `npm ci`;
 * the API test gate does not, so a Python-side npm scan would have found nothing and passed
 * vacuously — the failure mode this repo keeps paying for. Where a check runs is part of its claim.
 *
 * Policy and the reasoning behind the classifier live in `licencePolicy.mjs`. Read the note there
 * about MPL-2.0 naming the GPL in its own definitions before changing anything.
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { verdict } from "./licencePolicy.mjs";
import { findPackageDir } from "./wasmSources.mjs";

const here = dirname(fileURLToPath(import.meta.url));

/**
 * Locate `node_modules` by RESOLVING a package, never by counting `..` segments.
 *
 * The first draft used `join(here, "..", "..", "..")` — "the repo root, three levels up from
 * `apps/web/scripts`". That is true in the main clone and **false in every git worktree**, where the
 * hoisted `node_modules` lives in the main clone several levels away and at no fixed depth. It
 * printed "node_modules not found" from a worktree.
 *
 * This is the identical bug fixed in `copy-wasm.mjs` earlier the same day, reintroduced here by the
 * same reflex a few hours later — which is the argument for the shared resolver existing at all.
 * `findPackageDir` walks the way Node does; the parent of any resolved package is its `node_modules`.
 */
function locateNodeModules() {
  const webRoot = join(here, "..");
  for (const probe of ["vite", "three", "typescript"]) {
    const dir = findPackageDir(probe, webRoot);
    // A scoped package resolves two levels deep; none of the probes is scoped, so one parent is right.
    if (dir) return dirname(dir);
  }
  return null;
}

/** A licence file, whatever the extension: LICENSE, LICENCE, COPYING, LICENSE.md, LICENSE-MIT… */
const LICENCE_FILE = /^(LICENSE|LICENCE|COPYING)([.-].*)?$/i;

/** Directories that are not packages. `.bin` is symlinks; the rest are caches. */
const NOT_A_PACKAGE = new Set([".bin", ".vite", ".cache", ".package-lock.json"]);

export function scan(nodeModules, maxDepth = 3) {
  const found = [];
  const walk = (dir, depth) => {
    if (depth > maxDepth) return;
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      if (NOT_A_PACKAGE.has(e.name)) continue;
      const p = join(dir, e.name);
      // A scope directory (@thatopen) is a container, not a package — descend at the same depth.
      if (e.name.startsWith("@")) { walk(p, depth); continue; }
      const manifest = join(p, "package.json");
      if (existsSync(manifest)) {
        try {
          const j = JSON.parse(readFileSync(manifest, "utf8"));
          const declared = typeof j.license === "string"
            ? j.license
            : (j.license?.type ?? (Array.isArray(j.licenses) ? j.licenses.map((x) => x.type).join(" OR ") : null));
          const licenceFile = readdirSync(p).find((f) => LICENCE_FILE.test(f)) ?? null;
          found.push(verdict({
            name: j.name ?? e.name,
            declared,
            licenceFile,
            licenceText: licenceFile ? readFileSync(join(p, licenceFile), "utf8") : null,
          }));
        } catch { /* an unreadable manifest is not a licence finding; npm ci would have failed */ }
      }
      if (existsSync(join(p, "node_modules"))) walk(join(p, "node_modules"), depth + 1);
    }
  };
  walk(nodeModules, 0);
  return found;
}

/**
 * Unclassified packages are a RATCHET, not a pass. Eight licence files match no known title today
 * (two Tauri `.spdx` stubs, `type-fest`'s CC0, and five bespoke or terse texts). Letting that number
 * grow unremarked is how a classifier quietly stops classifying; it only ever moves down.
 *
 * Set at the EXACT current count, not comfortably above it. The first draft said 19 — the count from
 * an earlier, coarser classifier — which would have sat green through eleven new unreadable licences.
 * A threshold taken from a superseded measurement is a threshold for a different question.
 */
const UNCLASSIFIED_CEILING = Number(process.env.LICENCE_UNCLASSIFIED_CEILING || 8);

/** Below this the scan found nothing meaningful and every verdict below would be vacuous. */
const MIN_PACKAGES = 400;

if (import.meta.url === `file://${process.argv[1]}`.replace(/\\/g, "/") || process.argv[1]?.endsWith("check-licences.mjs")) {
  const root = locateNodeModules();
  if (!root || !existsSync(root)) {
    console.error("[licences] could not resolve node_modules from any known package — run `npm ci` at the repo root.");
    process.exit(2);
  }
  const all = scan(root);
  const by = (s) => all.filter((v) => v.status === s);

  console.log(`[licences] scanned ${all.length} npm packages under ${root.replace(/\\/g, "/")}`);
  if (all.length < MIN_PACKAGES) {
    console.error(`[licences] FAIL — only ${all.length} packages scanned (< ${MIN_PACKAGES}); this gate would be vacuous.`);
    process.exit(1);
  }

  const report = by("REPORT");
  if (report.length) {
    console.log(`[licences] weak copyleft, accepted for our distribution model (${report.length}):`);
    for (const v of report) console.log(`    ${v.name} — ${v.reason}`);
  }

  const unclassified = by("UNCLASSIFIED");
  console.log(`[licences] unclassified licence texts: ${unclassified.length} (ceiling ${UNCLASSIFIED_CEILING})`);

  const bad = [...by("FORBIDDEN"), ...by("CONTRADICTION")];
  if (bad.length) {
    console.error(`\n[licences] FAIL — ${bad.length} package(s) violate the MIT/BSD/Apache-only rule:\n`);
    for (const v of bad) console.error(`    ${v.status.padEnd(14)} ${v.name}\n                   ${v.reason}`);
    console.error(
      "\n  A CONTRADICTION means the package's own LICENSE file disagrees with what it declares.\n" +
      "  Trust the file. Remove the dependency or get the licence confirmed in writing.\n",
    );
    process.exit(1);
  }

  if (unclassified.length > UNCLASSIFIED_CEILING) {
    console.error(
      `\n[licences] FAIL — ${unclassified.length} unclassified licence texts exceeds the ceiling of ${UNCLASSIFIED_CEILING}.\n` +
      "  Either the classifier needs a new title, or a dependency ships a bespoke licence that wants reading:\n",
    );
    for (const v of unclassified) console.error(`    ${v.name} (${v.licenceFile})`);
    process.exit(1);
  }

  console.log(`[licences] OK — ${by("OK").length} permissive, ${report.length} weak-copyleft reported, 0 forbidden.`);
}
