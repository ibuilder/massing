import * as OBC from "@thatopen/components";
import type { ModelIdMap } from "../viewer/modelIds";
import { SelectionSets } from "../viewer/selectionSets";
import { VisibilityTool } from "./visibility";
import { ColorizeTool } from "./colorize";

/**
 * Layering (guide §6). Two layer concepts:
 *   1. IFC-driven layers (discipline / class / storey / system)
 *   2. user-defined custom layers
 * Each layer = a selection set with visibility, ghosting, and color override.
 */
export interface Layer {
  id: string;
  name: string;
  items: ModelIdMap;
  visible: boolean;
  ghosted: boolean;
  color?: string;
}

export class LayerManager {
  readonly layers = new Map<string, Layer>();
  private sets: SelectionSets;
  private visibility: VisibilityTool;
  private colorize: ColorizeTool;

  constructor(components: OBC.Components) {
    this.sets = new SelectionSets(components);
    this.visibility = new VisibilityTool(components);
    this.colorize = new ColorizeTool(components);
  }

  /** Create an IFC-class layer (e.g. all walls). */
  async addClassLayer(name: string, ifcClass: string): Promise<Layer> {
    const items = await this.sets.fromCategories([new RegExp(ifcClass)]);
    return this._add(name, items);
  }

  /** Create a layer from explicit element GUIDs (custom layer / discipline split). */
  async addGuidLayer(name: string, guids: string[]): Promise<Layer> {
    const items = await this.sets.fromGuids(guids);
    return this._add(name, items);
  }

  private _add(name: string, items: ModelIdMap): Layer {
    const layer: Layer = { id: crypto.randomUUID(), name, items, visible: true, ghosted: false };
    this.layers.set(layer.id, layer);
    return layer;
  }

  async setVisible(id: string, visible: boolean) {
    const layer = this.layers.get(id);
    if (!layer) return;
    layer.visible = visible;
    await this.visibility[visible ? "show" : "hide"](layer.items);
  }

  async setGhosted(id: string, ghosted: boolean) {
    const layer = this.layers.get(id);
    if (!layer) return;
    layer.ghosted = ghosted;
    if (ghosted) await this.colorize.ghost(layer.items);
    else await this.colorize.reset(layer.items);
  }

  async setColor(id: string, color: string) {
    const layer = this.layers.get(id);
    if (!layer) return;
    layer.color = color;
    await this.colorize.color(layer.items, color);
  }

  /** Isolate one layer (hide everything else). */
  isolate(id: string) {
    const layer = this.layers.get(id);
    if (layer) return this.visibility.isolate(layer.items);
  }
}
