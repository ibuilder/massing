/** Development pro-forma, plus disposition: appraisal, listings, comparables, MLS syndication.
 *
 *  SCALE-SEAM ⑧ took `/proforma`. SCALE-SEAM ㉜ adds the nine methods that answer *what is this
 *  asset worth, and how does it list?* — tri-approach appraisal, listing autofill / share /
 *  RESO, comparable import, and the MLS syndication bridge. They sit on `/appraisal`,
 *  `/listings`, `/comparables` and `/re-syndication`, so a prefix split would scatter them.
 *  Reports (`reports` / `reportUrl`) sat immediately above the cluster and did **not** come —
 *  those are the document catalog, not valuation. Composed through the existing `withProforma`
 *  wrapper — no extra `withX()` on `ApiClient`.
 *
 *  SCALE-SEAM (86) adds `portfolioPrioritization` — *which projects should we prioritise?* It
 *  scores every project on return, budget, schedule and risk, ranks them by a weighted composite
 *  and names a best and worst, carrying `equity_irr` and `gmp`. It belongs beside `portfolio`,
 *  `portfolioCompare` and `pipelineFunnel`, which are the rest of the deal pipeline. Its two
 *  `/portfolio/*` neighbours in `client.ts` did **not** come — they REPORT status and went to
 *  `evm.ts` with `projectHealth`; this one DECIDES.
 *
 *  SCALE-SEAM (84) adds the development budget and the draws against it — *what is this
 *  development costing, and how is it being funded?* Budget read/write, its cost lines, Sources
 *  & Uses, the GMP reconciliation pair, and both draw schedules, plus the lender draw-request
 *  PDF that `client.ts`'s own unfiled map had missed (it is `async`, and the query that built
 *  that map did not match `async` methods).
 *
 *  **`gmpReconciliation` and `syncGmpToHard` came HERE, not to `cost.ts`, and the TYPES decided
 *  it.** ㉚ put the GMP/pay-app stack in `cost.ts`, so route-and-history reasoning pointed there.
 *  But `cost.ts`'s `gmpBudget` is the GC's OWN GMP — contract value, categories, EAC/ETC — while
 *  these two are the DEVELOPER comparing their hard cost against it, and both return
 *  `DevBudgetLine` / `DevBudgetSummary`. Filing them in `cost.ts` would have forced the
 *  `DevBudget` type family into two mixins, and a split that duplicates a type family across
 *  mixins is almost always the wrong seam.
 *
 *  SCALE-SEAM ㊼ adds in-place operations — *what is this asset earning today?* Rent roll and
 *  lease-management depth. They sat above the investor stack in `client.ts` and did **not** go
 *  with ㉙ (capital is ownership, this is occupancy). `askProject` stayed.
 */
