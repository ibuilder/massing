/** CO-REJECTED — the change-order headline, and the term it did not name.
 *
 *  The fixture is the measured one: one executed COR at $100k, one approved at $50k, one pending at
 *  $25k and one **rejected at $400k**, with 5/3/2 schedule days on the live ones and 30 on the
 *  rejected. `total_value` is $575,000; the three state figures are $175,000.
 */
import { describe, expect, it } from "vitest";
import {
  COR_STATE_ORDER, type CoLog, coHeadline, coReconciles, coScheduleNote, coStateRows,
  rejectedShareNote,
} from "./coLogReadings";

const log = (over: Partial<CoLog> = {}): CoLog => ({
  co_count: 4,
  total_value: 575000, live_value: 175000,
  pending_value: 25000, approved_value: 50000, executed_value: 100000,
  rejected_value: 400000,
  total_schedule_days: 10, rejected_schedule_days: 30,
  change_events_open: 0, change_event_rom_exposure: 0,
  by_state: { executed: 1, approved: 1, submitted: 1, rejected: 1 },
  by_reason: { "Owner change": 4 }, ball_in_court: {},
  rows: [], ...over,
}) as CoLog;

describe("the headline leads with the live figure and names the refusal", () => {
  it("puts the exposure figure first and the raised total last", () => {
    // THE DEFECT, from the headline's side: `total` led, and it is the one number on the line that
    // nobody owes all of.
    const h = coHeadline(log());
    expect(h).toBe("4 CO(s) · live $175,000 · pending $25,000 · approved $50,000 "
                   + "· executed $100,000 · rejected $400,000 · raised to date $575,000");
    expect(h.indexOf("live")).toBeLessThan(h.indexOf("raised to date"));
  });

  it("names nothing about rejection when nothing was rejected", () => {
    const h = coHeadline(log({ rejected_value: 0, live_value: 175000, total_value: 175000 }));
    expect(h).not.toContain("rejected");
    expect(h).toContain("live $175,000");
    expect(h).toContain("raised to date $175,000");
  });

  it("omits the live figure against a server that does not send it, rather than inventing one", () => {
    // Subtracting an absent `rejected_value` from the total would produce the old wrong number
    // under a new and more confident label.
    const h = coHeadline(log({ live_value: undefined, rejected_value: undefined }));
    expect(h).not.toContain("live");
    expect(h).toContain("raised to date $575,000");
  });

  it("formats through `usd`, so a negative COR keeps the minus outside the currency mark", () => {
    // A deductive change order is a real thing and `ui/charts.test.ts` exists because eighteen
    // local formatters put the `$` on the wrong side of it.
    expect(coHeadline(log({ executed_value: -12000 }))).toContain("−$12,000");
  });
});

describe("the decomposition is checked, not presented", () => {
  it("reconciles on the measured fixture, both ways", () => {
    expect(coReconciles(log())).toBe(true);
  });

  it("reports false when live is not the sum of its three states", () => {
    expect(coReconciles(log({ live_value: 180000 }))).toBe(false);
  });

  it("reports false when total is not live plus rejected", () => {
    expect(coReconciles(log({ total_value: 600000 }))).toBe(false);
  });

  it("tolerates the server's 2dp rounding rather than failing on a half-cent", () => {
    expect(coReconciles(log({ live_value: 175000.001 }))).toBe(true);
  });

  it("is null, not false, when a key needed to check it is absent", () => {
    expect(coReconciles(log({ live_value: undefined }))).toBeNull();
    expect(coReconciles(log({ rejected_value: undefined }))).toBeNull();
  });
});

describe("the schedule figure states its exclusion", () => {
  it("names the rejected days that are NOT in the total", () => {
    const n = coScheduleNote(log());
    expect(n).toContain("10 schedule day(s) claimed");
    expect(n).toContain("a further 30 were claimed by the rejected CO(s)");
    // The asymmetry with the money total is the point, and it is said out loud.
    expect(n).toContain("the money figures above");
  });

  it("says only the plain figure when no rejected CO claimed time", () => {
    expect(coScheduleNote(log({ rejected_schedule_days: 0 })))
      .toBe("10 schedule day(s) claimed");
    expect(coScheduleNote(log({ rejected_schedule_days: undefined })))
      .toBe("10 schedule day(s) claimed");
  });
});

describe("the refused share is stated as a proportion", () => {
  it("says how much of the raised total is in no contract sum", () => {
    const n = rejectedShareNote(log());
    expect(n).toContain("70% of the $575,000 raised to date");
    expect(n).toContain("volume-of-change figure, not exposure");
  });

  it("is silent at zero, so the line does not fire on every render", () => {
    expect(rejectedShareNote(log({ rejected_value: 0 }))).toBeNull();
    expect(rejectedShareNote(log({ rejected_value: undefined }))).toBeNull();
  });

  it("is silent on an empty log rather than dividing by zero", () => {
    expect(rejectedShareNote(log({ co_count: 0, total_value: 0, rejected_value: 0 }))).toBeNull();
  });
});

describe("the by-state row is ordered by claim on money", () => {
  it("runs executed → approved → submitted → draft → rejected", () => {
    expect(coStateRows(log({ by_state: { rejected: 1, draft: 2, executed: 3, submitted: 4,
                                         approved: 5 } })).map((r) => r.state))
      .toEqual(["executed", "approved", "submitted", "draft", "rejected"]);
  });

  it("drops the zero states rather than padding the row", () => {
    expect(coStateRows(log()).map((r) => r.state))
      .toEqual(["executed", "approved", "submitted", "rejected"]);
  });

  it("APPENDS a state the order does not know, never drops it", () => {
    // The COR workflow is configurable (WORKFLOW-DARK made it so), so this list can legitimately
    // fall behind the register — and a count silently missing from a money report is worse than
    // one in an unexpected position.
    const rows = coStateRows(log({ by_state: { executed: 1, withdrawn: 2 } }));
    expect(rows.map((r) => r.state)).toEqual(["executed", "withdrawn"]);
  });

  it("is empty against a server that sends no by_state", () => {
    expect(coStateRows(log({ by_state: undefined }))).toEqual([]);
  });

  it("the order names the five states the module declares", () => {
    // `services/api/modules/cor/module.json` → draft, submitted, approved, rejected, executed.
    expect([...COR_STATE_ORDER].sort())
      .toEqual(["approved", "draft", "executed", "rejected", "submitted"]);
  });
});
