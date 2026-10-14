import type { ScheduleStatusReport, ScheduleStatusRow } from "../../api/types";

/**
 * SCHED-STATUS-DARK — the reading of a status report, with the four distinctions its engine keeps.
 *
 * `services/api/src/aec_api/schedule_status.py` answers the question a superintendent actually
 * asks — *what is late?* — and nothing called it. Its docstring is unusually careful, and every one
 * of its four rules is a thing a status card would naturally flatten:
 *
 * **① The data date is required, not defaulted.** *"Defaulting to today would be wrong on every
 * historical snapshot, every archived project and every what-if — and it would be wrong silently,
 * producing a page full of red on a job that finished two years ago."* With no date the engine
 * returns `checked: false` and every row `unknown`, and a reader must see **"nothing was
 * assessed"**, never "nothing is late". The input here is PREFILLED with today as a convenience
 * and is visible and editable, which is the engine's actual rule: the as-of line is chosen, not
 * assumed.
 *
 * **② Late to start is not overdue.** One is work that should have begun and has not; the other is
 * work past its planned finish. They are separate counts and separate words, never summed into
 * "N late", because the two need different conversations.
 *
 * **③ An activity that finished LATE is complete, not overdue.** Its slip already happened —
 * *"calling it overdue confuses a fact with a risk and puts work on a chase list nobody can act
 * on."*
 *
 * **④ Forecast slip is a CLAIM.** P6's Expected Finish is entered by the person doing the work, so
 * it is intent rather than evidence. It is reported apart from actual slip and **never added to
 * it** — merging them would let a claim masquerade as a condition.
 *
 * Pure, and returns values, so each of the four is assertable without a DOM.
 */

export type StatusTone = "ok" | "warn" | "bad" | "unknown";

/** The headline. `unknown` is its own tone: an unassessed report is not a clean one. */
export function statusReading(r: ScheduleStatusReport): { text: string; tone: StatusTone } {
  if (!r.checked) {
    return {
      text: "NOT ASSESSED — no data date, so nothing can be called late. "
        + `All ${r.counts.unknown} activity(s) came back unknown.`,
      tone: "unknown",
    };
  }
  const late = r.late_to_start.length, over = r.overdue.length, fc = r.forecast_slipping.length;
  // NEVER `late + over`. They are different questions about different work, and an activity can be
  // in both lists — so a sum is not even arithmetically a count of anything.
  const parts = [`as of ${r.data_date}`];
  parts.push(over ? `${over} overdue` : "none overdue");
  parts.push(late ? `${late} late to start` : "none late to start");
  if (fc) parts.push(`${fc} forecast to slip (crew's claim)`);
  if (r.counts.unknown) parts.push(`${r.counts.unknown} unplaceable`);
  return {
    text: parts.join(" · "),
    tone: over ? "bad" : late ? "warn" : r.counts.unknown ? "warn" : "ok",
  };
}

/** Rows for a named list, in the order the engine gave them. */
export function rowsFor(r: ScheduleStatusReport, refs: string[]): ScheduleStatusRow[] {
  const by = new Map(r.activities.map((a) => [a.ref, a]));
  return refs.map((ref) => by.get(ref)).filter((a): a is ScheduleStatusRow => !!a);
}

/**
 * The slip columns, kept apart.
 *
 * Returns BOTH numbers and no total, deliberately: the engine reports actual and forecast slip
 * separately and never adds them, so a consumer that offers a combined figure reintroduces exactly
 * what the separation exists to prevent.
 */
export function slipCells(a: ScheduleStatusRow): { actual: string; forecast: string } {
  return {
    actual: a.actual_slip_days == null ? "—" : `${a.actual_slip_days >= 0 ? "+" : ""}${a.actual_slip_days}d`,
    forecast: a.forecast_slip_days == null ? "—" : `+${a.forecast_slip_days}d claimed`,
  };
}

/**
 * Activities whose recorded actual lies AFTER the data date, which the engine disregards.
 *
 * It says so rather than ignoring them quietly (*"quietly ignoring recorded data is its own
 * trap"*), and reading `future_actual_ignored` is only safe because ROWKEY-SUPERSET put that key
 * in `_ROW_KEYS`: on a blank row it used to raise `KeyError`, so this list is the first consumer
 * that would have hit it.
 */
export function futureActualRows(r: ScheduleStatusReport): ScheduleStatusRow[] {
  return r.activities.filter((a) => a.future_actual_ignored);
}
