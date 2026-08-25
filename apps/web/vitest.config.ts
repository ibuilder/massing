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
  },
});
