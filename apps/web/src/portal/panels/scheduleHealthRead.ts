/**
 * SCHEDHEALTH-PARITY — the DCMA grade is relative to a data date the screen never showed, and the
 * loop refusal dropped the only actionable thing in it.
 *
 * `schedule_health.health` is careful about the three states: a project with no activities and a
 * schedule with a logic loop both come back `available: false` with `grade: null` and `score: null`,
 * because neither is a *failing* schedule — "a zero that means 'we did not measure' is
 * indistinguishable from a zero that means 'this is terrible', and only one of those should make
 * somebody's afternoon worse."
 *
 * Three things the card did not read:
 *
 *   - **`data_date`.** Every DCMA check that reads a date reads it relative to this. A grade shown
 *     without it is a verdict relative to nothing — the finding SCHED-STATUS-DARK recorded one
 *     route over, here again.
 *   - **`cycle`.** The loop refusal names the activities that form the loop, and the card printed
 *     the sentence and threw the list away. *The refusal was the useful half and the reason was the
 *     part that got rendered.*
 *   - **`issues`.** `build_network` reports unresolvable predecessor tokens rather than dropping
 *     them, because "the old engine discarded them, so a typo in a predecessor field produced a
 *     schedule with a missing dependency and no indication anywhere." The indication existed and
 *     reached no screen.
 *
 * And three of those keys were absent from BOTH refusal shapes while the engine's docstring promised
 * *"every key the assessed shape carries is present"* — fixed on the server in the same change.
 *
 * Pure, plain text: `issue.message` and `cycle` members are activity refs from user data.
 */

export interface ScheduleIssue {
  severity: string;
  code: string;
  message: string;
  action: string;
  row_key?: string | null;
  field?: string | null;
}

export interface ScheduleHealthRead {
  available: boolean;
  reason?: string;
  grade: string | null;
  score: number | null;
  assessed: number;
  skipped: number;
  failed: number;
  activity_count?: number;
  relationship_count?: number;
  data_date?: string | null;
  issues?: ScheduleIssue[];
  cycle?: string[];
}

export type HealthTone = "ok" | "warn" | "unknown";

export const HEALTH_CSS: Record<HealthTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)", unknown: "var(--muted)",
};

/**
 * The network this grade is about, as of when — shown in EVERY state, including the refusals.
 *
 * `null` only when the server sent none of the three, which is an older server rather than an empty
 * project: the no-activities refusal reports `0 / 0 / null` as a real measurement, and saying "0
 * activities as of no data date" there is the honest line. *A refusal that reports what it measured
 * before refusing is worth more than one that reports only that it refused.*
 */
export function scopeLine(r: ScheduleHealthRead): string | null {
  if (r.activity_count === undefined && r.relationship_count === undefined
      && r.data_date === undefined) return null;
  const a = r.activity_count ?? 0;
  const l = r.relationship_count ?? 0;
  const when = r.data_date ? `as of ${r.data_date}` : "no data date in the schedule";
  return `${a} activity(ies) · ${l} relationship(s) · ${when}.`;
}

/**
 * Whether the grade can be read as a date verdict at all.
 *
 * Without a data date the DCMA checks that compare against "now" have no "now", and the engine
 * derives one from the activities when the caller passes none — so an absent one means the schedule
 * carries no start anywhere. That is a finding, not a footnote.
 */
export function dataDateNote(r: ScheduleHealthRead): { text: string; tone: HealthTone } | null {
  if (r.data_date === undefined) return null;              // older server — `scopeLine` is silent too
  if (r.data_date) return null;                            // present: `scopeLine` already states it
  if (!r.activity_count) {
    return { text: "No activities, so there is no data date to compute against.", tone: "unknown" };
  }
  return { text: "⚠ No data date could be derived from these activities, so every check that "
                 + "compares against a point in time had nothing to compare to.", tone: "warn" };
}

/** The loop members, which the refusal names and the card discarded. */
export function cycleRows(r: ScheduleHealthRead): string[] {
  return r.cycle ?? [];
}

/**
 * Network issues worth showing, highest severity first.
 *
 * Deliberately NOT filtered to "errors": an unresolvable predecessor token is reported as a
 * warning and is exactly the typo whose whole point is that it produced "a schedule with a missing
 * dependency and no indication anywhere".
 */
export function issueRows(r: ScheduleHealthRead, cap = 8): {
  severity: string; message: string; action: string; where: string; tone: HealthTone;
}[] {
  const rank: Record<string, number> = { error: 0, warning: 1, info: 2 };
  return [...(r.issues ?? [])]
    .sort((a, b) => (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3))
    .slice(0, cap)
    .map((i) => ({
      severity: i.severity,
      message: i.message,
      action: i.action,
      where: [i.row_key, i.field].filter(Boolean).join(" · "),
      tone: i.severity === "error" ? "warn" : i.severity === "warning" ? "warn" : "unknown",
    }));
}

/** Both numbers where the issue list stops, or `""` when it is the whole list. */
export function issuePageNote(shown: number, total: number): string {
  return shown < total ? `Showing ${shown} of ${total} network issues.` : "";
}
