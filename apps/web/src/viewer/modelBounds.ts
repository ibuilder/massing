import * as THREE from "three";
import type { PlanBounds } from "./placeValid";

/**
 * The loaded model's plan extent — measured from the **model**, not from the scene.
 *
 * ## The defect this exists to fix
 *
 * `A29-PLACE-VALID`'s second refusal is, in `placeValid.ts`'s own words, *"a click FAR OUTSIDE the
 * model — the 3D click falls back to the infinite ground plane, so a mis-click near the horizon
 * quietly authors a wall 400 m from the building"*. It compares the click against the model's plan
 * extent plus a 50 m margin.
 *
 * That extent used to be computed by walking the **whole scene** and expanding a box over every
 * `isMesh` object. The scene contains a `2000 × 2000` shadow-catcher plane (`aec-shadow-ground` in
 * `world.ts`), added whenever presentation/render mode is on. So with render mode on the "model
 * extent" became roughly **±1000 m**, and with the margin a mis-click up to ~1050 m out passed.
 *
 * **The check written to catch a mis-click on a ground plane was defeated by a ground plane.** It
 * failed silently and in the permissive direction: nothing errors, placements just stop being
 * refused, and only in one render mode — so it would pass any test that did not turn that mode on.
 *
 * `world.ts` already knew this. It excludes the ground mesh by name in **two** places (its shadow
 * frustum fit and its material sweep). The bounds walk was the third site that needed to and did not
 * — the same fact encoded correctly twice and missed once.
 *
 * ## Why an allowlist rather than "skip the ground plane"
 *
 * Excluding `aec-shadow-ground` by name would fix today's symptom and leave the shape intact: every
 * future non-model mesh — draft proxies, the grid overlay, logistics markers, a guide underlay
 * pinned to a level — would silently widen the model again, one at a time, each needing to be
 * remembered. The repo's own rule is that needing an exemption list is the tell that the *population*
 * is wrong.
 *
 * So the population is stated positively: **a loaded Fragments model, and nothing else.** Anything
 * the viewer draws that is not streamed model geometry is structurally out of scope rather than
 * remembered-to-be-excluded.
 *
 * Preview models are deliberately IN. They are real fragment geometry for the element being placed,
 * they sit at the placement point, and they arrive through the same loader — so they can only widen
 * the extent toward the very point being validated, which is not a mis-click.
 */

/** What `modelPlanBounds` needs from a loaded model: its scene object. */
export interface BoundedModel { object: THREE.Object3D }

/**
 * Plan bounds over `models`, or null when nothing is loaded.
 *
 * Null is meaningful and is not an error: `checkBounds` passes everything when bounds are null,
 * because a blank model authoring its first element must never be refused by a check that needs a
 * model to exist.
 *
 * Plan coordinates are **E = world x, N = −world z**, so the N range is the *negated* world-z range
 * and the min/max swap. Getting that backwards yields a box that is still plausible — right size,
 * right shape, mirrored — which is why it is asserted directly rather than assumed.
 */
export function planBoundsFromModels(models: Iterable<BoundedModel>): PlanBounds | null {
  const box = new THREE.Box3();
  let any = false;
  for (const m of models) {
    if (!m?.object) continue;
    box.expandByObject(m.object);
    any = true;
  }
  if (!any || box.isEmpty()) return null;
  return { minX: box.min.x, maxX: box.max.x, minZ: -box.max.z, maxZ: -box.min.z };
}
