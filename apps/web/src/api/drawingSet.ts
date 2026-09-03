/** Controlled drawing-set register, issuance, and transmittals.
 *
 *  SCALE-SEAM ⑭. Route-group `/projects/{pid}/drawing-set`, taken out of `client.ts` by the
 *  route each method calls. They sat in **three** runs: generate/issue, issuance history, then
 *  revisions/transmittal — with `/preflight`, `/site-context`, `/hero`, `/pdf`, `/stamps` and
 *  `reviseDrawing` (`/drawings/…/revise`) in between. Grouping by the nearby comments would have
 *  dragged those across the seam.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { PreflightSummary } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withDrawingSet<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DrawingSet extends Base {
  /** Controlled drawing-set register (current set, superseded, sheet index, issuance new/revised). */
  drawingSet(pid: string) {
    return this.json<{ sheet_count: number; current_count: number; superseded_count: number;
      new_count: number; revised_count: number; by_discipline: Record<string, number>;
      sheet_index: Record<string, unknown>[] }>(`/projects/${pid}/drawing-set`);
  }
  /** Preview the discipline sheet set that would be generated (one NCS series per discipline: M-/FA-/S-/…). */
  drawingSetPlan(pid: string, opts: { disciplines?: string; all?: boolean } = {}) {
    const q = new URLSearchParams({ ...(opts.disciplines ? { disciplines: opts.disciplines } : {}),
      ...(opts.all ? { all: "true" } : {}) }).toString();
    return this.json<{ levels: number; series: string[]; sheet_count: number;
      by_discipline: Record<string, number>; sheets: Record<string, unknown>[] }>(
      `/projects/${pid}/drawing-set/plan${q ? "?" + q : ""}`);
  }
  /** Generate the discipline sheet set as drawing records (per-discipline NCS numbering, plan per level). */
  generateDrawingSet(pid: string, body: { disciplines?: string[]; all?: boolean; max_levels?: number } = {}) {
    return this.json<{ levels: number; series: string[]; planned: number; created: number;
      skipped_existing: number; by_discipline: Record<string, number>; sheet_count: number }>(
      `/projects/${pid}/drawing-set/generate`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Issue the current drawing set for a purpose (AIA/CD) — snapshots every sheet + its revision.
   *  The pre-flight gate runs server-side and its verdict is stamped on the issuance; `enforce: true`
   *  makes a HOLD verdict block the issue (409). */
  issueDrawingSet(pid: string, body: { purpose: string; date?: string; description?: string;
      recipients?: string; enforce?: boolean }) {
    return this.json<{ id: string; purpose: string; issue_date: string; sheet_count: number;
      preflight?: PreflightSummary | null }>(
      `/projects/${pid}/drawing-set/issue`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The issuance history (every release, purpose, date, sheet count, recipients). */
  drawingIssuances(pid: string) {
    return this.json<{ issuance_count: number; by_purpose: Record<string, number>;
      issuances: Record<string, unknown>[] }>(`/projects/${pid}/drawing-set/issuances`);
  }
  /** The sheet-index × issuance matrix (each sheet's revision in each issuance). */
  drawingIssuanceMatrix(pid: string) {
    return this.json<{ issuances: Record<string, unknown>[]; sheet_count: number;
      rows: { sheet_number: string; title: string; discipline: string; cells: (string | null)[] }[] }>(
      `/projects/${pid}/drawing-set/issuance-matrix`);
  }
  /** AIA/CD issuance purposes for the "issue for…" picker. */
  drawingIssuancePurposes(pid: string) {
    return this.json<{ purposes: { name: string; abbr: string }[] }>(
      `/projects/${pid}/drawing-set/issuance-purposes`);
  }
  /** URL of a per-issuance transmittal PDF (stamped with the purpose + date). */
  issuanceTransmittalUrl(pid: string, iid: string) {
    return this.url(`/projects/${pid}/drawing-set/issuances/${iid}/transmittal.pdf`);
  }
  /** URL of the digitally-sealed (PAdES) issuance transmittal, for permit/IFC submittal. */
  issuanceSealedUrl(pid: string, iid: string, name = "") {
    const q = name ? "?name=" + encodeURIComponent(name) : "";
    return this.url(`/projects/${pid}/drawing-set/issuances/${iid}/sealed.pdf${q}`);
  }
  /** The cross-sheet revision register — every delta on every sheet (newest first) + instrument rollup. */
  drawingRevisions(pid: string) {
    return this.json<{ delta_count: number; by_instrument: Record<string, number>;
      revisions: { sheet_number: string; discipline: string; rev: string; date: string; description: string; instrument: { type: string; ref: string } | null }[] }>(
      `/projects/${pid}/drawing-set/revisions`);
  }
  /** URL of a drawing-transmittal PDF for the current set (recipients comma-separated). */
  drawingTransmittalUrl(pid: string, to = "", note = "") {
    const q = new URLSearchParams({ ...(to ? { to } : {}), ...(note ? { note } : {}) }).toString();
    return this.url(`/projects/${pid}/drawing-set/transmittal.pdf${q ? "?" + q : ""}`);
  }
  /** Whole drawing set as one multi-page PDF (cover, plans, schedules). */
  compiledPdfUrl(pid: string, maxSheets = 16) {
    return this.url(`/projects/${pid}/drawing-set/compiled.pdf?max_sheets=${maxSheets}`);
  }
  /** Shareable project package PDF (cover, views, drawing set, cost summary). */
  projectPackagePdfUrl(pid: string, maxSheets = 8) {
    return this.url(`/projects/${pid}/project-package.pdf?max_sheets=${maxSheets}`);
  }
  };
}
