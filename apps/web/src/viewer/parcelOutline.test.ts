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
 * `ring_m` is already projected to metres about its own centroid — the frame `compute_massing`
 * offsets inward for the buildable footprint. Drawing it about the scene origin means the lot line
 * and the building agree by construction. Sending it through `project()` like the OSM context would
 * need a lon/lat anchor, and a metre ring read as degrees lands the lot a continent away: the error
 * is enormous, silent, and looks like a drawing bug.
 */
const SQUARE = [[-10, -10], [10, -10], [10, 10], [-10, 10]];   // OPEN, as `parcel_geometry` emits

describe("buildParcelOutline", () => {
  it("draws a closed loop through every vertex — the ring arrives OPEN and the loop closes it", () => {
    const { object } = buildParcelOutline(SQUARE);
    const line = object.children.find((c) => c.type === "LineLoop");
    expect(line, "no lot line: the overlay is a fill with no boundary").toBeDefined();
    const pos = (line as unknown as { geometry: { getAttribute(n: string): { count: number } } })
      .geometry.getAttribute("position");
    expect(pos.count, "a LineLoop must carry exactly the ring's vertices — repeating the first "
      + "would draw a zero-length segment, and dropping one would open the lot").toBe(4);
  });

  it("keeps the ring in the MODEL's frame: x→x, y→-z, and no projection", () => {
    const { object } = buildParcelOutline(SQUARE);
    const line = object.children.find((c) => c.type === "LineLoop") as unknown as
      { geometry: { getAttribute(n: string): { array: ArrayLike<number> } } };
    const a = Array.from(line.geometry.getAttribute("position").array).slice(0, 3);
    // (-10, -10) in plan → x = -10, z = +10. Magnitudes are metres, unchanged: a projection here
    // would scale them by ~111km/degree and put the lot line off the planet.
    expect(a[0]).toBeCloseTo(-10);
    expect(a[2]).toBeCloseTo(10);
  });

  it("sits above the ground plane but below the roads the site-context layer draws at 0.05", () => {
    const { object } = buildParcelOutline(SQUARE);
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
