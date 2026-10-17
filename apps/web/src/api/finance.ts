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

/** CAPTABLE-PIPELINE — one investor row, as `capital.cap_table` builds it.
 *
 *  This was `Record<string, unknown>` — the OPAQUE bucket in
 *  `apps/web/src/api/deadFieldTyped.test.ts`, which names nothing, so every field the engine
 *  carefully computes per row was outside every audit built on these declarations AND outside the
 *  response-key gate. `proforma.ts` cast the rows to `any` and read four of them. */
export interface CapTableRow {
  id?: string;
  ref?: string;
  investor?: string;
  investor_class: string;
  entity_type?: string;
  commitment: number;
  /** Whether this row's commitment is inside `total_commitment`. Carried on the ROW rather than
   *  re-derived, deliberately — the engine's own note: "seven call sites read this table, and a
   *  rule re-derived seven times is a rule that disagrees with itself somewhere." */
  counts_toward_ownership: boolean;
  /** 0 for a row that does not count toward ownership — which is NOT the same as a committed
   *  investor who happens to hold nothing. */
  ownership_pct: number;
  contributed: number;
  distributed: number;
  unreturned: number;
  /** `prospect` · `committed` · `funded` · `exited`, from the investor register's workflow. */
  status?: string;
}

/** CAPTABLE-PIPELINE — `GET /projects/{pid}/cap-table`.
 *
 *  `total_commitment` is COMMITTED capital — the denominator ownership is computed against — and
 *  `pipeline_commitment` is the uncommitted interest beside it. Both were needed to reconcile the
 *  screen's own Commit column, and only the first was declared: measured at a column of $16,000,000
 *  under a total of $6,000,000. */
export interface CapTable {
  investor_count: number;
  total_commitment: number;
  /** Commitment from rows that do NOT count toward ownership. The engine keeps those rows visible
   *  at 0% rather than dropping them, so the column includes money the total excludes. */
  pipeline_commitment: number;
  /** Has anyone used the investor workflow on this project? Until somebody leaves the stamped
   *  initial `prospect` state it carries no information and EVERY row counts; once one has,
   *  `prospect` means "not committed" and the state is evidence. Without this a 0% row cannot be
   *  told from an artefact of nobody having run the workflow. */
  workflow_in_use: boolean;
  total_contributed: number;
  total_distributed: number;
  total_unreturned: number;
  by_class: Record<string, number>;
  rows: CapTableRow[];
}


/** One investor's slice of a waterfall scenario, with BOTH shares of it.
 *
 *  `distribution` is allocated pro-rata to `commitment_share`, and the waterfall above it may have
 *  run on contributed capital — so when the two shares disagree the figure rests on the basis the
 *  waterfall did not use. Both are published rather than one being chosen, because which share a
 *  distribution follows is an operating-agreement term and not an arithmetic fact. */
export interface WaterfallInvestor {
  id: string;
  investor: string;
  investor_class: string;
  commitment: number;
  contributed: number;
  distribution: number;
  commitment_share: number;
  /** `null` when nothing has been called on this investor's side — there is no contributed share to
   *  compare against, and substituting the commitment share would make the two look agreed. */
  contributed_share: number | null;
}

/** A distribution / equity-waterfall scenario over the cap table — **and the capital base it ran on.**
 *
 *  WF-BASIS declared the base. `distwaterfall.scenario` computes
 *  `lp_contrib = sum(contributed) or commitment`, and the pref accrues on that figure, the
 *  return-of-capital tier returns it, and both IRRs and both multiples are computed against it.
 *  Measured on an $8m LP / $2m GP cap table at a $20m exit:
 *
 *  | cap table | LP distributions | LP IRR | GP |
 *  |---|---|---|---|
 *  | nothing contributed | $18,302,056 | 17.99% | $1,697,944 |
 *  | fully contributed | **identical** | **identical** | **identical** |
 *  | half contributed | $17,151,028 | **33.78%** | **$2,848,972** |
 *
 *  So the screen could not tell a deal nobody has funded from one fully funded, and the two sides
 *  fall back independently — a cap table where the LPs have funded and the GP has not produces one
 *  waterfall on two bases. `lp_basis`/`gp_basis` say which. */
export interface WaterfallScenario {
  total_distributable: number;
  lp_distributions: number;
  gp_distributions: number;
  lp_irr: number | null;
  gp_irr: number | null;
  lp_equity_multiple: number;
  gp_equity_multiple: number;
  lp_unreturned: number;
  pref_rate: number;
  style: string;
  note?: string;
  periods: Record<string, unknown>[];
  per_investor: WaterfallInvestor[];
  /** The capital base the pref, the return of capital and both returns were computed on.
   *  `"contributed"` or `"committed"`; `null` when there is no cap table and no waterfall ran. */
  lp_basis?: "contributed" | "committed" | null;
  gp_basis?: "contributed" | "committed" | null;
  lp_contrib?: number;
  gp_contrib?: number;
  lp_commitment?: number;
  gp_commitment?: number;
  /** How `per_investor[].distribution` was allocated — `"commitment"`. Published because it can
   *  differ from the basis the waterfall itself ran on. */
  split_basis?: string;
  /** Investors whose contributed share differs from their commitment share. Non-empty means every
   *  `distribution` above rests on the share the waterfall did not use. */
  split_mismatch?: { investor: string; commitment_share: number;
                     contributed_share: number | null }[];
}

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
      /** `bool(matched) and not actuals_only and not uncoded` — it REQUIRES that something
       *  reconciled. It used to be the absence of the two problem lists alone, which is true of a
       *  project that has never recorded a cost. */
      fully_reconciled: boolean;
      /** Why `fully_reconciled` is false, when it is false for want of a cost rather than for a
       *  finding. Declared so a derivation over declarations can see it — the two Falses are the
       *  same value and mean opposite things. */
      nothing_reconciled_yet: boolean }>(
      `/projects/${pid}/finance/reconcile`);
  }
  /** FIN-INGEST — import lineage: the project's audit-logged import batches, newest first.
   *
   *  An ENVELOPE, not a bare array: `import_total` is how many batches there are, `import_count`
   *  how many this window holds. They differ only when `truncated`, and a caller that shows one
   *  while meaning the other is why both are here. */
  financeImports(pid: string) {
    return this.json<{ imports: { ts: string | null; actor: string | null; module: string;
      filename: string; imported: number; error_count: number }[];
      import_count: number; import_total: number; truncated: boolean }>(
      `/projects/${pid}/finance/imports`);
  }

  /** Investor cap table — ownership by commitment + contributed/distributed totals. */
  capTable(pid: string) {
    return this.json<CapTable>(`/projects/${pid}/cap-table`);
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
    return this.json<WaterfallScenario>(
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
