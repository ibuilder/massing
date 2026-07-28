/**
 * Page-space geometry. Pure functions, no DOM — so the measurement maths is unit-testable on its
 * own and the same code can run server-side to recompute quantities after a re-calibration.
 */
import type { Box, Pt } from "./types";

export const dist = (a: Pt, b: Pt): number => Math.hypot(b.x - a.x, b.y - a.y);

/** Total length of an open path. */
export function pathLength(pts: readonly Pt[]): number {
  let n = 0;
  for (let i = 1; i < pts.length; i++) n += dist(pts[i - 1]!, pts[i]!);
  return n;
}

/** Perimeter of a closed path (the path length plus the closing segment). */
export function perimeter(pts: readonly Pt[]): number {
  if (pts.length < 3) return pathLength(pts);
  return pathLength(pts) + dist(pts[pts.length - 1]!, pts[0]!);
}

/** Shoelace area of a simple polygon. Sign-free — winding order is not the user's problem. */
export function polygonArea(pts: readonly Pt[]): number {
  if (pts.length < 3) return 0;
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i]!, b = pts[(i + 1) % pts.length]!;
    s += a.x * b.y - b.x * a.y;
  }
  return Math.abs(s) / 2;
}

/** Centroid of a polygon, falling back to the mean of the points for degenerate input. */
export function centroid(pts: readonly Pt[]): Pt {
  if (!pts.length) return { x: 0, y: 0 };
  if (pts.length < 3) return mean(pts);
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i]!, q = pts[(i + 1) % pts.length]!;
    const cross = p.x * q.y - q.x * p.y;
    a += cross; cx += (p.x + q.x) * cross; cy += (p.y + q.y) * cross;
  }
  if (Math.abs(a) < 1e-9) return mean(pts);
  return { x: cx / (3 * a), y: cy / (3 * a) };
}

export function mean(pts: readonly Pt[]): Pt {
  const n = pts.length || 1;
  return { x: pts.reduce((s, p) => s + p.x, 0) / n, y: pts.reduce((s, p) => s + p.y, 0) / n };
}

/** Interior angle at `b` in the corner `a-b-c`, in degrees (0..180). */
export function angleAt(a: Pt, b: Pt, c: Pt): number {
  const v1 = { x: a.x - b.x, y: a.y - b.y }, v2 = { x: c.x - b.x, y: c.y - b.y };
  const m1 = Math.hypot(v1.x, v1.y), m2 = Math.hypot(v2.x, v2.y);
  if (!m1 || !m2) return 0;
  const cos = Math.min(1, Math.max(-1, (v1.x * v2.x + v1.y * v2.y) / (m1 * m2)));
  return (Math.acos(cos) * 180) / Math.PI;
}

/** Radius of the circle through three points; `0` if they are collinear. */
export function circumradius(a: Pt, b: Pt, c: Pt): number {
  const A = dist(b, c), B = dist(a, c), C = dist(a, b);
  const area = Math.abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2;
  if (area < 1e-9) return 0;
  return (A * B * C) / (4 * area);
}

export function bbox(pts: readonly Pt[]): Box {
  if (!pts.length) return { x: 0, y: 0, w: 0, h: 0 };
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of pts) {
    if (p.x < x0) x0 = p.x; if (p.y < y0) y0 = p.y;
    if (p.x > x1) x1 = p.x; if (p.y > y1) y1 = p.y;
  }
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

export const growBox = (b: Box, by: number): Box =>
  ({ x: b.x - by, y: b.y - by, w: b.w + by * 2, h: b.h + by * 2 });

export const boxContains = (b: Box, p: Pt): boolean =>
  p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h;

export const boxesOverlap = (a: Box, b: Box): boolean =>
  a.x <= b.x + b.w && b.x <= a.x + a.w && a.y <= b.y + b.h && b.y <= a.y + a.h;

/** Distance from `p` to segment `a-b`. The primitive behind click-to-select on a thin line. */
export function distToSegment(p: Pt, a: Pt, b: Pt): number {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 < 1e-12) return dist(p, a);
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** Distance from `p` to a polyline (or its closing edge too, when `closed`). */
export function distToPath(p: Pt, pts: readonly Pt[], closed = false): number {
  if (pts.length === 0) return Infinity;
  if (pts.length === 1) return dist(p, pts[0]!);
  let best = Infinity;
  for (let i = 1; i < pts.length; i++) best = Math.min(best, distToSegment(p, pts[i - 1]!, pts[i]!));
  if (closed && pts.length > 2) best = Math.min(best, distToSegment(p, pts[pts.length - 1]!, pts[0]!));
  return best;
}

