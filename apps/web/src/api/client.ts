/** Typed client for the backend API (guide §7). Geometry comes from .frag; all element
 *  metadata and work artifacts (pins/RFIs/viewpoints) come from here. */
import { withAuth } from "./auth";
import { withAuthoring } from "./authoring";
import { withConnections } from "./connections";
import { withDrawingSet } from "./drawingSet";
import { withDrawingSheets } from "./drawingSheets";
import { withElements } from "./elements";
import { withModels } from "./models";
import { withDocuments } from "./documents";
import { withAccounting } from "./accounting";
import { withMep } from "./mep";
import { withTopics } from "./topics";
import { withAi } from "./ai";
import { withEvm } from "./evm";
import { withOperations } from "./operations";
import { withClientPortal } from "./clientPortal";
import { withCreDeal } from "./creDeal";
import { withAnnotate } from "./annotate";
import { withResilience } from "./resilience";
import { withResponsibility } from "./responsibility";
import { withCodeCheck } from "./codecheck"; import { withDealMemory } from "./dealMemory";
import { withPdfTools } from "./pdfTools";
import { withIds } from "./ids";
import { withSpecialty } from "./specialty";
import { withPrecon } from "./precon";
import { withEntitlements } from "./entitlements";
import { withRisk } from "./risk";
import { withMarkup } from "./markup";
import { withSync } from "./sync";
import { withCost } from "./cost";
import { withRoutines } from "./routines";
import { withContracts } from "./contracts";
import { withDesignOptions } from "./designOptions";
import { withFinance } from "./finance";
import { withLibrary } from "./library";
import { withAssetRights } from "./assetRights";
import { withDocQa } from "./docqa";
import { HttpCore } from "./httpCore";
import { withModel } from "./model";
import { withEstimate } from "./estimate";
import { withProcurement } from "./procurement";
import { withProforma } from "./proforma";
import { withModules } from "./modules";
import { withSchedule } from "./schedule";

// DTO types live in ./types (extracted from this file). Re-export them so the many
// `import { … } from "../api/client"` sites across the app keep resolving unchanged.
export * from "./types";
// `liveStream` + its LiveStream handle moved into HttpCore so a MIXIN can reach them: a mixin is a
// BASE of ApiClient and cannot see ApiClient's `private` members, which blocked every SSE method
// from extraction. Re-exported because drawings.ts imports the type as
// `import("../api/client").LiveStream`.
export type { LiveStream } from "./httpCore";
// The module-graph DTOs travelled with the /modules methods in SCALE-SEAM ④; re-exported because
// portal/panels/moduleGraph.ts imports them as `from "../../api/client"`.
export type { ModuleGraph, ModuleGraphEdge, ModuleGraphNode } from "./modules";
export * from "./authoring";
export * from "./library";
export type { ClashResult } from "./clash";
import type {
  Dashboard,
  DisciplineTree, EnergyResult, ModulePin, RoomAllocation,
  PropMapRule,
    SpecManual, WorkItem, VitalsPayload,
    DiligenceReadiness, MasterBuilderBrief, PrequalScores,
    SpineTraceability } from "./types";


