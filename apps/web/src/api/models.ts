/** Discipline-model health, QA, georeferencing, and federation CRUD.
 *
 *  SCALE-SEAM ⑰. Route-group `/projects/{pid}/models`, taken out of `client.ts` by the route
 *  each method calls. Named `models.ts` so it does not collide with `api/model.ts`
 *  (`withModel` is `/model` — capabilities, query, assets, exports).
 *
 *  Nine methods in **four** regions — health/QA/norm-valid next to layout loads, warnings next
 *  to the master-builder brief, georeferencing next to scan-deviation, federation CRUD next to
 *  energy/MEP. Grouping by the nearby comments would have dragged `/quantities`, `/massing`,
 *  `/scan`, `/validate` and `/energy` across the seam.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/**
 * Above this, a discipline model goes up resumably rather than as one multipart POST.
 *
 * Eight times the server's 1 MiB chunk floor: below it a file is one or two chunks, so the handshake
 * and the completion are two extra round trips that save nothing. Above it a dropped connection
 * starts to cost real time, which is the whole point of the chunked path.
 */
const RESUMABLE_ABOVE_BYTES = 8 * 1024 * 1024;

export function withModels<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Models extends Base {
  /** Composite Model Health scorecard — one score over hygiene + ISO 19650 KPIs + clash + verified. */
  modelHealth(pid: string) {
    return this.json<{ overall_score: number | null; band: string; scored_lenses: number; model_available: boolean;
      lenses: { key: string; label: string; tool: string; score: number | null; status: string; headline: string }[] }>(
      `/projects/${pid}/models/health`);
  }
  /** Model integrity scan — duplicate GUIDs, orphaned elements, overlaps, unenclosed spaces, blank names. */
  modelQa(pid: string) {
    type Check = { count: number; [k: string]: unknown };
    return this.json<{ element_count: number; total_issues: number; clean: boolean;
      checks: { duplicate_guids: Check; orphaned_elements: Check; overlapping_duplicates: Check;
        unenclosed_spaces: Check & { total_spaces: number }; blank_names: Check & { of_elements: number } };
      note: string }>(`/projects/${pid}/models/qa`);
  }
  /** NORM-VALID — normative openBIM conformance gauntlet (header/schema/IFC implementer-agreement rules). */
  normValid(pid: string) {
    return this.json<{
      schema: string; passed: boolean; summary: { pass: number; warn: number; fail: number };
      checks: { id: string; category: string; label: string; status: "pass" | "warn" | "fail";
        count: number; sample: unknown[]; note: string }[]; note: string;
    }>(`/projects/${pid}/models/norm-valid`);
  }
  /** WARN-1 — unified model-warnings feed: hygiene + normative-conformance defects, one worst-first punch list. */
  modelWarnings(pid: string) {
    return this.json<{
      total: number; clean: boolean; by_severity: { fail: number; warn: number; info: number };
      warnings: { source: string; id: string; severity: "fail" | "warn" | "info"; label: string;
        count: number; sample: unknown[]; note?: string }[]; note: string;
    }>(`/projects/${pid}/models/warnings`);
  }
  /** Shared-coordinates / setout basis — IfcMapConversion (E/N/height, true-north, scale) + CRS + LoGeoRef. */
  modelGeoreferencing(pid: string) {
    return this.json<{ georeferenced: boolean; level: number; level_label: string; note: string;
      map_conversion: { eastings: number | null; northings: number | null; orthogonal_height: number | null;
        true_north_bearing_deg: number | null; scale: number } | null;
      crs: { name: string | null; geodetic_datum: string | null; vertical_datum: string | null;
        map_projection: string | null; map_zone: string | null } | null;
      site: { ref_latitude: number[] | null; ref_longitude: number[] | null; ref_elevation: number | null } | null }>(
      `/projects/${pid}/models/georeferencing`);
  }
  /** Federation alignment report — do the discipline models share a storey scheme + georef origin? */
  modelAlignment(pid: string) {
    return this.json<{ models: { name: string; storey_count: number; error?: string;
        storeys: { name: string; elevation: number }[]; georef: Record<string, unknown> | null }[];
      issues: { type: string; severity: string; model: string; detail: string }[];
      aligned: boolean; message: string }>(`/projects/${pid}/models/alignment`);
  }
  /**
   * R41-MODEL-ALIGN — the yaw correction proposed for one discipline model, or `null` when there is
   * nothing to fit. A PROPOSAL: the server opens the IFC read-only and never writes it.
   *
   * `accepted` is the answer; the rest is the working. A fit that is refused still returns its
   * numbers, because "no" without the margin is a verdict nobody can calibrate.
   */
  modelAlignmentFit(pid: string, mid: string) {
    return this.json<{
      model: string; discipline: string; applied: boolean; note: string;
      fit: null | { yaw_deg: number; currently_at_deg: number; extent_m: [number, number];
        obb_area_m2: number; aabb_area_m2: number; area_saving: number;
        accepted: boolean; reason: string };
    }>(`/projects/${pid}/models/${mid}/alignment-fit`);
  }
  /** Discipline models layered on a project (for federated clash). */
  projectModels(pid: string) {
    return this.json<{ id: string; discipline: string; created_at: string | null }[]>(`/projects/${pid}/models`);
  }
  /**
   * Add a discipline model, choosing the transport by size.
   *
   * **The caller does not pick.** A screen that had to decide between multipart and the resumable
   * handshake would be a screen that has to know what a chunk is, and every future caller would have
   * to make the same choice again — one of them getting it wrong quietly, by sending a 300 MB IFC
   * down a path that cannot resume. The size is the only input the decision needs, and it is right
   * here.
   *
   * Above `RESUMABLE_ABOVE_BYTES` the file goes up in chunks (R41-UPLOAD-WARK): a dropped connection
   * costs one chunk instead of the transfer, and re-adding an unchanged model costs nothing at all.
   * Below it, the handshake and the completion are two extra round trips to save nothing.
   */
  async addProjectModel(pid: string, file: File, discipline: string,
                        onProgress?: (sent: number, total: number) => void) {
    if (file.size >= RESUMABLE_ABOVE_BYTES) {
      const up = await this._uploadResumable(pid, file, onProgress);
      const res = await this.json<{ id: string; discipline: string; size: number }>(
        `/projects/${pid}/models/from-upload`,
        { method: "POST", body: JSON.stringify({ key: up.key, discipline }) });
      return { ...res, deduplicated: up.deduplicated };
    }
    const fd = new FormData(); fd.append("file", file); fd.append("discipline", discipline);
    const res = await fetch(this.url(`/projects/${pid}/models`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `add model -> ${res.status}`); }
    return { ...(await res.json()) as { id: string; discipline: string; size: number },
             deduplicated: false };
  }
  deleteProjectModel(pid: string, mid: string) {
    return this.json<{ deleted: boolean; id: string }>(`/projects/${pid}/models/${mid}`, { method: "DELETE" });
  }
  /** Write→reopen serialization fidelity (schema / GUIDs / storeys / properties). */
  exportQa(pid: string) {
    return this.json<{
      method: string; comparable: boolean; identical?: boolean; lossless?: boolean;
      entities?: { before: number; after: number };
      guids?: { before: number; after: number; removed: number; added: number };
      properties?: { before: number; after: number; delta: number };
      note?: string;
    }>(`/projects/${pid}/models/export-qa`);
  }
  /** Structural IFC-schema validity from the STEP text (works even when the file will not load). */
  schemaDiag(pid: string) {
    return this.json<{
      schema: string | null; passed: boolean; instances?: number;
      summary: { error: number; warning: number; by_code?: Record<string, number>;
        reported?: number; truncated?: boolean };
      findings: { code: string; severity: string; instance?: string; entity?: string; message: string }[];
    }>(`/projects/${pid}/models/schema-diag`);
  }
  /** Building footprint + site point as WGS84 GeoJSON (409 with no source IFC). */
  footprintGeojsonUrl(pid: string) {
    return this.url(`/projects/${pid}/models/footprint.geojson`);
  }
  /** Nearby municipal filings as a GeoJSON FeatureCollection (points). `city` is required. */
  permitsGeojsonUrl(pid: string, city: string) {
    return this.url(`/projects/${pid}/opendata/permits.geojson?city=${encodeURIComponent(city)}`);
  }
  /** Cut vs projection graphic state for one view template (weight, colour, pattern, halftone). */
  viewTemplateGraphics(pid: string, tid: string) {
    return this.json<{
      visible_count?: number;
      cut?: Record<string, unknown>;
      projection?: Record<string, unknown>;
    }>(`/projects/${pid}/view-templates/${encodeURIComponent(tid)}/graphics`);
  }
  /** Quality-evidence closeout: unresolved NCRs plus elements nobody inspected. */
  qualityTurnoverReadiness(pid: string) {
    return this.json<{
      ready: boolean; outstanding_count: number; unrecorded_count: number;
      coverage_pct: number; any_attached: boolean;
      outstanding_elements: { guid: string; open_items: unknown[] }[];
      unrecorded_elements: string[]; basis: string; message: string | null;
    }>(`/projects/${pid}/quality/turnover-readiness`);
  }
  };
}
