import * as OBC from "@thatopen/components";
import type { World } from "../viewer/world";

/**
 * Section / clipping planes (guide §6). Add planes on any face by clicking, drag to move,
 * delete individually or clear all. A section can be captured into a viewpoint (Phase 4).
 */
export class SectionTool {
  readonly clipper: OBC.Clipper;

  constructor(components: OBC.Components, private world: World) {
    this.clipper = components.get(OBC.Clipper);
    this.clipper.enabled = false;
  }

  get enabled() {
    return this.clipper.enabled;
  }

  set enabled(v: boolean) {
    this.clipper.enabled = v;
  }

  /** Create a clip plane under the pointer (call from a dblclick handler when enabled). */
  createPlane() {
    return this.clipper.create(this.world);
  }

  /** Delete the plane under the pointer. */
  deletePlane() {
    return this.clipper.delete(this.world);
  }

  /** Capture current clip planes as serializable data for a viewpoint. */
  serialize() {
    return [...this.clipper.list.values()].map((p) => ({
      normal: { x: p.normal.x, y: p.normal.y, z: p.normal.z },
      point: { x: p.origin.x, y: p.origin.y, z: p.origin.z },
    }));
  }
}
