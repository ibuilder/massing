import { describe, expect, it } from "vitest";

import {
  CLAMP_HIGH, CLAMP_LOW, type Calibration,
  basisNote, basisTotal, clamped, direction, factorClaim, misPricePct, rawRatio, summary, trust,
  trustNote,
} from "./costCalibration";

/** A $10M estimate — the scale at which the clamp's damage is easiest to see in whole dollars. */
function fixture(over: Partial<Calibration> = {}): Calibration {
  return {
    estimate_total: 10_000_000,
    committed_total: 0,
    actual_total: 0,
    basis: null,
    calibration_factor: null,
    apply_hint: "",
    note: "",
    ...over,
  };
}

describe("which total the factor came from", () => {
  it("is the committed total when nothing has been posted", () => {
    const c = fixture({ committed_total: 12_000_000, basis: "committed", calibration_factor: 1.2 });
    expect(basisTotal(c)).toBe(12_000_000);
    expect(rawRatio(c)).toBeCloseTo(1.2, 6);
  });

  it("is the actual total once anything has been posted", () => {
    const c = fixture({ committed_total: 12_000_000, actual_total: 11_000_000,
      basis: "actual", calibration_factor: 1.1 });
    expect(basisTotal(c)).toBe(11_000_000);
  });

  it("is zero, and the ratio null, with no basis at all", () => {
    const c = fixture();
    expect(basisTotal(c)).toBe(0);
    expect(rawRatio(c)).toBeNull();
    expect(trust(c)).toBe("no-basis");
  });

  it("does not divide by a zero estimate, and refuses to vouch for what it cannot check", () => {
    // The route guards `if basis and est_total > 0`, so it should not send this. That is the reason
    // to handle it rather than assume it away: every other verdict rests on recomputing the ratio,
    // so a response where that is impossible must get NO endorsement.
    //
    // This case is why `unverifiable` exists. The first version of `trust()` reached `usable` here,
    // because `clamped()` returns false when it cannot compute a ratio — a correct answer to "was
    // it clamped?" and the wrong basis for "is it usable?". This test failed against that code.
    const c = fixture({ estimate_total: 0, committed_total: 5_000, basis: "committed",
      calibration_factor: 2 });
    expect(rawRatio(c)).toBeNull();
    expect(clamped(c)).toBe(false);          // the honest answer to a question it cannot ask
    expect(trust(c)).toBe("unverifiable");   // ...which must not become an endorsement
    expect(summary(c).usable).toBe(false);
    expect(trustNote("unverifiable", c)).toContain("cannot be checked");
  });
});

describe("the clamp, which is what makes an unusable ratio look considered", () => {
  it("reports a factor inside the band as measured", () => {
    const c = fixture({ committed_total: 12_000_000, basis: "committed", calibration_factor: 1.2 });
    expect(clamped(c)).toBe(false);
    expect(trust(c)).toBe("usable");
  });

  it("catches the case the engine cannot: one $500 invoice on a $10M job", () => {
    // `cost.py` computes round(max(0.5, min(2.0, 500 / 10_000_000)), 3) -> 0.5, and returns it as
    // `calibration_factor` with basis "actual". Rendered plainly that reads as a finding that the
    // model over-prices by half. The raw ratio is 0.00005.
    const c = fixture({ committed_total: 8_000_000, actual_total: 500,
      basis: "actual", calibration_factor: 0.5 });
    expect(rawRatio(c)).toBeCloseTo(0.00005, 9);
    expect(clamped(c)).toBe(true);
    expect(trust(c)).toBe("clamped");
    expect(trustNote("clamped", c)).toContain("below");
    expect(trustNote("clamped", c)).toContain("boundary");
  });

  it("catches a clamp at the other end too, and says which side", () => {
    const c = fixture({ committed_total: 90_000_000, basis: "committed", calibration_factor: 2 });
    expect(rawRatio(c)).toBeCloseTo(9, 6);
    expect(clamped(c)).toBe(true);
    expect(trustNote("clamped", c)).toContain("above");
  });

  it("treats the band edges themselves as unclamped — the boundary is not outside it", () => {
    const low = fixture({ committed_total: 5_000_000, basis: "committed", calibration_factor: CLAMP_LOW });
    const high = fixture({ committed_total: 20_000_000, basis: "committed", calibration_factor: CLAMP_HIGH });
    expect(rawRatio(low)).toBeCloseTo(CLAMP_LOW, 6);
    expect(rawRatio(high)).toBeCloseTo(CLAMP_HIGH, 6);
    // A ratio that lands exactly on the edge WAS measured there; only one outside it was moved.
    expect(clamped(low)).toBe(false);
    expect(clamped(high)).toBe(false);
  });
});

