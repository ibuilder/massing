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
 * Every `node_modules` this workspace can see — plural, because in an npm workspace the tree is SPLIT.
 *
 * TWO WRONG VERSIONS, BOTH FROM ASSUMING THE TREE HAS ONE ROOT
 *
 * 1. `join(here, "..", "..", "..")` — "the repo root, three levels up". True in the main clone,
 *    **false in every git worktree**, where the hoisted `node_modules` sits in the main clone at no
 *    fixed depth. Printed "node_modules not found". That is the identical bug fixed in
 *    `copy-wasm.mjs` earlier the same day, reintroduced hours later by reflex.
 *
 * 2. Resolving ONE package and taking its parent. This passed locally and **failed in CI on its
 *    first real run**, with the vacuity floor firing:
 *
 *        [licences] scanned 1 npm packages under .../apps/web/node_modules
 *        [licences] FAIL — only 1 packages scanned (< 400); this gate would be vacuous.
 *
 *    `apps/web/package.json` pins `vite`, so npm installs it NESTED at `apps/web/node_modules/vite`
 *    while everything else hoists to the repo root — **that directory holds exactly one entry.**
 *    Probing `vite` therefore resolves to a `node_modules` containing 1 package instead of 434.
 *
 *    The bitter part: that layout is the **same fact** diagnosed in BUILD-WORKTREE-CHUNKS hours
 *    earlier ("that directory contains exactly one entry, `vite`"). One root cause, two defects, and
 *    the second bit the tool built to prevent this class of mistake. **A fact you have already
 *    established about the layout does not automatically transfer to the next thing you build on it.**
 *
 *    Note also the inversion: in a WORKTREE (no nested dir) the probe resolves to the root and the
 *    scan is correct, so the broken configuration is the one that looks right locally. **The local
 *    run scanned the right tree by accident.**
 *
 * So: walk the ancestor chain and take EVERY `node_modules`, then add whatever Node resolves, and
 * union. The floor stays at 400 — it earned it.
 */
function nodeModulesRoots() {
  const webRoot = join(here, "..");
  const roots = new Set();

  // 1. Every `node_modules` on the ancestor chain. In an npm workspace the tree is SPLIT: most
  //    packages hoist to the repo root, and a few sit nested beside the workspace that pins them.
  let dir = webRoot;
  for (let i = 0; i < 8; i++) {
    const nm = join(dir, "node_modules");
    if (existsSync(nm)) roots.add(nm);
    const up = dirname(dir);
    if (up === dir) break;
    dir = up;
  }

  // 2. Plus wherever Node actually resolves a few packages, in case a layout the walk cannot see
  //    (a link, a different workspace root) holds something.
  for (const probe of ["vite", "three", "typescript"]) {
    const d = findPackageDir(probe, webRoot);
    if (d) roots.add(dirname(d));
  }
  return [...roots];
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
          found.push({
            // The package's own directory, so the caller can dedupe ACROSS ROOTS by identity rather
            // than by name. Deduping by name collapses a nested second copy of a package into the
            // hoisted one — and a nested copy can carry a DIFFERENT licence, which is precisely what
            // this gate exists to notice. Same directory reached twice is one package; same name at
            // two directories is two.
            dir: p.replace(/\\/g, "/"),
            ...verdict({
              name: j.name ?? e.name,
              declared,
              licenceFile,
              licenceText: licenceFile ? readFileSync(join(p, licenceFile), "utf8") : null,
            }),
          });
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
  const roots = nodeModulesRoots();
  if (!roots.length) {
    console.error("[licences] found no node_modules on the ancestor chain — run `npm ci` at the repo root.");
    process.exit(2);
  }
  // Union across roots, deduped by DIRECTORY. The same directory can be reachable from two roots and
  // must count once; two copies of one package at different paths are two packages and must both be
  // judged, because a nested copy can carry a different licence.
  const seen = new Map();
  const perRoot = new Map();
  for (const r of roots) {
    const found = scan(r);
    perRoot.set(r, found.length);
    for (const v of found) if (!seen.has(v.dir)) seen.set(v.dir, v);
  }
  const all = [...seen.values()];
  const by = (s) => all.filter((v) => v.status === s);

  // Name every root AND its count. The first version scanned one root and printed one number, so a
  // 1-package scan looked like a scan. Per-root counts make the split tree legible in the log.
  console.log(`[licences] scanned ${all.length} npm packages across ${roots.length} node_modules root(s):`);
  for (const r of roots) console.log(`    ${String(perRoot.get(r) ?? 0).padStart(4)}  ${r.replace(/\\/g, "/")}`);
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
