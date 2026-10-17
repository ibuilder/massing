import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { SubmittalRegister, SubmittalRow } from "../../api/procurement";
import {
  closedStatesCaveat, overdueCell, overdueCoverage, resubmittalLine, submittalCoverageLine,
  submittalHeadline, submittalSuspect, turnaroundLine,
} from "./submittalCoverage";

/** Every fixture is `submittals.register`'s real output, dumped from the engine rather than written
 *  out here. */
const mk = (o: Partial<SubmittalRegister>): SubmittalRegister => ({
  submittal_count: 0, open_count: 0, overdue_count: 0, dated_count: 0, undated_count: 0,
  avg_turnaround_days: null, turnaround_count: 0, needs_resubmittal_count: 0,
  closed_states: ["closed"], workflow_overridden: false, by_status: {}, by_section: {},
  coverage_note: "", rows: [], ...o,
});
const row = (o: Partial<SubmittalRow>): SubmittalRow => ({
  ref: null, title: null, spec_section: "08 44 13", type: null, responsible: null,
  disposition: null, status: "ae_review", required_on_site: null, turnaround_days: null,
  overdue: false, overdue_assessed: false, needs_resubmittal: false, closed: false,
  ball_in_court: "ae_review", ...o,
});

/** One submittal the A/E sent back marked "Revise & Resubmit", six weeks past its required-on-site
 *  date. Before this item: `0 open, 0 overdue`, because `returned` was in `CLOSED_STATES`. */
const REJECTED = mk({
  submittal_count: 1, open_count: 1, overdue_count: 1, dated_count: 1,
  avg_turnaround_days: 9.0, turnaround_count: 1, needs_resubmittal_count: 1,
  by_status: { returned: 1 },
  coverage_note: "1 submittal came back marked for resubmittal and is still open.",
  rows: [row({ ref: "S-001", title: "CW shop dwgs", disposition: "Revise & Resubmit",
    status: "returned", required_on_site: "2026-09-01", turnaround_days: 9, overdue: true,
    overdue_assessed: true, needs_resubmittal: true, ball_in_court: "returned" })],
});

/** The same submittal, APPROVED. **Identical on every corrected count.** */
const APPROVED = mk({
  submittal_count: 1, open_count: 1, overdue_count: 1, dated_count: 1,
  avg_turnaround_days: 9.0, turnaround_count: 1, needs_resubmittal_count: 0,
  by_status: { returned: 1 },
  coverage_note: "All 1 submittal carries the dates both counts need, and none is awaiting "
    + "resubmittal.",
  rows: [row({ ref: "S-002", title: "CW shop dwgs", disposition: "Approved", status: "returned",
    required_on_site: "2026-09-01", turnaround_days: 9, overdue: true, overdue_assessed: true,
    ball_in_court: "returned" })],
});

/** 40 submittals in A/E review, no required-on-site date recorded on any of them. */
const UNDATED = mk({
  submittal_count: 40, open_count: 40, undated_count: 40, by_status: { ae_review: 40 },
  coverage_note: "Overdue is over the 0 of 40 carrying a required-on-site date (40 have none, so "
    + "they cannot be counted late); the average turnaround is over the 0 of 40 carrying both a "
    + "received and a returned date.",
  rows: [row({ ref: "S-000", spec_section: "09" })],
});

/** 40 submittals, 2 of them reviewed — `avg_turnaround_days` is over those 2. */
const THIN = mk({
  submittal_count: 40, open_count: 38, undated_count: 40, avg_turnaround_days: 3.5,
  turnaround_count: 2, by_status: { ae_review: 38, closed: 2 },
  coverage_note: "Overdue is over the 0 of 40 carrying a required-on-site date (40 have none, so "
    + "they cannot be counted late); the average turnaround is over the 2 of 40 carrying both a "
    + "received and a returned date.",
});

/** The same two reviewed submittals, alone. Byte-identical on the turnaround figure. */
const WHOLE = mk({
  submittal_count: 2, undated_count: 2, avg_turnaround_days: 3.5, turnaround_count: 2,
  by_status: { closed: 2 },
  coverage_note: "Overdue is over the 0 of 2 carrying a required-on-site date (2 have none, so "
    + "they cannot be counted late).",
});

const EMPTY = mk({ coverage_note: "No submittals in the register." });

