/** Construction accounting: the double-entry books, the approval-gated journal batch, and WIP.
 *
 *  SCALE-SEAM ㉘. **Grouped by what the methods ANSWER, and this slice is the strongest case yet for
 *  that rule** — because the group was in TWO non-contiguous places in `client.ts`. The GL/IIF export
 *  URLs and `createJournalBatch` sat ~700 lines above `journalEntries`, `trialBalance` and
 *  `contractorStatements`, with prequal, carbon and land screening in between. A prefix split would
 *  not have found them either: they span `/accounting`, `/wip` and `/wip/portfolio`, and
 *  `journalBatchExportUrl` builds a URL for the batch `createJournalBatch` creates, so splitting by
 *  route would separate a batch from its own export.
 *
 *  What they answer together is one question — **what do the books say?** Ten methods: the journal and
 *  trial balance that must tie, the contractor statements built on them, the batch that freezes them
 *  for export to QuickBooks, and the WIP schedule that is the same POC arithmetic seen per project and
 *  across the portfolio.
 *
 *  **`costTraceability` did NOT come**, though it sits immediately above the second cluster. It
 *  answers which cost codes trace to model elements — a takeoff question that happens to be adjacent.
 *  *Adjacency in a file is not a relationship*, the lesson ㉕ recorded about `MaterialEntry` and ㉗ met
 *  again with the two RFI methods.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withAccounting<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Accounting extends Base {
  accountingGlCsvUrl(pid: string) { return this.url(`/projects/${pid}/accounting/gl.csv`); }
  accountingIifUrl(pid: string) { return this.url(`/projects/${pid}/accounting/bills.iif`); }
  /** Freeze the current books into an approval-gated journal batch (draft → submit → approve → export). */
  createJournalBatch(pid: string, period: string, memo = "") {
    return this.json<{ id: string; ref: string; workflow_state: string; data: Record<string, unknown> }>(
      `/projects/${pid}/accounting/journal-batch`, { method: "POST", body: JSON.stringify({ period, memo }) });
  }
  /** Download URL for an APPROVED batch's frozen GL — fmt "gl" (CSV) or "iif" (QuickBooks). */
  journalBatchExportUrl(pid: string, batchId: string, fmt: "gl" | "iif" = "gl") {
    return this.url(`/projects/${pid}/accounting/journal-batch/${batchId}/export?fmt=${fmt}`);
  }

  /** Balanced double-entry journal from job cost + billing + the WIP POC adjustment. */
  journalEntries(pid: string) {
    return this.json<{ entries: { date: string; ref: string; memo: string; debit_total: number;
      credit_total: number; lines: { account: string; code: string; debit: number; credit: number }[] }[];
      debit_total: number; credit_total: number; balanced: boolean; note: string }>(
      `/projects/${pid}/accounting/journal-entries`);
  }
  /** The construction chart of accounts the journal posts against (code, name, type, normal balance). */
  chartOfAccounts(pid: string) {
    return this.json<{ accounts: { code: string; name: string; type: string; normal: string }[] }>(
      `/projects/${pid}/accounting/chart-of-accounts`);
  }
  /** Trial balance — debits and credits per account (must tie). */
  trialBalance(pid: string) {
    return this.json<{ accounts: { code: string; account: string; type: string; debit: number;
      credit: number; balance: number; balance_side: "debit" | "credit" }[];
      debit_total: number; credit_total: number; balanced: boolean; note: string }>(
      `/projects/${pid}/accounting/trial-balance`);
  }
  /** Contractor statements: POC income statement + contract-position (asset/liability, retainage, AP). */
  contractorStatements(pid: string) {
    return this.json<{ contract_value: number; percent_complete: number; backlog: number; note: string;
      income_statement: { revenue_earned: number; cost_of_revenue: number; gross_profit: number;
        gross_margin_pct: number; basis: string };
      contract_position: { contract_asset_underbillings: number; contract_liability_overbillings: number;
        retainage_receivable: number; accounts_payable: number; net_contract_working_capital: number } }>(
      `/projects/${pid}/contractor-statements`);
  }
  /** WIP schedule: POC → earned vs billed → over/under-billing, retainage, gross profit, backlog.
   *  `method`: "cost-to-cost" (default) or "units-installed" (physical model progress by GlobalId). */
  wip(pid: string, method: "cost-to-cost" | "units-installed" = "cost-to-cost") {
    return this.json<{ contract_value: number; estimated_cost: number; cost_to_date: number;
      cost_to_complete: number; percent_complete: number; pct_method: string; earned_revenue: number;
      billed_to_date: number; over_billing: number; under_billing: number;
      billing_status: "over-billed" | "under-billed" | "even";
      retainage: number; gross_profit: number; gross_margin_pct: number; profit_to_date: number;
      backlog: number; note: string;
      model?: { model_percent_complete: number; cost_percent_complete: number; divergence_pct: number;
        installed_elements: number; total_elements: number;
        flag: "cost-ahead" | "physical-ahead" | "aligned"; note: string };
    }>(`/projects/${pid}/wip?method=${encodeURIComponent(method)}`);
  }
  /** Physical % complete from the model: installed elements ÷ total by IFC GlobalId, optionally
   *  quantity-weighted. The independent "units-installed" signal that cross-checks cost-to-cost POC. */
  wipModelProgress(pid: string, quantity?: string) {
    const q = quantity ? `?quantity=${encodeURIComponent(quantity)}` : "";
    return this.json<{ available: boolean; method?: string; total_elements?: number;
      installed_elements?: number; percent_complete_count?: number; percent_complete?: number;
      quantity?: string; elements_with_quantity?: number; total_quantity?: number;
      installed_quantity?: number; percent_complete_quantity?: number; note: string
    }>(`/projects/${pid}/wip/model-progress${q}`);
  }
  /** Portfolio WIP: one row per project, worst cash position (largest under-billing) first. */
  wipPortfolio() {
    return this.json<{ projects: { id: string; name: string; contract_value: number; earned_revenue: number;
      billed_to_date: number; over_billing: number; under_billing: number; billing_status: string;
      percent_complete: number; gross_profit: number }[];
      totals: Record<string, number>; project_count: number; note: string }>(`/wip/portfolio`);
  }
  };
}
