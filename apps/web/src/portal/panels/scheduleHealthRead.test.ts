import { describe, expect, it } from "vitest";

import {
  cycleRows, dataDateNote, HEALTH_CSS, issuePageNote, issueRows, scopeLine,
  type ScheduleHealthRead,
} from "./scheduleHealthRead";

const OK = (over: Partial<ScheduleHealthRead> = {}): ScheduleHealthRead => ({
  available: true, grade: "B", score: 78, assessed: 10, skipped: 4, failed: 2,
  activity_count: 340, relationship_count: 512, data_date: "2026-10-01", issues: [],
  ...over,
});

describe("SCHEDHEALTH-PARITY", () => {
  it("states the network and the data date the grade is relative to", () => {
    expect(scopeLine(OK())).toBe("340 activity(ies) · 512 relationship(s) · as of 2026-10-01.");
  });

  it("states them on the CYCLIC refusal too, which carried none of them", () => {
    // The engine has `len(tasks)`, `len(links)` and the data date in hand when it catches the loop
    // and passed none of them. A planner told "the logic contains a loop" and nothing else cannot
    // see that the loop sits in a network of this size, which is what decides fix-or-rebuild.
    const cyc = OK({ available: false, reason: "the logic contains a loop", grade: null,
                     score: null, assessed: 0, skipped: 0, failed: 0,
                     cycle: ["A-100", "A-110", "A-120"] });
    expect(scopeLine(cyc)).toContain("340 activity(ies)");
    expect(cycleRows(cyc)).toEqual(["A-100", "A-110", "A-120"]);
  });

  it("says 0 / 0 / no data date on the empty refusal rather than going silent", () => {
    // That IS the measurement there, and it is the sentence that distinguishes "nothing planned"
    // from "we could not read it".
    const empty = OK({ available: false, reason: "no activities", grade: null, score: null,
                       assessed: 0, skipped: 0, failed: 0, activity_count: 0,
                       relationship_count: 0, data_date: null });
    expect(scopeLine(empty)).toBe("0 activity(ies) · 0 relationship(s) · no data date in the schedule.");
  });

  it("goes silent only when the server sent none of the three", () => {
    const old = OK({ activity_count: undefined, relationship_count: undefined,
                     data_date: undefined });
    expect(scopeLine(old)).toBeNull();
    expect(dataDateNote(old)).toBeNull();
  });

  it("WARNS when activities exist and no data date could be derived", () => {
    // The engine derives a data date from the activities when the caller passes none, so an absent
    // one over a real schedule means nothing in it carries a start — a finding, not a footnote.
    const n = dataDateNote(OK({ data_date: null, activity_count: 340 }))!;
    expect(n.tone).toBe("warn");
    expect(n.text).toContain("nothing to compare to");
  });

  it("does NOT warn about a missing data date over zero activities", () => {
    const n = dataDateNote(OK({ data_date: null, activity_count: 0 }))!;
    expect(n.tone).toBe("unknown");
    expect(n.text).toContain("no data date to compute against");
  });

  it("says nothing when the data date is present — `scopeLine` already carries it", () => {
    expect(dataDateNote(OK())).toBeNull();
  });

  it("ranks issues by severity and keeps the WARNINGS", () => {
    // An unresolvable predecessor token is a warning, and it is exactly the typo whose whole point
    // is that the old engine "discarded them, so a typo produced a schedule with a missing
    // dependency and no indication anywhere". Filtering to errors would throw it away again.
    const rows = issueRows(OK({ issues: [
      { severity: "info", code: "I", message: "calendar defaulted", action: "none" },
      { severity: "warning", code: "PRED", message: "predecessor 'A-99x' not found",
        action: "fix the token", row_key: "A-204", field: "predecessors" },
      { severity: "error", code: "DUR", message: "negative duration", action: "correct it" },
    ] }));
    expect(rows.map((x) => x.severity)).toEqual(["error", "warning", "info"]);
    expect(rows[1]!.where).toBe("A-204 · predecessors");
    expect(rows[1]!.message).toContain("A-99x");
  });

  it("puts an issue with an unknown severity LAST rather than first", () => {
    // `rank[x] ?? 3` — an unranked severity must not sort ahead of a real error by being `undefined`.
    const rows = issueRows(OK({ issues: [
      { severity: "mystery", code: "X", message: "m", action: "a" },
      { severity: "error", code: "E", message: "e", action: "a" },
    ] }));
    expect(rows.map((x) => x.severity)).toEqual(["error", "mystery"]);
  });

  it("handles an absent issues array and states both numbers when capped", () => {
    expect(issueRows(OK({ issues: undefined }))).toEqual([]);
    expect(issuePageNote(8, 23)).toBe("Showing 8 of 23 network issues.");
    expect(issuePageNote(3, 3)).toBe("");
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn", "unknown"] as const) expect(HEALTH_CSS[t]).toMatch(/^var\(--/);
  });
});
