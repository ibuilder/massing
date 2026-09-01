/** Cost reconciliation across documents and cost codes: margin, cost-spine, commercial drift.
 *
 *  Route-group `/projects/{pid}/{margin,cost-spine,commercial-drift}`, taken out of `client.ts`
 *  because the size ratchet in `services/api/test_file_sizes.py` requires it — the file sat exactly
 *  on its 3,780 pin, and "a new endpoint added straight to `client.ts` will fail this, and that
 *  friction is the point". So the group moved and the pin moved DOWN.
 *
 *  **`commercialDrift` is new, and it exists because the endpoint was unreachable** —
 *  `test_route_reachability` flagged it as a new uncalled route, correctly, and the honest fix is a
 *  caller rather than an exemption.
 *
 *  The three are one family on purpose. `marginByCostCode` and `costSpine` both measure **per cost
 *  code**; `commercialDrift` measures **per document**. A roll-up adds before it compares, so two
 *  subcontracts can net to the right code total while one award drifted up and another down — which
 *  is invisible to the first two and is exactly what the third is for. Anyone reading one of these
 *  should know the other axis exists.
 *
 *  A mixin, so every call site resolves unchanged.
 */
import { HttpCore } from "./httpCore";
import type { ResolveAction } from "./types";

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
  };
}
