/** ITB-DOUBLE — five defects in the bid-coverage rollup, all of them flattering.
 *
 *  This is the screen that decides whether a trade has enough bidders to award, and every defect
 *  in `itb.summarize` pushed the same way:
 *
 *  | | measured before |
 *  |---|---|
 *  | 5 bids on a package whose name equals its ref | `responses: 10`, `bonded: 10`, rate **100%** (not 50%), coverage flipped to "covered" |
 *  | 5 bids, no invite list recorded | `response_rate: 0.0` — the value that means "nobody bid" — beside coverage "covered" |
 *  | 10 invited + 3 bids, plus an unrated package with 5 bids | `overall_response_rate: 80%`, where the rated package alone is 30% |
 *  | the two above together | a rate **over 100%** |
 *  | 3 bids posted, 2 naming a package that does not exist | `total_responses: 1` and no mention of the other two |
 *
 *  The card printed `${total_responses}/${total_invited} responses`, which is the third defect in
 *  fraction form — a numerator over every package and a denominator over only the rated ones.
 *
 *  `rows` was `Record<string, unknown>[]`, the opaque bucket, so `response_rate` and `coverage`
 *  were outside every audit built on declarations — the same way `sheet_index` hid SET-REVISED's
 *  counts. *An opaque row list costs more than an inline one: its fields are not even counted as a
 *  blind spot.*
 */
import type { ItbPackageRow, ItbSummary } from "../../api/procurement";

/** The headline. Never the two-population fraction the card used to print. */
export function itbHeadline(t: ItbSummary): string {
  const pkgs = t.package_count || 0;
  if (!pkgs) return "No bid packages yet.";
  const parts = [`${pkgs} package${pkgs === 1 ? "" : "s"}`];
  parts.push(`${t.total_responses} bid${t.total_responses === 1 ? "" : "s"} received`);
  if (t.overall_response_rate != null) {
    parts.push(`${t.overall_response_rate}% response across ${t.rated_packages} invited package`
      + `${t.rated_packages === 1 ? "" : "s"}`);
  }
  if (t.packages_without_bids) parts.push(`${t.packages_without_bids} with no bids`);
  return parts.join(" · ");
}

/**
 * The coverage sentence — the engine's own where it has one.
 *
 * Read rather than rebuilt, for the reason RENTROLL-BASIS established: a second copy of an
 * engine's sentence is a second thing to keep in agreement.
 */
export function itbCoverageLine(t: ItbSummary): string {
  if (t.coverage_note) return t.coverage_note;
  if (!t.package_count) return "No bid packages yet.";
  return `${t.rated_packages} of ${t.package_count} package(s) record an invite list.`;
}

/** A row's response rate as text — the basis where there is no rate. */
export function rateCell(r: ItbPackageRow): string {
  if (r.response_rate == null) return "— no invite list";
  return `${r.response_rate}%`;
}

/** The bids nobody is looking at, or null when every bid found its package. */
export function unmatchedLine(t: ItbSummary): string | null {
  if (!t.unmatched_submissions) return null;
  const n = t.unmatched_submissions;
  const one = n === 1;
  // Both verbs agree, not just the second. The first draft inflected `is`/`are` and left `name`
  // alone, giving "1 bid name a package" -- caught by its own test, which is the argument for
  // asserting the sentence rather than only the fields it is built from.
  return `${n} bid${one ? "" : "s"} ${one ? "names" : "name"} a package that does not exist on `
    + `this project and ${one ? "is" : "are"} counted in no package below — check the package `
    + `name on ${one ? "it" : "them"}.`;
}

/** True when the coverage on this screen should not be taken at face value: a bid went nowhere, or
 *  a package's rate has no denominator. */
export function itbSuspect(t: ItbSummary): boolean {
  return t.unmatched_submissions > 0 || t.unrated_packages > 0;
}