import { HttpCore } from "./httpCore";
import type { Appraisal, DevBudgetLine, DevBudgetResponse, DevBudgetSummary, FinancialStatements,
  MonteCarloResult, ProformaForecast, ProformaResult } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withProforma<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Proforma extends Base {
  solveProforma(assumptions: unknown) {
    return this.json<ProformaResult>(`/proforma/solve`, { method: "POST", body: JSON.stringify(assumptions) });
  }

  /** Same solve, but the guardrails also validate the exit cap against the project's sale comps (U3). */
  solveProformaForProject(pid: string, assumptions: unknown) {
    return this.json<ProformaResult>(`/projects/${pid}/proforma/solve`,
      { method: "POST", body: JSON.stringify(assumptions) });
  }

  /** Three financial statements + tax for the current deal (income/balance/cash-flow + two-sided budget). */
  financials(assumptions: unknown) {
    return this.json<FinancialStatements>(`/proforma/financials`, { method: "POST", body: JSON.stringify(assumptions) });
  }

  sensitivity(body: unknown) {
    return this.json<{ metric: string; x_values: number[]; y_values: number[]; matrix: (number | null)[][] }>(
      `/proforma/sensitivity`, { method: "POST", body: JSON.stringify(body) });
  }

  monteCarlo(body: unknown) {
    return this.json<MonteCarloResult>(
      `/proforma/monte-carlo`, { method: "POST", body: JSON.stringify(body) });
  }

  forecast(assumptions: unknown, actuals: unknown[], asOfMonth: number) {
    return this.json<ProformaForecast>(`/proforma/forecast`, {
      method: "POST", body: JSON.stringify({ assumptions, actuals, as_of_month: asOfMonth }) });
  }

  portfolio() {
    return this.json<{ deal_count: number; totals: Record<string, number | null>; deals: { id: string; name: string; total_uses: number; equity: number; loan: number; equity_irr: number | null; equity_multiple: number | null }[] }>(`/proforma/portfolio`);
  }

  createScenario(name: string, projectId: string | null, assumptions: unknown) {
    return this.json<{ id: string }>(`/proforma/scenarios`, {
      method: "POST", body: JSON.stringify({ name, project_id: projectId, assumptions }) });
  }

  /** Saved proforma scenarios for a project (with their solved returns), oldest→newest. */
  listScenarios(projectId: string) {
    return this.json<{ id: string; name: string; project_id: string | null;
      returns: { equity_irr?: number | null; equity_multiple?: number | null; project_irr?: number | null;
        yield_on_cost?: number | null; npv?: number | null } | null }[]>(
      `/proforma/scenarios?project_id=${encodeURIComponent(projectId)}`);
  }

  drawPackage(sid: string, body: unknown) {
    return this.json<{ sov_lines_created: number; g702: Record<string, number>; g702_pdf: string }>(
      `/proforma/scenarios/${sid}/draw-package`, { method: "POST", body: JSON.stringify(body) });
  }

  // --- The development budget, its GMP reconciliation, and the draws against it ---
  /** The development budget: line items and contingency, as saved for this project. */
  devBudget(pid: string) {
    return this.json<DevBudgetResponse>(`/projects/${pid}/dev-budget`);
  }
  saveDevBudget(pid: string, budget: { lines: DevBudgetLine[]; contingency: Record<string, number> }) {
    return this.json<DevBudgetResponse>(`/projects/${pid}/dev-budget`, { method: "PUT", body: JSON.stringify(budget) });
  }
  devBudgetCostLines(pid: string) {
    return this.json<{ cost_lines: { category: string; name: string; amount: number; curve: string }[]; summary: DevBudgetSummary }>(
      `/projects/${pid}/dev-budget/cost-lines`);
  }
  /** Sources & Uses built from the project's cost budget (grouped uses vs sized debt + equity). */
  sourcesUses(pid: string) {
    return this.json<{ uses: { label: string; amount: number }[]; sources: { label: string; amount: number }[];
      total_uses: number; total_sources: number; ltc: number; debt: number; equity: number;
      binding_constraint: string; balanced: boolean }>(`/projects/${pid}/sources-uses`);
  }
  /** Reconcile the developer's construction hard cost against the GC's live GMP. */
  gmpReconciliation(pid: string) {
    return this.json<{ dev_hard_cost: number; gc_gmp: number; delta: number; in_sync: boolean;
      gmp_committed: number; gmp_eac: number; gmp_variance_at_completion: number }>(
      `/projects/${pid}/dev-budget/gmp-reconciliation`);
  }
  /** Set the developer hard cost to the GC's GMP (replaces hard lines with one synced line). */
  syncGmpToHard(pid: string) {
    return this.json<{ synced: boolean; hard_cost: number; budget: { lines: DevBudgetLine[]; contingency: Record<string, number> }; summary: DevBudgetSummary }>(
      `/projects/${pid}/dev-budget/sync-gmp`, { method: "POST" });
  }
  /** Developer construction draw schedule sourced from the GC cost-loaded schedule + actual billed. */
  constructionDraws(pid: string) {
    return this.json<{ projected_total: number; months: number; peak_month_cost: number;
      series: { month: string; cost: number; cumulative: number; pct: number }[];
      actual_billed: number; invoice_count: number; pct_billed: number;
      by_cost_code: { code: string; description: string | null; division: string | null; billed: number }[] }>(
      `/projects/${pid}/construction-draws`);
  }
  /** Construction-loan draw status: owner invoices funded equity-first then debt vs the sized stack. */
  loanDraws(pid: string) {
    return this.json<{ loan_amount: number; equity: number; drawn_to_date: number; equity_drawn: number;
      loan_drawn: number; loan_available: number; loan_balance: number; pct_capital_drawn: number;
      interest_rate: number; accrued_interest: number; loan_start: string | null; outstanding_with_interest: number;
      budgeted_interest_reserve: number; forecast_interest: number; interest_variance: number;
      invoice_count: number }>(`/projects/${pid}/loan-draws`);
  }
  /** Lender draw-request PDF (the bank-facing submission) as an auth'd blob. */
  async loanDrawRequestPdf(pid: string, appNo = 1) {
    const res = await fetch(this.url(`/projects/${pid}/loan-draws/request.pdf?app_no=${appNo}`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`draw request PDF -> ${res.status}`);
    return res.blob();
  }

  /** FIN-GOV — move a scenario through draft → in_review → approved → published (reject/reopen → draft). */
  reviewScenario(sid: string, action: "submit" | "approve" | "reject" | "publish" | "reopen", note?: string) {
    return this.json<{ id: string; review_status: string; reviewed_by: string; note: string }>(
      `/proforma/scenarios/${sid}/review`, { method: "POST", body: JSON.stringify({ action, note: note ?? "" }) });
  }

  /** FIN-CALC — residual land value: the land price that hits a target return (bisection over the solve). */
  residualLand(assumptions: unknown, target: string, targetValue: number, maxLand?: number) {
    return this.json<{ land_value: number | null; achieved: number | null; target: string;
      target_value: number; iterations: number; converged: boolean; at_zero_land: number | null;
      note?: string }>(
      `/proforma/residual-land`, { method: "POST",
        body: JSON.stringify({ assumptions, target, target_value: targetValue, max_land: maxLand ?? null }) });
  }

  portfolioCompare() {
    return this.json<{ project_count: number; rows: { project_id: string; project_name: string;
      scenario_id: string; scenario_name: string; review_status: string;
      equity_irr: number | null; equity_multiple: number | null; yield_on_cost: number | null;
      total_uses: number | null }[];
      spread: Record<string, { best: string | null; worst: string | null;
        min: number | null; max: number | null }> }>(`/proforma/portfolio/compare`);
  }

  // --- Which projects should we prioritise? ---
  /** Portfolio prioritization — projects ranked 0-100 on return / budget / schedule / risk. */
  portfolioPrioritization() {
    type Scores = { return: number; budget: number; schedule: number; risk: number };
    return this.json<{ weights: Scores; criteria: string[];
      projects: { id: string; name: string; status: string; rank: number; composite: number;
        scores: Scores; equity_irr: number | null; gmp: number }[];
      top: { name: string } | null; bottom: { name: string } | null; note: string }>(
      `/portfolio/prioritization`);
  }

  /** PROFORMA-LIVE: the model's takeoff-priced cost + GFA + budget delta — refresh on each publish. */
  proformaLive(pid: string) {
    return this.json<{ model_version: string; est_construction_cost: number; gfa_m2: number;
      cost_per_m2: number | null; budget_hard_cost: number | null;
      delta_vs_budget: number | null; note: string }>(`/projects/${pid}/proforma/live`);
  }

  /** Proforma seed metrics derived from the project's source IFC (areas / space + storey counts). */
  proformaModelMetrics(pid: string) {
    return this.json<{ space_count: number; spaces_with_area: number; storey_count: number; net_floor_area_m2: number; net_floor_area_sf: number }>(
      `/projects/${pid}/proforma/model-metrics`);
  }

  /** RENOVATION schedule over the hold — pace, spend and what it renovates.
   *
   *  Reads `nothing_renovated` / `nothing_renovated_why`: the schedule says explicitly when a chosen
   *  pace renovates NOTHING across the entire hold. That is a load-bearing negative and callers
   *  should surface it prominently rather than treating a `false` as "fine".
   *
   *  **This was a GET against a POST route** and returned 405 for every possible caller — verified
   *  against the running API on 2026-08-27. Corrected to POST with the body the route requires.
   *
   *  It is NOT the case that nothing ever called it: PULSE-FINDINGS wired it from the home pulse,
   *  with no body, and v0.3.991 unwired it again precisely because the route is a POST and Pulse
   *  has no unit types to send (`clientCallers.test.ts` still asserts that). So the signature was
   *  wrong AND the capability is genuinely waiting for a screen that owns a renovation programme.
   *  Fixing the verb does not wire it; it stops the next caller being lied to about the contract.
   */
  proformaRenovation(pid: string, body: {
    unit_types: { type: string; count: number; current_rent_monthly: number;
                  renovated_rent_monthly: number; cost_per_unit: number }[];
    units_per_month?: number; downtime_months?: number;
  }) {
    return this.json<{ nothing_renovated?: boolean; nothing_renovated_why?: string;
      [k: string]: unknown }>(`/projects/${pid}/proforma/renovation`,
      { method: "POST", body: JSON.stringify(body) });
  }

  /** Lease ROLLOVER exposure across the hold — expiries, downtime and re-let assumptions. */
  proformaRollover(pid: string) {
    return this.json<Record<string, unknown>>(`/projects/${pid}/proforma/rollover`);
  }

  /** Project-level Uses vs Sources — latest saved scenario, else cost budget + debt/equity params. */
  twoSidedBudget(pid: string) {
    return this.json<{
      uses: { label: string; amount: number }[]; sources: { label: string; amount: number }[];
      total_uses: number; total_sources: number; balanced: boolean;
      scenario?: { id: string; name: string };
    }>(`/projects/${pid}/budget/two-sided`);
  }

  /** R22-PIPELINE — acquisition funnel across the book. Weighted value is this firm's closed history,
   *  never a textbook ladder; a stage without enough samples is excluded and counted. */
  pipelineFunnel() {
    return this.json<{
      as_of: string; deal_count: number; stages: string[]; terminal_states: string[];
      by_stage: Record<string, { count: number; value: number; deals_with_value: number }>;
      conversion: Record<string, { status: string; closed_samples: number; probability: number | null;
        needed: number; note: string }>;
      weighted: { weighted_value: number; deals_weighted: number; deals_in_flight: number;
        coverage: number | null; excluded_count: number; excluded_value: number; note: string };
      cycle_time: { closed: { count: number; median_days: number | null; mean_days: number | null };
        open_age: { count: number; median_days: number | null; mean_days: number | null };
        blended: null; note: string };
      warnings: { code: string; note: string }[];
      min_closed_samples: number;
    }>(`/pipeline/funnel`);
  }

  /**
   * PF-INCOME-BASIS — which income line each figure derives from, so a reader can TRACE it:
   *
   * `declaredAnnual` is passed through because the route accepts it and the ANSWER CHANGES: with a
   * declared figure the endpoint reconciles it against the rent roll and says which it used; without
   * one it can only report what it derived. The client dropped the parameter, so every call would
   * have asked the weaker question.
   *
   * `basis` is `derived` | `declared` | `reconciled` | `unavailable`, and `unavailable` is the one
   * that matters: it means income is UNKNOWN, which the endpoint is careful to say "is not the same
   * as zero and must not be underwritten as zero".
   */
  proformaIncomeBasis(pid: string, declaredAnnual?: number) {
    const q = declaredAnnual == null ? "" : `?declared_annual=${encodeURIComponent(declaredAnnual)}`;
    return this.json<{
      basis: string; potential_rent_annual: number | null; basis_meaning: string;
      reason?: string; derived_unavailable_reason?: string;
      declared_annual: number | null; derived: number | null;
    }>(`/projects/${pid}/proforma/income-basis${q}`);
  }

  /** Tri-approach valuation for a project (cost + income + sales-comparison + reconciliation). */
  appraisal(pid: string) {
    return this.json<Appraisal>(`/projects/${pid}/appraisal`);
  }
  /** Persist appraisal overrides (weights, depreciation, land value, …) and recompute. */
  saveAppraisal(pid: string, overrides: Record<string, unknown>) {
    return this.json<Appraisal>(`/projects/${pid}/appraisal`, {
      method: "POST", body: JSON.stringify(overrides) });
  }
  /** Re-run the appraisal with the income approach valued off the actual rent roll's in-place income. */
  appraisalFromRentRoll(pid: string) {
    return this.json<Appraisal>(`/projects/${pid}/appraisal?rentroll=1`);
  }
  /** Listing fields pre-populated from the project's proforma + model (off-plan auto-fill). */
  listingAutofill(pid: string) {
    return this.json<{ data: Record<string, unknown> }>(`/projects/${pid}/listings/autofill`);
  }
  /** Mint a signed, expiring listing share (QR / deep link). */
  shareListing(pid: string, lid: string, ttl?: number) {
    const q = ttl ? `?ttl=${ttl}` : "";
    return this.json<{ url: string; sig: string; exp: number; expires_in: number }>(
      `/projects/${pid}/listings/${lid}/share${q}`, { method: "POST" });
  }
  /** Bulk-import comparables from CSV or a RESO array into the comparable module (feeds appraisal). */
  importComparables(pid: string, body: { csv?: string; reso?: Record<string, unknown>[] }) {
    return this.json<{ imported: number; rows: { id: string; ref: string; address: string }[] }>(
      `/projects/${pid}/comparables/import`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The RESO Data Dictionary payload for a listing (the bridge seam to an MLS). */
  listingReso(pid: string, lid: string) {
    return this.json<{ reso: Record<string, unknown> }>(`/projects/${pid}/listings/${lid}/reso`);
  }
  /** Whether the listing syndication bridge is configured. */
  reSyndicationStatus() {
    return this.json<{ enabled: boolean; target: string; implemented: boolean;
      targets_supported: string[]; message: string }>(`/re-syndication/status`);
  }
  /** Push a listing (RESO-serialized) to the configured MLS bridge. 422 if it isn't configured. */
  syndicateListing(pid: string, lid: string) {
    return this.json<{ target: string; remote_id: string | null; url: string | null;
      fields_pushed: number; status: string }>(
      `/projects/${pid}/listings/${lid}/syndicate`, { method: "POST" });
  }

  /** rentRoll — occupancy, WALT, expiration schedule, in-place income. */
  rentRoll(pid: string) {
    return this.json<{ occupancy_pct: number; lease_count: number; base_rent_annual: number;
      in_place_gross_income: number; walt_years: number; expirations_by_year: Record<string, unknown>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/rent-roll`);
  }
  /** leaseManagement — renewal pipeline, rent-escalation schedule, CAM/recovery reconciliation. */
  leaseManagement(pid: string, years?: number, recoverableOpex?: number) {
    const q = new URLSearchParams();
    if (years != null) q.set("years", String(years));
    if (recoverableOpex != null) q.set("recoverable_opex", String(recoverableOpex));
    const qs = q.toString() ? `?${q}` : "";
    return this.json<{
      lease_count: number;
      renewals: { holdover_count: number; expired_count: number; options_outstanding: number;
        at_risk_rent: number; expiring: Record<string, { count: number; rent: number }>;
        rows: Record<string, unknown>[] };
      escalations: { years: number; portfolio_by_year: number[]; current_base_rent: number;
        projected_base_rent: number; rows: Record<string, unknown>[] };
      cam: { recoverable_income: number; recoverable_sf: number; by_lease_type: Record<string, number>;
        recovery_ratio?: number | null; over_recovery?: number; under_recovery?: number;
        rows: Record<string, unknown>[] };
    }>(`/projects/${pid}/leases/management${qs}`);
  }
  };
}
