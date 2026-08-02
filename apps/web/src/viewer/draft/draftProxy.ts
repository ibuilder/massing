/**
 * Draft proxy layer (P6 + A29-LOCAL-PREVIEW) — the optimistic AND the honest side of drafting.
 *
 * The moment an element is placed, a lightweight amber proxy (box / line / polygon) is drawn where
 * it will land, so the modeler gets instant feedback instead of staring at the publish round-trip.
 *
 * A29's rule, now enforced here rather than stated in a ring: **a pending edit must look pending,
 * and a failed edit must stay visible.**
 *
 *   * The amber outline is the PENDING marker. It stays up even after the incremental one-element
 *     preview streams in — real-looking geometry with no marker would be indistinguishable from a
 *     committed element, which becomes a lie the moment the recipe fails. Amber over accurate
 *     geometry says exactly the truth: "this shape, not yet on the record."
 *   * On failure the marker turns RED and stays. The old behaviour cleared every trace and raised a
 *     toast, so the user knew something failed but not WHERE. A failed placement is information
 *     with a location; the next draft action clears it.
 *
 * World coordinates follow the viewer convention: (E, elevation, -N).
 */
import * as THREE from "three";

const AMBER = 0xffb000;
const RED = 0xe5484d;

export class DraftProxyLayer {
  readonly group = new THREE.Group();
  private lineMat = new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.9, depthTest: false });
  private faceMat = new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.25, depthTest: false, side: THREE.DoubleSide });
  private _failed = false;

  constructor(scene: THREE.Scene) { this.group.name = "draft-proxies"; scene.add(this.group); }

  /** A box proxy for point equipment (centre at [E, N], base at elevation z). */
  addBox(e: number, n: number, z: number, w = 0.4, h = 0.6, d = 0.4): void {
    const box = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), this.faceMat);
    box.position.set(e, z + h / 2, -n);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry), this.lineMat);
    edges.position.copy(box.position);
    this.group.add(box, edges);
  }

  /** A line proxy for a linear run (wall/beam/duct/pipe/rebar/railing). */
  addLine(e1: number, n1: number, e2: number, n2: number, z: number): void {
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(e1, z, -n1), new THREE.Vector3(e2, z, -n2)]);
    this.group.add(new THREE.Line(g, this.lineMat));
  }

  /** A closed polygon outline proxy for a slab/roof/covering. */
  addPoly(pts: [number, number][], z: number): void {
    if (pts.length < 2) return;
    const vs = pts.map(([e, n]) => new THREE.Vector3(e, z, -n));
    vs.push(vs[0]!); // safe: pts.length >= 2 checked above
    this.group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(vs), this.lineMat));
  }

  /** Build the right proxy from an authoring recipe's params (point / start+end / points).
   *  A new draft action is also what retires a previous FAILED marker — the red outline answers
   *  "where did it fail", and the user starting a fresh placement is the acknowledgement. */
  fromParams(p: Record<string, unknown>, z: number): void {
    if (this._failed) this.clear();
    const num = (v: unknown, dflt: number) => (typeof v === "number" ? v : dflt);
    const pt = p.point as number[] | undefined;
    const start = p.start as number[] | undefined;
    const end = p.end as number[] | undefined;
    const poly = p.points as [number, number][] | undefined;
    if (Array.isArray(pt)) {
      this.addBox(pt[0] ?? 0, pt[1] ?? 0, z, num(p.width, 0.4), num(p.height, 0.6), num(p.depth, 0.4));
    } else if (Array.isArray(start) && Array.isArray(end)) {
      this.addLine(start[0] ?? 0, start[1] ?? 0, end[0] ?? 0, end[1] ?? 0, z);
    } else if (Array.isArray(poly)) {
      this.addPoly(poly, z);
    }
  }

  /**
   * Mark the current proxies as FAILED: red, still visible, still saying where.
   *
   * The pre-A29 behaviour on a failed recipe was `clear()` + a toast — every trace of the attempt
   * erased, so the user knew something failed but not WHERE. The marker now stays until the next
   * draft action (`fromParams` clears a failed layer first), which is the user acknowledging it.
   */
  markFailed(): void {
    this._failed = true;
    this.lineMat.color.setHex(RED);
    this.faceMat.color.setHex(RED);
  }

  clear(): void {
    for (const o of [...this.group.children]) {
      this.group.remove(o);
      (o as THREE.Mesh).geometry?.dispose?.();
    }
    // reset to the pending palette — materials are shared across all proxies in the layer
    this._failed = false;
    this.lineMat.color.setHex(AMBER);
    this.faceMat.color.setHex(AMBER);
  }

  get pending(): boolean { return this.group.children.length > 0 && !this._failed; }

  get failed(): boolean { return this._failed && this.group.children.length > 0; }
}
