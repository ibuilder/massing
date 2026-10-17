import type { LiveStatus } from "../api/httpCore";

/**
 * How a live (SSE) subscription's state reads on screen — one mapping, four subscribers.
 *
 * **Why this is shared and the DOM is not.** Slice ⑦ gave the three silent subscribers an
 * `onStatus` handler, and each one's chrome is genuinely different: an inline dot in the pull-plan
 * toolbar, a floating banner over the viewport, a note in the drawings toolbar. Forcing one renderer
 * on all three would need an options bag per caller and read worse than three small functions.
 *
 * What must NOT differ is the part a reader compares across screens: which state is which colour,
 * and what the sentence says. Three copies of that is the shape `noRespelledShapes.test.ts` was
 * written for — *not "these look alike" but "somebody wrote this out twice"* — and it is the part
 * most likely to drift, because it is prose.
 *
 * **`why` is `string | undefined` and the empty string is handled explicitly.** This branch has now
 * corrected the empty-versus-absent confusion six times, twice in the file that was written about
 * it, so the fallback is not a `||` that happens to work: an empty reason is a refusal whose reason
 * the server did not give, which is still a refusal and must still read as one.
 */
export interface LiveDisplay {
  /** A CSS custom-property name, so the colour contract in `ui/colorContract.ts` still governs. */
  tone: "--status-good" | "--status-warn" | "--status-crit";
  /** The whole sentence, ready to put in a text node. Never HTML — a server reason is free text. */
  text: string;
  /** Whether to offer *Try again*. Only a refusal is actionable: the other states are already
   *  retrying on their own, and a button that does what is already happening is noise. */
  retryable: boolean;
}

/**
 * @param st     the stream's state, plus `"connecting"` for the window before the first frame —
 *               `liveStream` reports `connected` on the first MESSAGE, because a delivered frame is
 *               proof the stream works and an accepted socket is not.
 * @param why    the server's refusal reason, when there is one.
 * @param what   what specifically stops working, in the caller's own words. It is the subject of the
 *               sentence on purpose: *"the SSE stream was refused"* tells a superintendent nothing
 *               they can act on, and every one of these three screens loses a different thing.
 */
export function liveDisplay(st: LiveStatus | "connecting", why?: string,
                            what = "Live updates"): LiveDisplay {
  switch (st) {
    case "connected":
      return { tone: "--status-good", text: "live", retryable: false };
    case "connecting":
      return { tone: "--status-warn", text: "connecting…", retryable: false };
    case "reconnecting":
      return { tone: "--status-warn", text: "reconnecting…", retryable: false };
    case "refused":
      return { tone: "--status-crit", retryable: true,
               text: `${what} stopped — ${why && why.trim() ? why : "refused by the server"}.` };
  }
}
