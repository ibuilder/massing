/** PRICE-MATCHED — the pricing card's variance was computed across two populations.
 *
 *  `pricing.reconcile` sums `priced_total` over every line the price book could price, and
 *  `estimated_total` over the strictly smaller subset of those that also carried an
 *  `estimated_unit_price`. `variance_total` subtracted the one from the other. Measured on the
 *  repo's own `test_pricing.py` fixture — 2 priced lines, 1 of them estimated:
 *
 *  | | old | corrected |
 *  |---|---|---|
 *  | `priced_total` | 32,250 | 32,250 |
 *  | `estimated_total` | 20,000 | 20,000 |
 *  | `comparable_priced_total` | — | **18,500** |
 *  | `variance_total` | **+12,250** | **−1,500** |
 *
 *  The card renders a positive variance in `--status-warn` red, so it showed an overrun on a
 *  takeoff where the book is $1,500 CHEAPER than the estimate. **The sign was wrong, not the
 *  magnitude** — and `test_pricing.py` already asserted that sign one level down
 *  (`concrete["variance"] == 100 * 185 - 100 * 200`, commented *"negative variance (book
 *  cheaper)"*) without ever checking the total that contradicted it.
 *
 *  ### And the coverage, which is the defect the KNOWN_GAPS entry named
 *
 *  `matched` was declared and used only as a truthiness gate, so **400 takeoff lines with 3 priced
 *  rendered identically to 3 lines with 3 priced** — `Priced $55,500 (book) vs estimate $27,000 —
 *  variance $28,500`, with 397 unpriced lines and $397,000 of estimate absent from the sentence.
 *  `line_count`, `unmatched` and `unit_mismatch` were all computed by the engine and discarded;
 *  the last two were recoverable only by parsing per-line `note` strings.
 *
 *  The engine's module docstring already promised that "unmatched materials or unit mismatches are
 *  reported, not guessed", and they were — per line. *The promise was kept at the row level and
 *  the summary threw it away*, which is this session's recurring shape and the reason the fix is
 *  split: the engine states `coverage_note`, this module renders it.
 */
import type { PricingReconcile } from "../../api/cost";
import { usd } from "../../ui/charts";

/** How much of the takeoff the price book could price at all. */
export type PricedCoverage = "none" | "partial" | "full";

export function pricedCoverage(r: PricingReconcile): PricedCoverage {
  const total = r.line_count || 0;
  if (!total || !r.matched) return "none";
  return r.matched >= total ? "full" : "partial";
}

/**
 * The coverage sentence — the engine's own where it has one.
 *
 * Reading `coverage_note` rather than rebuilding it is deliberate: RENTROLL-BASIS shipped a second
 * copy of an engine's sentence and the two had to be kept in agreement by hand. One source.
 */
export function pricedCoverageLine(r: PricingReconcile): string {
  if (r.coverage_note) return r.coverage_note;
  // Only reached by a server that predates the note. Still never a bare count.
  const total = r.line_count || 0;
  if (!total) return "No takeoff quantities to price.";
  return `${r.matched} of ${total} takeoff line(s) priced.`;
}

/**
 * The variance, with the population it is over — or the reason there is none.
 *
 * `null` and zero are different answers and the old card could not show the difference: it tested
 * `v != null` and otherwise printed nothing at all, so "no line carries both a price and an
 * estimate" rendered as silence beside a priced total, which reads as agreement.
 */
export function varianceBasisLine(r: PricingReconcile): string {
  if (r.variance_total == null || !r.comparable_line_count) {
    return "No line carries both a price and an estimated unit price, so there is no variance to "
      + "report — which is not a variance of zero.";
  }
  const n = r.comparable_line_count;
  const over = r.variance_total > 0 ? "over" : r.variance_total < 0 ? "under" : "level with";
  const lines = `${n} line${n === 1 ? "" : "s"}`;
  const scope = n === r.matched
    ? `all ${lines} priced`
    : `${lines} priced AND estimated, not the ${r.matched} priced above`;
  return `${usd(Math.abs(r.variance_total))} ${over} estimate across ${scope} `
    + `(${usd(r.comparable_priced_total)} priced vs ${usd(r.estimated_total)} estimated)`;
}

/** True when the numbers on this card are about materially less than the takeoff they sit on, so a
 *  reader should be warned before quoting either total. */
export function pricingSuspect(r: PricingReconcile): boolean {
  if (pricedCoverage(r) !== "full") return true;
  // Fully priced and still suspect: the variance covers fewer lines than the price does.
  return r.comparable_line_count > 0 && r.comparable_line_count < r.matched;
}
