import { describe, expect, it, vi } from "vitest";

import { overstatement, parseBoundary, parcelBoundaryControl } from "./parcelBoundary";
import type { LoadedParcel, ParcelBoundaryHost } from "./parcelBoundary";

/**
 * PARCEL-SHAPE — the claim about the CONTROL.
 *
 * `services/api/test_parcel_geometry.py` proves the server returns a metric ring and that the ring
 * sizes a smaller building than its bounding box. That is a claim about an ENGINE. The defect this
 * item exists to end is a UI one: a feasibility tab that could describe a lot only as `width ×
 * depth`, and so quietly underwrote every irregular parcel as its bounding rectangle.
 *
 * So the assertions here are about what the user is told, not only about what is sent. A control
 * that adopted the ring and said nothing would fix the arithmetic and leave the reader unable to
 * tell which lot a number came from — and a GFA sized on 1,600 m² looks exactly like one sized on
 * 2,500 m².
 */

// The L-shaped corner lot from the server test: 1,600 m² inside a 50 × 50 m box.
const ELL = {
  ring_m: [[0, 0], [50, 0], [50, 20], [20, 20], [20, 50], [0, 50]],
  area_m2: 1600, area_acres: 0.395, bounding_rect_m2: 2500,
  lot_width_m: 50, lot_depth_m: 50, vertices: 6, coordinates_were_lonlat: false,
};

const LOADED: LoadedParcel = {
  ring: ELL.ring_m, areaM2: 1600, areaAcres: 0.395, rectM2: 2500,
  widthM: 50, depthM: 50, vertices: 6, wasLonLat: false,
};

function host(res: unknown | Error) {
  return {
    api: {
      parcelAnalyze: vi.fn().mockImplementation(() =>
        res instanceof Error ? Promise.reject(res) : Promise.resolve(res)),
    },
  } as unknown as ParcelBoundaryHost & { api: { parcelAnalyze: ReturnType<typeof vi.fn> } };
}

const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

describe("reading a parcel boundary", () => {
  it("tells GeoJSON from WKT by shape, and refuses anything else by name", () => {
    expect(parseBoundary('{"type":"Polygon","coordinates":[]}')).toEqual({
      geojson: { type: "Polygon", coordinates: [] } });
    expect(parseBoundary("POLYGON ((0 0, 1 0, 1 1, 0 0))")).toEqual({
      wkt: "POLYGON ((0 0, 1 0, 1 1, 0 0))" });
    expect(parseBoundary("polygon ((0 0, 1 0, 1 1, 0 0))").wkt, "WKT keywords are case-insensitive")
      .toBeTruthy();
    // A parse error must name the problem. "could not read that" sends the user to re-export a
    // file that was fine, when a trailing comma is the whole story.
    expect(() => parseBoundary("{oops")).toThrow(/not valid JSON/);
    expect(() => parseBoundary("LINESTRING (0 0, 1 1)")).toThrow(/GeoJSON.*or WKT/);
    // MULTIPOLYGON was accepted here while the server takes POLYGON only, so the control shipped it
    // and the user got a round trip and a generic 422. Refused locally, by name, with the reason —
    // and asserted, because "the client accepts what the server accepts" is exactly the kind of
    // claim that holds until someone widens one side. Raised in review.
    expect(() => parseBoundary("MULTIPOLYGON (((0 0, 1 0, 1 1, 0 0)))"))
      .toThrow(/MULTIPOLYGON is not supported/);
    expect(() => parseBoundary("   ")).toThrow(/paste a parcel boundary/);
  });
});

