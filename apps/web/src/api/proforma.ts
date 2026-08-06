/** Development pro-forma: solve, scenarios, sensitivity, portfolio and the model-linked metrics.
 *
 *  SCALE-SEAM ⑧. Route-group `/proforma`, taken out of `client.ts` by the route each method calls.
 *
 *  **The group was four times the size the hand-off estimated.** It was scoped as "~3 methods
 *  (`solve`, `live`, `model-metrics`)"; locating by route rather than by eye found **15**, sitting in
 *  four separate regions — a run of twelve, then `portfolioCompare`, `proformaLive` and
 *  `proformaModelMetrics` each alone, ~1,200 and ~1,500 lines further down. That is the same finding
 *  ⑥ and ⑦ recorded in their own words: the `// --- section ---` comments label where a run *starts*
 *  and stop meaning anything after it.
 *
 *  **Three methods here are new, not moved**, and they exist because the endpoints were unreachable:
 *  `/proforma/renovation`, `/proforma/rollover` and `/proforma/income-basis` are built, tested and
 *  had no client caller at all — `test_reachable` passes on them because the *route* exists, which is
 *  the gap `test_route_reachability` now ratchets. `renovation` carries the load-bearing negative:
 *  `nothing_renovated` says a pace renovates NOTHING across the whole hold, and a finding like that
 *  should be loud rather than a `false` in a payload nobody fetches.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it: moving a
 *  method is invisible to it, losing one fails it by number. The floor moves 699 -> 702 because of
 *  the three NEW methods, not because anything moved.
 */
import { HttpCore } from "./httpCore";
import type { FinancialStatements, MonteCarloResult, ProformaForecast, ProformaResult } from "./types";

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

  /** Import a Primavera P6 export (.xer or .xml/PMXML — auto-detected) so the 4D scrub reports
   *  real calendar dates and the tasks become editable schedule_activity records. */
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
   */
  proformaRenovation(pid: string) {
    return this.json<{ nothing_renovated?: boolean; nothing_renovated_why?: string;
      [k: string]: unknown }>(`/projects/${pid}/proforma/renovation`);
  }

  /** Lease ROLLOVER exposure across the hold — expiries, downtime and re-let assumptions. */
  proformaRollover(pid: string) {
    return this.json<Record<string, unknown>>(`/projects/${pid}/proforma/rollover`);
  }

  /** INCOME BASIS — which income line each figure is derived from, so a reader can trace it. */
  proformaIncomeBasis(pid: string) {
    return this.json<Record<string, unknown>>(`/projects/${pid}/proforma/income-basis`);
  }
  };
}
