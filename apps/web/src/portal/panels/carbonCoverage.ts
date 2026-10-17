/** CARBON-UNCONVERTED — a recognised material the engine could not convert left no trace but a tally.
 *
 *  `carbon.compute_item` declines a line two ways, and `compute` counted both as `unmatched`:
 *
 *  | refusal | what it means | remedy |
 *  |---|---|---|
 *  | no EPD factor matched | the material is unrecognised | add a factor |
 *  | unit not convertible | the material IS recognised, wrong unit family | record it in the factor's unit, or supply a density |
 *
 *  **The second is the dangerous one**, because the line is a known emitter that leaves
 *  `total_kgco2e`, `by_material` and `by_cost_code` entirely. Measured on a concrete frame whose
 *  takeoff is in kg:
 *
 *  ```
 *  329.17 tCO₂e embodied (A1-A3) · 1 line(s) unmatched
 *  materials: structural steel: 279.0 t · glazing: 50.2 t
 *  ```
 *
 *  2,400 t of concrete — worth roughly another 300 tCO₂e, and on most frames the single largest
 *  contributor — is absent from both rollups. *A total that silently excludes its largest term is
 *  worse than no total*, and embodied carbon is reported outward, to lenders and authorities.
 *
 *  The engine is right to refuse: converting a mass against a volume factor needs a density, and
 *  guessing one would fabricate the number. What was missing is the consumer saying so.
 *
 *  Same class as PRICE-MATCHED's `unmatched`/`unit_mismatch` split in `pricing.reconcile` — the
 *  sibling engine over the same `production_quantity` records, with the same keyword-table-plus-unit
 *  shape. *Fixing a class in one engine is a reason to look at its twin.*
 */
import type { ProjectCarbon } from "../../api/designPerformance";

/** How much of the takeoff reached the carbon total. */
export type CarbonCoverage = "none" | "partial" | "full";

export function carbonCoverage(c: ProjectCarbon): CarbonCoverage {
  const total = c.line_count || 0;
  if (!total || !c.assessed) return "none";
  return c.assessed >= total ? "full" : "partial";
}

/**
 * The coverage sentence — the engine's own where it has one.
 *
 * Read rather than rebuilt: RENTROLL-BASIS shipped a second copy of an engine's note and the two
 * had to be kept in agreement by hand.
 */
export function carbonCoverageLine(c: ProjectCarbon): string {
  if (c.coverage_note) return c.coverage_note;
  const total = c.line_count || 0;
  if (!total) return "No material quantities to assess.";
  return `${c.assessed} of ${total} quantity line(s) assessed.`;
}

/**
 * The materials recognised and left out of the total, or null when none are.
 *
 * Named, never counted: a reader shown "1 line unmatched" cannot tell whether the missing emitter
 * is a stair nosing or the whole concrete frame.
 */
export function excludedMaterialsLine(c: ProjectCarbon): string | null {
  const names = Object.keys(c.unconverted_materials || {});
  if (!names.length) return null;
  const verb = names.length === 1 ? "is" : "are";
  return `${names.sort().join(", ")} ${verb} recognised but NOT in this total — the quantity's unit `
    + "is not in the factor's unit family. Re-record in the factor's unit to include it; the "
    + "figure above is missing it until then.";
}

/** The unrecognised-material count, which has a different remedy, or null when there are none. */
export function noFactorLine(c: ProjectCarbon): string | null {
  if (!c.no_factor) return null;
  return `${c.no_factor} line(s) name a material with no EPD factor — add a factor to bring them in.`;
}

/** True when the total omits a material the engine recognised. The loudest of the two gaps: an
 *  unrecognised line might be a non-material row, a recognised one is a real emitter. */
export function carbonSuspect(c: ProjectCarbon): boolean {
  return Object.keys(c.unconverted_materials || {}).length > 0;
}
