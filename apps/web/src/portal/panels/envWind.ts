/** ENV-WIND — the wording for the pedestrian wind-comfort screen at massing stage.
 *
 *  Pure, so the rules can be tested without a DOM.
 *
 *  `POST …/env/wind` has graded corner acceleration, downwash and channelling on the Lawson comfort
 *  categories since ENV-1, offline and deterministic, deriving the mass from the model's bounding box
 *  when no dimensions are given. **Nothing called it.** A massing-stage wind answer that only a
 *  `curl` can reach is not an answer the design has.
 *
 *  Three things about this screen will be misread if the panel does not say them, and each has its
 *  own function below because each is a different lie:
 *
 *  1. **A check that did not run is not a check that passed.** Channelling is raised only when a gap
 *     to a neighbouring mass is supplied. Leave the gap blank and `acceptable_for_entrances` can come
 *     back `true` having never looked at the passage — which is where pedestrian wind complaints
 *     actually come from. `unassessed()` names what was skipped, and `verdict()` refuses the word
 *     "acceptable" while anything is on that list.
 *  2. **Every speed here is the site wind times a factor.** `wind_ms` scales the whole result
 *     linearly, and it defaults. A screen run on the default and read as a site answer is wrong by
 *     exactly the ratio of the two. `windBasis()` says which one produced the numbers.
 *  3. **A bounding box is not a building.** With no dimensions the server takes the model's world
 *     bounds, which span site and context geometry too. `dimensionBasis()` prints what was actually
 *     screened so a 400 m "width" is visible rather than silently believed.
 *
 *  And under all three: this is a screening heuristic, not CFD and not a wind tunnel. The server says
 *  so in `disclaimer`; the panel shows it rather than filing it.
 */

import type { WindResult, WindZone } from "../../api/designPerformance";

/** What the form holds. Every field optional — the server derives the mass when the dims are blank. */
export interface WindForm {
  height_m?: number | null;
  width_m?: number | null;
  depth_m?: number | null;
  wind_ms?: number | null;
  gap_m?: number | null;
  podium_height_m?: number | null;
}

/**
 * Whether the screen can run at all, and why not when it cannot.
 *
 * The server needs a full set of dimensions OR a source model to derive the missing ones from, and
 * answers 409 otherwise. Saying that here beats letting a 409 surface as "request failed".
 */
export function screenGate(form: WindForm, hasModel: boolean): { can: boolean; why: string } {
  const complete = [form.height_m, form.width_m, form.depth_m]
    .every((v) => typeof v === "number" && Number.isFinite(v) && v > 0);
  if (complete || hasModel) return { can: true, why: "" };
  return { can: false,
           why: "give a height, width and depth — or load a source model and they will be derived "
                + "from its bounding box" };
}

/**
 * The checks this screen did NOT run. **The load-bearing function of this file.**
 *
 * Read off the RESPONSE, never re-derived from the inputs: the server decides when a mechanism
 * applies, and a second copy of that rule here would be measuring the copy. A `passage (…)` zone in
 * the answer means channelling was looked at; no passage zone and no gap supplied means it was not.
 *
 * Downwash is deliberately absent from this list. Below about 25 m it does not apply — that is a
 * mechanism ruled out, which is a finding, not a hole.
 */
export function unassessed(r: WindResult): string[] {
  const gaps: string[] = [];
  const hasPassage = r.zones.some((z) => z.zone.startsWith("passage"));
  if (!hasPassage && (r.inputs.gap_m == null || r.inputs.gap_m <= 0)) {
    gaps.push("Channelling between buildings was NOT checked — no gap to a neighbouring mass was "
              + "given. A narrow passage is the commonest source of a pedestrian wind complaint, and "
              + "it is not in the figure above.");
  }
  return gaps;
}

/**
 * The headline.
 *
 * While anything is on the `unassessed` list the word "acceptable" is withheld, whatever
 * `acceptable_for_entrances` says: a partial screen that reads as a pass is how a scheme goes to
 * planning on a check nobody ran. `S` is the 15 m/s SAFETY criterion, not a comfort grade, and is
 * called out as such.
 */
