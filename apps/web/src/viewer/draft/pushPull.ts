/**
 * R38-PUSHPULL — the hero gesture: select an element, drag its top handle, the extrusion deepens.
 *
 * IFC-safely: the gesture edits the element's RECIPE PARAMETER — `set_extrusion_depth`, which
 * rewrites `IfcExtrudedAreaSolid.Depth` in place, GUID-stable — never arbitrary mesh. A wall gets
 * taller, a slab thicker, a sketch mass rises; psets and every reference survive. The server
 * refuses non-extrusions (meshes/booleans), and the refusal surfaces through the normal recipe
 * error path, so the gesture needs no client-side allowlist that would drift from the truth.
 *
 * The ghost stretches FROM THE BASE: the bottom face stays exactly where the element stands and
 * only the top follows the handle — matching what the recipe will do, so the preview and the
 * committed result agree. World convention: (E, elevation, -N); the extrusion axis handled here is
 * vertical (elevation), which is what walls, columns, slabs and sketch masses extrude along.
 */
import * as THREE from "three";
import { TransformControls } from "three/addons/controls/TransformControls.js";

const AMBER = 0xffb000;

/** Pure: the new extrusion depth a drag commits. Null when the drag is a no-op (< 5 mm) so a
 *  click-and-release never authors an edit; clamped to `min` so a hard downward drag cannot zero or
 *  invert the solid (the server also refuses depth <= 0 — this keeps the GHOST honest too). */
export function pulledDepth(startDepth: number, dragDelta: number, min = 0.02): number | null {
  if (!Number.isFinite(startDepth) || startDepth <= 0) return null;
  if (!Number.isFinite(dragDelta) || Math.abs(dragDelta) < 0.005) return null;
  return Math.max(min, +(startDepth + dragDelta).toFixed(4));
}

/** Pure: base-anchored stretch — scale about the bottom face, not the centre. Returns the ghost's
 *  scaleY and centre elevation for a box of height h0 whose base sits at minY. The invariant the
 *  test pins: the base NEVER moves, whatever the delta. */
export function stretchTransform(h0: number, delta: number, minY: number, minH = 0.02):
    { scaleY: number; centerY: number } {
  const h = Math.max(minH, h0 + delta);
  return { scaleY: h / h0, centerY: minY + h / 2 };
}

export class PushPullGizmo {
  private controls: TransformControls;
  private helper: THREE.Object3D;
  private anchor = new THREE.Object3D();
  private ghost: THREE.Mesh | null = null;
  private ghostEdges: THREE.LineSegments | null = null;
  private startY = 0;
  private h0 = 0;
  private baseY = 0;
  private ghostMat = new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.28, depthTest: false, side: THREE.DoubleSide });
  private edgeMat = new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.95, depthTest: false });

  /** Fired on release with the depth to commit (already no-op-filtered and clamped). */
  onCommit?: (newDepth: number) => void;
  /** Fired continuously during a drag with the live depth (for a status readout). */
  onDrag?: (liveDepth: number) => void;

  constructor(
    camera: THREE.Camera,
    dom: HTMLElement,
    private scene: THREE.Scene,
    private setCameraEnabled: (enabled: boolean) => void,
  ) {
    this.controls = new TransformControls(camera, dom);
    this.controls.setMode("translate");
    // one handle, one direction: the extrusion axis. A full triad here would read as "move".
    this.controls.showX = false;
    this.controls.showZ = false;
    this.helper = this.controls.getHelper();
    this.scene.add(this.anchor);
    this.scene.add(this.helper);
    this.helper.visible = false;

    this.controls.addEventListener("dragging-changed", (e) => {
      const dragging = e.value as boolean;
      this.setCameraEnabled(!dragging);
      if (dragging) { this.startY = this.anchor.position.y; return; }
      const depth = pulledDepth(this.h0, this.anchor.position.y - this.startY);
      this.resetGhost();
      if (depth !== null) this.onCommit?.(depth);
    });
    this.controls.addEventListener("objectChange", () => {
      const delta = this.anchor.position.y - this.startY;
      const t = stretchTransform(this.h0, delta, this.baseY);
      if (this.ghost) { this.ghost.scale.y = t.scaleY; this.ghost.position.y = t.centerY; }
      if (this.ghostEdges) { this.ghostEdges.scale.y = t.scaleY; this.ghostEdges.position.y = t.centerY; }
      this.onDrag?.(Math.max(0.02, this.h0 + delta));
    });
  }

  /** Attach to a selection's world bounding box; its height IS the current vertical extrusion
   *  depth for the elements this gesture serves. Handle sits at the top-face centre. */
  attach(box: THREE.Box3): void {
    this.detachGhost();
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    this.h0 = size.y;
    this.baseY = box.min.y;
    if (this.h0 <= 0) return;
    this.anchor.position.set(center.x, box.max.y, center.z);
    this.controls.attach(this.anchor);
    this.helper.visible = true;

    const g = new THREE.BoxGeometry(size.x, size.y, size.z);
    this.ghost = new THREE.Mesh(g, this.ghostMat);
    this.ghost.position.copy(center);
    this.ghostEdges = new THREE.LineSegments(new THREE.EdgesGeometry(g), this.edgeMat);
    this.ghostEdges.position.copy(center);
    this.scene.add(this.ghost, this.ghostEdges);
  }

  get currentDepth(): number { return this.h0; }

  private resetGhost(): void {
    const t = stretchTransform(this.h0, 0, this.baseY);
    for (const o of [this.ghost, this.ghostEdges]) {
      if (o) { o.scale.y = t.scaleY; o.position.y = t.centerY; }
    }
    this.anchor.position.y = this.baseY + this.h0;
  }

  private detachGhost(): void {
    for (const o of [this.ghost, this.ghostEdges]) {
      if (o) { this.scene.remove(o); (o as THREE.Mesh).geometry?.dispose?.(); }
    }
    this.ghost = null;
    this.ghostEdges = null;
  }

  hide(): void {
    this.controls.detach();
    this.helper.visible = false;
    this.detachGhost();
  }
}