/** Even-odd point-in-polygon. */
export function pointInPolygon(p: Pt, pts: readonly Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const a = pts[i]!, b = pts[j]!;
    if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

/** Two corner points → the four corners of the axis-aligned rectangle they span. */
export function rectCorners(a: Pt, b: Pt): Pt[] {
  const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
  const y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
  return [{ x: x0, y: y0 }, { x: x1, y: y0 }, { x: x1, y: y1 }, { x: x0, y: y1 }];
}

/**
 * A revision cloud: scalloped arcs along a path. The single most recognisable AEC markup, and the
 * reason a generic annotator never quite looks right on a drawing.
 *
 * Returns an SVG path `d` — arcs, not sampled points, so it stays crisp at any zoom and stays small
 * when serialised. `radius` is in page units; the arc count per segment adapts to its length.
 */
export function cloudPath(pts: readonly Pt[], radius = 6, closed = true): string {
  if (pts.length < 2) return "";
  const ring = closed ? [...pts, pts[0]!] : [...pts];
  let d = "";
  let started = false;
  for (let i = 1; i < ring.length; i++) {
    const a = ring[i - 1]!, b = ring[i]!;
    const len = dist(a, b);
    if (len < 1e-6) continue;
    // Arc chord ≈ 2r, but never fewer than one bump per segment, so short jogs still read as cloud.
    const n = Math.max(1, Math.round(len / (radius * 1.8)));
    const step = len / n;
    const ux = (b.x - a.x) / len, uy = (b.y - a.y) / len;
    if (!started) { d += `M${r2(a.x)},${r2(a.y)}`; started = true; }
    for (let k = 1; k <= n; k++) {
      const px = a.x + ux * step * k, py = a.y + uy * step * k;
      // sweep=1 puts the bulge on the left of travel; for a closed CW ring that is outward.
      d += `A${r2(step / 2)},${r2(step / 2)} 0 0 1 ${r2(px)},${r2(py)}`;
    }
  }
  return closed && started ? `${d}Z` : d;
}

/** Ramer–Douglas–Peucker. Freehand ink arrives at pointer resolution; this is what makes it storable. */
export function simplify(pts: readonly Pt[], tolerance = 0.8): Pt[] {
  if (pts.length < 3) return [...pts];
  const first = pts[0]!, last = pts[pts.length - 1]!;
  let maxD = -1, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = distToSegment(pts[i]!, first, last);
    if (d > maxD) { maxD = d; idx = i; }
  }
  if (maxD <= tolerance) return [first, last];
  const left = simplify(pts.slice(0, idx + 1), tolerance);
  const right = simplify(pts.slice(idx), tolerance);
  return [...left.slice(0, -1), ...right];
}

/** Catmull–Rom → cubic Bézier, so simplified ink still renders as a smooth stroke. */
export function smoothPath(pts: readonly Pt[]): string {
  if (pts.length < 2) return pts.length === 1 ? `M${r2(pts[0]!.x)},${r2(pts[0]!.y)}` : "";
  if (pts.length === 2) return `M${r2(pts[0]!.x)},${r2(pts[0]!.y)}L${r2(pts[1]!.x)},${r2(pts[1]!.y)}`;
  let d = `M${r2(pts[0]!.x)},${r2(pts[0]!.y)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)]!, p1 = pts[i]!, p2 = pts[i + 1]!, p3 = pts[Math.min(pts.length - 1, i + 2)]!;
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    d += `C${r2(c1.x)},${r2(c1.y)} ${r2(c2.x)},${r2(c2.y)} ${r2(p2.x)},${r2(p2.y)}`;
  }
  return d;
}

/** Plain polyline `d`. */
export const linePath = (pts: readonly Pt[], closed = false): string =>
  pts.length ? pts.map((p, i) => `${i ? "L" : "M"}${r2(p.x)},${r2(p.y)}`).join("") + (closed ? "Z" : "") : "";

/** Arrowhead wings for a segment ending at `to`, as two points to draw back from the tip. */
export function arrowHead(from: Pt, to: Pt, size = 8): [Pt, Pt] {
  const a = Math.atan2(to.y - from.y, to.x - from.x);
  const spread = Math.PI / 7;
  return [
    { x: to.x - size * Math.cos(a - spread), y: to.y - size * Math.sin(a - spread) },
    { x: to.x - size * Math.cos(a + spread), y: to.y - size * Math.sin(a + spread) },
  ];
}

/** Snap `b` so the segment `a→b` lies on a multiple of `stepDeg` — shift-drag for orthogonal lines. */
export function snapAngle(a: Pt, b: Pt, stepDeg = 15): Pt {
  const len = dist(a, b);
  if (!len) return { ...b };
  const step = (stepDeg * Math.PI) / 180;
  const ang = Math.round(Math.atan2(b.y - a.y, b.x - a.x) / step) * step;
  return { x: a.x + Math.cos(ang) * len, y: a.y + Math.sin(ang) * len };
}

/** Translate a path. */
export const translate = (pts: readonly Pt[], dx: number, dy: number): Pt[] =>
  pts.map((p) => ({ x: p.x + dx, y: p.y + dy }));

/** Scale a path about an origin — used by markup migration when a sheet is re-issued at a new size. */
export const scaleAbout = (pts: readonly Pt[], origin: Pt, k: number): Pt[] =>
  pts.map((p) => ({ x: origin.x + (p.x - origin.x) * k, y: origin.y + (p.y - origin.y) * k }));

/** Rotate a path about an origin by `deg` clockwise (page space is y-down). */
export function rotateAbout(pts: readonly Pt[], origin: Pt, deg: number): Pt[] {
  const r = (deg * Math.PI) / 180, c = Math.cos(r), s = Math.sin(r);
  return pts.map((p) => {
    const dx = p.x - origin.x, dy = p.y - origin.y;
    return { x: origin.x + dx * c - dy * s, y: origin.y + dx * s + dy * c };
  });
}

/** Round to 2dp for path strings — keeps serialised geometry small without visible error. */
const r2 = (n: number): number => Math.round(n * 100) / 100;
export { r2 as round2 };
