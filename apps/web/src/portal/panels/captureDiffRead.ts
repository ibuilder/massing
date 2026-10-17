/**
 * CAPTURE-SESSION — the capture diff, and the half of it a derived capture cannot answer.
 *
 * `POST /projects/{pid}/progress/capture-diff` answers what a superintendent asks weekly: between
 * two site captures, what went in, per class and per level, and at what daily rate. It had no caller
 * because the roadmap recorded that *nothing in this product persists a capture*, so a screen would
 * have to invent the concept.
 *
 * **That was half right, and the other half is why this file exists.** It is true of a stored
 * capture ROW. It is not true of the SET: every `field_verification` record carries a REQUIRED
 * `guid` and an `observed_date`, so *"what was observed installed as of 2026-09-30"* is a filter.
 * *"There is no stored X" and "X is not available" are different claims.*
 *
 * ## What the derivation costs, which the screen must say out loud
 *
 * A derived capture is **cumulative** — `observed_date <= as_of` — and that choice was forced. A
 * point-in-time reading (`== as_of`) would report every element not re-verified on the later date
 * as *disappeared*, manufacturing rework flags out of a crew's ordinary habit of not re-walking
 * finished work. So the set can only grow, `disappeared` is empty **by construction**, and the
 * rework half is unanswerable from this source. *Choosing which half to make unreachable is better
 * than leaving a half that lies* — and the consumer has to SUPPRESS it rather than render an empty
 * table, because an empty rework table reads as "no rework found", which is the opposite of "this
 * source cannot tell you".
 *
 * ## Three coverage facts, all measured
 *
 * Against the engine with 6 design elements, 6 verifications (one undated, one naming a GUID the
 * model does not know) and captures at 2026-09-15 / 2026-09-30:
 *
 * | | value | what it is over |
 * |---|---|---|
 * | `installed_t1` / `installed_t2` | 3 / 5 | elements the MODEL knows, of those the register dated |
 * | `pct_complete_t2` | 0.833 | 5 of the 6 DESIGN elements |
 * | `unmatched_t2` | 1 | a verification whose GUID this model has never had |
 * | `derived.undated` | 1 | a verification no date could place, invisible at every `as_of` |
 *
 * So `pct_complete` is over the design set while the installed side is bounded by what the register
 * dated: a crew that verified forty elements of five thousand produces a true 0.8%, and a reader
 * who takes it for progress is reading the register's coverage as the building's.
 *
 * Pure, returning plain text.
 */
import type { Tone } from "./flowlineRead";
import type { CaptureDiff } from "../../api/schedule";

/** The SAME four names `flowlineRead` uses, imported rather than re-spelled.
 *
 *  A second `Tone` with `"ok"`/`"bad"` in place of `"good"`/`"crit"` typechecked fine in this file
 *  and failed at the panel that renders both, because `TONE_CSS` is keyed by the other spelling.
 *  *A parallel vocabulary for one concept is a re-spelled shape in miniature* —
 *  `apps/web/src/api/noRespelledShapes.test.ts` refuses the type-level version of exactly this. */
export type { Tone } from "./flowlineRead";

/** Is the rework half answerable at all from this response's source?
 *
 *  `false` for a derived capture, where the set is cumulative by construction. Separate from
 *  "`disappeared` happens to be 0", because those are different facts and only one of them is
 *  worth rendering a table for. */
export function reworkAnswerable(r: CaptureDiff): boolean {
  return !r.derived?.cumulative;
}

/** The headline: what went in, over how long, and at what rate. */
export function captureHeadline(r: CaptureDiff): string {
  if (r.days == null) {
    return `${r.newly_installed} element(s) newly installed (no dates given, so no rate)`;
  }
  const rate = r.elements_per_day == null ? "" : ` · ${r.elements_per_day}/day`;
  return `${r.newly_installed} element(s) newly installed over ${r.days} day(s)${rate}`;
}

/** Green only when something went in and nothing is unexplained.
 *
 *  A capture pair with no movement is NOT a failure — a quiet fortnight is a real result — so it is
 *  neutral rather than bad. What earns a warning is an unmatched GUID, because that means a capture
 *  was taken against a model version this project no longer has. */
