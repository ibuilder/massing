/** 2D sheets: storeys, schedules, revision deltas, markup pins, sync status.
 *
 *  SCALE-SEAM ⑮. Route-group `/projects/{pid}/drawings`, taken out of `client.ts` by the route
 *  each method calls. Eleven methods in **six** regions — schedules next to LOD, storeys under
 *  a `// 2D documentation` banner that then continues into propmap, markup next to notifications.
 *  `markupStream` uses `liveStream` on `HttpCore` (protected since SCALE-SEAM ③).
 *
 *  Named `drawingSheets.ts` so it does not collide with `apps/web/src/drawings/drawings.ts`.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore, HttpError, type LiveStatus, type LiveStream } from "./httpCore";
import type { SheetLayout } from "./types";

type Ctor<T> = new (...args: any[]) => T;

/** REVISE-DARK — what recording a sheet revision reports back.
 *
 *  Slip-sheeting tags every existing markup on that sheet `carried_from` so a reviewer re-checks it
 *  against the revised sheet. The tagging is deliberately wrapped so it can never block a revision,
 *  which means it can FAIL while the revision lands — so the three markup fields are a verdict plus
 *  its coverage, not one number. Named rather than inline so the fields are visible to the audits
 *  built on these declarations (DEADFIELD-INLINE). */
export interface RevisionResult {
  drawing_id: string;
  revision: string;
  /** Every delta on this sheet, including the one just recorded. */
  delta_count: number;
  /** Markups whose carried-forward tag was COMMITTED. Zero when the tagging failed. */
  markups_carried: number;
  /** Markups the tagging attempted. Equals `markups_carried` on success. */
  markups_to_carry: number;
  /** The exception TYPE when the tagging did not land, `null` when it did. The revision is
   *  recorded either way: a reviewer seeing untagged markups on a revised sheet has no way to
   *  know they are stale unless this is rendered. */
  markups_carry_failed: string | null;
}


