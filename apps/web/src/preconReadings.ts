import type { ApiClient } from "./api/client";
import { usd } from "./ui/charts";

/**
 * VE-DARK — the preconstruction money registers, and what their totals leave out.
 *
 * Three registers sit behind `services/api/src/aec_api/precon.py`: decisions, assumptions, and the
 * value-engineering log. Each sums a money field out of free-form record data through `_num`, which
 * **returns 0.0 for anything it cannot parse** — so a row recorded with no figure is counted in
 * `open_count` or `ve_count`, contributes nothing to the money beside it, and nothing in the
 * response said so. The engines now carry the counts (`open_without_cost_impact`,
 * `rows_without_savings`, `accepted_without_savings`) and these are the readings over them.
 *
 * **Which "no figure" states are reachable was measured, not imagined.** The module layer validates
 * these fields on write and refuses `'TBD'` and whitespace-only with 422, so through the register
 * the only ones are a MISSING field and an EMPTY STRING — plus one that surprised: **a boolean is
 * accepted**, and `float(True)` is `1.0`, so under the old `_num` a stray flag in a money column
 * became one dollar of exposure. `_num_or_none` excludes bools for that reason. Claiming a garbage
 * string as a register state would have been a defect nobody can produce.
 *
 * ## Which of the three was a live defect, and which were dark
 *
 * `decisionLog` was **already on screen** in `reportCenter.ts` printing `open_cost_exposure`, so
 * its subset problem was live. `assumptionsRegister` and `veLog` had no caller at all — frozen in
 * `apps/web/src/api/clientCallers.test.ts` — so for them it was latent, and the fix is the screen
 * plus the caveat rather than the caveat alone. *The same defect in three registers was a bug in
 * one and a design constraint on the two that had not shipped.*
 *
 * ## `target_met` is a verdict over a subset
 *
 * `ve_log` answers `target_met: accepted_savings >= target`. An accepted idea with no savings
 * figure adds 0, so a `false` can mean *nobody recorded the numbers* rather than *the ideas do not
 * close the gap* — and those two call for opposite actions: go and price the accepted ideas, versus
 * go and find more ideas. A screen that prints the boolean sends the reader at the wrong one.
 *
 * ## The target needs a stated basis
 *
 * A VE target is the gap you are trying to close, so the honest default is the project's own
 * over-budget variance from `preconAlignment` — and when there is no budget there is no target,
 * because a gap derived from a missing budget is a number nobody can check. The reading says which
 * of the two it is rather than presenting a bare figure.
 *
 * **The money is formatted by `usd` from `ui/charts`, and the repo's own ban is why.** The first
 * draft of this module declared `const money = n => "$" + …` locally, and
 * `apps/web/src/ui/charts.test.ts` refused it: eighteen local currency formatters once disagreed
 * about negatives and ten put the `$` on the wrong side of the minus. That is not academic here —
 * `gap_after_accepted` goes NEGATIVE the moment accepted VE exceeds the target, so the local copy
 * would have printed `$-50,000`. *A ban with a measurement behind it caught a defect in the file
 * written to explain that totals need their exclusions.*
 *
 * Every function here returns PLAIN TEXT: `reportCenter.ts` interpolates into `innerHTML`, and
 * `apps/web/src/ui/innerHtmlGuard.test.ts` is the ratchet that refused the alternative when
 * CODE-ADOPT-DARK tried it.
 */
export type VeLog = Awaited<ReturnType<ApiClient["veLog"]>>;
export type Assumptions = Awaited<ReturnType<ApiClient["assumptionsRegister"]>>;
export type Decisions = Awaited<ReturnType<ApiClient["decisionLog"]>>;

/** What a money total over a register leaves out, or `null` when it leaves out nothing. */
export function exposureCaveat(missing: number, total: number, unit: string,
                               noun = "row"): string | null {
  const n = Math.max(0, Math.trunc(missing) || 0);
  if (!n) return null;
  return `${n} of ${total} ${noun}(s) carry no ${unit} figure and add nothing to the total above `
    + "— the money is a sum over the rest, not over the count beside it.";
}

export interface VeReading {
  /** `none` — the register is empty. `unpriced` — every accepted idea lacks a figure.
   *  `no-target` — nothing to measure against. `short` / `met` — a real verdict. */
  kind: "none" | "unpriced" | "no-target" | "short" | "met";
  headline: string;
  detail: string;
}

/**
 * The VE log in one reading, with `target_met` used only where it means something.
 *
 * `target` being absent is not a failure state: a log with no target is a perfectly good list of
 * ideas and their savings, so it reads as one.
 */
