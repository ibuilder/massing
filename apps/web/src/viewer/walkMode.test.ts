import { describe, expect, it } from "vitest";

import { WalkController } from "./walkMode";

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
