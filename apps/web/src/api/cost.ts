/** Cost reconciliation, vintages, and the GC GMP / pay-app stack.
 *
 *  SCALE-SEAM ㉚. Grouped by what they ANSWER: *what does the GC job cost, and how is the GMP billed?*
 *  `costSummary` sat ~140 lines above `gmpBudget` in `client.ts`, with versions, safety, QTO and
 *  smart-views in between. `pxSummary` sat IN the GMP run and did **not** come — it answers whether
 *  the job is on track (schedule + budget together), not what the GMP is. `costTraceability` stayed
 *  too: ㉘ already recorded it as a takeoff question. *Adjacency in a file is not a relationship.*
 *
 *  Composed through the existing `withCost` wrapper — no extra `withX()` on `ApiClient`.
 */
import { HttpCore } from "./httpCore";
import type { ModuleRecord, ResolveAction } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withCost<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Cost extends Base {
  /** Close the current pay period (C1): roll every SOV line's `completed_this` into
   *  `completed_prev`, the way successive AIA pay applications accumulate.
   *
   *  **The only path that does this.** Nothing else in the API rolls `completed_prev`, and the
   *  route had no client caller until v0.3.1050 — so the pay-application cycle could not advance
   *  from the product and every application re-billed the same "completed this period" amounts.
   *  Mutating with no undo in the app, so the caller confirms before invoking it. */
  advancePayPeriod(pid: string) {
    return this.json<{ lines_advanced: number }>(`/projects/${pid}/cost/advance-period`,
      { method: "POST" });
  }

  marginByCostCode(pid: string) {
    type Row = { cost_code: string; budget: number; committed: number; actual: number; billed: number;
      buyout_margin: number; variance: number; pct_committed: number | null; pct_spent: number | null;
      over_committed: boolean; over_budget: boolean; actions: ResolveAction[] };
    return this.json<{
      code_count: number; total_budget: number; total_committed: number; total_actual: number;
      total_billed: number; total_buyout_margin: number; total_variance: number;
      pct_committed: number | null; pct_spent: number | null;
      over_committed_codes: number; over_budget_codes: number; rows: Row[]; note: string;
    }>(`/projects/${pid}/margin/by-costcode`);
  }
  /** COST-SPINE — does one cost code carry the same scope across budget → commitment → actual →
   *  invoice? Reports presence, not just amounts; `traceability_pct` is the share of committed+actual
   *  money on a budgeted code, which is the coverage the margin report above inherits. */
  costSpine(pid: string) {
    type SpineRow = { cost_code: string; code: string; ref: string;
      budget: number; committed: number; actual: number; billed: number;
      counts: Record<string, number>; stages_present: string[]; stage_count: number;
      first_break: string | null; traceable: boolean; flags: string[]; actions: ResolveAction[] };
    return this.json<{
      rows: SpineRow[]; code_count: number; stages: string[];
      unassigned: Record<string, { amount: number; count: number }>;
      unassigned_total: number; unassigned_count: number;
      codes_not_in_register: string[]; unused_register_codes: string[];
      traceability_pct: number | null; traceable_spend: number; total_spend: number;
      broken: string[]; note: string;
    }>(`/projects/${pid}/cost-spine`);
  }
  /** R41-COMMERCIAL-DRIFT — bid → executed contract → invoiced, per DOCUMENT rather than per cost
   *  code. Change orders are reported beside the drift and never inside the bid→contract hop (a CO is
   *  money somebody signed for); an unaccepted alternate is not part of the award. A hop missing a
   *  figure on either side is `incomparable`, which is not a zero-dollar difference. */
  commercialDrift(pid: string) {
    type Hop = { hop: string; status: "compared" | "incomparable";
      from: number | null; to: number | null; delta: number | null; drift_pct: number | null;
      note?: string; award_basis?: string; change_orders?: number; invoice_count?: number };
    return this.json<{
      rows: { subcontract_id: string; vendor: string; trade: string | null;
        contract_value: number | null; change_orders: number; contract_sum_to_date: number | null;
        invoiced: number | null; hops: Hop[]; incomparable_hops: string[] }[];
      subcontract_count: number; hops_compared: number; hops_incomparable: number;
      drifted_count: number; largest_drift: number; total_change_orders: number; note: string;
    }>(`/projects/${pid}/commercial-drift`);
  }
  /** Statutory lien waiver / release fields for a pay application (C1). */
  lienWaiver(pid: string, kind: "conditional_progress" | "unconditional_progress"
      | "conditional_final" | "unconditional_final" = "conditional_progress", appNo = 1) {
    const q = new URLSearchParams({ kind, app_no: String(appNo) });
    return this.json<{
      kind: string; title: string; conditional: boolean; final: boolean;
      amount: number; body: string; notice: string; project_name: string;
    }>(`/projects/${pid}/cost/lien-waiver?${q.toString()}`);
  }
  lienWaiverPdfUrl(pid: string, kind = "conditional_progress", appNo = 1) {
    return this.url(`/projects/${pid}/cost/lien-waiver.pdf?kind=${encodeURIComponent(kind)}&app_no=${appNo}`);
  }
  /** Installed cost-database vintages plus what the offline importer can build. */
  costDatasets() {
    return this.json<{
      datasets: { id: string; name?: string; vintage?: number; quarter?: number | null;
        origin?: string; is_latest?: boolean }[];
    }>("/cost/datasets");
  }
  /** The vintage this project's estimate resolves through (pinned, else latest). */
  costVintage(pid: string) {
    return this.json<{
      pinned_id: string | null;
      resolved: { id?: string; name?: string; vintage?: number; quarter?: number | null;
        origin?: string } | null;
      adjustment: Record<string, unknown> | null;
    }>(`/projects/${pid}/cost-vintage`);
  }
  /** Actual unit rates per cost code across the caller's projects (cost ÷ installed quantity). */
  unitRates(minProjects = 3) {
    return this.json<{
      cost_codes: { cost_code: string; unit: string; projects: number; below_threshold: boolean;
        low: number; p25: number; median: number; p75: number; high: number;
        pooled_rate: number | null; spread_ratio: number | null }[];
      code_count: number; usable_count: number; min_projects: number;
      message: string | null;
    }>(`/benchmarks/unit-rates?min_projects=${minProjects}`);
  }

  /** costSummary — job-cost rollup: budget, committed, actual, forecast, projected over/under. */
  costSummary(pid: string) {
    return this.json<{ budget: number; committed: number; actual: number; forecast: number; projected_over_under: number; pct_committed: number; pct_spent: number }>(
      `/projects/${pid}/cost/summary`);
  }
  /** Full GC project budget (GMP): direct + GC/GR + overhead/fee/contingency, each budget vs
   *  committed vs actual vs variance; reconciled to the prime contract + developer proforma. */
  gmpBudget(pid: string) {
    type Cat = { key: string; name: string; budget: number; committed: number; actual: number;
      forecast: number; eac: number; etc: number; variance: number; lines: { name: string; budget: number;
      committed: number; eac?: number; etc?: number; variance: number; is_group?: boolean }[];
      groups?: { name: string; budget: number }[] };
    return this.json<{
      gmp: { contract_value: number; computed: number; reconciliation: number | null; cost_of_work: number;
        approved_changes?: number; unallocated_changes?: number; revised?: number;
        markups: { overhead_pct: number; fee_pct: number; contingency_pct: number } };
      categories: Cat[];
      totals: { budget: number; committed: number; actual: number; forecast: number; eac: number; etc: number; variance: number };
      completion: { bac: number; eac: number; etc: number; actual_to_date: number; projected_over_under: number; pct_spent: number };
      bid_packages: { ref: string; name: string; trade?: string; budget: number; awarded: number;
        bought_out: boolean; savings: number; submissions: number }[];
      buyout: { packages: number; bought_out: number; budget: number; awarded: number; savings: number };
      staffing: { projected: number; headcount_roles: number };
      proforma: { hard_cost: number; gmp_vs_hard: number } | null;
    }>(`/projects/${pid}/budget/gmp`);
  }
  /** Snapshot the current GMP budget as the baseline (for budget-movement tracking). */
  setBudgetBaseline(pid: string) {
    return this.json<{ captured_at: string; gmp_computed: number; lines: number }>(
      `/projects/${pid}/budget/baseline`, { method: "POST" });
  }
  /** Budget movement vs the baseline (per category + line). Rejects if no baseline set. */
  budgetVariance(pid: string) {
    return this.json<{ captured_at: string; baseline_gmp: number; current_gmp: number; total_delta: number;
      categories: { key: string; baseline: number; current: number; delta: number }[];
      lines: { code: string; baseline: number; current: number; delta: number }[] }>(
      `/projects/${pid}/budget/variance`);
  }
  /** Cost-loaded schedule → monthly cash-flow / draw curve (construction S-curve). */
  budgetCashflow(pid: string) {
    return this.json<{ total: number; months: number; loaded_activities: number; peak_month_cost: number;
      series: { month: string; cost: number; cumulative: number; pct: number }[] }>(
      `/projects/${pid}/budget/cashflow`);
  }
  /** Seed the owner pay-app SOV from the GMP budget lines (idempotent unless replace). */
  sovFromBudget(pid: string, replace = false) {
    return this.json<{ created: number; lines?: number; scheduled_value?: number; skipped?: number; note?: string }>(
      `/projects/${pid}/cost/sov/from-budget?replace=${replace}`, { method: "POST" });
  }
  /** The owner pay application (G702 certificate + G703 continuation) as a signable PDF blob. */
  async payAppPdf(pid: string, appNo = 1) {
    const res = await fetch(this.url(`/projects/${pid}/cost/g702.pdf?app_no=${appNo}`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`pay-app PDF -> ${res.status}`);
    return res.blob();
  }
  /** Create an owner-invoice record from the current pay application (amount = current payment due). */
  payAppInvoice(pid: string, appNo = 1) {
    return this.json<{ owner_invoice: ModuleRecord; application_no: number; amount: number }>(
      `/projects/${pid}/cost/pay-app/invoice`, { method: "POST", body: JSON.stringify({ app_no: appNo }) });
  }
  };
}
