import * as OBC from "@thatopen/components";
import type { ModelIdMap } from "./modelIds";

/** Build ModelIdMaps from API/IFC facets (GUIDs, IFC class) across all loaded models. */
export class SelectionSets {
  private fragments: OBC.FragmentsManager;

  constructor(components: OBC.Components) {
    this.fragments = components.get(OBC.FragmentsManager);
  }

  /** Resolve a set of IFC GlobalIds into a ModelIdMap (GUIDs are the stable key). */
  async fromGuids(guids: string[]): Promise<ModelIdMap> {
    const out: Record<string, Set<number>> = {};
    for (const [modelId, model] of this.fragments.list) {
      const localIds = await model.getLocalIdsByGuids(guids);
      const found = localIds.filter((id): id is number => id !== null);
      if (found.length) out[modelId] = new Set(found);
    }
    return out;
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
