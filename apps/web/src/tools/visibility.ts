import * as OBC from "@thatopen/components";
import type { ModelIdMap } from "../viewer/modelIds";

/**
 * Isolate / hide / show-all (guide §6). Visibility states: visible, hidden.
 * Isolate = hide the complement. (X-ray/ghost is a Highlighter style — see colorize.ts.)
 */
export class VisibilityTool {
  private hider: OBC.Hider;

  constructor(components: OBC.Components) {
    this.hider = components.get(OBC.Hider);
  }

  isolate(items: ModelIdMap) {
    return this.hider.isolate(items);
  }

  hide(items: ModelIdMap) {
    return this.hider.set(false, items);
  }

  show(items: ModelIdMap) {
    return this.hider.set(true, items);
  }

  /** Reset everything to visible. */
  showAll() {
    return this.hider.set(true);
  }

  toggle(items: ModelIdMap) {
    return this.hider.toggle(items);
  }
}