export function withDrawingSheets<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DrawingSheets extends Base {
  /** The sheet layout `takeoff2d` scopes against — viewport rectangles plus the page↔world affine
   *  each was drawn with. This is the producer half of R27-LAYOUT: the route existed and had no
   *  client, so the `layout` the takeoff accepts was something no caller could obtain. */
  sheetRegions(pid: string, preset = "key", page = "A1") {
    return this.json<SheetLayout & { preset: string; page: string }>(
      `/projects/${pid}/drawings/sheet-regions?preset=${encodeURIComponent(preset)}`
      + `&page=${encodeURIComponent(page)}`);
  }

  /** Record a revision (delta) on a sheet, optionally citing the driving instrument (ASI/CCD/Addendum). */
  reviseDrawing(pid: string, drawingId: string, body: { rev: string; description?: string; date?: string; instrument_type?: string; instrument_ref?: string }) {
    return this.json<RevisionResult>(
      `/projects/${pid}/drawings/${drawingId}/revise`, { method: "POST", body: JSON.stringify(body) });
  }
  /** W11 C4: computed door / window / room schedules from the model. */
  drawingSchedules(pid: string) {
    return this.json<Record<"doors" | "windows" | "rooms", { columns: string[]; rows: string[][] }>>(
      `/projects/${pid}/drawings/schedules`);
  }
  /**
   * One schedule (doors|windows|rooms) as a drafted SVG table — **every row**, with long cell
   * values clipped to 22 characters by the renderer.
   *
   * SCHEDULE-TRUNC. The Schedules button's own tooltip has always said *"Also at GET
   * /drawings/schedule.svg"* and nothing reached it, while the on-screen table showed the first 60
   * rows under a heading that printed the real count. This is the escape for *reading* a long
   * schedule; `drawingSchedulesCsvUrl` is the one that loses nothing at all. Both limits are stated
   * on screen, because pointing a reader at an output that silently clips a 40-character type name
   * would be the same defect one click along.
   */
  drawingScheduleSvgUrl(pid: string, kind: "doors" | "windows" | "rooms") {
    return this.url(`/projects/${pid}/drawings/schedule.svg?kind=${encodeURIComponent(kind)}`);
  }
  /** Door / window / room schedules as a CSV download (`kind` omits for all three). */
  drawingSchedulesCsvUrl(pid: string, kind?: "doors" | "windows" | "rooms") {
    const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
    return this.url(`/projects/${pid}/drawings/schedule.csv${q}`);
  }
  drawingSchedulesCalc(pid: string, calcs: { doors?: { name: string; expr: string }[];
    windows?: { name: string; expr: string }[]; rooms?: { name: string; expr: string }[] }) {
    type Table = { columns: string[]; rows: (string | number | null)[][]; calculated?: string[] };
    return this.json<{ doors: Table; windows: Table; rooms: Table }>(
      `/projects/${pid}/drawings/schedules/calc`, { method: "POST", body: JSON.stringify(calcs) });
  }
  /**
   * Move pre-v0.3.1106 storey markups from `plan:<storeyName>` onto `plan:<storeyGuid>`.
   *
   * `dryRun` defaults to TRUE, matching the route: the mapping depends on a model that may have been
   * re-uploaded since the markups were made, so a caller sees exactly what would move before anything
   * does. `ambiguous_names` and `unmatched_names` are what it REFUSED to guess — a duplicated storey
   * name does not identify one GlobalId, and picking either would be the same guess, in the other
   * direction, that GUID-keying exists to stop. `already_keyed_by_guid` is the desired end state, so
   * it is reported apart from the unmappable rather than lumped in with them.
   */
  rekeyStoreyMarkups(pid: string, dryRun = true) {
    return this.json<{
      dry_run: boolean; moved: number; changes_truncated: boolean; changes_shown: number;
      changes: { markup_id: string; from: string; to: string }[];
      ambiguous_names: string[]; unmatched_names: string[]; already_keyed_by_guid: string[];
      note: string; storeys_in_model: number;
    }>(`/projects/${pid}/drawings/markups/rekey-storeys?dry_run=${dryRun}`, { method: "POST" });
  }
  drawingStoreys(pid: string) {
    return this.json<{ name: string | null; elevation: number; guid: string }[]>(`/projects/${pid}/drawings/storeys`);
  }
  /** Model version/signature for 2D staleness (bumps on publish; /drawings/stream pushes it). */
  drawingsSyncStatus(pid: string) {
    return this.json<{ model_loaded: boolean; version: number; signature: string | null;
      changed_at: number | null }>(`/projects/${pid}/drawings/sync-status`);
  }
  // The five drawing-markup methods (drawingMarkup / addDrawingMarkup / saveDrawingMarkups /
  // deleteDrawingMarkup / promoteDrawingMarkup) are NOT here: `api/markup.ts` owns them as
  // SCALE-SEAM ⑭, which landed on main first. Both extractions took them, and because this
  // mixin wraps the outer position its copy SHADOWED markup.ts's — silently dropping the
  // `guid` argument that R38-SHEET-MARKUP ③ added, so a pin would have gone back to being a
  // coordinate on paper. `ui/sheetGuid.test.ts` caught it by asserting the encoded body.
  // Two seams may not both claim a route group; the one that landed first keeps it.
  /** MARKUP-2d — SSE stream of the drawing-markup change-signature; fires whenever anyone saves a
   *  markup so open sheets live-refresh (live co-markup). */
  markupStream(pid: string, onMessage: (d: { count: number; latest: string | null }) => void,
               onStatus?: (s: LiveStatus, why?: string) => void): LiveStream {
    return this.liveStream(`/projects/${pid}/drawings/markup/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }

  // SCALE-SEAM ⓽ — *what sheets are in this PDF, and make the records?* Filed here rather
  // than with the AI drafting it sat next to: with `create: true` it creates DRAWING records.
  /** Extract a drawing-sheet index (number/title/discipline) from a PDF or pasted list; optionally create drawing records. */
  async extractSheets(pid: string, opts: { file?: File; text?: string; create?: boolean }) {
    const fd = new FormData();
    if (opts.file) fd.append("file", opts.file);
    if (opts.text) fd.append("text", opts.text);
    fd.append("create", opts.create ? "true" : "false");
    const res = await fetch(this.url(`/projects/${pid}/extract/sheets`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new HttpError(`Extract sheets -> ${res.status}`, res.status);
    return res.json() as Promise<{ sheets: { number: string; title: string; discipline: string }[];
      method: string; has_text_layer?: boolean; note?: string; created?: string[] }>;
  }
  };
}
