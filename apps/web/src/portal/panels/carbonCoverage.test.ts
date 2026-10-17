import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ProjectCarbon } from "../../api/designPerformance";
import {
  carbonCoverage, carbonCoverageLine, carbonSuspect, excludedMaterialsLine, noFactorLine,
} from "./carbonCoverage";

/** `carbon.compute`'s real output, dumped from the engine; `lines` dropped since this module reads
 *  only the summary. */
const mk = (o: Partial<ProjectCarbon>): ProjectCarbon => ({
  lines: [], total_kgco2e: 0, total_tco2e: 0, by_material: {}, by_cost_code: {},
  line_count: 0, assessed: 0, unmatched: 0, no_factor: 0, unit_mismatch: 0,
  unconverted_materials: {}, coverage_note: "", message: null, ...o,
});

const EXCLUDED_NOTE = "2 of 3 quantity line(s) assessed. EXCLUDED from the total and from the "
  + "material rollup: concrete — recognised, but the quantity's unit is not in the factor's unit "
  + "family (a mass against a volume factor needs a density, which is not guessed here). Record "
  + "these in the factor's unit to bring them in; until then the total is missing them.";

/** A concrete frame whose takeoff is in kg. **2,400 t of concrete — worth roughly another
 *  300 tCO₂e — is absent from `by_material`, and the old card said only "1 line(s) unmatched".** */
const FRAME: ProjectCarbon = mk({
  total_kgco2e: 329167.6, total_tco2e: 329.17,
  by_material: { "structural steel": 279000, glazing: 50167.6 },
  by_cost_code: { "05-1200": 279000, "08-4400": 50167.6 },
  line_count: 3, assessed: 2, unmatched: 1, no_factor: 0, unit_mismatch: 1,
  unconverted_materials: { concrete: 2400000 }, coverage_note: EXCLUDED_NOTE,
});

/** Everything recognised and counted. */
const CLEAN: ProjectCarbon = mk({
  total_kgco2e: 30000, total_tco2e: 30, by_material: { concrete: 30000 },
  by_cost_code: { "03-3000": 30000 }, line_count: 1, assessed: 1,
  coverage_note: "1 of 1 quantity line(s) assessed. Every recognised material was counted.",
});

/** One of each refusal — the case the repo's aggregate fixture never had. */
const BOTH: ProjectCarbon = mk({
  line_count: 2, assessed: 0, unmatched: 2, no_factor: 1, unit_mismatch: 1,
  unconverted_materials: { concrete: 100 },
  coverage_note: "0 of 2 quantity line(s) assessed (1 with no EPD factor for the material). "
    + "EXCLUDED from the total and from the material rollup: concrete — recognised, but the "
    + "quantity's unit is not in the factor's unit family (a mass against a volume factor needs a "
    + "density, which is not guessed here). Record these in the factor's unit to bring them in; "
    + "until then the total is missing them.",
});

const EMPTY: ProjectCarbon = mk({ coverage_note: "No material quantities to assess.",
  message: "No material quantities to assess — add production quantities with a material and unit." });

describe("carbonCoverage", () => {
  it("separates nothing assessed, some assessed and all assessed", () => {
    expect(carbonCoverage(EMPTY)).toBe("none");
    expect(carbonCoverage(BOTH)).toBe("none");
    expect(carbonCoverage(FRAME)).toBe("partial");
    expect(carbonCoverage(CLEAN)).toBe("full");
  });

  it("does not call a zero-line takeoff fully covered", () => {
    expect(carbonCoverage(mk({ line_count: 0, assessed: 0 }))).toBe("none");
  });
});

