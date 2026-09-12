/** The bSDD lookup's failure wording — pure, so the rules can be tested without a DOM.
 *
 *  bSDD is an ONLINE reference service, and the standards panel already scored *what fraction* of
 *  the model carries a bSDD classification URI while offering no way to look one up. BSDD-LOOKUP
 *  wired `GET /bsdd/search` and `GET /bsdd/class`; this module owns the one decision in that screen
 *  that is easy to get quietly wrong.
 *
 *  **The whole point is that an outage must not render as an empty result.** `routers/standards.py`
 *  deliberately maps an unreachable dictionary to 502 rather than letting it 500, and a missing
 *  class to 404. On screen those two, plus "the dictionary genuinely matched nothing", are three
 *  states that look identical if you render them all as a blank list — and they mean opposite
 *  things: one says *try again*, one says *that class does not exist*, one says *your search was
 *  wrong*. Collapsing them is the offered-and-refused shape `lodProxy.ts` beside this file exists
 *  to remove, in its reading form.
 */

/** What went wrong, as the screen must distinguish it. */
export type BsddFailure = "unavailable" | "not-found" | "unknown";

/** Classify a rejected bSDD call by the status our own API attached to it.
 *
 *  Takes the status rather than the error so the rule can be tested without constructing an
 *  `HttpError`, and so a caller that has already unwrapped one cannot accidentally pass `undefined`
 *  and land in a branch that reads as a definite answer. Anything that is not 502 or 404 is
 *  `"unknown"` — deliberately NOT folded into `"unavailable"`, because claiming the reference
 *  service is down when a request was merely malformed sends the reader to wait for a recovery
 *  that is not coming.
 */
export function bsddFailure(status: number): BsddFailure {
  if (status === 502) return "unavailable";
  if (status === 404) return "not-found";
  return "unknown";
}

/** What to tell the reader, given the failure and what was being asked for. `detail` carries the
 *  underlying message for the `"unknown"` case only — the two known states are described in the
 *  product's own words rather than the transport's. */
export function bsddFailureText(kind: BsddFailure, what: string, detail = ""): string {
  if (kind === "unavailable") {
    return `buildingSMART reference service unavailable — ${what} could not be checked. `
      + `This is not an empty result; try again shortly.`;
  }
  if (kind === "not-found") return "The dictionary has no such class.";
  return `failed: ${detail}`;
}
