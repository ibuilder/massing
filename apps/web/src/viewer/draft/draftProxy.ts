/**
 * Draft proxy layer (P6) — the optimistic side of drafting. The moment an element is placed, a
 * lightweight amber proxy (box / line / polygon) is drawn where it will land, so the modeler gets
 * instant feedback instead of staring at the ~publish round-trip. When the server finishes authoring
 * the real IFC and the fragment is re-streamed, the proxies are cleared and replaced by real geometry.
 *
 * World coordinates follow the viewer convention: (E, elevation, -N).
 */
import * as THREE from "three";

const AMBER = 0xffb000;

export class DraftProxyLayer {
  readonly group = new THREE.Group();
  private lineMat = new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.9, depthTest: false });
  private faceMat = new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.25, depthTest: false, side: THREE.DoubleSide });

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

  /** Build the right proxy from an authoring recipe's params (point / start+end / points). */
  fromParams(p: Record<string, unknown>, z: number): void {
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

  clear(): void {
    for (const o of [...this.group.children]) {
      this.group.remove(o);
      (o as THREE.Mesh).geometry?.dispose?.();
    }
  }

  get pending(): boolean { return this.group.children.length > 0; }
}
