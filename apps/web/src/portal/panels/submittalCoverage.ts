/** SUBMITTAL-RETURNED — the submittal card read `N submittals · M open · K overdue · avg T d`, and
 *  every one of those four could be the wrong number for a different reason.
 *
 *  `submittals.CLOSED_STATES` was hand-written as `("returned", "closed")`. The shipped `submittal`
 *  workflow gives `returned` TWO outgoing transitions — `close` and `revise_resubmit` — so it is
 *  not terminal, and a submittal the A/E sent back marked *"Revise & Resubmit"* was counted as
 *  closed: out of `open_count`, and unable to be overdue at all, because the overdue test read
 *  `state not in CLOSED_STATES`. Measured, one such row six weeks past its required-on-site date:
 *
 *  | | `Revise & Resubmit` | `Approved` |
 *  |---|---|---|
 *  | `open_count` | 0 → **1** | 0 → 1 |
 *  | `overdue_count` | 0 → **1** | 0 → 1 |
 *  | `avg_turnaround_days` | 9.0 | 9.0 |
 *  | `needs_resubmittal_count` | — → **1** | — → 0 |
 *
 *  The corrected counts still agree — both rows are `returned` and both are late — so the
 *  resubmittal count is what tells them apart. *A state says where the record is; the disposition
 *  says which way it is going*, and a rejected submittal six weeks late is the most urgent row in
 *  a submittal log.
 *
 *  ### The two counts that could not be taken
 *
 *  * `overdue_count` only counts a row carrying a `required_on_site` date. Measured: **40
 *    submittals in A/E review with none recorded → `overdue_count: 0`**, which reads as *nothing is
 *    late*. EXPIRY-UNDATED is the same shape one register over.
 *  * `avg_turnaround_days` only averages a row carrying BOTH review dates. Measured: **3.5 days
 *    over 2 of 40** — the same number a fully-dated 2-row register returns.
 *
 *  Both reached further than this card: `projecthealth` turned `overdue_count` into a
 *  red/amber/green tile (`submittal_status` there), and `report_builders.construction` printed
 *  `Open` / `Overdue` / `Avg turnaround` as KPIs on an exported register. *A count whose population
 *  is unstated gets quoted by whoever reads it next.*
 */
import type { SubmittalRegister } from "../../api/procurement";

/** How much of the register the lateness check could rule on. */
export type OverdueCoverage = "empty" | "none" | "partial" | "full";

export function overdueCoverage(s: SubmittalRegister): OverdueCoverage {
  const total = s.submittal_count || 0;
  if (!total) return "empty";
  const dated = s.dated_count || 0;
  if (!dated) return "none";
  return dated >= total ? "full" : "partial";
}

/**
 * The headline. Open is never printed without what is owed back, and overdue never without the
 * population it was taken over.
 */
export function submittalHeadline(s: SubmittalRegister): string {
  const total = s.submittal_count || 0;
  if (!total) return "No submittals logged yet";
  const bits = [`${total} submittal${total === 1 ? "" : "s"}`, `${s.open_count} open`];
  if (s.needs_resubmittal_count) bits.push(`${s.needs_resubmittal_count} awaiting resubmittal`);
  const cov = overdueCoverage(s);
  if (cov === "none") bits.push("lateness not assessable — no required-on-site dates recorded");
  else if (cov === "partial") bits.push(`${s.overdue_count} overdue of ${s.dated_count} dated`);
  else bits.push(`${s.overdue_count} overdue`);
  return bits.join(" · ");
}

/**
 * The turnaround figure with its population, or the reason there is none.
 *
 * `null` and zero are different answers: no row has both review dates is not "turnaround is zero
 * days", and the old card printed an em dash for it beside an open count, which reads as fast.
 */
export function turnaroundLine(s: SubmittalRegister): string {
  if (s.avg_turnaround_days == null || !s.turnaround_count) {
    return "No submittal carries both a received and a returned date, so there is no turnaround to "
      + "report — which is not a turnaround of zero.";
  }
  const n = s.turnaround_count;
  const scope = n >= (s.submittal_count || 0)
    ? `all ${n} reviewed submittal${n === 1 ? "" : "s"}`
    : `${n} of ${s.submittal_count} — the ones carrying both review dates`;
  return `Average turnaround ${s.avg_turnaround_days} d over ${scope}.`;
}

/**
 * The coverage sentence — the engine's own where it has one.
 *
 * Reading `coverage_note` rather than rebuilding it is deliberate: RENTROLL-BASIS shipped a second
 * copy of an engine's sentence and the two had to be kept in agreement by hand. One source.
 */
export function submittalCoverageLine(s: SubmittalRegister): string {
  if (s.coverage_note) return s.coverage_note;
  // Only reached by a server that predates the note. Still never a bare count.
  const total = s.submittal_count || 0;
  if (!total) return "No submittals in the register.";
  return `Overdue is over the ${s.dated_count} of ${total} carrying a required-on-site date.`;
}

/**
 * The resubmittal warning, or null.
 *
 * Its own line rather than a clause of the coverage note: this is work owed by a subcontractor
 * today, not a caveat about the figures.
 */
export function resubmittalLine(s: SubmittalRegister): string | null {
  const n = s.needs_resubmittal_count || 0;
  if (!n) return null;
  const rows = (s.rows || []).filter((r) => r.needs_resubmittal);
  const named = rows.slice(0, 4).map((r) => `${r.ref || r.title || "(unref'd)"} (${r.disposition})`);
  const more = rows.length > named.length ? `, +${rows.length - named.length} more` : "";
  return `${n} submittal${n === 1 ? "" : "s"} came back for resubmittal and ${n === 1 ? "is" : "are"} `
    + `still open${named.length ? `: ${named.join(", ")}${more}` : ""}.`;
}

/**
 * The caveat about which states this register calls done, or null.
 *
 * `closed_states` is on the wire because the client cannot derive it — a project may have replaced
 * the submittal workflow, and the terminal states are then its own, not the shipped ones.
 */
export function closedStatesCaveat(s: SubmittalRegister): string | null {
  if (!s.workflow_overridden) return null;
  const st = s.closed_states || [];
  return "This project has replaced the submittal workflow, so “closed” means "
    + (st.length ? `${st.map((x) => `“${x}”`).join(" or ")}` : "a state this register could not resolve")
    + " — not the shipped workflow’s states.";
}

/** The per-row lateness cell. `—` where the row carries no required-on-site date, because a blank
 *  and an on-time row must not render alike. */
export function overdueCell(r: SubmittalRegister["rows"][number]): string {
  if (!r.overdue_assessed) return "—";
  return r.overdue ? "OVERDUE" : "on time";
}

/** True when a number on this card is about materially less than the register it sits on, or work
 *  is owed back. An empty register is not suspect — there is nothing to be missing. */
export function submittalSuspect(s: SubmittalRegister): boolean {
  const cov = overdueCoverage(s);
  if (cov === "none" || cov === "partial") return true;
  if (s.needs_resubmittal_count > 0) return true;
  return s.turnaround_count > 0 && s.turnaround_count < (s.submittal_count || 0);
}
