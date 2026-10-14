/** LEVEL-UNREAD — the levelling card reported how far it moved the work and never whether the crew
 *  cap is met.
 *
 *  `services/api/src/aec_api/schedule_levelling.py` levels a schedule against per-trade crew caps
 *  and is careful about what it will not invent: *"a trade with no cap is left unconstrained rather
 *  than capped at a guess — inventing an availability would silently move real work for a limit
 *  nobody set"*, and it refuses outright when no cap matches any activity with *"check the trade
 *  spelling"*.
 *
 *  The card rendered three tiles — `move_count`, `unresolved_count`, `finish_moved_days` — and
 *  measured on a four-activity fixture at a cap of 8 crew/day:
 *
 *      within_float   peak 26 -> 26   moves 0   unresolved 5   finish +0d    within_caps FALSE
 *      extend_finish  peak 26 ->  8   moves 3   unresolved 0   finish +21d   within_caps true
 *
 *  **The first row is a total failure and two of its three tiles read zero.** `0 moves` and
 *  `0 days of finish movement` are exactly what a schedule already inside its caps produces, so the
 *  only distinguishing figure was a bare `unresolved 5` beside them. *A screen that reports motion
 *  instead of outcome cannot tell "nothing needed doing" from "nothing could be done".*
 *
 *  Three further things the response carried and the card did not read:
 *
 *  * **`issues`** — the engine's `IssueLog`, whose own module docstring says *"every coercion, drop
 *    or fallback emits one of these. A silent default produces a plausible schedule that is wrong,
 *    with nothing in the output to look at."* A mistyped predecessor arrives as
 *    `MASSING.PREDECESSOR_UNRESOLVED` with `action: "relationship dropped"` — the indication exists,
 *    and the screen was where it stopped.
 *  * **the uncapped trades** — `Electrical` at 30 crew/day is absent from `peak_before` entirely,
 *    because an uncapped trade is unconstrained by definition. Right, and the reader of a verdict
 *    over the capped ones is entitled to know which trades it is silent about.
 *  * **the activities with no trade or no crew size** — one missing field drops an activity from the
 *    levelling, and 2 of 10 did on that fixture.
 */
import type { LevellingResult, ScheduleIssue } from "../../api/schedule";

export type Tone = "" | "good" | "warn" | "crit";

/** Literal tokens, never `` `var(--status-${tone})` `` — `shell/cssVars.test.ts` cannot resolve a
 *  name built at runtime, and a property nothing defines is ignored in silence. */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** THE OUTCOME, which is what levelling is for.
 *
 *  Returns PLAIN TEXT, never markup. The trade name it names comes from the caps the user typed
 *  into the card's own input, so a `<strong>` here would hand the caller a string it has to escape
 *  around — and the first draft did exactly that, then stripped its own tags back out at the render
 *  site. *A reading function that emits HTML makes every one of its callers an escaping decision.*
 *
 *  Returns `null` only when the run did not happen — the caller renders `reason` there, and the
 *  distinction matters because `within_caps` is `null` rather than `false` for a levelling that did
 *  not run: it did not fail to meet the caps either. */
export function capVerdict(r: LevellingResult): { text: string; tone: Tone } | null {
  if (!r.available || r.within_caps == null) return null;
  const over = r.over_cap ?? [];
  if (r.within_caps) {
    return {
      tone: "good",
      text: `Every capped trade is at or below its limit`
        + (r.finish_moved_days ? ` — at the cost of ${r.finish_moved_days} day(s) on the finish`
                               : ` with no movement of the finish`),
    };
  }
  const worst = [...over].sort((a, b) => b.over_by - a.over_by)[0];
  return {
    tone: "crit",
    text: `${over.length} trade(s) still over the cap.`
      + (worst ? ` ${worst.trade} peaks at ${worst.peak_after} against a cap of ${worst.cap}`
                 + ` — ${worst.over_by} over.` : "")
      + (r.horizon === "within_float"
         ? ` The horizon was "keep the finish", so the engine reported what it could not solve `
           + `rather than moving the finish. Re-run with "allow a later finish" to see the price.`
         : ""),
  };
}

/** Per-trade peak against its cap, strongest signal first. Only the CAPPED trades appear — the
 *  uncapped ones have no cap to be compared to and are named separately. */
