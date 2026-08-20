/**
 * Locate the Vite this repo actually pins — the nested copy under `apps/web/node_modules`,
 * not the Vite 6 hoisted at the workspace root.
 *
 * WHY
 *     `apps/web/package.json` pins vite 8.x. The repo root holds 6.x because `vite-plugin-pwa`
 *     and `vitest` still depend on ^6, so npm nests the pin at `apps/web/node_modules/vite`.
 *     A git worktree has no that directory. Node's upward walk from the worktree finds the
 *     root's 6.x. Vite 6 is rollup-based and ignores `rolldownOptions.advancedChunks`, so
 *     `vite build` exits 0 and emits a 19.7× eager shell.
 *
 *     `findPackageDir("vite")` is the same walk, so a preflight that uses it from a worktree
 *     reports "wrong vite" and refuses — which is honest, and also means the directions that
 *     say "work in a worktree" cannot produce a shippable bundle.
 *
 *     The nested pin is not an ancestor of an *out-of-repo* worktree. It lives in the main
 *     clone. `git rev-parse --git-common-dir` names that clone. Looking there — both
 *     `apps/web/node_modules/vite` (nested pin) and `node_modules/vite` (hoisted pin) —
 *     is what makes a worktree build the same bundler as CI.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { findPackageDir } from "./wasmSources.mjs";

/** Absolute path of the main clone (the directory that contains `.git/`), or null. */
export function gitMainRoot(fromDir) {
  try {
    const common = execFileSync(
      "git",
      ["-C", fromDir, "rev-parse", "--git-common-dir"],
      { encoding: "utf8" },
    ).trim();
    if (!common) return null;
    return dirname(resolve(fromDir, common));
  } catch {
    return null;
  }
}

function viteVersion(dir) {
  try {
    return JSON.parse(readFileSync(join(dir, "package.json"), "utf8")).version;
  } catch {
    return null;
  }
}

function pinOf(webRoot) {
  const tryRead = (dir) => {
    try {
      const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
      return pkg.devDependencies?.vite ?? pkg.dependencies?.vite ?? null;
    } catch {
      return null;
    }
  };
  return tryRead(webRoot) || tryRead(join(gitMainRoot(webRoot) || "", "apps", "web")) || null;
}

function matchesPin(found, pinned) {
  if (!found || !pinned) return false;
  const exact = /^\d/.test(pinned);
  const major = (v) => String(v).replace(/^[^\d]*/, "").split(".")[0];
  return exact ? found === pinned : major(found) === major(pinned);
}

/**
 * Directory of the pinned vite package, or null.
 *
 * Order is the point: nested pin under apps/web, then the same path on the main clone
 * (worktrees), then Node's walk. A candidate whose version does not match the pin is
 * skipped — that is how the workspace-root Vite 6 loses to the nested 8 when both exist.
 * Layouts that hoist the pin to the workspace root (this cloud image) still succeed,
 * because the walked copy matches.
 */
export function findPinnedViteDir(webRoot) {
  const pin = pinOf(webRoot);
  const seen = new Set();
  const candidates = [join(webRoot, "node_modules", "vite")];
  const main = gitMainRoot(webRoot);
  if (main) {
    candidates.push(join(main, "apps", "web", "node_modules", "vite"));
    candidates.push(join(main, "node_modules", "vite"));
    const fromMain = findPackageDir(
      "vite",
      join(main, "apps", "web"),
      pathToFileURL(join(main, "apps", "web", "package.json")).href,
    );
    if (fromMain) candidates.push(fromMain);
  }
  const walked = findPackageDir("vite", webRoot);
  if (walked) candidates.push(walked);
  for (const c of candidates) {
    const abs = resolve(c);
    if (seen.has(abs)) continue;
    seen.add(abs);
    if (!existsSync(join(abs, "package.json"))) continue;
    if (pin && !matchesPin(viteVersion(abs), pin)) continue;
    return abs;
  }
  return null;
}

/** Absolute path of `vite`'s CLI entry, or null. */
export function viteCli(dir) {
  if (!dir) return null;
  const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  const bin = typeof pkg.bin === "string" ? pkg.bin : pkg.bin?.vite;
  if (!bin) return null;
  return join(dir, bin);
}
