// E1 — SketchUp-style drawing inference (pure math, unit-tested; wired into the draft point-capture flow).
// Works in the world X/Z plane (plan E = x, N = -z). Given the previous point and the live cursor, snap the
// cursor onto an inferred direction — the four axes (±X / ±Z) or a reference edge's direction and its
// perpendicular — when the cursor's bearing is within an angular tolerance. This is the automatic "on-axis /
// parallel / perpendicular" snapping that makes free-hand drawing land clean lines without holding Shift.

export type Vec2 = { x: number; z: number };
export type Inference = { x: number; z: number; kind: "axis-x" | "axis-z" | "parallel" | "perpendicular" };

const DEG = Math.PI / 180;

/** Project `cursor` onto the ray from `prev` along unit direction (dx,dz). Returns the closest point on
 *  that infinite line (a point behind `prev` is allowed — inference lines extend both ways). */
function projectOnAxis(prev: Vec2, cursor: Vec2, dx: number, dz: number): Vec2 {
  const t = (cursor.x - prev.x) * dx + (cursor.z - prev.z) * dz; // scalar projection (dir is unit)
  return { x: prev.x + t * dx, z: prev.z + t * dz };
}

/** Angle (deg, 0..180) between two direction vectors. */
function angleBetween(ax: number, az: number, bx: number, bz: number): number {
  const la = Math.hypot(ax, az), lb = Math.hypot(bx, bz);
  if (la < 1e-9 || lb < 1e-9) return 180;
  const c = Math.min(1, Math.max(-1, (ax * bx + az * bz) / (la * lb)));
  return Math.acos(c) / DEG;
}

/**
 * Infer a snapped cursor position. Candidate directions, in priority order:
 *   1. the four world axes (±X, ±Z) → "axis-x" / "axis-z"
 *   2. (optional) a reference edge direction → "parallel", and its perpendicular → "perpendicular"
 * The candidate whose direction is closest to the live bearing (prev→cursor) within `tolDeg` wins; the
 * cursor is projected onto that inference line. Returns null when nothing is within tolerance (free draw).
 */
export function inferDirection(
  prev: Vec2,
  cursor: Vec2,
  opts: { tolDeg?: number; ref?: Vec2 } = {},
): Inference | null {
  const tol = opts.tolDeg ?? 6;
  const bx = cursor.x - prev.x, bz = cursor.z - prev.z;
  if (Math.hypot(bx, bz) < 1e-6) return null; // cursor on prev — nothing to infer

  const candidates: { dx: number; dz: number; kind: Inference["kind"] }[] = [
    { dx: 1, dz: 0, kind: "axis-x" },
    { dx: 0, dz: 1, kind: "axis-z" },
  ];
  if (opts.ref) {
    const rx = opts.ref.x, rz = opts.ref.z, rl = Math.hypot(rx, rz);
    if (rl > 1e-9) {
      const ux = rx / rl, uz = rz / rl;
      candidates.push({ dx: ux, dz: uz, kind: "parallel" });
      candidates.push({ dx: -uz, dz: ux, kind: "perpendicular" }); // 90° rotation
    }
  }

  let best: { kind: Inference["kind"]; dx: number; dz: number; ang: number } | null = null;
  for (const c of candidates) {
    // a direction and its opposite are the same inference line, so fold to 0..90
    const ang = Math.min(angleBetween(bx, bz, c.dx, c.dz), angleBetween(bx, bz, -c.dx, -c.dz));
    if (ang <= tol && (!best || ang < best.ang)) best = { kind: c.kind, dx: c.dx, dz: c.dz, ang };
  }
  if (!best) return null;
  const p = projectOnAxis(prev, cursor, best.dx, best.dz);
  return { x: p.x, z: p.z, kind: best.kind };
}

/** Midpoint of a segment — the SketchUp midpoint inference target. */
export function midpoint(a: Vec2, b: Vec2): Vec2 {
  return { x: (a.x + b.x) / 2, z: (a.z + b.z) / 2 };
}
