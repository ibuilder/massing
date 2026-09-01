/** Document-control file manager: tree, folders, health, upload/move/delete, download.
 *
 *  SCALE-SEAM ⑱. Route-group `/projects/{pid}/documents`, taken out of `client.ts` by the
 *  route each method calls. **Nine methods, one contiguous run** under
 *  `// --- Document control / file manager ---` — this time the section comment and the route
 *  agree. Named `documents.ts` so it does not collide with `api/docqa.ts` (`/review` + `/doctext`).
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { DocFile, DocFolderNode } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withDocuments<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Documents extends Base {
  // --- Document control / file manager (F1-F6) ---------------------------------
  documentsTree(pid: string) {
    return this.json<{ project: string; total_files: number; required_gaps: string[];
      nodes: DocFolderNode[] }>(`/projects/${pid}/documents/tree`);
  }
  documentsFolder(pid: string, path: string, superseded = false) {
    const q = `?path=${encodeURIComponent(path)}${superseded ? "&superseded=true" : ""}`;
    return this.json<{ folder: string; owner_role: string | null; valid_folder: boolean;
      count: number; files: DocFile[] }>(`/projects/${pid}/documents/folder${q}`);
  }
  documentsByRole(pid: string, role: string) {
    return this.json<{ role: string; count: number; folders: DocFolderNode[] }>(
      `/projects/${pid}/documents/by-role?role=${encodeURIComponent(role)}`);
  }
  documentsHealth(pid: string) {
    return this.json<{ total_files: number; naming_compliance_pct: number | null;
      required_coverage_pct: number | null; revision_control_pct: number | null;
      required_missing: string[]; by_cde_state: Record<string, number>; superseded_kept: number }>(
      `/projects/${pid}/documents/health`);
  }
  documentsPhaseGaps(pid: string, phase: string) {
    return this.json<{ phase: string; missing: number; complete: boolean;
      items: { folder: string; description: string; present: boolean }[] }>(
      `/projects/${pid}/documents/phase-gaps?phase=${encodeURIComponent(phase)}`);
  }
  async uploadDocument(pid: string, path: string, file: File,
      meta: { title?: string; discipline?: string; doc_type?: string; cde_state?: string } = {}) {
    const fd = new FormData();
    fd.append("path", path); fd.append("file", file);
    for (const [k, v] of Object.entries(meta)) if (v) fd.append(k, v);
    const res = await fetch(this.url(`/projects/${pid}/documents/upload`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `upload failed (${res.status})`);
    return res.json() as Promise<{ entry: DocFile; naming: { valid: boolean; issues: string[] };
      superseded: string | null }>;
  }
  async moveDocument(pid: string, fid: string, path: string) {
    const fd = new FormData(); fd.append("path", path);
    const res = await fetch(this.url(`/projects/${pid}/documents/${fid}/move`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `move failed (${res.status})`);
    return res.json() as Promise<DocFile>;
  }
  deleteDocument(pid: string, fid: string, hard = false) {
    return this.json<{ deleted: string }>(`/projects/${pid}/documents/${fid}${hard ? "?hard=true" : ""}`,
      { method: "DELETE" });
  }
  documentDownloadUrl(pid: string, fid: string) {
    return this.url(`/projects/${pid}/documents/${fid}/download`);
  }
  /** Filename + sheet-ID patterns the naming audit enforces (ISO 19650 container / NCS sheet). */
  namingConventions(pid: string) {
    return this.json<{
      container: { pattern: string; separator: string; fields: string[]; note: string };
      sheet: { pattern: string; note: string };
    }>(`/projects/${pid}/naming/conventions`);
  }
  /** Filed revisions of the authored model (newest first), including superseded ones. */
  modelHistory(pid: string) {
    return this.json<{
      folder: string; count: number; model_present: boolean;
      revisions: { title?: string; revision?: string; cde_state?: string; id?: string }[];
    }>(`/projects/${pid}/documents/model-history`);
  }
  /** File the current source IFC into `12_Model/IFC` as a revision (explicit act, not on every edit). */
  async fileModel(pid: string, title = "Federated Model") {
    const fd = new FormData();
    fd.append("title", title);
    const res = await fetch(this.url(`/projects/${pid}/documents/file-model`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `file model failed (${res.status})`);
    return res.json() as Promise<Record<string, unknown>>;
  }
  };
}
