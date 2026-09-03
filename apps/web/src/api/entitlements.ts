import { HttpCore } from "./httpCore";
import type {
  DepthPoint,
  EgressResult,
  EntitlementConditions,
  OpendataPermit,
  OptScheme,
  ReviewCycles,
} from "./types";

/**
 * Entitlements — the `/projects/{pid}/entitlements/…` route group.
 *
 * SCALE-SEAM ㉑, forced rather than chosen: adding `entitlementConditions` put `client.ts` at 3,136
 * against a 3,129 ratchet. That pin's own comment says the friction should buy a cluster out of the
 * file instead of buying the pin a higher number, and `/entitlements` is a clean route group — the
 * rule ⑫–⑳ used, applied to two methods rather than seven.
 *
 * Both answer R22-ENTITLEMENT's question — the hole between "we underwrite the deal" and "we build
 * it" — from opposite ends: `entitlementReviewCycles` measures the time an application has already
 * spent and whose court held it; `entitlementConditions` tracks what an approval obliges us to do
 * afterwards. Neither ever reports a condition satisfied or a round scored on incomplete data.
 *
 * SCALE-SEAM ㊽ adds open-data municipal filings — *which permits exist near this site?*
 * Cities catalog, query, import into the GC permit module. `permitReadiness` stayed — that
 * is a model-submission checklist, not a city feed.
 *
 * SCALE-SEAM ❼ adds zoning feasibility — *what can we legally build on this site?*
 * Envelope plus scheme compare. `qualitySummary` sat below and did **not** come.
 *
 * SCALE-SEAM ⓸ adds land context — *what's on and around this site?* OSM site-context plus parcel analyze / screen / data-status. Preflight stayed.
 */
type Ctor<T> = new (...args: any[]) => T;

