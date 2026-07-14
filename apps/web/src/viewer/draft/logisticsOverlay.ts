/**
 * Site-logistics overlay (Wave 9 · W9-5). Renders temporary construction resources — cranes, laydown
 * yards, gates, fencing, haul routes — as lightweight glyphs in the scene, so a site plan reads at a
 * glance and can be time-phased on the 4D timeline (show only what's active on the current date).
 *
 * World coordinates follow the viewer convention: (E, elevation, -N).
 */
import * as THREE from "three";

export interface LogisticsResource {
  id: string; kind: string; label?: string;
  position?: [number, number, number]; polygon?: [number, number][]; radius?: number;
  start?: string; end?: string;
}

const COLORS: Record<string, number> = {
  crane: 0xffb000, hoist: 0xff8c00, laydown: 0x33d17a, gate: 0x4a8cff,
  fence: 0x9aa0a6, haul_route: 0xffd000, trailer: 0x8a63d2, parking: 0x6ab0ff,
};

export class LogisticsOverlay {
  readonly group = new THREE.Group();
  private byId = new Map<string, THREE.Object3D>();

  constructor(scene: THREE.Scene) { this.group.name = "site-logistics"; scene.add(this.group); }

  /** Rebuild every glyph from the resource list. */
  render(resources: LogisticsResource[]): void {
    this.clear();
    for (const r of resources) this.byId.set(r.id, this.build(r));
  }

  /** Time-phase: show only the resources whose ids are in `activeIds` (from /logistics/state). */
  showActive(activeIds: Set<string>): void {
    for (const [id, obj] of this.byId) obj.visible = activeIds.has(id);
  }

  showAll(): void { for (const obj of this.byId.values()) obj.visible = true; }

  private build(r: LogisticsResource): THREE.Object3D {
    const color = COLORS[r.kind] ?? 0xffb000;
    const g = new THREE.Group();
    if (r.polygon && r.polygon.length >= 2) {
      // laydown / fence / haul route — a closed (or open) outline + faint fill for areas
      const pts = r.polygon.map(([e, n]) => new THREE.Vector3(e, 0.05, -n));
      const closed = r.kind !== "haul_route" && r.kind !== "fence";
      if (closed) pts.push(pts[0]!.clone());
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.95, depthTest: false }));
      g.add(line);
    } else if (r.position) {
      const [e, , n] = r.position;
      const box = new THREE.Mesh(new THREE.BoxGeometry(1.2, 2.4, 1.2),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5, depthTest: false }));
      box.position.set(e, 1.2, -n);
      g.add(box, new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry),
        new THREE.LineBasicMaterial({ color, depthTest: false })));
      if (r.kind === "crane" && r.radius) {
        // reach ring
        const ring = new THREE.Mesh(new THREE.RingGeometry(r.radius - 0.15, r.radius, 64),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthTest: false }));
        ring.rotation.x = -Math.PI / 2; ring.position.set(e, 0.05, -n);
        g.add(ring);
      }
    }
    this.group.add(g);
    return g;
  }

  clear(): void {
    for (const o of [...this.group.children]) {
      this.group.remove(o);
      o.traverse((c) => { (c as THREE.Mesh).geometry?.dispose?.(); });
    }
    this.byId.clear();
  }

  get count(): number { return this.byId.size; }
}
