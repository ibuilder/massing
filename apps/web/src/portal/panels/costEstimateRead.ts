/**
 * ESTIMATE-DARK — a rules-based estimate nobody could run, and the second coverage axis that
 * appears the moment somebody can.
 *
 * `POST /projects/{pid}/cost/estimate` has priced the model since R25 and had no caller, and the
 * blocker was never a missing screen: it takes a `rules` body and **nothing in this product stored
 * a cost rule set**, so any card would have had to invent one. `services/api/src/aec_api/cost_rules.py`
 * is that store. This is the reading side.
 *
 * ## The engine's verdict is careful, and it is about ONE axis
 *
 * `complete` is `bool(lines) and not unpriced_count and not missing_quantity_count and not
 * no_rate_count` — three distinct gap populations, kept apart on purpose:
 *
 * | population | what happened | why it is not one of the others |
 * |---|---|---|
 * | `unpriced` | no rule matched the element | nothing was claimed about it |
 * | `missing_quantity` | a rule matched; the model has no quantity for that basis | *"a rate with nothing to multiply is not a cost of nothing, it is an unknown cost"* |
 * | `no_rate` | a `vintage` rule matched; the cost database has no rate for the class | *"neither priced nor unpriced"* — the element was found, the number was not |
 *
 * All three are coverage of **the model**. None of them is coverage of **the rates**.
 *
 * ## The axis the engine cannot see, and the one this card had to add
 *
 * The store seeds a starter set so a new project is not an empty box, and those rates are
 * order-of-magnitude placeholders. So `complete: true` is reachable over a rule set **nobody
 * chose** — every element matched, every quantity measured, every rate invented. *That is the most
 * dangerous output this route has, because it is the confident one.* `fived.estimate` cannot know
 * it: the rules arrive as a list and a list does not say who wrote it. So the route carries
 * `rules_seeded` from the store into the response, and every function here that produces a
 * headline, a tone or a total takes it. **A total whose rates nobody authored is never `ok` and is
 * never presented as the firm's number**, however complete its coverage of the model.
 *
 * Pure, returning plain text. Cost codes, descriptions and selectors are all user-authored free
 * text, so callers set them with `textContent` (`kvTable` does).
 */
// The app's ONE grouped currency format, imported and never rewritten:
// `apps/web/src/ui/charts.test.ts` refuses a local one, because eighteen local copies once
// disagreed about negatives and ten put the `$` on the wrong side of the minus. The first draft of
// this file was the nineteenth — and then tried to alias it to a local `money`, which that gate
// also refuses BY NAME, correctly: a local binding called `money` is the thing a reader has to go
// and check, whatever its body happens to be today.
import { usd } from "../../ui/charts";
import type { CostEstimate, CostMissingQuantity, CostNoRate, CostSov } from "../../api/cost";

export type Tone = "" | "ok" | "warn" | "bad";

/** The estimate as the ROUTE returns it, provenance included.
 *
 *  An alias rather than a second shape: `rules_seeded` and `rule_count` are keys of the response,
 *  so they belong on the response's declared type in `apps/web/src/api/cost.ts` — declaring them
 *  again here would put a wire field outside every audit built on those declarations, which is the
 *  re-spelled-shape defect `apps/web/src/api/noRespelledShapes.test.ts` refuses. The name stays
 *  because the reading functions below are about what a READER needs, and `CostEstimate` is about
 *  what the server sends. */
export type EstimateRead = CostEstimate;


/** The three gap populations, and whether the estimate covers the whole model.
 *
 *  Kept as three numbers and not a sum: they are three different fixes — write a rule, measure a
 *  quantity, pin a cost database — and a single "47 elements not priced" tells a reader there is
 *  work without saying which of the three it is. */