export function withEntitlements<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Entitlements extends Base {
  /** R22-ENTITLEMENT review rounds, split by whose court held them. See {@link ReviewCycles}. */
  entitlementReviewCycles(pid: string, application?: string) {
    return this.json<ReviewCycles>(`/projects/${pid}/entitlements/review-cycles`
      + (application ? `?application=${encodeURIComponent(application)}` : ""));
  }

  /** R22-ENTITLEMENT — an approval's conditions as tracked items rather than one paragraph.
   *  Nothing is ever reported satisfied: a condition whose topic and quantity cannot be read is
   *  `unparsed`, because an approval condition silently treated as met is a building put up out of
   *  compliance while the report said it was fine. */
  entitlementConditions(pid: string) {
    return this.json<EntitlementConditions>(`/projects/${pid}/entitlements/conditions`);
  }

  /** R22-ENTITLEMENT ② — approval conditions checked against the model (height max, parking min).
   *  Anything unevaluable is `not_checkable`, never a pass. Refused entitlements are listed, not scored. */
  entitlementConditionChecks(pid: string) {
    return this.json<{
      project_id: string;
      model_facts: { height_m: number | null; storeys: number | null; parking_spaces: number | null };
      entitlements: {
        entitlement_id: string; ref: string | null; workflow_state: string; refused: boolean;
        exceeds_count: number; not_checkable_count: number; checked_count?: number;
        exceeds?: { topic: string; note?: string }[];
        not_checkable?: { topic: string; reason?: string }[];
      }[];
      in_force_count: number;
      refused: { ref: string | null; workflow_state: string }[];
      total_exceeds: number; total_not_checkable: number; note: string;
    }>(`/projects/${pid}/entitlements/condition-checks`);
  }

  /** permitCities — open-data permit sources this deployment can query. */
  permitCities() {
    return this.json<{ cities: { id: string; label: string; region: string; authority: string; geo: boolean }[] }>(
      "/opendata/permit-cities");
  }
  /** opendataPermits — a city's filings near a point / by text. */
  opendataPermits(pid: string, opts: { city: string; lat?: number; lon?: number; radius?: number; address?: string; q?: string; limit?: number }) {
    const qs = new URLSearchParams({ city: opts.city });
    for (const k of ["lat", "lon", "radius", "address", "q", "limit"] as const)
      if (opts[k] !== undefined && opts[k] !== "") qs.set(k, String(opts[k]));
    return this.json<{ city: string; count: number; permits: OpendataPermit[] }>(
      `/projects/${pid}/opendata/permits?${qs}`);
  }
  /** importOpendataPermits — import a city's filings into the GC permit module (source-tagged, deduped). */
  importOpendataPermits(pid: string, body: { city: string; lat?: number; lon?: number; radius?: number; address?: string; q?: string; max?: number }) {
    return this.json<{ imported: number; skipped: number; found: number; refs: string[] }>(
      `/projects/${pid}/opendata/permits/import`, { method: "POST", body: JSON.stringify(body) });
  }

  /** feasibility — zoning envelope: max buildable GFA, unit yield, parking, vs model GFA. */
  feasibility(pid: string, gfa?: number) {
    const qs = gfa != null ? `?gfa=${gfa}` : "";
    return this.json<{ error?: string; site?: string; jurisdiction?: string; use_type?: string;
      site_area_sf?: number; site_area_acres?: number; buildable_footprint_sf?: number | null;
      max_floors?: number | null; far_gfa_sf?: number | null; envelope_gfa_sf?: number | null;
      allowed_gfa_sf?: number | null; binding_constraint?: string | null; net_buildable_sf?: number | null;
      unit_yield?: number | null; parking_required?: number | null; open_space_required_sf?: number | null;
      constraints?: { constraint: string; limit_gfa_sf: number; basis: string }[];
      model?: { actual_gfa_sf: number; far_used: number; pct_of_allowed: number;
        headroom_gfa_sf: number; status: string } | null; warnings?: string[]; ref?: string }>(
      `/projects/${pid}/feasibility${qs}`);
  }
  /** feasibilityCompare — zoning schemes ranked by buildable yield. */
  feasibilityCompare(pid: string) {
    return this.json<{ count: number; best_ref?: string | null; warnings?: string[];
      scenarios: { ref?: string; site?: string; use_type?: string; far?: number | null;
        max_floors?: number | null; allowed_gfa_sf?: number | null; binding_constraint?: string | null;
        net_buildable_sf?: number | null; unit_yield?: number | null; parking_required?: number | null;
        delta_units?: number; delta_gfa_sf?: number }[] }>(
      `/projects/${pid}/feasibility/compare`);
  }

  // --- Test fit: what fits on this plate, and what is the best scheme? ---
  /** Test-fit: compare unit-mix schemes on a floor plate (yield + parking, ranked). */
  testFitCompare(params: { plate_w: number; plate_d: number; floors: number; schemes?: unknown[]; with_defaults?: boolean }) {
    return this.json<{ best: string | null; schemes: { name: string; total_units: number; efficiency: number; daylight_efficiency: number; daylight_limited: boolean; total_nsf: number; total_gsf: number; avg_unit_sf: number; parking_stalls: number; mix: Record<string, number> }[]; egress?: EgressResult }>(
      "/test-fit/compare", { method: "POST", body: JSON.stringify(params) });
  }
  /** Generative design: sweep schemes (× optional plate depths), filter by targets, rank by yield-on-cost.
   * Pass `depths` or `targets.sweep_depth` to make daylight-limited plate depth an optimize dimension. */
  testFitOptimize(params: { plate_w: number; plate_d: number; floors: number;
    targets?: Record<string, number | string | boolean>; econ?: Record<string, number>; depths?: number[] }) {
    return this.json<{ considered: number; feasible: number; objective: string; best: OptScheme | null;
      ranked: OptScheme[]; swept_depths: number[]; depth_curve: DepthPoint[]; best_depth_m: number | null }>(
      "/test-fit/optimize", { method: "POST", body: JSON.stringify(params) });
  }
  /** SITE-1: OSM site context (buildings/roads/land-use) as GeoJSON — fetched once server-side,
   *  cached for offline use afterwards. Omit lat/lon to use the model's IfcSite georeference. */
  siteContext(pid: string, opts: { lat?: number; lon?: number; radius?: number; refresh?: boolean } = {}) {
    const q = new URLSearchParams();
    if (opts.lat !== undefined) q.set("lat", String(opts.lat));
    if (opts.lon !== undefined) q.set("lon", String(opts.lon));
    if (opts.radius !== undefined) q.set("radius", String(opts.radius));
    if (opts.refresh) q.set("refresh", "true");
    const qs = q.toString();
    return this.json<{ lat: number; lon: number; radius: number; attribution: string;
      counts: Record<string, number>; geojson: { features: { properties: Record<string, unknown>;
      geometry: { type: string; coordinates: unknown } }[] } }>(
      `/projects/${pid}/site-context${qs ? "?" + qs : ""}`);
  }
  /** Parcel geometry analyze — area, centroid, optional zoning slack. */
  parcelAnalyze(body: {
    geojson?: unknown; wkt?: string; parcel_id?: string;
    zoning?: { max_far?: number; max_coverage?: number; max_height_m?: number };
    proposal?: { gfa_m2?: number; footprint_m2?: number; height_m?: number };
  }) {
    type Check = { metric: string; value: number; limit: number | null; ok: boolean | null; slack: number | null; max_gfa_m2?: number | null };
    return this.json<{
      parcel_id: string | null; vertices: number; coordinates_were_lonlat: boolean;
      area_m2: number; area_acres: number; perimeter_m: number;
      centroid: { x: number; y: number }; bbox: { minx: number; miny: number; maxx: number; maxy: number };
      compliance?: { checks: Check[]; ok: boolean | null; violations: string[] }; note: string;
    }>(`/parcels/analyze`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Parcel screening — match a list against zoning / flood / acres criteria. */
  parcelsScreen(parcelList: unknown[], criteria: Record<string, unknown>) {
    return this.json<{ matches: { id: string; acres: number; zoning?: string; flood_zone?: string;
      price?: number | null; buildable: { acres: number; max_gfa_sf?: number | null;
      conceptual_cost?: number; land_cost_per_buildable_sf?: number } }[];
      rejected: { id: string; failed: string[] }[]; match_count: number; screened: number;
      message?: string | null }>(`/parcels/screen`, { method: "POST",
      body: JSON.stringify({ parcels: parcelList, criteria }) });
  }
  /** Parcel data-source status — whether a provider is wired. */
  parcelsDataStatus() {
    return this.json<{ enabled: boolean; provider: string | null; message: string }>(`/parcels/data-status`);
  }
  };
}
