import { escapeHtml as esc } from "../../ui/feedback";

/**
 * SCHEDULE-TRUNC — the door schedule printed its row count above a table that showed sixty.
 *
 * `drawingsSection.ts` rendered the computed door / window / room schedules as
 *
 *     resultNote(`<b>Door schedule</b> — ${t.rows.length} row(s)`)   //  240 row(s)
 *     for (const row of t.rows.slice(0, 60))                          //  …and 60 of them
 *
 * with nothing between the two. **The honest total was printed directly above the subset**, which is
 * TRUNC-COUNTED's class in its purest form: not a number that is wrong, but two numbers one of which
 * is never shown. `/drawings/schedules` returns every row, so the cap is entirely the screen's, and a
 * 240-door project is exactly the kind that has a procurement problem to find in row 180.
 *
 * ## Three outputs, three different losses — and that is what a reader needs told
 *
 * The honest escape is not "download the CSV", it is which one loses what:
 *
 * | output | rows | cell text |
 * |---|---|---|
 * | this table | the first 60 | complete |
 * | `/drawings/schedule.svg` (the drafted table) | **every row** | clipped to 22 characters by `cell()` |
 * | `/drawings/schedule.csv` | every row | complete |
 *
 * The SVG route was dark — named in the Schedules button's own tooltip (*"Also at GET
 * /drawings/schedule.svg"*) and reachable from nothing — and it is the right escape for *reading* a
 * long schedule on screen. It is offered with its limit stated, because pointing a reader at an
 * output that silently clips a 40-character type name would be the same defect one click along.
 */

export interface ScheduleTable {
  columns: string[];
  rows: string[][];
}

/** The screen's own cap. Sixty rows is about a screenful; the number is not the point, saying so is. */
export const SCHEDULE_ROW_CAP = 60;

export interface ScheduleReading {
  shown: number;
  total: number;
  capped: boolean;
  /** The heading: both numbers when capped, one when not. */
  headline: string;
  /** What is missing and where to get it — `null` when nothing is missing. */
  note: string | null;
}

export function scheduleReading(label: string, t: ScheduleTable,
                                cap = SCHEDULE_ROW_CAP): ScheduleReading {
  const total = t.rows.length;
  const shown = Math.min(total, cap);
  const capped = total > cap;
  return {
    shown, total, capped,
    headline: capped
      ? `${label} — showing ${shown} of ${total} row(s)`
      : `${label} — ${total} row(s)`,
    note: capped
      ? `The other ${total - shown} row(s) are in the schedule and not in this table, so anything `
        + `read off it — a count, a type, a missing rating — is about the first ${shown}. The `
        + `drafted table shows every row with long cell values clipped to 22 characters; the CSV `
        + `shows every row in full.`
      : null,
  };
}

/** One schedule's heading and, when it matters, what the table leaves out. */
export function scheduleHeadHtml(label: string, t: ScheduleTable,
                                 cap = SCHEDULE_ROW_CAP): string {
  const r = scheduleReading(label, t, cap);
  return `<b>${esc(r.headline)}</b>`
    + (r.note ? `<br><span style="opacity:.8">${esc(r.note)}</span>` : "");
}
