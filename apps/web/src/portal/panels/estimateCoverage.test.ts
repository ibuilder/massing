import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ResourceEstimate } from "../../api/estimate";
import {
  estimateCoverage, estimateCoverageLine, estimateHeadline, estimateSuspect, noQuantityLine,
  unmappedLine,
} from "./estimateCoverage";

/** Every fixture below is `assemblies.estimate_resource_based`'s real output, dumped from the
 *  engine rather than written out here — `lines` and `by_trade` dropped, since this module reads
 *  only the coverage keys. */
const mk = (o: Partial<ResourceEstimate>): ResourceEstimate => ({
  total: 0, element_count: 0, priced_elements: 0, unpriced_elements: 0, labor_hours: 0,
  by_kind: { labor: 0, material: 0, equipment: 0 }, by_trade: [], lines: [], unmapped: [],
  no_quantity: [], coverage_note: "", source: "resource", ...o,
});

/** 20 `IfcWall` carrying area beside 80 `IfcSlab` carrying none. The slabs MAP — `cip_slab` — and
 *  the takeoff has no volume for them, so before the fix they were a line reading
 *  `IfcSlab | 80 | 0.00 m3 | $0.00` and `unmapped` was empty. */
const ZERO_QTY = mk({
  total: 14916, element_count: 100, priced_elements: 20, unpriced_elements: 80, labor_hours: 150,
  by_kind: { labor: 9840, material: 5076, equipment: 0 },
  no_quantity: [{ ifc_class: "IfcSlab", count: 80, assembly: "cip_slab", needs: "m3" }],
  coverage_note: "20 of 100 element(s) priced. Outside it: 80 in 1 mapped class(es) the takeoff "
    + "carries no m3 for, so they could not be priced at all -- NOT priced at zero (IfcSlab).",
});

/** **The same 20 walls, alone.** Identical on every figure the old card rendered. */
const WALLS_ONLY = mk({
  total: 14916, element_count: 20, priced_elements: 20, unpriced_elements: 0, labor_hours: 150,
  by_kind: { labor: 9840, material: 5076, equipment: 0 },
  coverage_note: "20 of 20 element(s) priced. Every element in the takeoff is in this total.",
});

/** Both causes at once — 30 unmapped pipes on top of the unquantified slabs. */
const BOTH = mk({
  total: 14916, element_count: 130, priced_elements: 20, unpriced_elements: 110, labor_hours: 150,
  by_kind: { labor: 9840, material: 5076, equipment: 0 },
  unmapped: [{ ifc_class: "IfcPipeSegment", count: 30 }],
  no_quantity: [{ ifc_class: "IfcSlab", count: 80, assembly: "cip_slab", needs: "m3" }],
  coverage_note: "20 of 130 element(s) priced. Outside it: 30 in 1 class(es) with no assembly "
    + "mapped (IfcPipeSegment); 80 in 1 mapped class(es) the takeoff carries no m3 for, so they "
    + "could not be priced at all -- NOT priced at zero (IfcSlab).",
});

/** Nothing mapped at all: the MEP-only case, which is what most coordinated models look like to
 *  `CLASS_TO_ASSEMBLY`'s 11 architectural and structural classes. */
const NONE_PRICED = mk({
  element_count: 30, unpriced_elements: 30,
  unmapped: [{ ifc_class: "IfcPipeSegment", count: 30 }],
  coverage_note: "0 of 30 element(s) priced. Outside it: 30 in 1 class(es) with no assembly "
    + "mapped (IfcPipeSegment).",
});

const FULL = mk({
  total: 33098, element_count: 30, priced_elements: 30, labor_hours: 250,
  by_kind: { labor: 15872, material: 16506, equipment: 720 },
  coverage_note: "30 of 30 element(s) priced. Every element in the takeoff is in this total.",
});

const EMPTY = mk({
  coverage_note: "No elements in the takeoff -- load a model with geometry to price it.",
});

describe("estimateCoverage", () => {
  it("separates an empty takeoff, nothing priced, some priced and all priced", () => {
    expect(estimateCoverage(EMPTY)).toBe("empty");
    expect(estimateCoverage(NONE_PRICED)).toBe("none");
    expect(estimateCoverage(ZERO_QTY)).toBe("partial");
    expect(estimateCoverage(BOTH)).toBe("partial");
    expect(estimateCoverage(FULL)).toBe("full");
    expect(estimateCoverage(WALLS_ONLY)).toBe("full");
  });

  it("does not call an empty takeoff fully covered on a zero denominator", () => {
    // `priced >= element_count` is true for 0 of 0, and so is `!priced`. Neither answer is the
    // same finding: one is a model with nothing in it, the other a model nothing could price.
    expect(estimateCoverage(mk({}))).toBe("empty");
    expect(estimateCoverage(mk({}))).not.toBe("full");
  });
});

