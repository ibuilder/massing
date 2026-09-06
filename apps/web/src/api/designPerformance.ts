/** What will this design CONSUME and EMIT, and does it comply?
 *
 *  SCALE-SEAM ㉞. Five methods grouped by the question they answer, and the seam they sit on was
 *  drawn by earlier slices rather than by this one — which is why they belong together.
 *
 *  **Design-phase PREDICTION, as against in-service MEASUREMENT.** `operations.ts` already holds the
 *  metered counterparts (`/projects/{pid}/energy/actual`, `/energy/benchmark-status`) and its own
 *  header records why the carbon half did not go with them: *"`projectCarbon` is EMBODIED carbon —
 *  what building it emits, a design-phase estimate. The GHG figures in `esgSummary` come from metered
 *  utility data. Same molecule, opposite ends of the asset life."* `models.ts` records the parallel
 *  call for energy — grouping by nearby comments *"would have dragged … `/energy` across the seam"*.
 *  So the axis was already committed to twice, independently, and these five are the prediction side
 *  of it: the thermal model and its gbXML/IDF handoff, and embodied carbon against the project target.
 *
 *  **Deliberately NOT called `environmental.ts`.** That names the TOPIC, and the topic is exactly what
 *  both halves share — naming it that would re-blur the seam `operations.ts` drew. What separates them
 *  is not subject matter but whether the number is forecast or observed.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it: moving a
 *  method is invisible to it, losing one fails it by number.
 */
import type { EnergyResult } from "./types";

import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withDesignPerformance<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class extends Base {
  energy(pid: string) {
    return this.json<EnergyResult>(`/projects/${pid}/energy`);
  }

  /** ENERGY phase 1 — the thermal model extracted from the IFC (zones · surfaces · constructions). */
  energyModel(pid: string) {
    return this.json<{ zone_source: string;
      zones: { id: string; name: string; storey: string; area_m2: number; volume_m3: number }[];
      surfaces: { id: string; name: string; ifc_class: string; idf_type: string; zone_id: string;
        construction: string; orientation: string; area_m2: number; geometry: "exact" | "bbox";
        corners: number[][] }[];
      constructions: { name: string; u_value: number | null; source: string }[];
      counts: Record<string, number>; note: string }>(`/projects/${pid}/energy/model`);
  }

  /** ENERGY phase 1 — the gbXML / IDF envelope export URLs (downloads, not JSON). */
  energyExportUrl(pid: string, fmt: "gbxml" | "idf") {
    return `${this.baseUrl}/projects/${pid}/energy/export.${fmt}`;
  }

  /** Embodied-carbon compliance: element totals, coverage and intensity against the project's limits. */
  carbonComplianceReport(pid: string) {
    return this.json<{
      elements: { total_tco2e: number; coverage_pct: number; intensity_kgco2e_m2?: number;
                  carbon_matched: number; with_quantity: number;
                  hotspots: { guid: string; name: string | null; category: string; kgco2e: number }[] };
      buy_clean: { rows: { category: string; achieved_factor: number; limit: number; unit: string;
                           pass: boolean; headroom_pct: number; action: string | null }[];
                   passing: number; failing: number };
      leed_inventory: { total_tco2e: number; items: { category: string; kgco2e: number; share_pct: number }[] };
    }>(`/projects/${pid}/carbon/compliance`);
  }

  projectCarbon(pid: string) {
    return this.json<{ total_kgco2e: number; total_tco2e: number; line_count: number; unmatched: number;
      by_material: Record<string, number>; by_cost_code: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/carbon`);
  }
  };
}
