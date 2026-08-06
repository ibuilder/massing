import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  GuideUnderlay, LEVEL_LIFT_M, UNDERLAY_EXTENSIONS, UNDERLAY_NAME, buildPlacement, clampOpacity,
  isSupportedImageName, mppFromTwoPoints, mppFromWidth, normaliseRotation, underlayPlanSize,
} from "./guideUnderlay";
import { planBoundsFromModels } from "./modelBounds";

const widthScale = (realWidthM: number) => ({ kind: "width" as const, realWidthM });

describe("A29-GUIDE-UNDERLAY — scale from a known width", () => {
  it("divides real width by pixel width", () => {
    const r = mppFromWidth(1000, 50);
    expect(r.ok && r.value).toBeCloseTo(0.05, 9);
  });

  // A silently-wrong scale is the one failure that poisons everything traced afterwards, and unlike
  // a mis-placed image it looks completely fine on screen. So each of these refuses with a reason.
  it("refuses a width that is missing, zero or negative", () => {
    for (const w of [0, -5, NaN, Infinity]) {
      const r = mppFromWidth(1000, w);
      expect(r.ok, `width ${w}`).toBe(false);
      if (!r.ok) expect(r.reason).toMatch(/greater than zero/);
    }
  });

  it("refuses a pixel width that is not a usable image", () => {
    for (const px of [0, 1, -100, 1.5, 40_000]) {
      expect(mppFromWidth(px, 50).ok, `px ${px}`).toBe(false);
    }
  });

  it("refuses an implausible scale and says it looks like a typo", () => {
    const tiny = mppFromWidth(1000, 0.01);          // 1e-5 m/px
    expect(tiny.ok).toBe(false);
    if (!tiny.ok) expect(tiny.reason).toMatch(/typo/);
    expect(mppFromWidth(1000, 500_000).ok).toBe(false);   // 500 m/px
  });

  it("accepts the extremes of the plausible band", () => {
    expect(mppFromWidth(1000, 0.1).ok).toBe(true);        // 1e-4 m/px exactly
    expect(mppFromWidth(1000, 100_000).ok).toBe(true);    // 100 m/px exactly
  });
});

describe("A29-GUIDE-UNDERLAY — scale from two points", () => {
  it("divides the known distance by the pixel separation", () => {
    const r = mppFromTwoPoints({ x: 100, y: 100 }, { x: 400, y: 500 }, 25);   // 500 px
    expect(r.ok && r.value).toBeCloseTo(0.05, 9);
  });

  // Dividing by a zero pixel distance yields Infinity — an underlay the size of the solar system,
  // or nothing at all, depending on the driver. It is the pick a real user makes by double-clicking.
  it("refuses two picks at the same spot rather than dividing by zero", () => {
    const r = mppFromTwoPoints({ x: 7, y: 7 }, { x: 7, y: 7 }, 10);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toMatch(/same spot/);
  });

  it("refuses non-finite picks and non-positive distances", () => {
    expect(mppFromTwoPoints({ x: NaN, y: 0 }, { x: 10, y: 0 }, 5).ok).toBe(false);
    expect(mppFromTwoPoints({ x: 0, y: 0 }, { x: 100, y: 0 }, 0).ok).toBe(false);
    expect(mppFromTwoPoints({ x: 0, y: 0 }, { x: 100, y: 0 }, -3).ok).toBe(false);
  });

  it("agrees with the width method when they describe the same image", () => {
    // 1000 px wide, 50 m across => 0.05 m/px, and a 500 px span is therefore 25 m.
    const byWidth = mppFromWidth(1000, 50);
    const byPoints = mppFromTwoPoints({ x: 0, y: 0 }, { x: 500, y: 0 }, 25);
    expect(byWidth.ok && byPoints.ok).toBe(true);
    if (byWidth.ok && byPoints.ok) expect(byPoints.value).toBeCloseTo(byWidth.value, 12);
  });
});

