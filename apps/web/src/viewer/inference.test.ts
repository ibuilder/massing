import { describe, expect, it } from "vitest";
import { inferDirection, midpoint } from "./inference";

describe("E1 drawing inference", () => {
  const prev = { x: 0, z: 0 };

  it("snaps a near-horizontal cursor onto the X axis", () => {
    const inf = inferDirection(prev, { x: 5, z: 0.2 }, { tolDeg: 6 }); // ~2.3° off X
    expect(inf).not.toBeNull();
    expect(inf!.kind).toBe("axis-x");
    expect(inf!.z).toBeCloseTo(0, 6); // projected onto z=0
    expect(inf!.x).toBeCloseTo(5, 6);
  });

  it("snaps a near-vertical cursor onto the Z axis", () => {
    const inf = inferDirection(prev, { x: -0.1, z: 4 }, { tolDeg: 6 });
    expect(inf!.kind).toBe("axis-z");
    expect(inf!.x).toBeCloseTo(0, 6);
    expect(inf!.z).toBeCloseTo(4, 6);
  });

  it("returns null when the cursor is well off any axis (free draw)", () => {
    expect(inferDirection(prev, { x: 5, z: 5 }, { tolDeg: 6 })).toBeNull(); // 45° — nothing snaps
  });

  it("infers parallel to a reference edge", () => {
    // reference edge points along (1,1); a cursor nearly along (1,1) snaps parallel
    const inf = inferDirection(prev, { x: 3, z: 3.2 }, { tolDeg: 6, ref: { x: 1, z: 1 } });
    expect(inf!.kind).toBe("parallel");
    // projected onto the (1,1)/√2 line → x ≈ z
    expect(inf!.x).toBeCloseTo(inf!.z, 6);
  });

  it("infers perpendicular to a reference edge", () => {
    // ref along X; a near-vertical cursor is perpendicular to it (axis-z also fits, but perpendicular is
    // the same line — either way it lands on x=0). Use a ref along (1,1) so perpendicular is (-1,1).
    const inf = inferDirection(prev, { x: -3, z: 3.1 }, { tolDeg: 6, ref: { x: 1, z: 1 } });
    expect(["perpendicular", "parallel"]).toContain(inf!.kind);
    expect(inf!.x).toBeCloseTo(-inf!.z, 6); // on the (-1,1) line
  });

  it("prefers the closest axis when two are in range", () => {
    // 4° off X should pick axis-x, not axis-z
    const inf = inferDirection(prev, { x: 5, z: 0.35 }, { tolDeg: 10 });
    expect(inf!.kind).toBe("axis-x");
  });

  it("midpoint is the average", () => {
    expect(midpoint({ x: 0, z: 0 }, { x: 4, z: 2 })).toEqual({ x: 2, z: 1 });
  });
});
