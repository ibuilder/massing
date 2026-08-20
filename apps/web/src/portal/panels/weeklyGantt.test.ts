import { describe, expect, it } from "vitest";

import { SERIES_PALETTE } from "../../ui/charts";
import {
  barInWeek, flattenLookahead, mondayUtc, parseDay, renderWeeklyGantt, tradeColor, weekMetrics,
} from "./weeklyGantt";

describe("UX-GANTT — week geometry", () => {
  const mon = mondayUtc(new Date("2026-08-19T12:00:00Z")); // Wed → Mon 17

  it("mondayUtc is ISO Monday", () => {
    expect(mon.toISOString().slice(0, 10)).toBe("2026-08-17");
    expect(mondayUtc(new Date("2026-08-17T00:00:00Z")).toISOString().slice(0, 10)).toBe("2026-08-17");
    expect(mondayUtc(new Date("2026-08-23T00:00:00Z")).toISOString().slice(0, 10)).toBe("2026-08-17");
  });

  it("a Wed–Thu activity sits in the middle of the week, not full width", () => {
    const b = barInWeek(
      { name: "Pour", start: "2026-08-19", finish: "2026-08-20", percent: 40 },
      mon,
    );
    expect(b).toEqual({ leftPct: expect.closeTo(2 / 7 * 100), widthPct: expect.closeTo(2 / 7 * 100) });
  });

  it("clips an activity that started last week", () => {
    const b = barInWeek(
      { name: "Rebar", start: "2026-08-10", finish: "2026-08-18", percent: 80 },
      mon,
    );
    expect(b?.leftPct).toBe(0);
    expect(b?.widthPct).toBeCloseTo(2 / 7 * 100); // Mon 17 + Tue 18
  });

  it("a one-day bar is one seventh, not zero", () => {
    const b = barInWeek(
      { name: "Inspect", start: "2026-08-17", finish: "2026-08-17", percent: 0 },
      mon,
    );
    expect(b).toEqual({ leftPct: 0, widthPct: expect.closeTo(100 / 7) });
  });

  it("outside the week is absent, not a zero-width ghost", () => {
    expect(barInWeek(
      { name: "Later", start: "2026-08-24", finish: "2026-08-25", percent: 0 },
      mon,
    )).toBeNull();
  });

  it("parseDay refuses junk rather than inventing a date", () => {
    expect(parseDay(undefined)).toBeNull();
    expect(parseDay("nope")).toBeNull();
    expect(parseDay("2026-08-19")?.toISOString().slice(0, 10)).toBe("2026-08-19");
  });
});

describe("UX-GANTT — colour and metrics", () => {
  const mon = mondayUtc(new Date("2026-08-19T00:00:00Z"));

  it("the same trade always gets the same series slot, never a status hue", () => {
    const a = tradeColor("concrete");
    const b = tradeColor("concrete");
    expect(a).toBe(b);
    expect(SERIES_PALETTE).toContain(a);
    expect(a).not.toMatch(/#33d17a|#e6a700|#e2554a/i);
  });

  it("empty week is a zero count, not a fake average", () => {
    expect(weekMetrics([], mon)).toEqual({ count: 0, avgPct: 0, trades: 0 });
  });

  it("counts only activities that intersect the week", () => {
    const acts = [
      { name: "A", trade: "concrete", start: "2026-08-17", finish: "2026-08-17", percent: 50 },
      { name: "B", trade: "mep", start: "2026-08-18", finish: "2026-08-19", percent: 100 },
      { name: "C", trade: "concrete", start: "2026-09-01", finish: "2026-09-02", percent: 0 },
    ];
    expect(weekMetrics(acts, mon)).toEqual({ count: 2, avgPct: 75, trades: 2 });
  });
});

describe("UX-GANTT — render", () => {
  it("an empty week is a sentence", () => {
    const el = renderWeeklyGantt([], mondayUtc(new Date("2026-08-17T00:00:00Z")));
    expect(el.dataset.weeklyGantt).toBe("1");
    expect(el.textContent).toContain("no activities in this interval");
    expect(el.querySelector("[data-metrics]")?.textContent).not.toMatch(/\b0%/);
  });

  it("paints named bars with inline percent", () => {
    const el = renderWeeklyGantt(
      [{ name: "Pour L3", trade: "concrete", start: "2026-08-17", finish: "2026-08-19", percent: 40, crew_size: 8 }],
      mondayUtc(new Date("2026-08-17T00:00:00Z")),
    );
    expect(el.textContent).toContain("Pour L3");
    expect(el.textContent).toContain("40%");
    expect(el.textContent).toContain("crew 8");
    expect(el.textContent).toContain("1 activity");
  });

  it("flattens lookahead weeks without inventing rows", () => {
    expect(flattenLookahead(undefined)).toEqual([]);
    expect(flattenLookahead([{ activities: [{ name: "A", percent: 0 }] }])).toHaveLength(1);
  });
});
