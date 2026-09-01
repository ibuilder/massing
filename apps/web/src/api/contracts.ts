/** Contract documents, the scope-of-work clause library, and signing (typed, PAdES, 3rd-party).
 *
 *  SCALE-SEAM ⑨. Route-groups `/projects/{pid}/contracts/*`, `/scope-library` and `/esign`, taken out
 *  of `client.ts` by the route each method calls — the recipe ⑥ established and ⑦ repeated.
 *
 *  **This extraction was forced by the ratchet, which is the ratchet working.** `client.ts` sat at
 *  exactly its `test_file_sizes.py` pin of 3,780, and the check is `measured > cap`, so adding the
 *  one new method this feature needed (`scopeExhibit`) failed the build. The file's own comment says
 *  the friction is the point and that it should force the question *"should this live in a domain
 *  module instead?"* — and for contract documents the answer was plainly yes. Two other lanes hit the
 *  same wall the same day and routed their methods elsewhere; this one had a whole domain to take
 *  with it, so the pin moves DOWN rather than up.
 *
 *  **The section comment was again not the group.** `client.ts` had a
 *  `// --- contract documents (generate / scope library / sign) ---` header, and the run underneath it
 *  carried straight on into `e57Status` and `convertE57` — point-cloud conversion, route `/convert` —
 *  before returning to `esignStatus` and `sendForSignature`. Grouping by that comment would have
 *  dragged E57 across the seam. Grouped by route instead, so the two contract runs move and the E57
 *  pair stays exactly where it was.
 *
 *  Reaches only `json`, `url` and `authHeaders` on `HttpCore`; no private of `ApiClient` crosses the
 *  boundary, so nothing here needed the treatment ③'s `liveStream` did.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it: moving a
 *  method is invisible to it, losing one fails it by number.
 *
 *  SCALE-SEAM ㊹ adds owner selections / allowance vs actual — *what did the owner pick, and does
 *  it trigger a change order?* Share tokens sat immediately below in `client.ts` and did **not**
 *  come (client portal, not the contract).
 *
 *  SCALE-SEAM ❹ adds the change-order log — *what is the CO pipeline worth, and who holds the
 *  ball?* `actionTracker` sat immediately below and did **not** come.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withContracts<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class extends Base {
  /** URL of a generated contract document — doc = agreement | prime | co | exhibit. */
  contractDocUrl(pid: string, key: string, rid: string, doc: string, clauses?: string, attach = false) {
    const q = new URLSearchParams({ doc, ...(clauses ? { clauses } : {}), ...(attach ? { attach: "1" } : {}) }).toString();
    return this.url(`/projects/${pid}/contracts/${key}/${rid}/document.pdf?${q}`);
  }

  /** Exhibit A as an editable Word document — the copy a subcontractor redlines and sends back.
   *
   *  Same clause selection and merge context as `contractDocUrl(..., "exhibit")`; only the container
   *  differs. A separate path rather than a `?fmt=` on the PDF one, because the extension is what a
   *  browser, a mail client and a document-management system key on — a `.pdf` URL returning a Word
   *  file reaches a subcontractor as something their machine refuses to open. */
  exhibitDocxUrl(pid: string, key: string, rid: string, clauses?: string) {
    const q = new URLSearchParams(clauses ? { clauses } : {}).toString();
    return this.url(`/projects/${pid}/contracts/${key}/${rid}/exhibit.docx${q ? `?${q}` : ""}`);
  }
  /** Scope-of-work clause library for composing Exhibit A (ids + titles, no bodies).
   *
   * `trade` or `division` narrows the catalog. Pass one whenever the record has a trade: the library
   * carries 249 clauses across 21 MasterFormat divisions, and unnarrowed it asks somebody to pick a
   * plumbing subcontract out of a list where 95% of the entries belong to other trades. `trade`
   * resolves to a division server-side so the mapping stays in one place; an unrecognised trade
   * returns the whole catalog rather than an empty one.
   */
  scopeLibrary(opts: { trade?: string; division?: string } = {}) {
    const q = new URLSearchParams({ ...(opts.trade ? { trade: opts.trade } : {}),
                                    ...(opts.division ? { division: opts.division } : {}) }).toString();
    return this.json<{
      clauses: { id: string; category: string; title: string; trade?: string | null;
                 division?: string | null; default: boolean }[];
      division: string | null; division_name: string | null; divisions: string[];
      /** Which of the returned categories may go into Exhibit A. Filter the picker by THIS rather
       *  than by a client-side literal — a narrowed catalog still contains conditions clauses
       *  (`library()` matches division-or-None and every `gc-*`/`sc-*` has None), and the exhibit
       *  renderer drops them. A second copy of this rule is what caused the preview/PDF divergence. */
      exhibit_categories: string[];
    }>(`/scope-library${q ? `?${q}` : ""}`);
  }
  /** The assembled Exhibit A — numbered clauses WITH bodies, plus per-category counts.
   *
   * This is the read-only half of what `contractDocUrl(..., "exhibit", ids)` renders, and it exists so
   * a composer can show what it is about to produce before a PDF is generated and attached to a
   * record. Omitting `clauses` yields the server's default selection for the trade, which is the same
   * `default_ids` path the document uses — so the preview and the signed document come from one code
   * path rather than two that drift.
   */
  scopeExhibit(opts: { trade?: string; clauses?: string[] } = {}) {
    const q = new URLSearchParams({ ...(opts.trade ? { trade: opts.trade } : {}),
                                    ...(opts.clauses?.length ? { clauses: opts.clauses.join(",") } : {}) }).toString();
    return this.json<{
      trade: string | null; division: string | null; division_name: string | null;
      clauses: { id: string; category: string; title: string; body: string;
                 number: string; section: string }[];
      counts: Record<string, number>;
    }>(`/scope-library/exhibit${q ? `?${q}` : ""}`);
  }
  /** Record a party's signature (typed name) on a contract / change order. */
  signContract(pid: string, key: string, rid: string, party: string, name: string) {
    return this.json<{ signatures: { party: string; name: string; signed_at: string; method: string }[] }>(
      `/projects/${pid}/contracts/${key}/${rid}/sign`, { method: "POST", body: JSON.stringify({ party, name }) });
  }
  /** Apply a certificate-based PAdES digital signature to the contract document (tamper-evident). */
  digitalSignContract(pid: string, key: string, rid: string) {
    return this.json<{ signed: boolean; fingerprint: string; kind: string }>(
      `/projects/${pid}/contracts/${key}/${rid}/digital-sign`, { method: "POST", body: "{}" });
  }
  /** Digital-signature capability — built-in PAdES + the optional 3rd-party bridge (DocuSeal etc.). */
  esignStatus() {
    return this.json<{ pades: { available: boolean; kind: string };
      bridge: { enabled: boolean; provider: string | null; implemented: boolean; message: string } }>(
      `/esign/status`);
  }
  /** Route a contract/CO through the configured 3rd-party e-signature provider (DocuSeal etc.). */
  sendForSignature(pid: string, key: string, rid: string, signers: { email: string; name?: string; party?: string }[]) {
    return this.json<{ provider: string; submission_id: number | string | null;
      signers: { email: string; role: string; url: string | null }[]; status: string }>(
      `/projects/${pid}/contracts/${key}/${rid}/send-for-signature`,
      { method: "POST", body: JSON.stringify({ signers }) });
  }

  /** selectionsSummary — owner selections and allowances vs actual (change-order candidates). */
  selectionsSummary(pid: string) {
    type Cat = { category: string; count: number; allowance: number; actual: number; delta: number };
    type Cand = { ref: string; item: string; category: string; allowance: number; actual: number;
      delta: number; state: string; change_subject: string };
    return this.json<{
      count: number; priced: number; approved: number; total_allowance: number; total_actual: number;
      net_delta: number; direction: "over" | "under" | "on-allowance";
      over_count: number; under_count: number; on_count: number;
      by_category: Cat[]; co_candidate_count: number; co_candidates: Cand[]; note: string;
    }>(`/projects/${pid}/selections/summary`);
  }
  /** pushSelectionChangeEvents — push over-allowance selections into change events (idempotent). */
  pushSelectionChangeEvents(pid: string) {
    return this.json<{ created: number; skipped: number; created_refs: string[]; note: string }>(
      `/projects/${pid}/selections/push-change-events`, { method: "POST", body: "{}" });
  }

  /** coLog — CO value pipeline (pending/approved/executed), reason mix, schedule exposure. */
  coLog(pid: string) {
    return this.json<{ co_count: number; total_value: number; pending_value: number;
      approved_value: number; executed_value: number; total_schedule_days: number;
      change_events_open: number; change_event_rom_exposure: number;
      by_reason: Record<string, number>; ball_in_court: Record<string, number>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/change-orders/log`);
  }
  };
}