export function veReading(v: VeLog, targetBasis: string | null): VeReading {
  if (!v.ve_count) {
    return {
      kind: "none",
      headline: "No value-engineering ideas recorded",
      detail: "so there is nothing to measure against a target. A target the register cannot "
        + "speak to is not a shortfall — record the ideas first.",
    };
  }
  const totals = `${v.ve_count} idea(s) · proposed ${usd(v.proposed_savings)} · accepted `
    + `${usd(v.accepted_savings)} · rejected ${usd(v.rejected_savings)} · pipeline `
    + `${usd(v.pipeline_savings)}`;
  if (v.target == null) {
    return {
      kind: "no-target", headline: totals,
      detail: targetBasis
        ? `No target to measure against — ${targetBasis}`
        : "No target was given, so no gap is being claimed either way.",
    };
  }
  const accepted = v.accepted_savings;
  const gap = v.gap_after_accepted ?? v.target - accepted;
  const basis = targetBasis ? ` Target basis: ${targetBasis}` : "";
  // THE ORDER MATTERS. An unpriced accepted idea makes the verdict meaningless, so it is answered
  // before the verdict is read — not after it, as a caveat beside a number somebody has believed.
  if (v.accepted_without_savings > 0 && !v.target_met) {
    return {
      kind: "unpriced", headline: totals,
      detail: `${v.accepted_without_savings} of the accepted idea(s) carry NO savings figure, so `
        + `"${usd(accepted)} accepted against a ${usd(v.target)} target" is a sum over the `
        + "priced ones only. Price them before reading this as a shortfall — the two have opposite "
        + `remedies.${basis}`,
    };
  }
  if (v.target_met) {
    return {
      kind: "met", headline: totals,
      detail: `Accepted VE closes the ${usd(v.target)} target.${basis}`,
    };
  }
  return {
    kind: "short", headline: totals,
    detail: `${usd(gap)} of the ${usd(v.target)} target is still open after the accepted `
      + `ideas; ${usd(v.proposed_savings)} is still in proposal.${basis}`,
  };
}

/**
 * Where a VE target comes from, stated so a reader can check it.
 *
 * Returns the number to send and the sentence that justifies it. `null` target means *do not claim
 * a gap*, which is the answer whenever the project has no budget to be over.
 */
export function veTargetFromAlignment(
  a: { budget?: number | null; variance_to_budget?: number | null } | null,
): { target: number | null; basis: string } {
  if (!a || a.budget == null) {
    return { target: null, basis: "this project has no budget recorded, so there is no gap to size "
      + "a VE target from" };
  }
  const v = a.variance_to_budget;
  if (v == null || v <= 0) {
    return { target: null, basis: "the latest estimate is not over budget, so there is no gap to "
      + "close" };
  }
  return { target: v, basis: `the latest estimate is ${usd(v)} over the recorded budget `
    + "(preconstruction alignment)" };
}

/**
 * DECISION-AXES — the decision log's headline printed a STATE count and an ALIGNMENT count as one
 * series, left two of seven decisions unaccounted for, and discarded the category breakdown.
 *
 * As shipped, over a seven-row register measured against a live route:
 *
 * > `7 decisions · 2 open · 2 disputed · cost exposure $250,000 · 0.0 sched days`
 *
 * **`open` is a state and `disputed` is an alignment.** A reader parses three numbers in a row as
 * three slices of the same seven, and these are two different cuts: of the 2 disputed, **1 was open
 * and 1 had already been DECIDED** — a decision taken over a recorded objection, which is a
 * claim-exposure question rather than a to-do, and the opposite of what "2 disputed" beside "2
 * open" suggests. *Two axes rendered as one series is not a presentation choice; it produces a
 * reading the data does not support.*
 *
 * **And `open + decided` came to 5 of 7.** The other two were `superseded`, and `decided_count`,
 * `superseded_count` and `by_status` were all undeclared — so on a decision log the screen could not
 * say how many decisions had been MADE, and could not account for the rest. `by_category` was dark
 * too: `{Envelope: 4, Structure: 2, Vertical transport: 1}` is what tells a PM where the next design
 * meeting goes.
 */

/** The state line: three counts that account for every decision, and nothing else. */
export function decisionStates(d: Decisions): string {
  const parts = [`${d.open_count} open`, `${d.decided_count} decided`];
  if (d.superseded_count) parts.push(`${d.superseded_count} superseded`);
  const named = d.open_count + d.decided_count + d.superseded_count;
  // The states are exhaustive by construction, so a shortfall means a state this reading does not
  // know about — said rather than silently absorbed into the total.
  const gap = d.decision_count - named;
  const unknown = gap > 0 ? ` · ${gap} in another state` : "";
  return `${d.decision_count} decision(s): ${parts.join(" · ")}${unknown}`;
}

/** The alignment line, kept SEPARATE and labelled as a different cut.
 *
 * `null` when nothing is disputed — a `0 disputed` on its own line is a decoration, and the state
 * line above already accounts for everything. */
export function decisionAlignment(d: Decisions): string | null {
  if (!d.disputed_count) return null;
  const bits: string[] = [];
  if (d.disputed_open) bits.push(`${d.disputed_open} still open`);
  if (d.disputed_decided) {
    bits.push(`${d.disputed_decided} already DECIDED over the objection`);
  }
  return `Alignment cuts across those states: ${d.disputed_count} disputed — ${bits.join(", ")}.`;
}

/** The engine's statement of why the two lines above are two lines. Verbatim. */
export function decisionAxisBasis(d: Decisions): string {
  return d.axis_basis;
}

/** Where the decisions cluster, worst-first. Plain text, like everything here. */
export function decisionCategories(d: Decisions, max = 6): string | null {
  const entries = Object.entries(d.by_category);
  if (!entries.length) return null;
  const sorted = entries.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const shown = sorted.slice(0, max).map(([k, v]) => `${k} ${v}`).join(" · ");
  const more = sorted.length > max ? ` · ${sorted.length - max} more categor(ies)` : "";
  return `By category: ${shown}${more}`;
}

/** `showing N of M` when the row list is capped, against the server's own total. */
export function decisionRowNote(d: Decisions): string | null {
  if (!d.rows_truncated) return null;
  return `Showing ${d.rows.length} of ${d.decision_count} row(s) — the server caps the list at `
    + `${d.max_rows}. Every count above is over all ${d.decision_count}.`;
}
