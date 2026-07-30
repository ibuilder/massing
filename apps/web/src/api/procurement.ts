/** Procurement: buyout packages and schedule, bid levelling, the compliance feed and vendor gate,
 *  three-way match, material price history and material-request suggestions.
 *
 *  SCALE-SEAM ⑥. Route-group `/procurement`, 9 methods / 86 lines. Reaches only `json` on HttpCore,
 *  so no shared private helper crosses this boundary.
 *
 *  Worth recording because it is what the roadmap predicted and the reason the estimate held: these
 *  nine methods were spread across **six** separate regions of `client.ts` (lines ~1297, ~2152, ~2634,
 *  ~3185, ~3242, ~3252). The `// --- section ---` comments label where a run *starts* and the file
 *  then carries on into other domains, so they have not delimited anything for a long time. Groups
 *  were located by the route each method calls, and each method's body by brace matching with its doc
 *  comment claimed by scanning BACKWARDS to the opening `/**` — a forward scan takes the *next*
 *  method's comment, and a single-line-comment assumption broke the ③ extraction outright.
 *
 *  A mixin, so every call site resolves unchanged. The surface ratchet in `api/surface.test.ts` is
 *  what proves it: moving a method is invisible to it, losing one fails it by number.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withProcurement<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Procurement extends Base {
  /** PROCURE-LEVEL: group QTO line items into buyout packages (each with an RFQ scope to send out). */
  buyoutPackages(pid: string, qtoLines: Record<string, unknown>[], by = "trade") {
    type Pkg = {
      package: string; line_count: number; est_cost: number;
      rfq_scope: { item: string; qty: number | null; unit: string }[];
      lines: { item: string; qty: number | null; unit: string; unit_price: number | null }[];
    };
    return this.json<{ grouped_by: string; package_count: number; total_est_cost: number; packages: Pkg[]; note: string }>(
      `/projects/${pid}/procurement/buyout-packages`, { method: "POST", body: JSON.stringify({ qto_lines: qtoLines, by }) });
  }
  /** PROCURE-LEVEL: score returned quotes for a buyout package on price + coverage completeness + lead time. */
  procurementLevel(pid: string, scope: Record<string, unknown>[], quotes: Record<string, unknown>[],
                   weights?: Record<string, number>) {
    type Supplier = {
      supplier: string; coverage_pct: number; covered_lines: number; scope_lines: number;
      covered_ext: number; est_full_scope: number | null; lead_time_days: number | null;
      scope_gaps: string[]; price_score: number; lead_score: number; score: number;
    };
    type Item = { item: string; qty: number; low_supplier: string | null; low_price: number | null; quoted_by: number };
    return this.json<{
      scope_lines: number; supplier_count: number; best_value_supplier: string | null;
      weights: { price: number; coverage: number; lead_time: number };
      suppliers: Supplier[]; items: Item[]; note: string;
    }>(`/projects/${pid}/procurement/level`, { method: "POST", body: JSON.stringify({ scope, quotes, weights }) });
  }
  /** BUYOUT-SCHED — time-phased buyout schedule from QTO joined to the install schedule → last-responsible
   * -order dates (install − lead), soonest first, classified overdue/urgent/upcoming/ok vs an as_of date. */
  buyoutSchedule(pid: string, body: {
    qto_lines: Record<string, unknown>[]; activities: Record<string, unknown>[];
    lead_times?: Record<string, number>; as_of?: string; default_lead_days?: number;
  }) {
    type Entry = {
      material: string; cost_code: string | null; trade: string | null; qty: number | null; unit: string | null;
      value: number | null; install_start: string | null; lead_time_days: number;
      last_responsible_order: string | null; buffer_days: number | null; status: string;
    };
    return this.json<{
      line_count: number; unscheduled: number; as_of: string | null; status_counts: Record<string, number>;
      overdue: number; next_30_days: number; total_value: number; entries: Entry[]; note: string;
    }>(`/projects/${pid}/procurement/buyout-schedule`, { method: "POST", body: JSON.stringify(body) });
  }
  procurementComplianceFeed(pid: string) {
    return this.json<{ within_days: number; vendors_flagged: number;
      vendors: { vendor: string; issues: string[]; can_bid: boolean; can_bill: boolean }[];
      note: string }>(`/projects/${pid}/procurement/compliance-feed`);
  }
  procurementGate(pid: string, vendor: string) {
    return this.json<{ vendor: string; coi: { status: string; expires: string | null };
      prequal: { status: string }; subcontract: { executed: boolean }; waiver_on_file: boolean;
      can_bid: boolean; bid_blockers: string[]; can_bill: boolean; bill_blockers: string[] }>(
      `/projects/${pid}/procurement/gate?vendor=${encodeURIComponent(vendor)}`);
  }
  // --- materials procure-to-pay (FieldMaterials) -----------------------------
  procurementThreeWayMatch(pid: string) {
    return this.json<{ pos: { po: string; vendor: string; cost_code: string; po_amount: number;
      deliveries: number; received: number; invoiced: number; invoice_count: number; variance: number;
      flags: string[]; status: string }[]; po_count: number; flagged: string[];
      message?: string | null }>(`/projects/${pid}/procurement/three-way-match`);
  }
  procurementLevelQuotes(pid: string, quotes: unknown[], record = false) {
    return this.json<{ suppliers: string[]; items: { item: string; low_supplier: string | null;
      low_price: number; prices: Record<string, number | null>; spread_pct: number }[];
      supplier_totals: Record<string, number>; best_all_in_supplier: string | null;
      line_by_line_savings: number; recorded_observations?: number; message?: string | null }>(
      `/projects/${pid}/procurement/level-quotes${record ? "?record=true" : ""}`,
      { method: "POST", body: JSON.stringify({ quotes }) });
  }
  /** PROC-LOOP — the price-observation ledger per material: min/median/avg/max, latest + drift. */
  procurementPriceHistory(pid: string, material?: string) {
    return this.json<{ materials: { material: string; observations: number; min: number;
      median: number; avg: number; max: number; unit?: string | null;
      latest: { unit_price: number; date: string; vendor?: string | null; source?: string | null };
      latest_vs_median_pct: number; vendors: string[];
      series: { date: string; unit_price: number }[] }[];
      material_count: number; message?: string | null }>(
      `/projects/${pid}/procurement/price-history${material ? `?material=${encodeURIComponent(material)}` : ""}`);
  }
  /** PROC-LOOP — QTO-derived material-request suggestions for a model selection; `create` also
   *  creates `material_request` records keyed to the GUIDs. */
  procurementMaterialSuggest(pid: string, opts: { q?: string; guids?: string[]; create?: boolean;
    needed_by?: string } = {}) {
    return this.json<{ suggestions: { material: string; ifc_class: string; qty: number | null;
      unit: string | null; elements: number; guids: string[] }[]; created: string[] }>(
      `/projects/${pid}/procurement/material-request/suggest`,
      { method: "POST", body: JSON.stringify(opts) });
  }
  };
}
