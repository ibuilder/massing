import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ItbPackageRow, ItbSummary } from "../../api/procurement";
import {
  itbCoverageLine, itbHeadline, itbSuspect, rateCell, unmatchedLine,
} from "./itbCoverage";

const row = (o: Partial<ItbPackageRow>): ItbPackageRow => ({
  ref: null, package: "", invited: 0, responses: 0, bonded: 0, response_rate: null,
  coverage: "no bids", rate_basis: "no invite list recorded", ...o,
});

const mk = (o: Partial<ItbSummary>): ItbSummary => ({
  package_count: 0, total_invited: 0, total_responses: 0, total_bonded: 0,
  packages_without_bids: 0, overall_response_rate: null, rated_packages: 0, unrated_packages: 0,
  rated_responses: 0, unmatched_submissions: 0, submission_count: 0, coverage_note: "", rows: [],
  ...o,
});

/** `itb.summarize`'s real output, dumped from the engine: Concrete 3/10, Painting 5 bids with no
 *  invite list, Glazing 3 invited and no bids, plus one bid naming a package that does not exist.
 *  **The old card printed `8/13 responses` — 62% — where the rated packages give 23.1%.** */
const MIXED: ItbSummary = mk({
  package_count: 3, total_invited: 13, total_responses: 8, total_bonded: 8,
  packages_without_bids: 1, overall_response_rate: 23.1, rated_packages: 2, unrated_packages: 1,
  rated_responses: 3, unmatched_submissions: 1, submission_count: 9,
  coverage_note: "The response rate is over the 2 package(s) that record an invite list; 1 "
    + "package(s) do not and are not in it. 1 submission(s) name a package that does not exist "
    + "here and are counted in NO package above -- check the package name on them.",
  rows: [
    row({ ref: "BP-03", package: "Glazing", invited: 3, response_rate: 0.0, coverage: "no bids",
      rate_basis: "invited" }),
    row({ ref: "BP-01", package: "Concrete", trade: "Concrete", invited: 10, responses: 3,
      bonded: 3, low_bid: 1000, response_rate: 30.0, coverage: "covered", rate_basis: "invited" }),
    row({ ref: "BP-02", package: "Painting", responses: 5, bonded: 5, low_bid: 1000,
      response_rate: null, coverage: "covered", rate_basis: "no invite list recorded" }),
  ],
});

/** Every package rated, every bid matched. */
const CLEAN: ItbSummary = mk({
  package_count: 1, total_invited: 10, total_responses: 3, total_bonded: 3,
  overall_response_rate: 30.0, rated_packages: 1, rated_responses: 3, submission_count: 3,
  coverage_note: "The response rate is over the 1 package(s) that record an invite list -- every "
    + "package records one.",
  rows: [row({ ref: "BP-01", package: "Concrete", invited: 10, responses: 3, bonded: 3,
    response_rate: 30.0, coverage: "covered", rate_basis: "invited" })],
});

const EMPTY: ItbSummary = mk({ coverage_note: "No bid packages yet." });

describe("itbHeadline", () => {
  /** **The two-population fraction, gone.** */
  it("does not print responses over a denominator from a different population", () => {
    const line = itbHeadline(MIXED);
    expect(line).not.toContain("8/13");
    expect(line).toContain("8 bids received");
    expect(line).toContain("23.1% response across 2 invited packages");
    expect(MIXED.rated_responses).toBeLessThan(MIXED.total_responses);
  });

  it("omits the rate entirely when no package records an invite list", () => {
    const unrated = mk({ package_count: 2, total_responses: 4, unrated_packages: 2,
      submission_count: 4, coverage_note: "x" });
    const line = itbHeadline(unrated);
    expect(line).toContain("4 bids received");
    expect(line).not.toContain("%");
    expect(line).not.toContain("0");
  });

  it("names the no-bid packages, which is the coverage gap", () => {
    expect(itbHeadline(MIXED)).toContain("1 with no bids");
    expect(itbHeadline(CLEAN)).not.toContain("no bids");
  });

  it("is singular on one package and one bid", () => {
    const one = mk({ package_count: 1, total_responses: 1, rated_packages: 1,
      overall_response_rate: 10.0, rated_responses: 1 });
    expect(itbHeadline(one)).toContain("1 package ");
    expect(itbHeadline(one)).toContain("1 bid received");
    expect(itbHeadline(one)).toContain("1 invited package");
    expect(itbHeadline(one)).not.toContain("packages");
  });

  it("says so when there are no packages rather than printing zeroes", () => {
    expect(itbHeadline(EMPTY)).toBe("No bid packages yet.");
  });
});

