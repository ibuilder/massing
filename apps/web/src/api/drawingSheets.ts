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
import { HttpCore, type LiveStream } from "./httpCore";
import type { SheetLayout } from "./types";

type Ctor<T> = new (...args: any[]) => T;

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
    return this.json<{ drawing_id: string; revision: string; delta_count: number }>(
      `/projects/${pid}/drawings/${drawingId}/revise`, { method: "POST", body: JSON.stringify(body) });
  }
  /** W11 C4: computed door / window / room schedules from the model. */
  drawingSchedules(pid: string) {
    return this.json<Record<"doors" | "windows" | "rooms", { columns: string[]; rows: string[][] }>>(
      `/projects/${pid}/drawings/schedules`);
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
               onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/drawings/markup/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }
  };
}
