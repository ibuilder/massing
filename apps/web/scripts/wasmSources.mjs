/**
 * Locate an installed package directory, without assuming how deep `node_modules` sits.
 *
 * WHY THIS EXISTS
 *     `copy-wasm.mjs` found `web-ifc` by trying two hard-coded relative paths:
 *
 *         <webRoot>/node_modules/web-ifc
 *         <webRoot>/../../node_modules/web-ifc      <- "the repo root", assumed two levels up
 *
 *     That second assumption is true in the main clone and **false in every git worktree**. A
 *     worktree at `.claude/worktrees/<lane>` puts the repo root FOUR levels above `apps/web`, and a
 *     worktree has no `node_modules` of its own — it resolves the main clone's by Node's upward
 *     lookup. So both candidates miss, and `npm run build` dies in `prebuild` with
 *     "could not find web-ifc package". Measured: exit 1 from a worktree's own `apps/web`.
 *     (That sentence originally cited the path as a glob, whose "star-slash" closed this very
 *     comment and made the file a syntax error — the build script's own docs breaking the build.)
 *
 *     That matters more than a broken build script, because `docs/roadmap-directions.md` §3 tells
 *     every agent to work in a worktree and states the marginal cost is "a source checkout". The
 *     build was an unlisted part of that cost.
 *
 * THE FIX WAS ALREADY IN THIS REPO, ONE DIRECTORY AWAY
 *     `apps/web/vitest.config.ts` hit the identical problem — a worktree resolving `node_modules`
 *     up into the main clone — and solved it by asking Node instead of guessing:
 *
 *         path.dirname(createRequire(import.meta.url).resolve("pdfjs-dist/package.json"))
 *
 *     Same cause, same fix, written for the test config and never carried across to the build
 *     script. **Depth is the thing you must not hard-code**; `createRequire` walks upward exactly
 *     the way the runtime does, so it is correct at any depth and in any checkout.
 *
 * WHY NOT JUST `resolve(name + "/package.json")`
 *     Because `web-ifc` blocks `./package.json` in its exports map — that resolve throws
 *     `ERR_PACKAGE_PATH_NOT_EXPORTED`. (`laz-perf` allows it; the two packages genuinely differ,
 *     which is why this tries both and then truncates a resolved entry point instead.) The original
 *     script's comment already recorded this hazard, and it even imported `createRequire` on the
 *     line above — then left it unused with the note "kept for potential future resolve use". The
 *     tool that would have fixed this was sitting in the file the whole time.
 */
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { dirname, join, sep } from "node:path";

/**
 * Absolute path to an installed package's root directory, or `null`.
 *
 * `webRoot` is consulted only as a LAST resort, for layouts Node cannot resolve (a package vendored
 * somewhere that is not on the resolution path). It is a parameter rather than a constant so a test
 * can hand this function a directory where the old relative candidates could not possibly succeed —
 * which is the only way to assert the depth assumption is really gone. See `src/build/copyWasm.test.ts`.
 */
export function findPackageDir(name, webRoot, requireFrom = import.meta.url) {
  const req = createRequire(requireFrom);

  // 1. The package's own manifest, when its exports map permits it.
  try {
    return dirname(req.resolve(`${name}/package.json`));
  } catch { /* exports map may block it (web-ifc does) — try the entry point instead */ }

  // 2. The entry point, truncated back to the package root. `lastIndexOf` rather than `indexOf`
  //    because a nested `node_modules` (a transitive copy) is the one actually being used.
  try {
    const entry = req.resolve(name);
    const marker = `node_modules${sep}${name.split("/").join(sep)}`;
    const at = entry.lastIndexOf(marker);
    if (at >= 0) return entry.slice(0, at + marker.length);
  } catch { /* not resolvable at all — fall through to the explicit candidates */ }

  // 3. Explicit layouts, kept so a non-node_modules checkout still works. NOT the primary path:
  //    these are the assumptions that broke, and they must never be the only mechanism again.
  for (const candidate of [join(webRoot, "node_modules", name), join(webRoot, "..", "..", "node_modules", name)]) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}
