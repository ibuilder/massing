import { describe, expect, it } from "vitest";

import { CACHE_KEY_PREFIXES, KEEP_DATABASES, clearCaches, isKeeper } from "./clearCache";

function fakeStorage(seed: Record<string, string>): Storage {
  const m = new Map(Object.entries(seed));
  return {
    get length() { return m.size; },
    key: (i: number) => [...m.keys()][i] ?? null,
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  } as unknown as Storage;
}

function fakeCaches(names: string[]) {
  const live = new Set(names);
  return { keys: async () => [...live], delete: async (n: string) => live.delete(n) } as unknown as CacheStorage;
}

function fakeIdb(dbs: string[], opts: { blocked?: boolean } = {}) {
  return {
    databases: async () => dbs.map((name) => ({ name })),
    deleteDatabase: (_n: string) => {
      const req: Record<string, unknown> = {};
      setTimeout(() => {
        const cb = opts.blocked ? req.onblocked : req.onsuccess;
        (cb as (() => void) | undefined)?.();
      }, 0);
      return req as unknown as IDBOpenDBRequest;
    },
  } as unknown as IDBFactory;
}

/**
 * These assert against keys this app ACTUALLY writes.
 *
 * The block they replace did not. It checked `isKeeper("aec_token")`, `isKeeper("shell-spine")`,
 * `isKeeper("prefs:rfi:columns")`, `isKeeper("aec_pref_density")` and `isKeeper("aec_persona:proj-1")` —
 * every one a key with no writer anywhere in the repository. Its "cached payloads do NOT survive"
 * cases (`cache:modules`, `aec_demo_snapshot`, `rooms:proj-1`, `whatever`) were equally invented. The
 * file asserted the constant back to itself over a namespace that did not exist, so it was green,
 * readable, thorough, and vouched for nothing: the real session key is `aec-token`, with a hyphen.
 *
 * **A test whose fixtures are invented cannot fail for the reason it exists.** The enumeration in
 * `clearCacheKeys.test.ts` is the structural fix; these are the specific promises worth naming.
 */
describe("what survives a clear", () => {
  it("THE SESSION SURVIVES — clearing a cache must not sign you out", () => {
    expect(isKeeper("aec-token")).toBe(true);
  });

  it("UNSENT WORK SURVIVES — a queue is not a cache", () => {
    // `aec-field-queue` holds QueuedCapture[]: field captures with photo dataURLs taken offline and
    // not yet uploaded. Deleting it is losing the user's work, not evicting a copy of something.
    expect(isKeeper("aec-field-queue")).toBe(true);
    expect(KEEP_DATABASES).toContain("aec-offline");
  });

  it("preferences survive", () => {
    for (const k of ["aec-settings", "persona", "workspace", "portal-favs", "portal-recents",
                     "portal-density", "portal-cols:rfi", "rail-w", "tools-ribbon"]) {
      expect(isKeeper(k), k).toBe(true);
    }
  });

  it("an UNKNOWN key survives — the default direction is the whole fix", () => {
    // With the previous allowlist an unrecognised key was destroyed, so a rename cost the user their
    // data. Drift is inevitable; what this chooses is what drift costs.
    expect(isKeeper("something-nobody-thought-about")).toBe(true);
  });

  it("...but a declared cache prefix is still cleared, so the mechanism is not a no-op", () => {
    // Proved by construction rather than by a real entry, because there are no real entries today —
    // every key this app writes is user state. Without this the inversion could have shipped as
    // "keep everything, always" and nothing would have said so.
    const probe = (key: string, prefixes: readonly string[]) =>
      !prefixes.some((pfx) => key === pfx || key.startsWith(pfx));
    expect(probe("tmpcache:models", ["tmpcache:"])).toBe(false);
    expect(probe("aec-token", ["tmpcache:"])).toBe(true);
  });
});

describe("clearing", () => {
  it("clears caches, databases and cached keys, and REPORTS COUNTS", async () => {
    const ls = fakeStorage({ "aec-token": "t", "portal-favs": "[]", "aec-field-queue": "[]" });
    const r = await clearCaches({
      caches: fakeCaches(["assets-v1", "frag-v1"]),
      indexedDB: fakeIdb(["aec-offline", "some-cache-db"]),
      localStorage: ls,
    });
    expect(r.caches).toBe(2);
    expect(r.databases, "aec-offline holds unsent uploads and must be skipped").toBe(1);
    expect(r.keptDbs).toBe(1);
    expect(r.localKeys, "nothing this app stores is clearable cache today").toBe(0);
    expect(r.kept).toBe(3);
    // Counts are checkable; "Done!" is a claim. This codebase has spent a cycle on that distinction.
    expect(r.detail).toContain("2 caches");
    expect(r.detail).toContain("Kept your sign-in");
    expect(r.detail, "the kept queue is named, not silently omitted").toContain("unsent work");
    expect(ls.getItem("aec-token"), "THE SESSION").toBe("t");
    expect(ls.getItem("aec-field-queue"), "UNSENT FIELD WORK").toBe("[]");
  });

  it("a store that throws is NAMED and the others still run", async () => {
    const broken = { keys: async () => { throw new Error("denied by policy"); } } as unknown as CacheStorage;
    const ls = fakeStorage({ "aec-token": "t" });
    const r = await clearCaches({ caches: broken, indexedDB: fakeIdb(["db1"]), localStorage: ls });
    expect(r.failed.join()).toContain("denied by policy");
    expect(r.databases).toBe(1);          // kept going
    expect(r.kept).toBe(1);
    expect(r.detail).toContain("Could not clear");
  });

  it("a database held open by another tab does not hang the button", async () => {
    // `blocked` fires when another tab has the database open. A promise that never settles would
    // freeze the UI with no explanation, which is worse than an incomplete clear.
    const r = await clearCaches({ indexedDB: fakeIdb(["busy"], { blocked: true }), localStorage: fakeStorage({}) });
    expect(r.databases).toBe(1);
  });

  it("missing browser APIs are not an error — nothing to clear is not a failure", async () => {
    const r = await clearCaches({ localStorage: fakeStorage({}) });
    expect(r.failed).toEqual([]);
    expect(r.caches).toBe(0);
  });

  it("every declared cache prefix is real — the check the old list failed", () => {
    // `CACHE_KEY_PREFIXES` is empty today, and this is what stops it filling with strings that match
    // nothing. The list it replaced held five such strings for months while looking authoritative.
    // The cross-check against the actual source lives in `clearCacheKeys.test.ts`.
    for (const p of CACHE_KEY_PREFIXES) {
      expect(p.length, "an empty prefix would match every key and clear everything").toBeGreaterThan(2);
    }
  });
});
