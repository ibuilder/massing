import { describe, expect, it } from "vitest";

import lockJson from "../../../../package-lock.json";
import tauriConf from "../../src-tauri/tauri.conf.json";
import pkg from "../../package.json";

/**
 * One version, stated in three places, asserted to agree.
 *
 * A release here bumps `apps/web/package.json` and `src-tauri/tauri.conf.json`, and
 * `package-lock.json` carries a *fourth* copy under `packages["apps/web"].version`. Nothing checked
 * that they matched, and they had not since **0.3.655** — the lock sat on a stale number for ~100
 * releases without a single failure.
 *
 * It survives that long because the failure is invisible from every direction that normally catches
 * things. `npm ci` compares **dependency edges**, not version fields, so it stays perfectly happy.
 * The build never reads the lock's version. And a regenerated lock silently re-syncs, so the drift
 * heals and re-opens depending on the order of two commands — which is exactly how v0.3.752
 * reintroduced it *in the commit that had just fixed it*: the lock was regenerated before the bump,
 * not after.
 *
 * The in-app version is read from `apps/web/package.json`, so a stale lock misreports what a
 * container was built from — which matters precisely when someone is trying to work out which build
 * a bug came from.
 */

const WEB = (pkg as { version: string }).version;

describe("the release version agrees with itself", () => {
  it("is a real version, not a placeholder", () => {
    // Guards the whole file: if this import resolved to something empty every check below would
    // pass vacuously by comparing undefined to undefined.
    expect(WEB).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("the desktop shell ships the same version as the web app", () => {
    expect((tauriConf as { version: string }).version).toBe(WEB);
  });

  it("the lockfile records the same version as the manifest", () => {
    // The one that had been wrong since 0.3.655. Regenerate the lock AFTER bumping, never before.
    const entry = (lockJson as { packages: Record<string, { version?: string } | undefined> })
      .packages["apps/web"];
    expect(entry, "packages['apps/web'] missing from package-lock.json").toBeTruthy();
    expect(entry?.version).toBe(WEB);
  });

  it("the lock still describes this workspace, so the check cannot pass by accident", () => {
    const lock = lockJson as { packages: Record<string, { name?: string }> };
    expect(Object.keys(lock.packages)).toContain("apps/web");
  });
});
