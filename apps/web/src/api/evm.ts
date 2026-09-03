/** Earned Value Management: control accounts, earned schedule, model-based EV, S-curve, trend.
 *
 *  SCALE-SEAM ㉓. Route-group `/projects/{pid}/evm`, taken out of `client.ts` by the route each method
 *  calls. **Six methods, one contiguous run** — the tightest group left in the file.
 *
 *  `EvmEarnedSchedule` comes with them: it is used by two of these methods and nothing else in the
 *  codebase, so leaving it behind would have kept a type in `client.ts` whose only readers had moved.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 *
 *  *Found on the way out: `evm()` had been documented as "Cost-loaded resource histogram", which is
 *  `schedule.ts`'s `resourceLoading()`. Eleven methods across the client carried a neighbour's comment,
 *  left behind by earlier slices of this same extraction — fixed in v0.3.1075, with
 *  `api/docComments.test.ts` now standing where that defect got in.*
 *
 *  SCALE-SEAM (86) adds the CROSS-PROJECT versions of that same rollup — *is every job on track?*
 *  `executivePortfolio` is `projectHealth` asked over the whole portfolio: per-project status with
 *  SPI/CPI and milestones, GMP/EAC and variance at completion, plus equity return, and a status
 *  tally. `constructionPortfolio` is the same shape one domain narrower — projected over/under,
 *  open risks and exposure, recordables, open RFIs — and carries no investment figure at all; it
 *  is global (`/portfolio/construction`, no project id).
 *
 *  **⓫ recorded that "safety sat below and did not come", and `constructionPortfolio` does carry
 *  recordables.** It comes anyway: it is a cross-project EXECUTION rollup that happens to include a
 *  safety count, not the safety module. The single-project and all-project forms of one question
 *  belong together — the pairing that decided (83)'s commissioning trio.
 *
 *  `portfolioPrioritization` sat with these two in `client.ts` and did **not** come: it RANKS deals
 *  by a composite of return/budget/schedule/risk and returns a best and worst. That is an
 *  investment decision, not a status report, so it went to `proforma.ts`.
 *
 *  SCALE-SEAM ⓫ adds the executive health rollup — *is the job on track across domains?*
 *  Score is a mean; status is worst-of. Safety sat below and did **not** come.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export interface EvmEarnedSchedule {
  period: string; planned_start: string; planned_finish: string;
  planned_duration_periods: number; actual_time_periods: number; earned_schedule_periods: number;
  sv_t_periods: number; spi_t: number | null; spi_t_band: string;
  ieac_t_periods: number | null; forecast_finish: string | null; days_late: number | null;
  bac: number; ev: number; curve: { period: number; date: string; pv: number }[]; note: string;
}

export function withEvm<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Evm extends Base {
  /** Earned Value: control accounts and activities with PV/EV/AC, CV/SV, CPI/SPI, plus earned schedule. */
  evm(pid: string, dataDate?: string) {
    return this.json<{
      totals: { data_date: string; bac: number; pv: number; ev: number; ac: number; cv: number; sv: number;
        cpi: number | null; spi: number | null; cpi_band: string; spi_band: string;
        percent_complete: number; percent_spent: number;
        forecast: { eac: { cpi: number | null; at_plan: number; cpi_spi: number | null };
          eac_working: number | null; etc: number | null; vac: number | null;
          tcpi_bac: number | null; tcpi_eac: number | null; tcpi_warning: boolean;
          recommended: { stage: string; recommended_eac: string; guidance: string } };
        activity_count: number; note: string };
      control_accounts: { cost_code: string; bac: number; pv: number; ev: number; ac: number; cv: number;
        sv: number; cpi: number | null; spi: number | null; percent_complete: number }[];
      activities: { ref: string; name: string; cost_code: string; budget: number; percent: number;
        ev: number; pv: number; sv: number }[];
      earned_schedule: EvmEarnedSchedule | null;
    }>(`/projects/${pid}/evm${dataDate ? `?data_date=${dataDate}` : ""}`);
  }
  /** Earned Schedule (time-based EVM): ES, SV(t), SPI(t), IEAC(t) → forecast finish + PV curve. */
  earnedSchedule(pid: string, period: "week" | "month" = "week") {
    return this.json<EvmEarnedSchedule & { note?: string }>(
      `/projects/${pid}/evm/earned-schedule?period=${period}`);
  }
  /** Model-based EV: EV from physically-installed model elements × BAC, vs schedule EV. */
  evmModelEv(pid: string) {
    return this.json<{ total_elements: number; installed_elements: number; tracked_elements: number;
      model_percent_complete: number; has_field_data: boolean;
      bac: number; ev_model: number; ev_schedule: number; divergence: number; front_loaded_flag: boolean;
      note: string }>(`/projects/${pid}/evm/model-ev`);
  }
  /** EVM S-curve: cumulative PV (full baseline) + EV + AC to the data date, for the 3-line chart. */
  evmScurve(pid: string, period: "week" | "month" = "week") {
    return this.json<{ period: string; labels: string[]; pv: number[]; ev: number[]; ac: number[];
      bac: number; eac: number | null; data_date_period: number; note: string }>(
      `/projects/${pid}/evm/scurve?period=${period}`);
  }
  /** CPI/SPI performance-index trend across captured EVM snapshots (oldest-first). */
  evmTrend(pid: string) {
    return this.json<{ count: number; labels: string[]; cpi: number[]; spi: number[]; spi_t: number[];
      points: { data_date: string; period_label: string; cpi: number | null; spi: number | null;
        spi_t: number | null; eac: number | null; percent_complete: number | null }[]; note: string }>(
      `/projects/${pid}/evm/trend`);
  }
  /** Capture the current EVM state as a dated snapshot baseline (feeds the trend). */
  evmCaptureSnapshot(pid: string, body: { data_date?: string; period_label?: string; notes?: string } = {}) {
    return this.json<{ id: string; ref: string }>(`/projects/${pid}/evm/snapshot`,
      { method: "POST", body: JSON.stringify(body) });
  }

  /** projectHealth — per-domain status, overall score, ranked attention items. */
  projectHealth(pid: string) {
    return this.json<{
      health_score: number | null; overall_status: string;
      score_basis: string; status_basis: string;
      governing_domain: string | null; governing_detail: string | null;
      open_items_total: number; overdue_items_total: number;
      domains: { key: string; label: string; status: string; headline: string;
        open_count: number; overdue_count: number }[];
      attention_items: { domain: string; status: string; issue: string }[];
    }>(`/projects/${pid}/health`);
  }

  // --- One project's executive scorecard: on schedule next to on budget ---
  /** PX executive health: on-schedule (SPI, % complete, critical path, lookahead, milestones) next
   *  to on-budget (GMP, EAC, variance-at-completion, buyout, cash flow), with an overall status. */
  pxSummary(pid: string) {
    return this.json<{
      status: "on_track" | "at_risk" | "behind";
      schedule: { spi: number | null; pct_complete: number; activities: number; critical_path_days: number;
        critical_activities: number; lookahead_3wk: number; milestones: { late: number; due_soon: number; upcoming: number } };
      budget: { gmp: number; revised_gmp: number; eac: number; variance_at_completion: number; committed: number;
        committed_pct: number; spent_pct: number; draw_this_month: number;
        buyout: { packages: number; bought_out: number; savings: number } | null; baseline_movement: number | null };
    }>(`/projects/${pid}/px-summary`);
  }

  // --- The same health question across every project, not one ---
  /** Cross-project executive roll-up: each project's on-schedule + on-budget status + portfolio totals. */
  executivePortfolio() {
    return this.json<{
      projects: { id: string; name: string; status: "on_track" | "at_risk" | "behind"; spi: number | null;
        cpi: number | null;
        pct_complete: number; lookahead_3wk: number; milestones_late: number; gmp: number; eac: number;
        variance_at_completion: number; committed_pct: number; equity_irr: number | null; equity_multiple: number | null }[];
      totals: { gmp: number; eac: number; variance_at_completion: number; committed: number; equity: number; blended_equity_irr: number | null };
      status_tally: { on_track: number; at_risk: number; behind: number }; project_count: number }>(
      `/portfolio/executive`);
  }
  /** Cross-project CONSTRUCTION health — projected over/under, open risks and exposure,
   *  recordables, open RFIs, per project and as totals. Global (`/portfolio/construction`, no
   *  project id), and unlike `executivePortfolio` it carries no investment figure at all. */
  constructionPortfolio() {
    return this.json<{ project_count: number; totals: { projected_over_under: number; over_budget_count: number; open_risks: number; risk_exposure: number; recordables: number; open_rfis: number }; projects: { id: string; name: string; projected_over_under: number; over_budget: boolean; open_risks: number; risk_exposure: number; recordables: number; open_rfis: number }[] }>(
      "/portfolio/construction");
  }
  };
}
