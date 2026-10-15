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

/** One graded zone as the screen returns it. */
export interface WindZone {
  zone: string;
  factor: number;
  speed_ms: number;
  lawson: string;
  comfort: string;
}

/** The screen's full answer. `inputs` echoes what was actually used — including derived dimensions. */
export interface WindResult {
  inputs: {
    height_m: number; width_m: number; depth_m: number; wind_ms: number;
    gap_m: number | null; podium_height_m: number;
  };
  zones: WindZone[];
  worst: { zone: string; lawson: string; speed_ms: number };
  acceptable_for_entrances: boolean;
  mitigations: string[];
  disclaimer: string;
}


type Ctor<T> = new (...args: any[]) => T;

/** CARBON-UNCONVERTED — embodied carbon (A1–A3) from the project's material quantities.
 *
 *  `carbon.compute` can decline a line two ways and used to count both as `unmatched`:
 *  **no EPD factor** (the material is unrecognised) and **unit not convertible** (the material IS
 *  recognised, and its takeoff unit is in a different family from the factor's — concrete factored
 *  per m³ against a quantity in kg). The second is the dangerous one: the line is a known emitter
 *  and it leaves `total_kgco2e`, `by_material` and `by_cost_code` with no trace but a tally.
 *  Measured — 2,400 t of concrete in kg beside steel and glazing gives `329.17 tCO₂e · 1 line(s)
 *  unmatched` and a material rollup naming only steel and glazing, while the concrete is worth
 *  roughly another 300 tCO₂e. The remedies differ, so the counts are separate and the excluded
 *  materials are named. See `portal/panels/carbonCoverage.ts`. */
export interface ProjectCarbonLine {
  material: string;
  quantity: number;
  unit: string;
  /** The EPD keyword the MATERIAL matched — set even on a line refused for its unit, which is why
   *  a recognised-but-unconverted line is not the same as an unrecognised one. */
  matched?: string | null;
  factor?: number;
  factor_unit?: string;
  kgco2e: number | null;
  cost_code?: string;
  note?: string | null;
}

export interface ProjectCarbon {
  lines: ProjectCarbonLine[];
  total_kgco2e: number;
  total_tco2e: number;
  by_material: Record<string, number>;
  by_cost_code: Record<string, number>;
  /** Every quantity line handed to the engine — the denominator `assessed` is out of. */
  line_count: number;
  /** Lines that reached the total. */
  assessed: number;
  /** The SUM of the two below, kept because it is rendered. */
  unmatched: number;
  /** The material is not in the factor table at all. Remedy: add an EPD factor. */
  no_factor: number;
  /** The material IS recognised and its unit is in the wrong family. Remedy: record the quantity in
   *  the factor's unit, or supply a density — which the engine refuses to guess. */
  unit_mismatch: number;
  /** The recognised materials excluded from the total, with the quantity left out. These are
   *  emitters ABSENT from `by_material`. */
  unconverted_materials: Record<string, number>;
  /** The engine's sentence about what the total covers and what it excludes. */
  coverage_note: string;
  message?: string | null;
}

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

  /** ENV-1 — the pedestrian wind-comfort screen. Omit the dims and the mass comes off the model's
   *  bounding box; 409 when there is neither a full set of dims nor a source model. NOT CFD. */
  envWindScreen(pid: string, body: { height_m?: number | null; width_m?: number | null;
                                     depth_m?: number | null; wind_ms?: number | null;
                                     gap_m?: number | null; podium_height_m?: number | null }) {
    return this.json<WindResult>(`/projects/${pid}/env/wind`, {
      method: "POST", body: JSON.stringify(body),
    });
  }

  projectCarbon(pid: string) {
    return this.json<ProjectCarbon>(`/projects/${pid}/carbon`);
  }
  };
}
