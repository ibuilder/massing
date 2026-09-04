/** Model: the read side of the IFC model — capabilities, query, assets, exports, roundtrip,
 *  columnar stats, the live edit stream, the analytical frame, the semantic graph, and
 *  IFC5-style property-override layers.
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
 *
 *  SCALE-SEAM (85) adds model INGEST — *how does this project get its source model?*
 *  `uploadSourceIfc` and `importRvt` both return `source_ifc` and both set it; `rvtBridgeStatus`
 *  is the precondition for the second, reporting whether the paid Autodesk bridge is enabled and
 *  what it costs. That third one came here rather than to `entitlements.ts`: THAT mixin is the
 *  LAND-USE entitlements route group (`/projects/{pid}/entitlements/…`, planning approvals), not
 *  software licensing. Filing on the shared word would have been the same mistake as filing on a
 *  shared route prefix.
 *
 *  SCALE-SEAM (83) adds the check side — *does this model pass its checks?* The MODEL-CI check
 *  pack (run + latest badge source), the RULE-LIB rule library, RULE-LIB-2 geometric rules, and
 *  `rebarCheckCage`. The rebar method came on what it ANSWERS, not on its route: it verifies an
 *  authored cage against the ACI envelope, which is the same question `envelopeAudit` and
 *  `standardsCheck` above it ask. **Its two `/rebar/` siblings did NOT come** — `rebarBbs` and
 *  `rebarBbsCsvUrl` are a bar bending SCHEDULE, a quantity, and share only a route prefix and a
 *  `REBAR-RULES` doc tag with the check. Route kinship is precisely the reason ⓽ nearly filed
 *  `bidLevelingDetail` in `ai.ts`.
 *
 *  SCALE-SEAM ㊻ adds field-install verification — *is this element installed as designed?*
 *  Coverage, status write, deviation log. They were **not** contiguous (`uploadVerificationPhoto`
 *  sat between set and deviations). **The photo upload did NOT come** (PHOTO-PIN is parked).
 *  `askModel` stayed — that is NL-Q, not install status.
 *
 *  **SCALE-SEAM (94) adds two members of that question ㊻ did not name:** `verifyAsbuilt`
 *  stamps `Massing_AsBuilt` (the LOD-500 reliability layer) and `recordAsbuiltDimension` records a
 *  field-verified dimension with its variance against design. Both are ㊻'s own question — *is this
 *  element installed as designed?* — and neither was named in its header.
 *
 *  **SCALE-SEAM (95) adds element STATE — *what state are the model's elements in, and set it?***
 *  Two read/write pairs: `lodSummary`/`setLod` (element maturity 100→500) and `phasing`/`setPhase`
 *  (new / existing / demolish / temporary).
 *
 *  *`lodSummary` was a sibling separated from its own family:* this file already held
 *  `/model/lod/census`, `/lod/handover-readiness` and `/lod/assessment`, while the BASE distribution
 *  `/projects/{pid}/lod` stayed behind. The two pairs come together because they are the same
 *  question in the same shape — both return `{ total, <x>ed, prop, counts }`, both writers are
 *  `(pid, guids, <enum>, publish) → editIfc`, both readers are consumed by
 *  `viewer/tools/modelStatePanels.ts`, and both writers sit unwired and adjacent on
 *  `api/clientCallers.test.ts`'s UNCALLED allowlist.
 *
 *  **`authoring_matrix.py` disagrees, and it is worth saying why it loses.** It files `set_lod` under
 *  `data` and `set_phase` under `lifecycle`, because it categorises by the IFC OUTPUT each recipe
 *  writes — an LOD stage tag against `Massing_Phasing.Status`. Different property sets, same
 *  question. **That is (89)'s "storage is a HOW" trap**: "they write different psets" has the same
 *  shape as "they are all module records", and neither is a question.
 *
 *  *This also resolves what (94) deliberately left open.* That slice declined `setPhase` because
 *  taking the writer would have stranded `phasing()` in `client.ts` — the reader/writer split (87)
 *  had to undo. Both halves move together here, so nothing is separated and the objection is met
 *  rather than overridden.
 *
 *  *Not contiguous — the pairs sat at 271–279 and 293–301 with `ensureContexts` and `queryElements`
 *  between them. (88) recorded that as the strongest case for grouping by what methods ANSWER, since
 *  no prefix or positional split would ever find them together.*
 *
 *  **Two known members, not necessarily all of them.** This slice does not claim the question is now
 *  complete: it claims these two answer it and were missed. *The first draft said "finishes that
 *  question", which asserts a completeness nothing here established — and the PR description
 *  simultaneously claimed only "two known missed members". **Hedging in the review request while the
 *  artifact overstates is not scoping**; it puts the caveat where a reviewer sees it and the
 *  overstatement where every later reader will. Caught in review of #411.*
 *
 *  *Why ㊻ missed them: it split on the `/verification/*` ROUTE PREFIX, and these two go through
 *  `editIfc`, so they carry no `/verification` route to be found by. **A route-prefix split cannot
 *  see a recipe-based sibling of the same question.** They were also unmovable at the time —
 *  `editIfc` is declared on the `Authoring` mixin rather than `HttpCore`, so a mixin typed
 *  `Ctor<HttpCore>` does not compile; (92) diagnosed that, and this mixin now declares the shared
 *  contract from `./types`. That is the THIRD slice found to have left a method behind for this
 *  reason, after ⑲'s MEP pair (taken by (93)).*
 *
 *  **`setPhase` did NOT come, and `authoring_matrix.py` argues it should have.** Its `lifecycle`
 *  category is exactly these two plus `set_phase` — a COMPLETE category, which is the signal that
 *  decided (92)'s annotate slice. Declined here on two checkable grounds: `setPhase` tags a
 *  construction phase (new/existing/demolish/temporary), which is element state in the build
 *  sequence rather than install-versus-design (`Massing_Phasing.Status`, against `Massing_AsBuilt`
 *  and `Massing_AsBuiltDim` for these two); and **its read half `phasing()` is still in `client.ts`**,
 *  so taking the writer alone would repeat the reader/rollup split (87) had to undo.
 *
 *  *Precisely: `phasing()` is read by `viewer/tools/modelStatePanels.ts`, which is the phasing panel
 *  — it also colours by `Massing_Phasing.Status` — while `setPhase` is that panel's UNWIRED writer,
 *  sitting on `api/clientCallers.test.ts`'s UNCALLED allowlist. So they are a reader and its writer
 *  on one panel rather than two live call sites, which is the accurate version of the claim and
 *  still the reason not to separate them.*
 *  *A complete category is one vote, not a verdict — and "lifecycle" is a word (88) already caught
 *  misleading once.*
 *
 *  SCALE-SEAM ⓭ adds E57 scan ingest — *can we bring this scan in?* Status plus convert.
 *  Admin audit/error stayed.
 *
 *  SCALE-SEAM ⓳ adds publish history — *what changed between publishes?* Version list,
 *  element diff, cost delta, and the submit/approve/reject review gate. They were **not**
 *  contiguous (`reviewModelVersion` sat with share-token decisions). Clash imports stayed.
 */
