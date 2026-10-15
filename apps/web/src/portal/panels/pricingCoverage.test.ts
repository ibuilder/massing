import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { PricingReconcile } from "../../api/cost";
import {
  pricedCoverage, pricedCoverageLine, pricingSuspect, varianceBasisLine,
} from "./pricingCoverage";

/** Every fixture below is `pricing.reconcile`'s real output, dumped from the engine rather than
 *  written out here — `lines` dropped, since this module reads only the summary. */
const mk = (o: Partial<PricingReconcile>): PricingReconcile => ({
  lines: [], line_count: 0, matched: 0, unmatched: 0, unit_mismatch: 0, comparable_line_count: 0,
  priced_total: 0, estimated_total: 0, comparable_priced_total: 0, variance_total: null,
  coverage_note: "", pricing_source: "book", message: null, ...o,
});

/** `test_pricing.py`'s own fixture — 2 priced of 4, 1 comparable. The old `variance_total` was
 *  `+12250`; the comparable variance is `-1500`, the figure the file asserts at row level. */
const REPO_FIXTURE = mk({
  line_count: 4, matched: 2, unmatched: 1, unit_mismatch: 1, comparable_line_count: 1,
  priced_total: 32250, estimated_total: 20000, comparable_priced_total: 18500,
  variance_total: -1500,
  coverage_note: "2 of 4 takeoff line(s) priced (1 with no price-book match; 1 matched in the book "
    + "but refused on the unit). The variance is over the 1 line(s) carrying BOTH a price and an "
    + "estimated unit price, which is not the 2 priced line(s) above.",
});

/** 400 takeoff lines, 3 of them priced. */
const THIN = mk({
  line_count: 400, matched: 3, unmatched: 397, comparable_line_count: 3,
  priced_total: 55500, estimated_total: 27000, comparable_priced_total: 55500,
  variance_total: 28500,
  coverage_note: "3 of 400 takeoff line(s) priced (397 with no price-book match). The variance "
    + "covers all 3 priced line(s).",
});

/** The same three lines, alone. **Byte-identical to THIN on every money figure.** */
const FULL = mk({
  line_count: 3, matched: 3, comparable_line_count: 3,
  priced_total: 55500, estimated_total: 27000, comparable_priced_total: 55500,
  variance_total: 28500,
  coverage_note: "3 of 3 takeoff line(s) priced. The variance covers all 3 priced line(s).",
});

/** Priced, and nothing to compare it to. `variance_total` is `null`, not `0`. */
const NO_ESTIMATE = mk({
  line_count: 1, matched: 1, comparable_line_count: 0, priced_total: 18500,
  coverage_note: "1 of 1 takeoff line(s) priced. No line carries both a price and an estimated "
    + "unit price, so there is no variance to report -- not a variance of zero.",
});

const EMPTY = mk({ coverage_note: "No takeoff quantities to price.",
  message: "No quantities to price." });

describe("pricedCoverage", () => {
  it("separates nothing priced, some priced and all priced", () => {
    expect(pricedCoverage(EMPTY)).toBe("none");
    expect(pricedCoverage(THIN)).toBe("partial");
    expect(pricedCoverage(REPO_FIXTURE)).toBe("partial");
    expect(pricedCoverage(FULL)).toBe("full");
    expect(pricedCoverage(NO_ESTIMATE)).toBe("full");
  });

  it("calls a priced-nothing takeoff `none` rather than `full` on a zero denominator", () => {
    // 0 of 0 is not complete coverage, and `matched >= line_count` is true for it.
    expect(pricedCoverage(mk({ line_count: 0, matched: 0 }))).toBe("none");
  });
});

describe("pricedCoverageLine", () => {
  /** **This is the coverage defect, in one assertion.** */
  it("tells 3 of 400 priced apart from 3 of 3, which agree on every money figure", () => {
    expect(THIN.priced_total).toBe(FULL.priced_total);
    expect(THIN.estimated_total).toBe(FULL.estimated_total);
    expect(THIN.variance_total).toBe(FULL.variance_total);
    expect(pricedCoverageLine(THIN)).not.toBe(pricedCoverageLine(FULL));
    expect(pricedCoverageLine(THIN)).toContain("3 of 400");
    expect(pricedCoverageLine(THIN)).toContain("397");
  });

  it("reads the engine's sentence rather than rebuilding it", () => {
    // RENTROLL-BASIS shipped a second copy of an engine's note and the two had to be kept in
    // agreement by hand. One source.
    expect(pricedCoverageLine(REPO_FIXTURE)).toBe(REPO_FIXTURE.coverage_note);
  });

  it("still refuses a bare count if the server predates the note", () => {
    const old = mk({ line_count: 400, matched: 3, coverage_note: "" });
    expect(pricedCoverageLine(old)).toContain("3 of 400");
    expect(pricedCoverageLine(mk({ coverage_note: "" }))).toContain("No takeoff quantities");
  });
});

