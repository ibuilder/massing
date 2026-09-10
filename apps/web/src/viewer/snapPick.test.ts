import { describe, expect, it } from "vitest";
import * as THREE from "three";

import { snapByOverride, snapPoint, snapToGeometry, type SnapFragments, type SnapHit } from "./snapPick";

/** Why this file exists.
 *
 *  These three functions were closures inside `initViewerApp` and had **no tests at all** — grep for
 *  `snapToGeometry` before the extraction found exactly one file, `app.ts` itself. That is the
 *  argument for lifting them rather than a line count: snapping is where a click becomes a
 *  coordinate, and a wall placed on the wrong vertex is written into the IFC under a GlobalId and
 *  travels to everyone downstream. The extraction is only worth its diff if the behaviour is now
 *  pinned, so every assertion below was mutation-checked against the code it describes.
 */

/** The smallest thing that satisfies `SnapFragments`. `positions` is what the picked element's mesh
 *  reports; `boxes` is what `getBBoxes` returns. Either can be made to throw, because both `try`
 *  blocks in `snapToGeometry` are load-bearing and a fragments loader really does reject. */
function fakeFrags(opts: {
  positions?: THREE.Vector3[] | null;
  positionsThrow?: boolean;
  boxes?: { min: THREE.Vector3; max: THREE.Vector3 }[];
  boxesThrow?: boolean;
  noModel?: boolean;
} = {}): SnapFragments & { bboxCalls: number } {
  const frags = {
    bboxCalls: 0,
    list: {
      get: (_id: string) => opts.noModel ? undefined : {
        getPositions: async (_ids: number[]) => {
          if (opts.positionsThrow) throw new Error("fragment read failed");
          return opts.positions ?? null;
        },
      },
    },
    getBBoxes: async (_sel: Record<string, Set<number>>) => {
      frags.bboxCalls += 1;
      if (opts.boxesThrow) throw new Error("bbox read failed");
      return opts.boxes ?? [];
    },
  };
  return frags;
}

const HIT: SnapHit = { point: new THREE.Vector3(), fragments: { modelId: "m1" }, localId: 7 };

/** A 4 × 3 × 2 box at the origin, so every candidate class lands on a distinct round number:
 *  corners at 0/4 · 0/3 · 0/2, edge midpoints at 2 / 1.5 / 1, centre at (2, 1.5, 1). */
const BOX = [{ min: new THREE.Vector3(0, 0, 0), max: new THREE.Vector3(4, 3, 2) }];

describe("snapPoint", () => {
  it("rounds the plan coords to the increment and leaves height alone", () => {
    const p = snapPoint(new THREE.Vector3(1.2, 7.9, -3.4), 0.5);
    expect([p.x, p.y, p.z]).toEqual([1, 7.9, -3.5]);
  });

  it("returns the point untouched when the increment is zero", () => {
    // Not merely equal — the SAME object. `snapPoint` is called on the raw cursor point on every
    // armed pick, and a copy here would be a per-pick allocation for nothing.
    const raw = new THREE.Vector3(1.234, 5, 6.789);
    expect(snapPoint(raw, 0)).toBe(raw);
  });
});