describe("the actual-over-committed preference, which is right at the end and wrong at the start", () => {
  it("calls a mid-job actuals basis partial, not usable", () => {
    // $6M posted against $9M committed on a $10M estimate — a raw 0.6, deliberately INSIDE the
    // 0.5–2.0 band so this asserts the partial rule alone. A smaller posted figure would trip the
    // clamp as well and the test would no longer distinguish the two.
    const c = fixture({ committed_total: 9_000_000, actual_total: 6_000_000,
      basis: "actual", calibration_factor: 0.6 });
    expect(clamped(c)).toBe(false);
    expect(trust(c)).toBe("partial");
    expect(trustNote("partial", c)).toContain("still running");
  });

  it("calls it usable once posted costs have caught up with commitments", () => {
    const c = fixture({ committed_total: 11_000_000, actual_total: 11_500_000,
      basis: "actual", calibration_factor: 1.15 });
    expect(trust(c)).toBe("usable");
  });

  it("does not call a committed basis partial — there is nothing posted to be partial against", () => {
    const c = fixture({ committed_total: 12_000_000, basis: "committed", calibration_factor: 1.2 });
    expect(trust(c)).toBe("usable");
  });

  it("reports the clamp ahead of the partial flag, because a boundary is not a measurement", () => {
    const c = fixture({ committed_total: 9_000_000, actual_total: 100_000,
      basis: "actual", calibration_factor: 0.5 });
    expect(trust(c)).toBe("clamped");
  });
});

describe("direction, which is the half most likely to be read backwards", () => {
  it("calls a factor above 1 under-priced — the job cost MORE than the model said", () => {
    expect(direction(1.2)).toBe("under-priced");
  });

  it("calls a factor below 1 over-priced", () => {
    expect(direction(0.8)).toBe("over-priced");
  });

  it("calls exactly 1, and no factor at all, level", () => {
    expect(direction(1)).toBe("level");
    expect(direction(null)).toBe("level");
  });
});

describe("mis-pricing percent", () => {
  it("is signed, so 'under' and 'over' cannot be read off the magnitude alone", () => {
    expect(misPricePct(1.2)).toBe(20);
    expect(misPricePct(0.8)).toBe(-20);
    expect(misPricePct(1)).toBe(0);
  });

  it("keeps one decimal, matching the engine's 3dp factor", () => {
    expect(misPricePct(1.153)).toBe(15.3);
  });

  it("is null without a factor", () => {
    expect(misPricePct(null)).toBeNull();
  });
});

describe("basis wording", () => {
  it("names committed values as a forecast, not a record", () => {
    expect(basisNote("committed")).toContain("forecast");
  });

  it("names actuals as money already spent", () => {
    expect(basisNote("actual")).toContain("actually spent");
  });

  it("says plainly that there is nothing to calibrate against", () => {
    expect(basisNote(null)).toContain("no history");
  });
});

describe("summary", () => {
  it("reports a sound committed-basis calibration as usable", () => {
    const c = fixture({ committed_total: 12_000_000, basis: "committed", calibration_factor: 1.2 });
    const s = summary(c);
    expect(s.factor).toBe(1.2);
    expect(s.raw).toBeCloseTo(1.2, 6);
    expect(s.direction).toBe("under-priced");
    expect(s.pct).toBe(20);
    expect(s.usable).toBe(true);
  });

  it("is NOT usable on the $500-invoice job, and carries the raw ratio that proves why", () => {
    const c = fixture({ committed_total: 8_000_000, actual_total: 500,
      basis: "actual", calibration_factor: 0.5 });
    const s = summary(c);
    expect(s.usable).toBe(false);
    expect(s.trust).toBe("clamped");
    // The reported factor and the real ratio differ by four orders of magnitude. Showing only the
    // first is the defect this screen exists to stop.
    expect(s.factor).toBe(0.5);
    expect(s.raw).toBeLessThan(0.001);
  });
});