export function capRows(r: LevellingResult): {
  trade: string; before: string; after: string; cap: string; tone: Tone;
}[] {
  const caps = r.caps ?? {};
  const over = new Set((r.over_cap ?? []).map((o) => o.trade));
  return Object.keys(caps).sort().map((trade) => ({
    trade,
    before: fmt(r.peak_before[trade]),
    after: fmt(r.peak_after[trade]),
    cap: fmt(caps[trade]),
    tone: over.has(trade) ? "crit" : "good",
  }));
}

const fmt = (n: number | undefined) =>
  n == null ? "—" : Number.isInteger(n) ? String(n) : n.toFixed(2);

/** The trades the verdict says nothing about.
 *
 *  Not a defect of the engine and not noise either: an uncapped trade's peak is unaddressed, so a
 *  reader who takes `within_caps` as "the crews work" needs to know which trades were never in the
 *  question. */
export function uncappedNote(r: LevellingResult): string | null {
  const un = r.coverage?.uncapped_trades ?? [];
  if (un.length === 0) return null;
  return `${un.length} trade(s) carry crew and no cap, so the verdict above says nothing about `
    + `them: ${un.join(" · ")}. An uncapped trade is left unconstrained rather than capped at a `
    + `guess — add a cap to bring it into the levelling.`;
}

/** How much of the schedule the levelling could see at all. */
export function coverageNote(r: LevellingResult): { text: string; tone: Tone } | null {
  const c = r.coverage;
  if (!c) return null;
  if (c.without_demand === 0) {
    return { tone: "", text: `All ${c.activities} activity(s) carry a trade and a crew size.` };
  }
  const named = c.without_demand_sample.join(" · ");
  return {
    tone: "warn",
    text: `${c.with_demand} of ${c.activities} activity(s) could enter the levelling. `
      + `${c.without_demand} carry no trade or no crew size, so they draw on nothing and were not `
      + `levelled: ${named}`
      + (c.without_demand > c.without_demand_sample.length
         ? ` … and more (the count is exact; the list is capped)` : "")
      + `.`,
  };
}

/** The engine's own issue log, worst first, with the action it took.
 *
 *  Ordered by severity rather than by arrival: an `error` means data was dropped, and a list that
 *  buries one under a dozen `info` rows is the prose list this type replaced. */
const SEVERITY_RANK: Record<string, number> = { error: 0, warning: 1, info: 2 };

/** Named `levelIssueRows` rather than `issueRows` because `scheduleMethods.ts` already has one,
 *  for the DCMA health checks — and the compiler said so. Worth keeping the longer name: the two
 *  lists answer different questions (what the engine could not represent vs what the schedule does
 *  badly) and a shared name would invite reading one as the other. */
export function levelIssueRows(r: LevellingResult): {
  code: string; text: string; where: string; tone: Tone;
}[] {
  const issues: ScheduleIssue[] = r.issues ?? [];
  return [...issues]
    .sort((a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3))
    .map((i) => ({
      code: i.code,
      text: `${i.message} — ${i.action}`,
      where: [i.field, i.raw_value].filter(Boolean).join(": "),
      tone: i.severity === "error" ? "crit" : i.severity === "warning" ? "warn" : "",
    }));
}

/** The diagnostic the engine attached to a refusal — and ONLY that, not the reason.
 *
 *  `trades` rides along on the two refusals about spelling: *"none of the capped trades appear on
 *  any activity — check the trade spelling"* is unactionable without the list of trades that DO
 *  appear, and that list was undeclared. `cycle` rides along on the logic-loop refusal.
 *
 *  The reason itself is deliberately NOT included. `scheduleMethods.render` already prints it for
 *  every unavailable result, and the first draft returned `reason + extras`, which left the caller
 *  stripping its own prefix back off with a string replace. *A function that returns more than the
 *  caller needs makes the caller undo the surplus.* */
export function unavailableExtras(r: LevellingResult): string | null {
  if (r.available) return null;
  const found = r.trades ?? [];
  const cycle = r.cycle ?? [];
  const parts = [
    found.length ? `Trades found on activities: ${found.join(" · ")}.` : "",
    cycle.length ? `The loop runs through: ${cycle.join(" → ")}.` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : null;
}
