import * as THREE from "three";
import * as OBC from "@thatopen/components";
import { frameLoop } from "../viewer/raf";
import type { World } from "../viewer/world";
import type { ApiClient, ResolvedPin, Viewpoint } from "../api/client";

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
  private stopLoop: (() => void) | null = null;

  constructor(
    _components: OBC.Components,
    private world: World,
    private api: ApiClient,
    private onRestore: (pin: ResolvedPin, viewpoint: Viewpoint | null) => void,
  ) {
    const container = this.world.renderer!.three.domElement.parentElement!;
    this.overlay = document.createElement("div");
    this.overlay.className = "pin-overlay";
    this.overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:5";
    container.appendChild(this.overlay);
    // R23-RAF-LEAK: this is a SECOND permanent animation loop alongside the engine's own, and it had
    // no cancellation path at all — it survived viewer teardown and kept projecting pins for a world
    // nobody was looking at. Two guards, because either alone is insufficient:
    //   * `dispose()` for the ordinary case, where a caller tears the overlay down;
    //   * a detached-node check for the case that actually leaked, where the container is dropped and
    //     `dispose()` is never called — the loop then stops itself rather than running until reload.
    this.stopLoop = frameLoop(() => this.update(), () => this.overlay.isConnected);
  }

  /** Stop the projection loop and remove the overlay. Safe to call more than once. */
  dispose() {
    this.stopLoop?.();
    this.stopLoop = null;
    this.markers = [];
    this.overlay.remove();
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

  /**
   * PIN-ONE-CALL — every pin, in one request and one loop.
   *
   * This was two methods: `load()` for BCF topics via `api.pins()`, `loadModulePins()` for register
   * records via `api.modulePins()`, each building its own marker from its own row shape. Two shapes
   * for one concept is how the two drifted — and the glyph map lived HERE, so the overlay could only
   * draw a topic type it had a local branch for.
   *
   * `/pins/all` is the superset of both (asserted by `services/api/test_pin_anchor.py`) and now
   * carries `icon` and `source_name` for either kind, so the renderer branches on nothing: a pin's
   * appearance is data. The one remaining branch is the CLICK, which is genuinely different — a
   * topic restores a saved viewpoint, a record opens its register row.
   *
   * Returns both counts. "0 pins" and "pins failed to load" look identical on an empty overlay, and
   * only one of them is a problem.
   */
  async load(projectId: string, onRecordClick: (pin: ResolvedPin) => void) {
    this.clear();
    const env = await this.api.allPins(projectId);
    let topics = 0, records = 0;
    for (const pin of env.pins) {
      if (pin.x === null || pin.y === null || pin.z === null) continue;   // `unlocated` counts these
      const el = document.createElement("div");
      el.className = `pin pin-${pin.kind}`;
      el.title = `${pin.guid} · ${pin.source_name}${pin.status ? ` · ${pin.status}` : ""}`;
      el.textContent = pin.icon || "•";
      // **A marker click must not also reach the canvas.** The overlay sits over the viewport, and
      // `app.ts` has a container `click` listener that raycasts the scene and calls `selectMap(null)`
      // when nothing is hit — asynchronously, after a race with a 1.5 s timeout. A pin is a DOM
      // element, not scene geometry, so a click on one can easily raycast to nothing: the handler
      // below selects the element and the container handler then clears it, a few frames later.
      // *Two handlers that both answer a click are not two features, they are a race*, and the loser
      // here is the one the user aimed at. Raised in review on PR #577.
      if (pin.source === "topic") {
        topics++;
        el.onclick = async (ev) => {
          ev.stopPropagation();
          const vps = await this.api.viewpoints(projectId, pin.id);
          this.onRestore(pin, vps[0] ?? null);
        };
      } else {
        records++;
        el.onclick = (ev) => { ev.stopPropagation(); onRecordClick(pin); };
      }
      this.addMarker(el, new THREE.Vector3(pin.x, pin.y, pin.z));
    }
    return { topics, records };
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
