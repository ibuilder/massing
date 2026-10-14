/** PREFIX-RANKED — "showing 2 of 3" over a worst-first table whose 2 were chosen before scoring.
 *
 *  Both portfolio sweeps bound their work the same way:
 *
 *  ```python
 *  scanned = projects[:max(0, int(limit))]        # risk_portfolio.py:75, resource_portfolio.py:171
 *  ```
 *
 *  A plain PREFIX of the caller's project list, taken **before any scoring**. `risk_portfolio` then
 *  does `rows.sort(key=lambda r: (-r["score"], ...))` and `hotspots[:8]` — so the ranking and the
 *  hotspots are over the prefix, not the portfolio. Measured against a live server with three
 *  projects, the risk on the last one by name, at `?limit=2`:
 *
 *  | | ZZZ Dangerous | AAA Quiet | BBB Quiet | hotspots | totals |
 *  |---|---|---|---|---|---|
 *  | full sweep | **score 3, high 1** | 0 | 0 | `[(ZZZ, coordination, 3)]` | 1 high |
 *  | prefix, limit 2 | **absent** | 0 | 0 | **`[]`** | **0 high** |
 *
 *  The caption read `2 project(s) × 5 engines · 0 high / 0 medium / 0 low · showing 2 of 3`. *The
 *  portfolio's only risky project is gone, the hotspots list is empty, and the heading reports zero
 *  high severity across the book* — not a truncation caveat but a clean bill of health over a
 *  portfolio carrying a high-severity coordination risk. `showing 2 of 3` is accurate about counts
 *  and silent about SELECTION, which is the only thing that matters when the table is sorted
 *  worst-first: a reader acts on the top rows and assumes they are the top rows.
 *
 *  ## The risk engine says exactly this, in a `note` declared and read by nothing
 *
 *  > When `truncated`, the scanned set is a deterministic prefix of the caller's projects, **not the
 *  > riskiest ones** — ranking is what the sweep produces, so it cannot select what to sweep.
 *
 *  That last clause is the reason this cannot be fixed by sorting earlier: the score does not exist
 *  until the sweep has run, so bounding the sweep necessarily bounds it by something other than
 *  rank. *The engine is right and the only available fix is to say so* — which is why this module
 *  renders the note rather than paraphrasing it.
 *
 *  ## And the resourcing sweep has the same shape with NO note about it
 *
 *  `resource_portfolio` prefixes identically and then aggregates a **peak**: `peak.units` is the
 *  maximum weekly concurrent demand summed across projects, and `over_allocation` is the whole
 *  point of the view — its own note says *"a trade committed to several jobs in one week is
 *  over-committed even when every project looks comfortable alone."* Over a prefix, a max is a
 *  LOWER BOUND presented as the peak, and a trade over-committed across the 1st and 40th projects
 *  reads as comfortable. Its `note` explains the cross-project arithmetic and **never mentions the
 *  prefix**, so for that route the caveat exists in no sentence anywhere — which is why
 *  `aggregatePrefixCaveat` states it in the client rather than passing something through. *The one
 *  place a consumer should author a caveat is where no engine has written one.*
 */
export type Tone = "" | "warn" | "crit";

/** Literal, not `var(--status-${tone})` — a runtime-built custom property resolves to nothing and
 *  is dropped in silence (`apps/web/src/shell/cssVars.test.ts` holds that line). */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** The scope triple both portfolio sweeps publish. */
export interface SweptScope {
  project_count: number;
  projects_available: number;
  truncated: boolean;
}

/** How many projects the sweep covered, stated as coverage rather than as a count.
 *
 *  Replaces `showing N of M`, which reads as "the first N of M" to nobody and as "the top N of M"
 *  to everybody looking at a sorted table. */
export function scopeLine(s: SweptScope): string | null {
  if (!s.truncated) return null;
  const skipped = Math.max(0, s.projects_available - s.project_count);
  return `${s.project_count} of ${s.projects_available} project(s) swept — ${skipped} not examined.`;
}

/** The caveat for a RANKED aggregate over a prefix. Renders the engine's own sentence when it has
 *  one, because the engine owns the statement of its own basis.
 *
 *  `crit`, not `warn`: a ranking that omits the worst row is wrong about the one thing it is for,
 *  and the measured case reported zero high severity over a portfolio that had some. */
export function rankedPrefixCaveat(s: SweptScope, note?: string): {
  text: string; tone: Tone;
} | null {
  if (!s.truncated) return null;
  const skipped = Math.max(0, s.projects_available - s.project_count);
  const own = (note ?? "").includes("not the riskiest")
    ? ` ${note!.slice(note!.indexOf("When `truncated`"))}`
    : "";
  return {
    tone: "crit",
    text: `These are NOT the ${s.project_count} riskiest projects. The sweep is bounded before any `
      + `scoring, so the ${s.project_count} examined are a deterministic prefix of your project `
      + `list and the ${skipped} unexamined one(s) could each outrank every row below — the counts `
      + `in this heading are over the prefix, not the book. Raise the limit to rank the whole `
      + `portfolio.${own}`,
  };
}

/** The caveat for a MAX or TOTAL over a prefix: the figure is a floor, not the figure.
 *
 *  `what` names the quantity so the sentence reads about it ("peak concurrent demand"). Authored
 *  here rather than passed through, because `resource_portfolio`'s note does not mention the
 *  prefix at all — see the module note. */
export function aggregatePrefixCaveat(s: SweptScope, what: string): {
  text: string; tone: Tone;
} | null {
  if (!s.truncated) return null;
  const skipped = Math.max(0, s.projects_available - s.project_count);
  return {
    tone: "warn",
    text: `${what} is a LOWER BOUND: it is summed over ${s.project_count} of `
      + `${s.projects_available} project(s), and the ${skipped} unexamined one(s) can only add to `
      + `it. A trade over-committed across an examined job and an unexamined one reads as `
      + `comfortable here. Raise the limit before treating this as the book's figure.`,
  };
}

/** Does the heading's own count cover the portfolio? The question a reader should not have to ask,
 *  exposed so a caller can choose a heading instead of appending a caveat to a wrong one. */
export function coversPortfolio(s: SweptScope): boolean {
  return !s.truncated && s.project_count >= s.projects_available;
}
