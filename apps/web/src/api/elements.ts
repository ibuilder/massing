/** Element properties, lifecycle, 5D, colouring, QA, citations, tied records, costs.
 *
 *  SCALE-SEAM ⑯. Route-group `/projects/{pid}/elements`, taken out of `client.ts` by the route
 *  each method calls. Eleven methods in **five** regions — inspector next to the job tray,
 *  list/colour/QA next to Speckle, sources next to the doc-graph, records next to model health,
 *  costs next to the cost-spine. `elements5dMap` is `/5d/heatmap` and stays.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { ElementProps, LifecycleStrip, SpatialNode } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withElements<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Elements extends Base {
  element(pid: string, guid: string) {
    return this.json<ElementProps>(`/projects/${pid}/elements/${guid}`);
  }
  /** R26-INSPECTOR — the six-state lifecycle strip for one element (designed → verified). A state
   *  the server could not consult comes back `unknown`, which is NOT the same as `none`. */
  elementLifecycle(pid: string, guid: string) {
    return this.json<LifecycleStrip>(`/projects/${pid}/elements/${guid}/lifecycle`);
  }
  /** 5D for an element: its schedule activity (%-complete, dates, hard-tied?) + cost-code budget. */
  element5d(pid: string, guid: string) {
    return this.json<{ guid: string; ifc_class: string | null; storey: string | null; name: string | null;
      schedule: { ref: string; name: string; trade: string | null; percent: number; start: string | null;
        finish: string | null; state: string | null; hard_tied: boolean } | null;
      cost: { code: string | null; ref: string | null; name: string | null; division: string | null;
        budget: number; committed: number; actual: number; eac: number; variance: number } | null }>(
      `/projects/${pid}/elements/${guid}/5d`);
  }
  /** R43-VIEWER-CONFORMANCE — the IFC spatial hierarchy as one root node (Project ▸ Site ▸
   *  Building ▸ Storey ▸ Space), derived server-side from decomposition rather than from the
   *  `storey` name string every element carries. Use it to group elements by `storey_guid`.
   *
   *  **Refuses (422) on a project whose element index predates `index_schema: 2`** — such an index
   *  has no tree, and neither does a model with genuinely no spatial structure (404). They are
   *  different answers on purpose: only the first is fixed by re-publishing the index, and a caller
   *  that treats both as "no tree" tells the user the wrong thing about one of them.
   */
  spatialTree(pid: string) {
    return this.json<SpatialNode>(`/projects/${pid}/spatial-tree`);
  }
  //
  // `POST /projects/{pid}/elements/properties` is deliberately ABSENT from this client.
  //
  // It exists for MassingViewer's `RemoteKernel`, which fetches property sets for a multi-selection
  // in one request. Our own model browser has no use for it: `elements()` already returns every
  // element with its psets inline, so a bulk re-fetch would be a second copy of data the tree is
  // holding. A typed method here with no caller would exist only to satisfy the route-reachability
  // gate — which is the gate measuring itself, and worse than the gap it papers over.
  //
  // Recorded rather than left implicit because `test_route_reachability` does NOT flag that route:
  // its rule matches on the distinctive leaf, and `properties` already appears in this client for
  // `/properties/index` and `/properties/meta`. So the route passes the gate by coincidence, not by
  // judgement, and this comment is the judgement. `services/api/test_spatial_tree.py` is what
  // actually holds the endpoint's contract.
  elements(pid: string, params: { ifc_class?: string; storey?: string; limit?: number } = {}) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return this.json<ElementProps[]>(`/projects/${pid}/elements?${q}`);
  }
  /** Properties you can colour the model by (attributes + pset/qto props), for the picker. */
  colorFacets(pid: string) {
    return this.json<{ attributes: { prop: string; label: string; distinct: number }[];
      properties: { prop: string; label: string; distinct: number }[] }>(
      `/projects/${pid}/elements/facets-list`);
  }
  /** Bucket every element by a property → colour buckets (numeric binned, categorical grouped). */
  colorBy(pid: string, prop: string, bins = 6) {
    return this.json<{ prop: string; kind: "numeric" | "categorical"; total: number; colored: number;
      unset: number; buckets: { label: string; count: number; guids: string[] }[] }>(
      `/projects/${pid}/elements/color-by?prop=${encodeURIComponent(prop)}&bins=${bins}`);
  }
  /** Model composition by NCS discipline — element count + class breakdown, in sheet order. */
  elementsByDiscipline(pid: string) {
    return this.json<{
      total: number;
      disciplines: { discipline: string; code: string; count: number;
        classes: { ifc_class: string; count: number }[] }[];
      coverage: { discipline: string; code: string; color: string; present: boolean; count: number }[];
      disciplines_covered: number; disciplines_total: number; missing: string[];
    }>(`/projects/${pid}/elements/by-discipline`);
  }
  /** BIM data-completeness check: per-attribute present/missing + non-compliant guids to highlight. */
  dataQa(pid: string) {
    return this.json<{ total: number; compliant: number; noncompliant: number; compliant_pct: number;
      rules: { key: string; label: string; severity: string; present: number; missing: number; missing_guids: string[] }[];
      noncompliant_guids: string[] }>(`/projects/${pid}/elements/qa`);
  }
  /** Code-readiness check: does the model carry the data a plan review needs (property-level). */
  codeCheck(pid: string) {
    return this.json<{ code: string; rules: number; checked: number; passed: number; readiness_pct: number;
      checks: { id: string; label: string; code: string; note: string; applies: string; checked: number;
        passed: number; failed: number; below_min: number; fail_guids: string[]; status: string }[];
      fail_guids: string[] }>(`/projects/${pid}/elements/code-check`);
  }
  // the cited provenance of one element (spec sections · documents · location)
  elementSources(pid: string, guid: string) {
    return this.json<{
      guid: string; found: boolean; name?: string | null; class?: string;
      spec_sections?: { system: string | null; code: string; title: string }[];
      documents?: { name: string; sheet: string }[];
      container?: { guid: string | null; name: string | null; class: string } | null;
      citations: { kind: string; ref: string; title?: string; sheet?: string; source: string }[];
    }>(`/projects/${pid}/elements/${encodeURIComponent(guid)}/sources`);
  }
  /** Reverse deep-link — every record across pinnable modules tied to this element by GlobalId. */
  elementRecords(pid: string, guid: string) {
    return this.json<{ guid: string; total: number;
      modules: { module: string; module_name: string; icon: string; count: number;
        records: { ref: string | null; title: string; id: number; state: string | null }[] }[] }>(
      `/projects/${pid}/elements/${encodeURIComponent(guid)}/records`);
  }
  /** Every cost line (budget / commitment / direct cost / sub invoice) tagged to one IFC element. */
  elementCosts(pid: string, guid: string) {
    return this.json<{ guid: string; total: number; count: number; by_kind: Record<string, number>;
      lines: { kind: string; ref: string | null; cost_code: string | null; amount: number }[]; note: string }>(
      `/projects/${pid}/elements/${encodeURIComponent(guid)}/costs`);
  }
  /** 5D-BIND — GUID-keyed quantity × class rate over the live property index (not per-element costs). */
  elementCosts5d(pid: string) {
    return this.json<{
      element_count: number; priced: number; total_cost: number;
      carbon_matched: number; total_carbon_kgco2e: number;
      by_class: Record<string, { cost: number; count: number }>;
      by_storey: Record<string, number>;
      top_cost: { guid: string; name: string | null; ifc_class: string; cost: number }[];
    }>(`/projects/${pid}/5d/element-costs`);
  }
  };
}
