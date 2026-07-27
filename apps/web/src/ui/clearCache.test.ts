import { describe, expect, it } from "vitest";

import { KEEP_KEYS, clearCaches, isKeeper } from "./clearCache";

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

describe("what survives a clear", () => {
  it("the session survives — clearing a cache must not sign you out", () => {
    expect(isKeeper("aec_token")).toBe(true);
    expect(isKeeper("aec_user")).toBe(true);
  });

  it("the shell choice survives", () => {
    // Resetting someone to the other shell when they asked to clear a cache would read as a bug,
    // and it is the one choice this product asked them to make deliberately.
    expect(isKeeper("shell-spine")).toBe(true);
  });

  it("per-module preferences survive", () => {
    expect(isKeeper("prefs:rfi:columns")).toBe(true);
    expect(isKeeper("aec_pref_density")).toBe(true);
  });

  it("cached payloads do NOT survive", () => {
    for (const k of ["cache:modules", "aec_demo_snapshot", "rooms:proj-1", "whatever"]) {
      expect(isKeeper(k), k).toBe(false);
    }
  });

  it("a keeper's namespaced children survive too", () => {
    expect(isKeeper("aec_persona:proj-1")).toBe(true);
  });
});

describe("clearing", () => {
  it("clears caches, databases and cached keys, and REPORTS COUNTS", async () => {
    const ls = fakeStorage({ "aec_token": "t", "prefs:x": "1", "cache:a": "1", "cache:b": "2" });
    const r = await clearCaches({
      caches: fakeCaches(["assets-v1", "frag-v1"]),
      indexedDB: fakeIdb(["aec-offline"]),
      localStorage: ls,
    });
    expect(r.caches).toBe(2);
    expect(r.databases).toBe(1);
    expect(r.localKeys).toBe(2);
    expect(r.kept).toBe(2);
    // Counts are checkable; "Done!" is a claim. This codebase has spent a cycle on that distinction.
    expect(r.detail).toContain("2 caches");
    expect(r.detail).toContain("Kept your sign-in");
    expect(ls.getItem("aec_token")).toBe("t");
    expect(ls.getItem("cache:a")).toBeNull();
  });

  it("a store that throws is NAMED and the others still run", async () => {
    const broken = { keys: async () => { throw new Error("denied by policy"); } } as unknown as CacheStorage;
    const ls = fakeStorage({ "cache:a": "1" });
    const r = await clearCaches({ caches: broken, indexedDB: fakeIdb(["db1"]), localStorage: ls });
    expect(r.failed.join()).toContain("denied by policy");
    expect(r.databases).toBe(1);          // kept going
    expect(r.localKeys).toBe(1);
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

  it("keeps every declared KEEP_KEY, so the list is not decorative", async () => {
    const seed = Object.fromEntries(KEEP_KEYS.map((k) => [k, "v"]));
    const ls = fakeStorage({ ...seed, junk: "x" });
    const r = await clearCaches({ localStorage: ls });
    expect(r.kept).toBe(KEEP_KEYS.length);
    for (const k of KEEP_KEYS) expect(ls.getItem(k), k).toBe("v");
  });
});
