import * as OBC from "@thatopen/components";

import { modelIdMapFromRefs, resolveGuids, type ResolveOutcome } from "../kernel/elementRef";
import type { ModelIdMap } from "./modelIds";

/** Build ModelIdMaps from API/IFC facets (GUIDs, IFC class) across all loaded models. */
export class SelectionSets {
  private fragments: OBC.FragmentsManager;

  constructor(components: OBC.Components) {
    this.fragments = components.get(OBC.FragmentsManager);
  }

  /**
   * Resolve GlobalIds and report what did NOT resolve (KERNEL-ADOPT ①).
   *
   * Until v0.3.713 this only returned the map, dropping any GlobalId that matched nothing — so
   * asking for ten elements with three missing gave a selection of seven and said nothing. Callers
   * that care whether they got everything read `complete`/`unresolved`; the identity rules live in
   * `kernel/elementRef`, on the vendored `ElementRef` contract.
   */
  async resolve(guids: string[]): Promise<ResolveOutcome> {
    return resolveGuids(guids, this.fragments.list);
  }

  /** Resolve a set of IFC GlobalIds into a ModelIdMap (GUIDs are the stable key). */
  async fromGuids(guids: string[]): Promise<ModelIdMap> {
    return modelIdMapFromRefs((await this.resolve(guids)).refs);
  }

  /** Select all items of one or more IFC classes (e.g. /IfcWall/). */
  async fromCategories(categories: RegExp[]): Promise<ModelIdMap> {
    const out: Record<string, Set<number>> = {};
    for (const [modelId, model] of this.fragments.list) {
      const result = await model.getItemsOfCategories(categories);
      const ids = Object.values(result).flat() as number[];
      if (ids.length) out[modelId] = new Set(ids);
    }
    return out;
  }
}
