import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { coverageKind, coverageLine, draftLine, fieldLogSuspect, type FieldLog } from "./fieldLogReadings";

/** Shaped from the engine's own output. The five fixtures below are the five cases measured
 *  against `dailylog.summary` when this was found. */
const base: FieldLog = {
  report_count: 3, submitted_count: 3, draft_count: 0,
  first_date: "2026-03-10", last_date: "2026-03-12",
  span_days: 3, logged_days: 3, coverage_pct: 100.0,
  coverage_note: "Coverage is 3 logged day(s) out of the 3-day window BETWEEN THE FIRST AND LAST "
    + "REPORT -- not out of the job.",
  total_manpower: 30, avg_manpower: 10,
  peak_manpower: { count: 10, date: "2026-03-10" }, weather_lost_days: 0, delay_days: 0,
  by_weather: { Clear: 3 }, by_impact: { None: 3 }, rows: [],
};
/** span 3 / logged 3 — measured 100.0% on a job of any length. */
const CONTIGUOUS = base;
/** span 1 / logged 1 — measured 100.0%. */
const SINGLE: FieldLog = { ...base, report_count: 1, submitted_count: 1, span_days: 1,
  logged_days: 1, last_date: "2026-03-10" };
/** span 31 / logged 20 — measured 64.5%, the only case where the figure says something. */
const GAPPY: FieldLog = { ...base, report_count: 20, submitted_count: 20, span_days: 31,
  logged_days: 20, coverage_pct: 64.5, first_date: "2026-03-01", last_date: "2026-03-31" };
/** Nothing dated — the engine returns null. */
const UNDATED: FieldLog = { ...base, span_days: 0, logged_days: 0, coverage_pct: null,
  first_date: null, last_date: null };
/** Three reports, none submitted — measured identical coverage to CONTIGUOUS. */
const ALL_DRAFT: FieldLog = { ...base, submitted_count: 0, draft_count: 3 };

describe("coverageKind", () => {
  it("calls an unbroken run vacuous, however long", () => {
    expect(coverageKind(CONTIGUOUS)).toBe("vacuous");
    expect(coverageKind(SINGLE)).toBe("vacuous");
  });

  it("calls a gappy window the only measured case", () => {
    expect(coverageKind(GAPPY)).toBe("windowed");
  });

  it("has no opinion when nothing is dated", () => {
    expect(coverageKind(UNDATED)).toBe("none");
  });
});

describe("coverageLine", () => {
  it("refuses to print a bare 100% when the window cannot disagree with the reports", () => {
    const line = coverageLine(CONTIGUOUS);
    expect(line).toContain("3 of 3 days");
    expect(line).toContain("whole window these reports span");
    expect(line).toContain("unbroken, not complete");
    expect(line).not.toContain("100%)");
  });

  it("says the same of a single report, which is the extreme of the same case", () => {
    expect(coverageLine(SINGLE)).toContain("1 of 1 day");
    expect(coverageLine(SINGLE)).not.toContain("1 of 1 days");    // singular
  });

  it("prints the percentage when the window HAS gaps, with the window named", () => {
    const line = coverageLine(GAPPY);
    expect(line).toContain("coverage 64.5%");
    expect(line).toContain("20 of 31 days logged in");
    expect(line).toContain("2026-03-01 → 2026-03-31");
  });

  it("says there is no window rather than printing a dash percentage", () => {
    expect(coverageLine(UNDATED)).toBe("coverage — (no report carries a date)");
  });

  it("gives an unbroken run and a gappy one different text", () => {
    // The defect: both rendered as "coverage 100%" / "coverage 64.5%" with no way to tell that the
    // first number is a tautology and the second is a measurement.
    expect(coverageLine(CONTIGUOUS)).not.toBe(coverageLine(GAPPY));
  });
});

describe("draftLine", () => {
  it("is silent when everything is submitted, so a clean card gets no banner", () => {
    expect(draftLine(CONTIGUOUS)).toBeNull();
  });

  it("says ALL when nothing is signed, and names what the figures include", () => {
    const line = draftLine(ALL_DRAFT)!;
    expect(line).toContain("all 3 reports are still DRAFT");
    expect(line).toContain("coverage included");
  });

  it("gives the submitted/draft split when some are signed", () => {
    const line = draftLine({ ...base, submitted_count: 1, draft_count: 2 })!;
    expect(line).toContain("2 of 3 reports still draft");
    expect(line).toContain("1 submitted");
  });

  it("separates the two field logs the card rendered identically", () => {
    // ALL_DRAFT and CONTIGUOUS agree on every number the old card printed.
    expect(ALL_DRAFT.coverage_pct).toBe(CONTIGUOUS.coverage_pct);
    expect(ALL_DRAFT.report_count).toBe(CONTIGUOUS.report_count);
    expect(ALL_DRAFT.total_manpower).toBe(CONTIGUOUS.total_manpower);
    expect(draftLine(ALL_DRAFT)).not.toBe(draftLine(CONTIGUOUS));
  });
});

describe("fieldLogSuspect", () => {
  it("is false only on a gappy window with everything submitted", () => {
    expect(fieldLogSuspect(GAPPY)).toBe(false);
    expect(fieldLogSuspect(CONTIGUOUS)).toBe(true);
    expect(fieldLogSuspect(UNDATED)).toBe(true);
    expect(fieldLogSuspect({ ...GAPPY, draft_count: 1, submitted_count: 19 })).toBe(true);
  });
});

/** The consumer, at source level — same bargain and same limit as `cpmRead.test.ts` records: an
 *  `if (false)` around the render would pass. What it catches is the revert. */
describe("the report centre reads it", () => {
  const panel = readFileSync(resolve(__dirname, "reportCenter.ts"), "utf8");

  it("renders the coverage line and the draft line through this module", () => {
    expect(panel).toContain('from "./fieldLogReadings"');
    expect(panel).toContain("coverageLine(s)");
    expect(panel).toContain("draftLine(s)");
  });

  it("no longer prints the field log's bare percentage", () => {
    // **The first draft of this asserted `"coverage ${s.coverage_pct"` appears NOWHERE in the file,
    // and it red on a different card.** `reportCenter.ts:715` prints the submittal register's
    // coverage the same way — and that one is NOT an instance: `required_total` and `logged_total`
    // are rendered immediately beside it, so its denominator is on screen. *A negative assertion
    // over a whole file is a claim about every site in it, including the ones it was not reasoned
    // about.* Scoped to the fragment unique to THIS card instead.
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    expect(code.join("\n")).not.toContain('coverage ${s.coverage_pct ?? "—"}% · total manpower');
  });
});
