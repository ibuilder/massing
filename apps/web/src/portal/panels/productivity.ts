import type { ApiClient } from "../../api/client";

/**
 * PROD-DARK — the crew productivity loop, and the two things an ahead/behind read means nothing
 * without.
 *
 * `/projects/{pid}/progress/actuals` rolls installed quantities into an **installed rate**
 * (qty ÷ productive hours) and **crew utilization** (productive ÷ productive + idle) per activity
 * group, compares each against its planned rate, and projects the remaining hours at the current
 * rate. `progressActuals` was frozen in `apps/web/src/api/clientCallers.test.ts` as called by
 * nothing, so the field crew's own productivity record had no screen.
 *
 * ## ① The verdict counts only the groups that HAD a baseline
 *
 * `planned_compared` is `ahead + on_track + behind`, and it sits beside `group_count` precisely
 * because they differ: a group with no planned rate gets `status: null` and is in neither tally. So
 * *"0 behind"* over twelve groups none of which has a planned rate is not a job running to plan —
 * it is a job with no plan to run to, and the remedy is to record the rates rather than to relax.
 *
 * ## ② The rows may not be the ones you passed
 *
 * The route substitutes silently: with an empty `actuals` list it analyses the project's stored
 * **Productivity Actuals** records instead, *"so the loop runs off the record of authority, not a
 * one-shot payload"*. `source` names which, and the client type's own comment already called it
 * *"the one key the type did not name"*. A productivity figure whose provenance is unstated is a
 * number somebody will take to a progress meeting.
 *
 * ## Rates are not summable across trades, and the engine says so
 *
 * *"Rates are compared within a group only — units differ across trades, so no cross-trade rate is
 * summed."* There is deliberately no portfolio rate here for that reason; `overall_utilization` is
 * an HOURS ratio, which is unit-free and does roll up.
 */
export type ProdActuals = Awaited<ReturnType<ApiClient["progressActuals"]>>;

export interface ProductivityScope {
  /** `none` — nothing logged. `no-baseline` — groups, but no planned rate anywhere.
   *  `partial` — some groups compared. `full` — every group had a rate to compare against. */
  kind: "none" | "no-baseline" | "partial" | "full";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/** Where the analysed rows came from, in the words a reader needs. `null` when unstated. */
export function provenanceLine(source: string | null | undefined): string | null {
  const s = (source || "").trim();
  if (!s) return null;
  return s === "request"
    ? "Analysed the rows supplied with this request, not the project's stored log."
    : `Analysed the project's stored ${s} records — the field crew's own log, which is the record `
      + "of authority.";
}

/**
 * The reading, in plain text; the panel escapes it.
 *
 * A `behind` group is a finding and outranks the coverage gap, but the gap is still stated — the
 * two are different facts and a reader acting on one needs the other.
 */
export function productivityScope(p: ProdActuals): ProductivityScope {
  if (!p.group_count) {
    return {
      kind: "none", tone: "",
      headline: "No productivity actuals logged",
      detail: "nothing has been recorded against an activity, so there is no rate to compute. Log "
        + "installed quantities and crew hours in Productivity Actuals.",
    };
  }
  const util = p.overall_utilization == null
    ? "utilization —"
    : `${Math.round(p.overall_utilization * 1000) / 10}% utilization`;
  const base = `${p.group_count} activity group(s) · ${util} · `
    + `${p.total_productive_hours} productive / ${p.total_idle_hours} idle hour(s)`;
  if (!p.planned_compared) {
    return {
      kind: "no-baseline", tone: "warn",
      headline: `None of ${p.group_count} group(s) has a planned rate`,
      detail: `${base}. Ahead/behind is not being reported because nothing has a baseline to be `
        + "ahead OF — record planned rates per activity to get a variance.",
    };
  }
  const tally = `${p.ahead} ahead · ${p.on_track} on track · ${p.behind} behind`;
  const worst = p.worst ? ` Worst: ${p.worst}.` : "";
  if (p.planned_compared < p.group_count) {
    return {
      kind: "partial", tone: p.behind ? "bad" : "warn",
      headline: `${p.planned_compared} of ${p.group_count} group(s) compared — ${tally}`,
      detail: `${base}. The other ${p.group_count - p.planned_compared} have no planned rate and are `
        + `in none of those three counts.${worst}`,
    };
  }
  return {
    kind: "full", tone: p.behind ? "bad" : "ok",
    headline: `All ${p.group_count} group(s) compared — ${tally}`,
    detail: `${base}.${worst}`,
  };
}

/** One row per activity group. A group with no baseline says so rather than showing a blank variance. */
export function productivityRows(p: ProdActuals): {
  group: string; rate: string; utilization: string; vsPlanned: string; complete: string;
  remaining: string; strong: boolean;
}[] {
  const pct = (v: number | null) => v == null ? "—" : `${Math.round(v * 1000) / 10}%`;
  return p.groups.map((g) => ({
    group: `${g.group}${g.material_class ? ` · ${g.material_class}` : ""}`,
    rate: g.installed_rate == null ? "—" : `${g.installed_rate} ${g.unit}/h`,
    utilization: pct(g.utilization),
    vsPlanned: g.status == null
      ? "no planned rate"
      : `${g.variance_pct! > 0 ? "+" : ""}${g.variance_pct}% · ${g.status.replace("_", " ")}`,
    complete: g.pct_complete == null ? "—" : `${Math.round(g.pct_complete * 1000) / 10}%`,
    remaining: g.projected_hours_at_rate == null
      ? "—"
      : `${g.projected_hours_at_rate} h at this rate`,
    strong: g.status === "behind",
  }));
}
