import { describe, expect, it } from "vitest";

import { type ExpiryCoverage, expiryReading, unevaluatedClause } from "./expiryNote";

const COV = (over: Partial<ExpiryCoverage> = {}): ExpiryCoverage => ({
  population: 10, considered: 10, missing_date: 0, unreadable_date: 0, unevaluated: 0,
  reason: "every record carries a readable expiry date", ...over,
});

const R = (over: Partial<Parameters<typeof expiryReading>[1]> = {}) =>
  ({ count: 0, expired: [], expiring: [], coverage: COV(), ...over });

describe("EXPIRY-UNDATED — the tick has to be earned", () => {
  it("gives the tick when the window is clear AND everything in it was evaluated", () => {
    const r = expiryReading("Compliance", R());
    expect(r.tone).toBe("ok");
    expect(r.earned).toBe(true);
    expect(r.text).toContain("✓");
  });

  /** The shipped defect, as an assertion: `count === 0` over records nothing could read. */
  it("REFUSES the tick when the window is clear only because nothing was evaluated", () => {
    const r = expiryReading("Compliance", R({
      coverage: COV({ population: 30, considered: 0, missing_date: 28, unreadable_date: 2,
                      unevaluated: 30 }),
    }));
    expect(r.tone).toBe("warn");
    expect(r.earned).toBe(false);
    expect(r.text).not.toContain("✓");
    expect(r.text).toContain("30 of 30 NOT CHECKED");
  });

  it("names the two causes separately, because they ask different things of the reader", () => {
    const text = unevaluatedClause(COV({ population: 9, missing_date: 5, unreadable_date: 4,
                                         unevaluated: 9 }));
    expect(text).toContain("5 with no expiry date");
    expect(text).toContain("4 with an unreadable date");
  });

  it("says nothing at all when coverage is complete, and does not throw when it is absent", () => {
    expect(unevaluatedClause(COV())).toBe("");
    expect(unevaluatedClause(undefined)).toBe("");
    expect(expiryReading("Compliance", R({ coverage: undefined })).tone).toBe("ok");
  });

  it("is BAD on an expiry already past, and still carries the unevaluated tail", () => {
    const r = expiryReading("Compliance", R({
      count: 1, expired: [{}],
      coverage: COV({ population: 4, considered: 1, missing_date: 3, unevaluated: 3 }),
    }));
    expect(r.tone).toBe("bad");
    expect(r.earned).toBe(false);
    expect(r.text).toContain("1 expired");
    expect(r.text).toContain("3 of 4 NOT CHECKED");
  });

  /** The banner used to pick its colour from `cc.expired.length` alone, which cannot express
   *  "clear window, incomplete coverage" — the state the whole item is about. */
  it("maps each tone to its CSS variable, including the state the old colour rule could not reach", () => {
    expect(expiryReading("C", R()).css).toBe("var(--status-good)");
    expect(expiryReading("C", R({ count: 1, expired: [{}] })).css).toBe("var(--status-crit)");
    const clearButUnchecked = expiryReading("C", R({
      coverage: COV({ population: 3, considered: 0, missing_date: 3, unevaluated: 3 }),
    }));
    expect(clearButUnchecked.css).toBe("var(--status-warn)");   // 0 expired, and NOT good
  });

  it("is WARN on something lapsing, with coverage complete", () => {
    const r = expiryReading("Compliance", R({ count: 2, expiring: [{}, {}] }));
    expect(r.tone).toBe("warn");
    expect(r.earned).toBe(true);
    expect(r.text).toBe("Compliance: 0 expired · 2 expiring");
  });
});
