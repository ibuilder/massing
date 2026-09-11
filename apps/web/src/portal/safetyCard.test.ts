import { describe, expect, it } from "vitest";

import { type SafetyRollup, safetyClassLine, safetyHeadline } from "./safetyCard";

const base: SafetyRollup = {
  incident_count: 0, recordable_count: 0, lost_days: 0, trir: null, dart: null, by_class: {},
};

describe("safetyHeadline", () => {
  it("says so plainly when there is nothing to report", () => {
    expect(safetyHeadline(base)).toBe("Safety: no recordable incidents ✓");
  });

  it("omits TRIR and DART when hours are unknown rather than printing null", () => {
    // The route returns null for both when it could not derive man-hours; a rate of "null per
    // 200k hours" is not a safety statistic, it is a missing denominator.
    const s = { ...base, incident_count: 5, recordable_count: 2, lost_days: 9 };
    expect(safetyHeadline(s)).toBe("Safety: 2 recordable / 5 incidents · 9 lost days");
  });

  it("carries both rates when the hours are known", () => {
    const s = { ...base, incident_count: 5, recordable_count: 2, lost_days: 9, trir: 1.4, dart: 0.7 };
    expect(safetyHeadline(s)).toBe("Safety: 2 recordable / 5 incidents · 9 lost days · TRIR 1.4 · DART 0.7");
  });
});

describe("safetyClassLine", () => {
  it("ranks by count, biggest first", () => {
    expect(safetyClassLine({ "Near miss": 4, Recordable: 7, "First aid": 1 }))
      .toBe("↳ Recordable 7 · Near miss 4 · First aid 1");
  });

  it("breaks ties alphabetically, so the card does not reshuffle between renders", () => {
    // Equal counts would otherwise fall out in object key order, which is insertion order here and
    // therefore whatever the server happened to iterate — the same project, two different cards.
    expect(safetyClassLine({ Zeta: 2, Alpha: 2 })).toBe("↳ Alpha 2 · Zeta 2");
  });

  it("summarises the tail instead of listing every class", () => {
    expect(safetyClassLine({ a: 9, b: 8, c: 7, d: 6, e: 5 })).toBe("↳ a 9 · b 8 · c 7 · +2 more");
  });

  it("returns null — not an empty arrow — when there is nothing to show", () => {
    // The caller writes this straight into textContent, so "↳ " alone would render as a stray glyph.
    expect(safetyClassLine({})).toBeNull();
    expect(safetyClassLine(undefined)).toBeNull();
    expect(safetyClassLine({ "Near miss": 0 })).toBeNull();   // a class present but empty
  });
});
