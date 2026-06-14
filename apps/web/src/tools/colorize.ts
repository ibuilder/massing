import * as THREE from "three";
import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
import type { ModelIdMap } from "../viewer/modelIds";

/**
 * Color / theming by data and ghost/x-ray (guide §6). Color elements by storey, status,
 * cost code, or schedule activity — the basis for 4D/5D overlays. Implemented with the
 * Fragments highlight API so it works directly on streamed geometry.
 */
export class ColorizeTool {
  private fragments: OBC.FragmentsManager;

  constructor(components: OBC.Components) {
    this.fragments = components.get(OBC.FragmentsManager);
  }

  private def(color: THREE.Color, opacity = 1): FRAGS.MaterialDefinition {
    return {
      color,
      opacity,
      transparent: opacity < 1,
      renderedFaces: FRAGS.RenderedFaces.TWO,
      preserveOriginalMaterial: false,
    };
  }

  /** Apply a solid color to a selection set. */
  color(items: ModelIdMap, color: THREE.ColorRepresentation) {
    return this.fragments.highlight(this.def(new THREE.Color(color)), items);
  }

  /** Ghost / x-ray a selection set (semi-transparent). */
  ghost(items: ModelIdMap, opacity = 0.15) {
    return this.fragments.highlight(this.def(new THREE.Color("#88aaff"), opacity), items);
  }

  reset(items?: ModelIdMap) {
    return this.fragments.resetHighlight(items);
  }
}
