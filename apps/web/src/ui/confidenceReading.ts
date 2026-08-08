/**
 * BOE-MAPPING-DEDUP — one place that knows what the confidence response's numbers MEAN.
 *
 * `POST /projects/{pid}/estimate/confidence` returns three numbers that look alike and are not:
 *
 *   * `confidence`            — a FRACTION (0.715 = 71.5% confident)
 *   * `pct_assumption_based`  — a FRACTION, despite the `pct_` prefix (`est_confidence.py` computes
 *                               `round(assumption_cost / total, 3)`)
 *   * `avg_contingency_pct`   — already a PERCENTAGE (`cont_cost / total` over raw
 *                               `contingency_pct` inputs, so 10.63 means 10.63%)
 *
 * **This has already been got wrong once, in the direction that reassures.** `Math.round()` of a
 * 0–1 value yields only 0 or 1, so the budget panel rendered "1%" for a budget that was 71.5%
 * assumption-based — a plausible number, badly wrong, beside a correct dollar figure. It was fixed
 * at that site (v0.3.886) while the register kept its own copy of the same knowledge, which is the
 * state BOE-MAPPING-DEDUP describes: *"the mapping has more than one implementation"*.
 *
 * A comment in two files is not a fix — it is the same fact stored twice, and the next caller
 * writes a third. This module is the fix: the units are applied here, `confidenceUnitsTest`
 * asserts them, and a caller that goes around it is doing something visibly unusual.
 *
 * The field names are the only thing that has to stay in sync with the server, and
 * `test_est_confidence.py` pins the response shape on that side.
 */

/** Exactly the fields this module reads. Narrower than `ApiClient.estimateConfidence`'s return on
 *  purpose — a structural parameter means the register's and the budget panel's differently-typed
 *  locals both satisfy it, and neither has to import the client to call this. */
export type ConfidenceResponse = {
  confidence: number;
  pct_assumption_based: number;
  assumption_based_cost: number;
  avg_contingency_pct: number;
};

/** The same numbers, all as PERCENTAGES, ready to render. Named `*Pct` throughout so a site that
 *  multiplies by 100 again is reading a name that says it should not. */
export type ConfidenceReading = {
  /** 0–100. */
  confidencePct: number;
  /** 0–100. The one that was rendered as "1%". */
  assumptionBasedPct: number;
  /** Currency, untouched — the server already rounds it. */
  assumptionBasedCost: number;
  /** 0–100. Arrives as a percentage already; converting it would be the opposite error. */
  avgContingencyPct: number;
};

/**
 * Convert one confidence response into display units.
 *
 * Rounds to whole percentages because every current caller does; a caller wanting decimals should
 * take the raw response rather than have this return an unrounded value nobody rounds consistently.
 */
export function confidenceReading(c: ConfidenceResponse): ConfidenceReading {
  return {
    confidencePct: Math.round((c.confidence ?? 0) * 100),
    assumptionBasedPct: Math.round((c.pct_assumption_based ?? 0) * 100),
    assumptionBasedCost: c.assumption_based_cost ?? 0,
    // NOT scaled. This is the asymmetry the whole module exists for.
    avgContingencyPct: Math.round(c.avg_contingency_pct ?? 0),
  };
}

/**
 * The shared one-line readout, as plain text.
 *
 * Both call sites wrote their own sentence and both said the same thing, so the sentence lives here
 * too — with the caveat included. "Documented" and "confident" are different claims and a reader who
 * has just seen a documentation percentage will otherwise carry it over.
 *
 * Returns text, not HTML: the register builds DOM nodes and the budget panel builds an HTML string,
 * so a shared HTML fragment would force one of them to change how it renders. `money` is passed in
 * for the same reason — this module does not choose a currency format.
 */
export function confidenceSummary(c: ConfidenceResponse, money: (n: number) => string): string {
  const r = confidenceReading(c);
  return `${r.assumptionBasedPct}% of cost is assumption-based (${money(r.assumptionBasedCost)}), `
    + `average contingency ${r.avgContingencyPct}%.`;
}
