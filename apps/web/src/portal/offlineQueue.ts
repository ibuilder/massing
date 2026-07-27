/** Persistent offline upload queue (IndexedDB). Files attempted while offline are stored here as
 *  real File/Blob objects and survive a reload; the portal flushes them on reconnect / next launch.
 *  Falls back to a no-op-ish in-memory array when IndexedDB is unavailable (e.g. private mode). */

import { currentIdentity, ownedByMe } from "../api/identity";

export interface QueuedUpload {
  id?: number; pid: string; key: string; rid: string; files: File[]; ts: number;
  /** Who queued this. Absent on entries from before scoping — see `ownedByMe`. */
  owner?: string;
}

const DB_NAME = "aec-offline";
const STORE = "uploads";
let memFallback: QueuedUpload[] | null = null;   // used only if IndexedDB can't open

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
    (memFallback ??= []).push(rec);
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

export async function dequeue(id: number | undefined): Promise<void> {
  if (id == null) { if (memFallback) memFallback.shift(); return; }
  try {
    const s = await store("readwrite");
    await new Promise<void>((res) => { const r = s.delete(id); r.onsuccess = () => res(); r.onerror = () => res(); });
  } catch { /* ignore */ }
}

export async function queuedCountForRecord(rid: string): Promise<number> {
  return (await allQueued()).filter((q) => q.rid === rid).reduce((n, q) => n + q.files.length, 0);
}
