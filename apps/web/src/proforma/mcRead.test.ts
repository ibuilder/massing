/** MC-UNDEFINED — the percentile's denominator, and the all-undefined run.
 *
 *  Every fixture below is a shape `proforma/monte_carlo._summary` actually returns, including the
 *  degenerate `{n: 0, undefined: N}` that the old client type declared impossible.
 */
import { describe, expect, it } from "vitest";
import type { MonteCarloMetric } from "../api/types";
import { degenerate, drawScope, histogram, probReading, undefinedNote } from "./mcRead";

const metric = (over: Partial<MonteCarloMetric> = {}): MonteCarloMetric => ({
  n: 1000, undefined: 0, mean: 0.18, std: 0.04, min: 0.02, max: 0.31,
  p5: 0.11, p10: 0.12, p25: 0.15, p50: 0.18, p75: 0.21, p90: 0.24, p95: 0.26,
  target: 0.15, prob_at_least: 0.74,
  histogram: { counts: [1, 5, 20, 40, 20, 5, 1], edges: [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35] },
  ...over,
});

/** The shape `_summary` returns when every draw produced NaN — two keys, nothing else. */
const allUndefined: MonteCarloMetric = { n: 0, undefined: 500 };

describe("the caption names the draws the percentiles describe", () => {
  it("says 'N draws' only when nothing was left out", () => {
    const s = drawScope(metric(), 1000);
    expect(s.text).toBe("1000 draws");
    expect(s.complete).toBe(true);
  });

  it("says 'n of attempted' as soon as a draw produced no value", () => {
    // THE DEFECT, from the caption's side. 400 scenarios where the deal never returned capital are
    // outside every percentile, and the old title read "1000 draws".
    const s = drawScope(metric({ n: 600, undefined: 400 }), 1000);
    expect(s.text).toBe("600 of 1000 draws");
    expect(s.complete).toBe(false);
  });

  it("is incomplete when the attempted figure exceeds n even with `undefined` zero", () => {
    // The specialty engine reports `iterations` (requested), not solved, so draws can vanish
    // between the two without ever being counted as undefined. `n === attempted` is the test,
    // never `undefined === 0`.
    const s = drawScope(metric({ n: 480, undefined: 0 }), 500);
    expect(s.text).toBe("480 of 500 draws");
    expect(s.complete).toBe(false);
  });

  it("treats an absent `undefined` as zero rather than as unknown", () => {
    // An older server omits the key; the figures it does send are still a complete band.
    expect(drawScope(metric({ undefined: undefined }), 1000).complete).toBe(true);
  });

  it("takes the caller's word for the unit", () => {
    expect(drawScope(metric({ n: 2, undefined: 1 }), 3, "iterations").text)
      .toBe("2 of 3 iterations");
  });
});

describe("the undefined draws are explained, not just subtracted", () => {
  it("names the count and what an undefined value means", () => {
    const n = undefinedNote(metric({ n: 600, undefined: 400 }), "equity IRR");
    expect(n).toContain("400 draw(s) produced no equity IRR");
    expect(n).toContain("never returned capital");
    expect(n).toContain("600 draw(s) that resolved");
    // The engine counts them in the probability and cannot put them in a percentile; both halves
    // are stated, because a reader who sees only the subtraction assumes they were dropped.
    expect(n).toContain("counted in the probability");
    expect(n).toContain("cannot appear in a percentile");
  });

  it("is silent on a complete run, and when the key is absent", () => {
    expect(undefinedNote(metric())).toBeNull();
    expect(undefinedNote(metric({ undefined: undefined }))).toBeNull();
  });
});

describe("the all-undefined run is the finding, not an empty card", () => {
  it("reports that no scenario returned capital", () => {
    const d = degenerate(allUndefined, 500, "equity IRR");
    expect(d).toContain("500 of 500 draw(s) produced no equity IRR");
    expect(d).toContain("not missing data");
    expect(d).toContain("in none of these scenarios did the deal return capital");
  });

  it("falls back to the attempted count when the server omits `undefined`", () => {
    expect(degenerate({ n: 0 }, 250, "blended IRR")).toContain("250 of 250");
  });

  it("is null whenever a band exists, so it renders INSTEAD of dashes and never beside them", () => {
    expect(degenerate(metric(), 1000)).toBeNull();
    expect(degenerate(metric({ n: 1, undefined: 999 }), 1000)).toBeNull();
  });
});

describe("the clearing probability carries the engine's conditional figure", () => {
  it("heads with the unconditional one and names the gap", () => {
    // The engine's own worked example: 400 of 1000 scenarios never returning capital came back as
    // a 100% clearing rate when the denominator was the defined draws.
    const r = probReading(metric({ n: 600, undefined: 400, prob_at_least: 0.6,
                                   prob_at_least_of_defined: 1.0 }));
    expect(r.headline).toBe("60%");
    expect(r.gap).toContain("100% among the draws that resolved");
    expect(r.gap).toContain("count against it");
  });

  it("shows no gap when the two agree, which is every complete run", () => {
    expect(probReading(metric({ prob_at_least: 0.74, prob_at_least_of_defined: 0.74 })).gap)
      .toBeNull();
    expect(probReading(metric()).gap).toBeNull();
  });

  it("renders an em-dash rather than 0% when no target was asked for", () => {
    // `prob_at_least` is absent without a `targets` entry, and `Math.round(undefined * 100)` is
    // NaN — while `0%` would be a confident claim the engine never made.
    const r = probReading(metric({ target: undefined, prob_at_least: undefined }));
    expect(r.headline).toBe("—");
    expect(r.gap).toBeNull();
  });
});

describe("the histogram is asked for, because the degenerate branch has none", () => {
  it("returns the bars when there are any", () => {
    expect(histogram(metric())?.counts).toHaveLength(7);
  });

  it("returns null on the all-undefined branch and on an empty histogram", () => {
    expect(histogram(allUndefined)).toBeNull();
    expect(histogram(metric({ histogram: { counts: [], edges: [] } }))).toBeNull();
  });
});
