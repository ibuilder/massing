/**
 * Every tracked JavaScript file in this repository is read by some ESLint config.
 *
 * ## Why this exists
 *
 * It has now happened twice, in two different directories, for the same structural reason.
 *
 * On 2026-08-06 (PR #219) `apps/web/scripts/` was in `ignores`, so — in that PR's own words — **"the
 * only web source nobody linted was the source that gates the build"**: `check-vite-version.mjs`,
 * `check-licences.mjs`, `bundle-budget.mjs`. Its note is the part worth keeping: the directory was
 * ignored *"rather than a decision anyone made about linting build scripts"*. An accident of
 * configuration reads, from outside, exactly like a choice.
 *
 * On 2026-08-25 the same sentence was true one directory up. `apps/web/eslint.config.js` matches
 * `scripts/**‌/*.mjs` relative to **its own base path**, so it covers `apps/web/scripts/` and
 * *structurally cannot* reach the repository-root `scripts/` — a flat config cannot lint above its own
 * directory, and pointing it there fails with "was not found by the project service". So the root
 * `scripts/` was covered by nothing, and it holds `check-fragments-version.mjs`, the program CI runs
 * to gate the fragments/web-ifc pin and the shared Node base image.
 *
 * Enumerating the population then turned up three more: `services/converter/src/{cli,ifcToFrag,
 * rvtToIfc}.mjs` — the IFC→Fragments conversion named in the first non-negotiable of CLAUDE.md.
 *
 * **The fix for a recurring gap is not a third careful config; it is a check that fails.** A rule held
 * as prose — "new JS should be linted" — is what drifted twice.
 *
 * ## What is asserted, and how the first draft of this file got it wrong
 *
 * Coverage is **measured through ESLint's own config resolution**, not inferred from globs: each
 * tracked file is put to `isPathIgnored` and `calculateConfigForFile`, and counts as covered only if
 * it is not ignored AND resolves a config carrying at least one rule. ESLint 10 finds the governing
 * config by walking up from *the file*, so one instance answers for both trees — `apps/web/**`
 * resolves `apps/web/eslint.config.js`, everything else resolves the root `eslint.config.mjs`.
 *
 * **The first draft ran `eslint . --format json` and treated every path in the output as covered.
 * That draft passed its own mutation.** Removing `services/converter/src/**` from the root config —
 * reconstructing the exact defect this file was written for — left those three files linted by
 * nothing, and the test still reported green: ESLint emits a zero-message result for a file it merely
 * *walked past* without matching any `files` entry, so "appears in the output" and "had rules applied
 * to it" are different questions, and the draft asked the easier one.
 *
 * That is the same shape as everything this check is about — a measurement whose population quietly
 * includes the failure case — reproduced inside the very test written to catch it. A rule *count*
 * cannot be satisfied by a file ESLint declined to lint, so that is the question worth asking.
 * **The mutation run is the only thing that told the difference; the PASS lines were identical.**
 */
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const REPO = resolve(process.cwd(), "..", "..");

/** Tracked JS the repo deliberately does not lint, each for a reason written where it is excluded. */
const EXCLUDED = [
  /^apps\/web\/src\/vendor\//,      // third-party, vendored verbatim (MIT) — see VENDOR.md
  // coi-serviceworker v0.1.7 (Guido Zuidhof, MIT), vendored verbatim: the COOP/COEP shim that lets
  // web-ifc's multithreaded WASM use SharedArrayBuffer on GitHub Pages. Same reason as src/vendor/
  // and the same `ignores` entry (`public/**`) — third-party source is not ours to restyle.
  // **This entry was written because the check found the file**, not before: the first run of this
  // test reported it, which is the check doing its job on its own first execution.
  /^apps\/web\/public\//,
  /^apps\/web\/dist\//,
  /^apps\/web\/src-tauri\//,
  /\.config\.js$/,                  // *.config.js is in apps/web's ignores
];

const tracked = execFileSync("git", ["ls-files", "*.mjs", "*.js", "*.cjs"],
  { cwd: REPO, encoding: "utf8", maxBuffer: 1 << 26 })
  .split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  .filter((f) => !EXCLUDED.some((re) => re.test(f)));

describe("ESLint coverage", () => {
  it("has a non-empty population to check — otherwise every assertion here is vacuous", () => {
    expect(tracked.length, `tracked JS files found: ${tracked.join(", ")}`).toBeGreaterThanOrEqual(10);
  });

  it("spans both trees, so neither config is being checked alone", () => {
    // The population must actually reach the root-governed files AND the apps/web-governed ones.
    // Without this, a `git ls-files` glob that stopped matching one tree would leave the assertion
    // below true over the other tree alone — green, and blind to exactly one config.
    expect(tracked.some((f) => f.startsWith("apps/web/")), "no apps/web JS in the population").toBe(true);
    expect(tracked.some((f) => !f.startsWith("apps/web/")), "no root-tree JS in the population").toBe(true);
  });

  it("lints every tracked JavaScript file", async () => {
    const { ESLint } = await import("eslint");
    const eslint = new ESLint({ cwd: REPO });

    const results = await Promise.all(tracked.map(async (file) => {
      const abs = resolve(REPO, file);
      if (await eslint.isPathIgnored(abs)) return [file, 0] as const;
      const cfg = (await eslint.calculateConfigForFile(abs)) as { rules?: object } | null;
      return [file, Object.keys(cfg?.rules ?? {}).length] as const;
    }));

    const uncovered = results.filter(([, n]) => n === 0).map(([f]) => f);
    expect(uncovered, "these tracked JavaScript files are linted by no ESLint config — add them to "
      + "eslint.config.mjs at the repo root, or to apps/web's config").toEqual([]);
  }, 60_000);
});
