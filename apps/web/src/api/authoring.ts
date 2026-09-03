/** Authoring: server-side IFC edit recipes, the family/content shelf, the compute graph, the
 *  massing generator, and saved recipe macros — the endpoints that WRITE to the model rather
 *  than read from it.
 *
 *  SCALE-SEAM ㊳ adds editGraph plus the four macro methods that answer *run this parameterized
 *  authoring chain?* Property-override layers sat immediately below in `client.ts` and did
 *  **not** come — those compose properties, they do not write recipes.
 *
 *  SCALE-SEAM ⓻ adds family types — *what families can I place?* List, inspector,
 *  create, edit, material-layer set. Groups sat below and did **not** come with that slice.
 *
 *  SCALE-SEAM ⓼ adds groups and assemblies — *how are these elements grouped?*
 *  List, inspector, create group/assembly, parametric array. Detailing stayed.
 *
 *  First extraction of roadmap SCALE-SEAM. `client.ts` was measured at 4,956 lines with 152 commits
 *  in a fortnight and 631 methods on one class: it had to be opened to add any endpoint, so every
 *  change to it competed with every other change. The server solved this long ago by splitting into
 *  `routers/*.py`; the client kept the seams as comments and never cut along them.
 *
 *  This is a **mixin**, not a separate client, so `api.editIfc(...)` still resolves exactly as it did
 *  — no call site in the app changes. `api/surface.test.ts` asserts that: it captures the runtime
 *  method surface and fails if an extraction drops one, which a typecheck cannot catch (deleting a
 *  method and deleting its last caller both compile clean).
 *
 *  Chosen as the first cut because it reaches nothing but HttpCore's `json`/`url`/`authHeaders`.
 *  The SSE methods cannot follow yet: they call the `private` `liveStream`, and a mixin cannot see a
 *  sibling's private member — that has to move into HttpCore first.
 */
