import { describe, expect, it } from "vitest";

import type { ScheduleStatusReport, ScheduleStatusRow } from "../../api/types";
import { futureActualRows, rowsFor, slipCells, statusReading } from "./scheduleStatusReading";

const ROW = (over: Partial<ScheduleStatusRow> = {}): ScheduleStatusRow => ({
  ref: "A1", state: "not_started", detail: "no actual start recorded",
  planned_start: "2026-05-01", planned_finish: "2026-05-10",
  actual_start: null, actual_finish: null, expected_finish: null,
  late_to_start: false, days_late_to_start: null,
  overdue: false, days_overdue: null,
  actual_slip_days: null, forecast_slip_days: null, future_actual_ignored: false, ...over,
});

const R = (over: Partial<ScheduleStatusReport> = {}): ScheduleStatusReport => ({
  data_date: "2026-06-01",
  activities: [ROW()],
  counts: { complete: 0, in_progress: 0, not_started: 1, unknown: 0 },
  late_to_start: [], overdue: [], forecast_slipping: [],
  checked: true,
  note: "`overdue` is measured against the data date — a fact.",
  ...over,
});

describe("① no data date is NOT a clean schedule", () => {
  it("says nothing was assessed, never that nothing is late", () => {
    const r = statusReading(R({
      data_date: null, checked: false,
      counts: { complete: 0, in_progress: 0, not_started: 0, unknown: 7 },
      activities: [ROW({ state: "unknown" })],
    }));
    expect(r.tone).toBe("unknown");
    expect(r.text).toContain("NOT ASSESSED");
    expect(r.text).toContain("7");
    // the sentence that must never appear on an unassessed report
    expect(r.text).not.toMatch(/none overdue|no late|on track|✓/i);
  });
});

describe("② late to start is not overdue", () => {
  it("counts and names them separately, and never sums them", () => {
    const r = statusReading(R({
      late_to_start: ["A1", "A2"], overdue: ["A3"],
      activities: [ROW(), ROW({ ref: "A2" }), ROW({ ref: "A3" })],
    }));
    expect(r.text).toContain("1 overdue");
    expect(r.text).toContain("2 late to start");
    expect(r.text).not.toContain("3 late");     // the sum, which is not a count of anything
    expect(r.tone).toBe("bad");                 // overdue dominates
  });

  it("is WARN when work is late to start but nothing is overdue yet", () => {
    const r = statusReading(R({ late_to_start: ["A1"] }));
    expect(r.tone).toBe("warn");
    expect(r.text).toContain("none overdue");
  });

  /** An activity can be in BOTH lists, which is why a sum is not even arithmetic. */
  it("does not double-count an activity that is late to start AND overdue", () => {
    const r = statusReading(R({ late_to_start: ["A1"], overdue: ["A1"] }));
    expect(r.text).toContain("1 overdue");
    expect(r.text).toContain("1 late to start");
  });
});

describe("③ finished late is complete, not overdue", () => {
  it("leaves a complete-but-slipped activity out of the overdue count", () => {
    // the engine decides this; the reading must not re-derive it from the slip number
    const r = statusReading(R({
      overdue: [],
      activities: [ROW({ state: "complete", actual_finish: "2026-05-20", actual_slip_days: 10 })],
    }));
    expect(r.text).toContain("none overdue");
    expect(r.tone).toBe("ok");
  });
});

describe("④ forecast slip is a CLAIM, kept apart from actual slip", () => {
  it("labels it as the crew's claim in the headline", () => {
    const r = statusReading(R({ forecast_slipping: ["A1"] }));
    expect(r.text).toContain("1 forecast to slip");
    expect(r.text).toContain("claim");
  });

  it("renders the two slip numbers as two cells and offers NO total", () => {
    const cells = slipCells(ROW({ actual_slip_days: 4, forecast_slip_days: 6 }));
    expect(cells.actual).toBe("+4d");
    expect(cells.forecast).toBe("+6d claimed");
    expect(Object.keys(cells).sort()).toEqual(["actual", "forecast"]);   // no `total`
    expect(JSON.stringify(cells)).not.toContain("10");                   // never summed
  });

  it("shows an em-dash rather than a zero for a slip that does not exist", () => {
    expect(slipCells(ROW()).actual).toBe("—");
    expect(slipCells(ROW()).forecast).toBe("—");
    expect(slipCells(ROW({ actual_slip_days: 0 })).actual).toBe("+0d");  // zero is a measurement
  });
});

describe("the report's own lists resolve to rows", () => {
  it("maps refs to activities and drops a ref with no row rather than throwing", () => {
    const r = R({ activities: [ROW(), ROW({ ref: "A2" })], overdue: ["A2", "GONE"] });
    expect(rowsFor(r, r.overdue).map((a) => a.ref)).toEqual(["A2"]);
  });

  /**
   * ROWKEY-SUPERSET closed this: `future_actual_ignored` was absent from `_ROW_KEYS`, so a blank
   * row raised `KeyError` server-side. This list is the first consumer that reads the key, which
   * is why the row-shape fix had to land before the wiring.
   */
  it("surfaces the activities whose recorded actual the engine disregarded", () => {
    const r = R({ activities: [ROW(), ROW({ ref: "A2", future_actual_ignored: true })] });
    expect(futureActualRows(r).map((a) => a.ref)).toEqual(["A2"]);
    expect(futureActualRows(R())).toEqual([]);
  });
});
