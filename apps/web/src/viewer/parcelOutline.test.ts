import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { buildParcelOutline } from "./gis";

/**
 * SITE-1 — the project's parcel boundary, drawn on the model.
 *
 * ## What the roadmap said, and what was actually missing
 *
 * The entry read "SITE-1 remaining — parcel overlays", which sounds like a drawing task.
 * `buildSiteContext` already draws OSM land-use parcels; `parcel_geometry.analyze` already parses a
 * real cadastral boundary, and PARCEL-SHAPE wired it to the feasibility tab, where it sizes the
 * building on the lot's true outline instead of its bounding rectangle. Both halves shipped and the
 * viewer still had no lot line.
 *
 * **Nothing persisted the ring.** `massingTab.ts` held it in a local variable and sent it to
 * `compute_massing` as `lot_polygon`; a tab re-render dropped it, and no other screen could ask for
 * it. *A blocker named one layer too high* — there was nothing for a drawing task to draw, and a
 * reader taking the entry at its word would have gone looking in the viewer.
 *
 * ## The frame, which is the part that can silently be wrong
 *
 * `ring_m` is in metres and must NOT be projected: sending it through `project()` like the OSM
 * context would need a lon/lat anchor, and a metre ring read as degrees lands the lot a continent
 * away — an error that is enormous, silent, and looks like a drawing bug.
 *
 * **The first version of this comment then got the origin wrong, and the fixture agreed with the
 * comment rather than with the data.** It said the ring arrives *"about its own centroid"*.
 * `parcel_geometry.analyze` shifts it to its bounding-box **minimum** (*"origin-shifted to its own
 * bbox minimum so the polygon sits near (0,0)"*), so a saved ring lies wholly in the +x/+y quadrant
 * while the generated model is built around the origin — the lot line sat off the corner of its own
 * building. `buildParcelOutline` now recentres on the bounding-box CENTRE, which is the anchor
 * `services/data/src/aec_data/massing.py` already uses to put the parcel in the building's frame.
 *
 * **Every assertion here passed before and after that fix**, because `SQUARE` was symmetric about
 * the origin and its bbox centre is (0, 0) — the translation was a no-op on the only shape tested.
 * *A fixture that already satisfies the property cannot witness it*, and a fixture chosen to match
 * a comment inherits whatever the comment got wrong. The fixture below is asymmetric AND
 * bbox-min-shifted, which is the shape `parcel_geometry` actually emits.
 */
/** OPEN (no repeated closing vertex) and bbox-min-shifted, as `parcel_geometry.analyze` emits.
 *  Deliberately asymmetric: bbox centre (15, 10), area centroid elsewhere, neither at the origin. */
const LOT = [[0, 0], [30, 0], [30, 20], [10, 20]];

