import type { ApiClient } from "./api/client";

/**
 * ACTION-SUBSET — an action tracker whose only declared rollup counts finished work.
 *
 * `actions.action_tracker` returns five numbers about what is OUTSTANDING — `open_count`,
 * `overdue_count`, `completion_pct` and the rest — and two rollups over the WHOLE register. Only
 * `by_assignee` was declared, and nothing rendered it. Measured against a live route on a 14-item
 * tracker with 3 open:
 *
 * | | reported | outstanding |
 * |---|---|---|
 * | `by_assignee` | Ana 11 · Ben 2 · Cara 1 | **Ben 2 · Cara 1** |
 * | `by_priority` | High 12 · Low 2 | **High 1 · Low 2** |
 *
 * **Ana has zero outstanding items.** A reader asking an action tracker *who owes what* is sent to
 * whoever has finished the most — and High reads as the dominant priority when exactly one High
 * item is live. *A rollup over the whole register, printed beside five numbers about the open
 * subset, answers a question nobody asked on that screen.* Both populations are kept, because
 * "where has the work been" is fair; the open-scoped pair is what the card reads, and
 * `rollup_basis` carries the engine's own statement of the difference.
 *
 * The row shape was `Record<string, unknown>[]` — the index-signature erasure a sibling register's
 * client comment already names as *"the erasure that keeps a response out of reach of every audit
 * here"*. It forced `(r: any)` at the only call site, so `overdue` in particular was unreachable by
 * any derivation over these declarations.
 *
 * Everything here returns PLAIN TEXT: `reportCenter.ts` interpolates into `innerHTML` and
 * `apps/web/src/ui/innerHtmlGuard.test.ts` is the ratchet.
 */
export type ActionTracker = Awaited<ReturnType<ApiClient["actionTracker"]>>;

/** The outstanding-work headline. `completion_pct` stays, because done-over-total is the one number
 *  here that is legitimately about the whole register and says so by name. */
export function actionHeadline(t: ActionTracker): string {
  if (!t.action_count) return "No action items recorded yet.";
  const pct = t.completion_pct == null ? "—" : `${t.completion_pct}%`;
  const od = t.overdue_count ? ` · ${t.overdue_count} OVERDUE` : "";
  return `${t.open_count} of ${t.action_count} action item(s) outstanding${od} · ${pct} complete`;
}

/** Who owes what, over the OPEN items, worst-first. `null` when nothing is outstanding — a rollup
 *  of an empty set is a heading with no rows. */
export function owedBy(t: ActionTracker, max = 6): string | null {
  const entries = Object.entries(t.open_by_assignee);
  if (!entries.length) return null;
  const shown = entries.slice(0, max).map(([k, v]) => `${k} ${v}`).join(" · ");
  const more = entries.length > max ? ` · ${entries.length - max} more` : "";
  return `Outstanding by assignee: ${shown}${more}`;
}

/** The open items' priority mix. */
export function openPriorities(t: ActionTracker): string | null {
  const entries = Object.entries(t.open_by_priority);
  if (!entries.length) return null;
  return `Outstanding by priority: ${entries.map(([k, v]) => `${k} ${v}`).join(" · ")}`;
}

/** The engine's statement of which rollup is over which population. Verbatim. */
export function rollupBasis(t: ActionTracker): string {
  return t.rollup_basis;
}

/** Where the work HAS been, said as a different question rather than beside the open numbers.
 *
 *  Suppressed when it would merely restate the open rollup — on a tracker with nothing completed the
 *  two are identical, and printing both invites the reader to treat them as two findings. */
export function historicBy(t: ActionTracker, max = 6): string | null {
  if (!t.done_count) return null;
  const entries = Object.entries(t.by_assignee);
  if (!entries.length) return null;
  const shown = entries.slice(0, max).map(([k, v]) => `${k} ${v}`).join(" · ");
  return `Across all ${t.action_count} item(s), done or not: ${shown}`;
}

/** The meeting log line. Separate from the action numbers because it is a different register. */
export function meetingLine(t: ActionTracker): string {
  if (!t.meeting_count) return "No meetings logged.";
  const types = Object.entries(t.meetings_by_type).map(([k, v]) => `${k} ${v}`).join(" · ");
  return `${t.meeting_count} meeting(s) · last ${t.last_meeting ?? "undated"}`
    + (types ? ` · ${types}` : "");
}