import { HttpCore } from "./httpCore";
import type { AssemblyRow, EditMacro, GroupRow, TypeDetail, TypeRow } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withAuthoring<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Authoring extends Base {
    /** `wantGuid` — adopt the GUID the preview fragment already carries, so the kept delta geometry
     *  and the committed element are one element. See `adopt_guid` in the data engine. */
    editIfc(pid: string, recipe: string, params: Record<string, unknown>, publish = true,
            wantGuid?: string) {
      return this.json<{ recipe: string; changed: number | string; published: unknown }>(
        `/projects/${pid}/edit`,
        // `want_guid` is omitted, not sent as null, when there is no preview to match: the route
        // treats absence as "mint a fresh id", which is the pre-existing behaviour every other
        // caller relies on.
        { method: "POST", body: JSON.stringify(wantGuid ? { recipe, params, publish, want_guid: wantGuid }
                                                        : { recipe, params, publish }) });
    }
    /**
     * R38-SOLVER-LOCKS — solve a dimensional-lock system. Pure computation: the route neither reads
     * nor writes the model, so the caller supplies the variables and applies the result itself.
     *
     * Lives beside `editIfc` because that is what Apply writes through, and the two are always used
     * together. The endpoint shipped in v0.3.701 with no client caller at all.
     *
     * `solved` is false when a REQUIRED row cannot hold or a clearance is violated; `conflicts` names
     * the pair. A weaker tier yielding is the system working as designed, not a failure.
     */
    solveConstraints(pid: string, variables: Record<string, number>,
                     constraints: Record<string, unknown>[]) {
      return this.json<{
        values: Record<string, number>; dof: number; solved: boolean;
        conflicts: { a?: string; b?: string; detail?: string }[];
        violations: Record<string, unknown>[]; note?: string;
      }>(`/projects/${pid}/constraints/solve`,
        { method: "POST", body: JSON.stringify({ variables, constraints }) });
    }
    modelMaintenance(pid: string) {
      return this.json<{ total_entities: number; cleanable: number;
        recipes: { recipe: string; label: string; removable: number; sample: string[] }[] }>(
        `/projects/${pid}/model/maintenance`);
    }
    /** Incremental one-element preview fragment (real geometry, fast) while the full model republishes.
     *  Returns the fragment bytes + new element GUID, or null (fail-open → the viewer keeps its proxy). */
    async editPreview(pid: string, recipe: string, params: Record<string, unknown>):
        Promise<{ frag: ArrayBuffer; guid: string } | null> {
      try {
        const res = await fetch(this.url(`/projects/${pid}/edit-preview`), {
          method: "POST", headers: { "Content-Type": "application/json", ...this.authHeaders() },
          body: JSON.stringify({ recipe, params }),
        });
        if (!res.ok) return null;
        return { frag: await res.arrayBuffer(), guid: res.headers.get("X-Element-Guid") || "" };
      } catch { return null; }
    }
    /** Drafting grid (real IfcGrid or derived from columns) + snap intersections + storey levels. */
    modelGrid(pid: string) {
      return this.json<{
        grid: { source: string;
          axes: { tag: string; dir: "u" | "v"; start: [number, number]; end: [number, number] }[];
          intersections: { x: number; y: number; label: string }[];
          bounds: { min: [number, number]; max: [number, number] } | null; note?: string };
        /**
         * `guid` is the IfcBuildingStorey's GlobalId, and it has been served since this endpoint
         * shipped — `storey_elevations` returns `{name, elevation, guid}`. It was simply not declared
         * here, so no caller could reach it, and R36 slice 6 was scoped as needing a server change to
         * carry a level identity down to the plan cut. It does not.
         *
         * Third instance of one defect shape in a day: the sheet routes were SENT keys they ignore,
         * the spec manual's `elements` were IGNORED though sent, and this. A response type narrower
         * than the response is invisible — nothing fails, the field just cannot be used.
         *
         * It matters that this is the GUID and not the name: levels are renameable here, and markup
         * or state keyed on a name orphans silently on rename. The non-negotiable is GlobalId.
         *
         * Declared REQUIRED, not optional, and that was checked rather than assumed. The route
         * is `/projects/{pid}/model/grid`, which does NOT call `storey_elevations` directly —
         * it calls `grid.grid_and_levels`, which imports it. Traced end to end against
         * `samples/school_str.ifc`: keys are `elevation, guid, name` with a non-empty guid on
         * all five levels. `guid?:` would understate that, and an optional field forces every
         * caller into a defensive branch for a case that cannot occur — which is precisely
         * where a `?? level.name` fallback gets written, reintroducing the rename orphan this
         * field exists to prevent.
         */
        levels: { name: string | null; elevation: number; guid: string }[];
      }>(`/projects/${pid}/model/grid`);
    }
    familyCatalog() {
      return this.json<{ count: number; categories: Record<string, FamilyItem[]> }>("/families/catalog");
    }
    /** The shippable IFC family library: the generated parametric catalog (grouped) plus the
     *  generated `library.ifc` and any curated external `.ifc` files. */
    familyLibrary() {
      return this.json<{ count: number; categories: Record<string, FamilyItem[]>;
        generated_library: { exists: boolean; size_bytes: number };
        external: { name: string; size_bytes: number }[];
        shelf: { count: number; manifest: boolean;
          totals: { packs: number; families: number; types: number; size_bytes: number; undescribed: number };
          packs: FamilyPack[] } }>("/families/library");
    }
    /** Import a family pack already on the server's external shelf — no download-and-re-upload round
     *  trip. `pack` is a plain file name from `familyLibrary().shelf.packs`. */
    importFamilyPack(pid: string, pack: string, publish = false) {
      return this.json<{ imported: string[]; count: number; pack: string; sha256: string;
        described: boolean; discipline?: string | null; declared_types?: number | null;
        note?: string; publish?: string }>(
        `/projects/${pid}/families/import-pack`,
        { method: "POST", body: JSON.stringify({ pack, publish }) });
    }
    /** Place a library family (thin wrapper over the add_family recipe). */
    placeFamily(pid: string, family: string, position?: [number, number] | null) {
      return this.json<{ recipe: string; changed: number | string; publish?: string }>(
        `/projects/${pid}/families/place`, { method: "POST",
        body: JSON.stringify({ family, position: position || undefined, publish: true }) });
    }
    /** Place a starter-library family on a storey (optionally at an [E,N] point in metres), then
     *  publish the round-trip. Reuses the `add_family` edit recipe. */
    addFamily(pid: string, family: string, position?: [number, number] | null, storey?: string | null) {
      const params: Record<string, unknown> = { family };
      if (position) params.position = position;
      if (storey) params.storey = storey;
      return this.editIfc(pid, "add_family", params, true);
    }
    /** Import external IFC type content (manufacturer / 3rd-party families) from an uploaded IFC into
     *  the project; imported types then appear in the place-family picker. */
    async importFamilies(pid: string, file: File, publish = true) {
      const fd = new FormData(); fd.append("file", file);
      const res = await fetch(this.url(`/projects/${pid}/families/import?publish=${publish}`), {
        method: "POST", body: fd, headers: this.authHeaders() });
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `import -> ${res.status}`); }
      return res.json() as Promise<{ imported: { guid: string; name: string; ifc_class: string }[]; count: number; publish?: string }>;
    }
    /**
     * Re-run the pipeline. `reconvert: false` reindexes WITHOUT rebuilding fragments — the index and
     * version snapshot go current while the rendered geometry stays at the previous publish.
     *
     * THE BODY IS A BARE BOOLEAN, NOT AN OBJECT, and that is not a style choice. The route declares
     * `reconvert: bool = Body(default=True)` with no `embed`, so FastAPI takes the whole body as the
     * value. This method sent `{"reconvert": true}` from the day it was written and every call
     * **422'd** — `⟳ Republish` in the rail and the AI plan's Apply were both dead. Nothing caught
     * it: the failure is a rejected promise in a click handler, so the button just never finished.
     */
    publish(pid: string, reconvert = true) {
      return this.json<{ state: string; reconvert?: boolean }>(
        `/projects/${pid}/publish`, { method: "POST", body: JSON.stringify(reconvert) });
    }
    /** Computational-graph (M4) node palette — each node's input/output ports for the visual editor. */
    computeNodes() {
      return this.json<{ nodes: ComputeNodeSpec[] }>("/compute/nodes");
    }
    /** Run a {nodes, edges} compute graph; returns each node's outputs + the execution order. */
    runGraph(graph: ComputeGraph) {
      return this.json<{ order: string[]; results: Record<string, Record<string, unknown>>; node_count: number }>(
        "/compute/graph", { method: "POST", body: JSON.stringify(graph) });
    }
    publishStatus(pid: string) {
      return this.json<{ state: "idle" | "running" | "done" | "error"; detail?: Record<string, unknown> }>(
        `/projects/${pid}/publish/status`);
    }
    /** Generative massing — zoning envelope → program (+ proforma) WITHOUT writing a model. Instant. */
    previewMassing(params: MassingParams) {
      return this.json<MassingResult>("/generate/massing/preview", { method: "POST", body: JSON.stringify(params) });
    }
    /** Generate an IFC massing model from a zoning envelope, set it as the project's source IFC,
     *  publish it (off-thread), and return the program + a starter acquisition proforma. */
    generateMassing(pid: string, params: MassingParams) {
      return this.json<MassingResult & { source_ifc: string; publish: string }>(
        `/projects/${pid}/generate/massing`, { method: "POST", body: JSON.stringify(params) });
    }
    /** massingOptioneer — ranked envelope options over a lever sweep (yield, GFA, units). */
    massingOptioneer(envelope: Record<string, unknown>, opts?: { levers?: Record<string, number[]>; objective?: string; limit?: number }) {
      type Opt = { id: string; levers: Record<string, number>; floors: number; height_m: number;
        gfa_m2: number; gfa_sf: number; net_sellable_m2: number; units: number; far_achieved: number;
        binding_constraint: string; on_frontier: boolean;
        proforma: { total_cost: number; noi: number; stabilized_value: number; profit: number;
          yield_on_cost: number; profit_margin: number } };
      return this.json<{
        scenarios: Opt[]; frontier: string[]; best: string | null; objective: string;
        count: number; shown: number; levers_swept: Record<string, number[]>; note: string;
      }>(`/massing/optioneer`, { method: "POST", body: JSON.stringify({ envelope, levers: opts?.levers ?? null, objective: opts?.objective ?? "yield_on_cost", limit: opts?.limit ?? 24 }) });
    }
    /** massingOptionRecipes — emit a ranked option as the blank-model bootstrap plus edit-recipe steps. */
    massingOptionRecipes(envelope: Record<string, unknown>, option?: string,
                         opts?: { levers?: Record<string, number[]>; objective?: string; limit?: number }) {
      return this.json<{
        option: string; floors: number; floor_to_floor: number; plate_m2: number; plate_side_m: number;
        core_side_m: number;
        bootstrap: { name: string; storeys: number; storey_height: number; ground_size: number };
        steps: { recipe: string; params: Record<string, unknown> }[]; step_count: number; note: string;
      }>(`/massing/optioneer/recipes`, { method: "POST", body: JSON.stringify({
        envelope, option: option ?? "", levers: opts?.levers ?? null,
        objective: opts?.objective ?? "yield_on_cost", limit: opts?.limit ?? 24 }) });
    }
    /** Create a blank authoring model (base IFC + levels + ground datum) — the from-scratch start for
     *  the in-browser modeler; sets it as the project's source IFC + publishes. */
    createBlankModel(pid: string, opts?: { name?: string; storeys?: number; storey_height?: number }) {
      return this.json<{ storeys: number; storey_height: number; source_ifc: string; publish: string }>(
        `/projects/${pid}/model/blank`, { method: "POST", body: JSON.stringify(opts || {}) });
    }
    /** Live recipe coverage by concern — derived from `edit.RECIPES`, not a hand list. */
    authoringMatrix() {
      return this.json<{
        recipe_count: number; category_count: number; uncategorized: string[];
        by_category: Record<string, { count: number; recipes: { recipe: string; category: string; produces: string }[] }>;
        note: string;
      }>("/reference/authoring-matrix");
    }
    /** Per-IfcSpace rule pack folded into `/rules/run` (dimensional / daylight / wet-wall). */
    spacePack(pid: string) {
      return this.json<{ pack: Record<string, unknown> | null }>(
        `/projects/${pid}/rules/space-pack`);
    }

    /** editGraph — execute a visual recipe graph as one GUID-stable authoring pass. */
    editGraph(pid: string, graph: unknown, opts?: { publish?: boolean; baseSource?: string }) {
      return this.json<{ node_count: number; order: string[]; outputs: Record<string, unknown>; publish?: string }>(
        `/projects/${pid}/edit/graph`,
        { method: "POST", body: JSON.stringify({ graph, publish: opts?.publish ?? false, base_source: opts?.baseSource ?? null }) });
    }
    /** listMacros — saved, parameterized chained edit-recipes for this project. */
    listMacros(pid: string) {
      return this.json<{ macros: EditMacro[]; seeded: boolean }>(`/projects/${pid}/macros`);
    }
    /** saveMacros — replace the project's saved recipe-macro list. */
    saveMacros(pid: string, macros: EditMacro[]) {
      return this.json<{ saved: number; macros: EditMacro[] }>(
        `/projects/${pid}/macros`, { method: "PUT", body: JSON.stringify({ macros }) });
    }
    /** expandMacro — expand one macro plus args into GUID-stable recipe steps. */
    expandMacro(pid: string, macroId: string, args: Record<string, unknown>) {
      return this.json<{ macro: string; name: string; steps: { recipe: string; params: Record<string, unknown> }[]; step_count: number }>(
        `/projects/${pid}/macros/${encodeURIComponent(macroId)}/expand`, { method: "POST", body: JSON.stringify({ args }) });
    }
    /** runMacro — run a saved recipe chain as one GUID-stable version. */
    runMacro(pid: string, macroId: string, args: Record<string, unknown>, opts?: { publish?: boolean; baseSource?: string }) {
      return this.json<Record<string, unknown>>(
        `/projects/${pid}/macros/${encodeURIComponent(macroId)}/run`,
        { method: "POST", body: JSON.stringify({ args, publish: opts?.publish ?? false, base_source: opts?.baseSource ?? null }) });
    }
    /** Placeable types ("families") in the project's source IFC, for the place-family picker and the
     *  type browser. Carries PredefinedType + how many occurrences reference each type. */
    types(pid: string) {
      return this.json<{ types: TypeRow[] }>(`/projects/${pid}/types`);
    }
    /** W10-1 type inspector: class, predefined, box dims, type Psets, material layers, occurrences. */
    typeDetail(pid: string, typeGuid: string) {
      return this.json<TypeDetail>(`/projects/${pid}/types/${encodeURIComponent(typeGuid)}`);
    }
    /** W10-1: author a custom family type (class + optional [w,d,h] box + PredefinedType + type Psets).
     *  Returns the new type GUID in `changed`. Versioned + GUID-stable via the /edit recipe path. */
    createType(pid: string, ifc_class: string, name: string, dims?: [number, number, number] | null,
               predefined?: string | null, psets?: Record<string, Record<string, unknown>> | null,
               publish = true) {
      return this.editIfc(pid, "create_type", { ifc_class, name, dims, predefined, psets }, publish);
    }
    /** W10-1: edit a type's params. Changing `dims` propagates to EVERY placed occurrence at once
     *  (shared RepresentationMap), GUID-stable — no re-placement. */
    editType(pid: string, type_guid: string, patch: { name?: string; dims?: [number, number, number];
               predefined?: string; psets?: Record<string, Record<string, unknown>> }, publish = true) {
      return this.editIfc(pid, "edit_type_params", { type_guid, ...patch }, publish);
    }
    /** W10-1: give a type an ordered IfcMaterialLayerSet ([{material, thickness(m)}]); occurrences inherit. */
    assignMaterialSet(pid: string, type_guid: string,
                      layers: { material: string; thickness: number }[], publish = true) {
      return this.editIfc(pid, "assign_material_set", { type_guid, layers }, publish);
    }
    /** W10-3: every IfcGroup (named set) and IfcElementAssembly (part-of whole) with member counts. */
    groups(pid: string) {
      return this.json<{ groups: GroupRow[]; assemblies: AssemblyRow[] }>(`/projects/${pid}/groups`);
    }
    /** W10-3 inspector: the members/parts of one group or assembly. */
    groupDetail(pid: string, guid: string) {
      return this.json<{ guid: string; kind: "group" | "assembly"; name: string; member_count: number;
        members: { guid: string; name: string; ifc_class: string }[] }>(
        `/projects/${pid}/groups/${encodeURIComponent(guid)}`);
    }
    /** W10-3: author an IfcGroup (named set) over the given element GUIDs (re-using a name adds to it). */
    createGroup(pid: string, name: string, guids: string[], publish = true) {
      return this.editIfc(pid, "create_group", { name, guids }, publish);
    }
    /** W10-3: aggregate the given elements into an IfcElementAssembly (a real part-of whole). */
    createAssembly(pid: string, name: string, guids: string[], predefined?: string | null, publish = true) {
      return this.editIfc(pid, "create_assembly", { name, guids, predefined }, publish);
    }
    /** W10-3: rectangular parametric array — nx×ny copies at pitch (dx,dy) m (dz per column). */
    arrayElement(pid: string, guid: string, nx: number, ny: number, dx: number, dy: number, dz = 0, publish = true) {
      return this.editIfc(pid, "array_element", { guid, nx, ny, dx, dy, dz }, publish);
    }
  };
}

