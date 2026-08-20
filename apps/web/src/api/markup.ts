/** Drawing markup — 2D sheet pins and takeoff markups, promotable to RFIs.
 *
 *  SCALE-SEAM ⑭. Route-group `/projects/{pid}/drawings/markup…`, taken out of `client.ts` by the
 *  route each method calls — the same rule ⑫ and ⑬ used. The other `drawing*` methods stay put:
 *  they answer `/drawings/set`, `/drawings/issuances`, `/drawings/schedules` and so on, which are
 *  different route groups that will want their own cuts.
 *
 *  This cut was forced rather than chosen. Teaching `addDrawingMarkup` to carry the IFC GlobalId
 *  (R38-SHEET-MARKUP ③) added four lines and `client.ts` went 3,602 → 3,606, one line over the
 *  extraction ratchet in `services/api/test_file_sizes.py`. That is the ratchet working exactly as
 *  its own comment says it should: the friction buys a cluster out of the file instead of buying
 *  the pin a higher number. 3,606 → 3,579.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { DrawingMarkupItem, SheetMarkupIn } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withMarkup<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Markup extends Base {
  /** Markups for one sheet — or, with no sheet, EVERY markup in the project (the MARKUP-2b grid). */
  drawingMarkup(pid: string, sheet?: string) {
    return this.json<DrawingMarkupItem[]>(
      `/projects/${pid}/drawings/markup${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`);
  }
  /** Drop a pin on a sheet. `guid` is the IFC GlobalId of the linework under the click (R38-SHEET-
   *  MARKUP ③) — omitted entirely when the click hit empty paper, so `data` is absent rather than a
   *  null the server would have to interpret. A coordinate-only pin points at empty paper once the
   *  element moves, which is why the guid rides on the pin and not beside it. */
  addDrawingMarkup(pid: string, sheetId: string, x: number, y: number, note: string, guid?: string | null) {
    return this.json<DrawingMarkupItem>(`/projects/${pid}/drawings/markup`, { method: "POST", body: JSON.stringify({ sheet_id: sheetId, x, y, note, kind: "pin", ...(guid ? { data: { guid } } : {}) }) });
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
  };
}
