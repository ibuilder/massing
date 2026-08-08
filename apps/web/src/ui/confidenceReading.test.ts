import { describe, expect, it } from "vitest";

import { type ConfidenceResponse, confidenceReading, confidenceSummary } from "./confidenceReading";

/**
 * The units, asserted rather than commented.
 *
 * Two of these three numbers are fractions and one is already a percentage, and the difference has
 * cost a wrong reading once: `Math.round(0.715)` is 1, so a budget that was 71.5% assumption-based
 * rendered "1%" beside a correct dollar figure. Plausible, badly wrong, and reassuring — the worst
 * combination. The fix was a comment in two files, which is the same fact stored twice; this is the
 * fact stored once, in something that fails.
 *
 * THE ASYMMETRY IS THE POINT. A test that only checked the two fractions would pass against a
 * "helpful" refactor that scaled all three uniformly — which would turn 10.63% contingency into
 * 1063%. So `avg_contingency_pct` is asserted to be left ALONE, in the same breath as the others
 * are asserted to be scaled.
 */

/** A realistic response: 71.5% assumption-based, 10.63% average contingency, 0.62 confidence.
 *  Values chosen so every unit error produces a visibly different number rather than a coincidence
 *  — 0.5 and 50 would agree under several wrong transforms. */
const RESP: ConfidenceResponse = {
  confidence: 0.624,
  pct_assumption_based: 0.715,
  assumption_based_cost: 4_182_500,
  avg_contingency_pct: 10.63,
};

describe("confidence reading units", () => {
  it("scales the two FRACTIONS to percentages", () => {
    const r = confidenceReading(RESP);
    expect(r.confidencePct, "confidence is a fraction (0.624 → 62%)").toBe(62);
    expect(r.assumptionBasedPct, "pct_assumption_based is a fraction DESPITE its name (0.715 → 72%)")
      .toBe(72);
  });

  it("leaves avg_contingency_pct alone — it is already a percentage", () => {
    // Guards the opposite error from the one that shipped. Scaling this would render 1063%.
    expect(confidenceReading(RESP).avgContingencyPct).toBe(11);
  });

  it("catches the exact defect that shipped: a fraction rounded without scaling", () => {
    // `Math.round(0.715)` is 1. Any implementation that forgets the *100 lands on 0 or 1 for every
    // input in range, so asserting "not 0 and not 1" is a direct test of the failure mode rather
    // than of one arithmetic result.
    const r = confidenceReading(RESP);
    expect([0, 1]).not.toContain(r.assumptionBasedPct);
    expect([0, 1]).not.toContain(r.confidencePct);
  });

  it("passes money through untouched — the server already rounded it", () => {
    expect(confidenceReading(RESP).assumptionBasedCost).toBe(4_182_500);
  });

  it("treats an all-zero estimate as zero, not as unavailable", () => {
    // A project with no assumption-based cost really is 0% — this is a genuine zero and must not be
    // dressed up as missing, which is the opposite of the `available: false` rule.
    const r = confidenceReading({ confidence: 0, pct_assumption_based: 0,
                                  assumption_based_cost: 0, avg_contingency_pct: 0 });
    expect(r).toEqual({ confidencePct: 0, assumptionBasedPct: 0, assumptionBasedCost: 0,
                        avgContingencyPct: 0 });
  });

  it("survives missing fields instead of rendering NaN%", () => {
    // An older server, or a caught error path handing over a partial object. `NaN%` on a cost
    // screen is worse than 0% because it looks like a bug in the number rather than in the fetch.
    const r = confidenceReading({} as ConfidenceResponse);
    expect(Number.isFinite(r.confidencePct)).toBe(true);
    expect(Number.isFinite(r.assumptionBasedPct)).toBe(true);
    expect(Number.isFinite(r.avgContingencyPct)).toBe(true);
  });

  it("writes one sentence both call sites can use, with the caveat attached", () => {
    const s = confidenceSummary(RESP, (n) => `$${n.toLocaleString("en-US")}`);
    expect(s).toContain("72% of cost is assumption-based");
    expect(s).toContain("$4,182,500");
    expect(s).toContain("average contingency 11%");
  });
});