describe("overdueCoverage", () => {
  it("separates an empty register, nothing assessable, some and all", () => {
    expect(overdueCoverage(EMPTY)).toBe("empty");
    expect(overdueCoverage(UNDATED)).toBe("none");
    expect(overdueCoverage(mk({ submittal_count: 10, dated_count: 4, undated_count: 6 })))
      .toBe("partial");
    expect(overdueCoverage(REJECTED)).toBe("full");
  });

  it("does not call an empty register fully assessable on a zero denominator", () => {
    // `dated >= submittal_count` is true for 0 of 0, and so is `!dated`. Neither is the same
    // finding: one is an empty log, the other a log nothing can be measured against.
    expect(overdueCoverage(mk({}))).toBe("empty");
    expect(overdueCoverage(mk({}))).not.toBe("full");
  });
});

describe("submittalHeadline", () => {
  /** **The defect, in one assertion.** */
  it("tells a rejected submittal from an approved one, which agree on every count", () => {
    expect(REJECTED.open_count).toBe(APPROVED.open_count);
    expect(REJECTED.overdue_count).toBe(APPROVED.overdue_count);
    expect(REJECTED.avg_turnaround_days).toBe(APPROVED.avg_turnaround_days);
    expect(REJECTED.by_status).toEqual(APPROVED.by_status);

    expect(submittalHeadline(REJECTED)).not.toBe(submittalHeadline(APPROVED));
    expect(submittalHeadline(REJECTED)).toContain("1 awaiting resubmittal");
    expect(submittalHeadline(APPROVED)).not.toContain("resubmittal");
  });

  it("refuses to print `0 overdue` when nothing could be assessed", () => {
    // 40 submittals in review and no required-on-site date on any of them. `0 overdue` reads as
    // "nothing is late"; it means "nothing can be measured".
    expect(UNDATED.overdue_count).toBe(0);
    expect(submittalHeadline(UNDATED)).toContain("lateness not assessable");
    expect(submittalHeadline(UNDATED)).not.toContain("0 overdue");
  });

  it("names the assessable population when it is smaller than the register", () => {
    const partly = mk({ submittal_count: 10, open_count: 10, overdue_count: 2, dated_count: 4,
      undated_count: 6 });
    expect(submittalHeadline(partly)).toContain("2 overdue of 4 dated");
  });

  it("does not assert a contrast that does not exist", () => {
    // A warning a reader checks once and finds spurious is a warning they stop reading.
    expect(submittalHeadline(REJECTED)).toContain("1 overdue");
    expect(submittalHeadline(REJECTED)).not.toContain("of 1 dated");
  });

  it("says an empty register is empty rather than reporting zeroes", () => {
    expect(submittalHeadline(EMPTY)).toBe("No submittals logged yet");
  });
});

describe("turnaroundLine", () => {
  it("names the population when the average is over part of the register", () => {
    expect(THIN.avg_turnaround_days).toBe(WHOLE.avg_turnaround_days);
    expect(turnaroundLine(THIN)).not.toBe(turnaroundLine(WHOLE));
    expect(turnaroundLine(THIN)).toContain("3.5 d over 2 of 40");
    expect(turnaroundLine(WHOLE)).toContain("all 2 reviewed submittals");
  });

  it("says there is no turnaround rather than printing an em dash beside an open count", () => {
    const line = turnaroundLine(UNDATED);
    expect(line).toContain("no turnaround to report");
    expect(line).toContain("not a turnaround of zero");
  });

  it("treats a null average and a zero average as different answers", () => {
    const sameday = mk({ submittal_count: 1, avg_turnaround_days: 0, turnaround_count: 1 });
    expect(turnaroundLine(sameday)).toContain("0 d");
    expect(turnaroundLine(sameday)).not.toContain("no turnaround to report");
  });
});

describe("submittalCoverageLine", () => {
  it("reads the engine's sentence rather than rebuilding it", () => {
    expect(submittalCoverageLine(UNDATED)).toBe(UNDATED.coverage_note);
  });

  it("still refuses a bare count if the server predates the note", () => {
    const old = mk({ submittal_count: 40, dated_count: 2, coverage_note: "" });
    expect(submittalCoverageLine(old)).toContain("2 of 40");
    expect(submittalCoverageLine(mk({ coverage_note: "" }))).toContain("No submittals");
  });
});

