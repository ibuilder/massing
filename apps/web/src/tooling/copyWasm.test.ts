import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The build's WASM copy step must not assume how deep `node_modules` is.
 *
 * WHAT BROKE
 *     `scripts/copy-wasm.mjs` located `web-ifc` with two hard-coded relative candidates, the second
 *     being `<webRoot>/../../node_modules` — "the repo root, two levels above apps/web". True in the
 *     main clone, false in every git worktree, where the root is four levels up and the worktree has
 *     no `node_modules` of its own. `npm run build` therefore exited 1 in `prebuild` from any
 *     worktree, taking `build`, `build:desktop` and `build:mobile` with it.
 *
 * WHY THIS TEST IS SHAPED THE WAY IT IS — the important part
 *     The obvious test ("run the build script, assert exit 0") **cannot fail in CI**, because CI runs
 *     in the main clone where the broken assumption happens to hold. It would have been green
 *     throughout the entire period the bug existed. A check that is structurally unable to reach the
 *     failure is not a check, and this repo has shipped that shape before.
 *
 *     So the depth assumption is attacked directly instead: `findPackageDir` takes `webRoot` as a
 *     PARAMETER, and this test hands it a temp directory that has no `node_modules` anywhere above
 *     it. Under the old implementation both candidates miss and the answer is null — in the main
 *     clone, on CI, everywhere. Under the fixed one, `createRequire` resolves upward from the
 *     script's own location and finds the real package regardless of what `webRoot` says.
 *
 *     That is what makes this fail on a regression rather than on a checkout.
 *
 * WHY THIS FILE IS IN `src/tooling/` AND NOT `src/build/`
 *     It was written in `src/build/` first. `.gitignore` line 9 is `build/`, which matches a
 *     directory of that name **at any depth**, so the file was ignored. Vitest collected it off disk
 *     and reported 110 passing files locally; `git status` never mentioned it, and CI — which only
 *     ever sees the archive — would have run 109. A test that passes on your machine and does not
 *     exist on the runner is worse than no test, because the green is real and the coverage is not.
 *     The repo has been bitten by the archive-vs-disk distinction before, with `samples/*.ifc`.
 *     `git check-ignore -v <path>` answers this in one command; `ls` never will.
 */

// process.cwd() is apps/web under vitest (see roadmap-directions §5). Resolved from cwd rather than
// import.meta.url because the suite runs under happy-dom, where import.meta.url has no file: scheme.
const SCRIPTS = join(process.cwd(), "scripts");

type WasmSources = {
  findPackageDir: (name: string, webRoot: string, requireFrom?: string) => string | null;
};

/** Dynamic import so TypeScript does not need a declaration for the .mjs build script. */
async function load(): Promise<WasmSources> {
  return (await import(
    /* @vite-ignore */ pathToFileURL(join(SCRIPTS, "wasmSources.mjs")).href
  )) as WasmSources;
}

describe("the build's WASM package resolution", () => {
  it("finds web-ifc and laz-perf at all — otherwise every assertion below is vacuous", async () => {
    const { findPackageDir } = await load();
    for (const name of ["web-ifc", "laz-perf"]) {
      const dir = findPackageDir(name, process.cwd());
      expect(dir, `${name} did not resolve; the viewer cannot be built offline without it`).toBeTruthy();
      expect(existsSync(dir as string)).toBe(true);
    }
  });

  it("copies the exact files the offline viewer needs", async () => {
    // Named, not counted. The non-negotiable is that the viewer runs fully offline with local WASM,
    // so a missing binary here is a runtime CDN fetch or a dead viewer, not a slow build.
    const { findPackageDir } = await load();
    const webIfc = findPackageDir("web-ifc", process.cwd()) as string;
    expect(existsSync(join(webIfc, "web-ifc.wasm")), "web-ifc.wasm missing").toBe(true);

    const laz = findPackageDir("laz-perf", process.cwd()) as string;
    expect(existsSync(join(laz, "lib", "laz-perf.wasm")), "laz-perf.wasm missing").toBe(true);
  });

  it("resolves without depending on where node_modules sits relative to webRoot", async () => {
    // THE REGRESSION GUARD. This temp path has no node_modules at any ancestor, so both of the old
    // relative candidates are guaranteed to miss. Passing here means resolution is anchored to the
    // module's own location (upward lookup) rather than to a counted number of `..` segments.
    const { findPackageDir } = await load();
    const nowhere = join(tmpdir(), "massing-wasm-resolve-probe");
    expect(existsSync(join(nowhere, "node_modules"))).toBe(false);

    for (const name of ["web-ifc", "laz-perf"]) {
      const dir = findPackageDir(name, nowhere);
      expect(
        dir,
        `${name} resolved only via a webRoot-relative guess — the worktree build is broken again`,
      ).toBeTruthy();
      // And it must be a real directory, not a plausible string assembled from the fake root.
      expect(existsSync(dir as string)).toBe(true);
      expect(dir as string).not.toContain(nowhere);
    }
  });

  it("is itself in the archive CI runs from, not merely on this disk", async () => {
    // The generalisation of why this file moved out of src/build/. Vitest collects from DISK; CI
    // collects from the ARCHIVE. A test in an ignored directory passes locally and does not exist on
    // the runner. This asserts the whole suite is tracked, so the next person who adds a test under
    // a conveniently-named folder (`build/`, `dist/`, `tmp/` — all in .gitignore) is told at once
    // rather than believing a green that never ran.
    // Ask git for the whole of src/ and filter HERE, rather than handing git a `**` pathspec.
    // Git's default pathspec is not the same glob as Node's: `*` matches `/` too, so
    // `src/**/*.test.ts` requires an intermediate directory and silently misses a test sitting
    // directly in `src/`. The first draft did exactly that and reported the tracked, unmodified
    // `src/no-import-cycles.test.ts` as unshipped — a false positive produced by using two
    // different glob dialects for the two halves of one comparison. One reader defines the
    // pattern; the other only supplies its side of the set.
    const { execFileSync } = await import("node:child_process");
    const tracked = new Set(
      execFileSync("git", ["ls-files", "src/"], { cwd: process.cwd(), encoding: "utf8" })
        .split("\n").map((s) => s.trim()).filter((p) => p.endsWith(".test.ts")),
    );
    expect(tracked.size, "git ls-files returned nothing — this check would pass vacuously").toBeGreaterThan(50);

    const { globSync } = await import("node:fs");
    const onDisk = globSync("src/**/*.test.ts", { cwd: process.cwd() })
      .map((p: string) => p.split("\\").join("/"))
      .filter((p) => !p.includes("/vendor/"));   // vendored suites are excluded from the run itself

    const untracked = onDisk.filter((p) => !tracked.has(p));
    expect(untracked, `test files vitest runs but git does not ship: ${untracked.join(", ")}`).toEqual([]);
  });

  it("keeps copy-wasm.mjs wired to the shared resolver", async () => {
    // The resolver is only load-bearing if the build script actually calls it. Without this, someone
    // could reintroduce the inline candidates and every assertion above would still pass — the same
    // "engine exists, nothing calls it" gap the directions warn about.
    const src = await import("node:fs").then((fs) =>
      fs.readFileSync(join(SCRIPTS, "copy-wasm.mjs"), "utf8"),
    );
    expect(src).toContain("findPackageDir");
    expect(
      src.includes(`"..", "..", "node_modules"`),
      "copy-wasm.mjs has a hard-coded ../../node_modules candidate again",
    ).toBe(false);
  });
});
