import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import { hasStatedTotals, incomeFromT12, parseAmount, parseT12, renderT12Result } from "./t12Card";

/**
 * T12-SELFTIE — `t12.py` exists for one refusal and the refusal is unreachable without a caller that
 * hands it real evidence.
 *
 * `normalize()`'s docstring: *"When the caller supplies source totals they are the reference the
 * mapping must reproduce; **without them the sum of the source lines is**."* Both sides then come from
 * the same mapped rows, so the deltas are zero by construction. Measured through the real engine, on
 * one T-12 with a single unmapped $90,000 line:
 *
 *     no stated totals    reconciles: true    deltas all 0.0    adjusted_noi: 3,180,000
 *     with stated totals  reconciles: false   expense −90,000   stopped: true · adjusted_noi: null
 *
 * So the response for a vacuous tie-out is **indistinguishable from a real pass** on every field the
 * card could read — `reconciles` is true either way. Only the CALLER knows which it handed over, which
 * is why `stated` is a parameter here and not something derived from the response.
 */

type T12 = Awaited<ReturnType<ApiClient["normalizeT12"]>>;

/** The engine's shape for a tie-out that "passed" — identical whether or not totals were supplied. */
const PASSED = (over: Partial<T12> = {}): T12 => ({
  line_count: 24,
  source_totals: { income: 3_420_000, expense: 1_330_000, noi: 2_090_000 },
  mapped_totals: { income: 3_420_000, expense: 1_330_000, noi: 2_090_000 },
  tie_out: { reconciles: true, deltas: { income: 0, expense: 0, noi: 0 }, tolerance: 1 },
  adjusted_noi: 2_140_000, unmapped_count: 0, unmapped: [],
  one_time_items: [{ description: "Legal settlement", amount: 50_000, kind: "expense" }],
  capital_items: [{ description: "Roof replacement", amount: 180_000 }],
  by_category: [{ category: "gross_potential_rent", label: "Gross potential rent",
                  amount: 3_600_000, run_rate: 3_648_000 },
                { category: "bad_debt", label: "Bad debt", amount: 41_000, run_rate: 52_000 }],
  run_rate_vs_trailing: [{ category: "bad_debt", label: "Bad debt", trailing: 41_000,
                           run_rate: 52_000, delta: 11_000 }],
  add_back_questions: [{ check: "management_fee", severity: "high",
                         finding: "no management fee in the statement",
                         question: "Is this owner-managed? Add a market management fee before pricing.",
                         amount: 0, pct_of_income: 0 }],
  note: "Tie-out passed",
  ...over,
} as T12);

const STOPPED = (over: Partial<T12> = {}): T12 => ({
  line_count: 24,
  source_totals: { income: 3_420_000, expense: 1_330_000, noi: 2_090_000 },
  mapped_totals: { income: 3_420_000, expense: 1_240_000, noi: 2_180_000 },
  tie_out: { reconciles: false, deltas: { income: 0, expense: -90_000, noi: 90_000 }, tolerance: 1 },
  stopped: true, adjusted_noi: null, unmapped_count: 1,
  unmapped: [{ description: "Owner draw — misc", amount: 90_000 }],
  reconciling_items: [{ issue: "unmapped line", description: "Owner draw — misc", amount: 90_000 }],
  note: "STOPPED: source and mapped totals do not reconcile",
  ...over,
} as T12);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

describe("the paste parser", () => {
  it("splits on the LAST comma, because account names contain commas and amounts do not", () => {
    // Splitting on the first comma truncates the description AND reads the remainder as the amount,
    // which parses — so the failure would be a wrong number rather than an error.
    const { lines } = parseT12("Repairs, maintenance & turnover, 240000");
    expect(lines).toEqual([{ description: "Repairs, maintenance & turnover", amount: 240_000 }]);
  });

  it("prefers a tab when there is one", () => {
    const { lines } = parseT12("Repairs, maintenance\t240000");
    expect(lines[0]!.description).toBe("Repairs, maintenance");
  });

  it("reads what a spreadsheet paste actually contains", () => {
    expect(parseAmount("$3,600,000.00")).toBe(3_600_000);
    expect(parseAmount("(180,000)")).toBe(-180_000);   // parenthesised negative
    expect(parseAmount(" -1234.5 ")).toBe(-1234.5);
  });

  it("returns null rather than 0 for something it cannot read", () => {
    // 0 would enter the mapping as a real line worth nothing and shift no total, so a misread row
    // would be invisible in both the tie-out and the unmapped list.
    expect(parseAmount("n/a")).toBeNull();
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("12,34,x")).toBeNull();
  });

  it("collects unreadable rows instead of dropping them", () => {
    const { lines, skipped } = parseT12("Rent, 100\nsomething odd\nTaxes, n/a\n\nInsurance\t2000");
    expect(lines.map((l) => l.description)).toEqual(["Rent", "Insurance"]);
    expect(skipped).toEqual(["something odd", "Taxes, n/a"]);
  });
});

