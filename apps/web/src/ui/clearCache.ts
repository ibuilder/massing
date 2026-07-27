/**
 * CACHE-CLEAR — the way out of a bad cache, from Settings.
 *
 * This app caches aggressively and deliberately: the engine bundles, the WASM and `.frag` geometry
 * are all `CacheFirst`, because they are content-hashed and immutable. That is right, and it is also
 * exactly why a way out has to exist. A cache that cannot be cleared turns any bad entry — a
 * half-written response, a service worker that updated badly, a stale offline queue — into "reinstall
 * the browser profile", which is not a thing anyone should have to be told.
 *
 * **What it deliberately does NOT touch:** the auth token and the user's own preferences. Clearing a
 * cache should not sign you out or reset your columns — those are not cache, they are state you
 * chose, and quietly destroying them would make people afraid of the button. A "clear everything"
 * that people are afraid to press is worse than no button, because they will not press it when they
 * need it.
 *
 * **What it reports:** counts, per store. "Cleared 3 caches, 2 databases" is checkable; "Done!" is a
 * claim. If a store fails it is named and the rest still run — a partial clear reported honestly beats
 * an all-or-nothing that aborts halfway and says nothing.
 */

/** localStorage keys that survive a clear, because they are the user's choices — not cached data. */
export const KEEP_KEYS: readonly string[] = [
  "aec_token",        // the session — clearing a cache must not sign you out
  "aec_user",
  "shell-spine",      // the shell they chose (v0.3.715); resetting it would look like a bug
  "aec_persona",      // "viewing as" role
  "aec_ws",           // workspace tab
];

/** True for a key holding user preference rather than cached payload. Prefix-matched. */
export function isKeeper(key: string): boolean {
  return KEEP_KEYS.some((k) => key === k || key.startsWith(`${k}:`))
    || key.startsWith("prefs:")            // per-module column choices, filters, collapse state
    || key.startsWith("aec_pref_");
}

export interface ClearResult {
  caches: number;
  databases: number;
  localKeys: number;
  serviceWorkers: number;
  kept: number;
  failed: string[];
  /** Human summary — counts, not reassurance. */
  detail: string;
}

interface ClearDeps {
  caches?: CacheStorage;
  indexedDB?: IDBFactory;
  localStorage?: Storage;
  serviceWorker?: ServiceWorkerContainer;
}

/**
 * Clear the local caches, keeping session and preferences.
 *
 * Every store is attempted even if an earlier one throws: a browser that denies one API (private
 * mode, an old engine, a locked-down policy) should not prevent the others being cleared. Failures
 * are collected and named rather than swallowed.
 */
export async function clearCaches(deps: ClearDeps = {}): Promise<ClearResult> {
  const g = globalThis as unknown as {
    caches?: CacheStorage; indexedDB?: IDBFactory; localStorage?: Storage;
    navigator?: { serviceWorker?: ServiceWorkerContainer };
  };
  const cacheApi = deps.caches ?? g.caches;
  const idb = deps.indexedDB ?? g.indexedDB;
  const ls = deps.localStorage ?? g.localStorage;
  const sw = deps.serviceWorker ?? g.navigator?.serviceWorker;

  const failed: string[] = [];
  let caches = 0, databases = 0, localKeys = 0, serviceWorkers = 0, kept = 0;

  // 1. Cache API — the bundles, WASM and .frag geometry.
  try {
    if (cacheApi) {
      const names = await cacheApi.keys();
      for (const n of names) if (await cacheApi.delete(n)) caches++;
    }
  } catch (e) { failed.push(`caches: ${(e as Error).message}`); }

  // 2. IndexedDB — the offline queue and any kernel-stored records.
  try {
    if (idb?.databases) {
      for (const db of await idb.databases()) {
        if (!db.name) continue;
        await new Promise<void>((resolve) => {
          const req = idb.deleteDatabase(db.name!);
          // `blocked` fires when another tab holds the database open. Resolve rather than hang: the
          // clear is best-effort per store, and a promise that never settles would freeze the button.
          req.onsuccess = req.onerror = req.onblocked = () => resolve();
        });
        databases++;
      }
    }
  } catch (e) { failed.push(`indexedDB: ${(e as Error).message}`); }

  // 3. localStorage — cached payloads only.
  try {
    if (ls) {
      const doomed: string[] = [];
      for (let i = 0; i < ls.length; i++) {
        const k = ls.key(i);
        if (k == null) continue;
        if (isKeeper(k)) kept++; else doomed.push(k);
      }
      for (const k of doomed) { ls.removeItem(k); localKeys++; }
    }
  } catch (e) { failed.push(`localStorage: ${(e as Error).message}`); }

  // 4. The service worker itself — last, because unregistering it first would leave the caches above
  //    orphaned rather than deleted, and a stale worker is the thing most likely to be the problem.
  try {
    if (sw?.getRegistrations) {
      for (const reg of await sw.getRegistrations()) if (await reg.unregister()) serviceWorkers++;
    }
  } catch (e) { failed.push(`serviceWorker: ${(e as Error).message}`); }

  const parts = [
    `${caches} cache${caches === 1 ? "" : "s"}`,
    `${databases} database${databases === 1 ? "" : "s"}`,
    `${localKeys} stored item${localKeys === 1 ? "" : "s"}`,
  ];
  if (serviceWorkers) parts.push(`${serviceWorkers} service worker${serviceWorkers === 1 ? "" : "s"}`);
  let detail = `Cleared ${parts.join(", ")}. Kept your sign-in and preferences (${kept} setting${kept === 1 ? "" : "s"}).`;
  if (failed.length) detail += ` Could not clear: ${failed.join("; ")}.`;
  return { caches, databases, localKeys, serviceWorkers, kept, failed, detail };
}
