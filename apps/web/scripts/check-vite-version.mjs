#!/usr/bin/env node
/**
 * Refuse to build with a Vite other than the one `apps/web/package.json` pins.
 *
 * WHY — a build that is silently WRONG rather than broken
 *     `apps/web/package.json` pins vite **8.1.5**. The repo ROOT holds **6.4.3**, hoisted there
 *     because `vite-plugin-pwa` and `vitest` both depend on vite ^6, so npm installs the pin
 *     **nested** at `apps/web/node_modules/vite` — a directory whose only entry is `vite`.
 *
 *     **A git worktree has no `apps/web/node_modules`**, so Node walks up and finds the root's 6.4.3.
 *     The build then succeeds. It does not warn. Measured on one commit, same command:
 *
 *         main clone   vite v8.1.5   three- and thatopen- chunks present   shell    334 KB
 *         worktree     vite v6.4.3   NEITHER chunk emitted                 shell  6,581 KB  (19.7x)
 *
 *     (Those chunk names are written without a glob on purpose: a "star-slash" inside a block
 *     comment closes it. That broke `wasmSources.mjs` earlier the same day, and writing this file
 *     reproduced it — the note was in the neighbouring file and did not stop me repeating it, which
 *     is the argument for a check over a comment.)
 *
 *     Vite 8 is rolldown-based and honours `build.rolldownOptions.advancedChunks`; Vite 6 is
 *     rollup-based and does not know the option, so the vendor split silently stops splitting and
 *     three.js is folded into the eager shell. The 50 `?commonjs-*` proxy modules that appear under
 *     6 and not 8 are the same story from the other end.
 *
 *     `vite.config.ts` is NOT at fault and must not be "fixed" — it is correct, and it is being fed
 *     to the wrong bundler.
 *
 * WHY A VERSION CHECK RATHER THAN A CHUNK CHECK
 *     `bundle-budget.mjs` already asserts the vendor chunks exist. That guards the SYMPTOM and is
 *     worth keeping: it also catches a chunking regression that has nothing to do with worktrees.
 *     This guards the CAUSE, and it fails *before* a two-minute build instead of after one.
 *
 * THE GENERALISATION, which this repo has now paid for twice in one day
 *     **The toolchain is part of the command.** A bare name resolves off a search path to something
 *     else, and the wrong one *works* rather than erroring — so the output looks reproducible and is
 *     wrong. The other instance: `run_tests.py`'s own docstring said `python run_tests.py`, which
 *     picks up an unrelated 3.10 off PATH instead of `services/api/.venv`.
 *
 *     So this message names the resolved PATH and BOTH versions. A preflight that says "wrong vite"
 *     without saying which one it found, and from where, reproduces the class it exists to kill.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { findPinnedViteDir } from "./vitePin.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const manifest = join(webRoot, "package.json");

const pkg = JSON.parse(readFileSync(manifest, "utf8"));
const pinned = pkg.devDependencies?.vite ?? pkg.dependencies?.vite;
if (!pinned) {
  console.error("[vite-preflight] apps/web/package.json declares no vite dependency — cannot check.");
  process.exit(1);
}

const dir = findPinnedViteDir(webRoot);
if (!dir) {
  console.error("[vite-preflight] could not resolve the pinned `vite` package. Run `npm install` at the repo root of the main clone.");
  process.exit(1);
}
const found = JSON.parse(readFileSync(join(dir, "package.json"), "utf8")).version;

/** Exact pins must match exactly; a ranged pin ("^8.1.5") is held only to its major. */
const exact = /^\d/.test(pinned);
const major = (v) => String(v).replace(/^[^\d]*/, "").split(".")[0];
const ok = exact ? found === pinned : major(found) === major(pinned);

if (!ok) {
  console.error(
    `\n[vite-preflight] REFUSING TO BUILD — resolved vite does not match the pin.\n\n` +
    `    pinned   ${pinned}   (in ${manifest.replace(/\\/g, "/")})\n` +
    `    resolved ${found}\n` +
    `    from     ${dir.replace(/\\/g, "/")}\n\n` +
    `  A git worktree has no apps/web/node_modules of its own. This preflight looks in the main\n` +
    `  clone (git-common-dir) for the nested pin first. If you still see this, the main clone is\n` +
    `  missing apps/web/node_modules/vite — run npm install there, not in the worktree.\n`,
  );
  process.exit(1);
}

console.log(`[vite-preflight] vite ${found} matches the pin (${pinned}) — ${dir.replace(/\\/g, "/")}`);
