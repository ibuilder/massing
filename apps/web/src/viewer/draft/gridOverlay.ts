/**
 * Draft grid overlay — renders the project's grid axes (lines + bubble tags) and the storey level
 * datums in the 3D scene, and provides snap-to-grid-intersection for the Draft panel. Data comes from
 * `GET /projects/{id}/model/grid` (real IfcGrid or a grid derived from columns). Plan coordinates are
 * `[E, N]` (metres); world = `(E, elevation, -N)` — the viewer's E=x, N=-z convention.
 */
import * as THREE from "three";

export interface GridData {
  source: string;
  axes: { tag: string; dir: "u" | "v"; start: [number, number]; end: [number, number] }[];
  intersections: { x: number; y: number; label: string }[];
  bounds: { min: [number, number]; max: [number, number] } | null;
  note?: string;
}

function bubbleSprite(text: string): THREE.Sprite {
  const c = document.createElement("canvas"); c.width = 64; c.height = 64;
  const g = c.getContext("2d")!;
  g.fillStyle = "#1e88e5"; g.beginPath(); g.arc(32, 32, 28, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#fff"; g.font = "bold 30px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text.slice(0, 3), 32, 34);
  const tex = new THREE.CanvasTexture(c);
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  spr.scale.set(1.2, 1.2, 1.2);
  return spr;
}

export class GridOverlay {
  readonly group = new THREE.Group();
  private snaps: THREE.Vector2[] = [];   // plan [E, N] intersection points
  data: GridData | null = null;

  constructor(private scene: THREE.Scene) { this.group.name = "draft-grid"; this.group.visible = false; }

  /** Build the overlay at the given work-plane elevation (metres). */
  set(data: GridData, elevation = 0): void {
    this.clearMeshes();
    this.data = data;
    this.snaps = data.intersections.map((p) => new THREE.Vector2(p.x, p.y));
    const y = elevation;
    const lineMat = new THREE.LineBasicMaterial({ color: 0x5a9bd4, transparent: true, opacity: 0.7, depthTest: false });
    for (const ax of data.axes) {
      const [e1, n1] = ax.start; const [e2, n2] = ax.end;
      const geom = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(e1, y, -n1), new THREE.Vector3(e2, y, -n2),
      ]);
      this.group.add(new THREE.Line(geom, lineMat));
      // bubble at the "start" end (extended a touch past the axis for legibility)
      const dx = e1 - e2, dz = -n1 - (-n2);
      const len = Math.hypot(dx, dz) || 1;
      const b = bubbleSprite(ax.tag);
      b.position.set(e1 + (dx / len) * 0.9, y, -n1 + (dz / len) * 0.9);
      this.group.add(b);
    }
    if (!this.group.parent) this.scene.add(this.group);
  }

  /** Nearest grid intersection to a plan point [E,N] within `tol` metres, or null. */
  nearestSnap(E: number, N: number, tol = 0.6): [number, number] | null {
    let best: [number, number] | null = null; let bd = tol * tol;
    for (const s of this.snaps) {
      const d = (s.x - E) ** 2 + (s.y - N) ** 2;
      if (d < bd) { bd = d; best = [s.x, s.y]; }
    }
    return best;
  }

  get visible(): boolean { return this.group.visible; }
  set visible(v: boolean) { this.group.visible = v; }
  get hasData(): boolean { return !!this.data && this.data.axes.length > 0; }

  private clearMeshes(): void {
    for (const o of [...this.group.children]) {
      this.group.remove(o);
      const m = o as THREE.Mesh & THREE.Line & THREE.Sprite;
      m.geometry?.dispose?.();
      const mat = m.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
    }
  }

  dispose(): void { this.clearMeshes(); this.scene.remove(this.group); this.data = null; this.snaps = []; }
}
