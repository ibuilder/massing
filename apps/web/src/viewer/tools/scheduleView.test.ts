import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { ScheduleTable } from "./scheduleView";
import { SCHEDULE_ROW_CAP, scheduleHeadHtml, scheduleReading } from "./scheduleView";

/**
 * SCHEDULE-TRUNC — the door schedule printed its row count above a table that showed sixty.
 *
 * `drawingsSection.ts` rendered `${t.rows.length} row(s)` and then `t.rows.slice(0, 60)`, with
 * nothing in between. **The honest total was printed directly above the subset** — TRUNC-COUNTED's
 * class in its purest form: not a number that is wrong, but two numbers one of which was never
 * shown. `/drawings/schedules` returns every row, so the cap was entirely the screen's, and a
 * 240-door project is exactly the one with a procurement problem to find in row 180.
 *
 * The escapes are labelled with what EACH loses, which is the part a reader needs: the drafted SVG
 * table shows every row and clips cell text at 22 characters; only the CSV loses nothing.
 */

const table = (n: number): ScheduleTable => ({
  columns: ["Mark", "Type", "Width", "Height", "Level"],
  rows: Array.from({ length: n }, (_, i) => [`D${i + 1}`, "SC-FL", "900", "2100", "L1"]),
});

describe("scheduleReading — both numbers, or one", () => {
  it("names BOTH numbers when the table is capped", () => {
    const r = scheduleReading("Door schedule", table(240));
    expect(r.capped).toBe(true);
    expect(r.shown).toBe(SCHEDULE_ROW_CAP);
    expect(r.total).toBe(240);
    expect(r.headline).toContain(`${SCHEDULE_ROW_CAP} of 240`);
  });

  it("names ONE number when nothing is hidden — a cap note on a short schedule is noise", () => {
    const r = scheduleReading("Window schedule", table(12));
    expect(r.capped).toBe(false);
    expect(r.note).toBeNull();
    expect(r.headline).toBe("Window schedule — 12 row(s)");
  });

  it("is not capped at exactly the cap — an off-by-one here cries wolf on every full screen", () => {
    expect(scheduleReading("x", table(SCHEDULE_ROW_CAP)).capped).toBe(false);
    expect(scheduleReading("x", table(SCHEDULE_ROW_CAP + 1)).capped).toBe(true);
  });

  it("says how many are missing, and that everything read off the table is about the subset", () => {
    const r = scheduleReading("Door schedule", table(240));
    expect(r.note).toContain(`other ${240 - SCHEDULE_ROW_CAP} row(s)`);
    expect(r.note, "a count or a missing rating read off 60 rows is a claim about 60 rows")
      .toContain("is about the first");
  });

  it("labels each escape with what IT loses, not just where it is", () => {
    // Pointing a reader at an output that silently clips a 40-character type name would be the
    // same defect one click along.
    const n = scheduleReading("Door schedule", table(240)).note!;
    expect(n).toContain("clipped to 22 characters");
    expect(n).toContain("in full");
  });

  it("handles an empty schedule without claiming a cap", () => {
    const r = scheduleReading("Room schedule", table(0));
    expect(r.capped).toBe(false);
    expect(r.shown).toBe(0);
    expect(r.headline).toContain("0 row(s)");
  });
});

describe("scheduleHeadHtml — escaped, and silent when it should be", () => {
  it("renders the note only when capped", () => {
    expect(scheduleHeadHtml("Door schedule", table(240))).toContain("row(s) are in the schedule");
    expect(scheduleHeadHtml("Door schedule", table(5))).not.toContain("are in the schedule");
  });

  it("escapes the label, which is ours today and need not be tomorrow", () => {
    expect(scheduleHeadHtml("<img src=x onerror=alert(1)>", table(5))).not.toContain("<img src=x");
  });
});

/** The pins: the screen uses the reading, and the dark SVG route has a door. */
const here = dirname(fileURLToPath(import.meta.url));
const section = readFileSync(resolve(here, "drawingsSection.ts"), "utf8");
const client = readFileSync(resolve(here, "../../api/drawingSheets.ts"), "utf8");

describe("the schedules screen says what it is showing", () => {
  it("heads each schedule with the reading, not with a bare row count", () => {
    expect(section).toMatch(/scheduleHeadHtml\(label, t\)/);
    expect(section, "the bare count above a sliced table is the defect")
      .not.toMatch(/\$\{t\.rows\.length\} row\(s\)/);
  });

  it("slices by the SAME constant the reading counts with", () => {
    // Two literals drift: the heading would say "60 of 240" while the table showed a different
    // number, and nothing would be wrong enough to notice.
    expect(section).toContain("t.rows.slice(0, SCHEDULE_ROW_CAP)");
    expect(section).not.toContain("t.rows.slice(0, 60)");
  });

  it("is reached LAZILY — `viewer/tools/*` is the eager chunk and a click cannot be eager", () => {
    // Added when CLASSIFY-DARK spent the headroom this file's roadmap entry had recorded. Pinned
    // rather than left as a convention: a static import is one autocompletion away, costs nothing
    // locally, and only shows up as a budget failure in somebody else's change.
    expect(section).toContain('await import("./scheduleView")');
    expect(section, "a static import of this module puts it back in the first load")
      .not.toMatch(/^import \{[^}]*\} from "\.\/scheduleView";$/m);
  });

  it("tones a capped schedule as a warning", () => {
    expect(section).toMatch(/r\.capped \? "warn" : ""/);
  });

  it("offers both escapes, only when capped", () => {
    expect(section).toMatch(/if \(r\.capped\) \{/);
    expect(section).toMatch(/api\.drawingScheduleSvgUrl\(d\.pid, kind\)/);
    expect(section).toMatch(/api\.drawingSchedulesCsvUrl\(d\.pid, kind\)/);
  });

  it("declares the SVG url method the button's own tooltip has always named", () => {
    expect(client).toMatch(/drawingScheduleSvgUrl\(pid: string/);
    expect(client).toContain("/drawings/schedule.svg");
    expect(client, "the kind must reach the route or it always renders doors")
      .toContain("kind=${encodeURIComponent(kind)}");
  });
});
