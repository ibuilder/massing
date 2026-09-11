/** How much of a solved pro forma rests on numbers nobody supplied.
 *
 *  `POST /proforma/solve` has always returned `provenance` — per headline figure, which assumptions
 *  the caller DECLARED and which the engine DEFAULTED — and the client type declared seven keys
 *  without it, so the caveat was computed on every solve and shown on none. A deal screen that
 *  reports a 19% equity IRR without saying that eleven of its inputs were engine defaults is not
 *  wrong, it is unreviewable: the reader cannot tell an underwritten number from a placeholder.
 *
 *  Pure, because the rule about when this is worth saying is the part worth pinning.
 */
import type { ProformaProvenance } from "../api/types";

export interface ProvenanceLine { text: string; level: "ok" | "warn"; paths: string[] }

/** At most this many defaulted paths are named inline; the rest are counted. */
const NAMED = 6;

/**
 * The line to show under the returns, or `null` when there is nothing to say.
 *
 * Null on a missing `provenance` (an older server, or a route that does not compute it) — an absent
 * caveat must read as absent, never as "all inputs declared", which is the opposite claim.
 */
export function provenanceLine(p: ProformaProvenance | undefined): ProvenanceLine | null {
  if (!p) return null;
  if (!p.figure_count) return null;
  const n = p.defaulted_input_count;
  if (!n) {
    return { text: `Every input behind these ${p.figure_count} figures was declared.`,
             level: "ok", paths: [] };
  }
  const named = p.defaulted_inputs.slice(0, NAMED);
  const more = p.defaulted_inputs.length - named.length;
  const tail = more > 0 ? `${named.join(", ")} +${more} more` : named.join(", ");
  return {
    text: `${n} input${n === 1 ? "" : "s"} behind these ${p.figure_count} figures `
      + `${n === 1 ? "was" : "were"} defaulted by the engine: ${tail}`,
    level: "warn",
    paths: p.defaulted_inputs,
  };
}
