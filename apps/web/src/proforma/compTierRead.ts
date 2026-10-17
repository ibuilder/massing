/** COMPTIER-DARK — the reading half of the tier-aware comps band.
 *
 *  `services/api/src/aec_api/comp_tier.py` opens with the case for itself: *"a comp is not a fact
 *  until you know where it came from."* It ranks sources into an explicit ladder, resolves comps
 *  describing the same address by tier instead of averaging them, and makes every derived band
 *  report **the weakest tier it rests on** — *"a median resting on one asking price is not the same
 *  number as a median resting on six recorded sales, and the output says so."*
 *
 *  `ApiClient.tieredComps()` was written for it and **no screen ever called it**, so none of that
 *  reached anybody. It sat in `apps/web/src/api/clientCallers.test.ts`'s uncalled-method freeze, and
 *  two of its keys sat in `apps/web/src/api/responseUndeclared.test.ts`'s gap list.
 *
 *  THE FUNCTIONS HERE ARE PURE, AND THAT IS THE POINT
 *  --------------------------------------------------
 *  Everything a reader could get wrong is a function with a sibling test rather than a branch inside
 *  an `insertAdjacentHTML` string. Four of this session's defects were a correct engine behind a
 *  consumer that dropped the qualifier, and a qualifier rendered inside a template literal is one no
 *  test can reach without a DOM.
 *
 *  WHY THERE IS NO AUTHORITY GATE ON THIS CARD, decided rather than omitted
 *  -----------------------------------------------------------------------
 *  `proforma/authorityGate.ts` governs the cards whose conclusion rests on a deal-room FACT, and
 *  says why `residual_land` is deliberately absent: *"a block nobody can act on teaches the reader
 *  to dismiss the ones they can."* The same reasoning lands the same way here. This route reads the
 *  project's own `comparable` register — records the user typed — and consumes no governed document.
 *  `appraisal` is the tempting dependency and it is the wrong one: an appraisal is a document whose
 *  freshness the table tracks, and these comps are not drawn from it.
 */
import type { TieredCompBand, TieredComps } from "../api/creDeal";
import { rate } from "../ui/charts";

export type Tone = "good" | "warn" | "crit";

