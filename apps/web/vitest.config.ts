import { createRequire } from "node:module";
import path from "node:path";

import { searchForWorkspaceRoot } from "vite";
import { defineConfig } from "vitest/config";

import { vendorAlias } from "./vendorAlias.ts";

// From a git worktree (.claude/worktrees/*) node_modules resolves up into the MAIN clone's root,
// which sits outside Vite's default fs-allow scope — ?url asset imports (pdfjs worker) then fail
// with "Denied ID". Allow the hoisted node_modules wherever it actually resolved to.
const hoistedNodeModules = path.join(
  path.dirname(createRequire(import.meta.url).resolve("pdfjs-dist/package.json")),
  "..",
);

// Standalone from vite.config.ts so the PWA/coi plugins don't run under test. happy-dom gives
// the unit tests a lightweight DOM + localStorage without a real browser.
export default defineConfig({
  // Same alias the app build uses, from the same source — see vendorAlias.ts.
  resolve: { alias: { ...vendorAlias } },
  server: { fs: { allow: [searchForWorkspaceRoot(process.cwd()), hoistedNodeModules] } },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.ts"],
    globals: true,
    // 30s, against vitest's 5s default. The 5s was never a decision about THIS suite - it is the
    // out-of-the-box value, and this suite is not the shape it was chosen for: 53 of its files are
    // whole-tree gates that read every tracked source file (import cycles, href schemes, lane
    // tables, licence policy, doc citations), and ~30 of those sat on the default.
    //
    // Measured, not guessed. Run alone, these finish in well under a second. Run inside the full
    // 197-file suite they inflate 3-5x on worker contention alone - docComments 6,762 ms, svgPdf
    // 15,648 ms, no-import-cycles and hrefGuard both over 5,000 ms - and WHICH ones breach varies
    // run to run, because it depends on which worker gets starved. Patching them one at a time was
    // whack-a-mole: fixing three surfaced two more on the very next run.
    //
    // CI's runner has the headroom and has stayed green throughout, which is precisely the danger.
    // A suite that goes red on a developer's machine and green in CI trains people to ignore local
    // failures, and then a real one gets waved through with them.
    //
    // SIZED FROM THE WORST MEASURED CASE, after 30s was tried and still flaked. Under full-suite
    // contention on a 16-CPU box with nothing else running, roadmapStale.test.ts took 61,019 ms and
    // docComments.test.ts 52,074 ms - the same files that finish in under a second alone. Two
    // consecutive full runs disagreed with each other at 30s, which is the only reason this number
    // is 120s and not a tidier one.
    //
    // This budget guards against a HUNG test, not a slow one - no test here asserts its own speed.
    // The real inefficiency is upstream and NOT fixed here: 53 gate files each independently walk
    // and re-read the whole source tree. Sharing one cached read across them would make this
    // budget irrelevant, and is the change to make if this number ever needs raising again.
    testTimeout: 120_000,
  },
});
