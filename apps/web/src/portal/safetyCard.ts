/**
 * The project-health card's safety lines: the headline rollup, and what the incidents actually were.
 *
 * Extracted from `portal.ts` rather than grown in place — the size ratchet in
 * `services/api/test_file_sizes.py` asked the question it exists to ask, and for two pure
 * string-shaping functions over one response the answer is plainly yes. Pure on purpose: both take
 * the response and return text, so the breakdown below can be tested without a DOM or a server.
 */

/** The response fields these lines read. Narrower than `safetyMetrics`' full return on purpose —
 *  this module should not be a second place that has to change when an unrelated key moves. */
export type SafetyRollup = {
  incident_count: number;
  recordable_count: number;
  lost_days: number;
  trir: number | null;
  dart: number | null;
  by_class: Record<string, number>;
};

/** The headline: recordables against total, lost days, and the two rates when hours are known. */
export function safetyHeadline(s: SafetyRollup): string {
  if (!s.incident_count) return "Safety: no recordable incidents ✓";
  const trir = s.trir != null ? ` · TRIR ${s.trir}` : "";
  const dart = s.dart != null ? ` · DART ${s.dart}` : "";
  return `Safety: ${s.recordable_count} recordable / ${s.incident_count} incidents `
    + `· ${s.lost_days} lost days${trir}${dart}`;
}

/**
 * WHAT the incidents were — the OSHA-classification breakdown.
 *
 * `by_class` is the first thing the route computes and the first thing its docstring names, and it
 * was the one key the client type omitted, so this card could report five incidents without being
 * able to say that four of them were near-misses.
 *
 * Ordered by count and then alphabetically: the tie-break is not cosmetic, because the card
 * re-renders on every project open and two classes on equal counts would otherwise swap places
 * depending on object key order. Returns null when there is nothing to add, so the caller appends
 * no empty element.
 */
export function safetyClassLine(by: Record<string, number> | undefined, top = 3): string | null {
  const classes = Object.entries(by ?? {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!classes.length) return null;
  const shown = classes.slice(0, top).map(([k, n]) => `${k} ${n}`).join(" · ");
  return `↳ ${shown}${classes.length > top ? ` · +${classes.length - top} more` : ""}`;
}
