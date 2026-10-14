import { describe, expect, it } from "vitest";

import {
  TONE_CSS, bandRows, ceilingDiffers, complianceRows, inertTargetNote, inertTargetRows,
  infoScoreLine, limitingRows, matrixBasis, readability, type LodAssessment,
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

/**
 * LOD-TARGET-INERT — which matrix the compliance table is against, and which authored rules
 * contributed nothing to it. Both fixtures are measured responses from a live server against the
 * same 3-element synthetic index.
 */
const DEFAULTS: LodAssessment = {
  model_scored: true,
  elements: 3,
  distribution: { "LOD 100": 1, "LOD 200": 1, "LOD 300": 0, "LOD 350": 1, "LOD 400": 0, "LOD 500": 0 },
  using_default: true,
  targets: [],
  default: [
    { phase: "Concept / SD", target_lod: "LOD 200" },
    { phase: "Design Development", target_lod: "LOD 300" },
    { phase: "Construction Docs", target_lod: "LOD 350" },
    { phase: "Construction", target_lod: "LOD 400" },
    { phase: "As-built", target_lod: "LOD 500" },
  ],
  targets_matching_nothing: [],
  compliance: {
    "As-built": { meeting_target: 0, short_of_target: 3, no_target: 0, pct_meeting: 0.0,
      short_by_rule: { "stage default (LOD 500)": 3 } },
    "Concept / SD": { meeting_target: 2, short_of_target: 1, no_target: 0, pct_meeting: 66.7,
      short_by_rule: { "stage default (LOD 200)": 1 } },
  },
};

const INERT: LodAssessment = {
  model_scored: true,
  elements: 3,
  distribution: DEFAULTS.distribution,
  using_default: false,
  targets: [{ element_category: "Exterior Walls" }, { element_category: "Plumbing" }],
  default: DEFAULTS.default,
  targets_matching_nothing: [
    { element_category: "Exterior Walls", phase: "Construction Docs", target_lod: "LOD 350",
      why: "names no ifc_class, uniformat or discipline — matching uses those three, and "
        + "`element_category` is a free-text label" },
    { element_category: "Plumbing", phase: "Construction Docs", target_lod: "LOD 300",
      why: "its ifc_class / uniformat / discipline matched no element in this model" },
  ],
  compliance: {
    "Construction Docs": { meeting_target: 0, short_of_target: 0, no_target: 3, pct_meeting: null,
      short_by_rule: {} },
  },
};

describe("LOD-TARGET-INERT · matrixBasis", () => {
  it("names the built-in defaults, with their bands, when nothing is authored", () => {
    const b = matrixBasis(DEFAULTS)!;
    expect(b).toContain("No LOD targets are authored for this project");
    expect(b).toContain("built-in RIBA/AIA defaults, not your standard");
    expect(b).toContain("Concept / SD LOD 200");
    expect(b).toContain("As-built LOD 500");
  });

  it("is silent when the firm's own targets are in force", () => {
    expect(matrixBasis(INERT)).toBeNull();
  });

  it("is silent when there is no compliance table to be about", () => {
    expect(matrixBasis({ ...DEFAULTS, compliance: {} })).toBeNull();
    expect(matrixBasis({ ...DEFAULTS, compliance: undefined })).toBeNull();
  });
});

describe("LOD-TARGET-INERT · inertTargetNote", () => {
  it("counts the inert rules against the authored total", () => {
    expect(inertTargetNote(INERT)).toBe("2 of 2 authored target(s) matched no element in this "
      + "model, so they contribute nothing to the table above.");
  });

  it("is silent when every authored rule resolved", () => {
    expect(inertTargetNote(DEFAULTS)).toBeNull();
    expect(inertTargetNote({ ...INERT, targets_matching_nothing: [] })).toBeNull();
  });

  it("still reports when the authored list is absent from the response", () => {
    // An older server, or a narrower projection. The count is what matters and it stands alone.
    expect(inertTargetNote({ ...INERT, targets: undefined }))
      .toBe("2 authored target(s) matched no element in this model, so they contribute nothing to "
        + "the table above.");
  });
});

describe("LOD-TARGET-INERT · inertTargetRows", () => {
  it("keeps the engine's two DIFFERENT reasons apart — they need different actions", () => {
    const rows = inertTargetRows(INERT);
    expect(rows.map((r) => r.category)).toEqual(["Exterior Walls", "Plumbing"]);
    // A data-entry fix...
    expect(rows[0]!.why).toContain("free-text label");
    // ...versus a model that has not got there yet.
    expect(rows[1]!.why).toContain("matched no element in this model");
    expect(rows[0]!.target).toBe("LOD 350");
    expect(rows[0]!.phase).toBe("Construction Docs");
  });

  it("names a rule with no category rather than rendering a blank cell", () => {
    expect(inertTargetRows({ ...INERT, targets_matching_nothing: [
      { element_category: "", phase: "", target_lod: "", why: "x" }] })[0])
      .toEqual({ category: "(unnamed)", phase: "—", target: "—", why: "x" });
  });

  it("is empty, not undefined, when the response carries no such list", () => {
    expect(inertTargetRows({ ...INERT, targets_matching_nothing: undefined })).toEqual([]);
  });
});

describe("LOD-TARGET-INERT · the reading the table gave before", () => {
  it("reported No target for every element with no way to tell why", () => {
    // Both fixtures have a compliance table. One is measured against built-in defaults, the other
    // against two rules that address nothing — and the rows alone cannot tell them apart.
    const inertRow = complianceRows(INERT)[0]!;
    expect(inertRow.noTarget).toBe(3);
    expect(inertRow.pct).toBe("—");
    expect(matrixBasis(INERT)).toBeNull();
    expect(inertTargetNote(INERT)).not.toBeNull();
  });
});
