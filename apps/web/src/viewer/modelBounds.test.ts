import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import * as THREE from "three";
import { modelBox3, planBoundsFromModels, type BoundedModel } from "./modelBounds";
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

/**
 * `modelBox3` — the 3D population, and the two consumers that used to hand-roll it.
 *
 * These assert the CONSEQUENCE rather than the box, because the box being right is not what the
 * user experiences: the section box either clips or it does not, and the storey grid is either the
 * size of the building or twenty-one times it. A test on `box.max.x` passes for a clip computation
 * that later divides by the wrong factor; these do not.
 */
describe("modelBox3 — the section box and the storey grid measure the MODEL", () => {
  const SHADOW_HALF = 1000;   // the 2000 x 2000 catcher, half-extent

  it("returns a 3D box over the models and nothing else", () => {
    const b = modelBox3([model(0, 0, 10, 6)])!;
    expect(b.max.x).toBeCloseTo(5, 6);
    expect(b.max.y).toBeCloseTo(1.5, 6);   // BoxGeometry height 3, centred at y=0
  });

  it("is null for an empty population — a blank model is not a model of size zero", () => {
    expect(modelBox3([])).toBeNull();
    expect(modelBox3([{ object: undefined as unknown as THREE.Object3D }])).toBeNull();
  });

  // The defect, reproduced: a scene walk includes the catcher; the model population cannot.
  it("EXCLUDES the shadow ground even when it is in the scene beside the model", () => {
    const m = model(0, 0, 90, 95);
    const scene = new THREE.Object3D();
    scene.add(m.object, shadowGround());
    scene.updateMatrixWorld(true);

    const sceneWalk = new THREE.Box3();
    scene.traverse((o) => { const msh = o as THREE.Mesh; if (msh.isMesh) sceneWalk.expandByObject(msh); });
    expect(sceneWalk.max.x, "the scene walk really does swallow the catcher").toBeCloseTo(SHADOW_HALF, 0);

    expect(modelBox3([m])!.max.x, "modelBox3 must measure the model").toBeCloseTo(45, 6);
  });

  it("SECTION BOX: the clip planes land inside the building, not 700 m away", () => {
    // installSectionBox keeps the middle ~70%: half-extent = size * 0.35 about the centre.
    const half = (b: THREE.Box3) => b.getSize(new THREE.Vector3()).x * 0.35;
    const m = model(0, 0, 90, 95);
    const swallowed = new THREE.Box3().setFromCenterAndSize(
      new THREE.Vector3(0, 0, 0), new THREE.Vector3(SHADOW_HALF * 2, 3, SHADOW_HALF * 2));

    expect(half(swallowed), "the old behaviour: a 700 m clip about the origin").toBeCloseTo(700, 0);
    expect(half(modelBox3([m])!), "the clip must be inside a 90 m building").toBeCloseTo(31.5, 1);
    expect(half(modelBox3([m])!)).toBeLessThan(45);   // strictly inside the model — it clips something
  });

  it("STOREY GRID: sized to the building, not 21x it", () => {
    const gridSize = (b: THREE.Box3 | null) =>
      !b ? 20 : Math.max(b.getSize(new THREE.Vector3()).x, b.getSize(new THREE.Vector3()).z) * 1.1;
    const m = model(0, 0, 90, 95);
    const swallowed = new THREE.Box3().setFromCenterAndSize(
      new THREE.Vector3(0, 0, 0), new THREE.Vector3(SHADOW_HALF * 2, 3, SHADOW_HALF * 2));

    expect(gridSize(swallowed), "the old behaviour").toBeCloseTo(2200, 0);
    expect(gridSize(modelBox3([m])), "104.5 m for a 95 m building").toBeCloseTo(104.5, 1);
  });

  /**
   * CAMERA FIT -- the SIXTH site, and the one R41-MODEL-ALIGN named when it said to check
   * "section box, zoom-to-model and any bounding-box UI". The 2026-08-06 pass fixed the two above
   * and left this one, so `modelBox3` shipped with a third caller still hand-rolling the walk.
   *
   * `fitToModels` hands `box.getBoundingSphere(...)` to `controls.fitToSphere`, so the sphere's
   * RADIUS is the thing the user experiences -- it is how far the camera pulls back. Asserted here
   * rather than the box, for the same reason as the two tests above: a correct box handed to a fit
   * that takes the wrong sphere still frames the wrong thing.
   */
  it("CAMERA FIT: frames the building, not the 2 km catcher", () => {
    const radius = (b: THREE.Box3) => b.getBoundingSphere(new THREE.Sphere()).radius;
    const m = model(0, 0, 90, 95);
    const swallowed = new THREE.Box3().setFromCenterAndSize(
      new THREE.Vector3(0, 0, 0), new THREE.Vector3(SHADOW_HALF * 2, 3, SHADOW_HALF * 2));

    const wrong = radius(swallowed), right = radius(modelBox3([m])!);
    expect(wrong, "the old behaviour: a ~1.4 km sphere about the origin").toBeGreaterThan(1400);
    expect(right, "a 90 x 95 m building").toBeLessThan(70);
    // The consequence as the user met it: the building drew at ~5% of the framed view -- a speck.
    expect(right / wrong).toBeLessThan(0.05);
  });

  // THE TWIN, and the half that makes the fix above safe to make.
  //
  // `modelBox3`'s population is loaded fragments models, while the scene walk it replaced included
  // `isPoints` ON PURPOSE -- reference overlays and survey point clouds. So `fitToModels` passes
  // `referenceModels` explicitly. Without this test, a "fix" that simply dropped them would trade a
  // 2 km fit for one that silently ignores a survey scan, and every assertion above still passes.
  it("CAMERA FIT: a reference point cloud is still inside the fit", () => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(
      new Float32Array([200, 0, 0, 210, 0, 5]), 3));
    const pts = new THREE.Points(geo);
    pts.updateMatrixWorld(true);

    const withRef = modelBox3([model(0, 0, 90, 95), { object: pts }])!;
    expect(withRef.max.x, "a reference overlay must widen the fit").toBeCloseTo(210, 0);
    expect(modelBox3([model(0, 0, 90, 95)])!.max.x, "and the model alone does not").toBeCloseTo(45, 0);
  });

  // The population guard, in the same spirit as the one above for `modelPlanBounds`.
  it("no consumer walks the scene for bounds any more", () => {
    for (const f of ["measureSection.ts", "envTools.ts", "app.ts"]) {
      const src = readFileSync(resolve(process.cwd(), "src/viewer", f), "utf8");
      expect(src, `${f} walks the scene for a bounding box — the shadow ground is back in it`)
        .not.toMatch(/scene\.three\.traverse\((?:[^)]|\)(?!\s*;))*expandByObject/s);
      expect(src, `${f} should measure the model`).toMatch(/modelBox3\(/);
    }
  });
});
