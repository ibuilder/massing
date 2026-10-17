import { describe, expect, it } from "vitest";

import type { CaptureDiff } from "../../api/schedule";
import {
  addedByClassRows, addedByLevelRows, captureHeadline, captureTone, dateRangeNote, derivationNote,
  progressNote, reworkAnswerable, reworkRows, undatedNote, unmatchedNote,
} from "./captureDiffRead";

/** MEASURED off `aec_api.progress_rollup` — `installed_as_of` for both dates, then `capture_diff` —
 *  over 6 design elements and 6 Field Verification records, one undated and one naming a GUID the
 *  model has never had:
 *
 *      t1 2026-09-15 → [S1, W1, W2]            t2 2026-09-30 → [D1, GHOST, S1, W1, W2, W3]
 *      installed_t1 3 · installed_t2 5 · newly_installed 2 · disappeared 0
 *      unmatched_t2 1 (GHOST) · derived.undated 1 (B1)
 *      pct_complete 0.5 → 0.833 (+0.333) · days 15 · elements_per_day 0.13
 *
 *  `installed_t2` is 5 and not 6 because GHOST is outside the model, and `pct_complete_t2` is 5/6 of
 *  the DESIGN set — two different denominators in one response, which is what `progressNote` exists
 *  to say out loud. */
const DERIVED: CaptureDiff = {
  t1: "2026-09-15", t2: "2026-09-30", days: 15,
  installed_t1: 3, installed_t2: 5, newly_installed: 2, disappeared: 0,
  added_guids: ["D1", "W3"], disappeared_guids: [],
  added_by_class: [{ ifc_class: "IfcDoor", count: 1 }, { ifc_class: "IfcWall", count: 1 }],
  added_by_level: [{ storey: "L2", count: 2 }],
  pct_complete_t1: 0.5, pct_complete_t2: 0.833, pct_delta: 0.333,
  elements_per_day: 0.13, note: "engine note",
  unmatched_t1: 0, unmatched_t2: 1, unmatched_guids: ["GHOST"],
  derived: {
    source: "field_verification", note: "derived note",
    t1: { as_of: "2026-09-15", count: 3 },
    t2: { as_of: "2026-09-30", count: 6 },
    undated: 1, register_earliest: "2026-09-01", register_latest: "2026-09-29",
    cumulative: true,
  },
};

/** The same diff from two sets the CALLER supplied — `derived` is null and the rework half is a real
 *  question again. */
const SUPPLIED: CaptureDiff = {
  ...DERIVED, derived: null,
  unmatched_t1: 0, unmatched_t2: 0, unmatched_guids: [],
  disappeared: 1, disappeared_guids: ["S1"],
};

describe("reworkAnswerable", () => {
  it("is FALSE on a derived capture, where the set is cumulative by construction", () => {
    // Not "disappeared happens to be 0" — a different fact, and only one of them justifies drawing
    // an empty table. An empty rework table reads as "no rework found", which is the opposite of
    // "this source cannot tell you".
    expect(reworkAnswerable(DERIVED)).toBe(false);
    expect(DERIVED.disappeared).toBe(0);
  });

  it("is TRUE when the caller supplied the sets, whatever the result", () => {
    expect(reworkAnswerable(SUPPLIED)).toBe(true);
    expect(reworkAnswerable({ ...SUPPLIED, disappeared: 0, disappeared_guids: [] })).toBe(true);
  });

  it("is TRUE for a derived source that is NOT cumulative, if one ever exists", () => {
    // The flag is read, not assumed from the presence of `derived` — a true point-in-time capture
    // import would set `cumulative: false` and the rework half would be answerable again.
    expect(reworkAnswerable({
      ...DERIVED, derived: { ...DERIVED.derived!, cumulative: false },
    })).toBe(true);
  });
});

describe("captureHeadline / captureTone", () => {
  it("gives the count, the window and the rate", () => {
    expect(captureHeadline(DERIVED))
      .toBe("2 element(s) newly installed over 15 day(s) · 0.13/day");
  });

  it("says why there is no rate rather than printing one over an unknown window", () => {
    expect(captureHeadline({ ...DERIVED, days: null, elements_per_day: null }))
      .toBe("2 element(s) newly installed (no dates given, so no rate)");
  });

  it("warns on an unmatched GUID, because that is a capture against the wrong model", () => {
    expect(captureTone(DERIVED)).toBe("warn");
  });

  it("is green when something moved and nothing is unexplained", () => {
    expect(captureTone({ ...DERIVED, unmatched_t2: 0, unmatched_guids: [] })).toBe("good");
  });

  it("is NEUTRAL on a quiet window, which is a real result rather than a failure", () => {
    expect(captureTone({
      ...DERIVED, newly_installed: 0, added_guids: [], unmatched_t2: 0, unmatched_guids: [],
    })).toBe("");
  });

  it("is bad when something disappeared", () => {
    expect(captureTone(SUPPLIED)).toBe("crit");
  });
});

