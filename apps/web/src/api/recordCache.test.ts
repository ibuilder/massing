import { describe, expect, it, vi } from "vitest";

import { freshnessLabel, recordsKey, swr } from "./recordCache";

/** An in-memory stand-in for IndexedDB — enough of the surface that `swr` exercises its real paths. */
function fakeIdb() {
  const rows = new Map<string, { key: string; value: unknown; storedAt: number }>();
  const store = {
    get: (k: string) => {
      const req: Record<string, unknown> = { result: rows.get(k) };
      queueMicrotask(() => (req.onsuccess as (() => void) | undefined)?.());
      return req;
    },
    put: (row: { key: string; value: unknown; storedAt: number }) => void rows.set(row.key, row),
  };
  const db = {
    objectStoreNames: { contains: () => true },
    createObjectStore: () => store,
    transaction: () => {
      const tx: Record<string, unknown> = { objectStore: () => store };
      queueMicrotask(() => (tx.oncomplete as (() => void) | undefined)?.());
      return tx;
    },
  };
  return {
    rows,
    factory: {
      open: () => {
        const req: Record<string, unknown> = { result: db };
        queueMicrotask(() => (req.onsuccess as (() => void) | undefined)?.());
        return req;
      },
    } as unknown as IDBFactory,
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("first load", () => {
  it("goes to the network and reports itself FRESH", async () => {
    const { factory } = fakeIdb();
    const r = await swr("k", async () => [1, 2], { idb: factory });
    expect(r.value).toEqual([1, 2]);
    expect(r.fresh).toBe(true);
    expect(r.ageSeconds).toBe(0);
  });

  it("a network failure with nothing cached PROPAGATES — there is genuinely no answer", async () => {
    const { factory } = fakeIdb();
    await expect(swr("k", async () => { throw new Error("offline"); }, { idb: factory }))
      .rejects.toThrow("offline");
  });
});

describe("the second load is where the point is", () => {
  it("serves the cached copy immediately and marks it NOT fresh, with its age", async () => {
    const { factory } = fakeIdb();
    let t = 1_000_000;
    await swr("k", async () => ["a"], { idb: factory, now: () => t });
    await flush();
    t += 120_000;                                     // two minutes later
    const fetcher = vi.fn(async () => ["a"]);
    const r = await swr("k", fetcher, { idb: factory, now: () => t });
    expect(r.fresh).toBe(false);
    expect(r.ageSeconds).toBe(120);
    expect(r.value).toEqual(["a"]);
  });

  it("onFresh fires only when the answer actually CHANGED", async () => {
    // Repainting a table that did not change is a visible flicker for no information.
    const { factory } = fakeIdb();
    let t = 1_000_000;
    await swr("k", async () => ["a"], { idb: factory, now: () => t });
    await flush();
    t += 1000;

    const unchanged = vi.fn();
    await swr("k", async () => ["a"], { idb: factory, now: () => t, onFresh: unchanged });
    await flush();
    expect(unchanged).not.toHaveBeenCalled();

    const changed = vi.fn();
    await swr("k", async () => ["a", "b"], { idb: factory, now: () => t, onFresh: changed });
    await flush();
    expect(changed).toHaveBeenCalledWith(["a", "b"]);
  });

  it("a failed revalidation keeps the cached copy and does NOT reject", async () => {
    // The caller already has an answer and was already told it is stale. Turning a background
    // refresh into a user-visible error would punish them for being offline.
    const { factory } = fakeIdb();
    let t = 1_000_000;
    await swr("k", async () => ["a"], { idb: factory, now: () => t });
    await flush();
    t += 1000;
    const r = await swr("k", async () => { throw new Error("offline"); }, { idb: factory, now: () => t });
    expect(r.value).toEqual(["a"]);
    expect(r.fresh).toBe(false);
    await flush();                                    // the background failure must not throw
  });
});

describe("staleness is never silent", () => {
  it("an entry past max age is not served as if current", async () => {
    const { factory } = fakeIdb();
    let t = 1_000_000;
    await swr("k", async () => ["old"], { idb: factory, now: () => t });
    await flush();
    t += 48 * 3600 * 1000;                            // two days
    const r = await swr("k", async () => ["new"], { idb: factory, now: () => t });
    expect(r.value).toEqual(["new"]);                 // refetched, not served from cache
    expect(r.fresh).toBe(true);
  });

  it("BUT an expired entry beats an empty screen when the network is also down — with its true age", async () => {
    const { factory } = fakeIdb();
    let t = 1_000_000;
    await swr("k", async () => ["old"], { idb: factory, now: () => t });
    await flush();
    t += 48 * 3600 * 1000;
    const r = await swr("k", async () => { throw new Error("offline"); }, { idb: factory, now: () => t });
    expect(r.value).toEqual(["old"]);
    expect(r.fresh).toBe(false);
    expect(r.ageSeconds).toBe(48 * 3600);             // honest about how old, not rounded to "recent"
  });

  it("every stale result produces a label a panel can show", () => {
    expect(freshnessLabel({ value: 0, fresh: true, ageSeconds: 0 })).toBe("");
    expect(freshnessLabel({ value: 0, fresh: false, ageSeconds: 30 })).toBe("cached moments ago");
    expect(freshnessLabel({ value: 0, fresh: false, ageSeconds: 600 })).toBe("cached 10 min ago");
    expect(freshnessLabel({ value: 0, fresh: false, ageSeconds: 7200 })).toBe("cached 2 h ago");
    expect(freshnessLabel({ value: 0, fresh: false, ageSeconds: 172800 })).toBe("cached 2 d ago");
  });
});

describe("degrading and scoping", () => {
  it("no IndexedDB at all means no cache, not an error", async () => {
    // Private mode, an old engine, a locked-down policy. Caching is an optimisation; losing it must
    // never be a failure the caller has to handle.
    const r = await swr("k", async () => ["x"], { idb: undefined as unknown as IDBFactory });
    expect(r.value).toEqual(["x"]);
    expect(r.fresh).toBe(true);
  });

  it("keys are project-scoped, so two projects never share an entry", () => {
    expect(recordsKey("p1", "rfi")).not.toBe(recordsKey("p2", "rfi"));
    expect(recordsKey("p1", "rfi")).not.toBe(recordsKey("p1", "submittal"));
  });
});
