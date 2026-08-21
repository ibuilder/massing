import { describe, expect, it } from "vitest";

import { groundToPlan, pixelToWorld, readPlanTransform, worldToPixel } from "./planTransform";

/** The six terms from a real cut: scale 2, origin inset, a 10×8 drawing of a 5×4 m plate. */
const T = { scale: 2, ox: 10, oy: 5, minx: 100, miny: 200, drawh: 8 };

describe("worldToPixel / pixelToWorld — the inverse the generator's docstring names", () => {
  it("round-trips a world point through pixel space", () => {
    const { px, py } = worldToPixel(T, 102, 201);
    const back = pixelToWorld(T, px, py);
    expect(back.x).toBeCloseTo(102, 10);
    expect(back.y).toBeCloseTo(201, 10);
  });

  it("places the drawing origin (minx, miny) at (ox, oy + drawh)", () => {
    // y increases "up" in the model and "down" in SVG, which is why drawh is in the formula.
    expect(worldToPixel(T, T.minx, T.miny)).toEqual({ px: T.ox, py: T.oy + T.drawh });
  });
});

describe("readPlanTransform — all six terms, or nothing", () => {
  it("reads a complete root", () => {
    const host = document.createElement("div");
    host.innerHTML = `<svg data-plan-scale="2" data-plan-ox="10" data-plan-oy="5"
      data-plan-minx="100" data-plan-miny="200" data-plan-drawh="8"></svg>`;
    expect(readPlanTransform(host)).toEqual(T);
  });

  it("refuses a partial root — one missing term is not a transform", () => {
    const host = document.createElement("div");
    host.innerHTML = `<svg data-plan-scale="2" data-plan-ox="10" data-plan-oy="5"
      data-plan-minx="100" data-plan-miny="200"></svg>`;
    expect(readPlanTransform(host)).toBeNull();
  });

  it("refuses a zero scale — it would divide in the inverse", () => {
    const host = document.createElement("div");
    host.innerHTML = `<svg data-plan-scale="0" data-plan-ox="10" data-plan-oy="5"
      data-plan-minx="100" data-plan-miny="200" data-plan-drawh="8"></svg>`;
    expect(readPlanTransform(host)).toBeNull();
  });
});

describe("groundToPlan — viewer Y-up to drawing East/North", () => {
  it("maps three.x to East and -three.z to North", () => {
    expect(groundToPlan({ x: 3, z: -7 })).toEqual({ x: 3, y: 7 });
  });
});
