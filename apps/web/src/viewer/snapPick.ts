import * as THREE from "three";

import { resolveSnap } from "./snapEngine";
import { overrideCandidates, type OverrideKind } from "./snapOverride";

/** What a pick gives us: where the ray landed, and which element it landed on. */
export type SnapHit = { point: THREE.Vector3; fragments: { modelId: string }; localId: number };

/** The slice of the fragments loader these need, and nothing more.
 *
 *  **This is the whole reason the three functions below could leave `app.ts`.** They were closures
 *  inside a 2,380-line `initViewerApp`, and the measurement that chose them counted what each one
 *  closes over: `buildToolsPanel` (696 lines) closes over 51 of the 143 outer bindings, so lifting it
 *  would mean inventing a 51-parameter callback bag — coupling added in the name of removing it, the
 *  same reject that kept `renderDesignHome` in `portal.ts`. These three close over `loader` and the
 *  grid increment. One structural parameter, declared here rather than importing `ModelLoader`, so a
 *  test can hand them a plain object and the module never learns what a viewer is. */
export interface SnapFragments {
  list: { get(modelId: string): { getPositions(localIds: number[]): Promise<THREE.Vector3[] | null | undefined> } | undefined };
  getBBoxes(selection: Record<string, Set<number>>): Promise<{ min: THREE.Vector3; max: THREE.Vector3 }[]>;
}

/** Round a point's plan coords (x,z) to the grid-snap increment; leave height (y).
 *
 *  `inc` is passed rather than read from settings: the caller owns the setting, and a pure function
 *  of (point, increment) is one a test can state an expectation about. */
export function snapPoint(p: THREE.Vector3, inc: number): THREE.Vector3 {
  if (!inc) return p;
  return new THREE.Vector3(Math.round(p.x / inc) * inc, p.y, Math.round(p.z / inc) * inc);
}

/** Snap to the hit element's nearest mesh vertex within ~0.4 m (true endpoint snap), then to its
 *  bounding-box corners / edge midpoints / center (the classic osnap set), then to grid snap. */
export async function snapToGeometry(
  raw: THREE.Vector3, hit: SnapHit | null, frags: SnapFragments,
): Promise<THREE.Vector3 | null> {
  if (!hit) return null;
  const nearest = (pts: THREE.Vector3[]) => {
    let best: THREE.Vector3 | null = null, bd = 0.4;
    for (const v of pts) { const d = raw.distanceTo(v); if (d < bd) { bd = d; best = v; } }
    return best ? best.clone() : null;
  };
  try {
    const model = frags.list.get(hit.fragments.modelId);
    const verts = model ? await model.getPositions([hit.localId]) : null;
    if (verts?.length) { const v = nearest(verts); if (v) return v; }
  } catch { /* fall back to bbox candidates */ }
  try {
    const boxes = await frags.getBBoxes({ [hit.fragments.modelId]: new Set([hit.localId]) });
    if (!boxes.length) return null;
    const bx = boxes[0]!; // safe: boxes.length checked above
    const xs = [bx.min.x, bx.max.x], ys = [bx.min.y, bx.max.y], zs = [bx.min.z, bx.max.z];
    const corners = xs.flatMap((x) => ys.flatMap((y) => zs.map((z) => new THREE.Vector3(x, y, z))));
    // UX-2: edge midpoints (each axis at its midpoint × the other two axes' extremes) + the center —
    // the midpoint/center osnaps annotation placement expects.
    const mx = (bx.min.x + bx.max.x) / 2, my = (bx.min.y + bx.max.y) / 2, mz = (bx.min.z + bx.max.z) / 2;
    const mids = [
      ...ys.flatMap((y) => zs.map((z) => new THREE.Vector3(mx, y, z))),
      ...xs.flatMap((x) => zs.map((z) => new THREE.Vector3(x, my, z))),
      ...xs.flatMap((x) => ys.map((y) => new THREE.Vector3(x, y, mz))),
      new THREE.Vector3(mx, my, mz),
    ];
    return nearest([...corners, ...mids]);
  } catch { return null; }
}

/** AUTH-SNAP-OVERRIDE — resolve ONE named snap kind against the picked element's plan footprint.
 *
 *  Null when the model has nothing of that kind to offer; the caller then keeps the raw cursor and
 *  says so on the glyph. It deliberately does **not** fall back to another kind — the drafter named
 *  one, and a point silently placed on a midpoint while the HUD said "perpendicular" carries a
 *  GlobalId into the schedules.
 *
 *  No aperture. The automatic path uses a 0.4 m tolerance because it is guessing which of six kinds
 *  the drafter meant; here the kind is stated and the candidates are the ≤4 points of the element
 *  the drafter explicitly picked, so a distance cut would only make a stated intent fail. */
export async function snapByOverride(
  raw: THREE.Vector3, hit: SnapHit | null, kind: OverrideKind,
  from: THREE.Vector3 | null, frags: SnapFragments,
): Promise<THREE.Vector3 | null> {
  if (kind === "none" || !hit) return null;
  try {
    const boxes = await frags.getBBoxes({ [hit.fragments.modelId]: new Set([hit.localId]) });
    const bx = boxes[0];
    if (!bx) return null;
    const cur = { x: raw.x, z: raw.z };
    const cands = overrideCandidates(kind, { minX: bx.min.x, maxX: bx.max.x, minZ: bx.min.z, maxZ: bx.max.z },
                                     cur, from ? { x: from.x, z: from.z } : null);
    const r = resolveSnap(cur, cands, Number.POSITIVE_INFINITY, kind);
    return r ? new THREE.Vector3(r.x, raw.y, r.z) : null;
  } catch { return null; }
}