describe("rateCell", () => {
  /** An unknown denominator and a 0% response were the same cell. */
  it("tells an unrecorded invite list apart from nobody bidding", () => {
    const noList = MIXED.rows.find((r) => r.package === "Painting")!;
    const noBids = MIXED.rows.find((r) => r.package === "Glazing")!;
    expect(noList.responses).toBe(5);
    expect(noBids.responses).toBe(0);
    expect(rateCell(noList)).not.toBe(rateCell(noBids));
    expect(rateCell(noList)).toContain("no invite list");
    expect(rateCell(noBids)).toBe("0%");
  });

  it("prints the percentage when there is a denominator", () => {
    expect(rateCell(MIXED.rows.find((r) => r.package === "Concrete")!)).toBe("30%");
  });

  it("never renders a null rate as a number", () => {
    expect(rateCell(row({ response_rate: null }))).not.toMatch(/\d/);
  });
});

describe("unmatchedLine", () => {
  it("reports bids that found no package", () => {
    const line = unmatchedLine(MIXED) ?? "";
    expect(line).toContain("1 bid names a package that does not exist");
    expect(line).toContain("counted in no package below");
  });

  it("is silent when every bid matched", () => {
    expect(unmatchedLine(CLEAN)).toBeNull();
    expect(unmatchedLine(EMPTY)).toBeNull();
  });

  it("agrees in number", () => {
    expect(unmatchedLine(mk({ unmatched_submissions: 3 })) ?? "").toContain("3 bids name");
  });
});

describe("itbCoverageLine", () => {
  it("reads the engine's sentence rather than rebuilding it", () => {
    expect(itbCoverageLine(MIXED)).toBe(MIXED.coverage_note);
    expect(itbCoverageLine(CLEAN)).toContain("every package records one");
  });

  it("still gives the split if the server predates the note", () => {
    const old = mk({ package_count: 3, rated_packages: 2, coverage_note: "" });
    expect(itbCoverageLine(old)).toContain("2 of 3");
  });
});

describe("itbSuspect", () => {
  it("flags a screen whose coverage should not be read at face value", () => {
    expect(itbSuspect(MIXED)).toBe(true);
    expect(itbSuspect(mk({ unrated_packages: 1 }))).toBe(true);
    expect(itbSuspect(mk({ unmatched_submissions: 1 }))).toBe(true);
    expect(itbSuspect(CLEAN)).toBe(false);
    expect(itbSuspect(EMPTY)).toBe(false);
  });
});

/** The consumer, at source level — same bargain and limit as the sibling read-modules. */
describe("the report centre reads it", () => {
  const panel = readFileSync(resolve(__dirname, "../../reportCenter.ts"), "utf8");

  it("renders the headline, the coverage note, the unmatched line and the rate column", () => {
    expect(panel).toContain('from "./portal/panels/itbCoverage"');
    expect(panel).toContain("itbHeadline(t)");
    expect(panel).toContain("itbCoverageLine(t)");
    expect(panel).toContain("unmatchedLine(t)");
    expect(panel).toContain("rateCell(r)");
  });

  it("no longer prints the two-population fraction", () => {
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    expect(code.join("\n")).not.toContain("${t.total_responses}/${t.total_invited}");
  });

  it("stopped casting the rows to any, which is what hid these fields from every audit", () => {
    const code = panel.split("\n").filter((l) => !l.trim().startsWith("//"));
    expect(code.join("\n")).not.toContain("t.rows.map((r: any)");
  });
});
