import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { installWalkMode, WalkController } from "./walkMode";

describe("WalkController (WALK-MODE core)", () => {
  it("walks forward along -Z at yaw 0 at walk speed", () => {
    const c = new WalkController();
    c.pos = { x: 0, y: 1.65, z: 0 };
    c.keyDown("KeyW");
    c.step(1.0);
    expect(c.pos.z).toBeCloseTo(-3.5, 5);         // 3.5 m/s × 1 s
    expect(c.pos.x).toBeCloseTo(0, 5);
    expect(c.pos.y).toBeCloseTo(1.65, 5);         // walking, not flying — y held
  });

  it("strafes +X with D at yaw 0 and runs with Shift", () => {
    const c = new WalkController();
    c.keyDown("KeyD");
    c.step(1.0);
    expect(c.pos.x).toBeCloseTo(3.5, 5);
    c.pos = { x: 0, y: 1.65, z: 0 };
    c.keyDown("ShiftLeft");
    c.step(1.0);
    expect(c.pos.x).toBeCloseTo(3.5 * 2.5, 5);    // run multiplier
  });

  it("heading follows yaw: at yaw 90° forward is -X", () => {
    const c = new WalkController();
    c.yaw = Math.PI / 2;
    c.keyDown("KeyW");
    c.step(1.0);
    expect(c.pos.x).toBeCloseTo(-3.5, 5);
    expect(c.pos.z).toBeCloseTo(0, 5);
  });

  it("mouse-look clamps pitch to ±85° and never flips", () => {
    const c = new WalkController();
    c.look(0, -100000);                            // huge upward drag
    expect(c.pitch).toBeLessThanOrEqual((85 * Math.PI) / 180 + 1e-9);
    c.look(0, 200000);                             // huge downward drag
    expect(c.pitch).toBeGreaterThanOrEqual(-(85 * Math.PI) / 180 - 1e-9);
  });

  it("target sits ahead along the heading with pitch applied", () => {
    const c = new WalkController();
    c.pos = { x: 0, y: 1.65, z: 0 };
    const level = c.target();
    expect(level.z).toBeCloseTo(-1, 5);            // 1 m ahead along -Z
    expect(level.y).toBeCloseTo(1.65, 5);
    c.pitch = Math.PI / 4;                          // look 45° up
    const up = c.target();
    expect(up.y).toBeCloseTo(1.65 + Math.SQRT1_2, 5);
    expect(up.z).toBeCloseTo(-Math.SQRT1_2, 5);
  });

  it("E raises and Q lowers eye height; keyUp stops movement", () => {
    const c = new WalkController();
    c.keyDown("KeyE");
    c.step(1.0);
    expect(c.pos.y).toBeCloseTo(1.65 + 3.5, 5);
    c.keyUp("KeyE");
    c.step(1.0);
    expect(c.pos.y).toBeCloseTo(1.65 + 3.5, 5);    // no drift after release
    expect(c.moving()).toBe(false);
  });

  it("opposed keys cancel (W+S stands still)", () => {
    const c = new WalkController();
    c.keyDown("KeyW");
    c.keyDown("KeyS");
    c.step(1.0);
    expect(c.pos.z).toBeCloseTo(0, 5);
  });
});

/**
 * R23-CAMERA-CLASS — the depth range must follow walk mode in AND out.
 *
 * Found by mutation: deleting the restore on exit passed all 433 viewer tests. Only `WalkController`
 * had coverage — the headless core — and `installWalkMode` itself was never driven, so everything
 * the toggle does to the camera was unguarded.
 *
 * The exit half is the one worth holding. A walk range (`near 0.1 / far 200`) left on an orbit camera
 * clips any model wider than 200 m and z-fights `guideUnderlay`'s 5 mm lift past ~100 m — a rendering
 * bug in a mode the user has already left, which is close to impossible to attribute back to here.
 */
describe("installWalkMode drives the camera depth range", () => {
  function harness() {
    const cam = new THREE.PerspectiveCamera(60, 1.6, 1, 1000);
    const controls = {
      getPosition: (v: THREE.Vector3) => v.set(0, 1.65, 0),
      getTarget: (v: THREE.Vector3) => v.set(0, 1.65, -1),
      setLookAt: () => {},
    };
    const canvas = document.createElement("canvas");
    Object.defineProperty(canvas, "clientWidth", { value: 1280 });
    Object.defineProperty(canvas, "clientHeight", { value: 800 });
    let click: (() => void) | null = null;
    const toolBtn = (_i: string, _t: string, onClick: (b: HTMLButtonElement) => void) => {
      const b = document.createElement("button");
      click = () => onClick(b);
      return b;
    };
    const api = installWalkMode({
      viewer: { world: { camera: { three: cam, controls } } },
      canvas, toolBtn, setStatus: () => {},
    } as unknown as Parameters<typeof installWalkMode>[0]);
    return { cam, api, toggle: () => click?.() };
  }

  it("drops the near plane on enter so you can approach a surface", () => {
    const h = harness();
    expect(h.cam.near, "precondition: the shipped default").toBe(1);
    h.toggle();
    expect(h.api.walking()).toBe(true);
    expect(h.cam.near).toBe(0.1);
    expect(h.cam.far).toBe(200);
    h.api.exit();
  });

  it("restores the orbit range on exit — the mutation that survived until now", () => {
    const h = harness();
    h.toggle();
    h.api.exit();
    expect(h.api.walking()).toBe(false);
    expect(h.cam.near, "a walk near-plane left on the orbit camera z-fights past ~100m").toBe(1);
    expect(h.cam.far, "...and clips any model wider than 200m").toBe(1000);
  });
});
