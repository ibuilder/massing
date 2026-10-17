/**
 * PPC-UNASSESSED — the project-health strip printed "Lean PPC: 0%" in CRITICAL RED on a team whose
 * week simply was not finished yet.
 *
 * `lean.ppc` is explicit about this, and its docstring records fixing the identical defect one layer
 * down in v0.3.974: *"Until v0.3.974 this divided by EVERY record, so the still-Planned ones counted
 * as failures and every team read as failing on a Wednesday."* The engine's rule is
 *
 *   - met or not met, no partial credit;
 *   - **an unanswered commitment makes the period unmeasurable, so `ppc` is `null`, not a number**;
 *   - nothing promised is `null` too — a team that made no commitments has not broken any.
 *
 * **The screen un-fixed it.** The client type declared `ppc: number` and `rating: string`, neither
 * nullable, so TypeScript could not warn — and the card did:
 *
 *     const color = l.rating === "good" ? ok : l.rating === "fair" ? warn : CRIT;
 *     `Lean PPC: <b style="color:${color}">${(l.ppc * 100).toFixed(0)}%</b>`
 *
 * On an unmeasurable period `rating` is `null`, so both comparisons fail and the chain lands on
 * CRIT; and `null * 100` is `0` in JavaScript, so `(0).toFixed(0)` prints `"0%"`. Not an error, not
 * a blank — **a confident red zero**, which is precisely the reading the engine refuses to produce.
 * *An engine that returns null to avoid a false verdict has handed the decision to its consumer,
 * and a non-nullable type is how the consumer is told there is no decision to make.*
 *
 * Found by RESPKEY-DELEGATED's `unassessed` / `reasons_not_recorded` gap. The undeclared keys were
 * the symptom; the LIE in the two keys that WERE declared was the defect, and no key-set comparison
 * can see a nullability that is simply wrong. *A gate that asks which keys are named cannot ask
 * whether the names are true* — which is why this module exists and is tested rather than being
 * four lines of ternary in a 1,228-line shell.
 *
 * Pure, and returns PLAIN TEXT rather than markup: `variance_reason` is free text from the
 * `weekly_plan` register and the old line interpolated it straight into `innerHTML`.
 */

export interface PpcRead {
  commitments: number;
  completed: number;
  missed: number;
  /** `null` while the period is unmeasurable — see this module's header. */
  ppc: number | null;
  /** `null` on the same condition: a rating is a judgement about a team and there is nothing to judge. */
  rating: string | null;
  unassessed: number;
  reasons_not_recorded: number;
  top_variance_reasons: { reason: string; count: number }[];
}

export type PpcTone = "good" | "fair" | "poor" | "unmeasurable";

const TONE_CSS: Record<PpcTone, string> = {
  good: "var(--status-good)",
  fair: "var(--status-warn)",
  poor: "var(--status-crit)",
  unmeasurable: "var(--muted)",
};

export interface PpcLine {
  /** The headline value, already decided: a percentage, or why there isn't one. */
  value: string;
  /** The counts and the top reason, as plain text for the caller to escape. */
  detail: string;
  tone: PpcTone;
  css: string;
  /** True only when a real percentage was computed — the one state a colour judgement is earned in. */
  measured: boolean;
}

/**
 * The health-strip line, or `null` when there is nothing to say.
 *
 * `null` for zero commitments keeps the old behaviour — the strip shows no PPC line at all for a
 * project that has never used weekly planning — and that is a deliberate choice rather than an
 * oversight: the engine's own rule is that a team which promised nothing has not broken anything,
 * and a muted "no commitments" line on every non-lean project is noise in a six-line strip. It is
 * NOT the SCOPE-EMPTY shape, because nothing here reports a verdict over the empty set; the line is
 * absent, not clean.
 */
export function ppcLine(l: PpcRead): PpcLine | null {
  if (!l.commitments) return null;

  const top = l.top_variance_reasons[0];
  const missed = l.missed ? ` · ${l.missed} missed` : "";
  const reason = top ? ` · top reason: ${top.reason}` : "";
  // The unrecorded-reason count, which was undeclared and unrendered. A Pareto of reasons over
  // misses whose reason nobody wrote down is a chart about the subset that was documented, and the
  // engine says so in as many words: "Reasons are never defaulted".
  const unrecorded = l.reasons_not_recorded
    ? ` · ${l.reasons_not_recorded} missed with no reason recorded`
    : "";

  if (l.ppc === null) {
    // UNMEASURABLE, and the detail says what would make it measurable. `unassessed` can be 0 here
    // only if `commitments` is 0, which returned above — but it is read rather than derived,
    // because deriving it as `commitments - completed - missed` would duplicate the engine's
    // arithmetic in the one place the two could drift apart.
    return {
      value: "not yet measurable",
      detail: `${l.unassessed} of ${l.commitments} commitment(s) still unanswered`
        + ` (${l.completed} complete${missed})${reason}${unrecorded}`,
      tone: "unmeasurable",
      css: TONE_CSS.unmeasurable,
      measured: false,
    };
  }

  // The tone is derived from the NUMBER, not from `rating`. The old line tested `rating` against
  // two string literals and fell through to critical on anything else, which is how `null` became
  // red — a default branch is not a place to put "unknown", the same lesson STAKEHOLDER-MEDIUM
  // recorded about the default quadrant of a 2x2.
  const tone: PpcTone = l.ppc >= 0.8 ? "good" : l.ppc >= 0.6 ? "fair" : "poor";
  return {
    value: `${(l.ppc * 100).toFixed(0)}%`,
    detail: `(${l.completed}/${l.commitments} commitments${missed})${reason}${unrecorded}`,
    tone,
    css: TONE_CSS[tone],
    measured: true,
  };
}