export function estimateCoverage(e: EstimateRead): {
  matched: number; unpriced: number; missingQuantity: number; noRate: number;
  coveragePct: number;
  /** Every element the rules could reach was priced. The engine's own axis. */
  modelComplete: boolean;
  /** The rates are the starter set's placeholders — nobody authored them. */
  ratesUnchosen: boolean;
  /** Nothing priced at all: there are rules and they matched nothing, or there is no model. */
  vacuous: boolean;
  /** **There was nothing to match against.** `/cost/estimate` prices the uploaded PROPERTY INDEX
   *  (`{pid}/props.json`), not the source IFC, so a project with a perfectly good model and no
   *  index prices nothing — and the response is byte-indistinguishable from "no rule matched
   *  anything" unless you notice that `unpriced_count` is also zero, because `unpriced` is derived
   *  over the index itself. Measured on a project with a source IFC and no index: `total: 0 ·
   *  coverage_pct: 0 · unpriced_count: 0 · complete: false`. *Two very different states that
   *  differ only in a number nobody prints.* */
  noModelIndex: boolean;
} {
  return {
    // MATCHED, not priced: `priced_count` is `len(assigned)` and an assigned element can still land
    // in `missing_quantity`. Calling it priced overstates by exactly `missingQuantity`.
    matched: e.priced_count,
    unpriced: e.unpriced_count,
    missingQuantity: e.missing_quantity_count,
    noRate: e.no_rate_count,
    coveragePct: e.coverage_pct,
    modelComplete: e.complete,
    ratesUnchosen: e.rules_seeded === true,
    vacuous: e.line_count === 0,
    noModelIndex: e.priced_count === 0 && e.unpriced_count === 0 && e.no_rate_count === 0
      && e.missing_quantity_count === 0 && (e.rule_count ?? 0) > 0,
  };
}

/** Which rules produced no line, and whether the response says why.
 *
 *  **No save-time check can catch this.** Measured against `query_dsl.parse`: it refuses an EMPTY
 *  query and essentially nothing else — `"(((("`, `"IfcWall &"`, `"=b"` and `"!"` all parse — so a
 *  typo'd property name saves cleanly and then matches nothing. *The validator proves a selector is
 *  well-formed, never that it is right*, which leaves the ESTIMATE as the only honest place to find
 *  out, and only if somebody looks.
 *
 *  `no_rate` carries the rule index, so a rule whose elements were all found and left unrated can
 *  be named as that rather than as a dud selector — the two have different fixes, and telling a
 *  user their selector is wrong when the cost database is the gap is the sort of message that gets
 *  acted on. Everything else is reported as "priced nothing", without guessing between a selector
 *  that matched no element and one whose elements lost their quantities. */
export function rulesPricedNothing(e: EstimateRead): {
  index: number; reason: "no rate in the cost database" | "priced nothing";
}[] {
  const total = e.rule_count ?? 0;
  if (!total) return [];
  const withLines = new Set(e.lines.map((l) => l.rule));
  const unrated = new Set(e.no_rate.map((g) => g.rule));
  const out: { index: number; reason: "no rate in the cost database" | "priced nothing" }[] = [];
  for (let i = 0; i < total; i += 1) {
    if (withLines.has(i)) continue;
    out.push({ index: i, reason: unrated.has(i) ? "no rate in the cost database" : "priced nothing" });
  }
  return out;
}

/** The sentence for rules that produced nothing, or null when every rule earned a line.
 *
 *  Phrased as *"rule 3 (1-based: the 3rd)"* rather than naming the selector, because the response
 *  does not carry the rule set — the index is what both sides agree on, and the editor shows the
 *  rules in that order. */
export function deadRulesNote(e: EstimateRead): string | null {
  const dead = rulesPricedNothing(e);
  if (!dead.length) return null;
  const by = new Map<string, number[]>();
  for (const d of dead) {
    by.set(d.reason, [...(by.get(d.reason) ?? []), d.index + 1]);
  }
  const parts = [...by.entries()].map(([why, ns]) => `rule(s) ${ns.join(", ")} — ${why}`);
  return `${dead.length} of ${e.rule_count} rule(s) put nothing in this estimate: ${parts.join(" · ")}. `
    + `A selector is only checked for being well-formed, never for matching anything, so this is `
    + `the only place a typo shows up.`;
}

/** The rail headline. A total is never printed bare while either axis is open.
 *
 *  Order is deliberate: an unauthored rate set outranks a coverage gap, because a reader who sees
 *  a qualified total goes and looks at the gap, while a reader who sees an unqualified one forwards
 *  it. */
export function estimateHeadline(e: EstimateRead): string {
  const c = estimateCoverage(e);
  if (c.noModelIndex) return "the model is not indexed";
  if (c.vacuous) return "nothing priced";
  if (c.ratesUnchosen) return `${usd(e.total)} at PLACEHOLDER rates`;
  if (c.modelComplete) return `${usd(e.total)} · complete`;
  return `${usd(e.total)} · ${c.coveragePct}% of the model matched`;
}

/** Green only when the model is fully covered AND the rates were authored. */
export function estimateTone(e: EstimateRead): Tone {
  const c = estimateCoverage(e);
  if (c.vacuous) return "bad";
  if (c.ratesUnchosen) return "warn";
  return c.modelComplete ? "ok" : "";
}

