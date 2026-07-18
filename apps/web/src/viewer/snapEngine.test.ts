import { describe, expect, it } from "vitest";
import { applyDynamicInput, polarConstrain, resolveSnap, segmentSnaps } from "./snapEngine";

describe("SNAP-KIT resolveSnap", () => {
  const cands = [
    { x: 0, z: 0, kind: "endpoint" as const },
    { x: 5, z: 0, kind: "endpoint" as const },
    { x: 2.5, z: 0, kind: "midpoint" as const },
    { x: 10, z: 10, kind: "center" as const },
  ];

  it("returns the nearest candidate within tolerance", () => {
    const r = resolveSnap({ x: 0.1, z: 0.05 }, cands, 0.3);
    expect(r).not.toBeNull();
    expect(r!.kind).toBe("endpoint");
    expect(r!.x).toBe(0);
  });

  it("returns null when nothing is within tolerance", () => {
    expect(resolveSnap({ x: 100, z: 100 }, cands, 0.3)).toBeNull();
  });

  it("breaks a near-tie by priority (endpoint beats midpoint at equal range)", () => {
    // cursor equidistant from the 5,0 endpoint and the 2.5,0 midpoint would be at 3.75,0;
    // place it exactly there so both are 1.25 away → endpoint (higher priority) wins.
    const r = resolveSnap({ x: 3.75, z: 0 }, cands, 5);
    expect(r!.kind).toBe("endpoint");
  });

  it("prefers a clearly-closer point regardless of priority", () => {
    const r = resolveSnap({ x: 2.5, z: 0.01 }, cands, 1);   // right on the midpoint
    expect(r!.kind).toBe("midpoint");
  });
});

describe("SNAP-KIT segmentSnaps", () => {
  it("emits endpoints + midpoints for an open polyline", () => {
    const s = segmentSnaps([{ x: 0, z: 0 }, { x: 4, z: 0 }]);
    expect(s).toContainEqual({ x: 0, z: 0, kind: "endpoint" });
    expect(s).toContainEqual({ x: 4, z: 0, kind: "endpoint" });
    expect(s).toContainEqual({ x: 2, z: 0, kind: "midpoint" });
  });

  it("closes the loop when asked (adds the last→first midpoint)", () => {
    const sq = [{ x: 0, z: 0 }, { x: 4, z: 0 }, { x: 4, z: 4 }, { x: 0, z: 4 }];
    const open = segmentSnaps(sq, false).filter((c) => c.kind === "midpoint").length;
    const closed = segmentSnaps(sq, true).filter((c) => c.kind === "midpoint").length;
    expect(closed).toBe(open + 1);
  });
});

describe("SNAP-KIT polarConstrain", () => {
  const O = { x: 0, z: 0 };

  it("snaps a near-45° bearing to exactly 45° and preserves distance", () => {
    const r = polarConstrain(O, { x: 5, z: 5.3 }, 45, 6);   // ~46.7° → snaps to 45
    expect(r.locked).toBe(true);
    expect(r.angle).toBe(45);
    // distance preserved: |cursor| == |result|
    expect(Math.hypot(r.x, r.z)).toBeCloseTo(Math.hypot(5, 5.3), 6);
    expect(r.x).toBeCloseTo(r.z, 6);                          // 45° → x == z
  });

  it("does not lock when the bearing is outside tolerance", () => {
    const r = polarConstrain(O, { x: 5, z: 1 }, 45, 4);      // ~11°, >4° from 0
    expect(r.locked).toBe(false);
    expect(r.x).toBe(5); expect(r.z).toBe(1);
  });

  it("locks a horizontal cursor to 0°", () => {
    const r = polarConstrain(O, { x: 7, z: 0.05 }, 90, 5);
    expect(r.locked).toBe(true); expect(r.angle).toBe(0);
    expect(r.z).toBeCloseTo(0, 6);
  });

  it("returns raw cursor at the origin or when disabled", () => {
    expect(polarConstrain(O, O, 45).locked).toBe(false);
    const off = polarConstrain(O, { x: 3, z: 3 }, 0);
    expect(off.locked).toBe(false); expect(off.x).toBe(3);
  });
});

describe("SNAP-KIT applyDynamicInput", () => {
  const O = { x: 0, z: 0 };

  it("distance-only keeps the cursor bearing, sets the length", () => {
    const p = applyDynamicInput(O, { x: 3, z: 4 }, { distance: 10 });   // bearing of 3,4 (len 5) → len 10
    expect(Math.hypot(p.x, p.z)).toBeCloseTo(10, 6);
    expect(p.x).toBeCloseTo(6, 6); expect(p.z).toBeCloseTo(8, 6);       // scaled 2×
  });

  it("angle-only keeps the cursor distance, sets the bearing", () => {
    const p = applyDynamicInput(O, { x: 5, z: 0 }, { angle: 90 });      // len 5, force 90° (+z)
    expect(p.x).toBeCloseTo(0, 6); expect(p.z).toBeCloseTo(5, 6);
  });

  it("distance + angle gives an exact point", () => {
    const p = applyDynamicInput(O, { x: 1, z: 1 }, { distance: 4, angle: 0 });
    expect(p.x).toBeCloseTo(4, 6); expect(p.z).toBeCloseTo(0, 6);
  });

  it("passes the raw cursor through when nothing (or invalid) is typed", () => {
    expect(applyDynamicInput(O, { x: 2, z: 3 }, {})).toEqual({ x: 2, z: 3 });
    expect(applyDynamicInput(O, { x: 2, z: 3 }, { distance: -1 })).toEqual({ x: 2, z: 3 });
  });
});
