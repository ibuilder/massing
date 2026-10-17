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
import type { DetailRefGraph, PreflightSummary } from "./types";

type Ctor<T> = new (...args: any[]) => T;

/** SET-REVISED — one revision of one sheet, as the controlled register reports it. */
export interface DrawingRevision {
  ref: string | null;
  sheet_number: string;
  title?: string | null;
  discipline?: string | null;
  status?: string | null;
  revision: string | null;
  /** Present when this revision came from the sheet's own recorded delta: the date it was made,
   *  what changed, and the instrument (ASI / CCD / Bulletin) that drove it. */
  rev_date?: string | null;
  description?: string | null;
  instrument?: { type?: string | null; ref?: string | null } | null;
  /** `delta` — a recorded revision on this sheet's record; `record` — a whole drawing record,
   *  which is how a drawing-log import carries one revision per row. */
  source: "delta" | "record";
  /** Only on a superseded revision: the revision that replaced it. */
  superseded_by?: string | null;
}

/** SET-REVISED — one sheet in the bound set. */
export interface DrawingSheetIndexRow {
  sheet_number: string;
  title?: string | null;
  discipline: string;
  sheet_id: Record<string, unknown> | null;
  current_revision: string | null;
  /** How many revisions this sheet has had. Counted over DISTINCT revision labels, so it is the
   *  same answer whether the history arrived as deltas on one record or as one record per row. */
  revisions: number;
  /** `new` — one known revision; `revised` — more than one. This is the issuance column on the
   *  transmittal PDF, and it was `new` on every sheet revised through `revise`. */
  change: "new" | "revised";
  /** Whether this sheet's revision ORDER is this register's ranking rather than a recorded fact. */
  order_ambiguous: boolean;
}

/** SET-REVISED — the controlled drawing-set register.
 *
 *  `register` used to classify issuance by counting drawing RECORDS per sheet, while `revise` keeps
 *  one record per sheet and appends to its own `revisions` list — so a sheet revised twice through
 *  this application came back `change: "new", revisions: 1, revised_count: 0, superseded_count: 0`,
 *  and the transmittal PDF told subcontractors it was a new sheet. `current_set` and `superseded`
 *  were both undeclared here, so no screen could show WHICH revisions a sheet had. */
export interface DrawingRegister {
  sheet_count: number;
  current_count: number;
  superseded_count: number;
  new_count: number;
  revised_count: number;
  by_discipline: Record<string, number>;
  sheet_index: DrawingSheetIndexRow[];
  /** The controlled set: the current revision of every sheet. */
  current_set: DrawingRevision[];
  /** Every earlier revision, each naming the revision that superseded it. */
  superseded: DrawingRevision[];
  /** Sheets carrying both lettered and numbered revisions across separate records, where which
   *  kind is later is a set convention rather than something the labels state. */
  order_ambiguous_sheets: string[];
  /** The engine's sentence about whether the revision order is recorded or ranked. */
  order_note: string;
}

export function withDrawingSet<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DrawingSet extends Base {
  /** Controlled drawing-set register (current set, superseded, sheet index, issuance new/revised). */
  drawingSet(pid: string) {
    return this.json<DrawingRegister>(`/projects/${pid}/drawing-set`);
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
  /**
   * DETAIL-REFS-DARK — the section↔detail cross-reference graph of an issued set.
   *
   * `dangling` is a callout pointing at a detail that does not exist: the reader follows it and
   * finds nothing. `orphans` is a detail nothing points at. The engine splits dangling ones BY
   * REASON because the fix differs — an unknown sheet is a typo or an unissued sheet, while a known
   * sheet missing the detail number is almost always a renumber that was not propagated.
   *
   * This is the first client method the route has had. It was frozen in
   * `test_route_reachability.UNREACHABLE_ROUTES`, and it is one of the two verdicts
   * `test_verdict_coverage`'s unowned bucket was counting as "dark" — a count that also held three
   * nested verdicts and one operator surface, so the only number a reader could act on mixed three
   * unrelated facts.
   */
  detailReferences(pid: string) {
    return this.json<DetailRefGraph>(`/projects/${pid}/drawing-set/references`);
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
