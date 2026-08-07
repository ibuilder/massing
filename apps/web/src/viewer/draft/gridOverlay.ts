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

/**
 * Draw one grid bubble. Returns null when there is no 2D context to draw into.
 *
 * The `!` that used to be on `getContext("2d")` asserted a context that is genuinely absent in some
 * environments — it is null under happy-dom, which is why this file had no tests at all. A null
 * context made `g.fillStyle = ...` throw a TypeError out of overlay construction, and per
 * `kernel/markupPlugin.ts` a throw on an overlay path takes the caller's remaining work with it.
 * A missing label is a far better outcome than a dead draft grid.
 */
function bubbleTexture(text: string): THREE.CanvasTexture | null {
  const c = document.createElement("canvas"); c.width = 64; c.height = 64;
  const g = c.getContext("2d");
  if (!g) return null;
  g.fillStyle = "#1e88e5"; g.beginPath(); g.arc(32, 32, 28, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#fff"; g.font = "bold 30px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text.slice(0, 3), 32, 34);
  return new THREE.CanvasTexture(c);
}

export class GridOverlay {
  readonly group = new THREE.Group();
  private snaps: THREE.Vector2[] = [];   // plan [E, N] intersection points
  data: GridData | null = null;
  /**
   * Bubble textures, cached by tag and owned by this overlay rather than by the sprites.
   *
   * `set()` runs on every work-plane move, and each run used to build a fresh canvas + texture per
   * axis. Two problems, and the second is the one that matters:
   *
   *  - CHURN: a 20-axis grid re-rasterised 20 canvases and uploaded 20 textures every time the
   *    elevation changed, to draw exactly the same bubbles.
   *  - A LEAK, measured: `clearMeshes` disposed geometry and material, and in three.js
   *    `Material.dispose()` does NOT dispose `material.map`. So every rebuild orphaned one GPU
   *    texture per axis — 8 axes, 8 textures, 8 leaked after a single rebuild when measured.
   *
   * Caching fixes both at once: identical tags reuse one texture, so a rebuild allocates nothing,
   * and ownership moves here where `dispose()` can actually release them.
   */
  private bubbles = new Map<string, THREE.CanvasTexture>();

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
      let tex = this.bubbles.get(ax.tag);
      if (tex === undefined) {
        tex = bubbleTexture(ax.tag) ?? undefined;
        if (tex) this.bubbles.set(ax.tag, tex);
      }
      if (tex) {
        const b = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
        b.scale.set(1.2, 1.2, 1.2);
        b.position.set(e1 + (dx / len) * 0.9, y, -n1 + (dz / len) * 0.9);
        this.group.add(b);
      }
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

  /**
   * Tear down the scene objects. Textures are deliberately NOT disposed here — they are cached and
   * reused by the next `set()`, and disposing one would leave the cache handing out a dead texture.
   * They are released in `dispose()`, which is where this overlay's lifetime actually ends.
   */
  private clearMeshes(): void {
    for (const o of [...this.group.children]) {
      this.group.remove(o);
      const m = o as THREE.Mesh & THREE.Line & THREE.Sprite;
      m.geometry?.dispose?.();
      const mat = m.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
    }
  }

  dispose(): void {
    this.clearMeshes();
    for (const t of this.bubbles.values()) t.dispose();
    this.bubbles.clear();
    this.scene.remove(this.group);
    this.data = null; this.snaps = [];
  }
}