describe("buildParcelOutline", () => {
  it("draws a closed loop through every vertex — the ring arrives OPEN and the loop closes it", () => {
    const { object } = buildParcelOutline(LOT);
    const line = object.children.find((c) => c.type === "LineLoop");
    expect(line, "no lot line: the overlay is a fill with no boundary").toBeDefined();
    const pos = (line as unknown as { geometry: { getAttribute(n: string): { count: number } } })
      .geometry.getAttribute("position");
    expect(pos.count, "a LineLoop must carry exactly the ring's vertices — repeating the first "
      + "would draw a zero-length segment, and dropping one would open the lot").toBe(4);
  });

  it("keeps the ring in the MODEL's frame: x→x, y→-z, recentred, and no projection", () => {
    const { object } = buildParcelOutline(LOT);
    const line = object.children.find((c) => c.type === "LineLoop") as unknown as
      { geometry: { getAttribute(n: string): { array: ArrayLike<number> } } };
    const xz = Array.from(line.geometry.getAttribute("position").array);
    // bbox centre of LOT is (15, 10), so (0,0) draws at x = -15, z = +10. Magnitudes stay metres:
    // a projection here would scale them by ~111 km/degree and put the lot line off the planet.
    expect(xz[0]).toBeCloseTo(-15);
    expect(xz[2]).toBeCloseTo(10);
    // …and the WHOLE ring is centred, not merely shifted: the extremes are symmetric about 0.
    const rx = xz.filter((_, i) => i % 3 === 0), rz = xz.filter((_, i) => i % 3 === 2);
    expect(Math.min(...rx) + Math.max(...rx), "x is not centred on the model origin").toBeCloseTo(0);
    expect(Math.min(...rz) + Math.max(...rz), "z is not centred on the model origin").toBeCloseTo(0);
    // The shape is untouched — recentring is a translation, never a rescale.
    expect(Math.max(...rx) - Math.min(...rx)).toBeCloseTo(30);
  });

  it("uses the SAME anchor the generator does — bbox centre, not the area centroid", () => {
    // `massing.py` recentres the parcel on `(min+max)/2` per axis so it shares the building's
    // origin frame. The two anchors agree only on a symmetric lot, so choosing the other one here
    // would leave a smaller version of the misalignment this fix exists to remove — against the
    // half of the system that has already placed geometry. Read the generator rather than restate
    // it: a drift there is silent, and the symptom is an overlay that is *nearly* right.
    const gen = readFileSync(join(process.cwd(), "..", "..", "services", "data", "src", "aec_data",
      "massing.py"), "utf8");
    expect(gen, "the generator no longer recentres on its bbox centre — re-derive the viewer's "
      + "anchor before trusting this overlay").toMatch(/\(min\(pxs\) \+ max\(pxs\)\) \/ 2/);
    const viewer = readFileSync(join(process.cwd(), "src", "viewer", "gis.ts"), "utf8");
    expect(viewer).toMatch(/Math\.min\(\.\.\.xs\) \+ Math\.max\(\.\.\.xs\)\) \/ 2/);
  });

  it("sits above the ground plane but below the roads the site-context layer draws at 0.05", () => {
    const { object } = buildParcelOutline(LOT);
    const fill = object.children.find((c) => c.type === "Mesh") as unknown as
      { geometry: { getAttribute(n: string): { array: ArrayLike<number> } } } | undefined;
    expect(fill, "no fill: the lot reads as four lines rather than an area").toBeDefined();
    expect(Array.from(fill!.geometry.getAttribute("position").array)[1]).toBeCloseTo(0.02);
  });

  it("refuses a ring that cannot be a polygon rather than drawing an empty group", () => {
    expect(() => buildParcelOutline([[0, 0], [1, 1]])).toThrow(/at least 3/);
  });

  it("drops non-finite vertices before counting — a NaN reaches the GPU as a hole in the lot", () => {
    expect(() => buildParcelOutline([[0, 0], [1, NaN], [2, 2]])).toThrow(/at least 3/);
  });

  /**
   * **The wire.** Every assertion above passes on a function nobody calls, and on a ring nobody
   * saves — which is exactly the state this item shipped in for months.
   */
  it("`massingTab.ts` PERSISTS the ring — without this the viewer has nothing to read", () => {
    const src = readFileSync(join(process.cwd(), "src", "proforma", "massingTab.ts"), "utf8");
    expect(src).toMatch(/saveProperty\([^)]*\{\s*parcel_boundary/s);
    expect(src, "a failed save must be reported: a silent one leaves the viewer drawing a lot line "
      + "for a parcel the user thinks they replaced").toMatch(/parcel boundary not saved/);
  });

  it("`main.ts` reads it back and the flow is reachable from the menu", () => {
    const src = readFileSync(join(process.cwd(), "src", "main.ts"), "utf8");
    expect(src).toMatch(/buildParcelOutline\(ring\)/);
    expect(src).toMatch(/onClick: \(\) => void addParcelBoundaryFlow\(\)/);
  });
});
