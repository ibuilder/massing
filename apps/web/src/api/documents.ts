/** Document-control file manager, plus ISO 19650 CDE / BEP / information requirements.
 *
 *  SCALE-SEAM ⑱ took `/projects/{pid}/documents`. SCALE-SEAM ㉛ adds the six methods that answer
 *  *is the information container (CDE) and its requirement flow in order?* — BEP, CDE status,
 *  the requirements register / cascade / delivery plan, and ISO 19650-6 exchange acceptance.
 *  They span `/bep`, `/cde` and `/info-requirements`. `aiReadiness` sat inside that run in
 *  `client.ts` and did **not** come: it is an AI scorecard, not a CDE question.
 *  Composed through the existing `withDocuments` wrapper — no extra `withX()` on `ApiClient`.
 *
 *  SCALE-SEAM ㊾ adds the report catalog — *what can we print from this project?* List plus
 *  the generated PDF/XLSX URL. They sat next to licence in `client.ts` and did **not** go
 *  with licence (that is the deployment plan, not a project document).
 *
 *  SCALE-SEAM ❿ adds closeout analytics — *is turnover actually closing?* Punchlist,
 *  commissioning, warranties, O&M. Safety sat below and did **not** come.
 *
 *  SCALE-SEAM ⓺ adds the issuance gate — *can this package go out?* `preflight`. Hero upload sat beside it and did **not** come.
 */
import { HttpCore } from "./httpCore";
import type { DocFile, DocFolderNode, PreflightGate } from "./types";

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

  /** bep — BIM Execution Plan generated from the project's live config (always current). */
  bep(pid: string) {
    return this.json<{
      project: { id: string; name: string; has_model: boolean } | null;
      sections: { id: string; title: string; configured: boolean; summary: string;
        items: { k: string; v: string }[] }[];
      completeness: { configured: number; total: number; pct: number }; note: string;
    }>(`/projects/${pid}/bep`);
  }
  /** cdeStatus — CDE container counts by state and suitability. */
  cdeStatus(pid: string) {
    return this.json<{ total: number; by_state: Record<string, number>;
      by_suitability: Record<string, number>;
      discipline: { revision_control_pct: number | null; approval_status_pct: number | null;
        metadata_completeness_pct: number | null; published: number; archived: number };
      note: string }>(`/projects/${pid}/cde/status`);
  }
  /** infoRequirementsRegister — OIR/PIR/AIR/EIR coverage of the requirements register. */
  infoRequirementsRegister(pid: string) {
    return this.json<{ total: number;
      by_type: Record<string, { total: number; issued: number; draft: number; superseded: number }>;
      core_coverage: { required: string[]; missing: string[]; complete: boolean }; note: string }>(
      `/projects/${pid}/info-requirements/register`);
  }
  /** ISO 19650 requirement flow-down (OIR→PIR/AIR→EIR→MIDP/TIDP) via each record's derives_from,
   *  with cascade health: orphans that don't trace up + links pointing the wrong way. */
  infoRequirementsCascade(pid: string) {
    type Brief = { id: string; ref: string | null; type: string; title: string | null };
    return this.json<{ total: number; linked: number; coverage_pct: number | null;
      roots: Brief[]; orphans: Brief[];
      misdirected: { id: string; ref: string | null; type: string; parent_type: string }[]; note: string }>(
      `/projects/${pid}/info-requirements/cascade`);
  }
  /** MIDP/TIDP delivery plan — requirements vs programme dates, overdue/due-soon, LOIN coverage. */
  infoRequirementsDeliveryPlan(pid: string) {
    type Item = { id: string; ref: string | null; title: string | null; type: string;
      due_date: string | null; status: string; has_loin: boolean };
    return this.json<{ total: number; overdue: number; due_soon: number; loin_coverage_pct: number | null;
      next_deliverable: Item | null;
      by_month: { month: string; total: number; issued: number; overdue: number }[];
      items: Item[]; note: string }>(
      `/projects/${pid}/info-requirements/delivery-plan`);
  }
  /** ISO 19650-6 exchange acceptance — non-WIP containers vs completeness/suitability/auth/traceability. */
  cdeExchangeAcceptance(pid: string) {
    return this.json<{ reviewed: number; accepted: number; nonconforming_count: number; acceptable: boolean;
      criteria_pct: { completeness: number | null; suitability: number | null; authorization: number | null; traceability: number | null };
      nonconforming: { id: string; ref: string | null; title: string | null; state: string; failed: string[] }[]; note: string }>(
      `/projects/${pid}/cde/exchange-acceptance`);
  }

  /** reports — catalog of available reports (id, name, group). */
  reports() {
    return this.json<{ reports: { id: string; name: string; group: string }[] }>(`/reports`);
  }
  /** reportUrl — generated report download; fmt = pdf | xlsx. */
  reportUrl(pid: string, report: string, fmt: "pdf" | "xlsx") {
    return this.url(`/projects/${pid}/reports/${report}.${fmt}`);
  }

  /** closeoutSummary — punchlist, commissioning, warranties, O&M. */
  closeoutSummary(pid: string) {
    return this.json<{
      punchlist: { punch_count: number; verified_count: number; open_count: number;
        overdue_count: number; complete_pct: number | null; open_cost: number;
        ball_in_court: Record<string, number>; by_trade: Record<string, number>;
        rows: Record<string, unknown>[] };
      commissioning: { cx_count: number; passed: number; failed: number; conditional: number;
        accepted: number; pass_rate: number | null };
      certificates: { cert_count: number; by_type: Record<string, number> };
      warranties: { warranty_count: number; active: number; expired: number; expiring_soon: number };
      om_manuals: { om_count: number; accepted: number; accepted_pct: number | null };
    }>(`/projects/${pid}/closeout/summary`);
  }
  /** The pre-flight issuance gate — PASS/HOLD verdict + checklist, every check deep-linked. */
  preflight(pid: string) {
    return this.json<PreflightGate>(`/projects/${pid}/preflight`);
  }
  };
}