describe("resubmittalLine", () => {
  it("names the rows and what the A/E wrote on them", () => {
    const line = resubmittalLine(REJECTED);
    expect(line).toContain("1 submittal came back for resubmittal");
    expect(line).toContain("S-001 (Revise & Resubmit)");
  });

  it("is null when nothing is owed back", () => {
    expect(resubmittalLine(APPROVED)).toBeNull();
    expect(resubmittalLine(UNDATED)).toBeNull();
    expect(resubmittalLine(EMPTY)).toBeNull();
  });

  it("caps the named rows and says how many more there are", () => {
    const many = mk({ submittal_count: 6, open_count: 6, needs_resubmittal_count: 6,
      rows: Array.from({ length: 6 }, (_, i) =>
        row({ ref: `R${i}`, status: "returned", disposition: "Rejected", needs_resubmittal: true })) });
    const line = resubmittalLine(many) || "";
    expect(line).toContain("6 submittals came back");
    expect(line).toContain("+2 more");
    expect(line).not.toContain("R5 (");
  });
});

describe("closedStatesCaveat", () => {
  it("is null on the shipped workflow — a caveat on every project is noise", () => {
    expect(closedStatesCaveat(REJECTED)).toBeNull();
  });

  it("says what `closed` means when the project replaced the workflow", () => {
    const over = mk({ ...REJECTED, workflow_overridden: true, closed_states: ["archived"] });
    expect(closedStatesCaveat(over)).toContain("replaced the submittal workflow");
    expect(closedStatesCaveat(over)).toContain("archived");
  });

  it("says so rather than claiming a state when the set could not be resolved", () => {
    const over = mk({ workflow_overridden: true, closed_states: [] });
    expect(closedStatesCaveat(over)).toContain("could not resolve");
  });
});

describe("overdueCell", () => {
  it("renders a row with no required-on-site date differently from an on-time one", () => {
    // `overdue: false` means two different things, and the old table printed the status alone for
    // both of them.
    const blank = row({ overdue_assessed: false });
    const ontime = row({ overdue_assessed: true, required_on_site: "2030-01-01" });
    expect(overdueCell(blank)).toBe("—");
    expect(overdueCell(ontime)).toBe("on time");
    const late = REJECTED.rows[0];
    expect(late, "the REJECTED fixture lost its row").toBeDefined();
    expect(overdueCell(late as SubmittalRow)).toBe("OVERDUE");
    expect(overdueCell(blank)).not.toBe(overdueCell(ontime));
  });
});

describe("submittalSuspect", () => {
  it("flags an unassessable register, a partly dated one and work owed back", () => {
    expect(submittalSuspect(UNDATED)).toBe(true);
    expect(submittalSuspect(THIN)).toBe(true);
    expect(submittalSuspect(REJECTED)).toBe(true);
    expect(submittalSuspect(mk({ submittal_count: 10, dated_count: 4, undated_count: 6 }))).toBe(true);
  });

  it("is quiet on a fully dated register with nothing owed, and on an empty one", () => {
    expect(submittalSuspect(APPROVED)).toBe(false);
    // Nothing to be missing.
    expect(submittalSuspect(EMPTY)).toBe(false);
  });
});

/** The consumer, at source level — the same bargain and the same limit the sibling read-modules
 *  record: an `if (false)` around the render would pass. What it catches is the revert. */
describe("the report-centre card reads it", () => {
  const panel = readFileSync(resolve(__dirname, "../../reportCenter.ts"), "utf8");

  it("renders the headline, turnaround, coverage, resubmittals and the workflow caveat", () => {
    expect(panel).toContain('from "./portal/panels/submittalCoverage"');
    for (const call of ["submittalHeadline(s)", "turnaroundLine(s)", "submittalCoverageLine(s)",
      "submittalSuspect(s)", "resubmittalLine(s)", "closedStatesCaveat(s)", "overdueCell(r)"]) {
      expect(panel, `the card no longer calls ${call}`).toContain(call);
    }
  });

  it("no longer prints the four bare counts, nor casts the rows through `any`", () => {
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    const src = code.join("\n");
    expect(src).not.toContain("${s.overdue_count} overdue · avg turnaround");
    expect(src).not.toContain("s.rows.map((r: any) => [r.ref ?? \"\", r.spec_section");
  });
});
