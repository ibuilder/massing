// SNAP-KIT — object-snap, polar tracking, and dynamic input (pure math, unit-tested).
//
// The other half of "friendly CAD" (the OpenAEC / Open CAD Studio study's precision kit). Like
// inference.ts this is pure geometry in the plan plane (E = x, N = -z), so it's exhaustively testable;
// the viewer supplies candidate points (raycast off the model + grid), the cursor, and draws the glyphs.
//
//  · resolveSnap  — the nearest object-snap point within a pixel tolerance (endpoint/midpoint/center/
//    intersection/nearest), priority-ordered so a vertex beats a midpoint beats a nearest-on-edge.
//  · polarConstrain — snap the cursor's bearing from an origin to the nearest N-degree increment
//    (AutoCAD polar tracking), returning the constrained point + the locked angle.
//  · applyDynamicInput — constrain the rubber-band by a typed distance and/or angle (the value you key
//    in while drawing), overriding the free cursor.

export type Vec2 = { x: number; z: number };
export type SnapKind = "endpoint" | "midpoint" | "center" | "intersection" | "perpendicular" | "nearest" | "grid";
export type SnapCandidate = { x: number; z: number; kind: SnapKind };
export type SnapResult = { x: number; z: number; kind: SnapKind; dist: number };

const DEG = Math.PI / 180;
// higher = stronger; a coincident vertex should win over a midpoint which wins over a point-on-edge.
const PRIORITY: Record<SnapKind, number> = {
  endpoint: 6, intersection: 5, center: 4, perpendicular: 3, midpoint: 2, grid: 1, nearest: 0,
};

/**
 * The best object-snap for `cursor` among `candidates`, or null if none is within `tol` (world units).
 * Ties on distance break by snap priority (a vertex beats a midpoint at the same range).
 *
 * `only` restricts the search to one snap kind — this is what a **one-shot override** is made of
 * (AUTH-SNAP-OVERRIDE). It is a filter and never a preference: when nothing of that kind is in range
 * the answer is `null`, *not* the nearest point of some other kind. Falling back would hand the
 * drafter a midpoint while the HUD said "perpendicular", and a snap that lies about its kind is worse
 * than no snap at all — the placed point carries a GlobalId and feeds schedules.
 */
export function resolveSnap(
  cursor: Vec2, candidates: SnapCandidate[], tol: number, only?: SnapKind | null,
): SnapResult | null {
  let best: SnapResult | null = null;
  for (const c of candidates) {
    if (only && c.kind !== only) continue;
    const d = Math.hypot(c.x - cursor.x, c.z - cursor.z);
    if (d > tol) continue;
    if (!best) { best = { x: c.x, z: c.z, kind: c.kind, dist: d }; continue; }
    // prefer clearly-closer; within a small epsilon prefer the higher-priority kind
    if (d < best.dist - 1e-6 || (Math.abs(d - best.dist) <= 1e-6 && PRIORITY[c.kind] > PRIORITY[best.kind])) {
      best = { x: c.x, z: c.z, kind: c.kind, dist: d };
    }
  }
  return best;
}

/** Parameter of the projection of `p` onto segment a→b, unclamped. Null for a degenerate segment. */
function projectT(a: Vec2, b: Vec2, p: Vec2): number | null {
  const dx = b.x - a.x, dz = b.z - a.z;
  const len2 = dx * dx + dz * dz;
  if (len2 < 1e-12) return null;
  return ((p.x - a.x) * dx + (p.z - a.z) * dz) / len2;
}

/**
 * Foot-of-perpendicular candidates: for each segment of `points`, the point where a line from `from`
 * meets that segment at 90°. **Emitted only when the foot lies ON the segment** — a perpendicular
 * that lands past the end of an edge is a perpendicular to that edge's *infinite line*, which is not
 * a place on the model, so it is dropped rather than clamped. (Clamping would silently return the
 * endpoint and label it "perpendicular".)
 *
 * `from` is the point being drawn *from* — the previous point of the run. Perpendicular is the one
 * osnap that is meaningless without it, which is why it takes an argument the others do not.
 */
export function perpendicularSnaps(points: Vec2[], from: Vec2, closed = false): SnapCandidate[] {
  const out: SnapCandidate[] = [];
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const j = i + 1;
    if (j >= n && !closed) break;
    const a = points[i]!, b = points[j % n]!;
    const t = projectT(a, b, from);
    if (t === null || t < -1e-9 || t > 1 + 1e-9) continue;
    out.push({ x: a.x + t * (b.x - a.x), z: a.z + t * (b.z - a.z), kind: "perpendicular" });
  }
  return out;
}

