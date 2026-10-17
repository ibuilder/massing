/** CAPTABLE-PIPELINE — the Commit column summed to $16,000,000 under a total row of $6,000,000.
 *
 *  `capital.cap_table` is careful and documents itself at length. Only COMMITTED capital owns
 *  anything, so a `prospect` row is kept visible at 0% with its money reported separately as
 *  `pipeline_commitment` — *"so the interest is still on screen, just not as ownership."* The
 *  Investors tab rendered Investor / Commit / Own % / Unreturned, with a Total row of
 *  `total_commitment`, which EXCLUDES the pipeline. Measured against a live server on the engine's
 *  own docstring scenario — one committed LP at $6M and one $10M prospect:
 *
 *  | investor | commitment | own % | counts_toward_ownership | status |
 *  |---|---|---|---|---|
 *  | Real LP | 6,000,000 | 100.0 | true | committed |
 *  | Big Prospect | **10,000,000** | 0.0 | **false** | prospect |
 *
 *  Commit column **$16,000,000**. Total row **$6,000,000**. *A total whose own parts do not sum to
 *  it leaves the reader to invent the difference* — CO-REJECTED, on equity instead of change
 *  orders, and on the one table where the invented difference reads as dilution.
 *
 *  ## Everything needed was published; two keys were undeclared and two were opaque
 *
 *  `pipeline_commitment` and `workflow_in_use` were undeclared at the top level. The per-row
 *  `counts_toward_ownership` and `status` were declared as `Record<string, unknown>` — the OPAQUE
 *  bucket in `apps/web/src/api/deadFieldTyped.test.ts`, which names nothing, so no audit over these
 *  declarations could see them and the response-key gate skipped the row surface entirely. The
 *  consumer then cast to `any`. *An opaque row type is a field list nobody can audit and every
 *  consumer must guess at.*
 *
 *  ## `workflow_in_use` is the distinction that makes a 0% row readable
 *
 *  `investor` declares `initial: prospect`, so on a project where nobody ever ran `commit` EVERY
 *  investor is a prospect. The engine's rule: until one leaves that state, `prospect` means
 *  *untouched* and everyone counts; once one has, it means *not committed* and the state is
 *  evidence. So a 0% row means two completely different things depending on this flag, and the
 *  screen had no way to say which.
 */
import type { CapTable, CapTableRow } from "../api/finance";

export type Tone = "" | "good" | "warn" | "crit";

/** Literal, not `var(--status-${tone})` — a runtime-built custom property resolves to nothing and
 *  is dropped in silence (`apps/web/src/shell/cssVars.test.ts` holds that line). */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** Does the Commit column add up to the totals beneath it? Asserted on the backend across four
 *  fixtures; checked here too, because the screen is where the two numbers meet. */
export function commitReconciles(t: CapTable): boolean {
  const col = t.rows.reduce((s, r) => s + r.commitment, 0);
  return Math.abs(col - (t.total_commitment + t.pipeline_commitment)) < 0.01;
}

/** The committed total with the uncommitted interest beside it, never folded in and never dropped.
 *
 *  `money` is injected rather than imported so this module formats nothing — the panel owns the
 *  currency formatter and `apps/web/src/ui/charts.test.ts` bans a second one. */
export function commitHeadline(t: CapTable, money: (n: number) => string): {
  text: string; tone: Tone;
} {
  if (!t.investor_count) {
    return { tone: "", text: "No investors recorded yet." };
  }
  const owners = t.rows.filter((r) => r.counts_toward_ownership).length;
  if (t.pipeline_commitment <= 0) {
    return {
      tone: "good",
      text: `${money(t.total_commitment)} committed across ${owners} investor(s) — every recorded `
        + "interest is committed, so the Commit column and this total are the same money.",
    };
  }
  const pipelineRows = t.investor_count - owners;
  return {
    tone: "warn",
    text: `${money(t.total_commitment)} COMMITTED across ${owners} investor(s), plus `
      + `${money(t.pipeline_commitment)} of uncommitted interest from ${pipelineRows} more. `
      + `Ownership is computed against the committed figure only, so the Commit column below sums `
      + `to ${money(t.total_commitment + t.pipeline_commitment)} and this total does not.`,
  };
}

/** What a 0% row MEANS on this project, which depends on whether the workflow has been used.
 *
 *  Shown only when it changes the reading: with the workflow untouched every row counts, so there
 *  are no 0% rows to explain, but the reader should still know the states are being ignored. */
export function workflowNote(t: CapTable): string | null {
  if (!t.investor_count) return null;
  if (!t.workflow_in_use) {
    return "No investor has been moved off the initial `prospect` state, so the state carries no "
      + "information yet and EVERY recorded interest is counted as ownership. Run `commit` on the "
      + "investors who have actually committed and these figures will narrow.";
  }
  const pipelineRows = t.rows.filter((r) => !r.counts_toward_ownership);
  if (!pipelineRows.length) return null;
  const names = pipelineRows.map((r) => r.investor || r.ref || "(unnamed)").join(", ");
  return `${pipelineRows.length} investor(s) hold 0% because their interest is not committed `
    + `(${names}). They are shown rather than dropped — the interest is real, it is just not `
    + "ownership.";
}

/** One row per investor, owners first, carrying the state and the ownership flag the table never
 *  showed. Sort order follows the engine's: it already puts owners first and then by size, and
 *  re-sorting here would be a second rule to disagree with. */
export function ownershipRows(t: CapTable): {
  investor: string; state: string; commitment: number; pct: string; unreturned: number;
  counts: boolean; tone: Tone; id: string;
}[] {
  return t.rows.map((r) => ({
    investor: r.investor || r.ref || "(unnamed)",
    state: stateLabel(r, t.workflow_in_use),
    commitment: r.commitment,
    // A non-owning row's 0% is not a measurement, so it is not printed as one.
    pct: r.counts_toward_ownership ? `${r.ownership_pct}%` : "—",
    unreturned: r.unreturned,
    counts: r.counts_toward_ownership,
    tone: r.counts_toward_ownership ? "" : "warn",
    id: r.id ?? "",
  }));
}

/** The row's state as a reader needs it. With the workflow unused, the stamped `prospect` is not a
 *  claim about the investor and is marked as such rather than shown as a status. */
export function stateLabel(r: CapTableRow, workflowInUse: boolean): string {
  const s = (r.status ?? "").trim();
  if (!workflowInUse) return s ? `${s} (workflow unused)` : "—";
  if (!s) return "—";
  return r.counts_toward_ownership ? s : `${s} — not ownership`;
}

/** The subtotal line for the Commit column, so the column has a total of its own that is true. */
export function commitColumnTotal(t: CapTable, money: (n: number) => string): string | null {
  if (t.pipeline_commitment <= 0) return null;
  return `Column total ${money(t.total_commitment + t.pipeline_commitment)} = `
    + `${money(t.total_commitment)} committed + ${money(t.pipeline_commitment)} uncommitted.`;
}