export const TONE_CSS: Record<Tone, string> = {
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** The three fields the engine builds a band for, with how each is spelled.
 *
 *  Keyed to `statistics`, which the engine builds by comprehension over exactly this tuple. The
 *  formatters are per-FIELD rather than one money helper, because `cap_rate` is stored as a percent
 *  (`module.json` labels it "Cap rate %", so `6.2` means 6.2%) and rendering it through a currency
 *  formatter would print `$6` for a cap rate — the mistake `ui/charts.ts` documents in the other
 *  direction, where a stormwater volume was formatted by a helper called `usd`. */
export const FIELDS: readonly { key: string; label: string; fmt: (n: number) => string }[] = [
  // `rate` from `ui/charts`, not a local formatter — and not `usd` either. `usd` rounds to whole
  // dollars, which is right for a total and wrong for the number that produces one: a $/SF of
  // `4.25` would print as `$4`. `rate` is the helper written for exactly that (*"a rate is not an
  // amount"*) and it puts the minus OUTSIDE the currency mark, which a hand-rolled
  // `` `$${n.toLocaleString()}` `` does not — the first draft of this line was that template, and
  // `ui/charts.test.ts` exists because eighteen copies of it once disagreed about negatives.
  { key: "price_psf", label: "$/SF", fmt: rate },
  // Local, and deliberately so: `cap_rate` is stored as a PERCENT (`module.json` labels the field
  // "Cap rate %", so `6.2` means 6.2%). Putting it through a currency helper would print `$6` for
  // a cap rate — the mistake `ui/charts.ts` records in the other direction, where a stormwater
  // volume was formatted by a helper called `usd`. No currency mark, so the ban does not apply.
  { key: "cap_rate", label: "Cap rate", fmt: (n) => `${n.toFixed(2)}%` },
  { key: "rent_psf", label: "Rent $/SF/yr", fmt: rate },
];

export const fieldSpec = (key: string) =>
  FIELDS.find((f) => f.key === key) ?? { key, label: key, fmt: (n: number) => String(n) };

/** The tier at or below which a band is resting on a marketing number rather than on evidence.
 *
 *  A tier KEY, because which tiers are "weak" is a product judgement; its RANK is read from the
 *  response's own `ladder` rather than restated, so renaming or reordering the ladder cannot leave
 *  this file quietly comparing against a stale integer. */
export const WEAK_FROM_TIER = "listing";

/** `rank` at or above which the card calls a band's weakest source weak.
 *
 *  Fails to the WARNING side when the ladder does not name `WEAK_FROM_TIER` — a tier key this file
 *  cannot find is a ladder it no longer understands, and the safe reading of a source hierarchy it
 *  cannot interpret is "do not rely on this band yet". The opposite default would silently bless
 *  every band on the day somebody renamed a tier. */
export function weakFrom(ladder: TieredComps["ladder"]): number {
  const hit = ladder.find((l) => l.tier === WEAK_FROM_TIER);
  return hit ? hit.rank : 0;
}

/** The headline for one band: how much of the comp set it actually rests on, and how good that is.
 *
 *  **`n` alone is not the coverage**, and publishing only `n` is what made this a subset verdict:
 *  `VERDICT-COVERAGE`'s whole finding this session was engines that return a figure beside a count
 *  of what they could not evaluate, read by screens that render the figure. Three of five comps
 *  carrying a `$/SF` is a market with two blank cells in it, not a thinner market. */
export function bandHeadline(b: TieredCompBand, ladder: TieredComps["ladder"]):
    { text: string; tone: Tone } {
  const label = fieldSpec(b.field).label;
  if (b.n === 0) {
    return {
      tone: "crit",
      text: `<strong>No band.</strong> ${b.reason ? b.reason.replace(/^no /, "No ")
        : `no comp carries a ${label}`} — ${b.of_comps} comp(s) are on file and `
        + `${b.without_value.count} of them have this field blank. That is a gap in the register, `
        + `not a market with no evidence in it.`,
    };
  }
  const missing = b.without_value.count;
  const unattributed = b.unattributed ?? 0;
  const weak = (b.worst_rank ?? 0) >= weakFrom(ladder);
  const tone: Tone = missing > 0 || unattributed > 0 || weak ? "warn" : "good";
  return {
    tone,
    text: `<strong>${b.n} of ${b.of_comps} comp(s)</strong> carry a ${label}`
      + (missing > 0 ? ` — ${missing} left blank` : "")
      + (b.worst_tier_label ? ` · weakest contributing source: <strong>`
         + `${b.worst_tier_label}</strong>` : ""),
  };
}

/** The band itself — p25 / median / p75 and the range, in the field's own units.
 *
 *  Returns `null` when there is no band, so the caller cannot render a row of em-dashes that reads
 *  like a market whose numbers all happen to be missing. */
export function bandRow(b: TieredCompBand): { label: string; cells: [string, string][] } | null {
  if (b.n === 0 || b.median == null) return null;
  const { label, fmt } = fieldSpec(b.field);
  const cells: [string, string][] = [
    ["p25", b.p25 == null ? "—" : fmt(b.p25)],
    ["median", fmt(b.median)],
    ["p75", b.p75 == null ? "—" : fmt(b.p75)],
    ["range", b.min == null || b.max == null ? "—" : `${fmt(b.min)} – ${fmt(b.max)}`],
  ];
  return { label, cells };
}

/** The tier mix behind one band, in the engine's own ladder order.
 *
 *  `tier_counts` is a dict, so rendering it needs an order and the only non-arbitrary one is the
 *  hierarchy itself. It comes from the response's `ladder` rather than from a copy here. Tiers with
 *  no comps are dropped, not rendered as zeros: a ladder of seven rows mostly reading 0 buries the
 *  two that carry the band. */
export function tierMix(b: TieredCompBand, ladder: TieredComps["ladder"]):
    { tier: string; label: string; count: number; weak: boolean }[] {
  const counts = b.tier_counts ?? {};
  const floor = weakFrom(ladder);
  return ladder
    .filter((l) => (counts[l.tier] ?? 0) > 0)
    .map((l) => ({ tier: l.tier, label: l.label, count: counts[l.tier]!, weak: l.rank >= floor }));
}

/** What the band left out, named. The engine caps the NAMES and never the count, so a truncated
 *  list has to say so — `CLASH-TRUNC` is this session's instance of a consumer handed a page and
 *  told it was a total. */
export function blankNote(b: TieredCompBand): string | null {
  const w = b.without_value;
  if (!w || w.count === 0) return null;
  const named = w.comps.map((c) => c.address || "(unnamed)").join(" · ");
  return `${w.count} comp(s) carry no ${fieldSpec(b.field).label}: ${named}`
    + (w.truncated ? ` … and more (the count is exact; the list is capped)` : "")
    + `. They are in the register and out of this band.`;
}

/** The unattributed warning — only when the band actually rests on one.
 *
 *  Separate from the headline because it is a different fact from the weakest tier: a band can rest
 *  on a `Broker package` (weak, but attributed) with no unattributed comps at all. */
export function unattributedNote(b: TieredCompBand): string | null {
  const u = b.unattributed ?? 0;
  if (u === 0) return null;
  return `${u} of the ${b.n} comp(s) in this band carry no attribution the source ladder could `
    + `place. An unattributed number does not outrank an honest asking price — that is the engine's `
    + `rule, and it means this band is carried partly by figures nobody can trace.`;
}

/** The tie-break count, scoped to the field, with the set-wide figure beside it.
 *
 *  These two were ONE number until COMPTIER-DARK: `conflicts_resolved` published the whole
 *  register's count while sitting among keys that are all properties of the band, so a one-comp
 *  rent band reported a tie-break about `$/SF` at a different address. Rendering them together is
 *  deliberate — the correction is only legible next to the figure it corrects. */
export function conflictNote(b: TieredCompBand): string | null {
  const here = b.conflicts_resolved ?? 0;
  const set = b.conflicts_in_set ?? 0;
  if (set === 0) return null;
  if (here === 0) {
    return `${set} address conflict(s) were resolved by tier in this register, none of them about `
      + `${fieldSpec(b.field).label} — so no number in this band is the survivor of a tie-break.`;
  }
  return `${here} of ${set} address conflict(s) resolved by tier moved a ${fieldSpec(b.field).label}`
    + ` value. The overruled figures are listed below, never averaged in.`;
}

/** One row per resolved conflict: what was kept, what it outranked, and by how much. */
export function conflictRows(r: TieredComps): {
  address: string; kept: string; outranked: string; deltas: string[];
}[] {
  return r.conflicts.map((c) => ({
    address: c.address || "(unnamed)",
    kept: c.kept_tier,
    outranked: c.outranked.map((o) => `${o.tier}${o.source ? ` (${o.source})` : ""}`).join(" · "),
    deltas: c.value_deltas.map((d) => {
      const { label, fmt } = fieldSpec(d.field);
      return `${label}: kept ${fmt(d.kept)} over ${fmt(d.outranked)} (${d.outranked_tier})`;
    }),
  }));
}

/** The appraiser's exclusions, which the engine names on purpose.
 *
 *  `comp_tier.from_project`: *"NAMED, not silently dropped: a sample that shrank without saying so
 *  reads as a thinner market rather than as a decision somebody made."* The key was undeclared on
 *  the client, so the decision was unreadable by construction. */
export function excludedNote(r: TieredComps): string | null {
  const ex = r.excluded_comparables ?? [];
  if (ex.length === 0) return null;
  const refs = ex.map((e) => e.ref || e.id || "?").join(" · ");
  return `${ex.length} comp(s) excluded by the appraiser and kept out of every band above: ${refs}. `
    + `Reinstate one from the Comparables register if that was not deliberate — the sample is `
    + `${r.comp_count} comp(s) because somebody decided so, not because the market is thin.`;
}

/** Whether the set says anything at all. An empty register and a register whose every comp was
 *  excluded are different problems and must not render the same. */
export function setState(r: TieredComps): { empty: boolean; text: string } | null {
  if (r.comp_count > 0) return null;
  const ex = (r.excluded_comparables ?? []).length;
  return ex > 0
    ? { empty: false,
        text: `Every comp on file is excluded (${ex}). There is nothing to band — not because the `
            + `market is empty, but because the register's contents were all ruled out.` }
    : { empty: true,
        text: `No comparables on file. Add them in the Comparables register and set each one's `
            + `Source — the source is what decides a tie, and an unset source is the weakest tier.` };
}
