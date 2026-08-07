import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";
import { applyCameraProfile } from "./world";

/**
 * The wiring half. `cameraProfile.test.ts` proves the arithmetic; nothing proved the numbers reach
 * the camera, and the failure mode there is silent.
 *
 * **`updateProjectionMatrix()` is the whole risk.** three caches the projection matrix, so assigning
 * `cam.fov` and forgetting the call leaves the camera rendering exactly as before — every assertion
 * about `cam.fov` still passes, the view never changes, and it looks like the profile is wrong rather
 * than uncalled. Asserted directly below.
 *
 * `world.ts` builds a real WebGL world, but `applyCameraProfile` was deliberately written to take the
 * minimum structurally (`{ camera?: { three?: unknown } }`), so it can be exercised with a plain
 * three camera and no context — which is also what lets `walkMode.ts` call it without giving up its
 * three-free core.
 */

const world = (cam: unknown) => ({ camera: { three: cam } });

describe("applyCameraProfile puts the profile on the live camera", () => {
  it("writes fov, near and far", () => {
    const cam = new THREE.PerspectiveCamera(60, 1.6, 1, 1000);
    applyCameraProfile(world(cam), 375, 812);          // portrait phone
    expect(cam.fov).toBe(85);
    expect(cam.near).toBe(1);
    expect(cam.far).toBe(1000);
  });

  it("calls updateProjectionMatrix — without it the change is inert", () => {
    const cam = new THREE.PerspectiveCamera(60, 1.6, 1, 1000);
    const spy = vi.spyOn(cam, "updateProjectionMatrix");
    applyCameraProfile(world(cam), 375, 812);
    expect(spy, "fov changed but the projection was never rebuilt — the view will not move")
      .toHaveBeenCalled();
  });

  it("applies the walk depth range when asked", () => {
    const cam = new THREE.PerspectiveCamera(60, 1.6, 1, 1000);
    applyCameraProfile(world(cam), 1280, 800, true);
    expect(cam.near).toBe(0.1);
    expect(cam.far).toBe(200);
  });

  it("restores the orbit range when walk mode ends", () => {
    // The half that matters after the user has moved on: a walk range left on an orbit camera clips
    // any model wider than 200 m, in a mode they already exited.
    const cam = new THREE.PerspectiveCamera(60, 1.6, 1, 1000);
    applyCameraProfile(world(cam), 1280, 800, true);
    applyCameraProfile(world(cam), 1280, 800, false);
    expect(cam.near).toBe(1);
    expect(cam.far).toBe(1000);
  });

  it("does nothing when the profile already matches — no needless matrix rebuild", () => {
    const cam = new THREE.PerspectiveCamera(60, 1.6, 1, 1000);
    applyCameraProfile(world(cam), 1280, 800);          // desktop profile == the defaults
    const spy = vi.spyOn(cam, "updateProjectionMatrix");
    applyCameraProfile(world(cam), 1280, 800);
    expect(spy).not.toHaveBeenCalled();
  });

  it("leaves an orthographic camera alone — plan mode has no fov to set", () => {
    // The paired control for the isPerspectiveCamera guard. Writing `fov` onto an ortho camera is
    // not an error in JS; it is simply ignored, so a missing guard would be invisible here without
    // asserting the ortho case explicitly.
    const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 1000);
    const spy = vi.spyOn(cam, "updateProjectionMatrix");
    applyCameraProfile(world(cam), 375, 812);
    expect(cam.near).toBe(1);
    expect(spy).not.toHaveBeenCalled();
  });

  it("survives a world with no camera at all", () => {
    // Reached during teardown and before the world is built. A throw here would come out of a
    // ResizeObserver, where nothing catches it.
    expect(() => applyCameraProfile({}, 375, 812)).not.toThrow();
    expect(() => applyCameraProfile({ camera: {} }, 375, 812)).not.toThrow();
  });
});
