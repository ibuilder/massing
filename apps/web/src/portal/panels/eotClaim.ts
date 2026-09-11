/** R40-EOT — the wording for an extension-of-time claim, and the refusals it must not smooth over.
 *
 *  Pure, so the rules can be tested without a DOM.
 *
 *  `POST …/schedule/eot` and `…/schedule/eot/sourced` have computed entitlement since R40 — against
 *  the AACE 29R-03 / SCL Protocol method taxonomy, with the method required and closed, concurrency
 *  named rather than apportioned, and float that absorbs a delay reported as *absorbed*. **Neither
 *  had a client caller.** The two were dark for different reasons and neither was visible to the
 *  reachability gate: `eot` has a three-character leaf, below `MIN_SEGMENT`, so it was never in that
 *  gate's population; `eot/sourced` was frozen in its allowlist.
 *
 *  **The engine's refusals are the feature, and a panel can destroy them without touching the
 *  server.** Every rule below exists to carry one of them intact to the reader:
 *
 *  * **Four refusals, four different places to go.** `method_required`, `baseline_required`,
 *    `actual_finish_required` and `method_needs_schedule_updates` are not one "couldn't compute".
 *    One needs a choice, one needs a captured baseline, one needs an as-built date, and one cannot
 *    be answered by this route at all.
 *  * **Absorbed is not zero.** A delay inside an activity's float earns no time and still happened.
 *    Rendering that row as "0 days" says nothing occurred.
 *  * **Unattributed is not non-excusable.** Slip with no matching cause is the number a claim turns
 *    on; folding it into contractor risk hands one party a finding nobody demonstrated.
 *  * **Concurrency is named, never apportioned** — the panel shows the pairs and says the split is a
 *    contract question, because the protocols themselves disagree.
 *  * **A detected event is not a quantified delay.** `needs_duration` events are excluded from the
 *    figure, so the headline is over a SUBSET and must say so. Same shape as the wind screen's
 *    unchecked mechanism: *a figure computed over part of the evidence is not a figure over all of
 *    it.*
 */
import type { EotResult, EotSourced, EotEvent } from "../../api/schedule";

/** Whether a claim can be computed at all, and what to do when it cannot. */
export function methodGate(method: string | null | undefined): { can: boolean; why: string } {
  if (!method) {
    return { can: false,
             why: "choose an analysis method first — the same facts give different answers under "
                  + "different methods, so an EOT without one cannot be weighed" };
  }
  return { can: true, why: "" };
}

/**
 * What the server refused, in the reader's terms — **kept distinct on purpose**.
 *
 * Collapsing these into one "could not compute" is the defect this file exists to prevent: they send
 * a reader to four different places, and two of them are not fixable by supplying anything.
 */
export function refusal(r: EotResult): string | null {
  switch (r.status) {
    case "analysed":
      return null;
    case "method_required":
      return "No analysis was run: pick a method. " + (r.reason || "");
    case "baseline_required":
      return "No analysis was run: there is no baseline finish to measure against. This is a missing "
             + "plan-of-record, NOT a finding of zero delay.";
    case "actual_finish_required":
      return "No analysis was run: as-planned-vs-as-built compares two END states and the as-built "
             + "finish is missing. Supply it, or choose a method that does not need it — running the "
             + "additive sum instead would put one method's number under another method's name.";
    case "method_needs_schedule_updates":
      return `No analysis was run: ${r.method} needs a dated SERIES of schedules, not one baseline `
             + `and one snapshot. ${r.performed_by
                 ? `It is performed by ${r.performed_by}.`
                 : "Nothing here performs it yet — it needs schedule updates most projects never "
                   + "kept."}`;
    default:
      return `No analysis was run, and the server reported a status this screen does not know `
             + `(${r.status || "none"}). Do not read the absence of a figure as a finding.`;
  }
}

/**
 * The headline, with its method attached — never the number alone.
 *
 * `over_claimed_days` is the published criticism of impacted-as-planned and is surfaced rather than
 * buried: the method is unbounded by what the job actually did, so a delay the contractor recovered
 * still counts at full value.
 */
export function claimHeadline(r: EotResult): string {
  if (r.status !== "analysed" || r.eot_days == null) return refusal(r) || "No analysis was run.";
  const d = r.eot_days;
  const head = `${d} day${d === 1 ? "" : "s"} of extension, by ${r.method.replace(/_/g, " ")}.`;
  const over = r.over_claimed_days
    ? ` This method is not bounded by what the job did: ${r.over_claimed_days} day`
      + `${r.over_claimed_days === 1 ? "" : "s"} were claimed beyond the actual slip.`
    : "";
  const capped = r.capped_by_actual_slip
    ? " Capped at the movement of the completion date — this method cannot grant more time than the "
      + "job actually lost."
    : "";
  return head + over + capped;
}