/** The sentence a seeded rule set needs, or null once the firm has saved its own.
 *
 *  Returned separately from the coverage note because they qualify different things and can be
 *  true at once: a complete estimate at placeholder rates, and a partial estimate at authored ones,
 *  are both ordinary states and each needs its own line. */
export function unchosenRatesNote(e: EstimateRead): string | null {
  if (e.rules_seeded !== true) return null;
  const n = e.rule_count ?? 0;
  return `These ${n || "starter"} rule(s) are the STARTER SET — placeholder rates nobody on this `
    + `project has chosen. ${usd(e.total)} is arithmetic, not an estimate. Edit and save the rules `
    + `to make this number yours.`;
}

/** What `total` leaves out, by population, with the fix each one names.
 *
 *  Null when the model side is complete. The engine's own note is appended verbatim rather than
 *  paraphrased: *"`total` covers the priced lines only. With unpriced elements or missing
 *  quantities it is a floor, not an estimate."* */
export function estimateCoverageNote(e: EstimateRead): string | null {
  const c = estimateCoverage(e);
  if (c.modelComplete) return null;
  const parts: string[] = [];
  if (c.unpriced) parts.push(`${c.unpriced} matched by no rule — add a selector`);
  if (c.missingQuantity) {
    parts.push(`${c.missingQuantity} priced on a basis the model has no quantity for — measure it`);
  }
  if (c.noRate) {
    parts.push(`${c.noRate} matched by a \`vintage\` rule with no rate in the cost database — pin a `
      + `cost vintage`);
  }
  const lead = c.noModelIndex
    ? `There are no elements to price. This estimate runs against the model's uploaded PROPERTY `
      + `INDEX, not its source IFC, and this project has none — open the model in the viewer (or `
      + `run the data service's indexer) and the ${e.rule_count} rule(s) will have something to match`
    : c.vacuous
    ? `No element was priced at all, so ${usd(e.total)} is a total over nothing`
    : `${usd(e.total)} is a FLOOR over the ${c.coveragePct}% of the model a rule matched`;
  const detail = parts.length ? `: ${parts.join(" · ")}` : "";
  return `${lead}${detail}.${e.note ? ` ${e.note}` : ""}`;
}

/** Where the numbers came from — undeclared quantities and dated rates, both or neither.
 *
 *  Null when every line rests on the model's own declared quantities and a quoted rate, which is
 *  the only case where there is nothing to say. *A quantity the model DECLARED and one this
 *  platform worked out are different claims*, and the difference is exactly what an estimator wants
 *  to know before signing.
 *
 *  **"NOT DECLARED", not "measured" — and the engine's own comment says measured.**
 *  `computed_quantity_lines` counts lines whose `quantity_source !== "declared"`, which folds in
 *  `computed` (measured off the mesh), `override` (an estimator's own number) and `unknown` — and
 *  `unknown` is the common one, because a `count` basis synthesises a quantity of 1.0 with no
 *  source at all. Measured against the engine: two lines, one declared wall area and one door
 *  priced per count, returns `computed_quantity_lines: 1` for the DOOR, whose quantity was assumed
 *  rather than measured. The predicate is the authority here and the comment is a gloss on it;
 *  calling the number "measured" on screen would claim a mesh was consulted where nothing was. */
export function provenanceNote(e: EstimateRead): string | null {
  const bits: string[] = [];
  if (e.computed_quantity_lines) {
    bits.push(`${e.computed_quantity_lines} line(s) worth ${usd(e.computed_quantity_amount)} rest `
      + `on quantities the model did NOT declare — measured, overridden or assumed`);
  }
  if (e.vintage_rate_lines) {
    const v = e.vintage;
    const where = v && (v.year || v.region)
      ? ` (${[v.year, v.region].filter(Boolean).join(" · ")}${v.escalation_pct != null
        ? `, escalated ${v.escalation_pct}%` : ""})`
      : "";
    bits.push(`${e.vintage_rate_lines} line(s) priced from the pinned cost database${where}`);
  }
  return bits.length ? `${bits.join(". ")}.` : null;
}

/** One row per priced line, biggest first (the engine already sorts by amount descending). */
export function lineRows(e: EstimateRead, cap = 40): { k: string; v: string }[] {
  return e.lines.slice(0, cap).map((l) => ({
    k: `${l.code} — ${l.description}`,
    v: `${usd(l.amount)} · ${l.quantity.toLocaleString()} ${l.basis} × $${l.unit_cost} `
      + `(${l.quantity_source} qty, ${l.rate_source} rate)`,
  }));
}

