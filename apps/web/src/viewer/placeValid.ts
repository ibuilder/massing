/**
 * A29-PLACE-VALID — say no BEFORE the round-trip, not after.
 *
 * Every draft placement used to commit blind: the server validates, so an invalid placement cost a
 * full author-and-republish round-trip (seconds, plus a failed-marker cleanup) just to be told no.
 * The three refusals here are the ones a client can answer *honestly* from what it already holds —
 * pure geometry over the draft points, no model round-trip, no guessing at server rules:
 *
 *  1. a DEGENERATE run — zero/near-zero length walls and beams author successfully and then exist
 *     as invisible slivers nobody can select;
 *  2. a click FAR OUTSIDE the model — the 3D click falls back to the infinite ground plane, so a
 *     mis-click near the horizon quietly authors a wall 400 m from the building;
 *  3. a SELF-INTERSECTING polygon — a bowtie slab outline produces garbage geometry downstream
 *     (mis-measured areas, broken plan cuts) rather than an error.
 *
 * Everything else stays the server's call — validating rules we don't own is how a client comes to
 * refuse things the server would accept. A refusal here names the reason and keeps the draft armed:
 * the user adjusts and re-clicks, nothing is torn down.
 *
 * Pure and unit-tested beside `inference.ts`, in the same plan coordinates it uses (E = x, N = -z).
 */

export interface PlanBounds { minX: number; minZ: number; maxX: number; maxZ: number }

export type PlacementVerdict = { ok: true } | { ok: false; reason: string };

const OK: PlacementVerdict = { ok: true };

/** Runs shorter than this author as invisible slivers — refuse and say how short. */
export const MIN_RUN_M = 0.05;

/** How far beyond the model's plan extent a placement may land before it reads as a mis-click.
 *  Generous on purpose: site work legitimately extends past the building. */
export const BOUNDS_MARGIN_M = 50;

/** 1. Degenerate run — a two-point element whose length is below `MIN_RUN_M`. */
export function checkRun(a: [number, number], b: [number, number]): PlacementVerdict {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  if (len < MIN_RUN_M) {
    return { ok: false, reason: `run is ${(len * 1000).toFixed(0)} mm — too short to author (min ${MIN_RUN_M * 1000} mm)` };
  }
  return OK;
}

/** 2. Far outside the model. With no bounds (empty model, first element) everything passes —
 *  a blank-model author must never be refused by a check that needs a model to exist. */
export function checkBounds(pts: [number, number][], bounds: PlanBounds | null,
                            marginM: number = BOUNDS_MARGIN_M): PlacementVerdict {
  if (!bounds) return OK;
  for (const [x, z] of pts) {
    const dx = Math.max(bounds.minX - x, 0, x - bounds.maxX);
    const dz = Math.max(bounds.minZ - z, 0, z - bounds.maxZ);
    const d = Math.hypot(dx, dz);
    if (d > marginM) {
      return { ok: false, reason: `point lands ${d.toFixed(0)} m outside the model — likely a mis-click on the ground plane` };
    }
  }
  return OK;
}

/** Proper segment intersection (excluding shared endpoints) — the primitive under the bowtie check. */
function segsCross(p1: [number, number], p2: [number, number],
                   q1: [number, number], q2: [number, number]): boolean {
  const d = (o: [number, number], a: [number, number], b: [number, number]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const d1 = d(q1, q2, p1), d2 = d(q1, q2, p2), d3 = d(p1, p2, q1), d4 = d(p1, p2, q2);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

/** 3. Self-intersecting outline — any two non-adjacent edges of the closed polygon cross. */
export function checkPolygon(pts: [number, number][]): PlacementVerdict {
  const n = pts.length;
  if (n < 3) return { ok: false, reason: `an outline needs at least 3 points (got ${n})` };
  for (let i = 0; i < n; i++) {
    const a1 = pts[i]!, a2 = pts[(i + 1) % n]!;
    for (let j = i + 1; j < n; j++) {
      // adjacent edges share a vertex and may touch there; the closing edge (n-1 → 0) is adjacent
      // to edge 0 as well, so skip neighbours in the CYCLIC sense, not the array sense.
      if (j === i || (j + 1) % n === i || (i + 1) % n === j) continue;
      const b1 = pts[j]!, b2 = pts[(j + 1) % n]!;
      if (segsCross(a1, a2, b1, b2)) {
        return { ok: false, reason: `outline crosses itself (edge ${i + 1} × edge ${j + 1}) — a bowtie slab would author garbage geometry` };
      }
    }
  }
  return OK;
}

/**
 * The composed verdict for a draft about to commit. `points` are the plan points the recipe will
 * receive; `pointsKind` says how the recipe reads them ("run" = a 2-point axis, "poly" = a closed
 * outline, "point" = a single placement). The first failing check wins — one reason, not a list.
 */
export function validatePlacement(pointsKind: "run" | "poly" | "point", points: [number, number][],
                                  bounds: PlanBounds | null): PlacementVerdict {
  const b = checkBounds(points, bounds);
  if (!b.ok) return b;
  if (pointsKind === "run" && points.length >= 2) return checkRun(points[0]!, points[points.length - 1]!);
  if (pointsKind === "poly") return checkPolygon(points);
  return OK;
}