export function captureTone(r: CaptureDiff): Tone {
  if (r.unmatched_t1 + r.unmatched_t2 > 0) return "warn";
  if (r.disappeared > 0) return "crit";
  return r.newly_installed > 0 ? "good" : "";
}

/** The progress delta, said as what it is over rather than as a bare percentage. */
export function progressNote(r: CaptureDiff): string {
  const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
  return `Percent complete ${pct(r.pct_complete_t1)} → ${pct(r.pct_complete_t2)} `
    + `(${r.pct_delta >= 0 ? "+" : ""}${pct(r.pct_delta)}), counted over the whole design element `
    + `set. The installed side is only what a capture could account for.`;
}

/** Where the two sets came from, and what the derivation cannot tell you. Null when the caller
 *  supplied the sets itself, in which case their provenance is the caller's to state. */
export function derivationNote(r: CaptureDiff): string | null {
  const d = r.derived;
  if (!d) return null;
  const bits = [`Both sets are DERIVED from Field Verification: `
    + `${d.t1.count} element(s) observed on or before ${d.t1.as_of ?? "—"}, `
    + `${d.t2.count} on or before ${d.t2.as_of ?? "—"}.`];
  if (d.cumulative) {
    bits.push("A cumulative set can only grow, so this call CANNOT raise a rework flag — an element "
      + "observed once and never re-observed still counts as installed.");
  }
  return bits.join(" ");
}

/** The verifications no capture can ever use, or null when every row carried a date. */
export function undatedNote(r: CaptureDiff): string | null {
  const n = r.derived?.undated ?? 0;
  if (!n) return null;
  return `${n} Field Verification record(s) carry no observed date. They are outside EVERY capture `
    + `at every date, so dating them is the only way they count.`;
}

/** Whether a chosen date falls outside the register's own dated range.
 *
 *  An `as_of` before the first observation returns an empty set, which is a correct answer and an
 *  alarming-looking one — a reader seeing `0 installed` otherwise concludes nothing has been built. */
export function dateRangeNote(r: CaptureDiff): string | null {
  const d = r.derived;
  if (!d || !d.register_earliest) {
    return d ? "The Field Verification register holds no dated records, so both sets are empty." : null;
  }
  const before = [d.t1, d.t2]
    .filter((x) => x.as_of && x.as_of < d.register_earliest!)
    .map((x) => x.as_of!);
  if (!before.length) return null;
  return `${before.join(" and ")} ${before.length > 1 ? "are" : "is"} before the register's first `
    + `observation (${d.register_earliest}), so that side is empty for want of records rather than `
    + `for want of progress.`;
}

/** Capture GUIDs the model does not know — a capture aimed at the wrong model version. */
export function unmatchedNote(r: CaptureDiff): string | null {
  const n = r.unmatched_t1 + r.unmatched_t2;
  if (!n) return null;
  const sample = r.unmatched_guids.slice(0, 5);
  const more = r.unmatched_guids.length > sample.length || n > r.unmatched_guids.length;
  return `${n} captured GlobalId(s) are not in this model (${sample.join(", ")}${more ? " …" : ""}). `
    + `They are outside the diff on both sides — a capture taken against a different model version, `
    + `or an element since removed from the model.`;
}

/** What went in, by IFC class. */
export function addedByClassRows(r: CaptureDiff, cap = 20): { k: string; v: string }[] {
  return r.added_by_class.slice(0, cap).map((c) => ({
    k: c.ifc_class.replace(/^Ifc/, ""), v: `${c.count}`,
  }));
}

/** What went in, by level. */
export function addedByLevelRows(r: CaptureDiff, cap = 20): { k: string; v: string }[] {
  return r.added_by_level.slice(0, cap).map((l) => ({ k: l.storey, v: `${l.count}` }));
}

/** The rework rows — EMPTY ARRAY and a null note are different answers, so callers use
 *  `reworkAnswerable` to decide whether to draw the section at all. */
export function reworkRows(r: CaptureDiff, cap = 20): { k: string; v: string }[] {
  return r.disappeared_guids.slice(0, cap).map((g) => ({ k: g, v: "present at t1, absent at t2" }));
}