describe("estimateHeadline", () => {
  /** **This is the defect, in one assertion.** */
  it("tells 20 of 100 priced apart from 20 of 20, which agree on every rendered figure", () => {
    expect(ZERO_QTY.total).toBe(WALLS_ONLY.total);
    expect(ZERO_QTY.labor_hours).toBe(WALLS_ONLY.labor_hours);
    expect(ZERO_QTY.by_kind).toEqual(WALLS_ONLY.by_kind);
    // And the one footnote the old card had is empty in BOTH of them, which is why `unmapped`
    // could not have caught this: the slabs are mapped.
    expect(ZERO_QTY.unmapped).toEqual([]);
    expect(WALLS_ONLY.unmapped).toEqual([]);

    expect(estimateHeadline(ZERO_QTY)).not.toBe(estimateHeadline(WALLS_ONLY));
    expect(estimateHeadline(ZERO_QTY)).toContain("20 of 100 element(s)");
    expect(estimateHeadline(WALLS_ONLY)).toContain("20 of 20 element(s)");
  });

  it("never prints the total without its population", () => {
    for (const e of [ZERO_QTY, BOTH, FULL, WALLS_ONLY]) {
      expect(estimateHeadline(e)).toContain(`of ${e.element_count} element(s)`);
    }
  });

  it("says an empty takeoff has nothing to price rather than reporting 0% coverage", () => {
    // "nothing could be priced" is a finding about the model; an empty takeoff is a finding about
    // the upload. Rendering them alike sends a reader at the wrong thing.
    expect(estimateHeadline(EMPTY)).toContain("no takeoff to price");
    expect(estimateHeadline(EMPTY)).not.toContain("nothing could be priced");
    expect(estimateHeadline(NONE_PRICED)).toContain("nothing could be priced");
  });
});

describe("estimateCoverageLine", () => {
  it("reads the engine's sentence rather than rebuilding it", () => {
    // RENTROLL-BASIS shipped a second copy of an engine's note and the two had to be kept in
    // agreement by hand. One source.
    expect(estimateCoverageLine(BOTH)).toBe(BOTH.coverage_note);
  });

  it("still refuses a bare total if the server predates the note", () => {
    const old = mk({ total: 14916, element_count: 100, priced_elements: 20, coverage_note: "" });
    expect(estimateCoverageLine(old)).toContain("20 of 100");
    expect(estimateCoverageLine(mk({}))).toContain("No elements in the takeoff");
  });
});

describe("noQuantityLine", () => {
  it("names the dimension the takeoff is missing, because the remedy differs from a mapping", () => {
    const line = noQuantityLine(ZERO_QTY);
    expect(line).toContain("80 element(s)");
    expect(line).toContain("Slab×80 (needs m3)");
    expect(line).toContain("NOT priced at zero");
  });

  it("is null when every mapped class could be quantified", () => {
    expect(noQuantityLine(FULL)).toBeNull();
    expect(noQuantityLine(WALLS_ONLY)).toBeNull();
    expect(noQuantityLine(NONE_PRICED)).toBeNull();
  });
});

describe("unmappedLine", () => {
  it("stays a separate footnote from the unquantified one", () => {
    expect(unmappedLine(BOTH)).toContain("no assembly mapped");
    expect(unmappedLine(BOTH)).toContain("PipeSegment×30");
    expect(unmappedLine(BOTH)).not.toContain("Slab");
    expect(noQuantityLine(BOTH)).not.toContain("PipeSegment");
  });

  it("is null when every class maps", () => {
    expect(unmappedLine(ZERO_QTY)).toBeNull();
    expect(unmappedLine(FULL)).toBeNull();
  });
});

describe("estimateSuspect", () => {
  it("flags a total over part of the takeoff", () => {
    expect(estimateSuspect(ZERO_QTY)).toBe(true);
    expect(estimateSuspect(BOTH)).toBe(true);
    expect(estimateSuspect(NONE_PRICED)).toBe(true);
  });

  it("is quiet on a fully priced takeoff and on an empty one", () => {
    expect(estimateSuspect(FULL)).toBe(false);
    expect(estimateSuspect(WALLS_ONLY)).toBe(false);
    // An empty takeoff has nothing to be missing, and a warning colour on it would be noise a
    // reader learns to ignore.
    expect(estimateSuspect(EMPTY)).toBe(false);
  });
});

/** The consumer, at source level — the same bargain and the same limit the sibling read-modules
 *  record: an `if (false)` around the render would pass. What it catches is the revert. */
describe("the budget panel reads it", () => {
  const panel = readFileSync(resolve(__dirname, "budget.ts"), "utf8");

  it("renders the headline, the coverage note and both footnotes through this module", () => {
    expect(panel).toContain('from "./estimateCoverage"');
    expect(panel).toContain("estimateHeadline(e)");
    expect(panel).toContain("estimateCoverageLine(e)");
    expect(panel).toContain("estimateSuspect(e)");
    expect(panel).toContain("noQuantityLine(e)");
    expect(panel).toContain("unmappedLine(e)");
  });

  it("no longer prints the resource-based total as a bare money figure", () => {
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    expect(code.join("\n")).not.toContain("Resource-based — <b>${usd(e.total)}</b>");
    // The old footnote, rebuilt inline from `unmapped` with no mention of the unquantified half.
    expect(code.join("\n")).not.toContain("Unmapped: ${e.unmapped.map(");
  });
});
