/** Modules: the config-driven register engine — CRUD over any of the 133 `module.json` registers,
 *  plus import/export, bulk actions, relations, comments and the per-record activity timeline.
 *
 *  SCALE-SEAM ④. Route-group `/modules`, 34 methods — the largest group left in `client.ts` after
 *  `/model` went in ③, and the one most call sites touch: every register screen in the portal is
 *  built on `moduleRecords` / `createModuleRecord` / `updateModuleRecord`.
 *
 *  Reaches `json` / `url` / `authHeaders` / `authToken` on HttpCore and nothing else. `authToken` is
 *  `protected` rather than `private` precisely so cache keys can be identity-scoped without the token
 *  joining the public surface — `surface.test.ts` asserts it stays off that surface.
 *
 *  A mixin, so every call site resolves unchanged. The surface ratchet (`>= 696`) is what proves it:
 *  moving a method is invisible to it, losing one fails it by number.
 */
import type {
  ModuleBoard, ModuleDef, ModuleFilterOp, ModuleRecord, RecordAttachmentMeta, RelatedRecords,
  SavedViewDef,
} from "./types";

import type { Cached } from "./recordCache";

import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withModules<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Modules extends Base {
  /** Resolve a record's distribution (CC) field against the contact directory → recipients + emails. */
  recordDistribution(pid: string, key: string, rid: string) {
    return this.json<{ ref: string; recipients: { name: string; email: string | null; resolved: boolean }[];
      emails: string[] }>(`/projects/${pid}/modules/${key}/${rid}/distribution`);
  }
  /** SCHED-CALC — formula columns over module records ({name, expr}; fields = normalized data keys). */
  moduleCalc(pid: string, key: string, calcs: { name: string; expr: string }[],
             opts?: { state?: string; q?: string; limit?: number }) {
    return this.json<{ columns: string[]; record_count: number;
      rows: { id: string; ref: string | null; values: Record<string, string | number | boolean | null> }[];
      note: string }>(
      `/projects/${pid}/modules/${key}/calc`,
      { method: "POST", body: JSON.stringify({ calcs, ...opts }) });
  }
  /** TOPIC-LIFE — the topic's merged history (creation, status moves, threaded comments, viewpoints,
   * attachments) + the canonical status machine and this topic's allowed next transitions. */
  // GC portal modules + model pins
  modules() {
    return this.json<ModuleDef[]>(`/modules`);
  }
  /** R26 — the room spine plus the allocation of every module to exactly one room. */
  moduleRecords(pid: string, key: string) {
    return this.json<ModuleRecord[]>(`/projects/${pid}/modules/${key}`);
  }

  /**
   * CACHE-JSON — records, served from cache first and revalidated behind you.
   *
   * `moduleRecords` above is unchanged and still the right call when you need a guaranteed-current
   * answer (immediately after a write, or before a decision that depends on it). This is for the
   * common case: opening a panel to look at a list.
   *
   * The result is NOT a bare array. It carries `fresh` and `ageSeconds`, because a cached list is a
   * claim about the present made from the past, and a caller that cannot tell the difference will
   * eventually present stale data as current. `freshnessLabel()` turns it into something to show.
   */
  async moduleRecordsCached(
    pid: string, key: string, onFresh?: (rows: ModuleRecord[]) => void,
  ): Promise<Cached<ModuleRecord[]>> {
    const { recordsKey, swr } = await import("./recordCache");
    const { identityScope } = await import("./identity");
    return swr<ModuleRecord[]>(
      recordsKey(pid, key, identityScope(this.authToken)),
      () => this.json<ModuleRecord[]>(`/projects/${pid}/modules/${key}`),
      onFresh ? { onFresh } : {},
    );
  }
  moduleRecord(pid: string, key: string, rid: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}`);
  }
  createModuleRecord(pid: string, key: string, body: Record<string, unknown>) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}`, {
      method: "POST", body: JSON.stringify(body) });
  }
  /** Download URL for a module's header-only import template (CSV). */
  importTemplateUrl(pid: string, key: string) {
    return this.url(`/projects/${pid}/modules/${key}/import-template.csv`);
  }
  /** Step 1 of a generic Excel/CSV import: parse + auto-map columns to fields + coerce a sample. */
  async importPreview(pid: string, key: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/import/preview`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Import preview -> ${res.status}`);
    return res.json() as Promise<{ headers: string[]; row_count: number; unmapped_required: string[];
      suggested_mapping: Record<string, string>; sample: Record<string, unknown>[];
      fields: { name: string; label: string; type: string; required: boolean }[] }>;
  }
  /** Step 2: import the sheet with a column->field mapping. */
  async importModuleRecords(pid: string, key: string, file: File, mapping: Record<string, string>) {
    const fd = new FormData(); fd.append("file", file); fd.append("mapping", JSON.stringify(mapping));
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/import`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Import -> ${res.status}`);
    return res.json() as Promise<{ imported: number; error_count: number;
      errors: { row: number; error: string }[]; truncated: boolean }>;
  }
  transitionRecord(pid: string, key: string, rid: string, action: string, note?: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/transition`, {
      method: "POST", body: JSON.stringify({ action, note }) });
  }
  linkRecord(pid: string, key: string, rid: string, module: string, id: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/link`, {
      method: "POST", body: JSON.stringify({ module, id }) });
  }
  // compliance expiry: COI + permit certs expiring soon / already expired
  addEnumOption(pid: string, key: string, field: string, value: string) {
    return this.json<{ module: string; field: string; value: string; options: string[] }>(
      `/projects/${pid}/modules/${key}/enum/${field}`, { method: "POST", body: JSON.stringify({ value }) });
  }
  addComment(pid: string, key: string, rid: string, text: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/comments`, {
      method: "POST", body: JSON.stringify({ text }) });
  }
  updateModuleRecord(pid: string, key: string, rid: string, data: Record<string, unknown>,
                     expectedModifiedAt?: string | null) {
    // pass the modified_at the editor loaded to opt into the optimistic lock — a concurrent edit
    // returns 409 instead of a silent overwrite (the caller reloads to reconcile).
    const qs = expectedModifiedAt ? `?expected_modified_at=${encodeURIComponent(expectedModifiedAt)}` : "";
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}${qs}`, {
      method: "PATCH", body: JSON.stringify(data) });
  }
  deleteModuleRecord(pid: string, key: string, rid: string) {
    return this.json<{ deleted: boolean; ref: string }>(`/projects/${pid}/modules/${key}/${rid}`, {
      method: "DELETE" });
  }
  relatedRecords(pid: string, key: string, rid: string) {
    return this.json<RelatedRecords>(`/projects/${pid}/modules/${key}/${rid}/related`);
  }
  moduleBoard(pid: string, key: string) {
    return this.json<ModuleBoard>(`/projects/${pid}/modules/${key}/board`);
  }
  /** The saved views defined on one module's register. */
  listViews(pid: string, key: string) {
    return this.json<SavedViewDef[]>(`/projects/${pid}/modules/${key}/views`);
  }
  saveView(pid: string, key: string, name: string, config: Record<string, unknown>) {
    return this.json<SavedViewDef>(`/projects/${pid}/modules/${key}/views`, {
      method: "POST", body: JSON.stringify({ name, config }) });
  }
  deleteView(pid: string, key: string, vid: string) {
    return this.json<{ deleted: boolean }>(`/projects/${pid}/modules/${key}/views/${vid}`, { method: "DELETE" });
  }
  /** Mark a saved view as seen (clears its 'new' alert count). */
  markViewSeen(pid: string, key: string, vid: string) {
    return this.json<{ ok: boolean; last_seen_at: string }>(
      `/projects/${pid}/modules/${key}/views/${vid}/seen`, { method: "POST" });
  }
  /** SSE stream of the notification feed; returns a resilient handle so callers can close it. */
  bulkAction(pid: string, key: string, ids: string[], action: "transition" | "assign" | "delete", value?: string) {
    return this.json<{ ok: number; failed: { id: string; error: string }[] }>(
      `/projects/${pid}/modules/${key}/bulk`, { method: "POST", body: JSON.stringify({ ids, action, value }) });
  }
  /**
   * MOD-FILTER — a register page, narrowed and ordered by the SERVER.
   *
   * `filters` becomes one `f.<field>[.<op>]=<value>` parameter each, and `sort`/`sort_dir` order the
   * whole register rather than the fetched page. Both matter for the same reason: narrowing or
   * ordering a page after it arrives answers a different question than the one asked, and the wrong
   * answer is indistinguishable from the right one. "Sort by amount" on a 500-row register used to
   * order the 200 rows already in the browser.
   *
   * An unknown field or operator is a 400 from the server, deliberately — a filter that is quietly
   * dropped returns MORE rows than were requested, which reads as data rather than as a bug.
   */
  moduleRecordsFiltered(pid: string, key: string, opts: {
    q?: string; state?: string; limit?: number; offset?: number;
    /**
     * A LIST, not a map keyed by field — a range is two clauses on one field (`amount.gte` **and**
     * `amount.lte`), so a field-keyed map cannot express it: the second entry overwrites the first and
     * a range silently collapses to a single bound, which is a narrower result that looks correct.
     */
    filters?: { field: string; op?: ModuleFilterOp; value?: string }[];
    sort?: string; sortDir?: "asc" | "desc";
  } = {}) {
    const p = new URLSearchParams();
    if (opts.q) p.set("q", opts.q);
    if (opts.state) p.set("state", opts.state);
    if (opts.limit != null) p.set("limit", String(opts.limit));
    if (opts.offset) p.set("offset", String(opts.offset));
    for (const { field, op = "eq", value } of opts.filters ?? []) {
      // `empty`/`nonempty` are predicates on their own; every other op needs a value, and sending a
      // blank one would filter for the empty string rather than not filtering at all.
      if (op !== "empty" && op !== "nonempty" && (value == null || value === "")) continue;
      // `append`, not `set`: two clauses on one field must both survive into the query string.
      p.append(op === "eq" ? `f.${field}` : `f.${field}.${op}`, value ?? "1");
    }
    if (opts.sort) {
      p.set("sort", opts.sort);
      p.set("sort_dir", opts.sortDir === "desc" ? "desc" : "asc");
    }
    const qs = p.toString();
    return this.json<ModuleRecord[]>(`/projects/${pid}/modules/${key}${qs ? `?${qs}` : ""}`);
  }
  /** Create a tracked revision of a record (revisable modules); re-opens the workflow. */
  reviseRecord(pid: string, key: string, rid: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/revise`, { method: "POST" });
  }
  assignRecord(pid: string, key: string, rid: string, assignee: string | null) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/assign`, {
      method: "POST", body: JSON.stringify({ assignee }) });
  }
  async uploadAttachment(pid: string, key: string, rid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/${rid}/attachments`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`upload -> ${res.status}`);
    return res.json() as Promise<RecordAttachmentMeta>;
  }
  /** Export a module's records as a BCF .bcfzip (auth'd blob, for coordination-issue interop). */
  async downloadModuleBcf(pid: string, key: string) {
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/bcf/export`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`BCF export -> ${res.status}`);
    return res.blob();
  }
  /** Import a BCF .bcfzip as records in a module. */
  async importModuleBcf(pid: string, key: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/bcf/import`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`BCF import -> ${res.status}`);
    return res.json() as Promise<{ count: number; ids: string[] }>;
  }
  /** Tie model elements (IFC GlobalIds) to a record. mode: add | remove | set. */
  tagElements(pid: string, key: string, rid: string, guids: string[], mode: "add" | "remove" | "set" = "add") {
    return this.json<{ element_guids: string[]; count: number }>(
      `/projects/${pid}/modules/${key}/${rid}/elements`, { method: "POST", body: JSON.stringify({ guids, mode }) });
  }
  /** Attach many files at once (bulk site-photo upload). */
  async uploadAttachmentsBulk(pid: string, key: string, rid: string, files: File[] | FileList) {
    const fd = new FormData();
    for (const f of Array.from(files)) fd.append("files", f);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/${rid}/attachments/bulk`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`bulk upload -> ${res.status}`);
    return res.json() as Promise<{ count: number; attachments: RecordAttachmentMeta[] }>;
  }
  saveTemplate(pid: string, key: string, name: string) {
    return this.json<{ id: string; item_count: number }>(`/projects/${pid}/modules/${key}/save-template`, { method: "POST", body: JSON.stringify({ name }) });
  }
  applyTemplate(pid: string, key: string, tid: string) {
    return this.json<{ applied: string; created: number }>(`/projects/${pid}/modules/${key}/apply-template/${tid}`, { method: "POST" });
  }
  /** The module-relations graph: nodes = modules, edges = reference + rollup links (optional workspace). */
  modulesGraph(workspace?: string) {
    const qs = workspace ? `?workspace=${encodeURIComponent(workspace)}` : "";
    return this.json<ModuleGraph>(`/modules/graph${qs}`);
  }
  /** Printable register PDF (RFI log, submittal log) from the same module engine. */
  moduleLogPdfUrl(pid: string, key: string) {
    return this.url(`/projects/${pid}/modules/${encodeURIComponent(key)}/log.pdf`);
  }
  };
}

export interface ModuleGraphNode {
  key: string; label: string; section: string; workspace: string; icon: string;
  in_degree: number; out_degree: number;
}
export interface ModuleGraphEdge {
  source: string; target: string; field: string | null; label: string; kind: "reference" | "rollup";
}
export interface ModuleGraph {
  workspace: string | null; node_count: number; edge_count: number;
  nodes: ModuleGraphNode[]; edges: ModuleGraphEdge[];
  most_referenced: { key: string; label: string; in_degree: number }[]; orphan_count: number;
}
