import * as THREE from "three";
import * as OBC from "@thatopen/components";
import type { World } from "../viewer/world";
import type { ApiClient, ModulePin, Topic, Viewpoint } from "../api/client";

/**
 * Pin / markup overlay (guide §7 + GC portal). Renders a screen-projected HTML marker for
 * every anchored record — BCF topics (RFIs/punch/clash) and GC module records (PCO/COR/…).
 * A pin is any record with a 3D anchor + element GUID(s); clicking it restores context.
 * Implemented as a projected DOM overlay (robust across engine versions).
 */
interface PinMarker { el: HTMLElement; point: THREE.Vector3; }

export class PinOverlay {
  private overlay: HTMLElement;
  private markers: PinMarker[] = [];

  constructor(
    _components: OBC.Components,
    private world: World,
    private api: ApiClient,
    private onRestore: (topic: Topic, viewpoint: Viewpoint | null) => void,
  ) {
    const container = this.world.renderer!.three.domElement.parentElement!;
    this.overlay = document.createElement("div");
    this.overlay.className = "pin-overlay";
    this.overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:5";
    container.appendChild(this.overlay);
    const tick = () => { this.update(); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  private addMarker(el: HTMLElement, point: THREE.Vector3) {
    el.style.position = "absolute";
    el.style.pointerEvents = "auto";
    el.style.transform = "translate(-50%, -100%)";
    this.overlay.appendChild(el);
    this.markers.push({ el, point });
  }

  /** Project each anchor to screen space and place its marker. Called every frame, but the actual
   *  reprojection + DOM writes are skipped unless the camera moved, the viewport resized, or the marker
   *  set changed — so a still scene with many pins costs almost nothing. */
  private _key = "";
  private update() {
    if (!this.markers.length) return;
    if (this.overlay.offsetParent === null) return;          // overlay hidden — nothing to place
    const cam = this.world.camera.three;
    const dom = this.world.renderer!.three.domElement;
    const w = dom.clientWidth, h = dom.clientHeight;
    const q = cam.quaternion, p = cam.position;
    const key = `${p.x.toFixed(3)},${p.y.toFixed(3)},${p.z.toFixed(3)},${q.x.toFixed(4)},${q.y.toFixed(4)},${q.z.toFixed(4)},${q.w.toFixed(4)},${w},${h},${this.markers.length}`;
    if (key === this._key) return;                           // camera + viewport + pins unchanged
    this._key = key;
    const v = new THREE.Vector3();
    for (const m of this.markers) {
      v.copy(m.point).project(cam);
      const behind = v.z > 1;
      m.el.style.display = behind ? "none" : "block";
      if (behind) continue;
      m.el.style.left = `${(v.x * 0.5 + 0.5) * w}px`;
      m.el.style.top = `${(-v.y * 0.5 + 0.5) * h}px`;
    }
  }

  /** BCF topic pins. */
  async load(projectId: string) {
    this.clear();
    const pins = await this.api.pins(projectId);
    for (const topic of pins) {
      if (!topic.anchor) continue;
      const el = document.createElement("div");
      el.className = `pin pin-${topic.type}`;
      el.title = topic.title;
      el.textContent = { rfi: "?", punch: "!", clash: "✶", info: "i" }[topic.type] ?? "•";
      el.onclick = async () => {
        const vps = await this.api.viewpoints(projectId, topic.id);
        this.onRestore(topic, vps[0] ?? null);
      };
      this.addMarker(el, new THREE.Vector3(topic.anchor.x, topic.anchor.y, topic.anchor.z));
    }
    return pins.length;
  }

  /** GC module record pins (RFIs, PCOs, CORs, …). */
  async loadModulePins(projectId: string, onClick: (pin: ModulePin) => void) {
    const pins = await this.api.modulePins(projectId);
    for (const pin of pins) {
      const el = document.createElement("div");
      el.className = "pin pin-gc";
      el.title = `${pin.ref} · ${pin.module_name} · ${pin.status}`;
      el.textContent = pin.icon || "•";
      el.onclick = () => onClick(pin);
      this.addMarker(el, new THREE.Vector3(pin.anchor.x, pin.anchor.y, pin.anchor.z));
    }
    return pins.length;
  }

  clear() {
    for (const m of this.markers) m.el.remove();
    this.markers = [];
  }
}

/** Apply a viewpoint's camera to the world (the "restore viewpoint" half of M3). */
export function restoreCamera(world: World, vp: Viewpoint | null) {
  if (!vp?.camera?.position) return;
  const p = vp.camera.position;
  const t = vp.camera.target ?? { x: 0, y: 0, z: 0 };
  void world.camera.controls.setLookAt(p.x, p.y, p.z, t.x, t.y, t.z, true);
}