/** The cap on the table, counted against `line_count` rather than the array it was handed. */
export function linePageNote(e: EstimateRead, cap = 40): string | null {
  const shown = Math.min(e.lines.length, cap);
  if (shown >= e.line_count) return null;
  return `Showing the ${shown} largest of ${e.line_count} line(s) — ordered by amount.`;
}

/** One row per unpriced element, labelled with WHICH of the three gaps it is in.
 *
 *  The three lists are concatenated and each row carries its population, because the reason is the
 *  fix: a reader scanning a flat list of GUIDs learns only that something is wrong. The three
 *  shapes differ — `unpriced` is a bare GlobalId, the other two carry the rule that wanted them —
 *  so each is read as what it is rather than through one widened type that would make every field
 *  optional and every row's detail a maybe. */
export function gapRows(e: EstimateRead, cap = 40): { k: string; v: string }[] {
  const mq = (g: CostMissingQuantity) => ({
    k: "no quantity", v: `${g.guid} · ${g.code} · needs ${g.basis}`,
  });
  const nr = (g: CostNoRate) => ({
    k: "no rate in the cost database", v: `${g.guid} · ${g.code} · ${g.ifc_class || "unclassified"}`,
  });
  return [
    ...e.unpriced.map((guid) => ({ k: "no rule matched", v: guid })),
    ...e.missing_quantity.map(mq),
    ...e.no_rate.map(nr),
  ].slice(0, cap);
}

/** The gap table's cap AND the server's own, which are two different claims.
 *
 *  `unpriced` and `no_rate` are each capped at 5,000 by `fived.bind` with their counts left exact —
 *  the engine already following the TRUNC-COUNTED rule — so a page of this table can be a page of a
 *  page. Counted against the three COUNTS, never against the arrays. */
export function gapPageNote(e: EstimateRead, cap = 40): string | null {
  const total = e.unpriced_count + e.missing_quantity_count + e.no_rate_count;
  const served = e.unpriced.length + e.missing_quantity.length + e.no_rate.length;
  const shown = Math.min(served, cap);
  if (shown >= total) return null;
  const trunc = served < total ? ` The server returned ${served} of them.` : "";
  return `Showing ${shown} of ${total} element(s) outside the total.${trunc}`;
}

/** Every GlobalId in the three gap populations, de-duplicated, for an isolate.
 *
 *  Bounded by whatever the server returned in those lists, which is why this is not a count of the
 *  whole population — the counts are. */
export function gapGuids(e: EstimateRead): string[] {
  return [...new Set([
    ...e.unpriced,
    ...e.missing_quantity.map((g) => g.guid),
    ...e.no_rate.map((g) => g.guid),
  ].filter(Boolean))];
}

// ------------------------------------------------------------------------------------------------
// The schedule of values. `/cost/sov` shares `_run_estimate` with the estimate, so it was unblocked
// by the same rule store — and its own response is careful in a way the estimate's is not: it
// carries THREE verdicts and its route docstring says, in as many words, to read them before using
// the result. *An engine that names its own preconditions has done the hard half; the consumer that
// prints the total and not the preconditions undoes it.*
// ------------------------------------------------------------------------------------------------

/** Is this schedule of values billable, and what would make it not?
 *
 *  Three independent questions, kept apart because each has a different remedy:
 *  **scope** (`covers_whole_model` — price the excluded elements), **fee** (`at_cost` — decide
 *  whether this is cost-plus), and **arithmetic** (`reconciles`, `reconciles_by_element` — a
 *  regrouping that lost money, which should be impossible and is therefore checked). */
export function sovBillable(s: CostSov): {
  coversScope: boolean; atCost: boolean; reconciles: boolean; byElement: boolean;
  duplicates: number; truncated: number;
  /** Nothing here would make a G702/G703 reviewer reject it. */
  clean: boolean;
} {
  return {
    coversScope: s.covers_whole_model,
    atCost: s.at_cost,
    reconciles: s.reconciles,
    byElement: s.reconciles_by_element,
    duplicates: s.duplicate_guids.length,
    truncated: s.truncated,
    clean: s.covers_whole_model && s.reconciles && s.reconciles_by_element
      && s.duplicate_guids.length === 0 && s.truncated === 0,
  };
}

/** The SOV headline. Never a bare total: a schedule of values is the document somebody bills
 *  against, and the one number on it that is always correct is the sum of its own lines. */
