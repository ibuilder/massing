/**
 * R38-NODE-SLIDERS — the pure contract: which params slide, over what range, and how a scrub
 * writes back. The textarea is the single source of truth, so the writeback rules matter more
 * than the widget: a scrub must never invent structure, destroy a hand-edit, or fill the JSON
 * with float noise.
 */
import { describe, expect, it } from "vitest";
import { applySlider, rangeFor, sliderSpecs } from "./nodeSliders";

describe("sliderSpecs — which params become sliders", () => {
  it("top-level finite numbers slide; arrays, objects, strings and refs do not", () => {
    const specs = sliderSpecs({
      start: [0, 0], end: [5, 0],                 // coordinates — positions, not magnitudes
      height: 3, thickness: 0.2,
      name: "W1", host: { $from: "n1" },
    });
    expect(specs.map((s) => s.key)).toEqual(["height", "thickness"]);
  });

  it("NaN and Infinity never slide — a slider needs a finite anchor", () => {
    expect(sliderSpecs({ a: NaN, b: Infinity, c: 1 }).map((s) => s.key)).toEqual(["c"]);
  });

  it("an all-structural params yields no sliders, not a crash", () => {
    expect(sliderSpecs({ points: [[0, 0], [1, 1]], guid: { $from: "n1" } })).toEqual([]);
  });
});

describe("rangeFor — a scrub range derived from the value", () => {
  it("scales the span and step with the magnitude", () => {
    expect(rangeFor(3)).toEqual({ min: 0, max: 12, step: 0.1 });
    expect(rangeFor(0.2)).toEqual({ min: 0, max: 0.8, step: 0.01 });
    expect(rangeFor(250)).toEqual({ min: 0, max: 1000, step: 1 });
  });

  it("zero gets a usable default span instead of a dead slider", () => {
    const r = rangeFor(0);
    expect(r.max).toBeGreaterThan(0);
  });

  it("a negative value's range includes it — elevation offsets are legitimately negative", () => {
    const r = rangeFor(-2);
    expect(r.min).toBeLessThanOrEqual(-2);
    expect(r.max).toBeGreaterThanOrEqual(0);
  });
});

describe("applySlider — writeback into the JSON source of truth", () => {
  it("changes exactly the scrubbed key and preserves everything else", () => {
    const out = applySlider('{"start":[0,0],"height":3,"name":"W1"}', "height", 4.5, 0.1);
    expect(JSON.parse(out!)).toEqual({ start: [0, 0], height: 4.5, name: "W1" });
  });

  it("rounds to the step's precision — no float noise in the params", () => {
    const out = applySlider('{"height":3}', "height", 2.4000000000000004, 0.1);
    expect(out).toContain('"height":2.4');
  });

  it("returns null on invalid JSON rather than destroying a half-edit", () => {
    // The user is mid-typing in the textarea; a scrub that replaced their text with {} would be a
    // data-loss bug wearing a convenience feature.
    expect(applySlider('{"height":', "height", 4, 0.1)).toBeNull();
    expect(applySlider("[1,2,3]", "height", 4, 0.1)).toBeNull();
  });
});
