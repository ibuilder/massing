/**
 * CACHE-JSON — stale-while-revalidate for module records, and the cached copy SAYS it is cached.
 *
 * Records are the larger aggregate in this product: 132 schema-driven modules × projects × history.
 * The binary half is already handled well — bundles, WASM and `.frag` geometry are `CacheFirst`
 * because they are content-hashed and immutable — but every panel refetched its records on every
 * visit, over a connection that on a site trailer is a phone tethered in a portacabin.
 *
 * The pattern is the standard one: serve what we have **immediately**, revalidate in the background,
 * update when the answer arrives.
 *
 * **The part this codebase cares about more than the speed.** A cached list is a claim about the
 * present made from the past. This session has been a long lesson in signals that measured something
 * other than what they claimed — an audit run against the wrong shell, a placeholder counted as
 * content, a limit that was silently four times its configured value. So a cached read here is never
 * returned bare: it comes back marked `fresh: false` with the age in seconds, and callers are
 * expected to show that. Stale-while-revalidate is fine. **Stale-and-silent is the failure mode.**
 *
 * Storage is IndexedDB rather than localStorage: record sets are large, localStorage is synchronous
 * and blocks the main thread, and its ~5 MB ceiling is not enough for a real project.
 */

const DB = "aec-records";
const STORE = "records";
const DB_VERSION = 1;

/** Older than this and we do not serve it at all — a day-old list is not "the present". */
export const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface Cached<T> {
  value: T;
  /** True when this came from the network on this call. */
  fresh: boolean;
  /** Seconds since the cached copy was stored; 0 when fresh. */
  ageSeconds: number;
}

interface Entry {
  key: string;
  value: unknown;
  storedAt: number;
}

function openDb(idb: IDBFactory): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    let req: IDBOpenDBRequest;
    try { req = idb.open(DB, DB_VERSION); } catch { resolve(null); return; }
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "key" });
    };
    req.onsuccess = () => resolve(req.result);
    // A browser that denies IndexedDB (private mode, policy) must degrade to "no cache", never to
    // an error the caller has to handle. Caching is an optimisation; losing it is not a failure.
    req.onerror = req.onblocked = () => resolve(null);
  });
}

export async function readEntry(key: string, idb?: IDBFactory): Promise<Entry | null> {
  const factory = idb ?? (globalThis as { indexedDB?: IDBFactory }).indexedDB;
  if (!factory) return null;
  const db = await openDb(factory);
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const req = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
      req.onsuccess = () => resolve((req.result as Entry) ?? null);
      req.onerror = () => resolve(null);
    } catch { resolve(null); }
  });
}

export async function writeEntry(key: string, value: unknown, now: number, idb?: IDBFactory): Promise<void> {
  const factory = idb ?? (globalThis as { indexedDB?: IDBFactory }).indexedDB;
  if (!factory) return;
  const db = await openDb(factory);
  if (!db) return;
  await new Promise<void>((resolve) => {
    try {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put({ key, value, storedAt: now } satisfies Entry);
      tx.oncomplete = tx.onerror = tx.onabort = () => resolve();
    } catch { resolve(); }
  });
}

/**
 * Serve the cached value immediately when there is one, and revalidate in the background.
 *
 * `onFresh` fires only when the network answer **differs** from what was served, so a caller can
 * re-render on a real change instead of on every revalidation — repainting a table that did not
 * change is a visible flicker for no information.
 *
 * A network failure with a cached copy present is not an error: the copy is returned, still marked
 * stale. A network failure with nothing cached propagates, because there is genuinely no answer.
 */
export async function swr<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts: { now?: () => number; idb?: IDBFactory; onFresh?: (value: T) => void; maxAgeMs?: number } = {},
): Promise<Cached<T>> {
  const now = opts.now ?? Date.now;
  const maxAge = opts.maxAgeMs ?? MAX_AGE_MS;
  const t = now();
  const entry = await readEntry(key, opts.idb);
  const usable = entry && t - entry.storedAt < maxAge ? entry : null;

  if (usable) {
    // Revalidate without blocking. A rejection here is deliberately swallowed: the caller already
    // has an answer, and an unhandled rejection would surface as an error for a request that was
    // only ever a background refresh.
    void (async () => {
      try {
        const next = await fetcher();
        await writeEntry(key, next, now(), opts.idb);
        if (opts.onFresh && JSON.stringify(next) !== JSON.stringify(usable.value)) opts.onFresh(next);
      } catch { /* keep the cached copy; the caller was already told it is stale */ }
    })();
    return {
      value: usable.value as T,
      fresh: false,
      ageSeconds: Math.max(0, Math.round((t - usable.storedAt) / 1000)),
    };
  }

  try {
    const value = await fetcher();
    await writeEntry(key, value, now(), opts.idb);
    return { value, fresh: true, ageSeconds: 0 };
  } catch (e) {
    // Nothing usable and the network failed. An expired entry is better than nothing HERE, because
    // the alternative is an empty screen — but it is returned with its true age, so the caller can
    // say "from yesterday" rather than presenting it as current.
    if (entry) {
      return {
        value: entry.value as T,
        fresh: false,
        ageSeconds: Math.max(0, Math.round((t - entry.storedAt) / 1000)),
      };
    }
    throw e;
  }
}

/** Human label for a cached result — what a panel shows so the copy is never silently stale. */
export function freshnessLabel(c: Cached<unknown>): string {
  if (c.fresh) return "";
  if (c.ageSeconds < 60) return "cached moments ago";
  if (c.ageSeconds < 3600) return `cached ${Math.round(c.ageSeconds / 60)} min ago`;
  if (c.ageSeconds < 86400) return `cached ${Math.round(c.ageSeconds / 3600)} h ago`;
  return `cached ${Math.round(c.ageSeconds / 86400)} d ago`;
}

/** Cache key for a module's record list. Project-scoped, so two projects never share an entry. */
export function recordsKey(pid: string, moduleKey: string): string {
  return `records:${pid}:${moduleKey}`;
}
