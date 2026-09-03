/** Resilience — what could the environment do to this project?
 *
 *  SCALE-SEAM (89), second slice from the 117 methods that sit above the STAYING banner.
 *
 *  Four methods, one question asked of three different things: the SITE (`resilienceFlood` — SFHA,
 *  design flood elevation, which assets sit below it), the CIVIL DESIGN (`resilienceStormwater` —
 *  runoff coefficient, peak CFS, detention volume), and the PROGRAMME (`resilienceWeather` —
 *  weather-sensitive activities by trade, open site risks, delay days and reports).
 *  `resilienceClimateRisk` is the composite over all three, returning one rating and the factors
 *  behind it.
 *
 *  ### The tension, named rather than smoothed over
 *
 *  `resilienceWeather` reads ACTIVITIES — trade, start, finish, percent complete, delay reports —
 *  which is `schedule.ts`'s vocabulary, and a split on subject matter would send it there. It stays
 *  because the question is not "how is the programme going" but "what is the weather doing to it",
 *  and because `resilienceClimateRisk` folds its `weather_delay_days` and `high_severity_open` into
 *  the same composite as the flood and runoff numbers. Separating the input from the rollup that
 *  consumes it is the rollup/detail split ⓽ made and (87) had to undo.
 *
 *  *A slice that quietly contradicts an earlier one's stated reason is how the next reader stops
 *  trusting either — so: this is the opposite call from (86)'s portfolio trio, where two methods
 *  REPORTED and one DECIDED. Here all four report on one subject from different angles.*
 *
 *  ### The banner over-claimed, for the sixth time in this sequence
 *
 *  In `client.ts` these sat under `// --- climate & water resilience (flood + stormwater) ---`,
 *  which names TWO of the four beneath it. Weather and the climate-risk composite were filed at
 *  whatever banner was nearest — the same defect as ⑨'s "AI drafting" running into sheet extraction,
 *  (81)'s `ifcClassify` under a G704 turnover header, and (82)'s RACI banner covering thirteen
 *  methods while describing four.
 *
 *  A mixin, so every call site resolves unchanged; `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withResilience<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Resilience extends Base {
  // --- site + civil + programme, and the composite that folds all three -----------------
  resilienceFlood(pid: string) {
    return this.json<{ count: number; in_special_flood_hazard_area: boolean;
      design_flood_elevation_ft: number | null; assets_checked: number; at_risk_count: number;
      compliant: boolean; note: string;
      assessments: { ref: string; name: string; flood_zone: string; in_sfha: boolean; bfe_ft: number | null;
        flood_design_class: string; freeboard_ft: number; dfe_ft: number | null }[];
      assets_at_risk: { ref: string; asset: string; elevation_ft: number; below_dfe_by_ft: number }[] }>(
      `/projects/${pid}/resilience/flood`);
  }
  resilienceStormwater(pid: string) {
    return this.json<{ count: number; total_area_acres: number; composite_runoff_coefficient: number | null;
      peak_runoff_cfs: number; detention_volume_cf: number; detention_volume_gal: number; note: string;
      catchments: { ref: string; name: string; surface: string; area_sf: number; c: number; i_in_hr: number;
        return_period_years: string; peak_cfs: number }[];
      by_surface: { surface: string; area_sf: number; peak_cfs: number }[] }>(
      `/projects/${pid}/resilience/stormwater`);
  }
  resilienceWeather(pid: string) {
    return this.json<{ sensitive_count: number; by_sensitivity: Record<string, number>;
      site_risk_count: number; open_risk_count: number; high_severity_open: number; risk_score: number;
      weather_delay_days: number; delay_report_count: number;
      by_season: Record<string, number>; by_hazard: Record<string, number>; note: string;
      weather_sensitive_activities: { ref: string; name: string; trade: string; sensitivity: string;
        start: string; finish: string; percent: number }[];
      site_risks: { ref: string; name: string; hazard_type: string; season: string; severity: string;
        location: string; activity_ref: string; open: boolean; state: string }[];
      delay_reports: { ref: string; date: string; weather: string; impact: string; days: number }[] }>(
      `/projects/${pid}/resilience/weather`);
  }
  resilienceClimateRisk(pid: string) {
    return this.json<{ rating: string; score: number; in_special_flood_hazard_area: boolean;
      design_flood_elevation_ft: number | null; assets_at_risk: number; peak_runoff_cfs: number;
      open_site_risks: number; high_severity_open: number; weather_delay_days: number;
      factors: string[]; note: string }>(`/projects/${pid}/resilience/climate-risk`);
  }
  };
}
