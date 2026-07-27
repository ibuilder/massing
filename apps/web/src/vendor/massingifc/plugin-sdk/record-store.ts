import type { Slice } from "@massingifc/core-kernel";

export interface Identified {
  readonly id: string;
}

/**
 * A keyed collection held in a kernel state slice.
 *
 * Nearly every capability family owns one or more collections of records with the same access
 * pattern: get by id, list, filter, insert, patch, delete. Writing that nine times would be nine
 * chances to get the immutability wrong — and the state store's change detection depends on writes
 * producing new objects, so getting it wrong means subscribers silently stop updating.
 *
 * Reads are O(1) via an index rebuilt on write, because list-scanning showed up first on hot paths
 * like resolving markup anchors across thousands of records.
 */
export interface RecordStore<T extends Identified> {
  readonly slice: Slice<readonly T[]>;
  all(): readonly T[];
  get(id: string): T | undefined;
  has(id: string): boolean;
  add(record: T): T;
  addMany(records: readonly T[]): readonly T[];
  /** Shallow-merges `changes`. Returns `undefined` if the id is unknown. */
  update(id: string, changes: Partial<T>): T | undefined;
  /** Replaces wholesale. Returns `undefined` if the id is unknown. */
  replace(record: T): T | undefined;
  remove(id: string): boolean;
  removeWhere(predicate: (record: T) => boolean): number;
  query(predicate?: (record: T) => boolean): readonly T[];
  find(predicate: (record: T) => boolean): T | undefined;
  count(): number;
  clear(): void;
}

export interface RecordStoreHost {
  defineSlice<T>(name: string, initial: T): Slice<T>;
}

export function createRecordStore<T extends Identified>(
  host: RecordStoreHost,
  name: string,
  initial: readonly T[] = [],
): RecordStore<T> {
  const slice = host.defineSlice<readonly T[]>(name, initial);

  let index = new Map<string, T>();
  let indexedFor: readonly T[] | undefined;

  const ensureIndex = (): Map<string, T> => {
    const current = slice.get();
    // Rebuilt lazily and only when the array identity changed — restoring a persisted project
    // replaces the slice wholesale without going through `add`, so tracking writes is not enough.
    if (indexedFor !== current) {
      index = new Map(current.map((record) => [record.id, record]));
      indexedFor = current;
    }
    return index;
  };

  return {
    slice,
    all: () => slice.get(),
    get: (id) => ensureIndex().get(id),
    has: (id) => ensureIndex().has(id),

    add(record) {
      slice.update((current) => [...current, record]);
      return record;
    },

    addMany(records) {
      if (records.length === 0) return records;
      slice.update((current) => [...current, ...records]);
      return records;
    },

    update(id, changes) {
      if (!ensureIndex().has(id)) return undefined;
      let updated: T | undefined;
      slice.update((current) =>
        current.map((record) => {
          if (record.id !== id) return record;
          updated = { ...record, ...changes, id: record.id };
          return updated;
        }),
      );
      return updated;
    },

    replace(record) {
      if (!ensureIndex().has(record.id)) return undefined;
      slice.update((current) => current.map((item) => (item.id === record.id ? record : item)));
      return record;
    },

    remove(id) {
      if (!ensureIndex().has(id)) return false;
      slice.update((current) => current.filter((record) => record.id !== id));
      return true;
    },

    removeWhere(predicate) {
      const current = slice.get();
      const kept = current.filter((record) => !predicate(record));
      const removed = current.length - kept.length;
      if (removed > 0) slice.set(kept);
      return removed;
    },

    query: (predicate) => (predicate ? slice.get().filter(predicate) : slice.get()),
    find: (predicate) => slice.get().find(predicate),
    count: () => slice.get().length,

    clear() {
      if (slice.get().length > 0) slice.set([]);
    },
  };
}
