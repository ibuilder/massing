/**
 * A29-PLACE-VALID — the pure refusal contract. Each check refuses only what the client can know
 * honestly; the blank-model case passes everything, because a first element must never be refused
 * by a check that needs a model to exist.
 */
import { describe, expect, it } from "vitest";
import { BOUNDS_MARGIN_M, checkBounds, checkPolygon, checkRun, validatePlacement } from "./placeValid";

describe("checkRun — degenerate runs never reach the server", () => {
  it("a zero-length wall is refused with the measured length", () => {
    const v = checkRun([2, 3], [2, 3]);
    expect(v.ok).toBe(false);
    if (!v.ok) expect(v.reason).toMatch(/0 mm/);
  });

  it("a 3 cm run is refused; a 10 cm run passes", () => {
    expect(checkRun([0, 0], [0.03, 0]).ok).toBe(false);
    expect(checkRun([0, 0], [0.1, 0]).ok).toBe(true);
  });
});

describe("checkBounds — the ground-plane mis-click", () => {
  const model = { minX: 0, minZ: 0, maxX: 20, maxZ: 15 };

  it("inside and near the model passes; hundreds of metres out is refused with the distance", () => {
    expect(checkBounds([[10, 7]], model).ok).toBe(true);
    expect(checkBounds([[20 + BOUNDS_MARGIN_M - 1, 7]], model).ok).toBe(true);  // within margin
    const v = checkBounds([[400, 7]], model);
    expect(v.ok).toBe(false);
    if (!v.ok) expect(v.reason).toMatch(/m outside the model/);
  });

  it("a BLANK model (no bounds) refuses nothing — the first wall must always be placeable", () => {
    expect(checkBounds([[1000, 1000]], null).ok).toBe(true);
  });
});

describe("checkPolygon — bowtie slabs author garbage; refuse them first", () => {
  it("a rectangle passes", () => {
    expect(checkPolygon([[0, 0], [5, 0], [5, 4], [0, 4]]).ok).toBe(true);
  });

  it("a bowtie (edges cross) is refused naming the crossing edges", () => {
    const v = checkPolygon([[0, 0], [5, 4], [5, 0], [0, 4]]);
    expect(v.ok).toBe(false);
    if (!v.ok) expect(v.reason).toMatch(/crosses itself/);
  });

  it("a concave-but-simple L-shape passes — concave is legitimate, crossing is not", () => {
    expect(checkPolygon([[0, 0], [6, 0], [6, 2], [2, 2], [2, 5], [0, 5]]).ok).toBe(true);
  });

  it("fewer than 3 points is refused", () => {
    expect(checkPolygon([[0, 0], [1, 1]]).ok).toBe(false);
  });

  it("the CLOSING edge is adjacency-exempt — a triangle never reports its own closure as a crossing", () => {
    expect(checkPolygon([[0, 0], [4, 0], [2, 3]]).ok).toBe(true);
  });
});

describe("validatePlacement — composition", () => {
  const model = { minX: 0, minZ: 0, maxX: 20, maxZ: 15 };

  it("bounds refuse first — a degenerate run 400 m away reports the mis-click, not the sliver", () => {
    const v = validatePlacement("run", [[400, 0], [400, 0]], model);
    expect(v.ok).toBe(false);
    if (!v.ok) expect(v.reason).toMatch(/outside the model/);
  });

  it("a good wall run inside the model passes end to end", () => {
    expect(validatePlacement("run", [[2, 2], [12, 2]], model).ok).toBe(true);
  });

  it("a single-point placement checks bounds only", () => {
    expect(validatePlacement("point", [[10, 7]], model).ok).toBe(true);
    expect(validatePlacement("point", [[900, 7]], model).ok).toBe(false);
  });
});
