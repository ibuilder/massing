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
  /** Preconstruction decision log — by status/alignment/category + open cost & schedule exposure.
   *
   *  DECISION-AXES. `decided_count`, `by_status` and `by_category` were all undeclared, so on a
   *  DECISION log the screen could not say how many decisions had been made, could not account for
   *  the rest, and could not show which trade they cluster in. */
  decisionLog(pid: string) {
    return this.json<{ decision_count: number;
      /** STATES. These three account for every decision between them. */
      open_count: number; decided_count: number; superseded_count: number;
      /** An ALIGNMENT, cutting across all three states — not a fourth slice of the same pie. The
       *  headline printed `open` and `disputed` as one series; measured on a 7-row register, 2 were
       *  disputed and one of those was already DECIDED, which is a claim-exposure question rather
       *  than a pending action. */
      disputed_count: number; disputed_open: number; disputed_decided: number;
      axis_basis: string;
      open_cost_exposure: number; open_schedule_exposure_days: number;
      /** Open decisions carrying no usable figure — what the two exposures above leave out. This
       *  register is the one of the three that was already on a screen, so the subset problem was
       *  live here rather than latent. */
      open_without_cost_impact: number; open_without_schedule_impact: number;
      by_status: Record<string, number>;
      by_alignment: Record<string, number>;
      /** Which trade or area the decisions cluster in — on a precon log this is what tells a PM
       *  where the next design meeting goes. */
      by_category: Record<string, number>;
      rows: { ref: string | null; subject: string | null; category: string; state: string;
        alignment: string; cost_impact: number; cost_impact_given: boolean;
        schedule_impact_days: number; schedule_impact_days_given: boolean;
        decided_by: string | null; due_date: string | null }[];
      rows_truncated: boolean; max_rows: number }>(
      `/projects/${pid}/precon/decisions`);
  }
  /** Assumptions & clarifications register — by status/category + open allowance exposure.
   *
   *  `open_cost_exposure` sums the OPEN rows' `cost_impact`, and a row carrying no usable figure
   *  adds nothing to it while still counting in `open_count` — so the money is a total over a
   *  subset of the count beside it. `open_without_cost_impact` is what qualifies the exposure;
   *  `cost_impact_given` marks the row. The row shape was `Record<string, unknown>`, which is the
   *  erasure that keeps a response out of reach of every audit here (see TRAY-UNCOMPUTED). */
  assumptionsRegister(pid: string) {
    return this.json<{ assumption_count: number; open_count: number; confirmed_count: number;
      voided_count?: number; open_cost_exposure: number;
      rows_without_cost_impact: number; open_without_cost_impact: number;
      by_status?: Record<string, number>; by_category: Record<string, number>;
      rows: { ref: string | null; subject: string | null; category: string; state: string;
        cost_impact: number; cost_impact_given: boolean; owner: string | null }[] }>(
      `/projects/${pid}/precon/assumptions`);
  }
  /** Value-engineering cycle — proposed/accepted/rejected savings; optional target gap.
   *
   *  **`target_met` is `accepted_savings >= target` and that is a verdict over a subset.** An idea
   *  recorded with no savings figure counts in `ve_count` and in `by_status` and adds 0 to every
   *  total, so a `false` can mean *the figures were never recorded* rather than *the ideas do not
   *  close the gap*. `accepted_without_savings` is the count that bears on it, and
   *  `rows_without_savings` on the totals. `target` is echoed back so a reading can state its own
   *  basis. */
  veLog(pid: string, target?: number) {
    const qs = target != null ? `?target=${target}` : "";
    return this.json<{ ve_count: number; proposed_savings: number; accepted_savings: number;
      rejected_savings: number; pipeline_savings: number;
      rows_without_savings: number; accepted_without_savings: number;
      target?: number; gap_after_accepted?: number; target_met?: boolean;
      by_status: Record<string, number>;
      rows: { ref: string | null; subject: string | null; status: string; savings: number;
        savings_given: boolean }[] }>(
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
