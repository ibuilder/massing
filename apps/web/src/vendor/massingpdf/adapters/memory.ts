/**
 * In-memory adapter. The default when no backend is configured, and the one the tests use.
 * Also the reference implementation of the contract — it is short enough to read in one sitting.
 */
import type { LoadResult, Mutation, StorageAdapter, StoreKey } from "./types";
import type { Annotation, Calibration, SheetMeta } from "../core/types";

const keyOf = (k: StoreKey): string => `${k.projectId ?? "-"}::${k.documentId}`;

interface Bucket {
  annots: Map<string, Annotation>;
  calibrations: Map<number, Calibration>;
  sheets: Map<number, SheetMeta>;
  listeners: Set<(r: LoadResult) => void>;
}

export class MemoryAdapter implements StorageAdapter {
  readonly id = "memory";
  private data = new Map<string, Bucket>();

  private bucket(key: StoreKey): Bucket {
    const k = keyOf(key);
    let b = this.data.get(k);
    if (!b) {
      b = { annots: new Map(), calibrations: new Map(), sheets: new Map(), listeners: new Set() };
      this.data.set(k, b);
    }
    return b;
  }

  private snapshot(b: Bucket): LoadResult {
    return {
      annotations: [...b.annots.values()],
      calibrations: [...b.calibrations.values()],
      sheets: [...b.sheets.values()],
    };
  }

  async load(key: StoreKey): Promise<LoadResult> {
    return this.snapshot(this.bucket(key));
  }

  async save(key: StoreKey, mutations: Mutation[]): Promise<void> {
    const b = this.bucket(key);
    for (const m of mutations) {
      switch (m.op) {
        case "upsert": b.annots.set(m.annot.id, m.annot); break;
        case "remove": b.annots.delete(m.id); break;
        case "calibration":
          if (m.calibration) b.calibrations.set(m.page, { ...m.calibration, page: m.page });
          else b.calibrations.delete(m.page);
          break;
        case "sheet": b.sheets.set(m.sheet.page, m.sheet); break;
      }
    }
    const snap = this.snapshot(b);
    for (const fn of b.listeners) fn(snap);
  }

  subscribe(key: StoreKey, onChange: (r: LoadResult) => void): () => void {
    const b = this.bucket(key);
    b.listeners.add(onChange);
    return () => { b.listeners.delete(onChange); };
  }

  online(): boolean { return true; }

  /** Test helper: wipe everything. */
  reset(): void { this.data.clear(); }
}