describe("the server's own clamp verdict wins over a local reconstruction", () => {
  // The route divides UNROUNDED totals and then quantizes them to cents in the response, so
  // recomputing here divides different numbers. They disagree at exactly the boundary that matters.
  it("trusts raw_ratio over the totals when the rounded totals would say otherwise", () => {
    // 200.021 / 100.01 = 2.00001... — above the band, so the route clamped. The response's ROUNDED
    // totals are 200.02 / 100.01 = exactly 2.0, which a local division reads as un-clamped.
    const c = fixture({ estimate_total: 100.01, committed_total: 200.02, basis: "committed",
      calibration_factor: 2, raw_ratio: 200.021 / 100.01, clamped: true });
    expect(200.02 / 100.01).toBeCloseTo(2, 10);        // what the fallback would have computed
    expect(rawRatio(c)).toBeGreaterThan(CLAMP_HIGH);   // what the route actually divided
    expect(clamped(c)).toBe(true);
    expect(trust(c)).toBe("clamped");
  });

  it("falls back to the local division when the server did not send one", () => {
    const c = fixture({ committed_total: 12_000_000, basis: "committed", calibration_factor: 1.2 });
    expect(c.raw_ratio).toBeUndefined();
    expect(rawRatio(c)).toBeCloseTo(1.2, 6);
    expect(clamped(c)).toBe(false);
  });

  it("honours an explicit clamped:false even where the local rule would flag it", () => {
    // Defensive, and the direction that matters: the route is the authority in BOTH directions.
    const c = fixture({ estimate_total: 100, committed_total: 100, basis: "committed",
      calibration_factor: 1, raw_ratio: 1, clamped: false });
    expect(clamped(c)).toBe(false);
  });
});

describe("what the factor may be CALLED beside the number", () => {
  it("gives a clamp boundary no mis-pricing percentage — the defect this module exists to stop", () => {
    // Shipped once: the panel rendered `${pct}% ${direction}` unconditionally, so this case read
    // "50% over-priced" — a percentage taken from the clamp floor, stated as a measurement.
    const c = fixture({ committed_total: 8_000_000, actual_total: 500,
      basis: "actual", calibration_factor: 0.5 });
    expect(trust(c)).toBe("clamped");
    expect(factorClaim(c)).toBe("a clamp boundary, not a measured difference");
    expect(factorClaim(c)).not.toContain("%");
    expect(factorClaim(c)).not.toContain("over-priced");
  });

  it("calls a mid-job actuals factor provisional, not a measured difference", () => {
    const c = fixture({ committed_total: 9_000_000, actual_total: 6_000_000,
      basis: "actual", calibration_factor: 0.6 });
    expect(factorClaim(c)).toContain("provisional");
    expect(factorClaim(c)).not.toContain("%");
  });

  it("refuses a percentage for an unverifiable factor too", () => {
    const c = fixture({ estimate_total: 0, committed_total: 5_000, basis: "committed",
      calibration_factor: 2 });
    expect(factorClaim(c)).toContain("not verifiable");
    expect(factorClaim(c)).not.toContain("%");
  });

  it("DOES give the percentage when the factor is usable — the claim is earned, not withheld", () => {
    const c = fixture({ committed_total: 12_000_000, basis: "committed", calibration_factor: 1.2 });
    expect(trust(c)).toBe("usable");
    expect(factorClaim(c)).toBe("20% under-priced versus this project's outcome");
  });

  it("says 'level' rather than '0% under-priced' at exactly 1", () => {
    const c = fixture({ committed_total: 10_000_000, basis: "committed", calibration_factor: 1 });
    expect(factorClaim(c)).toContain("level with");
  });
});
