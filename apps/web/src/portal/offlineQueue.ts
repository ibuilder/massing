/** Persistent offline upload queue (IndexedDB). Files attempted while offline are stored here as
 *  real File/Blob objects and survive a reload; the portal flushes them on reconnect / next launch.
 *  Falls back to a no-op-ish in-memory array when IndexedDB is unavailable (e.g. private mode). */

import { currentIdentity, ownedByMe } from "../api/identity";

export interface QueuedUpload {
  id?: number; pid: string; key: string; rid: string; files: File[]; ts: number;
  /** Who queued this. Absent on entries from before scoping — see `ownedByMe`. */
  owner?: string;
  /** Why the server refused this permanently. Set only for a rejection RETRYING CANNOT FIX, so the
   *  attachment notice can say what happened instead of promising an upload that will never occur.
   *  A marked entry is skipped by `flushUploads` and kept until a person discards it — these hold
   *  real `File` objects, so retrying one forever also costs the device the bytes forever. */
  rejected?: string;
}

const DB_NAME = "aec-offline";
const STORE = "uploads";
let memFallback: QueuedUpload[] | null = null;   // used only if IndexedDB can't open
//: Ids for the in-memory fallback. IndexedDB assigns its own via `autoIncrement`; the fallback had
//: none at all, and every operation that took an id therefore fell back to POSITION —
//: `dequeue(undefined)` did `memFallback.shift()`. That is not a weaker fallback, it is a wrong
//: one: flushing a queue where entry 0 fails transiently and entry 1 uploads would `shift()` away
//: entry 0, DISCARDING a file that never reached the server while leaving the one that did to be
//: uploaded a second time. The fallback is reached whenever `indexedDB` is UNAVAILABLE — storage
//: blocked by policy, a locked-down browser, an embedded webview. (Not private browsing: modern
//: private modes do provide IndexedDB, they just discard it when the session ends.)
let memSeq = 0;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function store(mode: IDBTransactionMode): Promise<IDBObjectStore> {
  const db = await openDb();
  return db.transaction(STORE, mode).objectStore(STORE);
}

export async function enqueueUpload(item: Omit<QueuedUpload, "id" | "ts" | "owner">): Promise<void> {
  const rec = { ...item, ts: Date.now(), owner: currentIdentity() };
  try {
    const s = await store("readwrite");
    await new Promise<void>((res, rej) => { const r = s.add(rec); r.onsuccess = () => res(); r.onerror = () => rej(r.error); });
  } catch {
    (memFallback ??= []).push({ ...rec, id: --memSeq });   // negative, so it can never collide with a real IndexedDB key
  }
}

/**
 * The uploads this session may see and flush: its own, plus untagged ones from before scoping.
 *
 * Another person's queued uploads are filtered out rather than deleted — they are unsent work, and
 * they stay on disk until that person signs back in. Flushing them here would post their files under
 * the wrong credentials, which is worse than merely showing them.
 */
export async function allQueued(): Promise<QueuedUpload[]> {
  const me = currentIdentity();
  return (await everyQueued()).filter((q) => ownedByMe(q.owner, me));
}

/** Every entry regardless of owner. Internal — callers want `allQueued`. */
async function everyQueued(): Promise<QueuedUpload[]> {
  try {
    const s = await store("readonly");
    return await new Promise((res, rej) => { const r = s.getAll(); r.onsuccess = () => res((r.result as QueuedUpload[]) || []); r.onerror = () => rej(r.error); });
  } catch {
    return memFallback ?? [];
  }
}

/**
 * Mark an entry permanently refused, so no later flush attempts it again.
 *
 * A separate call rather than a flag passed into `dequeue`, because the two are opposites: dequeue
 * means the bytes reached the server and may go, this means they never will and must STAY until
 * their owner decides. Silently dropping refused work is the one outcome neither queue may have.
 */
export async function markRejected(id: number | undefined, why: string): Promise<boolean> {
  if (id == null) return false;        // as in `dequeue`: no id means no entry, not "the first one"
  if (memFallback && id < 0) {
    const hit = memFallback.find((q) => q.id === id);
    if (hit) hit.rejected = why;
    return !!hit;
  }
  try {
    const s = await store("readwrite");
    // Read and write inside ONE request callback rather than `await`ing between them. Two reasons,
    // and only the second is about correctness of the report: an IndexedDB transaction commits once
    // control returns to the event loop with no pending request, so awaiting between `get` and
    // `put` can leave the `put` on a transaction that has already closed. And resolving on
    // `onerror` — which the first draft did, twice — reports a write that never happened as a
    // success, so `flush` would tell somebody N files were refused while the mark did not persist
    // and every one of them was about to be retried.
    return await new Promise<boolean>((res, rej) => {
      const r = s.get(id);
      r.onerror = () => rej(r.error);
      r.onsuccess = () => {
        const cur = r.result as QueuedUpload | undefined;
        if (!cur) return res(false);           // already gone — nothing to mark, and not an error
        const w = s.put({ ...cur, rejected: why });
        w.onerror = () => rej(w.error);
        w.onsuccess = () => res(true);
      };
    });
  } catch {
    const hit = memFallback?.find((q) => q.id === id);
    if (hit) hit.rejected = why;
    return !!hit;
  }
}

/**
 * Undo a refusal, so the entry is offered to the next flush again.
 *
 * The classifier decides "permanent" from a status code, and this PR's review found it getting one
 * wrong (401). **A verdict a person cannot overturn is a worse design than a verdict that is
 * occasionally wrong**, because the cost of being wrong is somebody's photo. This is the escape
 * hatch: the reason is shown, and Try again clears it.
 */
export async function clearRejection(id: number | undefined): Promise<void> {
  if (id == null) return;
  if (memFallback && id < 0) {
    const hit = memFallback.find((q) => q.id === id);
    if (hit) delete hit.rejected;
    return;
  }
  try {
    const s = await store("readwrite");
    await new Promise<void>((res, rej) => {
      const r = s.get(id);
      r.onerror = () => rej(r.error);
      r.onsuccess = () => {
        const cur = r.result as QueuedUpload | undefined;
        if (!cur) return res();
        const { rejected: _dropped, ...rest } = cur;
        const w = s.put(rest);
        w.onerror = () => rej(w.error);
        w.onsuccess = () => res();
      };
    });
  } catch {
    const hit = memFallback?.find((q) => q.id === id);
    if (hit) delete hit.rejected;
  }
}

export async function dequeue(id: number | undefined): Promise<void> {
  if (id == null) return;              // nothing addressable — never guess at a position
  if (memFallback && id < 0) {
    memFallback = memFallback.filter((q) => q.id !== id);
    return;
  }
  try {
    const s = await store("readwrite");
    await new Promise<void>((res) => { const r = s.delete(id); r.onsuccess = () => res(); r.onerror = () => res(); });
  } catch { /* ignore */ }
}

/** Files still worth retrying for one record. Refused entries are counted by `refusedForRecord`,
 *  never here — this number sits behind "will upload when back online", which must stay true. */
export async function queuedCountForRecord(rid: string): Promise<number> {
  return (await allQueued())
    .filter((q) => q.rid === rid && !q.rejected)
    .reduce((n, q) => n + q.files.length, 0);
}

/** The entries for one record the server has permanently refused, with their reasons. */
export async function refusedForRecord(rid: string): Promise<QueuedUpload[]> {
  return (await allQueued()).filter((q) => q.rid === rid && q.rejected);
}
