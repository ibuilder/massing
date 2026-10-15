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
 *
 *  SCALE-SEAM ❸ adds the submittal stack — *are required submittals turning around?*
 *  Register, spec-section log, extract-from-text. They were **not** contiguous (health,
 *  closeout, safety, field-log and the RFI register sat between). Those did **not** come.
 *
 *  SCALE-SEAM ❽ adds bidding coverage — *can we cover the bid?* ITB tracking, model-QTO
 *  scope-gap, invite list. `e57Status` sat below and did **not** come.
 */
import { HttpCore } from "./httpCore";
import type { BidLevelingDetail, SpecSubmittalLog } from "./types";

type Ctor<T> = new (...args: any[]) => T;

/** One NCS discipline in the model takeoff, with the classes behind its tally. */
export interface ScopeGapDiscipline {
  discipline: string;
  element_count: number;
  classes: { ifc_class: string; count: number }[];
}

/** SCOPE-GAP (R14) — does every element in the model land in someone's bid package?
 *
 *  **Four states, not two**, and the consumer read two. `scope_gap.analyze`'s own note:
 *
 *  > Gaps = disciplines present in the model with no covering package — their quantities aren't in
 *  > any bid. `covered_without_specs` flags disciplines covered by a package that cites no CSI spec
 *  > section (thin, non-traceable coverage).
 *
 *  Coverage is matched at the DISCIPLINE level, so "covered" means a package claimed the discipline
 *  — not that anybody wrote down which spec sections they were pricing. The fourth state is the
 *  engine refusing to call that coverage, and the card printed a green tick over it.
 *
 *  The module's own docstring enumerates three of the four outputs and never mentions the thin one,
 *  the same shape as `EntitlementConditions.status` listing three of its four values. *A list that
 *  stopped being extended reads exactly like a complete one.* */
export interface ScopeGapResult {
  package_count: number;
  element_count: number;
  /** Elements whose discipline a package CLAIMS, over all elements. Discipline-level: a 100% here
   *  is compatible with every package citing no spec section at all. */
  covered_pct: number;
  gap_element_count: number;
  covered: (ScopeGapDiscipline & {
    packages: string[];
    /** The CSI sections the covering packages cite for this discipline. Empty means the coverage is
     *  a claim with no traceability, and this discipline then also appears in
     *  `covered_without_specs`. Undeclared until SCOPE-THIN — the ROOT `spec_sections` was in the
     *  undeclared-key list and this nested one was invisible to it. */
    spec_sections?: string[];
  })[];
  /** Disciplines in the model that NO package claims — quantities in nobody's bid. GUIDs so the
   *  viewer can highlight them; an IFC GlobalId is the only identity that survives a reload. */
  gaps: (ScopeGapDiscipline & { sample_guids: string[] })[];
  /** THE FOURTH STATE: covered by discipline, by a package citing no CSI spec section. Not a gap —
   *  somebody is pricing it — and not traceable coverage either. */
  covered_without_specs?: {
    discipline: string;
    packages: string[];
    element_count: number;
    sample_guids: string[];
  }[];
  /** Every CSI section cited by any package, across the project. */
  spec_sections?: string[];
  /** `0` is the measurable signal that no package on this job cites a section at all. */
  spec_section_count?: number;
  /** Packages whose discipline has no model elements — over-scoped, nothing to price. */
  packages_without_model_scope: string[];
  note: string;
}

