/** Operations phase — how is this asset performing in service, and what will it need?
 *
 *  SCALE-SEAM (88), and the FIRST slice taken from the 126 methods that sit ABOVE the STAYING
 *  banner. (87) found that population by deriving it instead of reading the banner: no map had
 *  ever covered them, because they were never inside the RACI or CX-1 banners the earlier slices
 *  worked through. There is no map for the remaining 117 yet; this is one cluster read out of the
 *  file, not a plan for the rest.
 *
 *  What they answer together: the building is built and running. Three halves of one question —
 *  is it being MAINTAINED (`cmmsGeneratePm`, `cmmsKpis`: PM work orders, compliance, MTTR), what
 *  is it CONSUMING (`energyActual`, `energyBenchmarkStatus`, `esgSummary`: metered EUI, GHG from
 *  actuals, water, POE actual-vs-design), and what CONDITION is it in (`fcaIndex`, `fcaPortfolio`,
 *  `reserveStudy`: FCI, deferred-maintenance backlog, and whether the reserve fund clears the
 *  replacement schedule). `twinReadiness` asks whether the asset data is good enough to operate
 *  from at all, which is the precondition for the other three.
 *
 *  The backend agrees, and was checked rather than assumed: every one of these is served by
 *  `services/api/src/aec_api/routers/operations.py`, whose own docstring names the same cluster.
 *
 *  ### Three that did NOT come, and why the words say otherwise
 *
 *  **`lifecycle` / `lifecycleSeed` are not asset lifecycle.** The banner above them in `client.ts`
 *  reads "design lifecycle (RIBA/AIA phases + itemized soft costs)" and the payload is
 *  `design_fee_pct`, `deliverables`, `iso_status`, `soft_costs` — design stage gates and what the
 *  design costs, years before anything operates. Fourth shared-word trap in this sequence, after
 *  entitlements, view and carbon.
 *
 *  **`projectCarbon` is EMBODIED carbon** (`/projects/{pid}/carbon`) — what building it emits, a
 *  design-phase estimate. The GHG figures in `esgSummary` come from metered utility data. Same
 *  molecule, opposite ends of the asset life.
 *
 *  **`camReconciliation` shared a banner with `reserveStudy`** — "hold-phase asset management" —
 *  and sits in the same backend router. It stayed. It reconciles budget against actual operating
 *  expense and then allocates the recoverable pool ACROSS TENANTS by share, returning
 *  `balance_due` per suite: a lease-revenue answer, not a building-condition one. It belongs with
 *  `rentRollScrub`, `netEffectiveRent` and `normalizeT12`, all still in `client.ts` awaiting a
 *  rent-roll slice. Moving it here to empty a banner would have been the route-and-neighbour
 *  reasoning this sequence keeps rejecting. That banner is rewritten in `client.ts` rather than
 *  left naming a method that has gone.
 *
 *  A mixin, so every call site resolves unchanged; `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withOperations<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Operations extends Base {
  // --- operations: CMMS + metered energy ----------------------------------------
  cmmsGeneratePm(pid: string) {
    return this.json<{ generated: number; work_orders: { work_order: string; schedule: string }[];
      as_of: string }>(`/projects/${pid}/cmms/generate-pm`, { method: "POST" });
  }
  cmmsKpis(pid: string) {
    return this.json<{ total: number; open: number; completed: number; overdue: number;
      open_by_priority: Record<string, number>; by_type: Record<string, number>;
      pm_compliance_pct: number | null; mttr_days: number | null }>(`/projects/${pid}/cmms/kpis`);
  }
  energyActual(pid: string, gfaSf?: number) {
    const qs = gfaSf ? `?gfa_sf=${gfaSf}` : "";
    return this.json<{ total_kbtu: number; total_cost: number; water_gallons: number;
      by_utility: Record<string, { consumption: number; unit: string; kbtu: number; cost: number }>;
      monthly: { month: string; kbtu: number }[]; months_covered: number;
      gfa_sf: number | null; eui_kbtu_sf_yr: number | null; note: string }>(
      `/projects/${pid}/energy/actual${qs}`);
  }
  energyBenchmarkStatus() {
    return this.json<{ enabled: boolean; provider: string | null; message: string }>(
      `/energy/benchmark-status`);
  }
  twinReadiness(pid: string) {
    return this.json<{ assets: number; systems: number; systems_by_type: Record<string, number>;
      system_linked_pct: number | null; sensor_mapped_pct: number | null; bms_integrated_systems: number;
      dpp: { complete_pct: number | null; partial: number; complete: number; fields: string[]; note: string };
      twin_readiness_pct: number | null; note: string }>(`/projects/${pid}/twin/readiness`);
  }
  // --- facility condition assessment (FCI) --------------------------------------
  fcaIndex(pid: string) {
    return this.json<{ elements: number; open_deficiencies: number; crv: number; crv_source: string;
      deferred_maintenance: number; capital_renewal: number; fci_pct: number; band: string;
      by_uniformat: { group: string; count: number; deferred: number; renewal: number; crv: number; fci_pct: number | null }[];
      by_condition: Record<string, number>;
      worst_elements: { ref: string; element: string; uniformat: string; condition: string; cost: number }[];
      recommended_by_year: { year: number; cost: number }[];
      bands: Record<string, string>; note: string }>(`/projects/${pid}/fca/index`);
  }
  fcaPortfolio() {
    return this.json<{ count: number; note: string;
      projects: { project_id: string; project: string; fci_pct: number; band: string; crv: number;
        backlog: number; open_deficiencies: number }[] }>(`/fca/portfolio`);
  }
  // --- capital plan: is the reserve funded for what the condition survey found? -----------
  reserveStudy(pid: string, opts: { horizonYears?: number; openingBalance?: number;
      annualContribution?: number; inflationPct?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.horizonYears) q.set("horizon_years", String(opts.horizonYears));
    if (opts.openingBalance) q.set("opening_balance", String(opts.openingBalance));
    if (opts.annualContribution) q.set("annual_contribution", String(opts.annualContribution));
    if (opts.inflationPct) q.set("inflation_pct", String(opts.inflationPct));
    const qs = q.toString();
    return this.json<{ horizon: { from: number; to: number }; components: number;
      components_missing_data: number;
      events: { year: number; item: string; cost: number; cost_escalated: number; source: string; ref: string }[];
      schedule: { year: number; outflows: number; contribution: number; balance: number }[];
      total_outflows: number; first_underfunded_year: number | null; adequately_funded: boolean;
      suggested_level_contribution: number; suggestion_clears_horizon?: boolean; note: string }>(
      `/projects/${pid}/reserves/study${qs ? `?${qs}` : ""}`);
  }
  esgSummary(pid: string, gfaSf?: number) {
    const qs = gfaSf ? `?gfa_sf=${gfaSf}` : "";
    return this.json<{
      performance: {
        energy: { total_kbtu: number; eui_kbtu_sf_yr: number | null; months_covered: number; gfa_sf: number | null };
        ghg: { scope1_tco2e: number; scope2_tco2e: number; total_tco2e: number;
          intensity_kgco2e_sf: number | null; grid_factor_kgco2e_kwh: number; note: string };
        water: { gallons: number; intensity_gal_sf: number | null };
      };
      certifications: { credits_tracked: number; points_targeted: number; points_achieved: number };
      poe: { count: number; reported: number; latest: { ref: string; level: string | null; state: string;
        survey_date: string | null; satisfaction_score: number | null; design_eui: number | null;
        actual_eui: number | null; eui_gap_pct: number | null } | null };
      data_coverage: { meter_months: number }; as_of: string }>(`/projects/${pid}/esg${qs}`);
  }
  };
}