describe("varianceBasisLine", () => {
  it("names the comparable population when it is smaller than the priced one", () => {
    const line = varianceBasisLine(REPO_FIXTURE);
    expect(line).toContain("$1,500 under estimate");
    expect(line).toContain("1 line priced AND estimated, not the 2 priced above");
    expect(line).toContain("$18,500 priced vs $20,000 estimated");
  });

  it("does not assert a contrast that does not exist", () => {
    // A warning a reader checks once and finds spurious is a warning they stop reading.
    const line = varianceBasisLine(THIN);
    expect(line).toContain("all 3 lines priced");
    expect(line).not.toContain("not the");
  });

  it("says over or under, and never reads the sign off the wrong total", () => {
    // The old card coloured `priced_total - estimated_total`, which on REPO_FIXTURE is +12,250:
    // red, an overrun, on a takeoff the book prices BELOW estimate.
    expect(REPO_FIXTURE.priced_total - REPO_FIXTURE.estimated_total).toBeGreaterThan(0);
    expect(REPO_FIXTURE.variance_total).toBeLessThan(0);
    expect(varianceBasisLine(REPO_FIXTURE)).toContain("under estimate");
    expect(varianceBasisLine(THIN)).toContain("over estimate");
  });

  it("prints the comparable total, not the priced total, beside the estimate", () => {
    expect(varianceBasisLine(REPO_FIXTURE)).not.toContain("$32,250");
  });

  it("says there is no variance rather than falling silent beside a priced total", () => {
    const line = varianceBasisLine(NO_ESTIMATE);
    expect(line).toContain("no variance to report");
    expect(line).toContain("not a variance of zero");
  });

  it("treats a null variance and a zero variance as different answers", () => {
    const level = mk({ line_count: 1, matched: 1, comparable_line_count: 1, priced_total: 18500,
      estimated_total: 18500, comparable_priced_total: 18500, variance_total: 0 });
    expect(varianceBasisLine(level)).toContain("level with estimate");
    expect(varianceBasisLine(level)).not.toContain("no variance to report");
  });
});

describe("pricingSuspect", () => {
  it("flags a partly priced takeoff", () => {
    expect(pricingSuspect(THIN)).toBe(true);
    expect(pricingSuspect(REPO_FIXTURE)).toBe(true);
  });

  it("flags a fully priced takeoff whose variance covers fewer lines than the price", () => {
    const over = mk({ line_count: 5, matched: 5, comparable_line_count: 1, priced_total: 92500,
      estimated_total: 9000, comparable_priced_total: 18500, variance_total: 9500,
      coverage_note: "5 of 5 takeoff line(s) priced. The variance is over the 1 line(s) carrying "
        + "BOTH a price and an estimated unit price, which is not the 5 priced line(s) above." });
    expect(pricedCoverage(over)).toBe("full");
    expect(pricingSuspect(over)).toBe(true);
  });

  it("is quiet when the price and the variance cover the same whole takeoff", () => {
    expect(pricingSuspect(FULL)).toBe(false);
    // Fully priced with nothing to compare is not "suspect" — `varianceBasisLine` says so plainly
    // instead, and a warning colour on every unestimated takeoff would be noise.
    expect(pricingSuspect(NO_ESTIMATE)).toBe(false);
  });
});

/** The consumer, at source level — the same bargain and the same limit the sibling read-modules
 *  record: an `if (false)` around the render would pass. What it catches is the revert. */
describe("the analytics panel reads it", () => {
  const panel = readFileSync(resolve(__dirname, "analytics.ts"), "utf8");

  it("renders the coverage and the variance basis through this module", () => {
    expect(panel).toContain('from "./pricingCoverage"');
    expect(panel).toContain("pricedCoverageLine(r)");
    expect(panel).toContain("varianceBasisLine(r)");
    expect(panel).toContain("pricingSuspect(r)");
  });

  it("no longer prints the pricing variance as a bare money figure", () => {
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    // Scoped to this card's own fragment: `cmoney` is the right formatter for the dozen other
    // figures in this panel, so a whole-file ban on it would red on cards this item never looked at.
    expect(code.join("\n")).not.toContain("variance <b style=");
    expect(code.join("\n")).not.toContain("vs estimate ${cmoney(r.estimated_total)}");
  });
});
