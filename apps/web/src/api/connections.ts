/** Data-source connections — SQL, ACC, Procore mappings.
 *
 *  SCALE-SEAM ⑫. Route-group `/connections`, taken out of `client.ts` by the route each method
 *  calls — the recipe ⑥ established and ⑦–⑪ repeated.
 *
 *  **Eleven methods, one contiguous run.** They sat under `// --- data-source connections ---`
 *  and this time the section comment and the route actually agreed: nothing after
 *  `saveConnectionMappings` calls `/connections`. `syncProcore` / `pushProcore` / the schedule
 *  CRUD sit immediately below and route to `/projects/{pid}/sync/…` — grouping by the comment
 *  would have been right here, grouping by route is what keeps `/sync` for a later cut.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it: moving
 *  a method is invisible to it, losing one fails it by number.
 */
import { HttpCore } from "./httpCore";
import type { ConnectionItem } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withConnections<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Connections extends Base {
  connections() {
    return this.json<{ types: string[]; connections: ConnectionItem[] }>("/connections");
  }
  createConnection(name: string, type: string, config: Record<string, unknown>) {
    return this.json<ConnectionItem>("/connections", { method: "POST", body: JSON.stringify({ name, type, config }) });
  }
  updateConnection(id: string, name: string, type: string, config: Record<string, unknown>) {
    return this.json<ConnectionItem>(`/connections/${id}`, { method: "PUT", body: JSON.stringify({ name, type, config }) });
  }
  deleteConnection(id: string) {
    return this.json<{ ok: boolean }>(`/connections/${id}`, { method: "DELETE" });
  }
  testConnectionConfig(type: string, config: Record<string, unknown>) {
    return this.json<{ ok: boolean; detail: string }>("/connections/test", { method: "POST", body: JSON.stringify({ type, config }) });
  }
  testConnection(id: string) {
    return this.json<{ status: { ok: boolean; detail: string }; info: Record<string, unknown> }>(
      `/connections/${id}/test`, { method: "POST" });
  }
  /** Browse a connection: tables (SQL) or projects (Procore). */
  connectionTables(id: string) {
    return this.json<{ kind?: string; tables?: string[]; projects?: string[]; error?: string }>(
      `/connections/${id}/tables`);
  }
  /** Run a read-only SELECT against a SQL connection. */
  connectionQuery(id: string, sql: string, limit = 200) {
    return this.json<{ columns?: string[]; rows?: unknown[][]; row_count?: number; error?: string }>(
      `/connections/${id}/query`, { method: "POST", body: JSON.stringify({ sql, limit }) });
  }
  /** Read an ACC (Autodesk Construction Cloud) project's issues. */
  accIssues(id: string, projectId: string) {
    return this.json<{ kind?: string; count?: number; issues?: Record<string, unknown>[]; error?: string }>(
      `/connections/${id}/acc/projects/${projectId}/issues`);
  }
  /** Editable Procore->module field mapping for a connection (admin). */
  connectionMappings(id: string) {
    return this.json<{ mappings: Record<string, { module: string; fields: { field: string; label: string; default: string; path: string }[] }> }>(
      `/connections/${id}/mappings`);
  }
  /** Save per-field Procore source-path overrides ({kind: {field: path}}). */
  saveConnectionMappings(id: string, mappings: Record<string, Record<string, string>>) {
    return this.json<{ ok: boolean }>(`/connections/${id}/mappings`, { method: "PUT", body: JSON.stringify({ mappings }) });
  }
  };
}
