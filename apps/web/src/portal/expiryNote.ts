import type { ExpiryCoverage } from "../api/types";

/**
 * EXPIRY-UNDATED — the reading of an expiry window, in the states the engine can be in.
 *
 * `GET /projects/{pid}/compliance/expiring` counts COI and permit records whose `expires` date
 * falls inside the window. Records with **no readable date** match no window, and the project-health
 * banner read `if (!cc.count)` and printed *"Compliance: no COI/permit expiries ✓"* — a tick, on a
 * project where possibly not one certificate had been evaluated. The route's own docstring says a
 * super should see lapsing compliance "before it bites"; it cannot bite if the date was typed
 * `12/31/2026`, which is the ordinary American way to write one and which
 * `datetime.fromisoformat` refuses.
 *
 * So the tick is now EARNED rather than default: it requires a zero count **and** full coverage.
 * The two causes stay separate in the wording because they ask different things of the reader —
 * a blank field needs somebody to find the certificate, an unreadable one needs somebody to retype
 * a date they believe they already entered.
 *
 * Pure, and returns a value, so the three states are assertable without a DOM.
 */

export type { ExpiryCoverage };

export type ExpiryTone = "ok" | "warn" | "bad";

/** The CSS custom property for a tone. Here rather than at the call site because `portal.ts` sits
 *  on a downward extraction ratchet (`services/api/test_file_sizes.py`) and because a mapping is a
 *  thing worth asserting — the banner used to pick its colour from `cc.expired.length` directly,
 *  which cannot express "clear window, incomplete coverage". */
const TONE_CSS: Record<ExpiryTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)", bad: "var(--status-crit)",
};

const withCss = <T extends { tone: ExpiryTone }>(r: T): T & { css: string } =>
  ({ ...r, css: TONE_CSS[r.tone] });

/** The unevaluated tail, as a clause to append — empty when there is nothing to say. */
export function unevaluatedClause(cov: ExpiryCoverage | undefined): string {
  if (!cov || !cov.unevaluated) return "";
  const parts: string[] = [];
  if (cov.missing_date) parts.push(`${cov.missing_date} with no expiry date`);
  if (cov.unreadable_date) parts.push(`${cov.unreadable_date} with an unreadable date`);
  return ` · ${cov.unevaluated} of ${cov.population} NOT CHECKED (${parts.join(", ")})`;
}

/**
 * The banner's text and tone for an expiry window.
 *
 * `bad` when something has already expired, `warn` when something is lapsing OR when anything went
 * unevaluated, `ok` only when the window is clear AND everything in it was looked at.
 */
export function expiryReading(
  label: string,
  r: { count: number; expired: unknown[]; expiring: unknown[]; coverage?: ExpiryCoverage },
): { text: string; tone: ExpiryTone; earned: boolean; css: string } {
  const cov = r.coverage;
  const unevaluated = cov?.unevaluated ?? 0;
  const tail = unevaluatedClause(cov);
  if (!r.count) {
    // THE TICK IS THE WHOLE POINT. A zero count over records nothing could read is not a pass, and
    // this is the branch that used to print one unconditionally.
    return unevaluated
      ? withCss({ text: `${label}: nothing lapsing in the window${tail}`, tone: "warn", earned: false })
      : withCss({ text: `${label}: no expiries ✓`, tone: "ok", earned: true });
  }
  return withCss({
    text: `${label}: ${r.expired.length} expired · ${r.expiring.length} expiring${tail}`,
    tone: r.expired.length ? "bad" : "warn",
    earned: !unevaluated,
  });
}
