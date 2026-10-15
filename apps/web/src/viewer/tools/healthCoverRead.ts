import type { ModelHealth, ModelHealthLens } from "../../api/model";

/**
 * HEALTH-WEIGHT-COVER — the Model Health composite is a WEIGHTED mean, and its coverage was
 * reported as a COUNT.
 *
 * `model_health.composite` takes a weighted mean over the lenses that produced a score, with the
 * weights renormalised over exactly those. That is the right arithmetic: a lens with no inputs
 * should not drag the number down, and the engine's own note says so — *"lenses with no inputs show
 * 'n/a' and are excluded from the score rather than guessed"*.
 *
 * What follows from renormalising is that **the coverage of that mean is a weight, not a count**,
 * and the caption was the count. The weights are `hygiene .25 · information .25 · coordination .20 ·
 * verified .15 · readiness .15`, so, computed directly from `_WEIGHTS`:
 *
 * | scored | caption as shipped | share of the composite | `overall_score` |
 * |---|---|---|---|
 * | verified + readiness | `2 of 5 checks scored` | **30%** | 80 |
 * | hygiene + information | `2 of 5 checks scored` | **50%** | 80 |
 * | hygiene + information + coordination | `3 of 5 checks scored` | **70%** | 80 |
 *
 * *Two models, the same caption, the same 80, and one of them is a composite over less than a third
 * of what the composite is defined to be.* The count is true; it is simply not the denominator the
 * number depends on, which is the same error as reporting a page length as a total.
 *
 * ## The caption had also stopped counting the lenses
 *
 * The hardcoded note under the table read *"One score over integrity/hygiene (Model QA), ISO 19650
 * KPIs (BIM scorecard), clash coordination, and verified-as-built"* — **four**, where the engine has
 * five. `readiness` (code and permit pre-flight, 15% of the composite) was added and the caption was
 * not. `apps/web/src/api/models.ts`'s own docstring named the same four. And the sentence that names
 * all five correctly was being SERVED, in `note`, and declared by nothing — so the only authoritative
 * copy was the one nobody could read. *A client-side restatement of a server fact is a copy, and a
 * copy is what drifts* — the lesson CLAUDE.md's own line-count note had to learn.
 *
 * Every function here returns PLAIN TEXT. The caller passes it through `resultNote`, which takes
 * HTML, so a reading that carried markup would be a sink.
 */

/** A weight as a percentage share, with no false precision: 0.2 → `20%`. */
function pct(w: number): string {
  return `${Math.round(w * 1000) / 10}%`;
}

/**
 * The coverage line: the count AND the share, because they answer different questions.
 *
 * Returns `null` when nothing scored — then there is no composite to qualify and the caller already
 * says so.
 */
export function healthCoverage(h: ModelHealth): string | null {
  if (h.overall_score == null) return null;
  const n = h.lenses.length;
  const share = h.weight_scored;
  const base = `${h.scored_lenses} of ${n} lens(es) scored, carrying ${pct(share)} of the composite`;
  // The composite is renormalised over the scored lenses, so a partial basis is not a lower score —
  // it is the same score over less evidence, which is the thing a count cannot say.
  if (share >= 0.999) return `${base} — the full basis.`;
  return `${base}. The score is renormalised over those, so it is not lowered by what was not `
    + `measured — it is a composite over ${pct(share)} of the intended basis.`;
}

/** The lenses that did NOT score, with what each is worth, worst-first. `null` when all scored. */
export function healthUnscored(h: ModelHealth, max = 5): string | null {
  const miss = h.lenses.filter((l) => l.score == null)
    .sort((a, b) => b.weight - a.weight || a.label.localeCompare(b.label));
  if (!miss.length) return null;
  const shown = miss.slice(0, max).map((l) => `${l.label} (${pct(l.weight)})`).join(" · ");
  const more = miss.length > max ? ` · ${miss.length - max} more` : "";
  return `Not scored: ${shown}${more}. Each has a tool in this rail or the Report Center.`;
}

/** One lens row's value cell: its score, or `n/a`, and always what it is worth. */
export function healthLensValue(l: ModelHealthLens): string {
  const w = `${pct(l.weight)} of the score`;
  return `${l.score != null ? `${l.score}/100` : "n/a"} · ${w} — ${l.headline}`;
}

/**
 * Is the composite thin enough that the headline number should not be read on its own?
 *
 * The threshold is on the WEIGHT, not the count, which is the whole point of the item. Half is the
 * line: below it, more of the definition is missing than present.
 */
export function healthThin(h: ModelHealth): string | null {
  if (h.overall_score == null) return null;
  if (h.weight_scored >= 0.5) return null;
  return `⚠ Less than half the composite was measurable (${pct(h.weight_scored)}), so `
    + `${h.overall_score}/100 describes the part that was. Score the missing lenses before `
    + "reading this as the model's health.";
}

/** The engine's own sentence naming the lenses and the n/a rule. Verbatim, never restated. */
export function healthNote(h: ModelHealth): string {
  return h.note;
}

/** Why the count and the share are both printed. Verbatim from the engine. */
export function healthWeightBasis(h: ModelHealth): string {
  return h.weight_basis;
}