describe("excludedMaterialsLine", () => {
  /** **This is the defect, in one assertion.** */
  it("names the recognised material missing from the total", () => {
    const line = excludedMaterialsLine(FRAME) ?? "";
    expect(line).toContain("concrete");
    expect(line).toContain("recognised but NOT in this total");
    // The emitter is absent from the rollup the card prints beside the figure.
    expect(Object.keys(FRAME.by_material)).not.toContain("concrete");
  });

  it("is silent when every recognised material was counted", () => {
    expect(excludedMaterialsLine(CLEAN)).toBeNull();
    expect(excludedMaterialsLine(EMPTY)).toBeNull();
  });

  it("agrees in number with however many are excluded", () => {
    expect(excludedMaterialsLine(FRAME)).toContain(" is recognised");
    const two = mk({ ...FRAME, unconverted_materials: { concrete: 1, masonry: 2 } });
    expect(excludedMaterialsLine(two)).toContain(" are recognised");
    expect(excludedMaterialsLine(two)).toContain("concrete, masonry");
  });

  it("names the material rather than counting the lines", () => {
    // "1 line(s) unmatched" cannot tell a stair nosing from a whole concrete frame.
    expect(excludedMaterialsLine(FRAME)).not.toContain("1 line");
  });
});

describe("noFactorLine", () => {
  it("reports the unrecognised-material count with its own remedy", () => {
    const line = noFactorLine(BOTH) ?? "";
    expect(line).toContain("1 line(s)");
    expect(line).toContain("no EPD factor");
    expect(line).toContain("add a factor");
  });

  it("is silent when every material was recognised", () => {
    expect(noFactorLine(FRAME)).toBeNull();
    expect(noFactorLine(CLEAN)).toBeNull();
  });

  it("is a different sentence from the excluded-material one, on the same response", () => {
    // The two refusals have different remedies, which is the whole reason for splitting the count.
    expect(noFactorLine(BOTH)).not.toBe(excludedMaterialsLine(BOTH));
    expect(noFactorLine(BOTH)).not.toBeNull();
    expect(excludedMaterialsLine(BOTH)).not.toBeNull();
    expect(BOTH.no_factor + BOTH.unit_mismatch).toBe(BOTH.unmatched);
  });
});

describe("carbonCoverageLine", () => {
  it("reads the engine's sentence rather than rebuilding it", () => {
    expect(carbonCoverageLine(FRAME)).toBe(FRAME.coverage_note);
    expect(carbonCoverageLine(CLEAN)).toContain("Every recognised material was counted");
  });

  it("still gives a denominator if the server predates the note", () => {
    const old = mk({ line_count: 3, assessed: 2, coverage_note: "" });
    expect(carbonCoverageLine(old)).toContain("2 of 3");
    expect(carbonCoverageLine(mk({ coverage_note: "" }))).toContain("No material quantities");
  });
});

describe("carbonSuspect", () => {
  it("flags only a total missing a material the engine recognised", () => {
    expect(carbonSuspect(FRAME)).toBe(true);
    expect(carbonSuspect(BOTH)).toBe(true);
    // An unrecognised line might be a non-material row; a recognised one is a real emitter, so
    // only the second colours the coverage line.
    expect(carbonSuspect(mk({ line_count: 2, assessed: 1, unmatched: 1, no_factor: 1 }))).toBe(false);
    expect(carbonSuspect(CLEAN)).toBe(false);
  });
});

/** The consumer, at source level — same bargain and limit as the sibling read-modules. */
describe("the analytics panel reads it", () => {
  const panel = readFileSync(resolve(__dirname, "analytics.ts"), "utf8");

  it("renders the coverage, the excluded materials and the no-factor count", () => {
    expect(panel).toContain('from "./carbonCoverage"');
    expect(panel).toContain("carbonCoverageLine(r)");
    expect(panel).toContain("excludedMaterialsLine(r)");
    expect(panel).toContain("noFactorLine(r)");
    expect(panel).toContain("carbonSuspect(r)");
  });

  it("no longer prints the bare unmatched tally", () => {
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    expect(code.join("\n")).not.toContain("${r.unmatched} line(s) unmatched");
  });
});