export function withProcurement<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Procurement extends Base {
  /** PROCURE-LEVEL: group QTO line items into buyout packages (each with an RFQ scope to send out). */
  buyoutPackages(pid: string, qtoLines: Record<string, unknown>[], by = "trade") {
    type Pkg = {
      package: string; line_count: number; est_cost: number;
      rfq_scope: { item: string; qty: number | null; unit: string }[];
      lines: { item: string; qty: number | null; unit: string; unit_price: number | null }[];
    };
    // TOTAL-EXCLUDED — `skipped_unidentifiable` was returned by `procurement.buyout_packages` and
    // declared NOWHERE in this client, so every unread-field audit that starts from these
    // declarations was blind to it by construction (the hole `excluded_comparables` fell through).
    // The engine counts it deliberately: *"a caller seeing \"0 packages\" deserves to know lines were
    // discarded, not conclude there is no scope."*
    return this.json<{ grouped_by: string; package_count: number; total_est_cost: number;
      skipped_unidentifiable: number; packages: Pkg[]; note: string }>(
      `/projects/${pid}/procurement/buyout-packages`, { method: "POST", body: JSON.stringify({ qto_lines: qtoLines, by }) });
  }
  /**
   * BUYOUT-KEEP — the write that turns a grouping into records somebody can work.
   *
   * `buyoutPackages` above computes the same grouping and returns it; this one PERSISTS each group
   * as a `procurement_package` record in `draft`, which is what makes the buyout workflow
   * (draft → rfq_sent → quotes_in → awarded) reachable at all. Until 2026-09-11 the screen could
   * compute packages and had no way to keep them, so the entire downstream chain — this route and
   * `sendPackageRfq` below — was unreachable from the product.
   *
   * Needs the **editor** role, because it writes records the whole project then sees.
   */
  saveBuyoutPackages(pid: string, qtoLines: Record<string, unknown>[], by = "trade",
                     rfqDue?: string) {
    return this.json<{
      created: { id: string | number; ref: string; name: string; est_cost: number | null;
                 line_count: number }[];
      package_count: number;
      note: string;
    }>(`/projects/${pid}/procurement/packages/save`, {
      method: "POST",
      body: JSON.stringify({ qto_lines: qtoLines, by, ...(rfqDue ? { rfq_due: rfqDue } : {}) }),
    });
  }

  /**
   * BUYOUT-KEEP — mint a Bid Solicitation (ITB) from a stored package and advance it to `rfq_sent`.
   *
   * **`package_state` is the field that matters on the way back.** The server mints the
   * solicitation unconditionally but only transitions a package that is still in `draft`; sending
   * twice therefore produces a SECOND ITB and no state change. A client that reports "RFQ sent"
   * from a resolved promise would hide exactly that, so the caller must read the state it returns
   * rather than the fact that it returned.
   */
  sendPackageRfq(pid: string, rid: string, dueDate?: string) {
    return this.json<{
      solicitation: { id: string | number; ref: string };
      package: string;
      package_state: string | null;
    }>(`/projects/${pid}/procurement/packages/${encodeURIComponent(rid)}/send-rfq`, {
      method: "POST",
      body: JSON.stringify(dueDate ? { due_date: dueDate } : {}),
    });
  }

  /**
   * PROCURE-LEVEL — score returned quotes for ONE package against its RFQ scope.
   *
   * `scope` and `quotes` are typed to the shapes the route documents rather than to
   * `Record<string, unknown>[]`. The vague version compiled and told a caller nothing: the engine
   * reads `item`/`qty`/`unit` off the scope and `supplier`/`lines[]` off each quote, so a caller
   * shipping `{name, quantity}` would have typechecked and then scored every supplier at zero
   * coverage. `lead_time_days` is optional because the engine folds its weight into price and
   * coverage when no lead times are supplied.
   */
  procurementLevel(pid: string,
                   scope: { item: string; qty: number; unit: string }[],
                   quotes: { supplier: string; lead_time_days?: number;
                             lines: { item: string; qty: number; unit: string; unit_price: number }[] }[],
                   weights?: Record<string, number>) {
    type Supplier = {
      supplier: string;
      /**
       * A FRACTION 0..1, NOT a percentage, despite the name. `score_quotes` returns
       * `covered / scope` and folds it straight into the composite score. The first consumer this
       * field ever had trusted the name and rendered `0.6667%` for a supplier who had priced two
       * thirds of the scope — and made the shortfall warning fire on every complete bid too.
       * Multiply by 100 before display; compare against 1, not 100.
       */
      coverage_pct: number;
      covered_lines: number; scope_lines: number;
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
    return this.json<{ within_days: number;
      /** PREQUAL-LAPSE: the horizon actually used. `within_days` was accepted, clamped to 1–365 by
       *  its route, echoed, and used for nothing — the windows were a literal 30 inside the COI
       *  branch, so a caller asking for 7 days got a 30-day answer labelled 7. */
      warn_days: number; vendors_flagged: number;
      vendors: { vendor: string; issues: string[]; can_bid: boolean; can_bill: boolean }[];
      note: string }>(`/projects/${pid}/procurement/compliance-feed`);
  }
  /** One vendor's bid/bill readiness.
   *
   *  PREQUAL-LAPSE. `coi.expiring_soon` was computed on every call and declared on none, so the
   *  one warning this gate DID produce could not reach a screen; `prequal` carried a status and no
   *  date at all, so an approval dying in ten days read `can_bid: true · prequal approved`. The
   *  blockers/warnings split is the state this response had no way to express — a document still
   *  valid today is not a blocker, and that is exactly why the verdict alone is not enough.
   */
  procurementGate(pid: string, vendor: string) {
    return this.json<{ vendor: string;
      /** `expiring_soon` is present on every branch, `missing` included — an absent key is falsy
       *  and reads as "not expiring soon" when the truth is "there is nothing to expire". */
      coi: { status: string; expires: string | null; expiring_soon: boolean };
      /** An approved prequalification has no transition out of `approved`, so `expires` is the
       *  only thing that ends it. `expiring_soon` is false once it already has — that is a
       *  blocker, and "expiring soon" is only said about something currently valid. */
      prequal: { status: string; expires: string | null; expiring_soon: boolean };
      subcontract: { executed: boolean }; waiver_on_file: boolean;
      can_bid: boolean; bid_blockers: string[]; can_bill: boolean; bill_blockers: string[];
      /** Documents still valid that lapse within `warn_days`. Never a reason to refuse today. */
      bid_warnings: string[]; bill_warnings: string[]; warn_days: number; note: string }>(
      `/projects/${pid}/procurement/gate?vendor=${encodeURIComponent(vendor)}`);
  }
  // --- materials procure-to-pay (FieldMaterials) -----------------------------
  /** Whether RFQ dispatch to suppliers is configured (quote leveling still works either way). */
  rfqStatus() {
    return this.json<{ enabled: boolean; provider: string | null; message: string }>(
      `/procurement/rfq-status`);
  }
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

  /** submittalRegister — spec-section turnaround, ball-in-court, overdue. */
  submittalRegister(pid: string) {
    return this.json<{ submittal_count: number; open_count: number; overdue_count: number;
      avg_turnaround_days: number | null; by_section: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/submittals/register`);
  }
  /** specSubmittalLog — required submittals per spec section vs logged, with missing gaps. */
  specSubmittalLog(pid: string) {
    return this.json<SpecSubmittalLog>(`/projects/${pid}/specs/submittal-log`);
  }
  /** extractSubmittals — typed submittal list from pasted spec text (AI when configured; rules fallback). */
  extractSubmittals(pid: string, text: string, create = false) {
    return this.json<{ items: { section_number?: string; title: string; type: string }[];
      source: string; message?: string; created_submittals?: number }>(
      `/projects/${pid}/specs/extract-submittals`, { method: "POST", body: JSON.stringify({ text, create }) });
  }

  /** itb — invited vs responded vs bonded per package, plus coverage gaps. */
  itb(pid: string) {
    return this.json<{ package_count: number; total_invited: number; total_responses: number;
      packages_without_bids: number; rows: Record<string, unknown>[] }>(`/projects/${pid}/bidding/itb`);
  }
  /** scopeGap — model-QTO coverage vs bid packages: covered disciplines, gaps, over-scoped packages,
   *  **and the coverage the engine refuses to call coverage.**
   *
   *  SCOPE-THIN declared the fourth state. `scope_gap.analyze` matches an element's NCS discipline
   *  to a package that CLAIMS that discipline, and flags separately — in its own words — *"a claim
   *  with no CSI traceability"*: a discipline covered by a package citing no spec section at all.
   *  `covered_without_specs`, `spec_sections` and `spec_section_count` were all undeclared, and the
   *  only screen that calls this printed **"✅ Every model discipline is covered by a bid package"**
   *  whenever `gaps` was empty — including when every one of those packages cited nothing.
   *
   *  `spec_sections` on a `covered` entry was undeclared too, which is the same root-only blind spot
   *  `apps/web/src/api/responseUndeclared.test.ts` has: the root `spec_sections` was in its gap list
   *  and the per-discipline one, nested, was not. */
  scopeGap(pid: string) {
    return this.json<ScopeGapResult>(`/projects/${pid}/bidding/scope-gap`);
  }
  /** inviteBidders — record companies invited to bid on a package. */
  inviteBidders(pid: string, packageId: string, companies: string[]) {
    // `package` echoes the `packageId` this call passed in, so it tells the caller nothing it does
    // not already hold. Declared anyway: an undeclared key is invisible to the compiler and to every
    // audit built on these interfaces, and "redundant" is a judgement that has to be written down
    // somewhere a reader can find it rather than inferred from a type's silence.
    return this.json<{ package: string; bidders_invited: number; invited_companies: string[] }>(
      `/projects/${pid}/bidding/packages/${packageId}/invite`,
      { method: "POST", body: JSON.stringify({ companies }) });
  }

  // SCALE-SEAM ⓽ — *how do these bids compare, in detail?* The detail view of the levelling
  // `procurementLevel` and `procurementLevelQuotes` already answer; this file's own header has
  // claimed "bid levelling" since ⑥ while the method sat in `client.ts` under an AI banner.
  /** Deep bid leveling for one package: base stats, scope matrix, gaps, scope-adjusted recommendation. */
  bidLevelingDetail(pid: string, packageId: string) {
    return this.json<BidLevelingDetail>(`/projects/${pid}/bids/leveling/${packageId}`);
  }

  // --- The levelling SUMMARY its detail belongs to ---
  /** Bid leveling — submissions tabulated by package with low/high/avg/spread. */
  bidLeveling(pid: string) {
    return this.json<{ package_count: number; bid_count: number; packages: { package: string; bid_count: number; low: number | null; high: number | null; avg: number | null; spread: number; bids: { bidder: string | null; amount: number | null; is_low: boolean }[] }[] }>(
      `/projects/${pid}/bids/leveling`);
  }
  };
}
