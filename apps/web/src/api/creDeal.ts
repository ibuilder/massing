/** The CRE deal desk — *should we transact on this income property, and on what terms?*
 *
 *  SCALE-SEAM (91), thirteen methods lifted out of `client.ts` as one contiguous run.
 *
 *  ### Why these thirteen, and why nothing else
 *
 *  Three independent signals were derived and they agree, which is more than any slice in this
 *  sequence has had before:
 *
 *  1. **The source marks them itself.** Ten doc comments carry a `CRE-` code — `CRE-HOLDSELL`,
 *     `CRE-CLAUSE` (twice), `CRE-COVENANT`, `CRE-AUTHORITY`, `CRE-SUPPLY`, `CRE-DECISION-GATE`,
 *     `CRE-COMP-TIER`, `CRE-T12`, `CRE-RRSCRUB`, `CRE-NER`. Grepped across the whole of
 *     `apps/web/src`: those eleven occurrences were the ONLY ones, and every one of them was in
 *     `client.ts`. *(Re-run today the grep also finds this header and two notes left in
 *     `client.ts`, so count only the ones on method doc comments — `sed -n '/^import/,$p'` on this
 *     file gives the eleven.)* The other three methods here are the write halves of two read/write pairs
 *     (`saveClausePlaybook`, `saveDealAuthority`) and `reviewContractClauses`, which shares
 *     `CRE-CLAUSE` with the playbook it scores against.
 *  2. **A 1:1 router match.** Every route these thirteen call — eleven distinct paths, since the
 *     playbook and the authority table each have a read and a write half on one path — is served by
 *     `services/api/src/aec_api/routers/realestate.py` and by no other router. Its ten `(R20)`
 *     docstrings name the same ten codes — checked by pairing each `@router.` line with the `def`
 *     beneath it, not by reading the file top to bottom.
 *  3. **They answer one question.** Verify the seller's numbers (`normalizeT12` — the tie-out is a
 *     gate, `rentRollScrub` — a check without its inputs reports not-run, `netEffectiveRent`,
 *     `tieredComps` — a band reports the weakest tier it rests on, `competitiveSupply`), decide
 *     (`holdSell`, `decisionGate`), and set the terms (`clausePlaybook` + `reviewContractClauses`,
 *     `loanCovenants`, `dealAuthority`). Diligence, decision, terms — one transaction.
 *
 *  A marker alone would not have been enough. This sequence has been trapped four times by a
 *  shared word (entitlements, view, carbon, lifecycle), so the `CRE-` prefix is treated as one
 *  vote among three, and the router match is the one that carries the weight.
 *
 *  ### The boundary that decides `rent-roll`
 *
 *  `proforma.ts` already holds `GET /projects/{pid}/rent-roll`, and two methods here sit directly
 *  underneath it on `/rent-roll/scrub` and `/rent-roll/net-effective`. A route-prefix split would
 *  put all three in one file; the boundary is what they answer, and the backend states it. The
 *  plain rent roll carries **no** `CRE-` code and **no** `(R20)`, and its own docstring calls it
 *  the operating rent roll "from the `lease` module (**the hold phase**)". These two take the
 *  counterparty's figures — `rentRollScrub` and `normalizeT12` both POST a body of numbers
 *  somebody else supplied — and report whether they survive scrutiny. *What are we earning* and
 *  *is their number true* are different questions that happen to share a prefix.
 *
 *  ### A forecast that was checked and did not hold
 *
 *  SCALE-SEAM (88) left `camReconciliation` in `client.ts` with a note saying it "goes with
 *  `rentRollScrub`, `netEffectiveRent` and `normalizeT12`, still below, when a rent-roll slice
 *  takes them". This is that slice, and it did **not** take it. All three signals point the other
 *  way: no `CRE-` code, no `(R20)`, and `/projects/{pid}/cam/reconciliation` is served by
 *  `operations.py`, not `realestate.py`. Reading it settles it — a CAM true-up bills a **completed
 *  operating year** to sitting tenants, which is running the asset, not buying it.
 *
 *  So `camReconciliation` stays in `client.ts`, still unfiled, and (88)'s note above it has been
 *  corrected to say what was measured. **A placement forecast written by one slice is a hypothesis
 *  for the next slice to test, not an instruction to carry out** — and this one was wrong while
 *  reading as settled, because it was phrased as a plan rather than as a claim with evidence.

 *  ### A fourth corroboration, found by accident
 *
 *  The backend suite names this family too, and it partitions the same thirteen: `test_cre_deal_desk`
 *  (comps/tiered, rent-roll/scrub, t12/normalize), `test_cre_governance` (deal-room/authority,
 *  decision-gate, loan/covenants, supply/competitive), `test_cre_tier3` (contracts/playbook,
 *  contracts/review, hold-sell) and `test_net_effective` (rent-roll/net-effective). That is all
 *  eleven paths, and no `test_cre_*` file reaches a route outside this set.
 *
 *  *Caveats, because this was found late and is the kind of evidence it is tempting to round up.*
 *  `test_cre_tier3` reaches THREE routes outside the set — `POST /proforma/scenarios`,
 *  `POST /proforma/scenarios/{sid}/review` and `GET /projects/{pid}/reports/ic_memo.pdf` — and
 *  `test_net_effective` sets up through `/rent-roll` and `/modules/lease`. A test may use a
 *  neighbour as a fixture without that neighbour belonging to the cluster, but the count has to be
 *  right: **this said "also exercises `/reports/ic`", naming one of the three and truncating its
 *  path.** Caught in review of #408. The claim above is therefore "no `test_cre_*` file reaches a
 *  route outside the set" only for the routes those tests ASSERT ON, not for their fixtures — which
 *  is a weaker statement than the first draft made, and the true one.
 *
 *  It was noticed only because `test_cre_deal_desk` and `test_cre_governance` scrolled past in the
 *  suite output *after* the slice was already committed. **Test-file names are a grouping somebody
 *  else authored, which is exactly the kind of source (87) said to prefer — and it was not on the
 *  list of places this slice thought to look.** It is recorded as a fourth signal rather than folded
 *  into the three, so the derivation stays honest about when each piece arrived.
 *
 *  ### What actually holds the no-behaviour-change claim
 *
 *  A mixin, so every call site resolves unchanged — and `api/surface.test.ts` now proves that for
 *  these thirteen BY NAME, which it did not when this file was first written. That sentence used to
 *  read "`api/surface.test.ts` is what proves that" full stop, and it was overstated: that file
 *  spot-checks a name list none of these was on, plus a floor of 751 on the total surface. **The
 *  surface measured 788.** Losing one of these thirteen would have left 787 and passed; losing the
 *  whole mixin would have left 775 and passed. The count guarded nothing here, which is exactly the
 *  slack `surface.test.ts`'s own comment at the 696 floor predicted would accumulate.
 *
 *  So all thirteen are named there now, on the same reasoning that file already gives for naming the
 *  twenty auth methods. Mutation-checked in both directions: renaming `holdSell` fails with
 *  *"holdSell() vanished — a call site is now broken"*, and restoring it passes.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withCreDeal<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class CreDeal extends Base {
  /** CRE-HOLDSELL — hold vs sell: incremental hold-year IRRs against the proceeds declined today. */
  holdSell(pid: string, inputs: unknown, hurdleRate = 0.12, maxYears = 10) {
    return this.json<{ computable: boolean; reason?: string;
      sell_now: { gross_sale: number; selling_costs: number; loan_payoff: number;
        net_proceeds: number; exit_cap: number };
      hurdle_rate: number; assumptions: Record<string, number>;
      years: { hold_years: number; exit_cap: number; noi_at_exit: number;
        net_proceeds_at_exit: number; incremental_irr: number | null; beats_hurdle: boolean }[];
      breakeven_hold_years: number | null; recommendation: "hold" | "sell";
      best_year: unknown; note: string }>(
      `/projects/${pid}/hold-sell`,
      { method: "POST", body: JSON.stringify({ inputs, hurdle_rate: hurdleRate,
                                               max_years: maxYears }) });
  }
  /** CRE-CLAUSE — the clause-position playbook (a clause with no red line is not a standard). */
  clausePlaybook(pid: string) {
    return this.json<{ playbook: Record<string, { clause: string; severity: string; accept: string;
      negotiate: string; refuse: string; fallback: string }[]>;
      starter: unknown[]; positions: string[] }>(`/projects/${pid}/contracts/playbook`);
  }
  saveClausePlaybook(pid: string, playbook: unknown) {
    return this.json<{ playbook: unknown }>(`/projects/${pid}/contracts/playbook`,
      { method: "PUT", body: JSON.stringify({ playbook }) });
  }
  /** CRE-CLAUSE — record a review against the PLAYBOOK (distinct from the AI `reviewContract`
   *  above: this one takes findings a human already made and scores them against the standard).
   *  Unreviewed playbook clauses come back as open risk. */
  reviewContractClauses(pid: string, contractType: string, findings: unknown[], document = "") {
    return this.json<{ verdict: string; document: string | null; reason?: string;
      available_types?: string[];
      clauses: { clause: string; severity: string; position: string; deviation: boolean;
        note: string | null; reference: string | null; red_line: string }[];
      deviations: unknown[]; negotiable: unknown[];
      not_reviewed: { clause: string; severity: string }[]; unknown_clauses: string[];
      counts: Record<string, number>; note: string }>(
      `/projects/${pid}/contracts/review`,
      { method: "POST", body: JSON.stringify({ contract_type: contractType, findings, document }) });
  }
  /** CRE-COVENANT — the loan covenant + reporting register (day-count basis, clock start). */
  loanCovenants(pid: string, loan: unknown, actuals?: Record<string, number>) {
    return this.json<{ loan: { name: string; lender: string }; at_risk: boolean;
      summary: Record<string, number>;
      reporting: { obligations: { name: string; computable: boolean; due_date?: string;
        day_basis?: string; clock_start?: string; anchor_source?: string; status?: string;
        risk?: string; days_remaining?: number; clock_start_matters?: boolean;
        alternate_reading?: { due_date: string; days_difference: number; warning: string } }[];
        upcoming: unknown[]; overdue: unknown[]; not_computable: { name: string; reason: string }[];
        counts: Record<string, number> };
      financial: { covenants: { name: string; tested: boolean; passing?: boolean; status?: string;
        headroom?: number; cure_ends?: string | null; reason?: string }[];
        untested: { name: string; reason: string }[]; counts: Record<string, number>;
        clean: boolean } }>(
      `/projects/${pid}/loan/covenants`,
      { method: "POST", body: JSON.stringify({ loan, actuals }) });
  }
  /** CRE-AUTHORITY — the deal-room authority table; required gaps BLOCK downstream analysis. */
  dealAuthority(pid: string) {
    return this.json<{ table: { fact_type: string; label: string; document: string; as_of: string;
      age_days: number | null; freshness_days: number; fresh: boolean; required: boolean }[];
      missing: { fact_type: string; label: string }[];
      stale: { fact_type: string; days_over: number }[];
      superseded_still_active: { fact_type: string; document: string; issue: string }[];
      gate: { passes: boolean; blocking: { fact_type: string; why: string }[]; advisory: unknown[] };
      counts: Record<string, number>; note: string }>(`/projects/${pid}/deal-room/authority`);
  }
  saveDealAuthority(pid: string, entries: unknown[]) {
    return this.json<{ entries: unknown[]; assessment: { gate: { passes: boolean } } }>(
      `/projects/${pid}/deal-room/authority`,
      { method: "PUT", body: JSON.stringify({ entries }) });
  }
  /** CRE-SUPPLY — competitive supply weighted by recorded evidence, not by status label. */
  competitiveSupply(pid: string, body: { projects: unknown[]; window_start?: string;
                                         window_end?: string; product_type?: string;
                                         monthly_absorption?: number }) {
    return this.json<Record<string, unknown>>(
      `/projects/${pid}/supply/competitive`, { method: "POST", body: JSON.stringify(body) });
  }
  /** CRE-DECISION-GATE — the pre-committee gate; a gate without evidence is unknown, and blocks. */
  decisionGate(pid: string, evidence: unknown, requiredExhibits?: string[], minCoverage?: number) {
    return this.json<{ verdict: "ready" | "blocked"; ready: boolean;
      gates: { gate: string; label: string; status: "pass" | "fail" | "unknown"; detail: string;
        action: string }[];
      blocking: { gate: string; status: string; detail: string }[];
      actions: { gate: string; action: string }[];
      counts: Record<string, number>; note: string }>(
      `/projects/${pid}/decision-gate`,
      { method: "POST", body: JSON.stringify({ evidence, required_exhibits: requiredExhibits,
                                               min_coverage: minCoverage ?? 0.9 }) });
  }
  /** CRE-COMP-TIER — comps ranked by source tier; bands report the weakest tier they rest on. */
  tieredComps(pid: string, field = "price_psf") {
    return this.json<{ comp_count: number; conflict_count: number;
      comps: { tier: string; label: string; rank: number; address: string; source: string;
        price_psf: number | null; cap_rate: number | null }[];
      conflicts: { address: string; kept_tier: string;
        outranked: { tier: string; source: string }[];
        value_deltas: { field: string; kept: number; outranked: number }[] }[];
      statistics: Record<string, { n: number; median: number | null; p25?: number; p75?: number;
        worst_tier: string | null; worst_tier_label?: string; best_tier?: string;
        tier_counts?: Record<string, number>; unattributed?: number; note?: string }>;
      note: string }>(`/projects/${pid}/comps/tiered?field=${encodeURIComponent(field)}`);
  }
  /** CRE-T12 — normalize a trailing-twelve to the house chart; the tie-out is a GATE, not a report. */
  normalizeT12(pid: string, t12: unknown, units?: number) {
    return this.json<{ line_count: number; source_totals: Record<string, number>;
      mapped_totals: Record<string, number>;
      tie_out: { reconciles: boolean; deltas: Record<string, number>; tolerance: number };
      stopped?: boolean; adjusted_noi: number | null;
      reconciling_items?: { issue: string; description?: string; amount?: number }[];
      unmapped_count: number; unmapped: { description: string; amount: number }[];
      one_time_items?: { description: string; amount: number; kind: string }[];
      capital_items?: { description: string; amount: number }[];
      by_category?: { category: string; label: string; amount: number; run_rate: number }[];
      run_rate_vs_trailing?: { category: string; trailing: number; run_rate: number; delta: number }[];
      add_back_questions?: { check: string; severity: string; finding: string; question: string }[];
      note: string }>(
      `/projects/${pid}/t12/normalize`, { method: "POST", body: JSON.stringify({ t12, units }) });
  }
  /** CRE-RRSCRUB — rent roll vs income; a check without its inputs reports not-run, never a pass. */
  rentRollScrub(pid: string, income?: unknown, units?: unknown[]) {
    return this.json<{ lease_count: number; excluded_not_active: number; clean: boolean;
      counts: { total: number; ran: number; not_applicable: number; passed: number; failed: number };
      checks: { check: string; applicable: boolean; passed?: boolean; severity?: string;
        finding: string; needs?: string }[];
      findings: { check: string; severity: string; finding: string }[];
      coverage_note: string }>(
      `/projects/${pid}/rent-roll/scrub`, { method: "POST", body: JSON.stringify({ income, units }) });
  }
  /** CRE-NER — net effective rent: the rent roll after concessions (straight-line + discounted). */
  netEffectiveRent(pid: string, opts: { discountRate?: number; lcPct?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.discountRate !== undefined) q.set("discount_rate", String(opts.discountRate));
    if (opts.lcPct !== undefined) q.set("lc_pct", String(opts.lcPct));
    const qs = q.toString();
    return this.json<{ lease_count: number; skipped_count: number; excluded_not_active: number;
      face_gpr_annual: number; ner_gpr_annual_discounted: number;
      ner_gpr_annual_straight_line: number; concession_total_term: number;
      concession_load_pct: number; face_to_ner_delta_annual: number;
      face_to_ner_delta_pct: number; lc_included: boolean; discount_rate: number;
      skipped: { tenant: string; suite: string; reason: string }[];
      leases: { tenant: string; suite: string; face_rent_annual: number;
        ner_annual_discounted: number; ner_psf_discounted: number | null;
        concession_load_pct: number }[]; note: string }>(
      `/projects/${pid}/rent-roll/net-effective${qs ? `?${qs}` : ""}`);
  }
  };
}
