/** CO-REJECTED — the change-order log's total had a term the report did not name, and the term was
 *  money nobody owes.
 *
 *  `services/api/src/aec_api/changeorders.py` accumulates `total += amt` for every COR and then
 *  splits by state — pending, approved, executed, **rejected**. The report printed four of those
 *  five figures:
 *
 *      `${s.co_count} COs · total ${money(s.total_value)} · pending … · approved … · executed …`
 *
 *  Measured on a four-COR fixture (one executed at $100k, one approved at $50k, one pending at
 *  $25k, one **rejected at $400k**):
 *
 *      total_value                       575,000
 *      pending + approved + executed     175,000
 *      UNNAMED RESIDUE                   400,000   <- the rejected COR
 *
 *  *A total whose own parts do not sum to it leaves the reader to invent the difference* — and on a
 *  change-order report the invented difference reads as exposure.
 *
 *  **The same function treated the same refusal two ways.** `total_schedule_days` already excluded
 *  the rejected COR's 30 days (`sd if st not in ("rejected",) else 0`), so within one line of
 *  output the refusal was out of the schedule figure and in the money figure, with nothing saying
 *  so. `services/api/test_refusal_readers.py` states the rule for the class — a refused record is
 *  not exposure — and `cor` was not one of the five instances it covers. **26 of 139 modules
 *  declare a refusal-shaped state and that gate's population is a hand-made list of five**, which
 *  is the measurement the next piece of work needs rather than the fix this one makes.
 *
 *  The engine now publishes `live_value` (total minus rejected) alongside, rather than redefining
 *  `total_value`: the raised total answers a real question — volume of change — and quietly moving
 *  it would change a figure in somebody's saved report.
 */
import type { ApiClient } from "./api/client";
import { usd } from "./ui/charts";

export type CoLog = Awaited<ReturnType<ApiClient["coLog"]>>;

/** The headline: the LIVE figure first, with the raised total and the refusal named beside it.
 *
 *  `usd` from `ui/charts`, never a local formatter — `apps/web/src/ui/charts.test.ts` bans a second
 *  place to define one, because eighteen copies once disagreed about where the minus goes. */
export function coHeadline(s: CoLog): string {
  const live = s.live_value;
  const rejected = s.rejected_value ?? 0;
  const parts = [`${s.co_count} CO(s)`];
  if (live != null) {
    // The exposure figure leads. "Total" led before, and it was the one number on the line that
    // nobody owes all of.
    parts.push(`live ${usd(live)}`);
  }
  parts.push(`pending ${usd(s.pending_value)}`, `approved ${usd(s.approved_value)}`,
             `executed ${usd(s.executed_value)}`);
  if (rejected > 0) {
    // Named, so the gap between `live` and `total` is not a residue the reader has to derive.
    parts.push(`rejected ${usd(rejected)}`);
  }
  parts.push(`raised to date ${usd(s.total_value)}`);
  return parts.join(" · ");
}

/** Does the response's own arithmetic close?
 *
 *  `live_value` must equal pending + approved + executed, and `total_value` must equal
 *  `live_value + rejected_value`. Checked rather than trusted, because the headline above now
 *  presents five figures as a decomposition and a decomposition that does not add up is worse than
 *  one figure on its own. Returns `null` when a key needed to check it is absent — an older server
 *  gets no claim rather than a false one. */
export function coReconciles(s: CoLog): boolean | null {
  if (s.live_value == null || s.rejected_value == null) return null;
  const parts = s.pending_value + s.approved_value + s.executed_value;
  // Money in cents: these are rounded to 2dp server-side, so compare at half a cent.
  const near = (a: number, b: number) => Math.abs(a - b) < 0.005;
  return near(s.live_value, parts) && near(s.total_value, s.live_value + s.rejected_value);
}

/** The schedule side, with its exclusion stated.
 *
 *  `total_schedule_days` excludes the rejected CORs' days. That is right — a refused change claims
 *  no time — and it is the opposite of what the money total did, so the excluded figure is shown
 *  rather than left as an asymmetry a reader would have to find. */
export function coScheduleNote(s: CoLog): string {
  const rejected = s.rejected_schedule_days ?? 0;
  if (rejected <= 0) return `${s.total_schedule_days} schedule day(s) claimed`;
  return `${s.total_schedule_days} schedule day(s) claimed — a further ${rejected} were claimed by `
    + `the rejected CO(s) and are excluded, which is the treatment the money figures above now `
    + `make explicit too.`;
}

/** The refusal warning: how much of the raised total is refused, as a share.
 *
 *  Only above zero. A line that fires on every render is one its reader stops seeing, which is what
 *  COMPTIER-DARK's always-on qualifier cost. */
export function rejectedShareNote(s: CoLog): string | null {
  const rejected = s.rejected_value ?? 0;
  if (rejected <= 0 || s.total_value <= 0) return null;
  const pct = Math.round((rejected / s.total_value) * 100);
  return `${pct}% of the ${usd(s.total_value)} raised to date was rejected and is in no contract `
    + `sum. "Raised to date" is a volume-of-change figure, not exposure.`;
}

/** States in the COR workflow, strongest-to-weakest claim on money, for the by-state row.
 *
 *  Literal and ordered because `by_state` is a dict with no order in it and the states are fixed by
 *  `services/api/modules/cor/module.json` — five of them, enumerated there. Any state the module
 *  grows that is missing here still renders, appended, rather than being dropped. */
export const COR_STATE_ORDER = ["executed", "approved", "submitted", "draft", "rejected"] as const;

export function coStateRows(s: CoLog): { state: string; count: number }[] {
  const by = s.by_state ?? {};
  const known = COR_STATE_ORDER.filter((k) => (by[k] ?? 0) > 0)
    .map((k) => ({ state: k, count: by[k]! }));
  // An unrecognised state is appended, never dropped: the module's workflow is configurable
  // (WORKFLOW-DARK made it so), so this list can legitimately fall behind the register.
  const extra = Object.keys(by).sort()
    .filter((k) => !(COR_STATE_ORDER as readonly string[]).includes(k) && (by[k] ?? 0) > 0)
    .map((k) => ({ state: k, count: by[k]! }));
  return [...known, ...extra];
}
