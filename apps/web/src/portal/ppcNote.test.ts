import { describe, expect, it } from "vitest";

import { ppcLine, type PpcRead } from "./ppcNote";

/**
 * PPC-UNASSESSED. The first test is the shipped defect, written as the arithmetic that produced it,
 * because the reason it survived is that nothing about it looked like a failure: no error, no blank,
 * a plausible number in a plausible colour.
 */

const R = (over: Partial<PpcRead> = {}): PpcRead => ({
  commitments: 25, completed: 18, missed: 7, ppc: 0.72, rating: "fair",
  unassessed: 0, reasons_not_recorded: 0,
  top_variance_reasons: [{ reason: "weather", count: 4 }],
  ...over,
});

/** The card as it shipped, verbatim in behaviour — kept so the defect is asserted, not described. */
function shippedLine(l: PpcRead): { color: string; pct: string } {
  const color = l.rating === "good" ? "good" : l.rating === "fair" ? "warn" : "crit";
  return { color, pct: `${((l.ppc as number) * 100).toFixed(0)}%` };
}

describe("PPC-UNASSESSED", () => {
  it("THE SHIPPED DEFECT: an unmeasurable period printed 0% in critical red", () => {
    const mid = R({ completed: 4, missed: 1, unassessed: 20, ppc: null, rating: null });
    const was = shippedLine(mid);
    // `null * 100` is 0 in JavaScript, so this is not an error and not a blank — it is a confident
    // zero. And `rating === null` fails both string comparisons, so the ternary chain lands on its
    // default branch, which was the critical colour. *A default branch is not a place to put
    // "unknown"* — the same lesson STAKEHOLDER-MEDIUM recorded about the default quadrant of a 2x2.
    expect(was).toEqual({ color: "crit", pct: "0%" });
    // and what it says now
    const now = ppcLine(mid)!;
    expect(now.measured).toBe(false);
    expect(now.tone).toBe("unmeasurable");
    expect(now.value).toBe("not yet measurable");
    expect(now.detail).toContain("20 of 25 commitment(s) still unanswered");
    expect(now.detail).toContain("4 complete");
    expect(now.detail).toContain("1 missed");
  });

  it("derives the tone from the NUMBER, not from the `rating` string", () => {
    // The engine computes `rating` from the same thresholds, so this is not a second opinion — it
    // is the removal of a string comparison whose default branch was a verdict.
    expect(ppcLine(R({ ppc: 0.8, rating: "good" }))!.tone).toBe("good");
    expect(ppcLine(R({ ppc: 0.79, rating: "fair" }))!.tone).toBe("fair");
    expect(ppcLine(R({ ppc: 0.6, rating: "fair" }))!.tone).toBe("fair");
    expect(ppcLine(R({ ppc: 0.59, rating: "needs work" }))!.tone).toBe("poor");
    // and a rating that disagrees with the number does NOT move the colour
    expect(ppcLine(R({ ppc: 0.95, rating: "needs work" }))!.tone).toBe("good");
  });

  it("renders a measured period as it always did", () => {
    const r = ppcLine(R())!;
    expect(r.value).toBe("72%");
    expect(r.detail).toBe("(18/25 commitments · 7 missed) · top reason: weather");
    expect(r.measured).toBe(true);
  });

  it("omits the missed clause and the reason clause when there is nothing to say", () => {
    const r = ppcLine(R({ missed: 0, completed: 25, ppc: 1, rating: "good",
                          top_variance_reasons: [] }))!;
    expect(r.detail).toBe("(25/25 commitments)");
    expect(r.value).toBe("100%");
  });

  it("names the misses whose reason nobody recorded", () => {
    // A Pareto of reasons over misses whose reason nobody wrote down is a chart about the subset
    // that was documented. The engine refuses to default them; this says how many.
    const r = ppcLine(R({ reasons_not_recorded: 3 }))!;
    expect(r.detail).toContain("3 missed with no reason recorded");
    // and on the unmeasurable branch too — the count is about the misses so far, which exist
    const mid = ppcLine(R({ ppc: null, rating: null, unassessed: 10, reasons_not_recorded: 2 }))!;
    expect(mid.detail).toContain("2 missed with no reason recorded");
  });

  it("returns null when nothing was promised, so the strip shows no line", () => {
    // Deliberate, and not the SCOPE-EMPTY shape: nothing here reports a verdict over the empty
    // set. The line is ABSENT, not clean — a team that promised nothing has broken nothing, and a
    // muted "no commitments" row on every non-lean project is noise in a six-line strip.
    expect(ppcLine(R({ commitments: 0, completed: 0, missed: 0, unassessed: 0, ppc: null,
                       rating: null }))).toBeNull();
  });

  it("reads `unassessed` rather than deriving it", () => {
    // `commitments - completed - missed` is the engine's own arithmetic, and duplicating it here is
    // the one way the two could come to disagree. A deliberately inconsistent payload proves the
    // value is read: 25 - 4 - 1 = 20, and this one says 11.
    const r = ppcLine(R({ completed: 4, missed: 1, unassessed: 11, ppc: null, rating: null }))!;
    expect(r.detail).toContain("11 of 25");
  });

  it("maps every tone to a CSS variable", () => {
    const seen = new Set<string>();
    for (const l of [R({ ppc: 0.9, rating: "good" }), R({ ppc: 0.7 }), R({ ppc: 0.1 }),
                     R({ ppc: null, rating: null, unassessed: 5 })]) {
      const r = ppcLine(l)!;
      expect(r.css).toMatch(/^var\(--/);
      seen.add(r.tone);
    }
    expect(seen.size).toBe(4);     // all four tones exercised, so none is unreachable
  });
});
