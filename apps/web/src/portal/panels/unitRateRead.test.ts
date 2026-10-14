import { describe, expect, it } from "vitest";

import {
  exclusionLine, ORDER_OF_MAGNITUDE, pooledLine, RATE_CSS, ratePageNote, spreadReading, unquotable,
  type UnitRateCode, type UnitRates,
} from "./unitRateRead";

const C = (over: Partial<UnitRateCode> = {}): UnitRateCode => ({
  cost_code: "03-3000", unit: "CY", projects: 6, below_threshold: false,
  low: 180, p25: 205, median: 230, p75: 260, high: 310,
  pooled_rate: 241.5, spread_ratio: 1.72, total_cost: 482_000, total_quantity: 2000,
  ...over,
});

const R = (over: Partial<UnitRates> = {}): UnitRates => ({
  cost_codes: [C()], code_count: 9, usable_count: 1, min_projects: 3, message: null,
  basis: "each rate is one PROJECT's cost divided by that project's installed quantity…",
  limitation: "direct_cost and production_quantity accumulate independently… Check `spread_ratio` "
    + "and `per_project` before quoting a median",
  excluded: { mixed_units: [], cost_without_quantity: [], quantity_without_cost: [],
              note: "excluded rows are reported, never dropped" },
  ...over,
});

describe("UNITRATE-BASIS", () => {
  it("uses the ENGINE's order-of-magnitude line, not a threshold of its own", () => {
    // The engine's comment beside `spread_ratio`: "A code where one project is an order of
    // magnitude off another is usually a reporting-lag artefact rather than a price difference."
    // A softer second band would be a judgement this module is not entitled to make.
    expect(ORDER_OF_MAGNITUDE).toBe(10);
    expect(spreadReading(C({ spread_ratio: 9.99 })).quotable).toBe(true);
    expect(spreadReading(C({ spread_ratio: 10 })).quotable).toBe(false);
    expect(spreadReading(C({ spread_ratio: 10 })).tone).toBe("warn");
  });

  it("reports a NULL ratio as unknown rather than as a narrow spread", () => {
    // `spread_ratio` is null when the low rate was zero, so high/low is undefined. Rendering that
    // as a dash in an otherwise green row would read as "these projects agree".
    const s = spreadReading(C({ spread_ratio: null }));
    expect(s.tone).toBe("unknown");
    expect(s.quotable).toBe(false);
    expect(s.text).toBe("—");
  });

  it("lists the codes whose median should not be quoted, ignoring the under-threshold ones", () => {
    // A code below `min_projects` is already excluded from the table, so counting it here would
    // double-report the same caveat under a different name.
    const r = R({ cost_codes: [
      C({ cost_code: "03-3000", spread_ratio: 1.7 }),
      C({ cost_code: "09-9100", spread_ratio: 14.2 }),
      C({ cost_code: "26-0500", spread_ratio: 30, below_threshold: true }),
      C({ cost_code: "07-5000", spread_ratio: null }),
    ] });
    expect(unquotable(r).map((c) => c.cost_code)).toEqual(["09-9100", "07-5000"]);
  });

  it("counts the exclusions by reason and says why they are reported at all", () => {
    const e = exclusionLine(R({ excluded: {
      mixed_units: [{ project_id: "p1", cost_code: "03-3000" }],
      cost_without_quantity: [{ project_id: "p2", cost_code: "09-9100", cost: 12_000 },
                              { project_id: "p3", cost_code: "09-9100", cost: 4_000 }],
      quantity_without_cost: [],
    } }))!;
    expect(e.tone).toBe("warn");
    expect(e.text).toContain("1 recorded under two units");
    expect(e.text).toContain("2 with cost but no installed quantity");
    expect(e.text).not.toContain("quantity but no cost");      // an empty reason is not listed
    expect(e.text).toContain("is not a project that cost zero");
  });

  it("distinguishes NOTHING EXCLUDED from WE DID NOT LOOK", () => {
    // Both would otherwise render as no line at all, and only one of them is reassuring.
    const clean = exclusionLine(R())!;
    expect(clean.tone).toBe("ok");
    expect(clean.text).toContain("nothing excluded");
    expect(exclusionLine(R({ excluded: undefined }))).toBeNull();
  });

  it("labels the pooled rate as the different question it answers", () => {
    // The engine's own words: "`pooled_rate` is the portfolio-wide blend and answers a different
    // question" — and "one large project sets it".
    expect(pooledLine(C())).toContain("Σcost ÷ Σquantity");
    expect(pooledLine(C())).toContain("one large project sets it");
    expect(pooledLine(C({ pooled_rate: null }))).toBeNull();
  });

  it("states both numbers where the table stops", () => {
    expect(ratePageNote(20, 46)).toBe("Showing 20 of 46 usable cost codes.");
    expect(ratePageNote(9, 9)).toBe("");
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn", "unknown"] as const) expect(RATE_CSS[t]).toMatch(/^var\(--/);
  });
});