describe("A29-GUIDE-UNDERLAY — size, opacity, rotation", () => {
  it("preserves aspect ratio by construction — one scale, both axes", () => {
    const s = underlayPlanSize(1600, 900, 0.05);
    expect(s.ok).toBe(true);
    if (s.ok) {
      expect(s.value.widthM).toBeCloseTo(80, 9);
      expect(s.value.heightM).toBeCloseTo(45, 9);
      expect(s.value.widthM / s.value.heightM).toBeCloseTo(1600 / 900, 9);
    }
  });

  it("clamps opacity instead of refusing — a slider cannot produce a meaningful error", () => {
    expect(clampOpacity(-1)).toBe(0);
    expect(clampOpacity(2)).toBe(1);
    expect(clampOpacity(0.35)).toBeCloseTo(0.35, 9);
    expect(clampOpacity(NaN)).toBe(0.5);
    expect(clampOpacity(0)).toBe(0);          // "hide it for a moment" is legitimate, not an error
  });

  it("normalises rotation into [0,360) including negatives", () => {
    expect(normaliseRotation(-90)).toBe(270);
    expect(normaliseRotation(450)).toBe(90);
    expect(normaliseRotation(360)).toBe(0);
    expect(normaliseRotation(NaN)).toBe(0);
  });

  it("knows which files a browser can decode", () => {
    for (const ext of UNDERLAY_EXTENSIONS) expect(isSupportedImageName(`plan.${ext}`)).toBe(true);
    expect(isSupportedImageName("PLAN.PNG")).toBe(true);
    for (const n of ["plan.pdf", "plan.ifc", "plan.dwg", "plan", "plan.png.exe"]) {
      expect(isSupportedImageName(n), n).toBe(false);
    }
  });
});