// Transport (baseUrl, token, json/_pdfPost/url/health) lives in HttpCore; ApiClient adds the typed
// domain methods below. Every `api.method()` call site is unchanged by the split.
export class ApiClient extends withAnnotate(withCreDeal(withClientPortal(withResilience(withResponsibility(withOperations(withAccounting(withDealMemory(withPdfTools(withCodeCheck(withSpecialty(withIds(withEvm(withRisk(withEntitlements(withPrecon(withAi(withTopics(withMep(withDocuments(withModels(withElements(withDrawingSheets(withDrawingSet(withMarkup(withSync(withConnections(withDocQa(withFinance(withContracts(withAuth(withProforma(withDesignOptions(withRoutines(withCost(withProcurement(withEstimate(withModules(withModel(withSchedule(withLibrary(withAssetRights(withAuthoring(HttpCore))))))))))))))))))))))))))))))))))))))))))) {
  /**
   * R22-PHOTO-CV — attach a field photo to an element and get the server's read on it back.
   *
   * The endpoint has existed since the verification router shipped and, until now, **had no caller
   * in this app at all** — it appeared only in the generated `schema.d.ts`. So the photo analysis
   * built on top of it (quality gate, change screening, object detection) was reachable by API but
   * not by anyone using the product. This is the front door.
   *
   * The response carries three separately-hedged answers; use `photoVerdict` in `ui/photoVerdict.ts`
   * to render them rather than reading the fields raw, because the qualifiers matter and are easy to
   * drop. `quality` is trustworthy in both directions, `change` is a screening signal only, and
   * `detected` is absent unless the deployment has a model configured.
   */
  async uploadVerificationPhoto(pid: string, guid: string, file: File | Blob, name = "photo.jpg") {
    const fd = new FormData(); fd.append("file", file, name);
    const r = await fetch(this.url(`/projects/${pid}/verification/${encodeURIComponent(guid)}/photo`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<import("../ui/photoVerdict").PhotoUploadResult>;
  }
  /** 3D-HERO: pin a captured viewer screenshot as the project's hero image (page 2 of the package PDF). */
  async uploadHero(pid: string, image: Blob) {
    const fd = new FormData(); fd.append("file", image, "hero.png");
    const r = await fetch(this.url(`/projects/${pid}/hero`), { method: "PUT", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<{ stored: boolean; bytes: number }>;
  }
  meta(pid: string) {
    return this.json<{ schema: string; counts: Record<string, number>; facets: { classes: string[]; storeys: string[] } }>(
      `/projects/${pid}/properties/meta`,
    );
  }

  /** The unified discipline tree (colors + IFC-class→discipline map). Project-independent, so cached
   * for the session — the viewer, model browser, and any legend share one served vocabulary. */
  private _discTree?: Promise<DisciplineTree>;
  disciplineTree(): Promise<DisciplineTree> {
    return (this._discTree ??= this.json<{ tree: DisciplineTree }>(`/reference/disciplines`).then((r) => r.tree));
  }

  /** Batch 5D heatmap: bucket every element GUID by schedule %-complete (by=progress) or cost
   *  variance (by=cost), for coloring the whole model. */
  elements5dMap(pid: string, by: "progress" | "cost" = "progress") {
    return this.json<{ by: string; buckets: Record<string, string[]>; counts: Record<string, number>; element_count: number }>(
      `/projects/${pid}/5d/heatmap?by=${by}`);
  }
  /** W11 Track D: one element's attached carriers — classification codes + documents (details/instructions). */
  elementDetailing(pid: string, guid: string) {
    return this.json<{ guid: string; name: string; ifc_class: string;
      classifications: { system: string | null; code: string | null; title: string | null }[];
      documents: { identification: string | null; name: string | null; location: string | null; description: string | null }[] }>(
      `/projects/${pid}/detailing/${encodeURIComponent(guid)}`);
  }
  /** W11 Track D: classify elements with a keynote/spec/element code (UniFormat/MasterFormat/OmniClass). */
  classify(pid: string, guids: string[], system: string, code: string, name?: string, edition?: string, publish = true) {
    return this.editIfc(pid, "classify", { guids, system, code, name, edition }, publish);
  }
  /** W11 D3: auto-detail — run the condition→content rule set (e.g. exterior window → IBC flashing
   *  detail + 08 51 00), writing code/detail bundles to every matching element. */
  applyDetailingRules(pid: string, publish = true) {
    return this.editIfc(pid, "apply_detailing_rules", {}, publish);
  }
  /** W11 D3: IDS-style QA — elements that a rule applies to but are missing their required keynote/spec code. */
  validateDetailing(pid: string) {
    return this.json<{ rules_evaluated: number; gaps: number;
      elements: { rule: string; guid: string; name: string; missing: string }[] }>(
      `/projects/${pid}/detailing/rules/validate`);
  }
  /** W11 Track D: attach a document (detail drawing / installation instruction) to elements. */
  attachDocument(pid: string, guids: string[], name: string,
                 opts: { location?: string; identification?: string; description?: string; purpose?: string } = {}, publish = true) {
    return this.editIfc(pid, "attach_document", { guids, name, ...opts }, publish);
  }
  /** G3: attach an O&M / warranty document reference (purpose-tagged) to elements — turnover paperwork
   *  bound to the physical asset; surfaced in the as-built summary's `with_om_docs`. */
  attachOmDocument(pid: string, guids: string[], name: string,
                   opts: { location?: string; kind?: "om" | "warranty" } = {}, publish = true) {
    return this.editIfc(pid, "attach_om_document", { guids, name, ...opts }, publish);
  }
  /** W11 B6: author a base plate + anchor bolts under a steel column (fabrication assembly). */
  addBasePlate(pid: string, columnGuid: string, opts: { bolts?: number; width?: number; depth?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_base_plate", { column_guid: columnGuid, ...opts }, publish);
  }
  /** W11 B6: author a shear tab + bolts at a steel beam end (fabrication assembly). */
  addShearTab(pid: string, beamGuid: string, opts: { bolts?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_shear_tab", { beam_guid: beamGuid, ...opts }, publish);
  }
  /** W11 B6: author a reinforcement cage (longitudinal bars + stirrups) in a concrete column. */
  addRebarCage(pid: string, columnGuid: string,
               opts: { bar_size?: string; tie_size?: string; cover?: number; tie_spacing?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_rebar_cage", { column_guid: columnGuid, ...opts }, publish);
  }
  /** The 3-part MasterFormat project manual. See `SpecManual` in `types.ts` for the 50-per-section
   *  cap on `elements` — it matters to every caller. */
  specManual(pid: string) {
    return this.json<SpecManual>(`/projects/${pid}/spec/manual`);
  }
  /** S4: whether the model can be undone / redone + stack depths. */
  editHistory(pid: string) {
    return this.json<{ can_undo: boolean; can_redo: boolean; undo_depth: number; redo_depth: number }>(
      `/projects/${pid}/edit/history`);
  }
  /** S4: undo the last authoring edit (restore the prior model version + republish). */
  editUndo(pid: string, publish = true) {
    return this.json<{ restored: string; state: { can_undo: boolean; can_redo: boolean } }>(
      `/projects/${pid}/edit/undo`, { method: "POST", body: JSON.stringify({ publish }) });
  }
  /** S4: redo an undone edit. */
  editRedo(pid: string, publish = true) {
    return this.json<{ restored: string; state: { can_undo: boolean; can_redo: boolean } }>(
      `/projects/${pid}/edit/redo`, { method: "POST", body: JSON.stringify({ publish }) });
  }
  /** B3: give a wall a sloped top (start_height → end_height) for parapet/shed/gable walls. */
  setWallSlope(pid: string, guid: string, startHeight: number, endHeight: number, publish = true) {
    return this.editIfc(pid, "set_wall_slope", { guid, start_height: startHeight, end_height: endHeight }, publish);
  }
  /** B4: author an element from a raw triangle mesh (verts [[x,y,z]…], faces [[i,j,k]…] 0-based). */
  addMesh(pid: string, verts: number[][], faces: number[][], name = "Mesh", publish = true) {
    return this.editIfc(pid, "add_mesh_representation", { verts, faces, name }, publish);
  }
  /** A4: a compact scene digest of the model (counts by class, storeys, spaces, MEP, phasing, LOD, hygiene
   * + a one-paragraph prose overview) — grounds the AI command bar and gives a one-glance summary. */
  sceneDigest(pid: string) {
    return this.json<{ totals: { elements: number; storeys: number; spaces: number };
      by_class: Record<string, number>; storeys: string[]; prose: string;
      mep: { systems: number; has_fire_protection: boolean; by_discipline: Record<string, { systems: number; members: number }> };
      phasing: Record<string, number>; lod: Record<string, number>;
      hygiene: { issues: number | null; clean: boolean | null } }>(`/projects/${pid}/scene-digest`);
  }
  /** CONTENT-1: the curated content catalog (logistics / furniture / landscaping → IFC class + phase). */
  contentCatalog() {
    return this.json<{ count: number; note: string; groups: Record<string, { key: string; ifc_class: string;
      phase: string | null; classification: string; default_dims_m: number[] }[]> }>(`/content/catalog`);
  }
  /** CONTENT-1: place a catalogued content item at an [E,N] point (optionally with a supplied mesh). */
  placeContent(pid: string, category: string, point: [number, number], name?: string, publish = true) {
    return this.editIfc(pid, "place_content", { category, point, ...(name ? { name } : {}) }, publish);
  }
  /** CONTENT-1 (import): upload a detailed mesh (glTF/GLB/OBJ/STL/PLY) → auto-classified + placed as the
   *  right IFC via place_content. Category auto-detected from the filename unless given. */
  async importContent(pid: string, file: File, opts: { category?: string; e?: number; n?: number;
      scale?: number; name?: string; storey?: string } = {}) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts)) if (v !== undefined && v !== "") q.set(k, String(v));
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(this.url(`/projects/${pid}/content/import?${q.toString()}`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<{ guid: string; ifc_class: string; category: string; faces: number; publish?: string }>;
  }
  /** W11 E8: validate an edit's params against the authoring guardrails without applying it. */
  editPrecheck(pid: string, recipe: string, params: Record<string, unknown>) {
    return this.json<{ ok: boolean; errors: string[]; warnings: string[] }>(
      `/projects/${pid}/edit/precheck`, { method: "POST", body: JSON.stringify({ recipe, params }) });
  }
  /** W11 G1: LOD-500 readiness — share of the model field-verified as-built, by method. */
  lod500(pid: string) {
    return this.json<{ total: number; verified: number; unverified: number; readiness_pct: number;
      by_method: Record<string, number>; methods: string[]; prop: string;
      with_manufacturer: number; with_serial: number; with_dimensions: number; dimensions_out_of_tolerance: number;
      with_om_docs?: number; om_documents?: string[] }>(`/projects/${pid}/lod500`);
  }
  /** W11 G3: stamp manufacturer / serial info (Pset_Manufacturer*) — the LOD-500 / O&M / turnover layer. */
  setManufacturerInfo(pid: string, guids: string[], opts: { manufacturer?: string; model_label?: string; production_year?: string; serial?: string; barcode?: string } = {}, publish = true) {
    return this.editIfc(pid, "set_manufacturer_info", { guids, ...opts }, publish);
  }
  /** W11 B6: author an IfcCurtainWall (mullions + transoms + glazing panels) along a line. */
  addCurtainWall(pid: string, start: [number, number], end: [number, number],
                 opts: { height?: number; cols?: number; rows?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_curtain_wall", { start, end, ...opts }, publish);
  }
  /** PROD-ACTUALS: installed-rate actual vs planned + crew utilization over field productivity actuals. */
  progressActuals(pid: string, actuals: Record<string, unknown>[], planned?: Record<string, unknown>) {
    type Group = {
      group: string; material_class: string; unit: string; entries: number;
      installed_qty: number; productive_hours: number; idle_hours: number;
      installed_rate: number | null; utilization: number | null; planned_rate: number | null;
      variance_pct: number | null; status: "ahead" | "on_track" | "behind" | null;
      planned_qty: number | null; pct_complete: number | null; remaining_qty: number | null;
      projected_hours_at_rate: number | null;
    };
    return this.json<{
      group_count: number; groups: Group[]; overall_utilization: number | null;
      total_productive_hours: number; total_idle_hours: number; planned_compared: number;
      ahead: number; on_track: number; behind: number; worst: string | null; note: string;
    }>(`/projects/${pid}/progress/actuals`, { method: "POST", body: JSON.stringify({ actuals, planned }) });
  }
  /** B5: record a physical connection between two elements (IfcRelConnectsElements, LOD-350 coordination). */
  connectElements(pid: string, guidA: string, guidB: string, description?: string, publish = true) {
    return this.editIfc(pid, "connect_elements", { guid_a: guidA, guid_b: guidB, ...(description ? { description } : {}) }, publish);
  }
  /** B5: the element-to-element connection graph (IfcRelConnectsElements) — pairs + per-element degree. */
  elementConnections(pid: string) {
    return this.json<{ count: number; elements_connected: number; max_degree: number;
      connections: { a: string; a_class: string; b: string; b_class: string; description: string | null }[] }>(
      `/projects/${pid}/element-connections`);
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
  /** W11 F0: establish the view-keyed representation contexts (Model+Plan; Body/Axis/Box/Annotation/
   *  FootPrint) the drawing pipeline needs. Idempotent. */
  ensureContexts(pid: string, publish = false) {
    return this.editIfc(pid, "ensure_contexts", {}, publish);
  }
  /** W11: power selection via the IfcOpenShell selector DSL — e.g. `IfcWall`, `IfcWall, IfcDoor`,
   *  `IfcWall, Pset_WallCommon.FireRating=2HR`, `IfcElement, material=concrete`. */
  queryElements(pid: string, q: string, limit = 2000) {
    return this.json<{ query: string; count: number; truncated: boolean;
      elements: { guid: string; name: string; ifc_class: string; storey: string | null }[] }>(
      `/projects/${pid}/query?q=${encodeURIComponent(q)}&limit=${limit}`);
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
  /** Speckle interoperability bridge status (open-source, self-hostable; off unless configured). */
  speckleStatus() {
    return this.json<{ enabled: boolean; connected: boolean; server: string | null; server_name?: string;
      message: string }>(`/interop/speckle/status`);
  }
  /** Convert an uploaded CityGML (.gml) to a GeoJSON FeatureCollection of building footprints. */
  async convertCityGml(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert/citygml`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.status }))).detail || `CityGML -> ${res.status}`);
    return res.json() as Promise<{ type: string; features: unknown[]; meta: { buildings: number } }>;
  }
  /** SUBSET-EXPORT: download URL for an IFC of just the elements matching a QUERY-DSL selector. */
  subsetIfcUrl(pid: string, query: string) {
    return this.url(`/projects/${pid}/export/subset.ifc?query=${encodeURIComponent(query)}`);
  }

  // COLLAB-1: live co-editing snapshot (model signature + presence roster)
  collabSnapshot(pid: string) {
    return this.json<{
      model: { source: string | null; version: number; element_count: number; has_model: boolean };
      editors: { user: string; seconds_ago: number; viewpoint: unknown }[]; editor_count: number;
    }>(`/projects/${pid}/collab`);
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
  /** PERMIT-CHECK: submission-readiness — checklist + ranked deficiencies + verdict (409 without a model). */
  permitReadiness(pid: string) {
    return this.json<{
      verdict: string; readiness_pct: number; approvability_score: number;
      checklist: { requirement: string; satisfied: boolean; evidence: string }[];
      deficiencies: { item: string; severity: string; action: string }[];
    }>(`/projects/${pid}/permit/readiness`);
  }


  /** Discipline quantity roll-up — reinforcement tonnage, MEP linear runs, structural volume. */
  disciplineQuantities(pid: string) {
    return this.json<{ rebar: { count: number; weight_kg: number; tonnes: number; estimated: boolean };
      mep: { duct_m: number; pipe_m: number; cable_m: number; counts: Record<string, number> };
      structure: { element_volume_m3: number } }>(`/projects/${pid}/quantities/disciplines`);
  }
  /** MASTER-BUILDER brief as a shareable Markdown document (printable one-pager). */
  masterBuilderBriefMdUrl(pid: string) { return this.url(`/projects/${pid}/master-builder/brief.md`); }
  /** SPACE-UTIL benchmarking — capacity + m²/space across the portfolio's modelled projects. */
  spaceUtilBenchmarks(areaPerPerson = 10) {
    return this.json<{
      area_per_person: number; projects: number; skipped_over_cap: number; unreadable_models: number;
      rows: { project_id: string; project: string; space_count: number; total_area_m2: number;
        capacity: number; m2_per_space: number; top_type: string | null; top_type_area_m2: number | null }[];
      portfolio: { total_area_m2: number; total_capacity: number; median_m2_per_space: number | null };
      note: string;
    }>(`/benchmarks/space-utilization?area_per_person=${encodeURIComponent(areaPerPerson)}`);
  }
  /** ABSORPTION-SELLOUT — phase revenue by absorption rate → the monthly sell-out curve + months-to-sellout
   * (the carry driver) + total revenue/carry. */
  feasibilitySellout(pid: string, body: {
    units: number; absorption_per_month: number; avg_price: number; monthly_carry?: number; start_month?: number;
  }) {
    type Month = { month: number; units_sold: number; revenue: number; cumulative_units: number; cumulative_revenue: number; remaining_units: number };
    return this.json<{
      units: number; absorption_per_month: number; avg_price: number; months_to_sellout: number | null;
      years_to_sellout: number; total_revenue: number; avg_monthly_revenue: number; total_carry: number;
      monthly_carry: number | null; schedule: Month[]; note: string;
    }>(`/projects/${pid}/feasibility/sellout`, { method: "POST", body: JSON.stringify(body) });
  }
  /** LOT-SUPPLY-INDEX — months of supply = VDL ÷ monthly absorption, indexed to equilibrium (100). */
  feasibilityLotSupply(pid: string, body: { vdl: number; monthly_absorption: number; equilibrium_months?: number }) {
    return this.json<{
      vdl: number; monthly_absorption: number; equilibrium_months: number; months_of_supply: number | null;
      lsi: number | null; band: "oversupplied" | "balanced" | "undersupplied" | "unknown"; note: string;
    }>(`/projects/${pid}/feasibility/lot-supply`, { method: "POST", body: JSON.stringify(body) });
  }
  /** PERMIT-TIMELINE — days-to-issue percentiles (p25/median/p75) by jurisdiction × type × valuation band +
   * a pro-forma estimate (median expected / p75 conservative), over cached permit records. */
  permitsTimeline(pid: string, body: {
    permits?: Record<string, unknown>[]; target?: { jurisdiction?: string; type?: string; valuation?: number };
  } = {}) {
    type Dist = { n: number; p25: number | null; median: number | null; p75: number | null; min: number | null; max: number | null; mean: number | null };
    type Group = Dist & { jurisdiction: string; type: string; band: string };
    return this.json<{
      permit_count: number; measured: number; overall: Dist; groups: Group[];
      seasonal: { month: number; issued: number; median_days: number | null }[];
      estimate?: {
        expected_days: number | null; conservative_days?: number | null; expected_months?: number | null;
        conservative_months?: number | null; sample_size: number; basis: string; note?: string;
      };
      note: string;
    }>(`/projects/${pid}/permits/timeline`, { method: "POST", body: JSON.stringify(body) });
  }
  scopeRegister(pid: string, body: {
    scope_items: Record<string, unknown>[]; qto_lines?: Record<string, unknown>[]; activities?: Record<string, unknown>[];
  }) {
    type Item = {
      id: string | null; name: string; cost_code: string | null; qty: number | null; value: number | null;
      responsible: string | null; package: string | null; start: string | null; finish: string | null;
      quantified: boolean; allocated: boolean; scheduled: boolean; gaps: string[]; status: "complete" | "gap";
    };
    return this.json<{
      item_count: number; complete: number; with_gaps: number; pct_quantified: number; pct_allocated: number;
      pct_scheduled: number; total_value: number; by_owner: { owner: string; value: number }[];
      gap_items: Item[]; items: Item[]; note: string;
    }>(`/projects/${pid}/scope/register`, { method: "POST", body: JSON.stringify(body) });
  }
  citedQuery(pid: string, query: string, property?: string, persona?: "exec" | "pm" | "field") {
    type CitationRef = {
      source_type: "ifc" | "doc" | "record" | "rule"; document_id: string | null; revision: string | null;
      guid: string | null; sheet: string | null; page: number | null; bbox: number[] | null;
      record_ref: string | null; rule_id: string | null; span: number[] | null;
    };
    type Claim = { text: string; citations: CitationRef[]; confidence: number };
    type Conflict = { target: string; values: string[]; claims: { text: string; value: unknown; citations: CitationRef[] }[] };
    return this.json<{
      answer: string; claims: Claim[]; conflicts: Conflict[]; coverage: number; fully_cited: boolean;
      uncited_claims: number[]; citation_count: number; source_types: Record<string, number>;
      note: string; query: string; matched: number; truncated: boolean;
      persona?: string; insight?: string; follow_ups?: string[]; persona_note?: string;
    }>(`/projects/${pid}/answer/cited-query`, { method: "POST", body: JSON.stringify({ query, property, persona }) });
  }
  masterBuilderBrief(pid: string, scope?: { workspace?: string; persona?: string }) {
    const q = new URLSearchParams();
    if (scope?.workspace) q.set("workspace", scope.workspace);
    if (scope?.persona) q.set("persona", scope.persona);
    const qs = q.toString();
    return this.json<MasterBuilderBrief>(
      `/projects/${pid}/master-builder/brief${qs ? `?${qs}` : ""}`);
  }
  /** Scan-to-BIM deviation — upload an as-built point cloud (XYZ/CSV) and compare it to the model surface. */
  async scanDeviation(pid: string, file: File, tolerance = 0.05) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/scan/deviation?tolerance=${tolerance}`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.status }))).detail || `scan -> ${res.status}`);
    return res.json() as Promise<{ point_count: number; reference_count: number; tolerance: number;
      within_tolerance: number; within_pct: number | null; out_of_tolerance: number;
      mean_deviation: number; max_deviation: number; p95_deviation: number;
      histogram: { band: string; count: number }[]; note: string }>;
  }
  validate(pid: string) {
    return fetch(this.url(`/projects/${pid}/validate`), { method: "POST" }).then((r) => r.json() as Promise<ValidationResult>);
  }
  energy(pid: string) {
    return this.json<EnergyResult>(`/projects/${pid}/energy`);
  }

  // W9-1 property mapping / normalization — the transform verb between IDS-validate and COBie-export
  propmapDetect(pid: string) {
    return this.json<{ element_count: number; properties: { pset: string; prop: string; count: number; kind: string; sample: string }[] }>(
      `/projects/${pid}/propmap/detect`);
  }
  propmapPlan(pid: string, rules: PropMapRule[]) {
    return this.json<{ dry_run: boolean; changed: number; rules: { from: string; to: string; matched: number; cast: string; keep_source: boolean; samples: { guid: string; from: string; to: string }[] }[] }>(
      `/projects/${pid}/propmap/plan`, { method: "POST", body: JSON.stringify({ rules }) });
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
  sharedParams(pid: string) {
    return this.json<{ params: { name: string; pset: string; ptype: string; applies_to: string[];
      label: string; description: string }[]; max: number }>(`/projects/${pid}/shared-params`);
  }
  saveSharedParams(pid: string, params: unknown[]) {
    return this.json<{ params: unknown[] }>(`/projects/${pid}/shared-params`,
      { method: "PUT", body: JSON.stringify({ params }) });
  }

  rooms() {
    return this.json<RoomAllocation>(`/rooms`);
  }
  /**
   * R26-VITALS — the six numbers along the bottom strip.
   *
   * One request, deliberately: assembling LOD / area / $ft² / float / IRR / health from five engines
   * in the browser is how the same project came to show two different health scores in one session
   * (audit finding 03). The server owns the assembly.
   */
  vitals(pid: string) {
    return this.json<VitalsPayload>(`/projects/${pid}/vitals`);
  }
  modulePins(pid: string) {
    return this.json<ModulePin[]>(`/projects/${pid}/module-pins`);
  }
  dashboard(pid: string, party?: string) {
    const q = party ? `?party=${encodeURIComponent(party)}` : "";
    return this.json<Dashboard>(`/projects/${pid}/dashboard${q}`);
  }

  // --- portfolio benchmarking (cross-project) --------------------------------
  benchmarkCosts(minSamples = 3) {
    return this.json<{ cost_codes: { cost_code: string; samples: number; low: number; p25: number;
      median: number; p75: number; high: number; total: number }[];
      code_count: number; min_samples: number; codes_below_threshold: number; message?: string | null }>(
      `/benchmarks/costs?min_samples=${minSamples}`);
  }
  benchmarkResponseRates() {
    return this.json<{ rfi: { total: number; open: number; answered_or_closed: number;
      avg_turnaround_days: number | null; overdue: number; overdue_pct: number };
      submittal: { total: number; open: number; returned: number; avg_turnaround_days: number | null;
      overdue: number; overdue_pct: number } }>(`/benchmarks/response-rates`);
  }

  // --- Tier 2/3: prequal, lien exposure, accounting, carbon, code check, pricing ---------------
  prequalScores(pid: string, projectSize?: number) {
    const qs = projectSize ? `?project_size=${projectSize}` : "";
    return this.json<PrequalScores>(`/projects/${pid}/prequal/scores${qs}`);
  }
  coiExpiry(pid: string, soonDays = 30) {
    return this.json<{ expired: { vendor?: string; coverage_type?: string; expires: string; days: number }[];
      expiring_soon: { vendor?: string; coverage_type?: string; expires: string; days: number }[];
      expired_count: number; expiring_count: number }>(`/projects/${pid}/prequal/coi-expiry?soon_days=${soonDays}`);
  }
  lienExposure(pid: string) {
    return this.json<{ vendors: { vendor: string; billed: number; paid: number; retainage: number;
      waived_unconditional: number; waived_conditional: number; exposure: number; status: string }[];
      total_lien_exposure: number; vendors_at_risk: string[]; message?: string | null }>(
      `/projects/${pid}/payapp/lien-exposure`);
  }
  projectCarbon(pid: string) {
    return this.json<{ total_kgco2e: number; total_tco2e: number; line_count: number; unmatched: number;
      by_material: Record<string, number>; by_cost_code: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/carbon`);
  }
  // --- design lifecycle (RIBA/AIA phases + itemized soft costs) ---------------
  lifecycle(pid: string) {
    return this.json<{ count: number; seeded: boolean;
      current_stage: { id: string; riba_stage: string; aia_phase: string } | null;
      phases: { id: string; ref: string; order: number; state: string; riba_stage: string;
        aia_phase: string; design_fee_pct: number | string; iso_status: string;
        deliverables: string[]; design_fee_amount: number; signed_by?: string }[];
      hard_cost: number;
      soft_costs: { total: number; lines: { key: string; label: string; pct_of_hard: number; amount: number }[] } | null;
      }>(`/projects/${pid}/lifecycle`);
  }
  lifecycleSeed(pid: string) {
    return this.json<{ seeded: boolean; phases?: number; reason?: string }>(
      `/projects/${pid}/lifecycle/seed`, { method: "POST" });
  }
  diligenceReadiness(pid: string) {
    return this.json<DiligenceReadiness>(`/projects/${pid}/diligence/readiness`);
  }



  /** Discipline Spine traceability: discipline → sheets → specs → bid packages → cost codes → budget. */
  spineTraceability(pid: string) {
    return this.json<SpineTraceability>(`/projects/${pid}/spine/traceability`);
  }

  // --- concept space programming: adjacency graph + massing hints ---------------
  programSummary(pid: string) {
    return this.json<{ spaces: number; total_area_sf: number; net_area_sf: number;
      efficiency_pct: number | null;
      by_type: Record<string, { count: number; area: number; pct: number }>;
      graph: { nodes: { id: string; name: string; type: string; area: number; quantity: number; adjacent_to: string[] }[];
        edges: { from: string; from_type: string; to_type: string; satisfiable: boolean }[] };
      adjacency: { total: number; satisfiable: number; unmet: { from_type: string; to_type: string }[] };
      massing_hints: { gross_area_sf: number; net_area_sf: number; mix_pct: Record<string, number> };
      note: string }>(`/projects/${pid}/program/summary`);
  }


  // --- UNFILED: three methods that the RACI banner above used to cover -----------------
  // Named rather than left implicit, because a banner that over-claims is how the previous
  // three slices each lost a method. `mcpTools` is global (`/mcp/tools`); `handoverAcceptance`
  // is `/handover/acceptance`; `inspectVim` is `/convert/vim/inspect`. None is RACI, and each
  // needs its home decided by what it ANSWERS rather than by what it sits next to.
  mcpTools() {
    return this.json<{ tools: { name: string; description: string }[]; server: string; note: string }>(
      `/mcp/tools`);
  }
  handoverAcceptance(pid: string) {
    return this.json<{ accepted: boolean; checks: { key: string; label: string; ok: boolean }[];
      metrics: Record<string, number>; note: string }>(`/projects/${pid}/handover/acceptance`);
  }

  async inspectVim(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert/vim/inspect`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `inspect failed (${res.status})`);
    return res.json() as Promise<Record<string, unknown>>;
  }

  // --- lease revenue: what share of operating expense is recoverable from tenants? -----------
  // Shared a banner with `reserveStudy` ("hold-phase asset management") until SCALE-SEAM (88).
  // That slice took the condition-and-capital half to `operations.ts` and left this behind: it
  // allocates the recoverable pool ACROSS TENANTS by share and returns `balance_due` per suite,
  // which is a lease answer, not a building-condition one.
  //
  // **The rest of that note was a FORECAST, and SCALE-SEAM (91) checked it and it did not hold.**
  // It said this method "goes with `rentRollScrub`, `netEffectiveRent` and `normalizeT12`, still
  // below, when a rent-roll slice takes them". (91) is that slice — it took all three to
  // `creDeal.ts` — and left this one here, because all three signals it derived point the other
  // way: no `CRE-` code on this doc comment, no `(R20)` on the handler, and
  // `/projects/{pid}/cam/reconciliation` is served by `operations.py`, not by the `realestate.py`
  // that serves every method (91) took. A CAM true-up bills a COMPLETED OPERATING YEAR to sitting
  // tenants; the three it was predicted to join test a counterparty's figures before a purchase.
  //
  // So this stays, still unfiled, and the correction is the point: **a placement forecast is a
  // hypothesis for the next slice to test, not an instruction to carry out.** Phrased as a plan
  // ("it goes with X when Y"), it reads as settled and invites the next reader to execute it
  // without re-deriving anything — which is how a guess becomes a fact in this file.
  camReconciliation(pid: string, opts: { year?: number; grossUpToPct?: number; buildingSf?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.year) q.set("year", String(opts.year));
    if (opts.grossUpToPct) q.set("gross_up_to_pct", String(opts.grossUpToPct));
    if (opts.buildingSf) q.set("building_sf", String(opts.buildingSf));
    const qs = q.toString();
    return this.json<{ year: number; occupied_sf: number; building_sf: number; occupancy_pct: number;
      gross_up_to_pct: number;
      expense_lines: { ref: string; category: string; budget: number; actual: number;
        variable: boolean; recoverable: boolean; grossed_up: number }[];
      budget_total: number; actual_total: number; recoverable_pool: number;
      tenants: { id: string; ref: string; tenant: string; suite: string; rentable_sf: number;
        share_pct: number; share_of_expenses: number; estimated_paid: number; balance_due: number }[];
      note: string }>(`/projects/${pid}/cam/reconciliation${qs ? `?${qs}` : ""}`);
  }

  // --- STAYING — 4 client-level methods, deliberately not extracted -------------
  // These four are global or cross-cutting, not domain: an enum lookup, a project-wide search, an
  // attachment URL builder and a template list. They are the END of the CX-1 residue that (83)
  // through (87) worked through, and they are recorded here as DECIDED rather than pending.
  //
  // **THIS IS NOT THE END OF SCALE-SEAM, and a previous version of this banner implied it was.**
  // 80 methods still sit ABOVE this line — `disciplineTree`, `classify`, `specManual`, `editUndo`,
  // `energyModel`, `propmapPlan`, `camReconciliation` and the rest. They were never inside the
  // CX-1 banner, so no map has ever covered them. The UNFILED map described the TAIL of this file,
  // not the file.
  //
  // (87) found that by deriving the whole population instead of trusting the map: 130 methods
  // total, 4 below, 126 above. The lesson is the one this sequence keeps re-learning — **a
  // completeness claim computed over a self-authored list is confident and unfounded**, and the
  // list here was authored by the same slices it was meant to audit.
  //
  // (88) took the first nine of those 126 to `operations.ts`, leaving 117. **This example list
  // named `esgSummary` until that slice moved it** — a banner citing, as evidence of unfinished
  // work, a method that had left. Re-derive the number and the names from the file; do not read
  // them here. The count above is checked by `services/api/test_roadmap_status.py`, which counts
  // methods absent from the keep-list below rather than trusting any prose.
  //
  // (89) took eight more — the four `/resilience/*` to `resilience.ts` and the four
  // `/responsibility/*` to `responsibility.ts` — leaving 109. The seven names above were checked
  // against the file this time and none of them had moved; that check is the point, not the result.
  //
  // (90) took the eight client-portal methods to `clientPortal.ts`, leaving 101, still unmapped. Its
  // extractor swallowed the next doc comment after any ONE-LINE method; `docComments.test.ts` caught
  // that, while an orphan check written beside the slice passed — it allowed a comment to follow a
  // comment, which is the defect itself.
  //
  // (91) took thirteen to `creDeal.ts`, leaving 88, still unmapped — the R20 CRE deal desk, chosen
  // on three signals that were DERIVED and agreed: ten `CRE-` codes that occur nowhere else in
  // `apps/web/src`, a 1:1 match to `realestate.py` and to no other router, and one question
  // (diligence, decision, terms) running through all thirteen. It also tested (88)'s forecast about
  // `camReconciliation` instead of executing it, and the forecast lost; see the note at that method.
  // **`rentRollScrub` was named in the example list above until this slice moved it** — the second
  // time this banner has cited, as evidence of unfinished work, a method that had already left
  // (`esgSummary` was the first, caught by (88)). (89) checked its seven names and none had moved,
  // which is why they survived to be wrong now: a list that passes one audit is not thereby safe
  // for the next slice. Re-derive from the file.
  //
  // (92) took the four `annotate` methods to `annotate.ts`, leaving 84. It is the first mixin to call
  // `editIfc` WITHOUT DECLARING IT (`authoring.ts` calls it seven times, but it defines it, so it
  // never needed a base type that promises it) — most likely why all 24 edit recipes were still here:
  // is declared on the `Authoring` mixin rather than on `HttpCore`, so a mixin typed `Ctor<HttpCore>`
  // cannot see it and the extraction simply does not compile. `annotate.ts` declares the requirement
  // in its type instead; moving `editIfc` down into `HttpCore` would unblock the other 20 and is
  // left for whichever slice takes the next recipe cluster.
  //
  // (93) took `connectMep` and `addMepFitting` to `mep.ts`, leaving 82 — the two ⑲ had left behind
  // with the note that they "call `editIfc` (`/edit`) and stay", which recorded the symptom without
  // diagnosing the cause. `NeedsEditIfc` moved to `types.ts` so `annotate.ts` and `mep.ts` share one
  // definition rather than two hand-copied signatures. **(92)'s recommendation to move `editIfc`
  // into `HttpCore` was tested and does NOT hold** — that file exists to keep transport separate
  // from the endpoint surface, and `editIfc` is a domain endpoint.
  //
  // (94) took the as-built pair to `model.ts`, leaving 80 — the two members of ㊻'s question that a
  // route-prefix split could not see. `setPhase` did NOT come despite completing the matrix's
  // `lifecycle` category: its read half `phasing()` is still here. Reasoning in `model.ts`'s header.
  //
  //   the four that stay        enumOptions, searchAll, attachmentUrl, templates
  enumOptions(pid: string) {
    return this.json<Record<string, Record<string, string[]>>>(`/projects/${pid}/enum-options`);
  }
  searchAll(pid: string, q: string, limit = 50) {
    return this.json<WorkItem[]>(`/projects/${pid}/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  }
  attachmentUrl(attId: string) {
    // module-record attachments live in RecordAttachment; this distinct path avoids bim.py's
    // /attachments/{id}/download route (Attachment table) shadowing it (which 404'd every thumbnail).
    return this.url(`/module-attachments/${attId}/download`);
  }

  /** Reusable templates for a module (save a project's records → apply to another project). */
  templates(module: string) {
    return this.json<{ id: string; module: string; name: string; item_count: number }[]>(`/templates?module=${encodeURIComponent(module)}`);
  }
}


export interface ValidationResult {
  title: string;
  status: "pass" | "fail";
  summary: { specifications: number; passed: number; failed: number };
  specifications: { name: string; status: "pass" | "fail"; applicable: number; passed: number; failed: number; failed_guids: string[] }[];
}
