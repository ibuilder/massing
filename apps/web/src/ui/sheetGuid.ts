/**
 * R38-SHEET-MARKUP ③ ① — a pin on a generated sheet is a GlobalId, not a pixel.
 *
 * The SVG already carries `data-guid` (R38-PLAN-IDENTITY). The Drawings room was dropping
 * coordinate-only pins, so a wall that moved left the markup pointing at empty paper. Hit-twins
 * and highlight live in `viewer/planPane.ts`; this file is the drawing-room seam: read the guid
 * from the event, persist it on the pin, and hand it to the 3D viewer.
 */
import { addHitTargets, syncPlanHighlight } from "../viewer/planPane";

export { addHitTargets, syncPlanHighlight };

/** IFC GlobalId on the clicked linework, or null if the click was empty paper. */
export function guidFromEvent(e: Event): string | null {
  const el = (e.target as Element | null)?.closest?.("[data-guid]");
  const g = el?.getAttribute("data-guid")?.trim();
  return g || null;
}

export function guidFromMarkupData(data: { guid?: unknown } | null | undefined): string | null {
  const g = data?.guid;
  return typeof g === "string" && g.trim() ? g.trim() : null;
}

/** Same `__viewer` hook the Cost/Deal rooms use — drawings must not import `app.ts`. */
export function selectInViewer(guid: string): void {
  const v = (window as unknown as {
    __viewer?: { selectByGuid?: (g: string, fit?: boolean) => void };
  }).__viewer;
  v?.selectByGuid?.(guid, true);
}

export async function postSheetPin(
  api: { url: (p: string) => string; authHeaders: () => Record<string, string> },
  pid: string, sheetId: string, x: number, y: number, note: string, guid: string | null,
): Promise<void> {
  const res = await fetch(api.url(`/projects/${pid}/drawings/markup`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...api.authHeaders() },
    body: JSON.stringify({
      sheet_id: sheetId, x, y, note, kind: "pin",
      ...(guid ? { data: { guid } } : {}),
    }),
  });
  if (!res.ok) throw new Error(`markup ${res.status}`);
}