export function sovHeadline(s: CostSov): string {
  const b = sovBillable(s);
  const head = `${usd(s.sov_total)} over ${s.item_count} item(s)`;
  const fee = b.atCost ? " at cost (NO fee)" : ` incl. ${s.markup_pct}% markup`;
  if (!b.coversScope) return `${head}${fee} — PARTIAL SCOPE`;
  if (!b.reconciles || !b.byElement) return `${head}${fee} — DOES NOT RECONCILE`;
  return `${head}${fee}`;
}

/** Red on an arithmetic failure, amber on partial scope or an unpriced fee, green when billable.
 *
 *  A failure to reconcile outranks partial scope: missing scope is a bigger job than it looks,
 *  while money that vanished in the regrouping means a line on the bill is wrong. */
export function sovTone(s: CostSov): Tone {
  const b = sovBillable(s);
  if (!b.reconciles || !b.byElement || b.duplicates) return "bad";
  if (!b.coversScope || b.truncated) return "warn";
  return b.atCost ? "" : "ok";
}

/** The three sentences the route asks a caller to read, each only when it has something to say. */
export function sovBillableNotes(s: CostSov): string[] {
  const b = sovBillable(s);
  const out: string[] = [];
  if (!b.coversScope) {
    const why = s.excluded.map((x) => `${x.count} ${x.reason}`).join(" · ");
    out.push(`PARTIAL SCOPE — this schedule covers only what priced${why ? `: ${why}` : ""}. Every `
      + `line in it is correct and the job is bigger than the total.`);
  }
  if (b.atCost) {
    out.push("AT COST — the scheduled values carry no fee. Correct for cost-plus, an under-bill on "
      + "lump sum.");
  }
  if (!b.reconciles) {
    out.push(`DOES NOT RECONCILE — the items sum to ${usd(s.sov_total)} against an estimate of `
      + `${usd(s.estimate_total)} plus markup. The regrouping lost or gained money.`);
  }
  if (!b.byElement) {
    out.push(`THE SECOND ACCUMULATION DISAGREES — per-element amounts total `
      + `${usd(s.element_total)} against the estimate's ${usd(s.estimate_total)}. Two routes to `
      + `the same money, and they do not meet.`);
  }
  if (b.duplicates) {
    out.push(`${b.duplicates} GlobalId(s) reach two items and would be BILLED TWICE: `
      + `${s.duplicate_guids.slice(0, 5).join(", ")}${b.duplicates > 5 ? " …" : ""}.`);
  }
  if (s.residual_applied) {
    out.push(`${usd(s.residual_applied)} of rounding was placed on the largest item so the G703 `
      + `column foots.`);
  }
  if (b.truncated) {
    out.push(`${b.truncated} further item(s) were dropped by the server's cap and are NOT in this `
      + `total.`);
  }
  return out;
}

/** Was this schedule built from the estimate the reader is looking at?
 *
 *  The response carries `estimate_total` and not the estimate itself, which is enough: if the
 *  totals differ, the rule set moved between the two calls — somebody saved while this screen was
 *  open — and **billing off the older reading is the defect this whole item is about, one layer
 *  down.** Null when they agree, which is the ordinary case. */
export function sovDriftNote(s: CostSov, estimateTotal: number): string | null {
  if (s.estimate_total === estimateTotal) return null;
  return `The estimate under this schedule totals ${usd(s.estimate_total)}, not the `
    + `${usd(estimateTotal)} shown a moment ago — the cost rules changed in between. Re-run the `
    + `estimate before billing from this.`;
}

/** One row per SOV item, in COST CODE order as the engine returns them. */
export function sovItemRows(s: CostSov, cap = 60): { k: string; v: string }[] {
  return s.items.slice(0, cap).map((i) => ({
    k: `${i.item_no} · ${i.cost_code} — ${i.description}`,
    v: `${usd(i.scheduled_value)}${i.markup_amount ? ` (incl. ${usd(i.markup_amount)} fee)` : ""}`
      + ` · ${i.element_count} element(s)`
      + `${i.merged_lines > 1 ? ` · ${i.merged_lines} lines merged` : ""}`,
  }));
}

/** The table's cap and the server's, counted against `item_count` plus what the server dropped. */
export function sovPageNote(s: CostSov, cap = 60): string | null {
  const shown = Math.min(s.items.length, cap);
  const total = s.item_count + s.truncated;
  if (shown >= total) return null;
  return `Showing ${shown} of ${total} item(s), in cost-code order.`;
}
