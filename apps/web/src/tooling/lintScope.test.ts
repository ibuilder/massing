import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * `npm run lint` must cover the build scripts, not only `src/`.
 *
 * **The only web source nobody linted was the source that gates the build.** `scripts/` sat in
 * `eslint.config.js`'s `ignores` until 2026-08-06, so `check-vite-version.mjs` (refuses a build on
 * the wrong Vite), `check-licences.mjs` (the licence allowlist), `bundle-budget.mjs` (the shell
 * budget and the vendor split), `copy-wasm.mjs` and `wasmSources.mjs` were all unlinted.
 *
 * It was not ignored because anyone decided build tooling should not be linted. Without a config
 * block turning off type-aware parsing, eslint does not skip those files — it **errors** with "was
 * not found by the project service", and adding the directory to `ignores` makes that stop. A
 * workaround for a parser error became a silent coverage hole.
 *
 * That is not theoretical: `no-misleading-character-class` — on by default via
 * `js.configs.recommended` — caught a real bug in `shell/roadmapSelfConsistent.test.ts` (`[◧🟡]`,
 * where 🟡 is U+1F7E1, so a non-`u` class splits the surrogate pair and matches either half alone).
 * The identical mistake one directory over in `scripts/` would have gone unremarked. Verified by
 * planting exactly that regex in `wasmSources.mjs`: **error, one problem, exit 1.**
 *
 * TWO things have to hold, and checking one is how this rots: the config must not ignore the
 * directory, AND the `lint` script must actually pass it to eslint. Removing the ignore alone
 * changes nothing, because the glob is `src/**` — a population defined in two places agrees only by
 * accident.
 */

const WEB = process.cwd();  // apps/web under vitest
const CONFIG = readFileSync(join(WEB, "eslint.config.js"), "utf8");
const PKG = JSON.parse(readFileSync(join(WEB, "package.json"), "utf8")) as { scripts: Record<string, string> };

describe("the lint population includes the build scripts", () => {
  it("does not ignore scripts/ in the eslint config", () => {
    // The ignores array is the first block; a `scripts/**` entry there removes the directory wholesale.
    const ignores = /\{\s*ignores:\s*\[([\s\S]*?)\]\s*\}/.exec(CONFIG)?.[1] ?? "";
    expect(ignores, "the ignores block was not found — this check is measuring nothing").not.toBe("");
    expect(ignores, "scripts/ is ignored again; the build-gate scripts are unlinted").not.toContain("scripts/**");
  });

  it("passes scripts/ to eslint from the lint script", () => {
    // The other half. `ignores` and the CLI glob are two independent definitions of one population.
    expect(PKG.scripts.lint, "npm run lint no longer globs scripts/").toContain("scripts/**");
  });

  it("still configures scripts/ without type-aware parsing, or the run errors instead of linting", () => {
    // The failure that produced the original ignore. If this block goes, eslint reports a parsing
    // error per file — which looks like a broken config and invites re-adding the ignore.
    expect(CONFIG).toContain("scripts/**/*.mjs");
    expect(CONFIG, "type-aware parsing must stay off for scripts/").toMatch(/projectService:\s*false/);
  });

  it("the scripts it claims to cover are actually there", async () => {
    // A population check: globbing a directory that has emptied would pass every assertion above.
    //
    // Floor is 3, the count on THIS branch. The first draft said 4, taken from build scripts I had
    // written in two other unmerged branches — a threshold from a tree this test never runs against.
    // Exactly the "a number from a different measurement is a threshold for a different question"
    // trap, committed while writing a test about population correctness. Raise it as scripts land.
    const { globSync } = await import("node:fs");
    const found = globSync("scripts/**/*.mjs", { cwd: WEB });
    expect(found.length, `only ${found.length} build scripts found — has the directory moved?`)
      .toBeGreaterThanOrEqual(3);
  });
});
