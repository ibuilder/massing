import { describe, expect, it } from "vitest";
import { KEY_SHORTCUTS } from "./keysDyn";
import { resolveSnap, type SnapKind } from "./snapEngine";
import {
  ALL_OVERRIDE_KINDS, OVERRIDE_CODES, OVERRIDE_LABEL, createSnapOverride, overrideCandidates,
  type OverrideKind, type PlanBox,
} from "./snapOverride";

// A 4 x 2 footprint, axis-aligned: x 0..4, z 0..2.
const BOX: PlanBox = { minX: 0, maxX: 4, minZ: 0, maxZ: 2 };

describe("AUTH-SNAP-OVERRIDE — the code table is a partition, not a list", () => {
  // The override codes share the two-letter buffer with the draw-tool shortcuts. If they ever
  // overlap, one of the two features silently stops working for that code and nothing says so.
  it("no override code is also a draw-tool code", () => {
    const tools = new Set(KEY_SHORTCUTS.map(([code]) => code));
    const clashes = Object.keys(OVERRIDE_CODES).filter((c) => tools.has(c));
    expect(clashes).toEqual([]);
  });

  it("every override code is exactly two upper-case letters, like the tool codes it shares a buffer with", () => {
    for (const code of Object.keys(OVERRIDE_CODES)) expect(code).toMatch(/^[A-Z]{2}$/);
  });

  // The reason there is no `IN` (intersection) or grid code: nothing can produce one, so the override
  // would resolve to nothing 100% of the time. This asserts the two sets are the SAME set, in both
  // directions — a code with no producer and a producer with no code both fail here.
  it("the kinds a code can name are exactly the kinds a producer can emit", () => {
    expect([...new Set(Object.values(OVERRIDE_CODES))].sort()).toEqual([...ALL_OVERRIDE_KINDS].sort());
  });

  it("every override kind has a human label", () => {
    for (const k of ALL_OVERRIDE_KINDS) expect(OVERRIDE_LABEL[k]).toBeTruthy();
  });

  // Iterates the CODES rather than ALL_OVERRIDE_KINDS on purpose. A code added without extending
  // the kind list is invisible to the loop above — which is precisely the mistake this catches.
  it("every kind a code names has a label, reached from the code side", () => {
    for (const [code, kind] of Object.entries(OVERRIDE_CODES)) {
      expect(OVERRIDE_LABEL[kind], `code ${code} → ${kind}`).toBeTruthy();
    }
  });

  it("`intersection` and `grid` are deliberately absent — a control that can never resolve is worse than none", () => {
    const named: string[] = Object.values(OVERRIDE_CODES);
    expect(named).not.toContain("intersection");
    expect(named).not.toContain("grid");
  });
});

describe("AUTH-SNAP-OVERRIDE — overrideCandidates emits the asked-for kind and nothing else", () => {
  const from = { x: 2, z: 8 };      // well off the box, so a perpendicular foot lands on the far edge
  const cursor = { x: 2, z: 1 };

  // The producer half of the partition above: every kind except `none` must actually yield points.
  for (const kind of ALL_OVERRIDE_KINDS.filter((k) => k !== "none")) {
    it(`${kind}: yields candidates, all of that kind`, () => {
      const c = overrideCandidates(kind, BOX, cursor, from);
      expect(c.length).toBeGreaterThan(0);
      expect(new Set(c.map((p) => p.kind))).toEqual(new Set([kind as SnapKind]));
    });
  }

  it("none: yields nothing — its meaning is 'do not snap', not 'search harder'", () => {
    expect(overrideCandidates("none", BOX, cursor, from)).toEqual([]);
  });

  it("endpoint: the four footprint corners", () => {
    const c = overrideCandidates("endpoint", BOX, cursor, from);
    expect(c).toHaveLength(4);
    expect(c.map((p) => [p.x, p.z]).sort()).toEqual([[0, 0], [0, 2], [4, 0], [4, 2]].sort());
  });

  it("center: the single footprint centre", () => {
    expect(overrideCandidates("center", BOX, cursor, from))
      .toEqual([{ x: 2, z: 1, kind: "center" }]);
  });

  it("midpoint: one per edge, and none of them is a corner", () => {
    const c = overrideCandidates("midpoint", BOX, cursor, from);
    expect(c).toHaveLength(4);
    expect(c.map((p) => [p.x, p.z]).sort()).toEqual([[0, 1], [2, 0], [2, 2], [4, 1]].sort());
  });

  it("perpendicular: returns nothing without a previous point, rather than guessing one", () => {
    expect(overrideCandidates("perpendicular", BOX, cursor, null)).toEqual([]);
  });

  it("perpendicular: the foot from a point due north of the box is on the near and far edges", () => {
    const c = overrideCandidates("perpendicular", BOX, { x: 2, z: 1 }, { x: 2, z: 8 });
    // from (2,8): feet on z=0 and z=2 at x=2. The x=0 and x=4 edges take the foot at z=8, off-segment.
    expect(c.map((p) => [p.x, p.z]).sort()).toEqual([[2, 0], [2, 2]].sort());
  });

  it("perpendicular: an off-segment foot is DROPPED, never clamped to the endpoint", () => {
    // from (99, 1) — the foot on the z=0 edge would be x=99, way past the corner at x=4.
    const c = overrideCandidates("perpendicular", BOX, { x: 2, z: 1 }, { x: 99, z: 1 });
    for (const p of c) expect(p.x).toBeLessThanOrEqual(4 + 1e-9);
    // a clamped implementation would return the corner (4,0) and call it a perpendicular
    expect(c.map((p) => [p.x, p.z])).not.toContainEqual([4, 0]);
  });

  it("nearest: projects the cursor onto each edge, clamped", () => {
    const c = overrideCandidates("nearest", BOX, { x: 1, z: 0.25 }, from);
    expect(c).toHaveLength(4);
    expect(c.map((p) => [p.x, p.z])).toContainEqual([1, 0]);   // straight down onto the z=0 edge
  });
});

