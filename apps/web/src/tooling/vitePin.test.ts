import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The pinned Vite must be the nested apps/web copy, not the Vite 6 at the repo root.
 *
 * A worktree has no apps/web/node_modules. Node's walk finds 6.x. findPinnedViteDir looks in the
 * main clone via git-common-dir first, which is the only layout that makes `npm run build` in a
 * worktree the same bundler CI uses.
 */

const SCRIPTS = join(process.cwd(), "scripts");

type VitePin = {
  findPinnedViteDir: (webRoot: string) => string | null;
  gitMainRoot: (fromDir: string) => string | null;
  viteCli: (dir: string | null) => string | null;
};

async function load(): Promise<VitePin> {
  return (await import(
    /* @vite-ignore */ pathToFileURL(join(SCRIPTS, "vitePin.mjs")).href
  )) as VitePin;
}

describe("the pinned vite is the nested one", () => {
  it("resolves a vite at all — otherwise every assertion below is vacuous", async () => {
    const { findPinnedViteDir } = await load();
    const dir = findPinnedViteDir(process.cwd());
    expect(dir, "pinned vite did not resolve").toBeTruthy();
    expect(existsSync(join(dir as string, "package.json"))).toBe(true);
  });

  it("is the version apps/web pins, not a stray Vite 6", async () => {
    const { findPinnedViteDir } = await load();
    const dir = findPinnedViteDir(process.cwd()) as string;
    const found = JSON.parse(readFileSync(join(dir, "package.json"), "utf8")) as { version: string };
    const pinned = (JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8")) as {
      devDependencies: Record<string, string>;
    }).devDependencies.vite;
    expect(found.version).toBe(pinned);
    // Nested under apps/web when that copy exists (the layout that made worktrees pick 6);
    // otherwise the workspace-root copy, which on this image IS the pin.
    const nested = join(process.cwd(), "node_modules", "vite");
    if (existsSync(join(nested, "package.json"))) {
      expect(dir.replace(/\\/g, "/")).toMatch(/apps\/web\/node_modules\/vite$/);
    }
  });

  it("still finds a pin when asked from another directory inside the clone", async () => {
    const { gitMainRoot, findPinnedViteDir } = await load();
    const main = gitMainRoot(process.cwd());
    expect(main, "git-common-dir did not name a main clone").toBeTruthy();
    const dir = findPinnedViteDir(join(main as string, "docs"));
    expect(dir, "pin not found via git-common-dir from docs/").toBeTruthy();
    const found = JSON.parse(readFileSync(join(dir as string, "package.json"), "utf8")) as { version: string };
    const pinned = (JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8")) as {
      devDependencies: Record<string, string>;
    }).devDependencies.vite;
    expect(found.version).toBe(pinned);
  });

  it("exposes a CLI entry the runner can spawn", async () => {
    const { findPinnedViteDir, viteCli } = await load();
    const cli = viteCli(findPinnedViteDir(process.cwd()));
    expect(cli, "vite package has no bin").toBeTruthy();
    expect(existsSync(cli as string)).toBe(true);
  });
});
