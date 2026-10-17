/**
 * SEQ-UNSCHED — `clean`, in green, over a support check that dated nothing.
 *
 * `GET /projects/{pid}/clash/sequence` answers two questions at once. **Space contention** asks
 * whether two trades are scheduled into one place in one window; its population is the schedule,
 * and an activity the engine cannot read is `skipped` and bars `clean`. **Install-before-support**
 * asks whether an element is scheduled ahead of the thing the IFC says holds it up; its population
 * is the MODEL's directed relation graph, and a pair with no dated activity on either end is
 * counted in `support_unscheduled` and does **not** bar `clean`.
 *
 * That asymmetry is correct and the engine now states it (`clean_scope`): element-level schedule
 * binding is sparse on every real project, so folding every unreachable relation into `clean` would
 * make the verdict permanently false, which reports nothing. **What was wrong is what the screen
 * did with it.** Measured against the engine on a one-activity schedule and two directed pairs:
 *
 * | support_pairs | support_evaluated | clean | rail text as shipped | note tone as shipped |
 * |---|---|---|---|---|
 * | 2 | 0 | `true` | `clean` | `ok` — `var(--status-good)` |
 *
 * So the support half ruled on **none** of its pairs and the rail printed a bare `clean` in green.
 * The count was not even hidden — `support_unscheduled_count` was declared and rendered in the
 * body note. It simply did not reach the verdict or the colour, which is the whole of the defect:
 * *a coverage number rendered somewhere on the screen is not a coverage number read BY the
 * verdict.* `services/api/test_verdict_coverage.py` passes this consumer because it names a
 * coverage key, and naming one is what it can derive; whether the tone and the headline consult it
 * is the next question down, and this module is where that one is answered.
 *
 * The other half is the pairs themselves. `support_unscheduled` was undeclared on the client type
 * (`apps/web/src/api/responseUndeclared.test.ts` carried it as a known gap), so the panel could say
 * *34 pair(s) missing a dated binding* and nothing more. **The actionable half is WHICH 34**: each
 * entry is a pair of GlobalIds, so the planner can isolate them in the model and bind them to an
 * activity. A count tells somebody there is work; the GUIDs tell them where it is.
 *
 * Pure, returning plain text. Element names never appear here — the engine sends GlobalIds for the
 * unscheduled pairs and nothing else — but `grade` is engine-constant and the GUIDs are
 * model-derived, so callers still set them with `textContent` (`kvTable` does).
 */
import type { SequenceClashResult, SequenceUnscheduledPair } from "../../api/schedule";

export type Tone = "" | "ok" | "warn" | "bad";

/** How much of each question was asked, as the two populations rather than one blended number.
 *
 *  Deliberately not a single `coverage_pct`: the two halves have different denominators and
 *  averaging them would hide a support check that ruled on nothing behind a readable schedule. */
export function sequenceCoverage(r: SequenceClashResult): {
  analyzed: number; skipped: number;
  pairs: number; evaluated: number; unscheduled: number;
  /** The support question went entirely unasked — pairs exist and none could be dated. */
  supportVacuous: boolean;
  /** Every number below is over a complete population. */
  complete: boolean;
} {
  const pairs = r.support_pairs;
  const evaluated = r.support_evaluated;
  return {
    analyzed: r.analyzed,
    skipped: r.skipped_count,
    pairs,
    evaluated,
    unscheduled: r.support_unscheduled_count,
    supportVacuous: pairs > 0 && evaluated === 0,
    complete: r.skipped_count === 0 && r.support_unscheduled_count === 0,
  };
}

/** The rail headline. `clean` is never printed bare while either coverage gap is open.
 *
 *  The findings count still leads when there are findings — a real contention outranks a coverage
 *  gap, the same ordering the envelope card uses. */
export function sequenceHeadline(r: SequenceClashResult): string {
  const n = r.finding_count + r.support_finding_count;
  if (n) return `${n} sequence clash${n === 1 ? "" : "es"}`;
  const c = sequenceCoverage(r);
  if (!r.clean) return "checked";
  const gaps: string[] = [];
  if (c.skipped) gaps.push(`${c.skipped} not checked`);
  // "0 of 12 pairs dated" rather than "12 unscheduled": the ratio is what says the support half
  // produced no verdict, and the bare count reads as a to-do list beside a clean result.
  if (c.unscheduled) gaps.push(`support ${c.evaluated}/${c.pairs} dated`);
  if (!gaps.length) return "clean";
  return `clean of ${c.analyzed} · ${gaps.join(" · ")}`;
}

