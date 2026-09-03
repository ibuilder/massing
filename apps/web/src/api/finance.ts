/** Finance lock / ingest, plus the investor capital stack.
 *
 *  SCALE-SEAM ⑩ took `/projects/{pid}/finance` (lock, reconcile, imports) out of `client.ts`.
 *  SCALE-SEAM ㉙ adds the nine methods that answer *what do the investors own and get paid?* —
 *  cap table, waterfall, capital calls, distributions, investor statements, and the securities
 *  syndication package. `k1Pack` was already here (v0.3.1136); it is the same question from the
 *  accountant's side. They span `/cap-table`, `/waterfall`, `/capital-call`, `/distribution`,
 *  `/investors`, `/securities` and `/securities-syndication`, so a prefix split would have scattered
 *  them. Rent-roll and lease management sat immediately above the cluster in `client.ts` and did
 *  **not** come: those are property operations. *Adjacency in a file is not a relationship.*
 *
 *  Composed through the existing `withFinance` wrapper — no extra `withX()` on `ApiClient`
 *  (TS mixin depth). `api/surface.test.ts` proves a move is invisible to it and a loss is not.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withFinance<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class extends Base {
  /** FIN-GOV — the project's locked reporting period (books closed through lock_date, or null). */
  financeLock(pid: string) {
    return this.json<{ lock_date: string | null; set_by?: string; set_at?: string; note?: string }>(
      `/projects/${pid}/finance/lock`);
  }
  setFinanceLock(pid: string, lockDate: string | null, note?: string) {
    return this.json<{ lock_date: string | null; set_by: string; note: string }>(
      `/projects/${pid}/finance/lock`,
      { method: "PUT", body: JSON.stringify({ lock_date: lockDate, note: note ?? "" }) });
  }
  /** FIN-INGEST — budget ↔ actuals two-way reconciliation on the cost-code spine.
   *
   *  The three buckets were typed `unknown[]`, which meant the first caller had to go read
   *  `fin_ingest.reconcile` to render a row — so the type is now the shape the server actually
   *  returns. All three carry the same slim row; they differ only in which side had a value, and
   *  they are deliberately NOT netted against each other.
   */
  financeReconcile(pid: string) {
    type Row = { cost_code: string | null; budget: number | null; committed: number | null;
      actual: number | null; variance: number | null };
    return this.json<{ matched: Row[]; budget_only: Row[]; actuals_only: Row[];
      uncoded: { module: string; ref: string; amount: number; vendor?: string }[];
      counts: { matched: number; budget_only: number; actuals_only: number; uncoded: number };
      fully_reconciled: boolean }>(
      `/projects/${pid}/finance/reconcile`);
  }
  /** FIN-INGEST — import lineage: the project's audit-logged import batches, newest first. */
  financeImports(pid: string) {
    return this.json<{ ts: string | null; actor: string | null; module: string; filename: string;
      imported: number; error_count: number }[]>(`/projects/${pid}/finance/imports`);
  }

  /** Investor cap table — ownership by commitment + contributed/distributed totals. */
  capTable(pid: string) {
    return this.json<{ investor_count: number; total_commitment: number; total_contributed: number;
      total_distributed: number; total_unreturned: number; by_class: Record<string, number>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/cap-table`);
  }
  /** The syndication package — the cap table serialized to a neutral investor-platform schema. Always
   * available offline; this is the payload the capital-markets connector pushes. */
  securitiesPackage(pid: string) {
    return this.json<{ schema: string; project: string; fund: Record<string, unknown>;
      positions: Record<string, unknown>[]; disclosures: Record<string, unknown>; disclaimer: string }>(
      `/projects/${pid}/securities/package`);
  }
  /** Whether the capital-markets syndication bridge is configured. Ledger sync only — never moves money. */
  securitiesSyndicationStatus() {
    return this.json<{ enabled: boolean; target: string; implemented: boolean; moves_money: boolean;
      targets_supported: string[]; message: string }>(`/securities-syndication/status`);
  }
  /** Sync the cap table into the configured investor / digital-securities platform (positions only —
   * no funds move). 422 with an actionable message if the bridge isn't configured. */
  syndicateSecurities(pid: string) {
    return this.json<{ target: string; remote_id: string | null; positions_pushed: number;
      moves_money: boolean; status: string }>(
      `/projects/${pid}/securities/syndicate`, { method: "POST" });
  }
  /** Run a distribution / equity-waterfall scenario over the cap table (pref → RoC → promote tiers). */
  waterfallScenario(pid: string, body: { exit_amount?: number; contribution_date?: string;
    exit_date?: string; distributable?: number[]; dates?: string[]; pref_rate?: number;
    style?: string; clawback?: boolean } = {}) {
    return this.json<{ total_distributable: number; lp_distributions: number; gp_distributions: number;
      lp_irr: number | null; gp_irr: number | null; lp_equity_multiple: number; gp_equity_multiple: number;
      lp_unreturned: number; pref_rate: number; style: string; note?: string;
      periods: Record<string, unknown>[]; per_investor: Record<string, unknown>[] }>(
      `/projects/${pid}/waterfall`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Allocate a capital call (pro-rata by commitment). persist=true posts it to investor totals. */
  capitalCall(pid: string, amount: number, persist = false) {
    return this.json<{ kind: string; amount: number; persisted?: boolean; allocations: { investor: string; amount: number }[] }>(
      `/projects/${pid}/capital-call`, { method: "POST", body: JSON.stringify({ amount, persist }) });
  }
  /** Allocate a distribution (pro-rata by commitment). persist=true posts it to investor totals. */
  distribution(pid: string, amount: number, persist = false) {
    return this.json<{ kind: string; amount: number; persisted?: boolean; allocations: { investor: string; amount: number }[] }>(
      `/projects/${pid}/distribution`, { method: "POST", body: JSON.stringify({ amount, persist }) });
  }
  /** URL of a one-page investor capital-account statement PDF. */
  investorStatementUrl(pid: string, iid: string) {
    return this.url(`/projects/${pid}/investors/${iid}/statement.pdf`);
  }
  /** Mint a signed, expiring link to an investor's statement PDF (the no-login LP-portal share). */
  shareInvestorStatement(pid: string, iid: string, ttl?: number) {
    const q = ttl ? `?ttl=${ttl}` : "";
    return this.json<{ url: string; sig: string; exp: number; expires_in: number }>(
      `/projects/${pid}/investors/${iid}/share${q}`, { method: "POST" });
  }

  /** Capital-account movement an accountant needs for Schedule K-1 prep — not a tax document. */
  k1Pack(pid: string, period?: string) {
    const q = period ? `?period=${encodeURIComponent(period)}` : "";
    return this.json<{
      document_type: string; is_tax_document: boolean; project: string; period: string;
      investor_count: number;
      totals: { commitment: number; contributions_to_date: number;
        distributions_to_date: number; unreturned_capital: number };
      rows: { investor: string; ref: string; investor_class: string; entity_type: string | null;
        ownership_pct: number; commitment: number; contributions_to_date: number;
        distributions_to_date: number; net_capital_to_date: number; unreturned_capital: number;
        status: string | null }[];
      allocation_check: { ownership_pct_sum: number; residual: number; closes: boolean };
      not_included: string[]; note: string;
    }>(`/projects/${pid}/k1-pack${q}`);
  }
  };
}