describe("progressNote", () => {
  it("names both denominators, because the response carries two", () => {
    const n = progressNote(DERIVED);
    expect(n).toContain("50.0% → 83.3% (+33.3%)");
    expect(n).toContain("over the whole design element set");
    expect(n).toContain("only what a capture could account for");
  });

  it("signs a negative delta", () => {
    expect(progressNote({ ...DERIVED, pct_delta: -0.1 })).toContain("(-10.0%)");
  });
});

describe("derivationNote", () => {
  it("states both sets' provenance and that rework is unanswerable", () => {
    const n = derivationNote(DERIVED)!;
    expect(n).toContain("3 element(s) observed on or before 2026-09-15");
    expect(n).toContain("6 on or before 2026-09-30");
    expect(n).toContain("CANNOT raise a rework flag");
  });

  it("is null when the caller supplied the sets — their provenance is the caller's to state", () => {
    expect(derivationNote(SUPPLIED)).toBeNull();
  });
});

describe("undatedNote", () => {
  it("names the records no capture can ever use", () => {
    const n = undatedNote(DERIVED)!;
    expect(n).toContain("1 Field Verification record(s) carry no observed date");
    expect(n).toContain("outside EVERY capture at every date");
  });

  it("is null when every row carried a date, and on a supplied capture", () => {
    expect(undatedNote({ ...DERIVED, derived: { ...DERIVED.derived!, undated: 0 } })).toBeNull();
    expect(undatedNote(SUPPLIED)).toBeNull();
  });
});

describe("dateRangeNote", () => {
  it("explains an empty side that is empty for want of RECORDS, not of progress", () => {
    const n = dateRangeNote({
      ...DERIVED,
      derived: { ...DERIVED.derived!, t1: { as_of: "2026-08-01", count: 0 } },
    })!;
    expect(n).toContain("2026-08-01 is before the register's first observation (2026-09-01)");
    expect(n).toContain("for want of records rather than for want of progress");
  });

  it("names both dates when both are before the register begins", () => {
    expect(dateRangeNote({
      ...DERIVED,
      derived: { ...DERIVED.derived!, t1: { as_of: "2026-07-01", count: 0 },
                t2: { as_of: "2026-08-01", count: 0 } },
    })!).toContain("2026-07-01 and 2026-08-01 are before");
  });

  it("says so plainly when the register has no dated record at all", () => {
    expect(dateRangeNote({
      ...DERIVED,
      derived: { ...DERIVED.derived!, register_earliest: null, register_latest: null },
    })).toBe("The Field Verification register holds no dated records, so both sets are empty.");
  });

  it("is null inside the range, and on a supplied capture", () => {
    expect(dateRangeNote(DERIVED)).toBeNull();
    expect(dateRangeNote(SUPPLIED)).toBeNull();
  });
});

describe("unmatchedNote", () => {
  it("names the wrong-model-version case with a sample", () => {
    const n = unmatchedNote(DERIVED)!;
    expect(n).toContain("1 captured GlobalId(s) are not in this model (GHOST)");
    expect(n).toContain("outside the diff on both sides");
    expect(n).not.toContain("…");
  });

  it("marks the sample as a sample when the server capped it", () => {
    // `unmatched_guids` is capped at 200 server-side while the two counts are exact, so a response
    // can carry more unmatched than it lists — the TRUNC-COUNTED shape, in a third currency.
    expect(unmatchedNote({
      ...DERIVED, unmatched_t1: 150, unmatched_t2: 120,
      unmatched_guids: Array.from({ length: 200 }, (_, i) => `G${i}`),
    })!).toContain("270 captured GlobalId(s)");
    expect(unmatchedNote({
      ...DERIVED, unmatched_t1: 150, unmatched_t2: 120,
      unmatched_guids: Array.from({ length: 200 }, (_, i) => `G${i}`),
    })!).toContain("…");
  });

  it("is null when every captured GUID is in the model", () => {
    expect(unmatchedNote(SUPPLIED)).toBeNull();
  });
});

describe("the row builders", () => {
  it("strips the Ifc prefix on the class rows and keeps the engine's order", () => {
    expect(addedByClassRows(DERIVED)).toEqual([{ k: "Door", v: "1" }, { k: "Wall", v: "1" }]);
    expect(addedByLevelRows(DERIVED)).toEqual([{ k: "L2", v: "2" }]);
  });

  it("caps each table", () => {
    const many: CaptureDiff = {
      ...DERIVED,
      added_by_class: Array.from({ length: 30 }, (_, i) => ({ ifc_class: `IfcX${i}`, count: 1 })),
    };
    expect(addedByClassRows(many, 5)).toHaveLength(5);
  });

  it("builds rework rows only from what the response actually carries", () => {
    expect(reworkRows(SUPPLIED)).toEqual([{ k: "S1", v: "present at t1, absent at t2" }]);
    expect(reworkRows(DERIVED)).toEqual([]);
  });
});
