import { HttpCore } from "./httpCore";
import type { RiskDigest } from "./types";

/**
 * Risk — the project risk surfaces.
 *
 * SCALE-SEAM ㉒, forced rather than chosen: adding `riskDigest` put `client.ts` at 3,132 against a
 * 3,125 ratchet **and reddened main**, because the release that added it re-ran vitest, lint, build
 * and the route gate but not `test_file_sizes`. The ratchet had been run earlier in the same
 * session, before a different edit — a check run before the change it is meant to cover is not a
 * check of that change.
 *
 * `riskBoard` comes along because it is the same subject and the same reason: two methods is a thin
 * seam, and the alternative was raising a pin the file's own comment says to buy a cluster out of
 * instead.
 */
type Ctor<T> = new (...args: any[]) => T;

/** PREFIX-RANKED — `GET /portfolio/risk`.
 *
 *  NAMED rather than inline, which is the action `apps/web/src/api/deadFieldTyped.test.ts`'s
 *  inline ceiling asked for when declaring `weights` tripped it. It is the fourth time in this
 *  session that ratchet redirected a change from *raise the number* to *declare it properly*.
 *
 *  The scope triple is the whole of PREFIX-RANKED: the sweep is `projects[:limit]`, a prefix taken
 *  BEFORE any scoring, and `projects` / `hotspots` / `totals` are all over that prefix. */
export interface PortfolioRisk {
  projects: { id: string; name: string; band: string | null; score: number; count: number;
    high: number; medium: number; low: number; measured_sources: number;
    cells: Record<string, { state: string; score?: number; count?: number; high?: number;
      medium?: number; low?: number }> }[];
  sources: { key: string; label: string; score: number; count: number; high: number;
    projects_measured: number; projects_error: number }[];
  /** Over the SWEPT projects, not the portfolio, whenever `truncated`. */
  totals: { high: number; medium: number; low: number; count: number; score: number };
  band_tally: Record<string, number>;
  /** The top 8 of the prefix, not of the book. */
  hotspots: { project_id: string; project: string; source: string; score: number; high: number;
    title: string | null; link: string | null }[];
  coverage: { cells: number; measured: number; errored: number; unknown: number;
    pct: number | null };
  project_count: number;
  projects_available: number;
  truncated: boolean;
  limit: number;
  /** `_WEIGHT` — the severity weights the intensity score is built from. `portfolio.ts` hardcodes
   *  its colour ramp thresholds (9 and 4) against these, so declaring them is what lets the ramp
   *  and the formula be checked against each other instead of drifting apart in silence. */
  weights: { high: number; medium: number; low: number };
  /** Carries the sentence this item exists for: *"When `truncated`, the scanned set is a
   *  deterministic prefix of the caller's projects, not the riskiest ones — ranking is what the
   *  sweep produces, so it cannot select what to sweep."* Declared since the route shipped and
   *  read by nothing until PREFIX-RANKED. */
  note: string;
}


export function withRisk<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Risk extends Base {
  /** The risk narrative **with its drivers** — SPI, EAC, variance, open RFIs/submittals/CORs,
   *  incidents and the top alerts it was computed from. `/ai/risk-summary` (see `riskSummary`)
   *  returns the same prose with none of that, and a risk narrative a reader cannot check is the
   *  same as no narrative. Route shipped with no client caller until v0.3.1051. */
  riskDigest(pid: string) {
    return this.json<RiskDigest>(`/projects/${pid}/risk-digest`);
  }
  /** The same board gridded across the portfolio — projects × risk engine, severity-weighted.
   *  `state` on a cell is not decoration: an engine that could not run reads `error`, and the map
   *  must not render that as a clear cell. `coverage` says how much of the grid is measured. */
  portfolioRisk(limit = 25) {
    return this.json<PortfolioRisk>(`/portfolio/risk?limit=${limit}`);
  }
  /** RISK-BOARD: one ranked register unifying every computed risk signal (deep-linked per item). */
  riskBoard(pid: string) {
    return this.json<{ items: { source: string; severity: "high" | "medium" | "low"; title: string;
      detail: string; link: string | null; metric: number | null }[]; count: number;
      by_severity: { high: number; medium: number; low: number };
      lanes: Record<string, string>; band: string; note: string }>(`/projects/${pid}/risk-board`);
  }
  };
}
