/** MC-UNDEFINED — a Monte-Carlo percentile describes the draws that produced a number, and both
 *  cards captioned it with the draws that were attempted.
 *
 *  `services/api/src/aec_api/proforma/monte_carlo.py`'s `_summary` is careful and says so in its own
 *  docstring:
 *
 *  > `vals` carries NaN for a draw that solved but produced no value for this metric. Those draws
 *  > are **counted, not dropped**: an undefined equity IRR is a scenario where the deal never
 *  > returned capital, which is the worst outcome rather than a missing one. Averaging and
 *  > percentiles are necessarily taken over the defined draws only — there is no number to average
 *  > otherwise — but `prob_at_least` is taken over ALL of them, because that is the question it
 *  > claims to answer.
 *
 *  It publishes `n` (the defined draws), `undefined` (the rest) and `prob_at_least_of_defined`
 *  *"alongside rather than instead, so a reader can see the gap between the two"*. **`undefined`
 *  and `prob_at_least_of_defined` were declared nowhere in `api/types.ts`**, so neither consumer
 *  could read them:
 *
 *  * the Monte-Carlo card captioned `` `${mc.solved} draws` `` over percentiles covering `m.n`;
 *  * the specialty risk sim captioned `` `${r.iterations} draws` ``, which is worse — it is the
 *    draws requested, before failures and before undefined metrics.
 *
 *  **The direction is what makes this dangerous rather than untidy.** The draws left out of a
 *  percentile are the ones where the deal never returned capital, so a P10 over the defined draws
 *  is better than the P10 over the run — and it was labelled with the run's size. *A risk
 *  distribution that silently drops its worst outcomes reports less risk than it measured.*
 *
 *  **And the `n === 0` branch returns `{n, undefined}` and nothing else**, which the old declaration
 *  called impossible by marking the percentiles required. The specialty card rendered four
 *  em-dashes there — for the single most important finding a sim can produce.
 *
 *  Why the undeclared-key gate did not catch it: `apps/web/src/api/responseUndeclared.test.ts`
 *  compares a route's TOP-LEVEL keys, and these live two levels down in `metrics[*]`. That is its
 *  known blind spot (b), *"a root-only comparison blind to a shape wrong one level down"* — the
 *  entry it did hold for this route named `seed` and `variables`, both roots, and the defect was
 *  nested.
 */
import type { MonteCarloMetric } from "../api/types";

/** What the percentiles actually describe, and what was attempted.
 *
 *  `attempted` is whatever the run reports as its denominator — `solved` for the proforma engine,
 *  `iterations` for the specialty one, which does not publish a solved count. Named by the caller
 *  because the two engines answer with different things and flattening them here would hide that. */
export function drawScope(m: MonteCarloMetric, attempted: number, attemptedLabel = "draws"):
    { text: string; complete: boolean } {
  const undef = m.undefined ?? 0;
  // `n === attempted` is NOT the test: an engine may report `attempted` as draws requested while
  // some failed to solve at all, so the honest statement is always "n of attempted".
  const complete = undef === 0 && m.n === attempted;
  if (complete) return { text: `${m.n} ${attemptedLabel}`, complete: true };
  return {
    text: `${m.n} of ${attempted} ${attemptedLabel}`,
    complete: false,
  };
}

/** The sentence that says why the band rests on fewer draws than the run. */
export function undefinedNote(m: MonteCarloMetric, metricLabel = "this metric"): string | null {
  const undef = m.undefined ?? 0;
  if (undef === 0) return null;
  return `${undef} draw(s) produced no ${metricLabel} — a scenario where the deal never returned `
    + `capital, which is the worst outcome rather than a missing one. They are counted in the `
    + `probability below and cannot appear in a percentile, so the band above describes the `
    + `${m.n} draw(s) that resolved.`;
}

/** The all-undefined case: there is no band, and saying so is the finding.
 *
 *  Returns `null` whenever a band exists, so the caller renders this INSTEAD of a row of dashes
 *  rather than beside one. */
export function degenerate(m: MonteCarloMetric, attempted: number, metricLabel = "this metric"):
    string | null {
  if (m.n > 0) return null;
  const undef = m.undefined ?? attempted;
  return `No percentile can be computed: ${undef} of ${attempted} draw(s) produced no `
    + `${metricLabel} at all. That is not missing data — in none of these scenarios did the deal `
    + `return capital.`;
}

/** The clearing probability, with the conditional figure the engine publishes beside it.
 *
 *  Rendering only `prob_at_least` is correct and incomplete; rendering only
 *  `prob_at_least_of_defined` is the defect the engine's comment describes (*"400 of 1000 scenarios
 *  never returning capital came back as a 100% clearing rate"*). Both, with the unconditional one
 *  as the headline, is what the engine asks for. */
export function probReading(m: MonteCarloMetric): { headline: string; gap: string | null } {
  const p = m.prob_at_least;
  if (p == null) return { headline: "—", gap: null };
  const head = `${Math.round(p * 100)}%`;
  const cond = m.prob_at_least_of_defined;
  if (cond == null || cond === p) return { headline: head, gap: null };
  return {
    headline: head,
    gap: `${Math.round(cond * 100)}% among the draws that resolved — the gap is the draws with no `
      + `value, which cannot clear a target and so count against it.`,
  };
}

/** `m.histogram` is absent on the degenerate branch, so a caller that wants bars must ask. */
export function histogram(m: MonteCarloMetric): { counts: number[]; edges: number[] } | null {
  const h = m.histogram;
  return h && h.counts.length ? h : null;
}
