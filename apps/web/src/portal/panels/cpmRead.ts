/**
 * CPM-SILENT — the schedule card reports a loop as handled and a dropped relationship not at all.
 *
 * Found by RESPKEY-HOP2: `GET /projects/{pid}/schedule/cpm` returns `drawingset`-style through two
 * hops (`schedule_cpm.compute` → `schedule_engine.blank_result`), so until the gate followed the
 * second hop the route was reported as sending NO keys and nothing compared its 15 against the
 * client's 6. Two of the nine undeclared ones are the only things the response says when the
 * schedule is wrong: `cycle` and `issues`.
 *
 * ### What the card rendered, measured on a live engine
 *
 * A three-activity loop (A→B→C→A):
 *
 * ```
 * CPM: project 0d · 0/3 on the critical path · ⚠ cycle broken
 * Critical: —
 * ```
 *
 * while the response carried `cycle: ["a1","a2","a3","a1"]` and
 * `issues: [{severity:"error", code:"CPM.CIRCULAR_LOGIC",
 * message:"Circular logic: a1 -> a2 -> a3 -> a1",
 * action:"no dates computed; break the loop and recalculate"}]`.
 *
 * **"cycle broken" describes the behaviour the engine deliberately stopped having.**
 * `schedule_cpm._cyclic`'s own docstring: *"The old engine broke the loop in dictionary order and
 * returned a full set of dates anyway, flagged only by `has_cycle`. Those numbers were consumed by
 * EVM and the delay analysis exactly as if they meant something."* It now computes nothing and
 * every date is `null` — and the caption still tells a planner the loop was dealt with, over a
 * `project_duration` of 0 taken from `blank_result()`. *Three falsehoods in one line: 0 days is not
 * a duration, "0/3 on the critical path" is not a finding about criticality, and the loop was not
 * broken.*
 *
 * ### The quieter half, and the commoner one
 *
 * A typo'd predecessor needs no loop. Measured: three activities where C cites `"BB"` and no such
 * ref exists —
 *
 * ```
 * CPM: project 2d · 2/3 on the critical path
 * Critical: A → B
 * ```
 *
 * a clean, confident schedule in which Roof hangs off nothing and the duration is wrong, with
 * `issues: [{severity:"warning", code:"MASSING.PREDECESSOR_UNRESOLVED",
 * message:"a3: predecessor 'BB' matches no activity", action:"relationship dropped"}]` unread.
 * `schedule_engine.build_network`'s docstring is explicit about why that list exists: *"Unresolvable
 * predecessor tokens are reported rather than dropped in silence. The old engine discarded them, so
 * a typo in a predecessor field produced a schedule with a missing dependency and no indication
 * anywhere."* **The engine was fixed and the screen still shows nothing**, which is the same
 * sentence as the cycle half with the severity turned down — and this one needs no loop to happen.
 *
 * ### `cycle` holds ids, not refs
 *
 * `_cyclic` builds it from `exc.cycle`, which carries record ids, while the activity rows carry
 * both `id` and `ref`. `"a1 -> a2 -> a3"` names nothing a planner typed; `"A → B → C → A"` names
 * the activities they can go and edit. The mapping is the rows, so it cannot drift.
 */

import type { CpmIssue, CpmResult, CpmRow } from "../../api/schedule";

/** Re-exported so a consumer needs one import. The shapes are DECLARED once, in the api layer that
 *  owns the wire contract — a second copy here is what `api/noRespelledShapes.test.ts` refuses. */
export type { CpmIssue, CpmResult, CpmRow };

/** Activity ids → the ref a planner typed, falling back to the id when a row carries no ref. */
export function refOf(result: CpmResult, id: string): string {
  const row = (result.activities || []).find((r) => r.id === id);
  const ref = row?.ref;
  return typeof ref === "string" && ref.trim() ? ref.trim() : id;
}

/**
 * The loop, in refs rather than ids, as the engine ordered it.
 *
 * The engine closes the ring (`a1 → a2 → a3 → a1`), so the repeated head is kept: a cycle written
 * without its closing edge reads as a path, which is the thing it is not.
 */
export function cycleRefs(result: CpmResult): string[] {
  return (result.cycle || []).map((id) => refOf(result, id));
}

/** Did the engine refuse to compute? `has_cycle` is the engine's own flag and is preferred; a
 *  `cycle` list with no flag is the same refusal reported by the other key. */
export function noDates(result: CpmResult): boolean {
  return !!result.has_cycle || (result.cycle || []).length > 0;
}

export function errors(result: CpmResult): CpmIssue[] {
  return (result.issues || []).filter((i) => i.severity === "error");
}

export function warnings(result: CpmResult): CpmIssue[] {
  return (result.issues || []).filter((i) => i.severity === "warning");
}

/**
 * The headline. On a refused schedule it reports the refusal instead of its zeros.
 *
 * `project_duration`, `critical_count` and `critical_path` all come from `blank_result()` on the
 * cyclic exit — 0, 0 and `[]` — so printing them is printing the absence of an answer as an answer.
 */
export function cpmLine(result: CpmResult): string {
  if (!result.activity_count) return "CPM: no activities with durations yet.";
  if (noDates(result)) {
    const loop = cycleRefs(result);
    return `CPM: NO DATES COMPUTED — the logic contains a loop`
      + (loop.length ? ` (${loop.join(" → ")})` : "")
      + `. ${result.activity_count} activit${result.activity_count === 1 ? "y" : "ies"} are listed `
      + "with no dates at all; break the loop and recalculate. Duration, float and the critical "
      + "path are not available, not zero.";
  }
  return `CPM: project ${result.project_duration}d · ${result.critical_count}/${result.activity_count} on the critical path`;
}

/**
 * What the engine dropped or refused, as one line, or null when it reported nothing.
 *
 * Errors first and counted separately from warnings, because "relationship dropped" and "no dates
 * computed" are not the same news. Rendered on EVERY exit, not just the cyclic one: the dropped
 * predecessor arrives on a schedule that otherwise looks perfect.
 */
export function issuesLine(result: CpmResult): string | null {
  const errs = errors(result);
  const warns = warnings(result);
  if (!errs.length && !warns.length) return null;
  const parts: string[] = [];
  if (errs.length) parts.push(`${errs.length} error${errs.length === 1 ? "" : "s"}`);
  if (warns.length) parts.push(`${warns.length} warning${warns.length === 1 ? "" : "s"}`);
  const shown = [...errs, ...warns].slice(0, 3)
    .map((i) => i.message + (i.action ? ` — ${i.action}` : ""));
  return `Schedule logic: ${parts.join(", ")}. ${shown.join(" · ")}`
    + (errs.length + warns.length > shown.length
       ? ` (+${errs.length + warns.length - shown.length} more)` : "");
}

/** Whether the headline should be rendered as a failure rather than as a result. */
export function cpmSeverity(result: CpmResult): "none" | "warn" | "error" {
  if (noDates(result) || errors(result).length) return "error";
  return warnings(result).length ? "warn" : "none";
}
