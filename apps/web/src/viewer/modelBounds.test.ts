import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import * as THREE from "three";
import { planBoundsFromModels, type BoundedModel } from "./modelBounds";
import { BOUNDS_MARGIN_M, checkBounds } from "./placeValid";

/** A box mesh centred at (cx, 0, cz) with the given plan size, as a loaded model would appear. */
function model(cx: number, cz: number, sizeX = 10, sizeZ = 6): BoundedModel {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(sizeX, 3, sizeZ));
  mesh.position.set(cx, 0, cz);
  mesh.updateMatrixWorld(true);
  return { object: mesh };
}

/** The `2000 × 2000` shadow-catcher `world.ts` adds in presentation mode. */
function shadowGround(): THREE.Object3D {
  const g = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000));
  g.name = "aec-shadow-ground";
  g.rotation.x = -Math.PI / 2;
  g.position.y = -0.01;
  g.updateMatrixWorld(true);
  return g;
}

describe("planBoundsFromModels — the extent comes from the model", () => {
  it("measures a single model", () => {
    const b = planBoundsFromModels([model(0, 0, 10, 6)])!;
    expect(b.minX).toBeCloseTo(-5, 6);
    expect(b.maxX).toBeCloseTo(5, 6);
  });

  it("unions several models", () => {
    const b = planBoundsFromModels([model(0, 0, 10, 6), model(100, 0, 10, 6)])!;
    expect(b.minX).toBeCloseTo(-5, 6);
    expect(b.maxX).toBeCloseTo(105, 6);
  });

  // Plan is E = x, N = -z. A sign error here yields a box of the right size and shape, mirrored —
  // plausible enough to survive review, so it is asserted rather than assumed.
  it("negates the world-z range into plan N, swapping min and max", () => {
    const m = model(0, 20, 10, 6);                 // world z spans 17..23
    const b = planBoundsFromModels([m])!;
    expect(b.minZ).toBeCloseTo(-23, 6);            // N min is the NEGATED world-z MAX
    expect(b.maxZ).toBeCloseTo(-17, 6);
  });

  it("returns null with nothing loaded — a blank model must not be refused by this check", () => {
    expect(planBoundsFromModels([])).toBeNull();
    // and null really does mean "allow", which is the half that makes the null safe
    expect(checkBounds([[9999, 9999]], null).ok).toBe(true);
  });

  it("skips a model with no scene object rather than throwing mid-placement", () => {
    const models = [model(0, 0), { object: undefined } as unknown as BoundedModel];
    expect(planBoundsFromModels(models)).not.toBeNull();
    expect(planBoundsFromModels([{ object: undefined } as unknown as BoundedModel])).toBeNull();
  });
});

/**
 * The regression itself.
 *
 * These do not assert "the ground plane is excluded by name" — they assert the property that makes
 * that unnecessary: only loaded models are ever passed in, so a `2000 × 2000` shadow catcher sitting
 * in the same scene cannot reach the calculation at all.
 */
describe("the shadow ground plane cannot widen the model extent", () => {
  const ground = shadowGround();

  it("a scene-wide walk WOULD have blown the extent out to ±1000 m", () => {
    // Reproducing the old behaviour to prove the fixture is real: this is what expanding over every
    // mesh in the scene produced, and it is the number that made the check useless.
    const box = new THREE.Box3();
    for (const o of [model(0, 0).object, ground]) box.expandByObject(o);
    expect(box.min.x).toBeCloseTo(-1000, 3);
    expect(box.max.x).toBeCloseTo(1000, 3);
  });

  it("the model-scoped bounds stay at the building", () => {
    const b = planBoundsFromModels([model(0, 0, 10, 6)])!;
    expect(b.maxX).toBeCloseTo(5, 6);
    expect(b.minX).toBeCloseTo(-5, 6);
  });

  // The consequence, stated in the units the user experiences: a click 400 m out.
  it("a mis-click 400 m from the building is REFUSED with model bounds and ACCEPTED with scene bounds", () => {
    const misClick: [number, number][] = [[400, 0]];

    const modelBounds = planBoundsFromModels([model(0, 0, 10, 6)])!;
    expect(checkBounds(misClick, modelBounds).ok).toBe(false);

    // what the scene-wide walk yielded, expressed as PlanBounds
    const box = new THREE.Box3();
    for (const o of [model(0, 0).object, ground]) box.expandByObject(o);
    const sceneBounds = { minX: box.min.x, maxX: box.max.x, minZ: -box.max.z, maxZ: -box.min.z };
    expect(checkBounds(misClick, sceneBounds).ok).toBe(true);   // the bug, demonstrated
  });

  it("the refusal names a distance, so the message is not generic", () => {
    const b = planBoundsFromModels([model(0, 0, 10, 6)])!;
    const v = checkBounds([[400, 0]], b);
    expect(v.ok).toBe(false);
    if (!v.ok) expect(v.reason).toMatch(/\d+ m outside the model/);
  });

  it("legitimate site work just past the building still passes — the margin is intact", () => {
    const b = planBoundsFromModels([model(0, 0, 10, 6)])!;
    // 5 m (half-width) + 40 m is inside the 50 m margin
    expect(checkBounds([[45, 0]], b).ok).toBe(true);
    expect(BOUNDS_MARGIN_M).toBe(50);
  });
});

/**
 * The call site, asserted against source.
 *
 * Everything above tests a pure function that can only see what it is handed. None of it would
 * notice `app.ts` going back to walking the scene — which is the form the bug actually took, and the
 * form a later edit would most naturally reintroduce (a scene walk reads as the obvious way to get
 * "everything"). `modelPlanBounds` is a closure inside a 5k-line module that needs a WebGL renderer
 * and a Fragments worker to instantiate, so source text is the only reader available.
 *
 * Resolved from `process.cwd()` (= `apps/web`) — under happy-dom `import.meta.url` has no `file:`
 * scheme, the same constraint `shell/roadmapLanes.test.ts` works around.
 */
describe("app.ts asks the models, not the scene", () => {
  const src = readFileSync(resolve(process.cwd(), "src/viewer/app.ts"), "utf8");
  const fn = src.slice(src.indexOf("function modelPlanBounds"),
                       src.indexOf("async function finishDraft"));

  it("found the function to check — not vacuously green", () => {
    expect(fn.length).toBeGreaterThan(50);
    expect(fn).toContain("modelPlanBounds");
  });

  it("uses the model-scoped helper", () => {
    expect(fn).toContain("planBoundsFromModels");
  });

  it("does not traverse the scene for bounds", () => {
    expect(fn, "modelPlanBounds walks the scene again — the shadow ground plane is back in the extent")
      .not.toMatch(/scene\.three\.traverse/);
  });
});
