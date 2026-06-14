import * as OBC from "@thatopen/components";

/** ModelIdMap = Record<modelId, Set<localId>>. Small helpers for building selection sets
 *  that the Hider / Highlighter / Classifier consume. */
export type ModelIdMap = OBC.ModelIdMap;

export function single(modelId: string, localId: number): ModelIdMap {
  return { [modelId]: new Set([localId]) };
}

export function fromLocalIds(modelId: string, localIds: Iterable<number>): ModelIdMap {
  return { [modelId]: new Set(localIds) };
}

/** Merge several maps into one (union per model). */
export function merge(...maps: ModelIdMap[]): ModelIdMap {
  const out: Record<string, Set<number>> = {};
  for (const m of maps) {
    for (const [model, ids] of Object.entries(m)) {
      out[model] ??= new Set();
      ids.forEach((id) => out[model].add(id));
    }
  }
  return out;
}
