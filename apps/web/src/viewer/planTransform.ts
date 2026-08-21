/**
 * R38-SYNC-VIEW — the plan SVG's own world↔pixel map, read from the attributes the generator
 * serialises rather than reverse-engineered from linework.
 *
 * `plan_drawing_svg` computes T(x, y) = (ox + (x - minx) * scale, oy + drawh - (y - miny) * scale)
 * and (since v0.3.928) writes every term onto the root. Inventing the same numbers from a polyline
 * whose element geometry the client already knows would work in a demo and drift the first time a
 * cut differs from what the client assumes.
 *
 * Viewer ground is Y-up: East = `three.x`, North = `-three.z`. The drawing's (x, y) is that plan
 * pair. Mixing them is how a cursor sits on the wrong wall.
 */

export interface PlanTransform {
  scale: number;
  ox: number;
  oy: number;
  minx: number;
  miny: number;
  drawh: number;
}

const ATTRS = [
  "data-plan-scale", "data-plan-ox", "data-plan-oy",
  "data-plan-minx", "data-plan-miny", "data-plan-drawh",
] as const;

function num(el: Element, attr: string): number | null {
  const raw = el.getAttribute(attr);
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** Read the six terms off an SVG root. `null` when any term is missing or not a number — a partial
 *  transform is how a cursor would look "almost right" on a large plan. */
export function readPlanTransform(root: Element | null): PlanTransform | null {
  if (!root) return null;
  const svg = root instanceof SVGSVGElement ? root : root.querySelector("svg");
  if (!svg) return null;
  const vals = ATTRS.map((a) => num(svg, a));
  if (vals.some((v) => v == null)) return null;
  const [scale, ox, oy, minx, miny, drawh] = vals as number[];
  if (scale === 0) return null;
  return { scale, ox, oy, minx, miny, drawh };
}

export function worldToPixel(t: PlanTransform, x: number, y: number): { px: number; py: number } {
  return {
    px: t.ox + (x - t.minx) * t.scale,
    py: t.oy + t.drawh - (y - t.miny) * t.scale,
  };
}

export function pixelToWorld(t: PlanTransform, px: number, py: number): { x: number; y: number } {
  return {
    x: t.minx + (px - t.ox) / t.scale,
    y: t.miny + (t.drawh - (py - t.oy)) / t.scale,
  };
}

/** Viewer ground (Y-up) → drawing (x = East, y = North). */
export function groundToPlan(pt: { x: number; z: number }): { x: number; y: number } {
  return { x: pt.x, y: -pt.z };
}
