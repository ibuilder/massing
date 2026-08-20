#!/usr/bin/env node
/**
 * Run the *pinned* Vite, not whichever `vite` is first on PATH / Node's walk.
 *
 * Bare `vite` from a git worktree resolves the repo-root Vite 6. This script asks
 * `findPinnedViteDir` (nested pin, then the main clone via git-common-dir) and
 * execs that CLI with this Node.
 */
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { findPinnedViteDir, viteCli } from "./vitePin.mjs";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = findPinnedViteDir(webRoot);
const cli = viteCli(dir);
if (!cli) {
  console.error(
    "[run-vite] could not locate the pinned vite. Run `npm install` at the repo root of the main clone.",
  );
  process.exit(1);
}

const child = spawn(process.execPath, [cli, ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: process.cwd(),
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
