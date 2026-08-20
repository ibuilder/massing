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
import type { ElementProps, LifecycleStrip } from "./types";

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
  };
}
