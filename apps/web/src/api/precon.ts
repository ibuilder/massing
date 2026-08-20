/** Preconstruction: estimate continuity, snapshot, decisions, assumptions, VE, alignment.
 *
 *  SCALE-SEAM ㉒. Route-group `/projects/{pid}/precon`, taken out of `client.ts` by the route
 *  each method calls. **Six methods, one contiguous run** after feasibility and before the
 *  quality dashboard — this time the nearby comments and the route agree.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withPrecon<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Precon extends Base {
  /** Preconstruction estimate continuity — per-milestone totals + $/SF, drift, gap vs budget/GMP. */
  estimateContinuity(pid: string, budget?: number) {
    const qs = budget != null ? `?budget=${budget}` : "";
    return this.json<{ set_count: number; latest_total: number; latest_milestone: string | null;
      latest_psf: number | null; total_drift: number; total_drift_pct: number | null;
      budget: number | null; variance_to_budget: number | null; over_budget: boolean;
      milestones: string[]; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/estimate-continuity${qs}`);
  }
  /** One-click: price the current model and save it as an estimate set at the given milestone. */
  preconSnapshot(pid: string, milestone: string) {
    return this.json<{ created: string; ref: string; total: number; milestone: string }>(
      `/projects/${pid}/precon/snapshot?milestone=${encodeURIComponent(milestone)}`, { method: "POST" });
  }
  /** Preconstruction decision log — by status/alignment + open cost & schedule exposure. */
  decisionLog(pid: string) {
    return this.json<{ decision_count: number; open_count: number; disputed_count: number;
      open_cost_exposure: number; open_schedule_exposure_days: number;
      by_alignment: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/decisions`);
  }
  /** Assumptions & clarifications register — by status/category + open allowance exposure. */
  assumptionsRegister(pid: string) {
    return this.json<{ assumption_count: number; open_count: number; confirmed_count: number;
      open_cost_exposure: number; by_category: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/assumptions`);
  }
  /** Value-engineering cycle — proposed/accepted/rejected savings; optional target gap. */
  veLog(pid: string, target?: number) {
    const qs = target != null ? `?target=${target}` : "";
    return this.json<{ ve_count: number; proposed_savings: number; accepted_savings: number;
      rejected_savings: number; pipeline_savings: number; gap_after_accepted?: number;
      target_met?: boolean; by_status: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/ve${qs}`);
  }
  /** Calibrate-style preconstruction alignment — per-domain RAG + alignment score. */
  preconAlignment(pid: string) {
    return this.json<{ alignment_score: number | null; overall_status: string; latest_milestone: string | null;
      latest_total: number; budget: number | null; variance_to_budget: number | null;
      ve_accepted: number; ve_pipeline: number; open_decisions: number; open_assumptions: number;
      domains: { key: string; label: string; status: string; headline: string }[] }>(
      `/projects/${pid}/precon/alignment`);
  }
  };
}