describe("AUTH-SNAP-OVERRIDE — resolveSnap honours the filter without falling back", () => {
  const cands = [
    { x: 0, z: 0, kind: "endpoint" as const },
    { x: 0.05, z: 0, kind: "midpoint" as const },
  ];

  it("returns the filtered kind even when a nearer candidate of another kind exists", () => {
    const r = resolveSnap({ x: 0.05, z: 0 }, cands, 1, "endpoint");
    expect(r!.kind).toBe("endpoint");
    expect(r!.x).toBe(0);
  });

  // The whole point of the item: a snap that lies about its kind is worse than no snap.
  it("returns NULL when nothing of the asked-for kind is in range — it does not substitute", () => {
    expect(resolveSnap({ x: 0, z: 0 }, cands, 1, "perpendicular")).toBeNull();
  });

  it("without a filter it behaves exactly as before", () => {
    const r = resolveSnap({ x: 0.05, z: 0 }, cands, 1);
    expect(r!.kind).toBe("midpoint");
  });
});

describe("AUTH-SNAP-OVERRIDE — one shot means one shot", () => {
  it("arms from a code, case-insensitively", () => {
    const o = createSnapOverride();
    expect(o.arm("pe")).toBe("perpendicular");
    expect(o.peek()).toBe("perpendicular");
  });

  it("ignores a code that is not an override, and leaves any armed state alone", () => {
    const o = createSnapOverride();
    o.arm("PE");
    expect(o.arm("WA")).toBeNull();          // a draw-tool code, handled elsewhere
    expect(o.peek()).toBe("perpendicular");
  });

  it("consume returns the kind and disarms", () => {
    const o = createSnapOverride();
    o.arm("MI");
    expect(o.consume()).toBe("midpoint");
    expect(o.peek()).toBeNull();
    expect(o.consume()).toBeNull();
  });

  // A one-shot that survived a failed pick would silently steer the NEXT click too — the user would
  // have to notice a snap they never asked for on a click they thought was ordinary.
  it("is spent by the pick that reads it even when that pick found no such snap", () => {
    const o = createSnapOverride();
    o.arm("PE");
    const kind = o.consume();                                       // the pick reads it…
    expect(overrideCandidates(kind!, BOX, { x: 2, z: 1 }, null)).toEqual([]);   // …and finds nothing
    expect(o.peek()).toBeNull();                                    // still spent
  });

  it("clear disarms, and Escape can call it safely when nothing is armed", () => {
    const o = createSnapOverride();
    o.clear();
    expect(o.peek()).toBeNull();
    o.arm("NO");
    o.clear();
    expect(o.peek()).toBeNull();
  });

  it("notifies a subscriber on arm, consume and clear — the HUD cannot go stale", () => {
    const seen: (OverrideKind | null)[] = [];
    const o = createSnapOverride();
    o.subscribe((k) => seen.push(k));
    o.arm("CE");
    o.consume();
    o.arm("NE");
    o.clear();
    expect(seen).toEqual(["center", null, "nearest", null]);
  });

  it("does not fire the subscriber for a no-op clear", () => {
    const seen: (OverrideKind | null)[] = [];
    const o = createSnapOverride();
    o.subscribe((k) => seen.push(k));
    o.clear();
    expect(seen).toEqual([]);
  });
});
