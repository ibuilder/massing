/**
 * KERNEL-ADOPT ① — the identity boundary, made explicit.
 *
 * This is the first capability to sit on the vendored kernel, and it is deliberately the identity
 * one: every other capability that moves out of `app.ts` will cross this line, and if the line is
 * drawn wrong once it is drawn wrong everywhere above it.
 *
 * There are two kinds of element id in this app and they are not interchangeable:
 *
 * - **IFC GlobalId** — stable across re-conversion, the thing pins, clashes, 4D links, takeoff rows
 *   and field status all reference. Safe to persist. The kernel's `ElementRef` carries it.
 * - **Fragments local id** — a handle valid for *one load of one model in one session*. The renderer
 *   needs it (the Hider, Highlighter and Classifier all consume `ModelIdMap`). Re-converting the same
 *   IFC renumbers it, so storing one means "all the pins moved" after somebody re-issues a model.
 *
 * `ElementRef.localId` is typed as optional and documented "cache, never store" upstream, which is
 * the same rule this codebase has held since the beginning. This module is where the two vocabularies
 * meet, so the rule has one place to live rather than being re-remembered at each call site.
 *
 * **The defect this closes.** `SelectionSets.fromGuids` resolves GlobalIds to local ids and filters
 * out the nulls — so a GlobalId that is in no loaded model simply vanishes. Ask for ten elements with
 * three missing and you get a selection of seven, silently. "Not in any loaded model" and "found" are
 * reported identically, which is the unknown-versus-none failure this codebase keeps paying for: the
 * caller cannot tell a partial answer from a complete one, and the natural reading of a shorter
 * selection is that the model changed rather than that the lookup failed.
 */
import { sameElement, type ElementRef } from "@massingifc/project-schema";

import type { ModelIdMap } from "../viewer/modelIds";

export type { ElementRef };

/** What a GlobalId→element resolution actually produced, including what it could not. */
export interface ResolveOutcome {
  /** Elements found, each with the session-scoped `localId` attached for the renderer. */
  readonly refs: readonly ElementRef[];
  /** GlobalIds that matched nothing in any loaded model — the part `fromGuids` used to drop. */
  readonly unresolved: readonly string[];
  /** GlobalIds that resolved in more than one model. Federated projects make this normal, not an error. */
  readonly ambiguous: readonly string[];
  /** True only when every requested GlobalId was found. Callers that need certainty check this. */
  readonly complete: boolean;
}

/**
 * Turn a `ModelIdMap` back into refs, given a per-model reverse lookup.
 *
 * `toGuid` returns `null` for a local id the model cannot name — which happens for generated geometry
 * that never had a GlobalId. Those are reported, not dropped: an element the renderer can show but
 * nothing can reference is worth knowing about before somebody tries to pin it.
 */
export function refsFromModelIdMap(
  map: ModelIdMap,
  toGuid: (modelId: string, localId: number) => string | null,
): { refs: ElementRef[]; unnameable: { modelId: string; localId: number }[] } {
  const refs: ElementRef[] = [];
  const unnameable: { modelId: string; localId: number }[] = [];
  for (const [modelId, localIds] of Object.entries(map)) {
    for (const localId of localIds) {
      const globalId = toGuid(modelId, localId);
      if (globalId) refs.push({ modelId, globalId, localId });
      else unnameable.push({ modelId, localId });
    }
  }
  return { refs, unnameable };
}

/** The renderer's view of a set of refs. Drops any ref with no `localId` — it cannot be drawn. */
export function modelIdMapFromRefs(refs: readonly ElementRef[]): ModelIdMap {
  const out: Record<string, Set<number>> = {};
  for (const ref of refs) {
    if (typeof ref.localId !== "number") continue;
    (out[ref.modelId] ??= new Set<number>()).add(ref.localId);
  }
  return out;
}

/**
 * Resolve GlobalIds across every loaded model and **say what did not resolve**.
 *
 * `lookup` is the per-model `getLocalIdsByGuids` the Fragments API already provides, passed in rather
 * than imported so this module stays free of `@thatopen/*` and can be tested without a renderer.
 */
export async function resolveGuids(
  guids: readonly string[],
  models: Iterable<[string, { getLocalIdsByGuids(guids: string[]): Promise<(number | null)[]> }]>,
): Promise<ResolveOutcome> {
  const wanted = [...new Set(guids.filter(Boolean))];
  const found = new Map<string, ElementRef[]>();

  for (const [modelId, model] of models) {
    const localIds = await model.getLocalIdsByGuids([...wanted]);
    localIds.forEach((localId, i) => {
      if (localId === null || localId === undefined) return;
      const globalId = wanted[i]!;
      const list = found.get(globalId) ?? [];
      list.push({ modelId, globalId, localId });
      found.set(globalId, list);
    });
  }

  const refs = [...found.values()].flat();
  const unresolved = wanted.filter((g) => !found.has(g));
  const ambiguous = [...found.entries()].filter(([, l]) => l.length > 1).map(([g]) => g);
  return { refs, unresolved, ambiguous, complete: unresolved.length === 0 };
}

/**
 * Strip the session-scoped handle before persisting.
 *
 * Call this on the way to any store — API body, container document, localStorage. Keeping `localId`
 * on a stored ref is not a small mistake: it looks correct for the rest of the session and is only
 * discovered after a re-issue, by which point the wrong element is already attached.
 */
export function forStorage(ref: ElementRef): ElementRef {
  const { modelId, globalId } = ref;
  return { modelId, globalId };
}

/** True when the ref is safe to persist — carries a GlobalId and no transient handle. */
export function isStorable(ref: ElementRef): boolean {
  return Boolean(ref.globalId) && ref.localId === undefined;
}

export { sameElement };
