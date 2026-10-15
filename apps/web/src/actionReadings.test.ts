import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { ActionTracker } from "./actionReadings";
import { actionHeadline, historicBy, meetingLine, openPriorities, owedBy,
  rollupBasis } from "./actionReadings";

/**
 * ACTION-SUBSET — the tracker's only declared rollup counted finished work.
 *
 * Measured against a live route on this exact register: 14 items, 11 of them High and DONE under
 * Ana, 1 High open under Ben, 2 Low open under Ben and Cara. `by_assignee` reported `Ana: 11` —
 * and Ana has nothing outstanding. `services/api/test_actions.py` asserts the same shape at the
 * route.
 */
function tr(over: Partial<ActionTracker> = {}): ActionTracker {
  return {
    action_count: 14, open_count: 3, done_count: 11, overdue_count: 1, completion_pct: 78.6,
    meeting_count: 2, last_meeting: "2026-10-01",
    by_assignee: { Ana: 11, Ben: 2, Cara: 1 },
    by_priority: { High: 12, Low: 2 },
    by_state: { done: 11, open: 3 },
    open_by_assignee: { Ben: 2, Cara: 1 },
    open_by_priority: { High: 1, Low: 2 },
    rollup_basis: "`by_assignee` and `by_priority` are over EVERY action item, done or not.",
    meetings_by_type: { OAC: 2 },
    rows: [],
    ...over,
  } as ActionTracker;
}

describe("the outstanding-work headline", () => {
  it("leads with what is outstanding, against the register total", () => {
    expect(actionHeadline(tr()))
      .toBe("3 of 14 action item(s) outstanding · 1 OVERDUE · 78.6% complete");
  });

  it("omits the overdue clause when nothing is overdue", () => {
    expect(actionHeadline(tr({ overdue_count: 0 }))).not.toContain("OVERDUE");
  });

  it("reports an empty register as empty", () => {
    expect(actionHeadline(tr({ action_count: 0, open_count: 0, completion_pct: null })))
      .toBe("No action items recorded yet.");
  });
});

describe("who owes what", () => {
  it("counts only the OUTSTANDING items, which is the whole finding", () => {
    // `by_assignee` put Ana first with 11; Ana has zero outstanding.
    const o = owedBy(tr())!;
    expect(o).toBe("Outstanding by assignee: Ben 2 · Cara 1");
    expect(o).not.toContain("Ana");
  });

  it("is absent when nothing is outstanding, rather than an empty heading", () => {
    expect(owedBy(tr({ open_by_assignee: {}, open_count: 0 }))).toBeNull();
  });

  it("bounds the list and says how many it left out", () => {
    const many = Object.fromEntries(Array.from({ length: 9 }, (_, i) => [`P${i}`, 9 - i]));
    expect(owedBy(tr({ open_by_assignee: many }))).toContain("· 3 more");
  });
});

describe("the open priority mix", () => {
  it("is over the open items, not the register", () => {
    // `by_priority` said High 12; exactly one High item is live.
    expect(openPriorities(tr())).toBe("Outstanding by priority: High 1 · Low 2");
  });

  it("is absent on an empty open set", () => {
    expect(openPriorities(tr({ open_by_priority: {} }))).toBeNull();
  });
});

describe("the historic rollup", () => {
  it("is labelled as a different question, over the whole register", () => {
    expect(historicBy(tr())).toBe("Across all 14 item(s), done or not: Ana 11 · Ben 2 · Cara 1");
  });

  it("is suppressed when nothing is done, because it would restate the open rollup", () => {
    // Printing both identical lines invites a reader to treat them as two findings.
    expect(historicBy(tr({ done_count: 0 }))).toBeNull();
  });
});

describe("the basis and the meeting line", () => {
  it("returns the engine's basis verbatim", () => {
    expect(rollupBasis(tr())).toBe(tr().rollup_basis);
  });

  it("keeps meetings as their own register", () => {
    expect(meetingLine(tr())).toBe("2 meeting(s) · last 2026-10-01 · OAC 2");
    expect(meetingLine(tr({ meeting_count: 0 }))).toBe("No meetings logged.");
    expect(meetingLine(tr({ last_meeting: null }))).toContain("last undated");
  });
});

describe("the readings reach the screen", () => {
  const RC = readFileSync("src/reportCenter.ts", "utf8");

  it("renders the open-scoped rollups and the basis", () => {
    expect(RC).toContain("escapeHtml(actionHeadline(s))");
    expect(RC).toContain("const owed = owedBy(s)");
    expect(RC).toContain("const pri = openPriorities(s)");
    expect(RC).toContain("escapeHtml(rollupBasis(s))");
  });

  it("no longer prints the whole-register headline that hid the subset", () => {
    // Anchored on the ACTION tracker's own spelling. The first draft asserted the absence of
    // `"${s.open_count} open · ${s.overdue_count} overdue"`, which the SUBMITTAL register one card
    // down uses legitimately — an absence assertion over a shared spelling fails on somebody else's
    // correct code, which is the substring-probe mistake in its negative form.
    expect(RC).not.toContain("${s.action_count} action items");
    expect(RC).toContain("api.submittalRegister(pid)");   // the neighbour it must not rule on
  });

  it("reads the rows through the declared shape rather than casting to any", () => {
    // `rows: Record<string, unknown>[]` forced `(r: any)`, which put `overdue` out of reach of
    // every audit built on these declarations.
    expect(RC).toContain("s.rows.map((r) => [r.ref ?? \"\", r.subject ?? \"\", r.assignee");
    expect(RC).not.toContain("s.rows.map((r: any) => [r.ref ?? \"\", r.subject ?? \"\", r.assignee");
  });
});