describe("snapToGeometry", () => {
  it("is null with no hit — a click on empty space snaps to nothing", async () => {
    expect(await snapToGeometry(new THREE.Vector3(1, 0, 1), null, fakeFrags({ boxes: BOX }))).toBeNull();
  });

  it("prefers a mesh vertex inside the aperture over any bbox candidate", async () => {
    const vertex = new THREE.Vector3(0.9, 0, 0.9);
    const out = await snapToGeometry(new THREE.Vector3(1, 0, 1), HIT,
                                     fakeFrags({ positions: [vertex], boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([0.9, 0, 0.9]);
  });

  it("returns a CLONE of the vertex, so the caller cannot mutate the model's positions", async () => {
    // `lastPoint = (snapped ?? hit.point).clone()` at the call site clones again, but the override
    // path and every future caller do not have to know that. Aliasing a fragment's position array
    // into a draft point would corrupt the geometry of the element that was snapped TO.
    const vertex = new THREE.Vector3(1, 0, 1);
    const out = await snapToGeometry(new THREE.Vector3(1, 0, 1), HIT,
                                     fakeFrags({ positions: [vertex], boxes: BOX }));
    expect(out).not.toBe(vertex);
    out!.set(99, 99, 99);
    expect([vertex.x, vertex.y, vertex.z]).toEqual([1, 0, 1]);
  });

  it("ignores a vertex outside the 0.4 m aperture and falls through to the bbox corners", async () => {
    // The vertex is 0.5 m away — real, but not what the drafter was pointing at. The nearest corner
    // (0,0,0) is 0.3 m away and wins.
    const out = await snapToGeometry(new THREE.Vector3(0.3, 0, 0), HIT,
                                     fakeFrags({ positions: [new THREE.Vector3(0.8, 0, 0)], boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([0, 0, 0]);
  });

  it("snaps to an edge midpoint rather than a corner when the midpoint is nearer", async () => {
    // (2, 0, 0) is the midpoint of the near bottom edge; the nearest corner is 2 m away.
    const out = await snapToGeometry(new THREE.Vector3(2, 0, 0.1), HIT, fakeFrags({ boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([2, 0, 0]);
  });

  it("snaps to the box centre when the cursor is nearest to it", async () => {
    const out = await snapToGeometry(new THREE.Vector3(2, 1.5, 1.1), HIT, fakeFrags({ boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([2, 1.5, 1]);
  });

  it("applies the SAME 0.4 m aperture to the bbox candidates — far from everything is no snap",
     async () => {
       // This is the "◻ snap" glyph not appearing. Without the aperture on this path the pick would
       // be yanked metres across the model to the nearest corner of whatever the ray happened to
       // graze, which is worse than not snapping.
       const out = await snapToGeometry(new THREE.Vector3(2, 0.8, 0.4), HIT, fakeFrags({ boxes: BOX }));
       expect(out).toBeNull();
     });

  it("falls back to bbox candidates when reading the mesh throws", async () => {
    const out = await snapToGeometry(new THREE.Vector3(0.1, 0, 0), HIT,
                                     fakeFrags({ positionsThrow: true, boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([0, 0, 0]);
  });

  it("falls back to bbox candidates when the model is not in the fragments list", async () => {
    const out = await snapToGeometry(new THREE.Vector3(0.1, 0, 0), HIT,
                                     fakeFrags({ noModel: true, boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([0, 0, 0]);
  });

  it("is null when there is no bbox to fall back to", async () => {
    expect(await snapToGeometry(new THREE.Vector3(0.1, 0, 0), HIT, fakeFrags({ boxes: [] }))).toBeNull();
  });

  it("is null when the bbox read throws", async () => {
    expect(await snapToGeometry(new THREE.Vector3(0.1, 0, 0), HIT,
                                fakeFrags({ boxesThrow: true }))).toBeNull();
  });
});

describe("snapByOverride", () => {
  const from = new THREE.Vector3(-10, 0, 1);

  it("answers `none` from the drafter's statement, without ever reading the element", async () => {
    // The `toBeNull()` half of this ALONE could not fail: `overrideCandidates("none")` returns no
    // candidates, so the resolver answers null too and deleting the early return changes nothing
    // observable. Measured — the mutation passed all 21 tests. What the early return actually buys
    // is that "no snap" is decided by what the drafter SAID, not by what the model happens to
    // contain, and the way to state that is that the loader is never asked. If a `none` producer
    // were ever added to `overrideCandidates`, this refusal would still hold; the vacuous version
    // would have silently started snapping.
    const frags = fakeFrags({ boxes: BOX });
    expect(await snapByOverride(new THREE.Vector3(0.1, 0, 0), HIT, "none", from, frags)).toBeNull();
    expect(frags.bboxCalls).toBe(0);
  });

  it("is null with no hit", async () => {
    expect(await snapByOverride(new THREE.Vector3(0.1, 0, 0), null, "endpoint", from,
                                fakeFrags({ boxes: BOX }))).toBeNull();
  });

  it("resolves an endpoint at ANY distance — a stated kind has no aperture", async () => {
    // The deliberate difference from `snapToGeometry`. The automatic path guesses which of six kinds
    // was meant and needs a tolerance to stay honest; here the drafter named the kind AND picked the
    // element, so a distance cut could only make a stated intent fail silently.
    const out = await snapByOverride(new THREE.Vector3(50, 0, 50), HIT, "endpoint", from,
                                     fakeFrags({ boxes: BOX }));
    expect([out!.x, out!.z]).toEqual([4, 2]);
  });

  it("keeps the raw height — an override is a PLAN snap", async () => {
    const out = await snapByOverride(new THREE.Vector3(0.1, 7.25, 0.1), HIT, "center", from,
                                     fakeFrags({ boxes: BOX }));
    expect([out!.x, out!.y, out!.z]).toEqual([2, 7.25, 1]);
  });

  it("refuses a perpendicular with no previous point instead of falling back to another kind",
     async () => {
       // There is no perpendicular to something from nowhere. Returning an endpoint here would place
       // a point the HUD then labels "perpendicular", and that label travels into the schedules.
       expect(await snapByOverride(new THREE.Vector3(1, 0, 1), HIT, "perpendicular", null,
                                   fakeFrags({ boxes: BOX }))).toBeNull();
     });

  it("resolves a perpendicular once there IS a previous point", async () => {
    // `from` sits due west of the footprint at z = 1, so the foot on the minX edge is (0, ., 1).
    const out = await snapByOverride(new THREE.Vector3(0.2, 0, 1), HIT, "perpendicular", from,
                                     fakeFrags({ boxes: BOX }));
    expect([out!.x, out!.z]).toEqual([0, 1]);
  });

  it("is null when the element has nothing of the named kind", async () => {
    // No box → no candidates of any kind. The caller keeps the raw cursor and the glyph says
    // "no midpoint here", which is the honest answer.
    expect(await snapByOverride(new THREE.Vector3(1, 0, 1), HIT, "midpoint", from,
                                fakeFrags({ boxes: [] }))).toBeNull();
  });

  it("is null when the bbox read throws", async () => {
    expect(await snapByOverride(new THREE.Vector3(1, 0, 1), HIT, "endpoint", from,
                                fakeFrags({ boxesThrow: true }))).toBeNull();
  });
});