describe("A29-GUIDE-UNDERLAY — buildPlacement is the only arithmetic the panel needs", () => {
  it("assembles a full placement from a width scale", () => {
    const r = buildPlacement({ pixelW: 1000, pixelH: 500, scale: widthScale(50), levelZ: 3 });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.widthM).toBeCloseTo(50, 9);
    expect(r.value.heightM).toBeCloseTo(25, 9);
    expect(r.value.opacity).toBe(0.5);          // a guide defaults to see-through
    expect(r.value.rotationDeg).toBe(0);
  });

  // A guide sitting exactly at the level z-fights the slab it is being traced against — the artefact
  // reads as a rendering bug and makes the guide unusable at precisely the moment it is needed.
  it("lifts the plane fractionally above its level", () => {
    const r = buildPlacement({ pixelW: 1000, pixelH: 500, scale: widthScale(50), levelZ: 3 });
    expect(r.ok && r.value.levelZ).toBeCloseTo(3 + LEVEL_LIFT_M, 9);
    expect(LEVEL_LIFT_M).toBeGreaterThan(0);
    expect(LEVEL_LIFT_M).toBeLessThan(0.05);    // still reads as "on" the level
  });

  it("propagates the FIRST refusal rather than producing a half-valid placement", () => {
    const r = buildPlacement({ pixelW: 1000, pixelH: 500, scale: widthScale(0), rotationDeg: 45 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toMatch(/greater than zero/);
  });

  it("defaults every optional field instead of emitting NaN", () => {
    const r = buildPlacement({ pixelW: 800, pixelH: 600, scale: widthScale(40),
                               offsetE: NaN, offsetN: undefined, rotationDeg: NaN, opacity: NaN });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    for (const v of Object.values(r.value)) expect(Number.isFinite(v)).toBe(true);
    expect(r.value.offsetE).toBe(0);
    expect(r.value.offsetN).toBe(0);
  });
});

describe("A29-GUIDE-UNDERLAY — the scene object is a picture, not geometry", () => {
  const place = () => {
    const r = buildPlacement({ pixelW: 1000, pixelH: 500, scale: widthScale(50), levelZ: 0 });
    if (!r.ok) throw new Error(r.reason);
    return r.value;
  };
  const tex = () => new THREE.Texture();

  it("adds a named plane to the scene and removes it on clear", () => {
    const scene = new THREE.Scene();
    const u = new GuideUnderlay(scene);
    expect(u.hasImage).toBe(false);
    u.setTexture(tex(), place());
    expect(u.hasImage).toBe(true);
    expect(scene.getObjectByName(UNDERLAY_NAME)).toBeTruthy();
    u.clear();
    expect(scene.getObjectByName(UNDERLAY_NAME)).toBeFalsy();
    expect(u.hasImage).toBe(false);
  });

  it("clear is safe when nothing is loaded, and idempotent", () => {
    const u = new GuideUnderlay(new THREE.Scene());
    expect(() => { u.clear(); u.clear(); }).not.toThrow();
  });

  it("replaces rather than stacking when a second image is loaded", () => {
    const scene = new THREE.Scene();
    const u = new GuideUnderlay(scene);
    u.setTexture(tex(), place());
    u.setTexture(tex(), place());
    const found = scene.children.filter((c) => c.name === UNDERLAY_NAME);
    expect(found).toHaveLength(1);
  });

  /**
   * **A negative assertion needs a positive control, or it is measuring its own setup.**
   *
   * If you are writing an "X does not happen" test, this is the paragraph to read.
   *
   * It is a guide: if it can be picked it will be snapped to, selected and measured against. The
   * first version of this test passed **whether or not the guard existed** — a mutation removing
   * `mesh.raycast = () => {}` stayed green, because calling `mesh.raycast(...)` by hand on a mesh
   * whose world matrix was never updated intersects nothing either way. It asserted an empty array
   * that was empty *for the wrong reason*, and it would have shipped green having tested nothing.
   *
   * So the CONTROL comes first: an identical plane **without** the guard must be hit by this exact
   * ray. Only then does an empty result mean "the guard worked" rather than "the ray missed".
   *
   * This is the same defect as the picking benchmark that reported a confident p50 with `hits: 0`,
   * and the same family as happy-dom's `DataTransfer` vouching for a drop the browser silently
   * refuses (`railDrag.test.ts`). In each case the instrument never engaged and the result looked
   * like an answer. **Assert that the instrument engaged, never the output alone.**
   */
  it("is not a raycast target, and the ray is proven to be aimed at it", () => {
    const scene = new THREE.Scene();
    new GuideUnderlay(scene).setTexture(tex(), place());
    const mesh = scene.getObjectByName(UNDERLAY_NAME) as THREE.Mesh;
    scene.updateMatrixWorld(true);
    const rc = new THREE.Raycaster(new THREE.Vector3(0, 10, 0), new THREE.Vector3(0, -1, 0));

    const control = new THREE.Mesh(mesh.geometry, new THREE.MeshBasicMaterial());
    control.rotation.copy(mesh.rotation);
    control.position.copy(mesh.position);
    control.updateMatrixWorld(true);
    expect(rc.intersectObject(control, false).length,
      "the ray misses even an unguarded plane — this test would pass for the wrong reason")
      .toBeGreaterThan(0);

    expect(rc.intersectObject(mesh, false),
      "the guide is pickable — it will be snapped to and selected").toEqual([]);
  });

  it("never occludes the model it is traced against", () => {
    const scene = new THREE.Scene();
    new GuideUnderlay(scene).setTexture(tex(), place());
    const mesh = scene.getObjectByName(UNDERLAY_NAME) as THREE.Mesh;
    const mat = mesh.material as THREE.MeshBasicMaterial;
    expect(mat.transparent).toBe(true);
    expect(mat.depthWrite).toBe(false);
    expect(mesh.renderOrder).toBeLessThan(0);
  });

  it("maps plan N to -z and E to +x, the draft pipeline's convention", () => {
    const scene = new THREE.Scene();
    const u = new GuideUnderlay(scene);
    const p = place();
    u.setTexture(tex(), { ...p, offsetE: 10, offsetN: 4 });
    const mesh = scene.getObjectByName(UNDERLAY_NAME)!;
    expect(mesh.position.x).toBeCloseTo(10, 9);
    expect(mesh.position.z).toBeCloseTo(-4, 9);
  });

  it("apply() moves and fades without recreating the mesh", () => {
    const scene = new THREE.Scene();
    const u = new GuideUnderlay(scene);
    u.setTexture(tex(), place());
    const before = scene.getObjectByName(UNDERLAY_NAME);
    u.apply({ ...place(), offsetE: 25, opacity: 0.2 });
    const after = scene.getObjectByName(UNDERLAY_NAME);
    expect(after).toBe(before);                       // same object
    expect(after!.position.x).toBeCloseTo(25, 9);
    expect(((after as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity).toBeCloseTo(0.2, 9);
  });

  it("apply() on an empty underlay is a no-op, not a throw", () => {
    expect(() => new GuideUnderlay(new THREE.Scene()).apply(place())).not.toThrow();
  });

  /**
   * The reason `modelBounds.ts` exists. A 50 m guide plane in the scene must not become the model's
   * plan extent, or the mis-click guard drifts exactly the way the shadow-catcher made it drift.
   */
  it("does not enter the model's plan extent", () => {
    const scene = new THREE.Scene();
    new GuideUnderlay(scene).setTexture(tex(), place());
    // the underlay is in the SCENE but is not a loaded model, so bounds ignore it entirely
    expect(planBoundsFromModels([])).toBeNull();

    const building = new THREE.Mesh(new THREE.BoxGeometry(10, 3, 6));
    building.updateMatrixWorld(true);
    const b = planBoundsFromModels([{ object: building }])!;
    expect(b.maxX).toBeCloseTo(5, 6);                 // the building, not the 50 m guide
  });
});
