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
  const box = modelBox3(models);
  if (!box) return null;
  return { minX: box.min.x, maxX: box.max.x, minZ: -box.max.z, maxZ: -box.min.z };
}

/**
 * The same population as a full 3D box — for callers that need Y as well as the plan extent.
 *
 * Added 2026-08-06 after the docstring above turned out to be understating the problem. It says the
 * bounds walk "was the third site that needed to and did not". It was the third of **six** — and
 * this very sentence said **five** until 2026-08-23, because the pass that wrote it fixed the two it
 * had found and did not go looking for a third:
 *
 *     measureSection.ts  installSectionBox   scene.traverse(...expandByObject)   ← 4th
 *     envTools.ts        storey levels grid  scene.traverse(...expandByObject)   ← 5th
 *     app.ts             fitToModels         scene.traverse(...expandByObject)   ← 6th, fixed v0.3.1062
 *
 * The sixth is the one that stings: **R41-MODEL-ALIGN had written the instruction that finds it** —
 * *"check whether the AABB-versus-OBB gap already affects our section box, zoom-to-model and any
 * bounding-box UI"* — and the pass acting on that instruction fixed the section box and the storey
 * grid and left zoom-to-model. A checklist naming three things was followed for two, and the miss
 * was invisible precisely because the two fixes were real. *N−1 correct sites prove nothing about
 * the Nth, and that applies to the pass doing the fixing as much as to the code being fixed.*
 *
 * What it cost the user: with presentation mode on the fit received a **~1.4 km bounding sphere for
 * a ~65 m building — the model drew at roughly 5% of the view.** Silent, permissive, one render mode.
 *
 * **`fitToModels` passes `referenceModels` explicitly**, and a caller adding a new population must
 * do the same rather than restore the walk. The scene walk included `isPoints` on purpose — survey
 * scans and reference overlays — and this function's population is loaded fragments models alone, so
 * dropping them would trade a wrong fit for an incomplete one. That has its own twin test; without
 * it, a "fix" that silently ignored a survey scan would pass every other assertion in the file.
 *
 * Both computed a scene-wide box including the `2000 × 2000` shadow-catcher, and both are
 * user-visible in exactly the way this file predicts — silently, and only with presentation mode on:
 *
 *     section box   clip half-extent 700 m about the origin, against a ~95 m building
 *                   → the section box clipped NOTHING
 *     storey grid   2200 m across where the model is 104 m → 21x oversized, at every storey
 *
 * The plan-only signature is why they were not fixed when the third was: `planBoundsFromModels`
 * returns `PlanBounds`, so a caller needing Y could not use it and hand-rolled the traverse instead
 * — **the helper's shape, not its absence, is what let the defect spread.** A correct allowlist that
 * does not fit the call site is a correct allowlist nobody calls.
 *
 * Returns null on an empty population, for the same reason as above: a blank model must not be
 * treated as a model of size zero. Callers already handle `box.isEmpty()`; they now handle null.
 */
export function modelBox3(models: Iterable<BoundedModel>): THREE.Box3 | null {
  const box = new THREE.Box3();
  let any = false;
  for (const m of models) {
    if (!m?.object) continue;
    box.expandByObject(m.object);
    any = true;
  }
  return any && !box.isEmpty() ? box : null;
}
