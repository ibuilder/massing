/**
 * Edit-in-place transform gizmo (P5). Direct-manipulation move: instead of typing an offset and
 * waiting for a republish, the modeler drags a Blender/Revit-style gizmo on the selected element.
 * A translucent amber ghost box (the element's bounding box) follows the drag for instant feedback;
 * on release the world-space delta is mapped to the GUID-stable `move_element` recipe and committed.
 *
 * World coordinates follow the viewer convention: (E, elevation, -N). The recipe wants (dx=E, dy=N,
 * dz=Z elevation), so the axis remap on commit is: dx = Δx, dy = -Δz, dz = Δy.
 */
import * as THREE from "three";
import { TransformControls } from "three/addons/controls/TransformControls.js";

const AMBER = 0xffb000;

export interface MoveDelta { dx: number; dy: number; dz: number }

export class TransformGizmo {
  private controls: TransformControls;
  private helper: THREE.Object3D;
  private anchor = new THREE.Object3D();
  private ghost: THREE.Mesh | null = null;
  private ghostEdges: THREE.LineSegments | null = null;
  private start = new THREE.Vector3();
  private ghostMat = new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.28, depthTest: false, side: THREE.DoubleSide });
  private edgeMat = new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.95, depthTest: false });

  /** Fired on drag release with the committed world-delta (only when non-trivial). */
  onCommit?: (delta: MoveDelta) => void;
  /** Fired continuously during a drag with a live delta (for a status readout). */
  onDrag?: (delta: MoveDelta) => void;

  constructor(
    camera: THREE.Camera,
    dom: HTMLElement,
    private scene: THREE.Scene,
    /** Toggle the orbit/pan camera controls off while dragging a handle. */
    private setCameraEnabled: (enabled: boolean) => void,
  ) {
    this.controls = new TransformControls(camera, dom);
    this.controls.setMode("translate");
    this.controls.setSpace("world");
    this.helper = this.controls.getHelper();
    scene.add(this.anchor);
    scene.add(this.helper);

    this.controls.addEventListener("dragging-changed", (e) => {
      const dragging = Boolean((e as unknown as { value: boolean }).value);
      this.setCameraEnabled(!dragging);
      if (dragging) this.start.copy(this.anchor.position);
      else this.commit();
    });
    this.controls.addEventListener("objectChange", () => {
      this.syncGhost();
      if (this.controls.dragging) this.onDrag?.(this.delta());
    });

    this.hide();
  }

  /** Whether a handle is currently being dragged (guards click-to-deselect). */
  get dragging(): boolean { return this.controls.dragging; }

  /** Snap increment in metres for translation (0 = free). */
  setSnap(inc: number): void {
    this.controls.translationSnap = inc > 0 ? inc : null;
  }

  /** Show the gizmo + ghost at a world-space bounding box. */
  attach(box: THREE.Box3): void {
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    this.anchor.position.copy(center);
    this.buildGhost(size);
    this.controls.attach(this.anchor);
    this.helper.visible = true;
    this.controls.enabled = true;
  }

  hide(): void {
    this.controls.detach();
    this.helper.visible = false;
    this.controls.enabled = false;
    this.disposeGhost();
  }

  dispose(): void {
    this.hide();
    this.scene.remove(this.anchor, this.helper);
    this.controls.dispose();
    this.ghostMat.dispose();
    this.edgeMat.dispose();
  }

  private delta(): MoveDelta {
    const d = this.anchor.position.clone().sub(this.start);
    return { dx: d.x, dy: -d.z, dz: d.y };   // (E, elevation, -N) → (dx=E, dy=N, dz=Z)
  }

  private commit(): void {
    const m = this.delta();
    if (Math.abs(m.dx) < 1e-4 && Math.abs(m.dy) < 1e-4 && Math.abs(m.dz) < 1e-4) return;
    this.onCommit?.(m);
  }

  private buildGhost(size: THREE.Vector3): void {
    this.disposeGhost();
    const g = new THREE.BoxGeometry(Math.max(size.x, 0.05), Math.max(size.y, 0.05), Math.max(size.z, 0.05));
    this.ghost = new THREE.Mesh(g, this.ghostMat);
    this.ghostEdges = new THREE.LineSegments(new THREE.EdgesGeometry(g), this.edgeMat);
    this.ghost.position.copy(this.anchor.position);
    this.ghostEdges.position.copy(this.anchor.position);
    this.scene.add(this.ghost, this.ghostEdges);
  }

  private syncGhost(): void {
    if (this.ghost) this.ghost.position.copy(this.anchor.position);
    if (this.ghostEdges) this.ghostEdges.position.copy(this.anchor.position);
  }

  private disposeGhost(): void {
    for (const o of [this.ghost, this.ghostEdges]) {
      if (!o) continue;
      this.scene.remove(o);
      (o as THREE.Mesh).geometry?.dispose?.();
    }
    this.ghost = this.ghostEdges = null;
  }
}