describe("whether the caller handed the engine a real reference", () => {
  it("needs BOTH totals — one alone leaves the other tied to itself", () => {
    expect(hasStatedTotals({ income: 3_420_000, expense: 1_330_000 })).toBe(true);
    expect(hasStatedTotals({ income: 3_420_000 })).toBe(false);
    expect(hasStatedTotals({ expense: 1_330_000 })).toBe(false);
    expect(hasStatedTotals({ income: NaN, expense: 1_330_000 })).toBe(false);
  });
});

describe("the tie-out verdict", () => {
  // THE ONE THIS CARD EXISTS FOR. Same response, same `reconciles: true`; only the caller knows.
  it("refuses to call a self-tie a pass", () => {
    const t = renderT12Result(mount(), PASSED({ unmapped_count: 1 }), false).textContent ?? "";
    expect(t).toContain("tied to itself");
    expect(t).not.toContain("Tie-out passed");
    expect(t).toContain("the same mapping");
    expect(t).toContain("1");                      // unmapped_count — the only signal left
    expect(t).toContain("Enter the statement's own totals");
  });

  it("…and DOES call it a pass on the identical response when totals were stated", () => {
    const t = renderT12Result(mount(), PASSED({ unmapped_count: 1 }), true).textContent ?? "";
    expect(t).toContain("Tie-out passed against the stated totals");
    expect(t).not.toContain("tied to itself");
  });

  it("renders a stopped tie-out with its deltas and reconciling items, and no adjusted NOI", () => {
    const t = renderT12Result(mount(), STOPPED(), true).textContent ?? "";
    expect(t).toContain("Tie-out STOPPED");
    expect(t).toContain("Owner draw");
    expect(t).toContain("$90,000");
    expect(t).not.toContain("Adjusted NOI");
  });

  it("says the derived views were never calculated, not merely hidden", () => {
    // `add_back_questions` and `run_rate_vs_trailing` are computed only past the gate, so "hidden"
    // would misdescribe what happened and invite someone to look for a toggle.
    expect(renderT12Result(mount(), STOPPED(), true).textContent).toContain("never calculated");
  });

  it("shows stated against mapped side by side, which is the whole comparison", () => {
    const t = renderT12Result(mount(), STOPPED(), true).textContent ?? "";
    expect(t).toContain("$1,330,000");   // stated expense
    expect(t).toContain("$1,240,000");   // mapped expense
  });
});

describe("past the gate", () => {
  it("renders the adjusted NOI, the treatments and the run-rate movers", () => {
    const t = renderT12Result(mount(), PASSED(), true).textContent ?? "";
    expect(t).toContain("$2,140,000");
    expect(t).toContain("Legal settlement");
    expect(t).toContain("Roof replacement");
    expect(t).toContain("Bad debt");
  });

  it("renders add-backs as QUESTIONS with the number behind each, never as applied", () => {
    const t = renderT12Result(mount(), PASSED(), true).textContent ?? "";
    expect(t).toContain("Questions to ask before you price it");
    expect(t).toContain("Is this owner-managed?");
    expect(t).toContain("never applied for you");
  });

  it("says when the unmapped list is a page of a larger set", () => {
    const t = renderT12Result(mount(), PASSED({
      unmapped_count: 120,
      unmapped: Array.from({ length: 50 }, (_, i) => ({ description: `L${i}`, amount: 10 })),
    }), true).textContent ?? "";
    expect(t).toContain("Showing 50 of 120 unmapped lines");
  });
});

describe("the handoff into the rent-roll scrub", () => {
  it("supplies only the two fields a trailing twelve can honestly supply", () => {
    // `prior_bad_debt`, `occupancy_pct` and `prior_occupancy_pct` describe a PRIOR period and a unit
    // inventory. Filling them from this period to make a check run would be the defect the scrub is
    // written to refuse, committed from the outside — so the check that needs them stays not-run.
    expect(incomeFromT12(PASSED())).toEqual({ gross_potential_rent: 3_600_000, bad_debt: 41_000 });
  });

  it("supplies nothing when the mapping produced no categories", () => {
    expect(incomeFromT12(PASSED({ by_category: undefined }))).toEqual({});
  });
});
