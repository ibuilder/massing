import { describe, expect, it } from "vitest";

import {
  bandRows, ceilingDiffers, complianceRows, infoScoreLine, limitingRows, readability,
  TONE_CSS, type LodAssessment,
} from "./lodCoverage";

/**
 * LOD-UNREAD — the card titled "LOD coverage" rendered `distribution` and nothing else.
 *
 * Every assertion here is about a distinction `lod.assess` makes and the old card flattened. The
 * shape of the defect is the one the eighteen gate entries in CLAUDE.md keep finding: the engine is
 * careful, and the consumer renders the answer without the caveat.
 */

const FULL: LodAssessment = {
  model_scored: true,
  elements: 100,
  distribution: { "LOD 100": 10, "LOD 200": 60, "LOD 300": 20, "LOD 350": 5, "LOD 400": 5, "LOD 500": 0 },
  ceiling_distribution: { "LOD 100": 0, "LOD 200": 10, "LOD 300": 60, "LOD 350": 20, "LOD 400": 5, "LOD 500": 5 },
  limited_by: { detail: 40, dimensionality: 0, location: 12, appearance: 3, parametric_behavior: 0 },
  elements_with_an_undecidable_aspect: 55,
  elements_without_readable_geometry: 7,
  avg_information_score: 4.2,
  information_score_max: 8,
  compliance: {
    "Stage 3": { meeting_target: 30, short_of_target: 10, no_target: 60, pct_meeting: 75.0,
                 short_by_rule: { Walls: 6, Doors: 4 } },
    "Stage 4": { meeting_target: 0, short_of_target: 0, no_target: 100, pct_meeting: null,
                 short_by_rule: {} },
  },
};

describe("LOD-UNREAD", () => {
  it("puts the ceiling beside the achieved band rather than subtracting them", () => {
    const rows = bandRows(FULL);
    expect(rows).toHaveLength(6);
    expect(rows[1]).toEqual({ band: "LOD 200", achieved: 60, ceiling: 10 });
    // A PER-BAND DIFFERENCE WOULD BE ARITHMETIC ON TWO DIFFERENT POPULATIONS. An element sits in one
    // achieved band and one ceiling band, and the aggregates do not say which element moved where,
    // so there is deliberately no `headroom` field to render. *A derived number that looks precise
    // is worse than two honest columns.*
    expect(Object.keys(rows[0]!)).toEqual(["band", "achieved", "ceiling"]);
  });

  it("reports a ceiling of null, not zero, when the response carries none", () => {
    // A zero would read as "nothing could be higher" — the opposite of "not knowable".
    const rows = bandRows({ ...FULL, ceiling_distribution: undefined });
    expect(rows.every((r) => r.ceiling === null)).toBe(true);
    expect(ceilingDiffers({ ...FULL, ceiling_distribution: undefined })).toBe(false);
  });

  it("says the band is a FLOOR when any aspect could not be read", () => {
    const r = readability(FULL);
    expect(r.tone).toBe("warn");
    expect(r.earned).toBe(false);
    expect(r.text).toContain("55 have at least one aspect the index could not decide");
    expect(r.text).toContain("7 have no readable geometry");
    // the engine's distinction, carried through verbatim
    expect(r.text).toContain("unread model, not missing model");
  });

  it("earns the tick only when BOTH counts are zero and something was assessed", () => {
    const clean = readability({ ...FULL, elements_with_an_undecidable_aspect: 0,
                                elements_without_readable_geometry: 0 });
    expect(clean.earned).toBe(true);
    expect(clean.tone).toBe("ok");
    for (const partial of [{ elements_with_an_undecidable_aspect: 0 },
                           { elements_without_readable_geometry: 0 }]) {
      expect(readability({ ...FULL, ...partial }).earned).toBe(false);
    }
  });

  it("refuses the tick over an EMPTY assessment, which is where it would be vacuous", () => {
    // `!undecidable && !unreadable` is true of a model with no elements, so the empty case has to
    // come first. This is the shape `services/api/test_quant_vacuous.py` exists for.
    const empty = readability({ ...FULL, elements: 0, elements_with_an_undecidable_aspect: 0,
                                elements_without_readable_geometry: 0 });
    expect(empty.earned).toBe(false);
    expect(empty.tone).toBe("unknown");
    expect(empty.text).toContain("describe nothing");
  });

  it("says UNKNOWN rather than treating an absent count as a zero", () => {
    // An older response, or one that drops the keys, must not come back with a clean tick: the
    // counts are the evidence, and `?? 0` is for arithmetic, never for a verdict.
    const r = readability({ ...FULL, elements_with_an_undecidable_aspect: undefined,
                            elements_without_readable_geometry: undefined });
    expect(r.earned).toBe(false);
    expect(r.tone).toBe("unknown");
    expect(r.text).toContain("not knowable");
  });

  it("names which aspect proved the cap, highest first, dropping the zeros", () => {
    expect(limitingRows(FULL)).toEqual([
      { aspect: "Level of detail", elements: 40 },
      { aspect: "Location", elements: 12 },
      { aspect: "Appearance", elements: 3 },
    ]);
    expect(limitingRows({ ...FULL, limited_by: undefined })).toEqual([]);
  });

  it("keeps `no_target` beside the percentage, never inside it", () => {
    const rows = complianceRows(FULL);
    const s3 = rows.find((r) => r.phase === "Stage 3")!;
    expect(s3).toMatchObject({ met: 30, short: 10, noTarget: 60, pct: "75%", tone: "warn" });
    // 75% over 40 of 100 elements. The engine already kept the 60 out of the denominator; this
    // keeps it on the screen, because a percentage whose denominator is unstated is the same
    // defect one layer along.
    expect(s3.noTarget).toBeGreaterThan(s3.met + s3.short);
  });

  it("renders a stage that scored nothing as — and UNKNOWN, not as 0% or a pass", () => {
    const s4 = complianceRows(FULL).find((r) => r.phase === "Stage 4")!;
    expect(s4.pct).toBe("—");
    expect(s4.tone).toBe("unknown");       // "0 short of target" is not a pass over zero scored
  });

  it("warns on full coverage of the targeted elements only when something is short", () => {
    const rows = complianceRows({ ...FULL, compliance: {
      Done: { meeting_target: 100, short_of_target: 0, no_target: 0, pct_meeting: 100.0,
              short_by_rule: {} } } });
    expect(rows[0]!.tone).toBe("ok");
  });

  it("states the information score WITH its maximum, or not at all", () => {
    expect(infoScoreLine(FULL)).toContain("4.2 of 8 facets");
    // The engine's own note records this number having been reported AS the LOD band until
    // v0.3.901, so the line says plainly that it is a different question.
    expect(infoScoreLine(FULL)).toContain("different");
    expect(infoScoreLine({ ...FULL, avg_information_score: undefined })).toBeNull();
    expect(infoScoreLine({ ...FULL, information_score_max: 0 })).toBeNull();
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn", "unknown"] as const) expect(TONE_CSS[t]).toMatch(/^var\(--/);
  });
});
