/** FIN-GOV / FIN-INGEST — the locked reporting period, two-way reconciliation, and import lineage.
 *
 *  SCALE-SEAM ⑩ (targeted). Route-group `/projects/{pid}/finance`, taken out of `client.ts` by the
 *  route each method calls — the recipe ⑥ established.
 *
 *  **Not a sweep, and deliberately not one.** Measuring the residue of `client.ts` first showed 519
 *  methods across 191 route groups averaging 2.7 methods each — no coherent domain left worth a
 *  general extraction, and the largest remaining group would have moved 55 of 3,748 lines while
 *  moving the reachability ceiling by zero. That plan was dropped on those numbers.
 *
 *  This one is different because the ratchet asked for it by name. Giving `financeReconcile` the
 *  response shape it actually returns — instead of three `unknown[]` buckets that sent its first
 *  caller to read `fin_ingest.reconcile` — cost nine lines, and `client.ts` sat at exactly its
 *  `test_file_sizes.py` pin of 3,748. CI said `client.ts=3757 > 3748`. The file's own comment says
 *  the friction is the point and should force *"should this live in a domain module instead?"*, and
 *  for a four-method route group with a panel of its own the answer is yes. Pin 3,748 -> 3,726.
 *
 *  Reaches only `json` on `HttpCore`. A mixin, so every call site resolves unchanged;
 *  `api/surface.test.ts` proves a move is invisible to it and a loss is not.
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
  };
}
