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

/**
 * localStorage prefixes that are REGENERABLE CACHE and may be cleared.
 *
 * **This used to be the other way round — an allowlist of keys to KEEP — and every entry in it was
 * wrong.** `KEEP_KEYS` named `aec_token`, `aec_user`, `shell-spine`, `aec_persona`, `aec_ws` plus the
 * prefixes `prefs:` and `aec_pref_`. The session key is actually **`aec-token`** (hyphen, not
 * underscore) and the other six strings appear nowhere in this repository outside this file and its
 * test. `aec_user` matched exactly and has never been written by any commit.
 *
 * So `isKeeper` returned false for every key that can exist, and the button cleared the session, the
 * settings, the persona, the workspace, every portal preference, the saved selection sets, the studio
 * graph, and `aec-field-queue` — which holds **unsynced field captures**. It then reported *"Kept your
 * sign-in and preferences (0 settings)"*, a count that states the bug, under a Settings note reading
 * "Your sign-in and preferences are kept", and told the user to reload.
 *
 * **The direction of the default is the actual fix.** With an allowlist, a key nobody thought about —
 * or one that got renamed — is DESTROYED. With a denylist it is kept. Drift is inevitable; what is
 * chosen here is what drift costs. `clearCacheKeys.test.ts` enumerates every localStorage key literal
 * in `src/` so a new one cannot appear unclassified, and requires every prefix below to match a key
 * that really exists, which is the check that would have caught the original list on the day it rotted.
 *
 * **It is empty, and that is the honest answer rather than an oversight.** Every key this app writes
 * is a user choice or pending data; the caches this button exists for live in the Cache API,
 * IndexedDB and the service worker, all cleared above. An entry belongs here only when something
 * genuinely caches a regenerable server payload in localStorage.
 */
export const CACHE_KEY_PREFIXES: readonly string[] = [];

/** True for a key holding user state rather than cached payload — i.e. anything not named above. */
export function isKeeper(key: string): boolean {
  return !CACHE_KEY_PREFIXES.some((p) => key === p || key.startsWith(p));
}

/**
 * IndexedDB databases that hold PENDING WORK and must survive a clear.
 *
 * `aec-offline` is the upload queue: real `File`/`Blob` objects captured while offline and not yet
 * sent. Deleting it is not a cache eviction, it is losing the user's work — and unlike a preference
 * they cannot recreate it by clicking around again.
 */
export const KEEP_DATABASES: readonly string[] = ["aec-offline"];

export interface ClearResult {
  caches: number;
  databases: number;
  localKeys: number;
  serviceWorkers: number;
  kept: number;
  /** Databases skipped because they hold pending work — see `KEEP_DATABASES`. */
  keptDbs: number;
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
  let caches = 0, databases = 0, localKeys = 0, serviceWorkers = 0, kept = 0, keptDbs = 0;

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
        // Pending work, not cache — see KEEP_DATABASES. Skipped rather than deleted, and counted so
        // the summary can say it was kept instead of quietly omitting it.
        if (KEEP_DATABASES.includes(db.name)) { keptDbs++; continue; }
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
  // Say what was kept in the same breath as what went, and say it in countable terms. The previous
  // wording — "Kept your sign-in and preferences" with a number that was always 0 — was a reassurance
  // contradicted by its own figure, which is worse than either half alone.
  const keptParts = [`${kept} setting${kept === 1 ? "" : "s"}`];
  if (keptDbs) keptParts.push(`${keptDbs} queue${keptDbs === 1 ? "" : "s"} of unsent work`);
  let detail = `Cleared ${parts.join(", ")}. Kept your sign-in and ${keptParts.join(" and ")}.`;
  if (failed.length) detail += ` Could not clear: ${failed.join("; ")}.`;
  return { caches, databases, localKeys, serviceWorkers, kept, keptDbs, failed, detail };
}
