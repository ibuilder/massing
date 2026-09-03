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
  ResponsibilityMatrix, SmartView,
    SpecManual, WorkItem, VitalsPayload,
    DiligenceReadiness, MasterBuilderBrief, PrequalScores,
    SpineTraceability } from "./types";


// Transport (baseUrl, token, json/_pdfPost/url/health) lives in HttpCore; ApiClient adds the typed
// domain methods below. Every `api.method()` call site is unchanged by the split.
export class ApiClient extends withAccounting(withDealMemory(withPdfTools(withCodeCheck(withSpecialty(withIds(withEvm(withRisk(withEntitlements(withPrecon(withAi(withTopics(withMep(withDocuments(withModels(withElements(withDrawingSheets(withDrawingSet(withMarkup(withSync(withConnections(withDocQa(withFinance(withContracts(withAuth(withProforma(withDesignOptions(withRoutines(withCost(withProcurement(withEstimate(withModules(withModel(withSchedule(withLibrary(withAssetRights(withAuthoring(HttpCore))))))))))))))))))))))))))))))))))))) {
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
  /** UX-2: place a 2D text annotation (note / tag / callout) as an IfcAnnotation at an [E,N] point. */
  addAnnotation(pid: string, point: [number, number], text: string,
                opts: { kind?: "note" | "tag" | "callout"; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_annotation", { point, text, ...opts }, publish);
  }
  /** UX-2: place a dimension annotation (line + measured distance) between two [E,N] points. */
  addDimension(pid: string, start: [number, number], end: [number, number],
               opts: { text?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_dimension", { start, end, ...opts }, publish);
  }
  /** UX-2: place a revision cloud (scalloped outline + optional delta/number tag) around a region —
   *  two opposite [E,N] corners, or >=3 boundary points. Renders on the generated plan. */
  addRevisionCloud(pid: string, points: [number, number][],
                   opts: { tag?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_revision_cloud", { points, ...opts }, publish);
  }
  /** UX-2: place an element-aware tag on a host element — the label is auto-read from the host
   *  (its Name / Pset mark / type), or overridden with `text`; assigned to the element it labels. */
  addTag(pid: string, hostGuid: string,
         opts: { text?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_tag", { host_guid: hostGuid, ...opts }, publish);
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
  /** W11 G2: record a field-verified as-built dimension (+ variance vs design) on the selection. */
  recordAsbuiltDimension(pid: string, guids: string[], dimension: string, measured: number, design?: number, publish = true) {
    return this.editIfc(pid, "record_asbuilt_dimension", { guids, dimension, measured, ...(design != null ? { design } : {}) }, publish);
  }
  /** W11 G1: stamp elements as field-verified as-built (Massing_AsBuilt) — the LOD-500 reliability layer. */
  verifyAsbuilt(pid: string, guids: string[], opts: { verified_by?: string; method?: string; note?: string } = {}, publish = true) {
    return this.editIfc(pid, "verify_asbuilt", { guids, ...opts }, publish);
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
  /** W10-4: connect two MEP elements port-to-port (IfcRelConnectsPorts). */
  connectMep(pid: string, guidA: string, guidB: string, publish = true) {
    return this.editIfc(pid, "connect_mep", { guid_a: guidA, guid_b: guidB }, publish);
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
  /** W11 B6: author a MEP fitting (elbow BEND / tee JUNCTION / TRANSITION) at a point, on a system. */
  addMepFitting(pid: string, ifcClass: string, point: [number, number],
                opts: { predefined?: string; size?: number; system?: string } = {}, publish = true) {
    return this.editIfc(pid, "add_mep_fitting", { ifc_class: ifcClass, point, ...opts }, publish);
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
  /** CLIENT-PORTAL — read-only share tokens for a project-readiness digest. */
  shareTokens(pid: string) {
    type Tok = { token: string; label: string | null; revoked: boolean; created_at: string | null;
      created_by: string | null; view_count: number; last_viewed_at: string | null; share_path: string;
      show_payments: boolean };
    return this.json<{ tokens: Tok[] }>(`/projects/${pid}/share-tokens`);
  }
  /** `showPayments` is the explicit opt-in for THIS token's digest to carry the payment schedule. */
  createShareToken(pid: string, label?: string, showPayments?: boolean) {
    return this.json<{ token: string; label: string | null; share_path: string; revoked: boolean }>(
      `/projects/${pid}/share-tokens`,
      { method: "POST", body: JSON.stringify({ label: label ?? "", show_payments: !!showPayments }) });
  }
  revokeShareToken(pid: string, token: string) {
    return this.json<{ revoked: boolean }>(`/projects/${pid}/share-tokens/${encodeURIComponent(token)}`,
      { method: "DELETE" });
  }
  /** PORTAL-TXN phase 3 — post a client comment through a share token (public; lands on the token's
   * BCF feedback topic, so the team answers from the Issue Board). */
  sharedComment(token: string, body: { text: string; client_name?: string }) {
    return this.json<{ topic_id: string; comment_id: string; author: string | null; text: string;
      created_at: string | null }>(
      `/shared/${encodeURIComponent(token)}/comment`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The public digest JSON URL for a share token. */
  sharedDigestUrl(token: string) { return this.url(`/shared/${encodeURIComponent(token)}/digest`); }
  /** The public read-only HTML page for a share token (opens with no login — the human share link). */
  sharedPageUrl(token: string) { return this.url(`/shared/${encodeURIComponent(token)}`); }
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
  /** PORTAL-TXN — record a client decision through a share token (public; approve/acknowledge/decline). */
  sharedDecision(token: string, body: {
    item_type: string; item_ref: string; action: "approved" | "acknowledged" | "declined";
    client_name?: string; note?: string;
  }) {
    return this.json<{
      id: number; item_type: string; item_ref: string; action: string;
      client_name: string | null; note: string | null; created_at: string | null;
    }>(`/shared/${encodeURIComponent(token)}/decision`, { method: "POST", body: JSON.stringify(body) });
  }
  /** PORTAL-TXN — the project's client-decision feed (editor only), newest first. */
  clientDecisions(pid: string, limit = 500) {
    type D = { id: number; item_type: string; item_ref: string; action: string; client_name: string | null;
      note: string | null; created_at: string | null; token: string };
    return this.json<{ decisions: D[] }>(`/projects/${pid}/client-decisions?limit=${encodeURIComponent(limit)}`);
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

  /** CRE-HOLDSELL — hold vs sell: incremental hold-year IRRs against the proceeds declined today. */
  holdSell(pid: string, inputs: unknown, hurdleRate = 0.12, maxYears = 10) {
    return this.json<{ computable: boolean; reason?: string;
      sell_now: { gross_sale: number; selling_costs: number; loan_payoff: number;
        net_proceeds: number; exit_cap: number };
      hurdle_rate: number; assumptions: Record<string, number>;
      years: { hold_years: number; exit_cap: number; noi_at_exit: number;
        net_proceeds_at_exit: number; incremental_irr: number | null; beats_hurdle: boolean }[];
      breakeven_hold_years: number | null; recommendation: "hold" | "sell";
      best_year: unknown; note: string }>(
      `/projects/${pid}/hold-sell`,
      { method: "POST", body: JSON.stringify({ inputs, hurdle_rate: hurdleRate,
                                               max_years: maxYears }) });
  }
  /** CRE-CLAUSE — the clause-position playbook (a clause with no red line is not a standard). */
  clausePlaybook(pid: string) {
    return this.json<{ playbook: Record<string, { clause: string; severity: string; accept: string;
      negotiate: string; refuse: string; fallback: string }[]>;
      starter: unknown[]; positions: string[] }>(`/projects/${pid}/contracts/playbook`);
  }
  saveClausePlaybook(pid: string, playbook: unknown) {
    return this.json<{ playbook: unknown }>(`/projects/${pid}/contracts/playbook`,
      { method: "PUT", body: JSON.stringify({ playbook }) });
  }
  /** CRE-CLAUSE — record a review against the PLAYBOOK (distinct from the AI `reviewContract`
   *  above: this one takes findings a human already made and scores them against the standard).
   *  Unreviewed playbook clauses come back as open risk. */
  reviewContractClauses(pid: string, contractType: string, findings: unknown[], document = "") {
    return this.json<{ verdict: string; document: string | null; reason?: string;
      available_types?: string[];
      clauses: { clause: string; severity: string; position: string; deviation: boolean;
        note: string | null; reference: string | null; red_line: string }[];
      deviations: unknown[]; negotiable: unknown[];
      not_reviewed: { clause: string; severity: string }[]; unknown_clauses: string[];
      counts: Record<string, number>; note: string }>(
      `/projects/${pid}/contracts/review`,
      { method: "POST", body: JSON.stringify({ contract_type: contractType, findings, document }) });
  }
  /** CRE-COVENANT — the loan covenant + reporting register (day-count basis, clock start). */
  loanCovenants(pid: string, loan: unknown, actuals?: Record<string, number>) {
    return this.json<{ loan: { name: string; lender: string }; at_risk: boolean;
      summary: Record<string, number>;
      reporting: { obligations: { name: string; computable: boolean; due_date?: string;
        day_basis?: string; clock_start?: string; anchor_source?: string; status?: string;
        risk?: string; days_remaining?: number; clock_start_matters?: boolean;
        alternate_reading?: { due_date: string; days_difference: number; warning: string } }[];
        upcoming: unknown[]; overdue: unknown[]; not_computable: { name: string; reason: string }[];
        counts: Record<string, number> };
      financial: { covenants: { name: string; tested: boolean; passing?: boolean; status?: string;
        headroom?: number; cure_ends?: string | null; reason?: string }[];
        untested: { name: string; reason: string }[]; counts: Record<string, number>;
        clean: boolean } }>(
      `/projects/${pid}/loan/covenants`,
      { method: "POST", body: JSON.stringify({ loan, actuals }) });
  }
  /** CRE-AUTHORITY — the deal-room authority table; required gaps BLOCK downstream analysis. */
  dealAuthority(pid: string) {
    return this.json<{ table: { fact_type: string; label: string; document: string; as_of: string;
      age_days: number | null; freshness_days: number; fresh: boolean; required: boolean }[];
      missing: { fact_type: string; label: string }[];
      stale: { fact_type: string; days_over: number }[];
      superseded_still_active: { fact_type: string; document: string; issue: string }[];
      gate: { passes: boolean; blocking: { fact_type: string; why: string }[]; advisory: unknown[] };
      counts: Record<string, number>; note: string }>(`/projects/${pid}/deal-room/authority`);
  }
  saveDealAuthority(pid: string, entries: unknown[]) {
    return this.json<{ entries: unknown[]; assessment: { gate: { passes: boolean } } }>(
      `/projects/${pid}/deal-room/authority`,
      { method: "PUT", body: JSON.stringify({ entries }) });
  }
  /** CRE-SUPPLY — competitive supply weighted by recorded evidence, not by status label. */
  competitiveSupply(pid: string, body: { projects: unknown[]; window_start?: string;
                                         window_end?: string; product_type?: string;
                                         monthly_absorption?: number }) {
    return this.json<Record<string, unknown>>(
      `/projects/${pid}/supply/competitive`, { method: "POST", body: JSON.stringify(body) });
  }
  /** CRE-DECISION-GATE — the pre-committee gate; a gate without evidence is unknown, and blocks. */
  decisionGate(pid: string, evidence: unknown, requiredExhibits?: string[], minCoverage?: number) {
    return this.json<{ verdict: "ready" | "blocked"; ready: boolean;
      gates: { gate: string; label: string; status: "pass" | "fail" | "unknown"; detail: string;
        action: string }[];
      blocking: { gate: string; status: string; detail: string }[];
      actions: { gate: string; action: string }[];
      counts: Record<string, number>; note: string }>(
      `/projects/${pid}/decision-gate`,
      { method: "POST", body: JSON.stringify({ evidence, required_exhibits: requiredExhibits,
                                               min_coverage: minCoverage ?? 0.9 }) });
  }
  /** CRE-COMP-TIER — comps ranked by source tier; bands report the weakest tier they rest on. */
  tieredComps(pid: string, field = "price_psf") {
    return this.json<{ comp_count: number; conflict_count: number;
      comps: { tier: string; label: string; rank: number; address: string; source: string;
        price_psf: number | null; cap_rate: number | null }[];
      conflicts: { address: string; kept_tier: string;
        outranked: { tier: string; source: string }[];
        value_deltas: { field: string; kept: number; outranked: number }[] }[];
      statistics: Record<string, { n: number; median: number | null; p25?: number; p75?: number;
        worst_tier: string | null; worst_tier_label?: string; best_tier?: string;
        tier_counts?: Record<string, number>; unattributed?: number; note?: string }>;
      note: string }>(`/projects/${pid}/comps/tiered?field=${encodeURIComponent(field)}`);
  }
  /** CRE-T12 — normalize a trailing-twelve to the house chart; the tie-out is a GATE, not a report. */
  normalizeT12(pid: string, t12: unknown, units?: number) {
    return this.json<{ line_count: number; source_totals: Record<string, number>;
      mapped_totals: Record<string, number>;
      tie_out: { reconciles: boolean; deltas: Record<string, number>; tolerance: number };
      stopped?: boolean; adjusted_noi: number | null;
      reconciling_items?: { issue: string; description?: string; amount?: number }[];
      unmapped_count: number; unmapped: { description: string; amount: number }[];
      one_time_items?: { description: string; amount: number; kind: string }[];
      capital_items?: { description: string; amount: number }[];
      by_category?: { category: string; label: string; amount: number; run_rate: number }[];
      run_rate_vs_trailing?: { category: string; trailing: number; run_rate: number; delta: number }[];
      add_back_questions?: { check: string; severity: string; finding: string; question: string }[];
      note: string }>(
      `/projects/${pid}/t12/normalize`, { method: "POST", body: JSON.stringify({ t12, units }) });
  }
  /** CRE-RRSCRUB — rent roll vs income; a check without its inputs reports not-run, never a pass. */
  rentRollScrub(pid: string, income?: unknown, units?: unknown[]) {
    return this.json<{ lease_count: number; excluded_not_active: number; clean: boolean;
      counts: { total: number; ran: number; not_applicable: number; passed: number; failed: number };
      checks: { check: string; applicable: boolean; passed?: boolean; severity?: string;
        finding: string; needs?: string }[];
      findings: { check: string; severity: string; finding: string }[];
      coverage_note: string }>(
      `/projects/${pid}/rent-roll/scrub`, { method: "POST", body: JSON.stringify({ income, units }) });
  }
  /** CRE-NER — net effective rent: the rent roll after concessions (straight-line + discounted). */
  netEffectiveRent(pid: string, opts: { discountRate?: number; lcPct?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.discountRate !== undefined) q.set("discount_rate", String(opts.discountRate));
    if (opts.lcPct !== undefined) q.set("lc_pct", String(opts.lcPct));
    const qs = q.toString();
    return this.json<{ lease_count: number; skipped_count: number; excluded_not_active: number;
      face_gpr_annual: number; ner_gpr_annual_discounted: number;
      ner_gpr_annual_straight_line: number; concession_total_term: number;
      concession_load_pct: number; face_to_ner_delta_annual: number;
      face_to_ner_delta_pct: number; lc_included: boolean; discount_rate: number;
      skipped: { tenant: string; suite: string; reason: string }[];
      leases: { tenant: string; suite: string; face_rent_annual: number;
        ner_annual_discounted: number; ner_psf_discounted: number | null;
        concession_load_pct: number }[]; note: string }>(
      `/projects/${pid}/rent-roll/net-effective${qs ? `?${qs}` : ""}`);
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

  // --- operations: CMMS + metered energy ----------------------------------------
  cmmsGeneratePm(pid: string) {
    return this.json<{ generated: number; work_orders: { work_order: string; schedule: string }[];
      as_of: string }>(`/projects/${pid}/cmms/generate-pm`, { method: "POST" });
  }
  cmmsKpis(pid: string) {
    return this.json<{ total: number; open: number; completed: number; overdue: number;
      open_by_priority: Record<string, number>; by_type: Record<string, number>;
      pm_compliance_pct: number | null; mttr_days: number | null }>(`/projects/${pid}/cmms/kpis`);
  }
  energyActual(pid: string, gfaSf?: number) {
    const qs = gfaSf ? `?gfa_sf=${gfaSf}` : "";
    return this.json<{ total_kbtu: number; total_cost: number; water_gallons: number;
      by_utility: Record<string, { consumption: number; unit: string; kbtu: number; cost: number }>;
      monthly: { month: string; kbtu: number }[]; months_covered: number;
      gfa_sf: number | null; eui_kbtu_sf_yr: number | null; note: string }>(
      `/projects/${pid}/energy/actual${qs}`);
  }
  energyBenchmarkStatus() {
    return this.json<{ enabled: boolean; provider: string | null; message: string }>(
      `/energy/benchmark-status`);
  }
  twinReadiness(pid: string) {
    return this.json<{ assets: number; systems: number; systems_by_type: Record<string, number>;
      system_linked_pct: number | null; sensor_mapped_pct: number | null; bms_integrated_systems: number;
      dpp: { complete_pct: number | null; partial: number; complete: number; fields: string[]; note: string };
      twin_readiness_pct: number | null; note: string }>(`/projects/${pid}/twin/readiness`);
  }

  // --- facility condition assessment (FCI) --------------------------------------
  fcaIndex(pid: string) {
    return this.json<{ elements: number; open_deficiencies: number; crv: number; crv_source: string;
      deferred_maintenance: number; capital_renewal: number; fci_pct: number; band: string;
      by_uniformat: { group: string; count: number; deferred: number; renewal: number; crv: number; fci_pct: number | null }[];
      by_condition: Record<string, number>;
      worst_elements: { ref: string; element: string; uniformat: string; condition: string; cost: number }[];
      recommended_by_year: { year: number; cost: number }[];
      bands: Record<string, string>; note: string }>(`/projects/${pid}/fca/index`);
  }
  fcaPortfolio() {
    return this.json<{ count: number; note: string;
      projects: { project_id: string; project: string; fci_pct: number; band: string; crv: number;
        backlog: number; open_deficiencies: number }[] }>(`/fca/portfolio`);
  }

  // --- climate & water resilience (flood + stormwater) --------------------------
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

  // --- Responsibility matrix (RACI / DACI) — the four `/responsibility` methods only ------
  responsibilityMatrix(pid: string) {
    return this.json<ResponsibilityMatrix>(`/projects/${pid}/responsibility`);
  }
  responsibilityTemplates(pid: string) {
    return this.json<{ templates: { key: string; name: string; description: string; rows: number }[] }>(
      `/projects/${pid}/responsibility/templates`);
  }
  setResponsibilityConfig(pid: string, roles: string[], mode: "RACI" | "DACI") {
    return this.json<{ roles: string[]; mode: string }>(`/projects/${pid}/responsibility/config`, {
      method: "PUT", body: JSON.stringify({ roles, mode }) });
  }
  applyResponsibilityTemplate(pid: string, key: string, mode: "RACI" | "DACI") {
    return this.json<{ applied: string; created: number; mode: string }>(
      `/projects/${pid}/responsibility/apply-template`, {
        method: "POST", body: JSON.stringify({ key, mode }) });
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

  // --- hold-phase asset management: reserve study + CAM reconciliation ----------
  reserveStudy(pid: string, opts: { horizonYears?: number; openingBalance?: number;
      annualContribution?: number; inflationPct?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.horizonYears) q.set("horizon_years", String(opts.horizonYears));
    if (opts.openingBalance) q.set("opening_balance", String(opts.openingBalance));
    if (opts.annualContribution) q.set("annual_contribution", String(opts.annualContribution));
    if (opts.inflationPct) q.set("inflation_pct", String(opts.inflationPct));
    const qs = q.toString();
    return this.json<{ horizon: { from: number; to: number }; components: number;
      components_missing_data: number;
      events: { year: number; item: string; cost: number; cost_escalated: number; source: string; ref: string }[];
      schedule: { year: number; outflows: number; contribution: number; balance: number }[];
      total_outflows: number; first_underfunded_year: number | null; adequately_funded: boolean;
      suggested_level_contribution: number; suggestion_clears_horizon?: boolean; note: string }>(
      `/projects/${pid}/reserves/study${qs ? `?${qs}` : ""}`);
  }
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
  esgSummary(pid: string, gfaSf?: number) {
    const qs = gfaSf ? `?gfa_sf=${gfaSf}` : "";
    return this.json<{
      performance: {
        energy: { total_kbtu: number; eui_kbtu_sf_yr: number | null; months_covered: number; gfa_sf: number | null };
        ghg: { scope1_tco2e: number; scope2_tco2e: number; total_tco2e: number;
          intensity_kgco2e_sf: number | null; grid_factor_kgco2e_kwh: number; note: string };
        water: { gallons: number; intensity_gal_sf: number | null };
      };
      certifications: { credits_tracked: number; points_targeted: number; points_achieved: number };
      poe: { count: number; reported: number; latest: { ref: string; level: string | null; state: string;
        survey_date: string | null; satisfaction_score: number | null; design_eui: number | null;
        actual_eui: number | null; eui_gap_pct: number | null } | null };
      data_coverage: { meter_months: number }; as_of: string }>(`/projects/${pid}/esg${qs}`);
  }

  // --- UNFILED — 23 methods, no shared question --------------------------------
  // This banner said `CX-1 commissioning loop` until SCALE-SEAM (83) took the three `/cx/*`
  // methods to `documents.ts`. It never described the run: it labelled where commissioning
  // STARTED and the file then carried on to the end through a dozen unrelated domains. With the
  // commissioning methods gone it named nothing at all, so it is replaced rather than narrowed —
  // an over-claiming banner is how ⓽, ⓾, (81) and (82) each lost a method to the wrong mixin.
  //
  // The count and the names below are DERIVED, not proofread — `apps/web/src/api/unfiledMap.test.ts`
  // fails if either drifts from the methods underneath. It exists because (83) wrote this map from
  // a regex that did not match `async` methods and under-counted the banner by five.
  //
  // **Do not group by the HTTP mechanism either.** (85) proved that: the five methods this map
  // used to list as *how do I get a file into this project?* were grouped by being multipart
  // uploads, which is a HOW, not a question. Read for what they answer and they split four ways —
  // `takeoffDxf` is a 2D quantity takeoff (it went to `estimate.ts`, beside `takeoff2d`),
  // `raisePlan` writes walls (`authoring.ts`), `uploadSourceIfc` and `importRvt` both set the
  // project's source model, and `rvtBridgeStatus` is the precondition for the second — those three
  // to `model.ts`. Mechanism is as misleading a seam as route prefix.
  //
  // The portfolio trio below LIKELY SPLITS too, and the shapes say so: two of them carry
  // `equity_irr` and `equity_multiple` and sit near what `withProforma` already answers, while
  // `constructionPortfolio` carries recordables, open RFIs and risk exposure and no investment
  // field at all. Read the return types before moving them as one.
  //
  // What is actually below, by what each cluster ANSWERS — decide a home from that, not from the
  // route prefix and not from position:
  //   how much reinforcement?      rebarBbs, rebarBbsCsvUrl
  //   how is the portfolio doing?  executivePortfolio, portfolioPrioritization,
  //                                constructionPortfolio
  //   what saved views are there?  smartViews, smartViewsSave, smartViewRun
  //   how does the model look?     materialPalette, saveMaterialPalette, applyMaterialPalette
  //   what is on this site?        property, saveProperty, testFitCompare, testFitOptimize
  //   four singles, four           complianceExpiring, safetyMetrics, bidLeveling, pxSummary
  //   separate questions
  //   genuinely client-level —     enumOptions, searchAll, attachmentUrl, templates
  //   NOT domain, these stay
  /** REBAR-RULES — the bar bending schedule off the authored IfcReinforcingBar geometry. */
  rebarBbs(pid: string) {
    return this.json<{ rows: { mark: string; size: string | null; diameter_mm: number; shape: string;
      cut_length_m: number; count: number; unit_mass_kg_m: number; total_length_m: number;
      total_kg: number; guids: string[] }[]; marks: number; bars: number; skipped: number;
      total_length_m: number; total_kg: number; total_tonnes: number }>(
      `/projects/${pid}/rebar/bbs`);
  }
  rebarBbsCsvUrl(pid: string) { return this.url(`/projects/${pid}/rebar/bbs.csv`); }


  complianceExpiring(pid: string, withinDays = 30) {
    return this.json<{ within_days: number; count: number;
      expired: { module: string; ref: string; name: string; expires: string; days_left: number }[];
      expiring: { module: string; ref: string; name: string; expires: string; days_left: number }[]; }>(
      `/projects/${pid}/compliance/expiring?within_days=${withinDays}`);
  }
  // E1 — project-level custom select options, nested {module: {field: [values]}}
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
  /** Cross-project CONSTRUCTION health — projected over/under, open risks and exposure,
   *  recordables, open RFIs, per project and as totals. Global (`/portfolio/construction`, no
   *  project id), and unlike `executivePortfolio` it carries no investment figure at all. */
  constructionPortfolio() {
    return this.json<{ project_count: number; totals: { projected_over_under: number; over_budget_count: number; open_risks: number; risk_exposure: number; recordables: number; open_rfis: number }; projects: { id: string; name: string; projected_over_under: number; over_budget: boolean; open_risks: number; risk_exposure: number; recordables: number; open_rfis: number }[] }>(
      "/portfolio/construction");
  }
  /** Safety analytics — incidents by OSHA class, recordable/lost-time counts, TRIR/DART. */
  safetyMetrics(pid: string) {
    return this.json<{ incident_count: number; recordable_count: number; lost_time_count: number; lost_days: number; hours_worked: number; trir: number | null; dart: number | null; observation_count: number; toolbox_talk_count: number }>(
      `/projects/${pid}/safety/metrics`);
  }
  /** Bid leveling — submissions tabulated by package with low/high/avg/spread. */
  bidLeveling(pid: string) {
    return this.json<{ package_count: number; bid_count: number; packages: { package: string; bid_count: number; low: number | null; high: number | null; avg: number | null; spread: number; bids: { bidder: string | null; amount: number | null; is_low: boolean }[] }[] }>(
      `/projects/${pid}/bids/leveling`);
  }
  smartViews(pid: string) {
    return this.json<{ views: SmartView[]; count: number }>(`/projects/${pid}/smart-views`);
  }
  /** Replace the saved smart views (editor). Selectors are validated server-side → 422 on a bad one. */
  smartViewsSave(pid: string, views: SmartView[]) {
    return this.json<{ saved: number; views: SmartView[] }>(
      `/projects/${pid}/smart-views`, { method: "PUT", body: JSON.stringify({ views }) });
  }
  /** Resolve a saved view's selector to the matching GUIDs (to isolate / colour / hide in 3D). */
  smartViewRun(pid: string, vid: string) {
    return this.json<{ id: string; name: string; mode: string; color: string | null;
      selector: string; matched: number; truncated: boolean; guids: string[]; error?: string }>(
      `/projects/${pid}/smart-views/${encodeURIComponent(vid)}/run`);
  }
  /** PX executive health: on-schedule (SPI, % complete, critical path, lookahead, milestones) next
   *  to on-budget (GMP, EAC, variance-at-completion, buyout, cash flow), with an overall status. */
  pxSummary(pid: string) {
    return this.json<{
      status: "on_track" | "at_risk" | "behind";
      schedule: { spi: number | null; pct_complete: number; activities: number; critical_path_days: number;
        critical_activities: number; lookahead_3wk: number; milestones: { late: number; due_soon: number; upcoming: number } };
      budget: { gmp: number; revised_gmp: number; eac: number; variance_at_completion: number; committed: number;
        committed_pct: number; spent_pct: number; draw_this_month: number;
        buyout: { packages: number; bought_out: number; savings: number } | null; baseline_movement: number | null };
    }>(`/projects/${pid}/px-summary`);
  }
  /** The project's saved material overrides, keyed for the viewer. Read side of the pair whose
   *  write is `saveMaterialPalette`; `applyMaterialPalette` pushes the result onto the model. */
  materialPalette(pid: string) {
    return this.json<MaterialPaletteResult>(`/projects/${pid}/materials/palette`);
  }
  saveMaterialPalette(pid: string, overrides: Record<string, MaterialEntry>) {
    return this.json<{ overrides: Record<string, MaterialEntry>; effective: Record<string, MaterialEntry> }>(
      `/projects/${pid}/materials/palette`, { method: "PUT", body: JSON.stringify({ overrides }) });
  }
  applyMaterialPalette(pid: string) {
    return this.json<{ applied: { styled: number; materialed: number; materials: number; classes: number }; publish: string }>(
      `/projects/${pid}/materials/apply`, { method: "POST" });
  }
  /** Cross-project executive roll-up: each project's on-schedule + on-budget status + portfolio totals. */
  executivePortfolio() {
    return this.json<{
      projects: { id: string; name: string; status: "on_track" | "at_risk" | "behind"; spi: number | null;
        cpi: number | null;
        pct_complete: number; lookahead_3wk: number; milestones_late: number; gmp: number; eac: number;
        variance_at_completion: number; committed_pct: number; equity_irr: number | null; equity_multiple: number | null }[];
      totals: { gmp: number; eac: number; variance_at_completion: number; committed: number; equity: number; blended_equity_irr: number | null };
      status_tally: { on_track: number; at_risk: number; behind: number }; project_count: number }>(
      `/portfolio/executive`);
  }
  /** Portfolio prioritization — projects ranked 0-100 on return / budget / schedule / risk. */
  portfolioPrioritization() {
    type Scores = { return: number; budget: number; schedule: number; risk: number };
    return this.json<{ weights: Scores; criteria: string[];
      projects: { id: string; name: string; status: string; rank: number; composite: number;
        scores: Scores; equity_irr: number | null; gmp: number }[];
      top: { name: string } | null; bottom: { name: string } | null; note: string }>(
      `/portfolio/prioritization`);
  }
  /** Property & tax assumptions + computed summary (totals, per-SF ratios, proforma deltas). */
  property(pid: string) {
    return this.json<{ property: Record<string, unknown>; summary: { total_taxes: number; purchase_price: number; price_per_building_sf: number; tax_per_building_sf: number; far_existing: number; deltas: { opex_annual_add: number; acquisition_amount: number } } }>(
      `/projects/${pid}/property`);
  }
  saveProperty(pid: string, body: Record<string, unknown>) {
    return this.json<{ property: Record<string, unknown>; summary: { total_taxes: number; purchase_price: number; deltas: { opex_annual_add: number; acquisition_amount: number } } }>(
      `/projects/${pid}/property`, { method: "PUT", body: JSON.stringify(body) });
  }
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
}

export interface OptScheme {
  name: string; mix_preset: string; parking_ratio: number; total_units: number;
  efficiency: number; total_nsf: number; parking_stalls: number; yield_on_cost: number;
  plate_d?: number; daylight_efficiency?: number; core_efficiency?: number;
  daylight_limited?: boolean; dev_spread_bps?: number;
}
export interface DepthPoint {
  plate_d: number; yield_on_cost: number; daylight_efficiency: number;
  core_efficiency: number; total_units: number; dev_spread_bps: number;
}
export interface MaterialEntry {
  name: string; category: string; color: [number, number, number]; transparency: number;
}
export interface MaterialPaletteResult {
  default: Record<string, MaterialEntry>;
  overrides: Record<string, MaterialEntry>;
  effective: Record<string, MaterialEntry>;
}
export interface EgressResult {
  compliant: boolean; flags: string[]; max_travel_m: number; limit_m: number;
  occupant_load_per_floor: number; min_exits_required: number;
  exit_separation_m: number; required_separation_m: number;
}

export interface ValidationResult {
  title: string;
  status: "pass" | "fail";
  summary: { specifications: number; passed: number; failed: number };
  specifications: { name: string; status: "pass" | "fail"; applicable: number; passed: number; failed: number; failed_guids: string[] }[];
}
