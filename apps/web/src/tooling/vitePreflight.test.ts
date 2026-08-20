import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The Vite preflight must stay wired into every build entry point.
 *
 * A build with the wrong Vite does not fail — it SUCCEEDS and is wrong. `apps/web/package.json`
 * pins vite 8.1.5, installed nested at `apps/web/node_modules/vite` because the root already holds
 * 6.4.3 (hoisted for `vite-plugin-pwa` and `vitest`, which need ^6). A git worktree has no
 * `apps/web/node_modules`, resolves the root's 6, and Vite 6 is rollup-based: it does not know
 * `build.rolldownOptions.advancedChunks`, so the vendor split silently stops splitting and the eager
 * shell goes from 334 KB to 6,581 KB. Measured, same commit, same command.
 *
 * `scripts/check-vite-version.mjs` refuses that build. **A gate is only load-bearing if something
 * calls it**, and a prebuild hook is one careless edit from dropping it — the same "engine exists,
 * nothing calls it" gap the directions warn about, which is why this asserts the wiring rather than
 * trusting it.
 *
 * `predev` is still copy-wasm only (no version gate) — a wrong Vite on `npm run dev` is slower to
 * notice, but `dev` itself now goes through `run-vite.mjs` so a worktree no longer silently gets 6.x.
 */

// process.cwd() is apps/web under vitest.
const PKG = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8")) as {
  scripts: Record<string, string>;
};

/** Every hook that guards a build ARTEFACT, as opposed to a dev server. */
const BUILD_HOOKS = ["prebuild", "prebuild:desktop", "prebuild:mobile"];

describe("the vite preflight is wired into the build", () => {
  it("covers every build hook that exists — the list cannot go stale silently", () => {
    // If someone adds `build:foo`, its `prebuild:foo` must be considered rather than quietly
    // uncovered. Deriving the population from package.json instead of hard-coding it is what stops
    // this test's own list drifting away from the manifest it is about.
    const declared = Object.keys(PKG.scripts).filter((k) => /^prebuild(:|$)/.test(k));
    expect(declared.sort(), "a prebuild hook exists that this test does not know about")
      .toEqual([...BUILD_HOOKS].sort());
  });

  for (const hook of BUILD_HOOKS) {
    it(`${hook} runs the preflight before anything else`, () => {
      const cmd = PKG.scripts[hook] ?? "";
      expect(cmd, `${hook} no longer calls check-vite-version.mjs`).toContain("check-vite-version.mjs");
      // Order matters: refusing costs ~1.5s, while copy-wasm writes binaries into public/ that a
      // refused build has no use for. Failing first is the difference between a fast clear answer
      // and a slow one with side effects.
      expect(
        cmd.indexOf("check-vite-version.mjs"),
        `${hook} runs copy-wasm before the preflight`,
      ).toBeLessThan(cmd.indexOf("copy-wasm.mjs"));
    });
  }

    it("still pins a vite version for the preflight to check against", () => {
    // The preflight reads this pin. If it ever disappears the script exits 1 with "declares no vite
    // dependency", which is correct but would read as a broken script rather than a missing pin.
    const pinned = (PKG as unknown as { devDependencies?: Record<string, string> })
      .devDependencies?.vite;
    expect(pinned, "apps/web/package.json no longer pins vite").toBeTruthy();
  });

  it("build artefacts invoke the pinned vite, not a bare name on PATH", () => {
    // Bare `vite` is how a worktree picked up Vite 6. run-vite.mjs is the same pin the preflight
    // checks. A script that still says `vite build` after this lands is the original defect.
    for (const k of ["build", "build:desktop", "build:mobile", "dev", "preview"]) {
      expect(PKG.scripts[k], `${k} no longer calls run-vite.mjs`).toContain("run-vite.mjs");
      expect(PKG.scripts[k], `${k} still has a bare vite token`).not.toMatch(/(^|[^\w/-])vite([^\w]|$)/);
    }
  });
});
