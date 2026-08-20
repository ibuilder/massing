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
import type { DrawingMarkupItem, SheetMarkupIn } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withDrawingSheets<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DrawingSheets extends Base {
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
  drawingStoreys(pid: string) {
    return this.json<{ name: string | null; elevation: number; guid: string }[]>(`/projects/${pid}/drawings/storeys`);
  }
  /** Model version/signature for 2D staleness (bumps on publish; /drawings/stream pushes it). */
  drawingsSyncStatus(pid: string) {
    return this.json<{ model_loaded: boolean; version: number; signature: string | null;
      changed_at: number | null }>(`/projects/${pid}/drawings/sync-status`);
  }
  /** Markups for one sheet — or, with no sheet, EVERY markup in the project (the MARKUP-2b grid). */
  drawingMarkup(pid: string, sheet?: string) {
    return this.json<DrawingMarkupItem[]>(
      `/projects/${pid}/drawings/markup${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`);
  }
  addDrawingMarkup(pid: string, sheetId: string, x: number, y: number, note: string) {
    return this.json<DrawingMarkupItem>(`/projects/${pid}/drawings/markup`, { method: "POST", body: JSON.stringify({ sheet_id: sheetId, x, y, note }) });
  }
  /** Persist the 2D editor's whole markup scene for a sheet (structured takeoff markups, promotable to
   *  RFI like pins). `replace` clears the caller's own prior unpromoted markups for that sheet first. */
  saveDrawingMarkups(pid: string, sheetId: string, markups: SheetMarkupIn[], replace = true) {
    return this.json<{ saved: number; sheet_id: string }>(`/projects/${pid}/drawings/markup/bulk`,
      { method: "POST", body: JSON.stringify({ sheet_id: sheetId, replace, markups }) });
  }
  deleteDrawingMarkup(pid: string, id: string) {
    return this.json<{ ok: boolean }>(`/projects/${pid}/drawings/markup/${id}`, { method: "DELETE" });
  }
  promoteDrawingMarkup(pid: string, id: string) {
    return this.json<{ markup: DrawingMarkupItem; topic: { id: string; type: string; title: string; status: string } }>(
      `/projects/${pid}/drawings/markup/${id}/promote`, { method: "POST" });
  }
  /** MARKUP-2d — SSE stream of the drawing-markup change-signature; fires whenever anyone saves a
   *  markup so open sheets live-refresh (live co-markup). */
  markupStream(pid: string, onMessage: (d: { count: number; latest: string | null }) => void,
               onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/drawings/markup/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }
  };
}
