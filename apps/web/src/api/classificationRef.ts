/** Reading a code against the served classification reference.
 *
 *  `GET /reference/disciplines` returns four payloads and the client kept one. `tree` drove the
 *  viewer's colours; `masterformat_divisions` (the division master — code, title, and the discipline
 *  each rolls up to) and `uniformat_crosswalk` (Uniformat II element → the MasterFormat divisions it
 *  procures through) were dropped at the `.then`, and they are the two that exist nowhere else in
 *  this shape: `tree.disciplines[].divisions` carries only the subset belonging to one discipline,
 *  and nothing else in the client knows that B2020 buys out of Division 08.
 *
 *  That mattered where someone types a code by hand. The Detailing panel asked for a MasterFormat
 *  section with the hint *"e.g. 08 51 00"* and had no way to say what 08 IS — so `80 51 00`, a
 *  transposition into a division that does not exist, was accepted in silence and became a
 *  classification on an IFC element.
 *
 *  Pure, so the reading is testable without a dialog. Nothing here REFUSES a code: MasterFormat
 *  reserves 48-49 and the 80s-90s for user-defined divisions, so an unknown division is a thing to
 *  say out loud, not a thing to block.
 */

/** One row of the division master. */
export interface MfDivision { code: string; title: string; discipline: string | null }
/** One Uniformat II element and the MasterFormat divisions it maps to. */
export interface UfCrosswalk { code: string; title: string; masterformat_divisions: string[] }
/** The flat discipline catalog — code → display name, for naming what a division rolls up to. */
export interface DisciplineRef { code: string; name: string }

export interface ClassificationRefs {
  disciplines: DisciplineRef[];
  masterformat_divisions: MfDivision[];
  uniformat_crosswalk: UfCrosswalk[];
}

/** The leading division of a MasterFormat section — "08 51 00" and "085100" both sit in `08`. */
export function divisionOf(code: string): string | null {
  const digits = code.replace(/[^0-9]/g, "");
  return digits.length >= 2 ? digits.slice(0, 2) : null;
}

/** The Uniformat entry a code belongs to: the LONGEST declared prefix, because the table holds both
 *  `B` and `B20` and the coarser one must not win over the finer. */
export function crosswalkFor(code: string, crosswalk: UfCrosswalk[]): UfCrosswalk | null {
  const want = code.replace(/[^0-9A-Za-z]/g, "").toUpperCase();
  if (!want) return null;
  let best: UfCrosswalk | null = null;
  for (const x of crosswalk) {
    const c = x.code.toUpperCase();
    if (want.startsWith(c) && (!best || c.length > best.code.length)) best = x;
  }
  return best;
}

/**
 * What to tell the person about the code they just typed, or `null` when this system has no
 * reference to read it against (OmniClass and Uniclass are not served here, and saying nothing is
 * correct — an annotation that appears for two systems and not the others is information, whereas a
 * fabricated one is not).
 *
 * `known: false` is the one worth acting on: it means the code names a division the master does not
 * carry, which is either a user-defined division or a typo, and the caller says so without refusing.
 */
export function codeAnnotation(system: string, code: string, refs: ClassificationRefs):
    { text: string; known: boolean } | null {
  const sys = system.toLowerCase();
  if (sys === "masterformat") {
    const div = divisionOf(code);
    if (!div) return null;
    const row = refs.masterformat_divisions.find((d) => d.code === div);
    if (!row) return { text: `Division ${div} is not in the MasterFormat division master`, known: false };
    const disc = refs.disciplines.find((d) => d.code === row.discipline);
    return { text: `Division ${row.code} · ${row.title}${disc ? ` (${disc.name})` : ""}`, known: true };
  }
  if (sys === "uniformat") {
    const row = crosswalkFor(code, refs.uniformat_crosswalk);
    if (!row) return { text: `${code} is not under any Uniformat II element in the crosswalk`, known: false };
    const divs = row.masterformat_divisions;
    return { text: `${row.code} · ${row.title}${divs.length ? ` → MasterFormat ${divs.join(", ")}` : ""}`,
             known: true };
  }
  return null;
}