/**
 * One event row's finding. **The absorbed case is the load-bearing one.**
 *
 * A delay inside the activity's total float earns no extension and DID happen. Reporting it as zero
 * is the reading that says nothing occurred, and the engine's own comment forbids exactly that.
 */
export function eventFinding(e: EotEvent): string {
  if (e.absorbed_by_float) {
    return `${e.days} day${e.days === 1 ? "" : "s"} — ABSORBED by ${e.total_float} day`
      + `${e.total_float === 1 ? "" : "s"} of float. The delay happened; it did not move completion. `
      + "That is not the same as no delay.";
  }
  if (e.entitlement === "unclassified") {
    return `${e.impact_days} day${e.impact_days === 1 ? "" : "s"} beyond float, but the event carries `
      + "no entitlement class — so it earns nothing here. Unclassified is NOT a finding of "
      + "non-excusable; it means nobody has read it against the contract yet.";
  }
  if (!e.eot_days) {
    return `${e.impact_days} day${e.impact_days === 1 ? "" : "s"} beyond float, earning no time: `
      + `classified ${(e.entitlement || "").replace(/_/g, " ")}.`;
  }
  return `${e.eot_days} day${e.eot_days === 1 ? "" : "s"} of extension — `
    + `${(e.entitlement || "").replace(/_/g, " ")}.`;
}

/**
 * Concurrency, stated as the refusal it is.
 *
 * `apportioned` is `false` and must stay visibly false: whether overlapping employer-risk and
 * contractor-risk delay gives time, money, both or neither is a contract-and-jurisdiction question
 * the published protocols disagree on.
 */
export function concurrencyNote(r: EotResult): string {
  const c = r.concurrency;
  if (!c || !c.count) {
    return "No opposing-risk overlap was found among events carrying both a start and a duration. "
      + "Events missing either were NOT tested — that is unexamined, not clear.";
  }
  return `${c.count} concurrent pair${c.count === 1 ? "" : "s"} of opposing risk, named and `
    + "deliberately NOT split. Apportionment is contested between the protocols and governed by the "
    + "contract; a silent 50/50 would manufacture the most argued number in the discipline and "
    + "present it as arithmetic.";
}

/**
 * What the figure was computed OVER — the subset warning.
 *
 * Detection establishes that an event occurred and carries no duration at all, so `needs_duration`
 * events are excluded from the entitlement. A headline over a subset that does not say so is the
 * wind screen's unchecked-mechanism defect in another discipline.
 */
export function coverageNote(s: EotSourced): string[] {
  const out: string[] = [];
  const nd = s.attribution?.needs_duration?.length || 0;
  if (nd) {
    out.push(`${nd} detected event${nd === 1 ? " has" : "s have"} no stated duration and ${nd === 1
      ? "is" : "are"} EXCLUDED from the figure above. Detection establishes that an event occurred; `
      + "it does not establish what the event cost, and assigning it days would be arithmetic "
      + "presented as a finding.");
  }
  const ua = s.attribution?.unattributed_days || 0;
  if (ua) {
    out.push(`${ua} day${ua === 1 ? "" : "s"} of measured slip have NO matching cause. This is `
      + "reported as unattributed, and it is NOT non-excusable — defaulting unexplained slip to "
      + "contractor risk would hand one party a finding nobody demonstrated.");
  }
  const orphan = s.attribution?.events_without_activity || 0;
  if (orphan) {
    out.push(`${orphan} event${orphan === 1 ? " carries" : "s carry"} no activity id, so ${orphan === 1
      ? "it was" : "they were"} matched to nothing. Matching is by explicit activity only — `
      + "proximity is not causation.");
  }
  return out;
}

/** Where the inputs came from. The typed path is unauditable BY DESIGN and says so. */
export function provenanceLine(s: EotSourced | null): string {
  if (!s) {
    return "Computed from dates and events typed into this form. The baseline is the most contested "
      + "input in a delay claim, and typed it is unauditable: two people can produce different "
      + "answers from one project. Capture a baseline and use the sourced analysis for anything "
      + "that leaves this screen.";
  }
  const b = s.baseline;
  return `Measured against the captured baseline ${b?.name || "(unnamed)"}`
    + `${b?.captured_at ? `, taken ${String(b.captured_at).slice(0, 10)}` : ""}`
    + `, with causes from the project's own detected events. Both are re-derivable.`;
}

/** The sourced path's own refusal — a missing baseline is not a missing number. */
export function sourcedRefusal(s: EotSourced): string | null {
  if (s.status !== "baseline_required") return null;
  const n = s.baselines_available?.length || 0;
  return "No baseline is captured for this project, so there is nothing to measure slip against. "
    + (n ? `${n} baseline${n === 1 ? " is" : "s are"} listed — pick one.`
         : "Capture one first: an EOT from a typed finish date is not auditable, which is the whole "
           + "reason this path exists.");
}
