/**
 * R38-PUSHPULL — the pure half of the gesture: what a drag commits, and how the ghost stretches.
 *
 * What is deliberately asserted:
 *   * a click-and-release (sub-5 mm drag) commits NOTHING — the gesture must be safe to fumble;
 *   * the committed depth is clamped above zero — the ghost can never show a solid the server
 *     would refuse (`set_extrusion_depth` raises on depth <= 0);
 *   * the stretch is BASE-ANCHORED: whatever the delta, the bottom face stays exactly where the
 *     element stands. A centre-scaled ghost would show the element floating up as it grows —
 *     a preview disagreeing with what the recipe will do.
 */
import { describe, expect, it } from "vitest";
import { pulledDepth, stretchTransform } from "./pushPull";

describe("pulledDepth — what a drag commits", () => {
  it("a real drag adds the delta to the current depth", () => {
    expect(pulledDepth(3.0, 0.5)).toBe(3.5);
    expect(pulledDepth(3.0, -1.0)).toBe(2.0);
  });

  it("a fumbled click (sub-5 mm) commits nothing", () => {
    expect(pulledDepth(3.0, 0)).toBeNull();
    expect(pulledDepth(3.0, 0.004)).toBeNull();
    expect(pulledDepth(3.0, -0.004)).toBeNull();
  });

  it("a hard downward drag clamps to the minimum instead of inverting", () => {
    expect(pulledDepth(3.0, -5.0)).toBe(0.02);
  });

  it("a degenerate start depth refuses rather than manufacturing a number", () => {
    expect(pulledDepth(0, 1)).toBeNull();
    expect(pulledDepth(-1, 1)).toBeNull();
    expect(pulledDepth(Number.NaN, 1)).toBeNull();
  });
});

describe("stretchTransform — the ghost is base-anchored", () => {
  it("the base never moves, whatever the delta", () => {
    // base = centerY - (h0 * scaleY) / 2 must equal minY for any delta
    for (const delta of [-1.5, -0.2, 0, 0.7, 3.0]) {
      const t = stretchTransform(3.0, delta, 10.0);
      expect(10.0 + (3.0 * t.scaleY) / 2).toBeCloseTo(t.centerY, 10);
    }
  });

  it("zero delta is the identity", () => {
    const t = stretchTransform(3.0, 0, 10.0);
    expect(t.scaleY).toBe(1);
    expect(t.centerY).toBeCloseTo(11.5, 10);
  });

  it("collapse is floored, so the ghost never renders an impossible solid", () => {
    const t = stretchTransform(3.0, -10.0, 0);
    expect(3.0 * t.scaleY).toBeCloseTo(0.02, 10);
  });
});