describe("what the panel says about a parcel", () => {
  it("states BOTH areas and how much the rectangle overstates the lot", () => {
    const s = overstatement(LOADED);
    expect(s).toContain("1,600 m²");
    expect(s, "the rectangle it replaces, or the reader cannot judge the difference")
      .toContain("2,500 m²");
    // 2500/1600 - 1 = 56.25% → 56. Of the PARCEL, not of the box: this is the number that maps
    // onto the GFA error, and (2500-1600)/2500 = 36% answers a question nobody asked.
    expect(s).toMatch(/56% larger/);
  });

  it("says when the boundary was read as longitude/latitude", () => {
    // The projection is decided by a magnitude heuristic, and a parcel drawn in local metres near
    // the origin satisfies it. The two readings differ ~111,000x, so naming the decision is the
    // difference between a user catching it in a glance and generating a 1 m building.
    expect(overstatement({ ...LOADED, wasLonLat: true })).toContain("read as longitude/latitude");
    expect(overstatement(LOADED), "...and silence when it was already in metres")
      .not.toContain("longitude");
  });

  it("does not invent a difference on a rectangular parcel", () => {
    // Without this the sentence above passes for the wrong reason — a control that always prints a
    // percentage would report "0% larger" on a plain rectangular lot and send the reader hunting.
    const sq: LoadedParcel = { ...LOADED, areaM2: 2500, rectM2: 2500 };
    expect(overstatement(sq)).toMatch(/rectangular parcel, so nothing changes/);
    expect(overstatement(sq)).not.toMatch(/larger/);
  });
});

describe("the parcel boundary control", () => {
  it("holds no parcel until one is read, and then holds the RING", async () => {
    const h = host(ELL);
    const seen: (LoadedParcel | null)[] = [];
    const c = parcelBoundaryControl(h, (p) => seen.push(p));
    expect(c.parcel()).toBeNull();
    (c.el.querySelector("textarea") as HTMLTextAreaElement).value =
      '{"type":"Polygon","coordinates":[[[0,0]]]}';
    (c.el.querySelector("button") as HTMLButtonElement).click();
    await flush();
    expect(c.parcel()?.ring, "the ring is what `lot_polygon` needs; area alone changes nothing")
      .toEqual(ELL.ring_m);
    expect(seen).toEqual([c.parcel()]);
    expect(c.el.textContent ?? "").toMatch(/56% larger/);
  });

  it("keeps the parcel it had when a later read fails", async () => {
    // A half-read boundary silently replacing a good one is worse than a rejected paste: the panel
    // would go on reporting "on the real parcel" for a parcel it no longer has.
    const h = host(ELL);
    const c = parcelBoundaryControl(h, () => undefined);
    const ta = c.el.querySelector("textarea") as HTMLTextAreaElement;
    const use = c.el.querySelector("button") as HTMLButtonElement;
    ta.value = '{"type":"Polygon","coordinates":[[[0,0]]]}';
    use.click();
    await flush();
    expect(c.parcel()).not.toBeNull();
    ta.value = "not a boundary at all";
    use.click();
    await flush();
    expect(c.parcel()?.ring, "the good parcel survives a bad paste").toEqual(ELL.ring_m);
    expect(c.el.textContent ?? "").toMatch(/GeoJSON.*or WKT/);
    expect(use.disabled, "a failed read must not lock the control").toBe(false);
  });

  it("reports a server refusal rather than adopting nothing silently", async () => {
    const c = parcelBoundaryControl(host(new Error("422 could not parse the parcel boundary")),
      () => undefined);
    (c.el.querySelector("textarea") as HTMLTextAreaElement).value = "POLYGON ((0 0))";
    (c.el.querySelector("button") as HTMLButtonElement).click();
    await flush();
    expect(c.el.textContent ?? "").toContain("could not parse the parcel boundary");
    expect(c.parcel()).toBeNull();
  });

  it("can be cleared back to the rectangle", async () => {
    const seen: (LoadedParcel | null)[] = [];
    const c = parcelBoundaryControl(host(ELL), (p) => seen.push(p));
    (c.el.querySelector("textarea") as HTMLTextAreaElement).value = '{"type":"Polygon"}';
    (c.el.querySelector("button") as HTMLButtonElement).click();
    await flush();
    const clear = [...c.el.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "") === "Clear") as HTMLButtonElement;
    expect(clear.hidden, "nothing to clear before a parcel is loaded").toBe(false);
    clear.click();
    expect(c.parcel(), "the rectangle above is live again").toBeNull();
    expect(seen[seen.length - 1]).toBeNull();
  });
});
