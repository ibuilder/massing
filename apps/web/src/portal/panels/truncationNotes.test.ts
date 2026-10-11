import { describe, expect, it } from "vitest";

import { scheduleQuantity, scheduleScope } from "./equipment";
import { gapShown } from "./operations";
import { earlierNote } from "./topicBoard";

/** The two places a server-side cap becomes something a person can read.
 *
 *  Both engines were fixed to report a total beside their count (TRUNC-DISCLOSE). These are the
 *  half that renders it — because a disclosure nobody surfaces is not a disclosure, and the API
 *  being honest does not help someone reading a screen. */
describe("scheduleScope — the equipment RFQ header", () => {
  it("says only the count when the schedule is whole", () => {
    expect(scheduleScope({ line_count: 12, line_total: 12, truncated: false })).toBe("12 lines");
  });

  it("THE POINT: says how many it is not showing when the schedule is capped", () => {
    // A buyout package that looks complete and is short under-buys. The header used to read
    // "4000 lines" whether or not 4000 was the whole schedule.
    expect(scheduleScope({ line_count: 4000, line_total: 4600, truncated: true }))
      .toBe("4000 of 4600 lines");
  });

  it("falls back to the plain count against a server that does not send the total", () => {
    expect(scheduleScope({ line_count: 7 })).toBe("7 lines");
  });
});

describe("scheduleQuantity — the headline unit count on that same header", () => {
  it("says only the count when the schedule is whole", () => {
    expect(scheduleQuantity({ unit_count: 312, unit_total: 312, truncated: false })).toBe("312");
  });

  it("THE DEFECT: the big number was the SHORT quantity, next to an honest line caption", () => {
    // `scheduleScope` shipped first and disclosed the line cap; this stayed on `unit_count`, the
    // sum over returned lines only. The visible honesty about lines vouched for the wrong number.
    expect(scheduleQuantity({ unit_count: 9800, unit_total: 11240, truncated: true }))
      .toBe("9800 of 11240");
  });

  it("falls back to the plain count against a server that does not send the total", () => {
    expect(scheduleQuantity({ unit_count: 7, truncated: true })).toBe("7");
  });

  it("does not print a no-op range when the totals agree", () => {
    expect(scheduleQuantity({ unit_count: 40, unit_total: 40, truncated: true })).toBe("40");
  });
});

describe("earlierNote — the topic timeline drawer", () => {
  it("says nothing when the whole history fits on screen", () => {
    expect(earlierNote({ event_count: 9, event_total: 9 })).toBe("");
    expect(earlierNote({ event_count: 12, event_total: 12 })).toBe("");
  });

  it("counts the earlier events against the history, not the window", () => {
    expect(earlierNote({ event_count: 40, event_total: 40 })).toBe("…28 earlier event(s)");
  });

  it("THE DEFECT: a capped window used to understate by exactly what the server dropped", () => {
    // 620 events, the server returns its newest 500, the drawer renders the newest 12.
    // Computing from `event_count` gave "…488 earlier" — silently 120 short, and confident.
    expect(earlierNote({ event_count: 500, event_total: 620 })).toBe("…608 earlier event(s)");
  });

  it("never reports fewer than the window it was handed", () => {
    // A total that arrives smaller than the count is nonsense; prefer the count over a negative.
    expect(earlierNote({ event_count: 500, event_total: 3 })).toBe("…488 earlier event(s)");
  });
});

describe("gapShown — the broken-links list on the Spine traceability card", () => {
  it("says nothing when the whole gap list is on screen", () => {
    expect(gapShown(5, 5)).toEqual({ shown: 5, note: "" });
    expect(gapShown(12, 12)).toEqual({ shown: 12, note: "" });
  });

  it("THE DEFECT: it counted the server's PAGE, not the twelve rows rendered", () => {
    // 240 broken links, the server returns its first 100, the card renders twelve. The note read
    // "showing 100 of 240" — a page-as-total conflation inside the change set that existed to
    // remove the class, because the number nearest the honest caption was the uncounted one.
    expect(gapShown(100, 240)).toEqual({ shown: 12, note: "showing 12 of 240" });
  });

  it("discloses the cut even when the server sent everything", () => {
    // 40 gaps, all 40 returned, twelve rendered: the previous branch printed a bare "…" here,
    // which says something is missing without saying how much.
    expect(gapShown(40, 40)).toEqual({ shown: 12, note: "showing 12 of 40" });
  });

  it("never claims to show more than it has", () => {
    // A server total ahead of a short page (a row deleted between the count and the page) must
    // not produce "showing 12 of 8" — `shown` is bounded by what is actually in hand.
    expect(gapShown(3, 8)).toEqual({ shown: 3, note: "showing 3 of 8" });
  });
});
