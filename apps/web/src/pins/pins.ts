import * as THREE from "three";
import * as OBC from "@thatopen/components";
import * as OBCF from "@thatopen/components-front";
import type { World } from "../viewer/world";
import type { ApiClient, Topic, Viewpoint } from "../api/client";

/**
 * Pin / markup overlay (guide §7). A pin is a Topic with a 3D anchor + element GUID(s).
 * Renders one marker per topic; clicking a pin restores its viewpoint (camera + components
 * + visibility) via the provided callback. Pins reference GUIDs, so they survive model
 * updates.
 */
export class PinOverlay {
  private markers: OBCF.Marker;
  private ids: string[] = [];

  constructor(
    components: OBC.Components,
    private world: World,
    private api: ApiClient,
    private onRestore: (topic: Topic, viewpoint: Viewpoint | null) => void,
  ) {
    this.markers = components.get(OBCF.Marker);
  }

  /** Load pins for a project and drop a marker for each. */
  async load(projectId: string) {
    this.clear();
    const pins = await this.api.pins(projectId);
    for (const topic of pins) {
      if (!topic.anchor) continue;
      const el = this.markerElement(topic);
      const point = new THREE.Vector3(topic.anchor.x, topic.anchor.y, topic.anchor.z);
      const id = this.markers.create(this.world, el, point);
      if (id) this.ids.push(id);
      el.onclick = async () => {
        const vps = await this.api.viewpoints(projectId, topic.id);
        this.onRestore(topic, vps[0] ?? null);
      };
    }
  }

  private markerElement(topic: Topic): HTMLElement {
    const el = document.createElement("div");
    el.className = `pin pin-${topic.type}`;
    el.title = topic.title;
    el.textContent = { rfi: "?", punch: "!", clash: "✶", info: "i" }[topic.type] ?? "•";
    return el;
  }

  clear() {
    for (const id of this.ids) this.markers.delete(id);
    this.ids = [];
  }
}

/** Apply a viewpoint's camera to the world (the "restore viewpoint" half of M3). */
export function restoreCamera(world: World, vp: Viewpoint | null) {
  if (!vp?.camera?.position) return;
  const p = vp.camera.position;
  const t = vp.camera.target ?? { x: 0, y: 0, z: 0 };
  world.camera.controls.setLookAt(p.x, p.y, p.z, t.x, t.y, t.z, true);
}
