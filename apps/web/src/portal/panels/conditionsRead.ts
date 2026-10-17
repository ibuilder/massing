/** COND-REFUSED — the readings the "Conditions of approval" card makes about a DENIED approval.
 *
 *  `services/api/src/aec_api/approval_conditions.py` is careful about a refused entitlement and
 *  writes down exactly why:
 *
 *  > this entitlement was DENIED. Its conditions are listed because they are what the agency would
 *  > have required, and an appeal puts them back in play — but they are not open obligations, so
 *  > they count zero. **Nobody owes the terms of a permission that was refused.**
 *
 *  It implements that by zeroing the row's counts — `open_count: 0`, `unparsed_count: 0`,
 *  `discharged_count: 0` — so the row *"cannot read '3 open' while contributing 0 to the total"*,
 *  and it publishes `refused` (the rows, with their condition counts) and `live_count` beside the
 *  totals so the response reconciles: `live_count + refused.length === entitlement_count`.
 *
 *  **THE CARD READ NEITHER.** Both keys sat in `apps/web/src/api/responseUndeclared.test.ts`'s gap
 *  list, `status` was never branched on, and the per-entitlement loop printed
 *  `` `${e.ref} — ${e.open_count} open` ``. So a refused approval carrying five conditions rendered
 *  as **`ENT-003 — 0 open`** — which is the most reassuring row the card can produce, for a
 *  permission the agency *refused*. *The zeroing was right and the consumer read it as compliance.*
 *
 *  The asymmetry is what makes it measurable rather than arguable: the card directly beneath it on
 *  the same panel, reading the same register through `entitlementConditionChecks`, already prints
 *  *"N refused (listed, not scored)"*. **Two cards, one register, one of them honouring the
 *  refusal** — and the declared type's own doc comment on `status` enumerated three of its four
 *  values (`tracked` · `no_conditions` · `unrecorded`), with `refused` missing, which is why
 *  nothing branched on it.
 */
import type { EntitlementConditions } from "../../api/types";

/** The fourth `status` value, the one the declared comment left out. */
export const STATUS_REFUSED = "refused";

export type Tone = "" | "warn" | "crit";

/** Tone to a LITERAL custom property, never `` `var(--status-${tone})` ``.
 *
 *  `apps/web/src/shell/cssVars.test.ts` refuses a built token name and refused this file's first
 *  draft, reporting the stem `--status-`: it walks every `var()` and resolves it against what the
 *  stylesheets define, and a name assembled at runtime is one it cannot resolve — so a typo'd tone
 *  would set a property nothing defines, which CSS ignores in silence. *A colour that silently does
 *  not apply is indistinguishable from a row nobody thought needed one.* */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** The headline, over the LIVE set and with its denominator.
 *
 *  `total_open` and `total_unparsed` are sums over rows whose refused members contribute zero, so
 *  they are totals over `live_count` entitlements and not over `entitlement_count`. Printing them
 *  with no denominator is the subset-verdict shape this session kept finding: the figure is right
 *  and the population it covers is invisible. */
export function headline(ec: EntitlementConditions): string {
  const open = ec.total_open ?? 0;
  const unparsed = ec.total_unparsed ?? 0;
  const live = ec.live_count;
  const total = ec.entitlement_count;
  const scope = live != null && total != null && total !== live
    ? ` across ${live} of ${total} entitlement(s)`
    : live != null ? ` across ${live} entitlement(s)` : "";
  return `${open} open · ${unparsed} unparsed${scope}`
    + (ec.unrecorded.length
       ? ` · ${ec.unrecorded.length} approved with no conditions recorded` : "");
}

/** The refusal block: who was refused, with how many conditions, and why they count zero.
 *
 *  Returns `null` when nothing was refused — a card that always carries a refusal paragraph teaches
 *  its reader to skip it, which is how COMPTIER-DARK's always-on qualifier was defeated. */
export function refusedNote(ec: EntitlementConditions): string | null {
  const ref = ec.refused ?? [];
  if (ref.length === 0) return null;
  const named = ref.map((r) =>
    `${r.ref}${r.condition_count ? ` (${r.condition_count} condition(s))` : ""}`).join(" · ");
  return `${ref.length} refused, listed and counting zero: ${named}. Those conditions are what the `
    + `agency would have required; an appeal puts them back in play. Nobody owes the terms of a `
    + `permission that was refused — so they are NOT part of the open total above.`;
}

/** Does the response's own arithmetic reconcile?
 *
 *  `approval_conditions.for_project` states the identity in a comment —
 *  `live_count + len(refused) == entitlement_count` — and a card that renders a denominator is
 *  making a claim about it. Returns `null` when a key needed to check it is absent (an older
 *  server), because an unanswerable question is not a failed one. */
export function reconciles(ec: EntitlementConditions): boolean | null {
  if (ec.live_count == null || ec.entitlement_count == null || ec.refused == null) return null;
  return ec.live_count + ec.refused.length === ec.entitlement_count;
}

/** One row per entitlement, with its status carried rather than flattened into a count.
 *
 *  The old loop skipped `!e.conditions.length` and printed `open_count`. Two consequences, and the
 *  first is the defect: a **refused** row has conditions and zeroed counts, so it printed as
 *  `0 open`; and an `unrecorded` row has no conditions, so it was skipped here and visible only in
 *  the separate `unrecorded` line — which is right, and is why that line exists.
 *
 *  `tone` is deliberately NOT "good" for a refused row. A denial is not a satisfied obligation. */
export function entitlementRows(ec: EntitlementConditions): {
  ref: string; text: string; tone: Tone;
}[] {
  const rows: { ref: string; text: string; tone: Tone }[] = [];
  for (const e of ec.entitlements) {
    const ref = e.ref ?? e.entitlement_id;
    if (e.status === STATUS_REFUSED) {
      // Listed even though it contributes nothing, because the conditions ARE on file and an
      // appeal revives them. Never as a count of zero on its own.
      rows.push({
        ref,
        text: `${ref} — REFUSED (${e.workflow_state ?? "denied"})`
          + (e.conditions.length
             ? `, ${e.conditions.length} condition(s) on file, counting zero` : ""),
        tone: "crit",
      });
      continue;
    }
    if (!e.conditions.length) continue;
    const parts = [`${e.open_count} open`];
    if (e.unparsed_count) parts.push(`${e.unparsed_count} unparsed`);
    if (e.discharged_count) parts.push(`${e.discharged_count} discharged`);
    rows.push({
      ref,
      text: `${ref} — ${parts.join(", ")}`
        + (e.fully_discharged ? " · fully discharged" : ""),
      // Unparsed outranks open: a condition nobody could read has not been assessed at all.
      tone: e.unparsed_count ? "warn" : "",
    });
  }
  return rows;
}
