/** Specialty assets: on-site energy and vertical-farm/PFAL businesses layered onto a deal.
 *
 *  SCALE-SEAM ㉕. Route-group `/projects/{pid}/specialty`, taken out of `client.ts` by the route each
 *  method calls. Five methods in one contiguous run — params/save, a multi-year P&L, the blended IRR
 *  against the deal's own cash flows, and a Monte Carlo over the risk discount.
 *
 *  **Five types came with them and two deliberately did not.** `SpecialtySummary`, `SpecialtyResponse`,
 *  `SpecialtyProformaRow`, `SpecialtyProforma` and `SpecialtyBlended` move with them. Four are read by
 *  nothing else; `SpecialtySummary` is used by `portal/proforma/proforma.ts`, whose import now points
 *  here. *That one was nearly missed: the grep proving "nothing outside uses these" had been truncated
 *  with `head -4`, and the single outside reference was on the line after the cut. A population
 *  derived from a truncated list is not a population.* `MaterialEntry` and `MaterialPaletteResult` sat interleaved among them in `client.ts` and
 *  stay there — `portal/panels/materials.ts` imports `MaterialEntry` from `api/client`, so moving it
 *  would have been a breaking change dressed as tidying. **Adjacency in a file is not a relationship.**
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { MonteCarloMetric } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export interface SpecialtySummary {
  capex_total: number; annual_revenue: number; annual_opex: number;
  annual_energy_offset: number; annual_net_contribution: number;
  energy: { solar_panels: number; capex: number; generation_kwh_yr: number; annual_energy_offset: number } | null;
  pfal: { towers: number; annual_revenue: number; annual_opex: number; startup_capex: number } | null;
}
export interface SpecialtyResponse {
  params: Record<string, unknown>;
  summary: SpecialtySummary;
  deltas: { cost_line: { category: string; name: string; amount: number; curve: string } | null;
    other_income_annual_add: number; opex_annual_add: number };
}
export interface SpecialtyProformaRow {
  year: number; op_year: number; ramp: number; revenue: number; energy_offset: number;
  opex: number; net: number; cumulative: number;
}
export interface SpecialtyProforma {
  years: number; ramp_years: number; ramp_start: number; terminal_cap: number;
  capex_total: number; stabilized_net_annual: number; terminal_value: number;
  rows: SpecialtyProformaRow[]; cumulative_net: number;
  specialty_irr: number | null; payback_op_year: number | null;
}
export interface SpecialtyBlended {
  re_only_irr: number | null; blended_irr: number | null; irr_lift: number | null;
  error?: string;
  specialty?: { specialty_irr: number | null; capex_total: number; stabilized_net_annual: number;
    terminal_value: number; payback_op_year: number | null };
}

export function withSpecialty<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Specialty extends Base {
  /** Specialty assets (on-site energy + vertical-farm/PFAL) params + computed summary + deltas. */
  specialty(pid: string) {
    return this.json<SpecialtyResponse>(`/projects/${pid}/specialty`);
  }
  saveSpecialty(pid: string, params: Record<string, unknown>) {
    return this.json<SpecialtyResponse>(`/projects/${pid}/specialty`, { method: "PUT", body: JSON.stringify(params) });
  }
  /** Multi-year specialty P&L with a production ramp + a specialty-only IRR (U4 depth). */
  specialtyProforma(pid: string, opts?: { years?: number; ramp_years?: number; ramp_start?: number; terminal_cap?: number }) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts || {})) if (v != null) q.set(k, String(v));
    const qs = q.toString();
    return this.json<{ proforma: SpecialtyProforma }>(`/projects/${pid}/specialty/proforma${qs ? "?" + qs : ""}`);
  }
  /** Blend the saved specialty business into the deal's equity cash flows: RE-only vs blended IRR. */
  specialtyBlended(pid: string, assumptions: unknown, opts?: { years?: number; ramp_years?: number; ramp_start?: number; terminal_cap?: number }) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts || {})) if (v != null) q.set(k, String(v));
    const qs = q.toString();
    return this.json<{ blended: SpecialtyBlended }>(`/projects/${pid}/specialty/blended${qs ? "?" + qs : ""}`,
      { method: "POST", body: JSON.stringify(assumptions) });
  }
  /** Monte-Carlo the specialty risk discount → distribution of blended & specialty IRR. */
  specialtyMonteCarlo(pid: string, body: {
    assumptions: unknown; variables: { path: string; dist: Record<string, unknown> }[];
    iterations?: number; seed?: number; targets?: Record<string, number>;
    years?: number; ramp_years?: number; ramp_start?: number; terminal_cap?: number;
  }) {
    return this.json<{ iterations: number; metrics: Record<string, MonteCarloMetric> }>(
      `/projects/${pid}/specialty/monte-carlo`, { method: "POST", body: JSON.stringify(body) });
  }
  };
}
