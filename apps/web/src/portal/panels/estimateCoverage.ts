/** ESTIMATE-ZEROQTY — the resource-based estimate card quoted a cost total with no population.
 *
 *  `assemblies.estimate_resource_based` returns `element_count`, and that key has been declared on
 *  the client since the method was written and rendered by nothing. The card printed
 *  `Resource-based — $14,916 · 1,240 crew-hours`, the L/M/E split, a trade table and an
 *  `Unmapped:` footnote — so the only thing bounding the total was a list of classes with no
 *  assembly. Measured on the engine, 80 `IfcSlab` carrying no volume beside 20 `IfcWall` carrying
 *  area:
 *
 *  | | old | corrected |
 *  |---|---|---|
 *  | `total` | 14,916 | 14,916 |
 *  | `lines` | `IfcWall …`, **`IfcSlab \| 80 \| 0.00 m3 \| $0.00`** | `IfcWall …` |
 *  | `unmapped` | `[]` | `[]` |
 *  | `no_quantity` | — | **`IfcSlab × 80, needs m3`** |
 *  | `priced_elements` | — | **20 of 100** |
 *
 *  **The total was right and its population was unstated**, which is the shape this session keeps
 *  finding: `_class_quantity` returns `agg.get(dim, 0.0)`, so a class that MAPPED but whose takeoff
 *  carries nothing in the assembly's billing dimension was priced at zero and appended to `lines`
 *  as a success. Same shape as CARBON-UNCONVERTED — matched, contributes nothing, counted as
 *  priced — except that here the artifact is a cost estimate, and a cost estimate is quoted.
 *
 *  Three states a reader must tell apart, and the old card rendered the first two identically:
 *
 *  * **priced** — in `total`.
 *  * **mapped, unquantifiable** — `no_quantity`. Wants a takeoff (or a geometry fix), not a
 *    mapping. A $0 line said "this work is free".
 *  * **unmapped** — `unmapped`. Wants a mapping. `CLASS_TO_ASSEMBLY` covers 11 architectural and
 *    structural classes and no MEP, furniture or proxies, so on a coordinated model this is
 *    routinely most of the element count.
 */
import type { ResourceEstimate } from "../../api/estimate";
import { usd } from "../../ui/charts";

/** How much of the takeoff reached the total. */
export type EstimateCoverage = "empty" | "none" | "partial" | "full";

export function estimateCoverage(e: ResourceEstimate): EstimateCoverage {
  const total = e.element_count || 0;
  if (!total) return "empty";
  const priced = e.priced_elements || 0;
  if (!priced) return "none";
  return priced >= total ? "full" : "partial";
}

/**
 * The headline. The total is never printed without the population it is over.
 *
 * `0 of 0` is not a coverage failure — an empty takeoff has nothing to miss — so it says so
 * instead of reading as "nothing could be priced", which is a finding about the model.
 */
export function estimateHeadline(e: ResourceEstimate): string {
  const cov = estimateCoverage(e);
  const priced = usd(e.total || 0);
  if (cov === "empty") return `Resource-based — no takeoff to price`;
  const denom = `${e.priced_elements} of ${e.element_count} element(s)`;
  if (cov === "none") return `Resource-based — ${priced} over ${denom}: nothing could be priced`;
  return `Resource-based — ${priced} over ${denom}`;
}

/**
 * The coverage sentence — the engine's own where it has one.
 *
 * Reading `coverage_note` rather than rebuilding it is deliberate: RENTROLL-BASIS shipped a second
 * copy of an engine's sentence and the two had to be kept in agreement by hand. One source.
 */
export function estimateCoverageLine(e: ResourceEstimate): string {
  if (e.coverage_note) return e.coverage_note;
  // Only reached by a server that predates the note. Still never a bare total.
  const total = e.element_count || 0;
  if (!total) return "No elements in the takeoff.";
  return `${e.priced_elements || 0} of ${total} element(s) priced.`;
}

/**
 * The mapped-but-unquantifiable footnote, or null.
 *
 * Separate from the unmapped footnote because the remedy is different and the old card had no way
 * to say so — these classes were $0 rows in the priced table.
 */
export function noQuantityLine(e: ResourceEstimate): string | null {
  const rows = e.no_quantity || [];
  if (!rows.length) return null;
  const n = rows.reduce((a, r) => a + (r.count || 0), 0);
  const detail = rows.map((r) => `${r.ifc_class.replace("Ifc", "")}×${r.count} (needs ${r.needs})`);
  return `${n} element(s) map to an assembly the takeoff cannot quantify, so they are NOT in the `
    + `total and NOT priced at zero: ${detail.join(", ")}`;
}

/** The unmapped footnote, or null. Unchanged in meaning; here so both footnotes read alike. */
export function unmappedLine(e: ResourceEstimate): string | null {
  const rows = e.unmapped || [];
  if (!rows.length) return null;
  const n = rows.reduce((a, r) => a + (r.count || 0), 0);
  const detail = rows.map((r) => `${r.ifc_class.replace("Ifc", "")}×${r.count}`);
  return `${n} element(s) have no assembly mapped: ${detail.join(", ")}`;
}

/** True when the total covers materially less than the takeoff it sits on, so a reader should be
 *  warned before quoting it. An empty takeoff is not suspect — there is nothing to be missing. */
export function estimateSuspect(e: ResourceEstimate): boolean {
  const cov = estimateCoverage(e);
  return cov === "none" || cov === "partial";
}
