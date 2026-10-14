/** WF-BASIS — the waterfall's capital base, which decides every number on the card.
 *
 *  `services/api/src/aec_api/distwaterfall.py` computes
 *
 *      lp_contrib = sum(r["contributed"] for r in lp) or lp_commit
 *
 *  and the pref accrues on that figure, the return-of-capital tier returns it, and both IRRs and
 *  both equity multiples are computed against it. The `or` is a silent fallback to the COMMITMENT.
 *  Measured on an $8m LP / $2m GP cap table at a $20m exit:
 *
 *      nothing contributed    LP $18,302,056   IRR 17.99%   GP $1,697,944
 *      fully contributed      LP $18,302,056   IRR 17.99%   GP $1,697,944   <- IDENTICAL
 *      half contributed       LP $17,151,028   IRR 33.78%   GP $2,848,972   <- +$1.15m promote
 *
 *  The card rendered the distributions, both IRRs, both multiples, the pref rate and the style, and
 *  **not the capital base** — so a deal nobody has funded and one fully funded were the same
 *  screen. *An IRR without the capital it is a return on is not a return, it is a ratio.*
 *
 *  **And the two sides fall back independently**, so a cap table where the LPs have funded and the
 *  GP has not produces one waterfall on two bases, with the GP's promote priced against money the
 *  GP has not put in.
 *
 *  THE PER-INVESTOR SPLIT IS A DECISION, NOT A DEFECT TO PATCH
 *  ----------------------------------------------------------
 *  `per_investor[].distribution` is allocated pro-rata to COMMITMENT while the waterfall may have
 *  run on CONTRIBUTED capital. Measured: LP Big ($8m committed, $1m funded) takes **$13,490,617**
 *  and LP Small ($2m committed, $2m funded) takes **$3,372,654** — the investor who funded twice as
 *  much receives a quarter as much. Which share a distribution follows is an operating-agreement
 *  term, so the allocation is not changed here; both shares are rendered, the disagreement is
 *  flagged, and the choice is filed as WF-SPLIT. *Show the working, withhold the verdict* —
 *  `proforma/authorityGate.ts`'s rule for this family of card.
 */
import type { WaterfallScenario } from "../api/finance";
import { usd } from "../ui/charts";

export type Tone = "" | "warn" | "crit";

export const TONE_CSS: Record<Tone, string> = {
  "": "",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${(v * 100).toFixed(1)}%`;

/** The capital base, per side, with the commitment beside it.
 *
 *  Returns `null` only when the server sends no basis — an older one, or the no-cap-table branch
 *  where `lp_basis` is `null` because no waterfall ran. The card then renders as it used to rather
 *  than claiming a base. */
export function basisLine(w: WaterfallScenario): { text: string; tone: Tone } | null {
  if (!w.lp_basis && !w.gp_basis) return null;
  const side = (label: string, basis: string | null | undefined,
                contrib: number | undefined, commit: number | undefined) =>
    `${label} ${usd(contrib ?? null)} ${basis === "committed" ? "COMMITTED (not yet called)"
      : "contributed"}`
    + (basis === "contributed" && commit != null && contrib != null && commit > contrib
       ? ` of ${usd(commit)} committed` : "");
  const uncalled = w.lp_basis === "committed" || w.gp_basis === "committed";
  const mixed = w.lp_basis !== w.gp_basis;
  return {
    // A committed basis is the serious one: the pref and both returns are priced on money nobody
    // has put in. A mixed basis is serious for the same reason on one side only.
    tone: uncalled ? "crit" : "",
    text: `Basis: ${side("LP", w.lp_basis, w.lp_contrib, w.lp_commitment)}`
      + ` · ${side("GP", w.gp_basis, w.gp_contrib, w.gp_commitment)}`
      + (mixed ? " — the two sides are on DIFFERENT bases" : ""),
  };
}

/** The sentence that says what a committed basis means for every figure above it. */
export function uncalledNote(w: WaterfallScenario): string | null {
  const sides = [
    w.lp_basis === "committed" ? "LP" : null,
    w.gp_basis === "committed" ? "GP" : null,
  ].filter(Boolean) as string[];
  if (sides.length === 0) return null;
  return `${sides.join(" and ")} capital has not been called, so the waterfall priced `
    + `${sides.length === 2 ? "both sides" : `the ${sides[0]}`} on the COMMITMENT. The preferred `
    + `return, the return of capital, both IRRs and both multiples above are therefore returns on `
    + `money nobody has contributed yet — a deal with nothing called produces the same figures as `
    + `one fully funded.`;
}

/** The split-basis disagreement, with the two shares for each investor it affects. */
export function splitNote(w: WaterfallScenario): string | null {
  const mm = w.split_mismatch ?? [];
  if (mm.length === 0) return null;
  const named = mm.map((m) =>
    `${m.investor} (${pct(m.commitment_share)} of commitments vs `
    + `${pct(m.contributed_share)} of capital in)`).join(" · ");
  return `The per-investor split below is pro-rata to ${w.split_basis ?? "commitment"}, and the `
    + `waterfall ran on contributed capital. ${mm.length} investor(s) differ: ${named}. Each `
    + `figure below therefore rests on the share the waterfall did not use — confirm against the `
    + `operating agreement before distributing.`;
}

/** One row per investor, with both shares so the figure can be checked against either. */
export function investorRows(w: WaterfallScenario): {
  investor: string; distribution: string; commitment: string; contributed: string;
  shares: string; tone: Tone;
}[] {
  const mismatched = new Set((w.split_mismatch ?? []).map((m) => m.investor));
  return w.per_investor.map((p) => ({
    investor: p.investor,
    distribution: usd(p.distribution),
    commitment: usd(p.commitment),
    contributed: usd(p.contributed),
    shares: `${pct(p.commitment_share)} committed / ${pct(p.contributed_share)} funded`,
    tone: mismatched.has(p.investor) ? "warn" : "",
  }));
}

/** The headline, unchanged in substance and now carrying the base it rests on. */
export function returnsLine(w: WaterfallScenario): string {
  return `LP ${usd(w.lp_distributions)} (IRR ${pct(w.lp_irr)}, ${w.lp_equity_multiple}x)`
    + ` · GP ${usd(w.gp_distributions)} (${w.gp_equity_multiple}x)`
    + ` · pref ${pct(w.pref_rate)} ${w.style}`;
}
