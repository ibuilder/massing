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
    return this.json<{
      projects: { id: string; name: string; band: string | null; score: number; count: number;
        high: number; medium: number; low: number; measured_sources: number;
        cells: Record<string, { state: string; score?: number; count?: number; high?: number;
          medium?: number; low?: number }> }[];
      sources: { key: string; label: string; score: number; count: number; high: number;
        projects_measured: number; projects_error: number }[];
      totals: { high: number; medium: number; low: number; count: number; score: number };
      band_tally: Record<string, number>;
      hotspots: { project_id: string; project: string; source: string; score: number; high: number;
        title: string | null; link: string | null }[];
      coverage: { cells: number; measured: number; errored: number; unknown: number;
        pct: number | null };
      project_count: number; projects_available: number; truncated: boolean; limit: number;
      note: string;
    }>(`/portfolio/risk?limit=${limit}`);
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
