/** Model: the read side of the IFC model — capabilities, query, assets, exports, roundtrip,
 *  columnar stats and the live edit stream.
 *
 *  SCALE-SEAM ③. Route-group `/model`, the largest of the 219 groups in `client.ts` (29 methods).
 *  Picked by classifying every method by the route it calls — the `// --- section ---` comments label
 *  the start of a run and the file then continues into other domains, so they delimit nothing.
 *
 *  **This cut required moving `liveStream` into HttpCore, and that was the real work.** `modelStream`
 *  calls it and it was `private` on ApiClient. A mixin is a BASE of ApiClient, so it cannot see
 *  ApiClient's private members — exactly why `withAuthoring` recorded that "the SSE methods cannot
 *  follow yet". It is now `protected` on HttpCore, which also unblocks the notifications and
 *  drawing-markup streams for ④.
 *
 *  A mixin, so every `api.modelX(...)` call site resolves unchanged; `api/surface.test.ts` is what
 *  makes that checkable rather than hoped for.
 */
import { HttpCore, type LiveStream } from "./httpCore";
import type { ViewerLoadTiming, ProjectPulse } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withModel<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Model extends Base {
  /** Subscribe to the model-edit SSE stream; onMessage fires with the collab snapshot on each change. */
  modelStream(pid: string, onMessage: (snap: unknown) => void,
              onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/model/stream`, onMessage, onStatus);
  }

  // AUTH-VS: execute a recipe graph (visual node authoring) as one GUID-stable pass
  /** ASSET-REG — maintainable-asset register derived from the IFC (equipment/terminals/controls/transport). */
  modelAssets(pid: string) {
    type Tally = { count: number } & Record<string, string | number>;
    type Asset = { guid: string | null; name: string; ifc_class: string; type: string | null;
      discipline: string; category: string; storey: string | null };
    return this.json<{
      count: number; by_discipline: Tally[]; by_category: Tally[]; by_class: Tally[];
      assets: Asset[]; note: string;
    }>(`/projects/${pid}/model/assets`);
  }
  /** Seed the asset_register module from the model-derived assets (idempotent by tag). */
  seedModelAssets(pid: string) {
    return this.json<{ created: number; skipped: number; created_refs: string[]; note: string }>(
      `/projects/${pid}/model/assets/seed`, { method: "POST", body: "{}" });
  }
  /** MEP-EQUIP — the procurement equipment schedule from the IFC: procurable units grouped by class+type. */
  modelEquipment(pid: string) {
    type Tally = { count: number } & Record<string, string | number>;
    type Line = { ifc_class: string; type: string; discipline: string; count: number;
      spec: Record<string, unknown>; guids: (string | null)[] };
    return this.json<{
      line_count: number; unit_count: number; by_discipline: Tally[]; by_class: Tally[];
      lines: Line[]; note: string;
    }>(`/projects/${pid}/model/equipment`);
  }
  /** MEP-EQUIP SPEC-CONFLICT — cross-check the scheduled equipment against a specified-requirement set. */
  equipmentSpecCheck(pid: string, requirements: Record<string, Record<string, unknown>>) {
    type Row = { ifc_class: string; type: string; count: number; spec_key: string; expected: unknown; actual: unknown };
    return this.json<{
      conflict_count: number; missing_count: number; units_in_conflict: number;
      conflicts: Row[]; missing: Row[]; line_count: number; unit_count: number; note: string;
    }>(`/projects/${pid}/model/equipment/spec-check`, { method: "POST", body: JSON.stringify({ requirements }) });
  }
  /** SPACE-UTIL — occupancy capacity per IfcSpace at an area-per-person standard, rolled up by type. */
  modelSpaceUtilization(pid: string, areaPerPerson = 10) {
    type Row = { type: string; count: number; area_m2: number; capacity: number };
    return this.json<{
      space_count: number; total_area_m2: number; area_per_person: number; capacity_total: number;
      by_type: Row[]; spaces: { guid: string | null; name: string; type: string; area_m2: number; capacity: number }[]; note: string;
    }>(`/projects/${pid}/model/space-utilization?area_per_person=${encodeURIComponent(areaPerPerson)}`);
  }
  /** SPACE-UTIL — a headcount program ({space_type: headcount}) vs the modelled inventory → the area gap. */
  modelSpaceDemand(pid: string, program: Record<string, number>, areaPerPerson = 10) {
    type Row = { type: string; headcount: number; required_m2: number; supplied_m2: number; gap_m2: number; status: string };
    return this.json<{
      area_per_person: number; total_required_m2: number; total_supplied_m2: number; total_gap_m2: number;
      deficit_types: number; by_type: Row[]; note: string;
    }>(`/projects/${pid}/model/space-demand`, { method: "POST", body: JSON.stringify({ program, area_per_person: areaPerPerson }) });
  }
  /** DESIGN-METRICS — program-efficiency (floors/GFA/net-to-gross/unit count/area-by-type) + a deterministic
   * average-daylight-factor ESTIMATE from the model's own windows (CIBSE formula, not a ray-trace). */
  modelDesignMetrics(pid: string) {
    type TypeRow = { type: string; area_m2: number };
    return this.json<{
      floors: number; space_count: number; net_floor_area_m2: number; gross_floor_area_m2: number;
      net_to_gross: number; unit_count: number; avg_unit_m2: number; by_type: TypeRow[];
      daylight: {
        window_count: number; glazed_area_m2: number; window_to_floor_ratio: number;
        avg_daylight_factor_pct: number; band: "good" | "fair" | "limited"; estimate: boolean; note: string;
      };
      note: string;
    }>(`/projects/${pid}/model/design-metrics`);
  }
  /** TOPIC-BOARD — a kanban board over the BCF topics with QUERY-DSL smart filters over topic fields. */
  /** AUTH-CONSTRAINTS — validate the model's own constraint graph (broken hosts, dangling fills,
   * out-of-extent inserts, missing containment, level mismatches). */
  modelConstraints(pid: string) {
    return this.json<{
      issues: { kind: string; severity: string; guid: string; name: string; ifc_class: string; detail: string }[];
      issue_count: number; counts: Record<string, number>; errors: number; warnings: number;
      checked: { openings: number; elements_level_checked: number; storeys: number }; note: string;
    }>(`/projects/${pid}/model/constraints`);
  }
  /** SCHED-CALC — computed schedules extended with deterministic calculated-field columns. */
  /** WALL-ASSEMBLY THERMAL — every IfcMaterialLayerSet → R/U computed from the layers + per-layer takeoff. */
  modelAssemblyThermal(pid: string) {
    type Layer = { name: string; category: string | null; thickness_m: number; r_value: number };
    type Assembly = {
      name: string | null; element_count: number; guids: string[]; face_area_m2: number | null;
      layers: Layer[]; thickness_m: number; r_value: number; r_value_imperial: number; u_value: number | null;
      surface_films_r: number; takeoff: { material: string | null; thickness_m: number; volume_m3: number | null }[];
      note: string;
    };
    return this.json<{ assembly_count: number; assemblies: Assembly[]; note: string }>(
      `/projects/${pid}/model/assembly-thermal`);
  }
  /** PARCEL-IMPORT — cadastral parcel geometry (GeoJSON/WKT) → area/perimeter/centroid + FAR/coverage/
   * height compliance vs a zoning envelope. */
  /** FILL-MATRIX — category × property fill-rate pivot over the model; each property carries the blank GUIDs
   * (the selection a bulk edit fills) + worst_gaps (the biggest partially-filled fields). */
  modelFillMatrix(pid: string, minCount = 1) {
    type Prop = { pset: string; prop: string; filled: number; blank: number; fill_rate: number; blank_guids: string[]; selector: string };
    type Gap = { ifc_class: string; pset: string; prop: string; blank: number; fill_rate: number; blank_guids: string[] };
    return this.json<{
      element_count: number; class_count: number;
      classes: { ifc_class: string; count: number; property_count: number; properties: Prop[] }[];
      worst_gaps: Gap[]; note: string;
    }>(`/projects/${pid}/model/fill-matrix?min_count=${encodeURIComponent(minCount)}`);
  }
  /** PROGRESS-ROLLUP — % complete from as-built element presence, by IFC class / discipline / level /
   * overall, by count AND by value. */
  /** TESTFIT-ADJ — space adjacency graph + program-relation score + dimensional-compliance over IfcSpaces. */
  modelAdjacency(pid: string, program: {
    required_adjacent?: [string, string][]; forbidden?: [string, string][];
    dimensional?: { min_room_dim?: number; min_area?: number; min_ceiling_height?: number;
      by_type?: Record<string, { min_room_dim?: number; min_area?: number; min_ceiling_height?: number }> };
  } = {}) {
    type Space = { guid: string; name: string; type: string; min_dim: number; area: number; height: number; neighbors: string[] };
    return this.json<{
      space_count: number;
      adjacency: { edge_count: number; spaces: Space[] };
      program: {
        required_total: number; required_satisfied: number; required_pct: number | null;
        required_results: { a: string; b: string; satisfied: boolean }[];
        forbidden_violations: { rule: string; a: string; a_type: string; b: string; b_type: string }[];
        forbidden_ok: boolean;
      };
      dimensional: { checked: number; passed: number;
        violations: { guid: string; name: string; type: string; issues: string[] }[] };
      note: string;
    }>(`/projects/${pid}/model/adjacency`, { method: "POST", body: JSON.stringify(program) });
  }
  /** MASTER-BUILDER — the 8-step Master Builder Protocol run over the project's own data, grounded in place. */
  /** IFCPATCH-LIB — plan a per-storey split (feed a slice's GUIDs to the subset export). */
  modelSplitPlan(pid: string) {
    return this.json<{ storeys: Record<string, string[]>; counts: Record<string, number>;
      unassigned: string[]; unassigned_count: number; note: string }>(
      `/projects/${pid}/model/split-plan`);
  }
  /** AUTH-CONSTRAINTS ③ — detect L/T wall joins (resolution = the resolve_wall_joins edit recipe). */
  wallJoins(pid: string, tol?: number) {
    return this.json<{ joins: { kind: "L" | "T"; corner: number[]; through: string; stub: string;
      walls: string[] }[]; wall_count: number; counts: { L: number; T: number } }>(
      `/projects/${pid}/model/wall-joins${tol ? `?tol=${tol}` : ""}`);
  }
  /** INTEROP-RT — round-trip fidelity: serialize → reparse → compare, with a single verdict. */
  modelRoundtrip(pid: string) {
    return this.json<{ fidelity_ok: boolean; element_count: number;
      counts: { missing: number; added: number; changed: number };
      missing: string[]; added: string[];
      changed: { guid: string; class: string; aspects: string[] }[] }>(
      `/projects/${pid}/model/roundtrip`);
  }
  /** FAMILY-DEPTH ④ — the shared-parameter registry (registered params become schedule columns). */
  /** FAMILY-DEPTH ② — the effective (instance-over-type) property view for one element. */
  elementEffectiveProps(pid: string, guid: string) {
    return this.json<{ guid: string; type_guid: string | null; type_name: string | null;
      override_count: number;
      psets: Record<string, Record<string, { value: unknown; source: "instance" | "type";
        overridden: boolean; type_value: unknown }>> }>(
      `/projects/${pid}/model/element/${encodeURIComponent(guid)}/effective-props`);
  }
  /** FIN-PORTFOLIO — latest scenario per project side-by-side with governance state + the spread. */
  // --- model analysis (capabilities / query / LOD / envelope / MEP-extract / naming) --------------
  modelCapabilities(pid: string) {
    return this.json<{ supported_read_schemas: string[];
      loaded_model: { detected: string | null; supported: boolean | null; data_readable?: boolean; note: string };
      ifc5: { status: string; data_read?: boolean; geometry_read?: boolean; note: string } }>(
      `/projects/${pid}/model/capabilities`);
  }
  /** Download URL for the model element table in a columnar/graph format. */
  modelExportUrl(pid: string, fmt: "csv" | "jsonld" | "parquet") {
    return this.url(`/projects/${pid}/model/export.${fmt}`);
  }
  /** Download URL for the model geometry as a self-contained glTF 2.0 file (interchange). */
  modelGltfUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export.gltf`);
  }
  /** Download URL for the model geometry as a binary glTF (.glb) — the compact single-file interchange. */
  modelGlbUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export.glb`);
  }
  /** Download URL for a first-class IFC re-export — the current authored source IFC (GUID-stable). */
  modelIfcUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export.ifc`);
  }
  /** TAKEOFF-2D: measure + price regions traced on a 2D drawing at a calibrated scale (units/px). */
  /** Interning/columnar efficiency stats (dedup ratio + estimated RAM saved) — G1. */
  modelColumnarStats(pid: string) {
    return this.json<{ model_loaded: boolean; elements?: number; param_rows?: number;
      unique_strings?: number; dedup_ratio?: number | null; est_bytes_saved?: number;
      est_reduction_pct?: number | null }>(`/projects/${pid}/model/columnar/stats`);
  }
  /** Download URL for the EAV parameter table as Parquet (analytics) — G1. */
  modelParamsParquetUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export/params.parquet`);
  }
  /** Fast model summary — entity-type histogram from a streaming STEP scan (no full parse) — G3. */
  modelStepSummary(pid: string) {
    return this.json<{ ok: boolean; schema?: string | null; total_entities?: number;
      distinct_types?: number; file_size_bytes?: number;
      histogram?: { ifc_class: string; count: number }[] }>(`/projects/${pid}/model/step-summary`);
  }
  /** Inspect an uploaded VIM / G3D file (schema, buffers, geometry stats) — G2. */
  modelQueryViews(pid: string) {
    return this.json<{ views: { id: string; label: string }[] }>(`/projects/${pid}/model/query/views`);
  }
  modelQuery(pid: string, view?: string, groupBy = "ifc_class") {
    const qs = view ? `?view=${encodeURIComponent(view)}` : `?group_by=${encodeURIComponent(groupBy)}`;
    return this.json<{ model_scored: boolean; matched: number;
      rows: { group: string; value: number; count: number }[] }>(`/projects/${pid}/model/query${qs}`);
  }
  /** XLSX-ROUNDTRIP — download the GUID-keyed property table (chosen `Pset.Prop` columns) as CSV
   *  for editing in Excel/Sheets; re-import via `roundtripDiff` + the `set_props_by_guid` recipe. */
  async roundtripExport(pid: string, props: string[]) {
    const q = encodeURIComponent(props.join(","));
    const res = await fetch(this.url(`/projects/${pid}/model/roundtrip.csv?props=${q}`), { headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `export -> ${res.status}`); }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob()); a.download = "properties.csv"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
  /** XLSX-ROUNDTRIP — dry-run diff of an edited CSV/XLSX against the live model: what would change. */
  async roundtripDiff(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/model/roundtrip/diff`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `diff -> ${res.status}`); }
    return res.json() as Promise<{ checked: number; changes: { guid: string; pset: string; prop: string; old: string | null; new: string }[];
      unknown_guids: string[]; unchanged: number }>;
  }
  /** QUERY-DSL — select elements by a selector string (`IfcWall & Pset_WallCommon.FireRating=2HR &
   *  storey=L3`) → matching GUIDs + parsed predicates. One grammar for filter / isolate / scope. */
  modelSelect(pid: string, q: string, limit = 5000) {
    return this.json<{ query: string; matched: number; truncated: boolean; guids: string[];
      predicates: { field: string; op: string; value: string | null }[]; note?: string }>(
      `/projects/${pid}/model/select?q=${encodeURIComponent(q)}&limit=${limit}`);
  }
  /**
   * R39-VIEWER-OBS — one row per model load, including the loads that stalled or drew nothing.
   *
   * Lives here rather than in `client.ts` because that file is at its size pin, which is the friction
   * the ratchet exists to create; and as its own mixin it would have cost `client.ts` two lines it
   * does not have. Model-load telemetry belongs to the `/model` group anyway.
   *
   * Best-effort by contract: the caller drops the promise. A viewer must never be slowed, still less
   * broken, by the thing measuring it.
   */
  reportViewerLoad(pid: string, t: ViewerLoadTiming) {
    return this.json<{ recorded: boolean }>(`/projects/${pid}/model/load-timing`,
      { method: "POST", body: JSON.stringify(t) });
  }
  /** PROJECT PULSE — mapped inputs for the home rail. Fail-open per card; never POST renovation. */
  projectPulse(pid: string) {
    return this.json<ProjectPulse>(`/projects/${pid}/pulse`);
  }
  /** SMART-VIEWS — the project's saved property-driven view presets (name + selector + mode). */
  };
}