import type { LiveStream } from "./httpCore";
import type { ViewerLoadTiming, ProjectPulse, PropLayer, ModelCiReport, NeedsEditIfc } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withModel<TBase extends Ctor<NeedsEditIfc>>(Base: TBase) {
  return class Model extends Base {
  /** Subscribe to the model-edit SSE stream; onMessage fires with the collab snapshot on each change. */
  modelStream(pid: string, onMessage: (snap: unknown) => void,
              onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/model/stream`, onMessage, onStatus);
  }

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
  /** Curated starter properties an engineer expects on common equipment classes before buyout. */
  equipmentStarterRequirements(pid: string) {
    return this.json<{ requirements: Record<string, Record<string, unknown>>; note: string }>(
      `/projects/${pid}/model/equipment/starter-requirements`);
  }
  /** Mint one product-data submittal per scheduled equipment type (idempotent by title). */
  equipmentToSubmittals(pid: string) {
    return this.json<{ created: { id: number; ref: string; title: string; ifc_class: string; count: number }[];
      created_count: number; skipped_existing: number; note: string }>(
      `/projects/${pid}/model/equipment/to-submittals`, { method: "POST", body: "{}" });
  }
  /** Equipment schedule as budget-suggestion rows, priced from the project's own price ledger. */
  equipmentBudgetLines(pid: string) {
    return this.json<{
      rows: { description: string; ifc_class: string; discipline: string; qty: number;
        unit: string; unit_cost: number | null; extended: number | null }[];
      line_count: number; priced_lines: number; priced_total: number; note: string;
    }>(`/projects/${pid}/model/equipment/budget-lines`);
  }
  /** Where the triangle budget goes, and what a coarse proxy would save. */
  lodCensus(pid: string, maxElements = 5000) {
    return this.json<{
      status: string; status_meaning: string; elements_examined: number; total_triangles: number;
      by_class: { ifc_class: string; elements: number; triangles: number;
        pct_triangles: number; small_part: boolean }[];
      unmeshable_count: number; capped: boolean; cap: number | null;
      plan: { status: string; proxied?: string[]; triangles_saved?: number | null;
        pct_saved?: number | null; reason?: string };
    }>(`/projects/${pid}/model/lod/census?max_elements=${maxElements}`);
  }
  /** LOD 500 handover as a work list (unverified / out of tolerance / thin information). */
  lodHandoverReadiness(pid: string) {
    return this.json<{
      model_scored: boolean; elements: number; lod500: number; readiness_pct: number;
      by_reason: Record<string, number>; actions: Record<string, string>;
      by_discipline: { discipline: string; elements: number; lod500: number; readiness_pct: number }[];
      gaps: { guid: string; ifc_class: string; discipline: string; reason: string; action: string }[];
      truncated: number; note: string;
    }>(`/projects/${pid}/lod/handover-readiness`);
  }
  /** ffeBom — furnishings bill of materials from placed furniture. */
  ffeBom(pid: string) {
    return this.json<{
      total: number; line_count: number;
      items: { item: string; ifc_class: string; count: number; storeys: string[] }[];
      note: string;
    }>(`/projects/${pid}/ffe-bom`);
  }
  /** Spec-section breadcrumbs stamped on the model (`Pset_Massing_SpecLink`). */
  specLinks(pid: string) {
    return this.json<{
      sections: { section: string; title: string | null; count: number; guids: string[] }[];
      linked: number; unlinked: number; total: number; pset: string;
    }>(`/projects/${pid}/spec-links`);
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
  /** AUTH-CONSTRAINTS — validate the model's own constraint graph (broken hosts, dangling fills,
   * out-of-extent inserts, missing containment, level mismatches). */
  modelConstraints(pid: string) {
    return this.json<{
      issues: { kind: string; severity: string; guid: string; name: string; ifc_class: string; detail: string }[];
      issue_count: number; counts: Record<string, number>; errors: number; warnings: number;
      checked: { openings: number; elements_level_checked: number; storeys: number }; note: string;
    }>(`/projects/${pid}/model/constraints`);
  }
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
  /** FAMILY-DEPTH ② — the effective (instance-over-type) property view for one element. */
  elementEffectiveProps(pid: string, guid: string) {
    return this.json<{ guid: string; type_guid: string | null; type_name: string | null;
      override_count: number;
      psets: Record<string, Record<string, { value: unknown; source: "instance" | "type";
        overridden: boolean; type_value: unknown }>> }>(
      `/projects/${pid}/model/element/${encodeURIComponent(guid)}/effective-props`);
  }
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
  /** IFC5 JSON data layer (ifcJSON by default, or the IFCX node list). Geometry is out of scope. */
  modelExportIfcxUrl(pid: string, flavor: "ifcjson" | "ifcx" = "ifcjson") {
    const q = flavor === "ifcx" ? "?flavor=ifcx" : "";
    return this.url(`/projects/${pid}/model/export.ifcx${q}`);
  }
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
  /** The saved model-query views available for this project (id + label). */
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

  /** analyticalSummary — IfcStructuralAnalysisModel derived from the physical frame. */
  analyticalSummary(pid: string) {
    return this.json<{
      analysis_models: { guid: string; name: string | null; predefined_type: string | null }[];
      curve_members: number; surface_members: number; point_connections: number;
      load_cases: (string | null)[]; load_groups: (string | null)[]; load_actions?: number;
      supports?: number; has_model: boolean;
    }>(`/projects/${pid}/analytical`);
  }

  /** structureSolve — gravity load case on analytical members plus a determinate statics solve. */
  structureSolve(pid: string, opts?: {
    liveOccupancy?: string; sdlPsf?: number; slabThicknessIn?: number;
    tributaryFt?: number; grossAreaSf?: number; eKsi?: number; iIn4?: number;
  }) {
    const q = new URLSearchParams();
    if (opts?.liveOccupancy) q.set("live_occupancy", opts.liveOccupancy);
    if (opts?.sdlPsf != null) q.set("sdl_psf", String(opts.sdlPsf));
    if (opts?.slabThicknessIn != null) q.set("slab_thickness_in", String(opts.slabThicknessIn));
    if (opts?.tributaryFt != null) q.set("tributary_ft", String(opts.tributaryFt));
    if (opts?.grossAreaSf != null) q.set("gross_area_sf", String(opts.grossAreaSf));
    if (opts?.eKsi != null) q.set("e_ksi", String(opts.eKsi));
    if (opts?.iIn4 != null) q.set("i_in4", String(opts.iIn4));
    const qs = q.toString();
    type Diagram = { x_ft: number; shear_kip: number; moment_kipft: number; deflection_in: number };
    type Beam = {
      name: string; guid: string; length_ft: number;
      service: {
        reaction_kip: number; shear_max_kip: number; moment_max_kipft: number;
        deflection_in: number; deflection_limit_in: number; deflection_ok: boolean; diagram: Diagram[];
      };
      factored: Beam["service"];
    };
    return this.json<{
      has_analytical: boolean; message?: string;
      load_case?: {
        name: string; dead_klf: number; live_klf: number; service_klf: number;
        factored_lrfd_klf: number; dead_psf: number; live_psf: number; tributary_ft: number;
        governing_combo: string;
      };
      counts?: { beams: number; columns: number; total_beam_length_ft: number };
      governing_beam?: Beam | null; beams?: Beam[];
      columns_axial?: {
        service_total_kip: number; factored_lrfd_kip: number; storeys: number;
        column_count: number; note: string;
      } | null;
      reactions?: { sum_beam_service_kip: number };
      assumptions?: Record<string, unknown>; disclaimer?: string;
    }>(`/projects/${pid}/structure/solve${qs ? `?${qs}` : ""}`);
  }

  /** openseesTclUrl — download URL for the analytical frame as an OpenSees (.tcl) model. */
  openseesTclUrl(pid: string) {
    return this.url(`/projects/${pid}/structure/opensees.tcl`);
  }
  /** codeAsterMailUrl — the analytical frame as a Code_Aster mesh (.mail, SI metres). */
  codeAsterMailUrl(pid: string) {
    return this.url(`/projects/${pid}/structure/code-aster.mail`);
  }

  /** structureLateral — ASCE 7 wind plus seismic lateral analysis (base shear to story forces). */
  structureLateral(pid: string, opts?: {
    sds?: number; sd1?: number; r?: number; ie?: number; system?: string;
    windSpeedMph?: number; exposure?: string; deadPsf?: number; areaSf?: number;
  }) {
    const q = new URLSearchParams();
    const map: Record<string, number | string | undefined> = {
      sds: opts?.sds, sd1: opts?.sd1, r: opts?.r, ie: opts?.ie, system: opts?.system,
      wind_speed_mph: opts?.windSpeedMph, exposure: opts?.exposure,
      dead_psf: opts?.deadPsf, area_sf: opts?.areaSf,
    };
    for (const [k, v] of Object.entries(map)) if (v != null) q.set(k, String(v));
    const qs = q.toString();
    type Story = { level: number; height_ft: number; force_kip: number; shear_kip: number };
    return this.json<{
      story_count: number; area_sf: number | null; dead_psf: number; story_weight_kip: number;
      seismic: { method: string; period_s: number; k: number; Cs: number; seismic_weight_kip: number;
                 base_shear_kip: number; overturning_kipft: number; stories: (Story & { cvx: number; weight_kip: number })[] };
      wind: { method: string; qh_psf: number; base_shear_kip: number; overturning_kipft: number;
              stories: (Story & { trib_ft: number; pressure_psf: number })[] };
      governing: { system: string; base_shear_kip: number };
      disclaimer: string;
    }>(`/projects/${pid}/structure/lateral${qs ? `?${qs}` : ""}`);
  }

  /** modelGraphStats — IFC relationship graph: node and edge counts by relation. */
  modelGraphStats(pid: string) {
    return this.json<{ nodes: number; edges: number; by_rel: Record<string, number> }>(`/projects/${pid}/graph`);
  }
  /** graphNeighbors — multi-hop neighbors of one GlobalId in the IFC relationship graph. */
  graphNeighbors(pid: string, guid: string, depth = 1) {
    return this.json<{
      root: string; found: boolean; depth?: number; neighbor_count?: number;
      nodes: { guid: string; class: string; name: string | null }[];
      edges: { from: string; to: string; rel: string }[];
      paths: { guid: string; class: string; name: string | null; path: { rel: string; dir: string; to: string }[] }[];
    }>(`/projects/${pid}/graph/neighbors?guid=${encodeURIComponent(guid)}&depth=${depth}`);
  }
  /** docGraph — spec-section and document nodes linked to the elements they govern. */
  docGraph(pid: string) {
    return this.json<{
      spec_sections: { system: string | null; code: string; title: string; elements: string[] }[];
      documents: { name: string; sheet: string; elements: string[] }[];
      counts: { spec_sections: number; documents: number; edges: number };
      by_rel: Record<string, number>;
    }>(`/projects/${pid}/doc-graph`);
  }

  /** getLayers — IFC5-style property-override layers (non-destructive composition). */
  getLayers(pid: string) {
    return this.json<{ layers: PropLayer[] }>(`/projects/${pid}/layers`);
  }
  /** putLayers — replace the project's property-override layer stack. */
  putLayers(pid: string, layers: PropLayer[]) {
    return this.json<{ layers: PropLayer[] }>(`/projects/${pid}/layers`, { method: "PUT", body: JSON.stringify({ layers }) });
  }
  /** resolveLayers — effective properties after the layer stack, plus conflicts. */
  resolveLayers(pid: string) {
    return this.json<{
      layers: { name: string; enabled: boolean; overrides: number }[];
      overrides: { guid: string; pset: string; prop: string; base: unknown; effective: unknown; winning_layer: string; setters: string[] }[];
      conflicts: { guid: string; pset: string; prop: string; winning_layer: string; values: { layer: string; value: unknown }[] }[];
      effective_count: number; conflict_count: number;
    }>(`/projects/${pid}/layers/resolve`);
  }
  /** bakeLayers — write the winning layer overrides into the IFC and publish. */
  bakeLayers(pid: string) {
    return this.json<{ baked: number; publish?: string; message?: string }>(`/projects/${pid}/layers/bake`, { method: "POST", body: JSON.stringify({ publish: true }) });
  }

  /** layoutPoints — georeferenced field setout (grids, columns, footings, openings, walls). */
  layoutPoints(pid: string, classes?: string) {
    const q = classes ? `?classes=${encodeURIComponent(classes)}` : "";
    return this.json<{ count: number; by_class: Record<string, number>; truncated: boolean; note: string;
      points: { number: string; e: number; n: number; z: number; description: string; kind: string;
        ifc_class: string; guid: string }[] }>(`/projects/${pid}/layout/points${q}`);
  }
  /** layoutCsvUrl — PENZD/PNEZD points-CSV download URL for total stations. */
  layoutCsvUrl(pid: string, order: "PENZD" | "PNEZD" = "PENZD", delimiter = ",", classes?: string) {
    const q = new URLSearchParams({ order, delimiter, ...(classes ? { classes } : {}) }).toString();
    return this.url(`/projects/${pid}/layout/points.csv?${q}`);
  }
  /** layoutDxfUrl — layered DXF layout-drawing download URL for floor printers. */
  layoutDxfUrl(pid: string, classes?: string) {
    return this.url(`/projects/${pid}/layout.dxf${classes ? `?classes=${encodeURIComponent(classes)}` : ""}`);
  }
  /** layoutVerify — as-installed total-station shots against the design setout. */
  layoutVerify(pid: string, measured: { number: string; e: number; n: number; z: number }[], toleranceM = 0.02) {
    return this.json<{ tolerance_m: number; checked: number; in_tolerance: number; max_deviation_m: number;
      out_of_tolerance: { number: string; guid: string; ifc_class: string; deviation_m: number }[]; note: string }>(
      `/projects/${pid}/layout/verify`, { method: "POST", body: JSON.stringify({ measured, tolerance_m: toleranceM }) });
  }

  /** loadsDefaults — storey names/count and interior-column count for a gravity takedown. */
  loadsDefaults(pid: string) {
    return this.json<{ storey_names: string[]; storey_count: number; column_count: number }>(
      `/projects/${pid}/loads/defaults`);
  }
  /** loadsTakedown — preliminary gravity takedown to per-column/footing service and factored axial. */
  loadsTakedown(pid: string, params: { floor_area_sf?: number; storey_count?: number; occupancy?: string;
      column_count?: number; sdl_psf?: number; slab_thickness_in?: number; storeys?: unknown[] }) {
    return this.json<{ assumptions: Record<string, number>;
      storeys: { name: string; occupancy: string; area_sf: number; col_dead_kip: number; col_live_kip: number }[];
      column: { service_dead_kip: number; service_live_kip: number; service_total_kip: number;
        factored_lrfd_kip: number; factored_asd_kip: number };
      footing: { service_total_kip: number; factored_lrfd_kip: number };
      combinations: { governing_lrfd: { combo: string; kips: number }; governing_asd: { combo: string; kips: number } };
      disclaimer: string }>(`/projects/${pid}/loads/takedown`, { method: "POST", body: JSON.stringify(params) });
  }

  /** viewTemplates — reusable layered view presets (class visibility, isolate, stacked colors). */
  viewTemplates(pid: string) {
    return this.json<{ templates: { id: string; name: string; hide_classes: string[];
      isolate: string | null; rules: { selector: string; color: string }[] }[] }>(
      `/projects/${pid}/view-templates`);
  }
  /** saveViewTemplates — replace the project's saved view-template list. */
  saveViewTemplates(pid: string, templates: { id?: string; name: string; hide_classes?: string[];
    isolate?: string | null; rules?: { selector: string; color: string }[] }[]) {
    return this.json<{ saved: number }>(`/projects/${pid}/view-templates`,
      { method: "PUT", body: JSON.stringify({ templates }) });
  }
  /** resolveViewTemplate — visible GUIDs and colors after applying one view template. */
  resolveViewTemplate(pid: string, tid: string) {
    return this.json<{ template: string; name: string | null; visible: string[]; visible_count: number;
      hidden_count: number; colors: Record<string, string>; colored_count: number; note: string }>(
      `/projects/${pid}/view-templates/${encodeURIComponent(tid)}/resolve`);
  }

  /** verificationCoverage — installed/verified % vs the model total, plus deviation count. */
  verificationCoverage(pid: string) {
    return this.json<{ total_elements: number; tracked: number; verified: number; installed: number;
      deviations: number; verified_pct: number; installed_pct: number; by_status: Record<string, number> }>(
      `/projects/${pid}/verification/coverage`);
  }
  /** setVerification — write an element's field-verification status (installed | verified | deviation | pending). */
  setVerification(pid: string, guid: string, body: { status: string; note?: string }) {
    return this.json<{ guid: string; status: string; ifc_class?: string }>(
      `/projects/${pid}/verification/${guid}`, { method: "PUT", body: JSON.stringify(body) });
  }
  /** verificationDeviations — elements flagged as not matching design. */
  verificationDeviations(pid: string) {
    return this.json<{ guid: string; ifc_class?: string; storey?: string; note?: string }[]>(
      `/projects/${pid}/verification/deviations`);
  }

  /** e57Status — whether server-side E57 to .xyz conversion is available. */
  e57Status() {
    return this.json<{ available: boolean; max_points: number; message: string }>(`/convert/e57/status`);
  }
  /** convertE57 — upload an .e57 scan and get a decimated .xyz point cloud back. */
  async convertE57(file: File): Promise<Blob> {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert`), { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `convert failed (${res.status})`);
    return res.blob();
  }
  /** MODEL-PUBLISH — the review gate over model versions: submit | approve | reject (409 on an
   * illegal transition). The file pointer is never touched — this is the QA record. */
  reviewModelVersion(pid: string, version: number, action: "submit" | "approve" | "reject", note?: string) {
    return this.json<{ version: number; review_status: string; reviewed_by: string | null;
      reviewed_at: string; review_note: string | null }>(
      `/projects/${pid}/versions/${version}/review`,
      { method: "POST", body: JSON.stringify({ action, note }) });
  }
  /** Model version history (one snapshot per publish), WITH its review state. The four review keys
   *  are not new server work — this type declared 4 of the 8 keys `versions.history` has returned
   *  since R18, so the record was discarded here (see `viewer/tools/modelReviewPanel.ts`). */
  modelVersions(pid: string) {
    return this.json<{ version: number; element_count: number; note: string | null; created_at: string | null;
      review_status: "draft" | "in_review" | "approved"; reviewed_by: string | null;
      reviewed_at: string | null; review_note: string | null }[]>(`/projects/${pid}/versions`);
  }
  /** Diff two model versions — added/removed/modified elements (with change labels) + unchanged count. */
  versionDiff(pid: string, a: number, b: number) {
    return this.json<{
      from: number; to: number; added: string[]; removed: string[];
      modified: { guid: string; name: string | null; ifc_class: string | null; changes: string[];
        changed_properties?: { property: string; status: "added" | "removed" | "changed" }[] }[];
      modified_available: boolean; property_detail_available?: boolean;
      added_count: number; removed_count: number; modified_count: number; unchanged_count: number;
    }>(`/projects/${pid}/versions/diff?a=${a}&b=${b}`);
  }
  /** REVISION-DELTA — conceptual cost impact of a revision (added priced, removed counted, modified flagged). */
  versionCostDelta(pid: string, a: number, b: number) {
    return this.json<{
      from: number; to: number;
      added: { count: number; priced_count: number; cost: number;
        lines: { ifc_class: string; count: number; unit: string; quantity: number; rate: number; amount: number }[];
        unpriced: { ifc_class: string; count: number }[] };
      removed: { count: number; by_class: { ifc_class: string; count: number; discipline: string }[]; note: string };
      requantified: { count: number; sample: { guid: string; name: string | null; ifc_class: string | null }[]; note: string };
      summary: { added_count: number; removed_count: number; requantified_count: number; added_cost: number };
      note: string;
    }>(`/projects/${pid}/versions/cost-delta?a=${a}&b=${b}`);
  }

  // SCALE-SEAM (81) — *what IFC class should these generic elements be?* It sat under the
  // turnover/G704 banner in `client.ts`, separated by a blank line, with nothing to do with
  // substantial completion. A model question filed wherever the nearest banner happened to be.
  ifcClassify(pid: string) {
    return this.json<{ suggestions: { guid?: string; name: string; current_class: string;
      suggested_class: string; confidence: string; reason: string }[]; count: number;
      generic_elements: number; by_target_class: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/ifc/classify`, { method: "POST", body: JSON.stringify({}) });
  }

  // SCALE-SEAM (82) — *how good is this model, measured against a standard?* Five audits that
  // sat under a `// --- Responsibility matrix (RACI / DACI) ---` banner in `client.ts`, which
  // described four of the thirteen methods beneath it. `lodAssessment` joins `lodCensus` and
  // `lodHandoverReadiness`, which were already here.
  standardsCheck(pid: string, standard: "iso19650" | "cobie" | "ids" | "uniclass") {
    return this.json<{ standard: string; label?: string; score?: number;
      findings?: { level: string; text: string; reference: string }[];
      recommendations?: string[]; error?: string; note?: string }>(
      `/projects/${pid}/standards/check?standard=${standard}`);
  }
  /** BIM KPI scorecard — per-category grade plus a scored/good/warn/poor/na summary and health percentage. */
  bimKpiScorecard(pid: string) {
    return this.json<{
      categories: { key: string; label: string; grade: string; headline: string;
        metrics: Record<string, number | null> }[];
      summary: { scored: number; good: number; warn: number; poor: number; na: number; health_pct: number | null };
      model_scored: boolean; note: string }>(`/projects/${pid}/bim-kpi/scorecard`);
  }
  /** openBIM quality: LOIN scoring (coverage, coordination) and export health, optionally scoped to one use case. */
  openbimQuality(pid: string, useCase?: string) {
    const qs = useCase ? `?use_case=${encodeURIComponent(useCase)}` : "";
    return this.json<{
      loin: { total: number; max_score: number; avg_score: number; coordinated_pct: number | null;
        distribution: Record<string, number>; facet_coverage_pct: Record<string, number | null> };
      export_health: { total: number; proxy_count: number; overall: string;
        checks: { key: string; label: string; pct: number | null; grade: string }[] };
      bsdd: { total: number; classified: number; alignment_pct: number | null };
      ids?: { compliance_pct: number | null; applicable_total: number; passing_total: number;
        specs: { name: string; ifc_class: string; applicable: number; passing: number; pct: number | null }[] };
      use_case: string | null }>(`/projects/${pid}/openbim/quality${qs}`);
  }
  /** LOD assessment — element distribution and average LOD per discipline. `using_default` marks a model scored against the fallback rules. */
  lodAssessment(pid: string) {
    return this.json<{ model_scored: boolean; elements: number; using_default: boolean;
      distribution: Record<string, number>;
      by_discipline: { discipline: string; elements: number; avg_lod: string }[] }>(
      `/projects/${pid}/lod/assessment`);
  }
  /** Envelope audit — how many envelope elements were checked and how many comply, with the per-element verdict. */
  envelopeAudit(pid: string) {
    return this.json<{ total: number; checked: number; compliant: number; compliance_pct: number | null;
      results: { name: string; element_type: string; compliant: boolean | null }[] }>(
      `/projects/${pid}/envelope/audit`);
  }

  // --- How does this project get its source model? Upload, the paid RVT bridge, and whether that bridge is available ---
  /** Upload an IFC as the project's source model (sets source_ifc + publishes) — what lights up
   *  drawings, clash/IDS, energy, exports, and authoring for the project. */
  async uploadSourceIfc(pid: string, file: File, publish = true) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/source-ifc?publish=${publish}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `upload -> ${res.status}`); }
    return res.json() as Promise<{ source_ifc: string; publish?: string }>;
  }
  /** Import a native .rvt via the paid APS bridge (must confirm cost). 501 off · 402 unconfirmed. */
  async importRvt(pid: string, file: File, confirmCost: boolean) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/import/rvt?confirm_cost=${confirmCost}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `rvt import -> ${res.status}`); }
    return res.json() as Promise<{ source_ifc: string; size: number; source: string; publish?: string }>;
  }
  /** Is the optional paid Revit→IFC bridge configured? (+ cost warning / free alternative text). */
  rvtBridgeStatus() {
    return this.json<{ enabled: boolean; activity_configured: boolean; cost_warning: string;
      free_alternative: string; message: string }>(`/bridge/rvt/status`);
  }

  // --- Does this model pass its checks? Check pack, rule library, geometric rules, rebar cage ---
  /** MODEL-CI — run the model check pack → pass/warn/fail report + badge (persisted). With
   *  `createTopics`, each failing check becomes an open coordination Topic (BCF-model). */
  ciRun(pid: string, createTopics = false) {
    return this.json<ModelCiReport>(
      `/projects/${pid}/ci/run${createTopics ? "?create_topics=true" : ""}`, { method: "POST" });
  }
  /** MODEL-CI — the project's latest check-pack report (the badge source). */
  ciLatest(pid: string) {
    return this.json<ModelCiReport>(`/projects/${pid}/ci/latest`);
  }
  /** RULE-LIB — check the loaded model against the user-authored rule library → per-rule pass/fail
   *  + offending GUIDs + a by-severity rollup. */
  rulesRun(pid: string) {
    return this.json<{ model_scored: boolean; total_rules: number; failing_rules?: number;
      total_violations?: number; by_severity?: Record<string, number>; note?: string;
      rules: { id: string; name: string; severity: string; scope: string; require: string;
        scoped: number; passed: number; failed: number; fail_guids: string[]; status: string }[] }>(
      `/projects/${pid}/rules/run`);
  }
  /** RULE-LIB-2 — geometric rule checks over the model's baked AABBs (clearance / escape-distance /
   *  clear-width). Omit `checks` for the server's starter set. */
  rulesGeometryRun(pid: string, checks?: { kind: string; scope: string; [k: string]: unknown }[]) {
    return this.json<{ violation_total: number; by_severity: Record<string, number>;
        results: { id?: string; kind: string; name: string; severity: string; passed: boolean;
        checked: number; note?: string; basis?: string;
        violations: { guid: string; name?: string; detail: string; distance_m?: number;
          width_m?: number; blocking?: (string | null)[] }[] }[] }>(
      `/projects/${pid}/rules/geometry/run`,
      { method: "POST", body: JSON.stringify(checks?.length ? { checks } : {}) });
  }
  /** REBAR-RULES — verify a column's authored cage against the ACI envelope (bar count, tie spacing). */
  rebarCheckCage(pid: string, column: string) {
    return this.json<{ checked: boolean; longitudinal_bars?: number; ties?: number;
      violations: string[]; params: { bar_size: string; tie_size: string; tie_spacing: number;
        governing: string; rule: string; min_longitudinal_bars: number } }>(
      `/projects/${pid}/rebar/check?column=${encodeURIComponent(column)}`);
  }
  /** W11 G2: record a field-verified as-built dimension (+ variance vs design) on the selection. */
  recordAsbuiltDimension(pid: string, guids: string[], dimension: string, measured: number, design?: number, publish = true) {
    return this.editIfc(pid, "record_asbuilt_dimension", { guids, dimension, measured, ...(design != null ? { design } : {}) }, publish);
  }
  /** W11 G1: stamp elements as field-verified as-built (Massing_AsBuilt) — the LOD-500 reliability layer. */
  verifyAsbuilt(pid: string, guids: string[], opts: { verified_by?: string; method?: string; note?: string } = {}, publish = true) {
    return this.editIfc(pid, "verify_asbuilt", { guids, ...opts }, publish);
  }
  /** W11 F0: element LOD-stage distribution (100/200/300/350/400/500/unset). */
  lodSummary(pid: string) {
    return this.json<{ total: number; staged: number; prop: string;
      counts: Record<"100" | "200" | "300" | "350" | "400" | "500" | "UNSET", number> }>(
      `/projects/${pid}/lod`);
  }
  /** W11 F0: tag elements with a LOD stage (element maturity 100→500). */
  setLod(pid: string, guids: string[], stage: "100" | "200" | "300" | "350" | "400" | "500", publish = true) {
    return this.editIfc(pid, "set_lod", { guids, stage }, publish);
  }
  /** W10-8: element phase/status distribution (new · existing · demolish · temporary · unset). */
  phasing(pid: string) {
    return this.json<{ total: number; phased: number; prop: string;
      counts: Record<"NEW" | "EXISTING" | "DEMOLISH" | "TEMPORARY" | "UNSET", number> }>(
      `/projects/${pid}/phasing`);
  }
  /** W10-8: tag elements with a construction phase (new | existing | demolish | temporary). */
  setPhase(pid: string, guids: string[], phase: "new" | "existing" | "demolish" | "temporary", publish = true) {
    return this.editIfc(pid, "set_phase", { guids, phase }, publish);
  }
  };
}
