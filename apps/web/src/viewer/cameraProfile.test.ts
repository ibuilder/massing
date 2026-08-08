import { describe, expect, it } from "vitest";
import { cameraProfile, horizontalFov, viewportClass } from "./cameraProfile";

/**
 * R23-CAMERA-CLASS. The assertions that matter are the two the fix exists for — a phone gets a
 * usable horizontal view, and desktop is provably unchanged — plus the one that stops the near-plane
 * change from being made globally.
 *
 * The library default is `PerspectiveCamera(60, aspect, 1, 1e3)`, so every "before" number below is
 * what ships today, not a strawman.
 */

const PHONE: [number, number] = [375, 812];
const TABLET: [number, number] = [768, 1024];
const DESKTOP: [number, number] = [1280, 800];
const WIDE: [number, number] = [1920, 900];

describe("viewport class", () => {
  it("bands on the app's own breakpoints", () => {
    expect(viewportClass(375)).toBe("phone");
    expect(viewportClass(767)).toBe("phone");
    expect(viewportClass(768)).toBe("tablet");
    expect(viewportClass(1023)).toBe("tablet");
    expect(viewportClass(1024)).toBe("desktop");
  });

  it("falls back to desktop when the width is unmeasurable", () => {
    // A container measured at 0 during layout is a real state — `world.ts` skips resizing at 0x0 for
    // exactly that reason. Guessing "phone" there would narrow a desktop user's camera mid-load.
    expect(viewportClass(0)).toBe("desktop");
    expect(viewportClass(Number.NaN)).toBe("desktop");
  });
});

describe("the fix: a portrait phone gets a usable horizontal view", () => {
  it("widens the phone's horizontal fov well past today's 30 degrees", () => {
    const p = cameraProfile(...PHONE);
    const before = horizontalFov(60, ...PHONE);          // what ships today
    const after = horizontalFov(p.fov, ...PHONE);
    expect(Math.round(before)).toBe(30);                  // pins the defect, not a guess
    expect(after).toBeGreaterThan(44);
    expect(after / before).toBeGreaterThan(1.4);
  });

  it("clamps rather than fisheyeing — the unclamped answer is 127 degrees vertical", () => {
    const p = cameraProfile(...PHONE);
    expect(p.fov).toBeLessThanOrEqual(85);
    expect(p.fov).toBe(85);
  });
});

describe("it can only widen, never narrow — no silent regression", () => {
  it("leaves desktop exactly at the library default", () => {
    // The floor is 60 for this reason. A profile that computed a "better" 51 for desktop would ship
    // a regression as an improvement: nobody reports it as a bug, they just see less.
    expect(cameraProfile(...DESKTOP).fov).toBe(60);
    expect(cameraProfile(...WIDE).fov).toBe(60);
  });

  it("never returns a vertical fov below today's value, at any aspect", () => {
    // The property, over the whole range rather than three sampled points — a per-viewport check
    // cannot see a regression at an aspect nobody listed.
    for (let w = 240; w <= 3840; w += 40) {
      for (const h of [400, 800, 1200]) {
        expect(cameraProfile(w, h).fov,
          `${w}x${h} narrowed the view below the shipped default`).toBeGreaterThanOrEqual(60);
      }
    }
  });

  it("is monotonic — a narrower viewport never gets a narrower camera", () => {
    let prev = 0;
    for (let w = 3840; w >= 240; w -= 40) {
      const f = cameraProfile(w, 800).fov;
      expect(f, `fov went backwards at width ${w}`).toBeGreaterThanOrEqual(prev);
      prev = f;
    }
  });
});

describe("walk mode moves the near plane, and only walk mode does", () => {
  it("lets you approach a surface instead of clipping through it", () => {
    // walkMode.ts puts the eye at 1.65m. At near=1 everything within a metre of the eye is clipped,
    // so walking up to a wall makes it vanish — in the mode whose whole purpose is close inspection.
    expect(cameraProfile(...DESKTOP, { walk: true }).near).toBe(0.1);
  });

  it("leaves the orbit camera's near plane alone — the paired control", () => {
    // The important half. Making this global would trade a walk-mode defect for a rendering one:
    // guideUnderlay.ts lifts its plane 5mm, and at near=0.1 the resolvable depth gap passes 5mm
    // before 100m, so the underlay would z-fight on any model of real size.
    expect(cameraProfile(...DESKTOP).near).toBe(1);
    expect(cameraProfile(...PHONE).near).toBe(1);
    expect(cameraProfile(...TABLET).near).toBe(1);
  });

  it("pulls `far` in with `near` so the precision loss stays bounded", () => {
    const walk = cameraProfile(...DESKTOP, { walk: true });
    const orbit = cameraProfile(...DESKTOP);
    expect(walk.far).toBeLessThan(orbit.far);
    // Guard the actual property rather than the two numbers: the depth-precision argument is about
    // the RATIO, so a future edit that lowers `near` again must lower `far` too or fail here.
    expect(walk.far / walk.near).toBeLessThanOrEqual(orbit.far / orbit.near * 2);
  });

  it("still applies the viewport widening while walking", () => {
    // The two concerns are independent and both must survive being combined.
    expect(cameraProfile(...PHONE, { walk: true }).fov).toBe(cameraProfile(...PHONE).fov);
  });
});
