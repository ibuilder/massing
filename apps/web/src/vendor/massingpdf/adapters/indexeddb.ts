/**
 * IndexedDB adapter — the offline half of offline-first.
 *
 * Two stores: `annots` holds the markup records keyed by document, `queue` holds mutations that
 * haven't reached the server yet. A superintendent in a basement with no signal marks up a sheet,
 * closes the tab, comes back up, and the queue drains. That only works if the queue is durable
 * *before* the network is attempted, which is why writes land here first and sync second.
 */
import type { LoadResult, Mutation, StorageAdapter, StoreKey } from "./types";
import type { Annotation, Calibration, SheetMeta } from "../core/types";

const DB_NAME = "massing-pdf";
const DB_VERSION = 1;
const ANNOTS = "annots";
const META = "meta";
const QUEUE = "queue";

const keyOf = (k: StoreKey): string => `${k.projectId ?? "-"}::${k.documentId}`;

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("IndexedDB is unavailable in this environment")); return; }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(ANNOTS)) {
        const s = db.createObjectStore(ANNOTS, { keyPath: "pk" });
        s.createIndex("doc", "doc", { unique: false });
      }
      if (!db.objectStoreNames.contains(META)) db.createObjectStore(META, { keyPath: "doc" });
      if (!db.objectStoreNames.contains(QUEUE)) {
        const q = db.createObjectStore(QUEUE, { keyPath: "seq", autoIncrement: true });
        q.createIndex("doc", "doc", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("IndexedDB open failed"));
  });
}

const done = <T>(req: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("IndexedDB request failed"));
  });

const txDone = (tx: IDBTransaction): Promise<void> =>
  new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("IndexedDB transaction failed"));
    tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
  });

interface MetaRow { doc: string; calibrations: Calibration[]; sheets: SheetMeta[] }
interface QueueRow { seq?: number; doc: string; mutation: Mutation; at: number }

export class IndexedDbAdapter implements StorageAdapter {
  readonly id = "indexeddb";
  private dbPromise: Promise<IDBDatabase> | null = null;

  private db(): Promise<IDBDatabase> {
    this.dbPromise ??= open();
    return this.dbPromise;
  }

  async load(key: StoreKey): Promise<LoadResult> {
    const db = await this.db();
    const doc = keyOf(key);
    const tx = db.transaction([ANNOTS, META], "readonly");
    const rows = await done<{ pk: string; doc: string; annot: Annotation }[]>(
      tx.objectStore(ANNOTS).index("doc").getAll(doc) as IDBRequest<{ pk: string; doc: string; annot: Annotation }[]>,
    );
    const meta = await done<MetaRow | undefined>(tx.objectStore(META).get(doc) as IDBRequest<MetaRow | undefined>);
    return {
      annotations: rows.map((r) => r.annot),
      calibrations: meta?.calibrations ?? [],
      sheets: meta?.sheets ?? [],
    };
  }

  async save(key: StoreKey, mutations: Mutation[]): Promise<void> {
    if (!mutations.length) return;
    const db = await this.db();
    const doc = keyOf(key);
    const tx = db.transaction([ANNOTS, META], "readwrite");
    const annots = tx.objectStore(ANNOTS);
    const metaStore = tx.objectStore(META);

    // Read-modify-write the meta row once for the whole batch rather than per mutation.
    let meta: MetaRow | undefined;
    const metaTouched = mutations.some((m) => m.op === "calibration" || m.op === "sheet");
    if (metaTouched) {
      meta = await done<MetaRow | undefined>(metaStore.get(doc) as IDBRequest<MetaRow | undefined>)
        ?? { doc, calibrations: [], sheets: [] };
    }

    for (const m of mutations) {
      switch (m.op) {
        case "upsert":
          annots.put({ pk: `${doc}::${m.annot.id}`, doc, annot: m.annot });
          break;
        case "remove":
          annots.delete(`${doc}::${m.id}`);
          break;
        case "calibration": {
          if (!meta) break;
          meta.calibrations = meta.calibrations.filter((c) => c.page !== m.page);
          if (m.calibration) meta.calibrations.push({ ...m.calibration, page: m.page });
          break;
        }
        case "sheet": {
          if (!meta) break;
          meta.sheets = [...meta.sheets.filter((s) => s.page !== m.sheet.page), m.sheet];
          break;
        }
      }
    }
    if (meta) metaStore.put(meta);
    await txDone(tx);
  }

  /** Durably record mutations that still need to reach a server. */
  async enqueue(key: StoreKey, mutations: Mutation[]): Promise<void> {
    if (!mutations.length) return;
    const db = await this.db();
    const doc = keyOf(key);
    const tx = db.transaction(QUEUE, "readwrite");
    const q = tx.objectStore(QUEUE);
    for (const mutation of mutations) q.add({ doc, mutation, at: Date.now() } satisfies QueueRow);
    await txDone(tx);
  }

  /** Everything still pending for a document, oldest first. */
  async pending(key: StoreKey): Promise<{ seq: number; mutation: Mutation }[]> {
    const db = await this.db();
    const tx = db.transaction(QUEUE, "readonly");
    const rows = await done<QueueRow[]>(tx.objectStore(QUEUE).index("doc").getAll(keyOf(key)) as IDBRequest<QueueRow[]>);
    return rows
      .filter((r): r is QueueRow & { seq: number } => typeof r.seq === "number")
      .sort((a, b) => a.seq - b.seq)
      .map((r) => ({ seq: r.seq, mutation: r.mutation }));
  }

  /** Drop queue entries once they have been accepted by the server. */
  async ack(seqs: number[]): Promise<void> {
    if (!seqs.length) return;
    const db = await this.db();
    const tx = db.transaction(QUEUE, "readwrite");
    for (const seq of seqs) tx.objectStore(QUEUE).delete(seq);
    await txDone(tx);
  }

  async clear(key: StoreKey): Promise<void> {
    const db = await this.db();
    const doc = keyOf(key);
    const tx = db.transaction([ANNOTS, META, QUEUE], "readwrite");
    const idx = tx.objectStore(ANNOTS).index("doc");
    const keys = await done<IDBValidKey[]>(idx.getAllKeys(doc) as IDBRequest<IDBValidKey[]>);
    for (const k of keys) tx.objectStore(ANNOTS).delete(k);
    tx.objectStore(META).delete(doc);
    const qKeys = await done<IDBValidKey[]>(tx.objectStore(QUEUE).index("doc").getAllKeys(doc) as IDBRequest<IDBValidKey[]>);
    for (const k of qKeys) tx.objectStore(QUEUE).delete(k);
    await txDone(tx);
  }

  online(): boolean { return true; }
}

/** True when IndexedDB can be used at all — SSR, some private modes, and old WebViews cannot. */
export const indexedDbAvailable = (): boolean => typeof indexedDB !== "undefined";
