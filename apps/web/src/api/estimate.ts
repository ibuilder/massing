/** Estimating: model-derived takeoff pricing, assemblies, concept budgets, CBS, confidence bands
 *  and the basis-of-estimate.
 *
 *  SCALE-SEAM ⑤. Route-group `/estimate`, 12 methods. Reaches only `json` on HttpCore — no shared
 *  private helper crosses this boundary, which is why it is a smaller job than ④ was.
 *
 *  SCALE-SEAM (83) adds `qtoByFloor` — *what does this model cost, by storey and discipline?*
 *  It reads as a quantity method and its route is `/qto/by-floor`, but the shape settles it: every
 *  line carries `rate` and `amount` and the payload has a `grand_total`. It is priced takeoff, so
 *  it sits beside `estimateFromModel` rather than with the model reads.
 *
 *  A mixin, so every call site resolves unchanged. The surface ratchet in `api/surface.test.ts`
 *  (`>= 696`) is what proves that: moving a method is invisible to it, losing one fails it by number.
 */
import { HttpCore } from "./httpCore";
import type { Takeoff2dScopeOpts, TakeoffScope } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withEstimate<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Estimate extends Base {
  /** R34-SHEET-SCALE: `scale_units_per_px` on a **region** overrides the call-wide `scaleUnitsPerPx`, so
   *  one takeoff can span sheets at different scales. Declared rather than merely tolerated — structural
   *  typing carries an undeclared extra property onto the wire today, so this works either way, but the
   *  next normalisation pass over `regions` would drop it with no type error and no visible symptom. */
  takeoff2d(pid: string, regions: { category: string; points: [number, number][]; label?: string;
                                    scale_units_per_px?: number }[],
            scaleUnitsPerPx: number, unit = "m", opts: Takeoff2dScopeOpts = {}) {
    return this.json<{
      region_count: number; total_cost: number; unit: string;
      provenance?: { scales_used?: number[] };
      regions: { index: number; category: string; assembly: string; measure: string; quantity: number;
                 unit: string; rate: number; cost: number;
                 scale_applied?: number; scale_source?: "region" | "call" }[];
      by_assembly: { category: string; assembly: string; unit: string; quantity: number; cost: number; count: number }[];
      assemblies: { category: string; measure: string; rate: number; label: string; unit: string | null }[];
      scope?: TakeoffScope;
      annotation_scope?: TakeoffScope;
      disclaimer: string;
    }>(`/projects/${pid}/takeoff/2d`, {
      method: "POST",
      body: JSON.stringify({
        scale_units_per_px: scaleUnitsPerPx, unit, regions,
        // R27-LAYOUT ②/③ — omitted entirely when absent, which is what the route expects. The
        // route distinguishes "absent" from "present and malformed" (a 422), so spreading a
        // conditional object rather than passing `layout: undefined` is not cosmetic.
        ...(opts.layout ? { layout: opts.layout } : {}),
        ...(opts.pxPerPoint !== undefined ? { px_per_point: opts.pxPerPoint } : {}),
        ...(opts.annotations ? { annotations: opts.annotations } : {}),
      }),
    });
  }

  /** EST-1: rough cost + duration estimate from the model's quantities (productivity rates). With
   * `full`, adds material + equipment cost lines (labour + material + equipment total). */
  laborEstimate(pid: string, loading = "commercial", rate = 25, full = false) {
    return this.json<{ loading: string; loading_factor: number; hourly_rate: number; line_count: number;
      total_man_hours: number; total_labor_cost: number; note: string; derived_from_model?: boolean;
      has_material_equipment?: boolean; total_material_cost?: number; total_equipment_cost?: number; total_cost?: number;
      lines: { activity: string; group: string; unit: string; quantity: number; man_hours: number;
        crew: number; crew_days: number; labor_cost: number;
        material_cost?: number; equipment_cost?: number; line_total?: number }[] }>(
      `/projects/${pid}/estimate/labor?loading=${encodeURIComponent(loading)}&rate=${rate}${full ? "&full=true" : ""}`);
  }
  /** EST-ASSEMBLIES: the starter cost-assembly library (each a built-up unit rate). */
  estimateAssemblies() {
    return this.json<{ assemblies: { id: string; name: string; unit: string; csi?: string | null;
      unit_rate: number; component_count: number }[] }>("/estimate/assemblies");
  }
  /** Build up an assembly's unit rate (+ extend over a quantity). Pass assembly_id or components. */
  estimateAssemblyPrice(body: { assembly_id?: string; components?: unknown[]; quantity?: number;
    overrides?: Record<string, number> }) {
    return this.json<{ unit_rate: number; quantity?: number; total?: number;
      by_kind: Record<string, number>;
      lines: { resource: string; kind: string; qty: number; unit: string | null; unit_cost: number;
        waste_pct: number; extended: number }[]; component_count: number }>(
      "/estimate/assembly/price", { method: "POST", body: JSON.stringify(body) });
  }
  /** CONCEPT-BUDGET — massing program × the firm's own-history $/area rates (escalated), p25–p75 range. */
  estimateConceptBudget(pid: string, body: {
    program: { use: string; gfa: number; stories?: number }[];
    history?: Record<string, unknown>[]; rates?: Record<string, unknown>;
    default_rate?: number; to_year?: number; escalation_pct?: number; contingency_pct?: number;
  }) {
    type Line = { use: string; gfa: number; rate: number | null; cost: number | null;
      range: { low: number; high: number } | null; stories?: number | null; source: string };
    type Rate = { n: number; p25: number; median: number; p75: number; min: number; max: number };
    return this.json<{
      line_count: number; unpriced: number; subtotal: number; contingency_pct: number | null;
      contingency: number | null; total: number; range: { low: number; high: number }; lines: Line[];
      rates: { projects_used: number; projects_skipped: number; escalated_to: number | null;
        escalation_pct: number | null; rates: Record<string, Rate>; note: string };
      note: string;
    }>(`/projects/${pid}/estimate/concept-budget`, { method: "POST", body: JSON.stringify(body) });
  }
  /** BOE-LEDGER — the Basis-of-Estimate assumption ledger: completeness + version drift + exact
   * qty/price variance decomposition vs actuals. */
  estimateBoe(pid: string, body: {
    lines: Record<string, unknown>[]; prev?: Record<string, unknown>[]; actuals?: Record<string, unknown>[];
  }) {
    type Line = { key: string; cost_code: string | null; description: string; phase: string | null;
      qty: number | null; unit: string | null; unit_cost: number | null; total: number | null;
      source: string | null; quote_ref: string | null; escalation_pct: number | null;
      contingency_pct: number | null; basis_date: string | null };
    type Change = { key: string; description: string; changes: { field: string; from: unknown; to: unknown }[];
      total_from: number | null; total_to: number | null; total_delta: number | null };
    type VaRow = { key: string; description: string; assumed_qty: number | null; actual_qty: number | null;
      assumed_unit_cost: number | null; actual_unit_cost: number | null; assumed_total: number;
      actual_total: number; variance: number; qty_effect: number; price_effect: number; driver: string;
      source: string | null; quote_ref: string | null };
    return this.json<{
      ledger: { line_count: number; documented: number; pct_documented: number;
        undocumented: { key: string; description: string; missing: string[] }[]; lines: Line[]; note: string };
      phase_diff?: { compared: number; changed: number; added: string[]; removed: string[];
        changes: Change[]; note: string };
      vs_actuals?: { matched: number; total_variance: number; qty_effect: number; price_effect: number;
        rows: VaRow[]; note: string };
    }>(`/projects/${pid}/estimate/boe`, { method: "POST", body: JSON.stringify(body) });
  }
  /** EST-CONFIDENCE — score each estimate line's maturity/confidence (source × phase) → cost-weighted
   * project confidence + '% of budget still assumption-based' + the worst-value least-grounded lines. */
  estimateConfidence(pid: string, lines: Record<string, unknown>[]) {
    type Line = {
      description: string; cost_code: string | null; cost: number; source: string; phase: string;
      contingency_pct: number | null; confidence: number; band: "high" | "medium" | "low";
      assumption_based: boolean; high_contingency: boolean;
    };
    return this.json<{
      line_count: number; total_cost: number; confidence: number; band: "high" | "medium" | "low";
      pct_assumption_based: number; assumption_based_cost: number; avg_contingency_pct: number;
      cost_by_band: { high: number; medium: number; low: number };
      cost_by_source: { source: string; cost: number }[]; worst_lines: Line[]; lines: Line[]; note: string;
    }>(`/projects/${pid}/estimate/confidence`, { method: "POST", body: JSON.stringify({ lines }) });
  }
  /** CITED-ANSWER — a deterministic model query returning a CitedAnswer: every claim traces to its source
   * (GUID/record/rule/doc+revision) with coverage %, an uncited-claim guard, and source-conflict surfacing. */
  // --- conceptual estimating + IFC classification (Ediphi / Qonic) -----------
  conceptualCatalog() {
    return this.json<{ building_types: string[]; regions: string[]; base_year: number;
      annual_escalation: number; current_year: number }>(`/estimate/conceptual/catalog`);
  }
  conceptualEstimate(pid: string, params: Record<string, unknown>) {
    return this.json<{ building_type: string; gfa_sf: number; hard_cost: number; soft_cost: number;
      total_cost: number; range: { low: number; base: number; high: number };
      metrics: Record<string, number>; region_index: number; escalation_factor: number; error?: string }>(
      `/projects/${pid}/estimate/conceptual`, { method: "POST", body: JSON.stringify(params) });
  }
  /** Conceptual estimate from the IFC takeoff × unit rates — priced line items + total. */
  estimateFromModel(pid: string) {
    return this.json<{ total: number; element_count: number; lines: { ifc_class: string; count: number; unit: string; quantity: number; rate: number; amount: number }[]; unpriced: { ifc_class: string; count: number }[] }>(
      `/projects/${pid}/estimate/from-model`);
  }

  // --- Priced takeoff by storey ---
  /** QTO + cost by floor (storey) and discipline (IFC class) — quantities mapped to where they are. */
  qtoByFloor(pid: string) {
    type Line = { ifc_class: string; count: number; unit: string; quantity: number; rate: number; amount: number };
    return this.json<{ grand_total: number; element_count: number;
      storeys: { storey: string; total: number; element_count: number; lines: Line[] }[];
      by_discipline: Line[] }>(`/projects/${pid}/qto/by-floor`);
  }
  /** EST-BANDS — range estimate: low/likely/high per line + a correlated envelope and an independent
   *  P10/P50/P90 bid range from design-stage cost uncertainty by discipline. */
  estimateBands(pid: string) {
    return this.json<{
      expected: number; element_count: number;
      lines: { ifc_class: string; count: number; unit: string; quantity: number; rate: number;
        amount: number; low: number; likely: number; high: number; spread_pct: number }[];
      envelope: { low: number; high: number; note: string };
      range: { p10: number; p50: number; p90: number; std: number; note: string };
      unpriced: { ifc_class: string; count: number }[]; note: string;
    }>(`/projects/${pid}/estimate/bands`);
  }
  /** CBS-1 — Cost Breakdown Structure over the model estimate: direct → indirect → contingency →
   *  management reserve → overhead & profit → taxes, each with amount/rate/share. */
  estimateCbs(pid: string) {
    return this.json<{
      direct: number; indirect: number; subtotal: number; contingency: number;
      management_reserve: number; base_with_risk: number; overhead_profit: number; taxes: number;
      total: number; rates: Record<string, number>;
      layers: { level: string; amount: number; rate: number | null; pct_of_total: number }[];
      direct_source: string; note: string;
    }>(`/projects/${pid}/estimate/cbs`);
  }
  /** Resource-based (assembly) estimate — each class priced by building the cost up from labor +
   *  material + equipment, returning the L/M/E split + total crew-hours (not just a blended $/unit). */
  estimateResourceBased(pid: string) {
    type Line = { ifc_class: string; assembly: string; assembly_name: string; count: number; unit: string;
      quantity: number; total: number; unit_cost: number; labor_hours: number; by_kind: { labor: number; material: number; equipment: number } };
    return this.json<{ total: number; element_count: number; labor_hours: number;
      by_kind: { labor: number; material: number; equipment: number };
      by_trade: { resource: string; name: string; hours: number; cost: number }[];
      lines: Line[]; unmapped: { ifc_class: string; count: number }[] }>(
      `/projects/${pid}/estimate/resource-based`);
  }
  /** GAEB DA XML 3.2 Bill of Quantities (X83), coded to din276 / nrm1 / masterformat. */
  gaebX83Url(pid: string, system = "din276") {
    return this.url(`/projects/${pid}/estimate/gaeb.x83?system=${encodeURIComponent(system)}`);
  }
  };
}