/** Nearest-point-on-edge candidates ("nearest" osnap) — the projection of `cursor` onto each
 *  segment, clamped to the segment's ends. Unlike perpendicular this always yields a point per
 *  segment, because "nearest" makes no claim about the angle. */
export function nearestSnaps(points: Vec2[], cursor: Vec2, closed = false): SnapCandidate[] {
  const out: SnapCandidate[] = [];
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const j = i + 1;
    if (j >= n && !closed) break;
    const a = points[i]!, b = points[j % n]!;
    const t = projectT(a, b, cursor);
    if (t === null) continue;
    const c = Math.min(1, Math.max(0, t));
    out.push({ x: a.x + c * (b.x - a.x), z: a.z + c * (b.z - a.z), kind: "nearest" });
  }
  return out;
}

/** Endpoint + midpoint snap candidates for a polyline (open or closed). Used by the viewer to feed
 *  resolveSnap from the elements it raycasts. */
export function segmentSnaps(points: Vec2[], closed = false): SnapCandidate[] {
  const out: SnapCandidate[] = [];
  const n = points.length;
  for (let i = 0; i < n; i++) {
    out.push({ x: points[i]!.x, z: points[i]!.z, kind: "endpoint" });
    const j = i + 1;
    if (j < n || closed) {
      const b = points[j % n]!;
      out.push({ x: (points[i]!.x + b.x) / 2, z: (points[i]!.z + b.z) / 2, kind: "midpoint" });
    }
  }
  return out;
}

/**
 * Polar tracking: snap the bearing of `cursor` (relative to `origin`) to the nearest multiple of
 * `incDeg` (e.g. 45 → 0/45/90/…), preserving the cursor's distance from the origin. Returns the
 * constrained point, the locked angle (deg, 0..360), and whether the snap actually moved the cursor
 * within `tolDeg`. `incDeg <= 0` disables (returns the raw cursor).
 */
export function polarConstrain(
  origin: Vec2, cursor: Vec2, incDeg = 45, tolDeg = 4,
): { x: number; z: number; angle: number; locked: boolean } {
  const dx = cursor.x - origin.x, dz = cursor.z - origin.z;
  const r = Math.hypot(dx, dz);
  if (r < 1e-9 || incDeg <= 0) return { x: cursor.x, z: cursor.z, angle: 0, locked: false };
  const raw = Math.atan2(dz, dx) / DEG;                       // -180..180
  const snapped = Math.round(raw / incDeg) * incDeg;
  let delta = Math.abs(raw - snapped) % 360;
  if (delta > 180) delta = 360 - delta;
  const norm = ((snapped % 360) + 360) % 360;
  if (delta > tolDeg) return { x: cursor.x, z: cursor.z, angle: ((raw % 360) + 360) % 360, locked: false };
  const a = snapped * DEG;
  return { x: origin.x + r * Math.cos(a), z: origin.z + r * Math.sin(a), angle: norm, locked: true };
}

/**
 * Dynamic input: constrain the rubber-band from `origin` toward `cursor` by a typed `distance` and/or
 * `angle` (deg from +X). Distance-only keeps the cursor's bearing; angle-only keeps the cursor's
 * distance; both give an exact point. Returns the constrained point (or the raw cursor when nothing is
 * typed). This is the "key in 5 <Tab> 90 <Enter>" flow every drafter uses.
 */
export function applyDynamicInput(
  origin: Vec2, cursor: Vec2, input: { distance?: number; angle?: number },
): Vec2 {
  const dx = cursor.x - origin.x, dz = cursor.z - origin.z;
  const curR = Math.hypot(dx, dz);
  const curA = curR < 1e-9 ? 0 : Math.atan2(dz, dx);          // radians
  const hasD = input.distance !== undefined && Number.isFinite(input.distance) && input.distance! > 0;
  const hasA = input.angle !== undefined && Number.isFinite(input.angle);
  if (!hasD && !hasA) return { x: cursor.x, z: cursor.z };
  const r = hasD ? input.distance! : curR;
  const a = hasA ? input.angle! * DEG : curA;
  return { x: origin.x + r * Math.cos(a), z: origin.z + r * Math.sin(a) };
}