/** The tone for the summary note.
 *
 *  `ok` requires BOTH populations complete. As shipped it required `clean && !skipped_count`, so a
 *  project whose every support pair was undated painted `var(--status-good)`. */
export function sequenceTone(r: SequenceClashResult): Tone {
  if (r.finding_count + r.support_finding_count) return "bad";
  if (!r.clean) return "";
  const c = sequenceCoverage(r);
  if (c.complete) return "ok";
  // A support question that produced no verdict at all is the one coverage gap worth a colour:
  // the reader is otherwise looking at the word "clean" with nothing behind half of it.
  return c.supportVacuous ? "warn" : "";
}

/** The sentence that says what the support half could not rule on, and why it is not a finding.
 *
 *  Returns null when every pair was dated — there is nothing to qualify. Grouped by which END is
 *  missing, because the two are different fixes: an undated SUPPORT is usually the structural frame
 *  nobody bound to an activity, and an undated SUPPORTED element is usually the thing the schedule
 *  does cover at a coarser level.
 *
 *  **The counts come from the rollup and the reasons from the capped list**, which are two
 *  populations whenever the cap bites, so a shortfall is declared rather than quietly rescaling the
 *  denominator. */
export function supportCoverageNote(r: SequenceClashResult): string | null {
  const c = sequenceCoverage(r);
  if (!c.unscheduled) return null;
  const by = new Map<string, number>();
  for (const p of r.support_unscheduled) {
    const k = [...p.missing].sort().join(" + ") || "unstated";
    by.set(k, (by.get(k) ?? 0) + 1);
  }
  const parts = [...by.entries()]
    .sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0]))
    .map(([k, n]) => `${n} × no dated activity on the ${k}`);
  const reasons = parts.length ? `: ${parts.join(" · ")}` : "";
  const partial = r.support_unscheduled.length < c.unscheduled
    ? ` (reasons cover the ${r.support_unscheduled.length} pair(s) returned in this response)`
    : "";
  const lead = c.supportVacuous
    ? `NONE of the ${c.pairs} directed support pair(s) could be dated, so install-before-support `
      + `has no verdict on this project`
    : `${c.unscheduled} of ${c.pairs} directed support pair(s) could not be dated and are outside `
      + `the install-before-support result`;
  return `${lead}${reasons}${partial}. Bind an activity to both ends to bring a pair into the check.`;
}

/** One row per undated pair: the grade, and the two GlobalIds with the missing end marked.
 *
 *  GlobalId and not a name, because the engine has no name for an element no activity binds — the
 *  names in `support_findings` come from the ACTIVITY, and these pairs have none. The GUID is what
 *  the viewer can isolate, which is the point of the row. */
export function unscheduledRows(r: SequenceClashResult, cap = 40): { k: string; v: string }[] {
  const mark = (p: SequenceUnscheduledPair, end: "support" | "supported") =>
    `${p[end]}${p.missing.includes(end) ? " (undated)" : ""}`;
  return r.support_unscheduled.slice(0, cap).map((p) => ({
    k: p.grade,
    v: `${mark(p, "supported")} supported by ${mark(p, "support")}`,
  }));
}

/** The cap on the ROWS, and the cap the server already applied — both, or neither.
 *
 *  Two truncations stack here and they are not the same claim: the engine caps the list at 200
 *  (`MAX_UNSCHEDULED_REPORTED`) and the table caps what it draws. Counting against
 *  `support_unscheduled_count` rather than `support_unscheduled.length` is what keeps the page from
 *  presenting a page of a page as everything. */
export function unscheduledPageNote(r: SequenceClashResult, cap = 40): string | null {
  const total = r.support_unscheduled_count;
  const shown = Math.min(r.support_unscheduled.length, cap);
  if (shown >= total) return null;
  const served = r.support_unscheduled_truncated
    ? ` The server returned the first ${r.support_unscheduled.length}.`
    : "";
  return `Showing ${shown} of ${total} undated support pair(s).${served}`;
}

/** Every GlobalId in the undated pairs, de-duplicated, for an isolate.
 *
 *  Both ends, not just the undated one: a pair is only actionable as a pair, and seeing the dated
 *  support beside the undated element is how a planner recognises what the binding should be.
 *  Bounded by the engine's own cap, which is why this is not a count of the whole population. */
export function unscheduledGuids(r: SequenceClashResult): string[] {
  return [...new Set(r.support_unscheduled.flatMap((p) => [p.support, p.supported]).filter(Boolean))];
}