export function verdict(r: WindResult): string {
  const w = r.worst;
  const gaps = unassessed(r);
  if (w.lawson === "S") {
    return `UNSAFE — ${w.zone} screens at ${w.speed_ms} m/s, past the 15 m/s safety criterion. `
      + "This is a safety threshold, not a comfort grade; a wind consultant is not optional here.";
  }
  if (!r.acceptable_for_entrances) {
    return `NOT acceptable for entrances or seating — ${w.zone} screens at ${w.speed_ms} m/s `
      + `(Lawson ${w.lawson}). Lawson A–C is the range an entrance wants.`;
  }
  if (gaps.length) {
    return `No comfort problem in the checks that RAN — worst was ${w.zone} at ${w.speed_ms} m/s `
      + `(Lawson ${w.lawson}). This is a PARTIAL screen: ${gaps.length} mechanism was not checked, `
      + "so it is not a pass.";
  }
  return `Acceptable for entrances on this screen — worst zone ${w.zone} at ${w.speed_ms} m/s `
    + `(Lawson ${w.lawson}).`;
}

/**
 * Where the dimensions came from.
 *
 * `supplied` is what the form sent. When it sent nothing the server took the model's world bounds,
 * and a bounding box spans every piece of geometry in the file — site, context, a survey point left
 * at the origin. Printing what was screened is what makes a 400 m "width" visible.
 */
export function dimensionBasis(r: WindResult, supplied: WindForm): string {
  const dims = `${fmt(r.inputs.height_m)} m tall × ${fmt(r.inputs.width_m)} m × ${fmt(r.inputs.depth_m)} m`;
  const gave = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v > 0;
  const derived = (["height_m", "width_m", "depth_m"] as const).filter((k) => !gave(supplied[k]));
  if (!derived.length) return `Screened at ${dims} — the dimensions you gave.`;
  const which = derived.length === 3 ? "All three dimensions were"
    : `${derived.map((k) => k.replace("_m", "")).join(" and ")} ${derived.length === 1 ? "was" : "were"}`;
  return `Screened at ${dims}. ${which} derived from the model's BOUNDING BOX, which spans site and `
    + "context geometry as well as the building — override any that do not look like the mass you "
    + "meant to screen.";
}

/**
 * Which site wind produced these numbers.
 *
 * Every speed in the result is this figure times a zone factor, so reading a default-run screen as a
 * site answer is wrong by the ratio of the two. 5 m/s is the server's default, not a measurement.
 */
export function windBasis(supplied: number | null | undefined, used: number): string {
  const gave = typeof supplied === "number" && Number.isFinite(supplied) && supplied > 0;
  if (gave) {
    return `Site wind ${fmt(used)} m/s — every speed below is this times a zone factor.`;
  }
  return `Site wind ${fmt(used)} m/s — the DEFAULT, not a measurement for this site. Every speed `
    + "below scales directly with it, so put in the local mean pedestrian-level wind before quoting "
    + "any of these figures.";
}

/** The mitigations, or an explicit nothing — an empty list rendered as blank reads as "none needed". */
export function mitigationLines(r: WindResult): string[] {
  if (r.mitigations.length) return r.mitigations;
  return r.acceptable_for_entrances
    ? ["No mitigation is called for by this screen — every zone graded Lawson A–C."]
    : ["This screen raised no mitigation, which is unexpected for a failing result — treat the "
       + "zone table as the finding and take it to a wind consultant."];
}

/** One zone row's comfort phrase, with the safety grade called out rather than listed alongside. */
export function comfortLabel(z: WindZone): string {
  return z.lawson === "S" ? "unsafe — past the 15 m/s safety criterion" : `${z.lawson} · ${z.comfort}`;
}

/** Metres, trimmed — the screen's precision is nowhere near a decimal place on a 120 m tower. */
function fmt(n: number): string {
  return Number.isFinite(n) ? String(Math.round(n * 10) / 10) : "?";
}