export interface FamilyItem {
  key: string; label: string; ifc_class: string; category: string; dims: [number, number, number];
}
export interface FamilyPack {
  name: string; size_bytes: number; described: boolean;
  discipline?: string; families?: number; types?: number; tiers?: string[];
  licence?: string; version?: string;
}
export interface ComputeNodeSpec {
  key: string; label: string; category: string; doc: string;
  inputs: { name: string; default: number | string | null }[];
  outputs: string[];
}
export interface ComputeGraph {
  nodes: { id: string; type: string; params: Record<string, number | string> }[];
  edges: { from: string; from_port: string; to: string; to_port: string }[];
}
export interface MassingParams {
  name?: string; use_type?: "residential" | "commercial";
  lot_width?: number | null; lot_depth?: number | null; lot_area?: number | null;
  far?: number; coverage_max?: number; front_setback?: number; rear_setback?: number;
  side_setback?: number; height_limit?: number | null; floor_to_floor?: number;
  efficiency?: number; avg_unit_m2?: number;
  frame?: boolean; bay_m?: number; units?: boolean; envelope?: boolean; wwr?: number; core?: boolean;
  unit_layout?: "grid" | "corridor"; parking?: number;
  shape?: "box" | "dome"; dome_radius?: number;
  land_cost?: number; hard_cost_psf?: number; rent_per_unit_month?: number; rent_psf_year?: number;
  exit_cap?: number; ltc?: number; rate?: number;
}
export interface MassingMetrics {
  lot_area_m2: number; far: number; far_achieved: number; footprint_m2: number;
  plate_w: number; plate_d: number; floors: number; floor_to_floor: number;
  building_height_m: number; buildable_gfa_m2: number; buildable_gfa_sf: number;
  net_sellable_m2: number; units: number; binding_constraint: string;
  structure?: { system: string; lateral_system: string; rationale: string; load_path: string;
    slenderness: number; members_mm: { slab: number; beam_depth: number; column: number; uses_beams: boolean };
    column_schedule?: { floor: number; floors_carried: number; side_mm: number }[];
    base_column_mm?: number; top_column_mm?: number;
    lateral_core?: { provided: boolean; plan_w_m: number; plan_d_m: number; wall_mm: number; note: string };
    flags: string[] };
}
export interface MassingResult {
  metrics: MassingMetrics;
  proforma: { assumptions: Record<string, unknown>;
    returns?: { equity_irr?: number; equity_multiple?: number } | null;
    sources_uses?: { total_uses?: number; equity?: number; loan_amount?: number } | null;
    solve_error?: string };
}
