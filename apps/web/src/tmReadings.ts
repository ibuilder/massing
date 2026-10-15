/** TM-UNBILLED — $90k of unsigned drafts and $90k of GC-accepted T&M were the same sentence.
 *
 *  `services/api/src/aec_api/tm.py` returns `unbilled_total = grand_total - billed_total`, and
 *  `billed_total` counts only `workflow_state == "billed"`. The `eticket` workflow is
 *  `draft -> super_signed -> gc_signed -> billed`, so "unbilled" spans three different liabilities.
 *  Measured on the engine:
 *
 *  | fixture | grand_total | unbilled_total | by_status |
 *  |---|---|---|---|
 *  | all `draft` | 90,000 | **90,000** | `{draft: 90000}` |
 *  | all `gc_signed` | 90,000 | **90,000** | `{gc_signed: 90000}` |
 *
 *  and `reportCenter.ts` rendered both as `2 tickets · … · total $90,000 · unbilled $90,000`. The
 *  mixed case shows the breakdown existing and being discarded:
 *  `{draft: 25000, super_signed: 15000, gc_signed: 40000}` collapsed to `unbilled $80,000`.
 *
 *  **NOT the CO-REJECTED shape, and that is worth saying because it is the first thing to suspect.**
 *  `eticket` declares no refusal state, so there is no money-nobody-owes inside this figure — the
 *  total is sound and the defect is the flattening of ACCEPTANCE.
 *
 *  ### Which states mean "the GC accepted this" is the SERVER's answer, not this module's
 *
 *  The first draft of this file hardcoded `gc_signed`/`super_signed`/`draft`. That is a contract
 *  term written out on a client, and since WORKFLOW-DARK a project may REPLACE the `eticket`
 *  transitions — at which point the labels are a guess. `tm.accepted_states` now derives the set
 *  from the workflow the project actually runs (a state counts when every transition reaching it is
 *  performable by the GC alone) and `tm_summary` states it as `accepted_states`, with
 *  `workflow_overridden` saying whether those transitions are the shipped ones. Both are facts this
 *  side cannot derive, which is the whole reason they are on the wire — the same argument
 *  `occupancy_basis` makes on the rent roll.
 *
 *  The derivation's claim to being the right rule is that it reproduces the pair `cost.summary` had
 *  hardcoded independently, `("gc_signed", "billed")`; `services/api/test_eticket_tm.py` asserts
 *  that equality rather than leaving it as a docstring.
 *
 *  What stays here is the two labels BELOW acceptance — sub-signed and unsigned — because nothing on
 *  the wire distinguishes them. They are shipped-workflow names, so `labelsShipped` reports when
 *  they are not this project's, instead of being quietly wrong.
 */
import type { ApiClient } from "./api/client";
import { usd } from "./ui/charts";

export type TmSummary = Awaited<ReturnType<ApiClient["tmSummary"]>>;

/** The state `billed_total` counts, and the one the split must exclude — `unbilled_total` is
 *  everything else. The engine's own `tm.BILLED`. */
export const BILLED = "billed";
/** Shipped-workflow names for the two rungs below acceptance. Applied only as labels, never to
 *  decide what the GC accepted — `accepted_states` decides that. */
export const SUB_SIGNED = "super_signed";
export const UNSIGNED = "draft";

export interface UnbilledSplit {
  /** GC-accepted and not yet invoiced: owed. Membership is the server's `accepted_states`. */
  accepted: number;
  /** The sub has signed; the GC has not accepted. Shipped-workflow label. */
  subSigned: number;
  /** Nobody has signed. Not a claim. Shipped-workflow label. */
  unsigned: number;
  /** Unbilled money in a state none of the above places — reported, never folded in. */
  other: number;
  /** Whether the four above account for `unbilled_total`. False means a state arrived that this
   *  screen cannot place, which is a fact about the response, not about the money. */
  reconciles: boolean;
  /** Whether the server stated which states count as GC-accepted. When false, NOTHING is claimed
   *  as accepted — "the server did not say" is not "nothing is accepted". */
  acceptanceKnown: boolean;
  /** Whether `subSigned`/`unsigned` are labels from the workflow this project actually runs. */
  labelsShipped: boolean;
}

const n = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/**
 * `unbilled_total`, split by the states that compose it.
 *
 * `other` exists so a state this screen cannot place cannot be silently absorbed into one of the
 * three named buckets — the shape `by_status` would otherwise hide. `reconciles` is the check that
 * the split is still a partition of the figure it claims to explain; it is asserted, not assumed.
 */
export function unbilledSplit(s: TmSummary): UnbilledSplit {
  const by = s.by_status || {};
  const stated = s.accepted_states;
  const acceptanceKnown = Array.isArray(stated);
  // `accepted_states` includes `billed` — it is accepted AND invoiced. The split explains the
  // UNBILLED figure, so the billed state is excluded from every bucket below.
  const acceptedSet = new Set((acceptanceKnown ? stated : []).filter((x) => x !== BILLED));
  const labelsShipped = !s.workflow_overridden;
  let accepted = 0, subSigned = 0, unsigned = 0, other = 0;
  for (const [state, raw] of Object.entries(by)) {
    if (state === BILLED) continue;
    const v = n(raw);
    if (acceptedSet.has(state)) accepted += v;
    else if (state === SUB_SIGNED) subSigned += v;
    else if (state === UNSIGNED) unsigned += v;
    else other += v;
  }
  // Rounded to the cent: the engine rounds each bucket independently, so an exact comparison would
  // fail on a half-cent that is not a discrepancy.
  const sum = accepted + subSigned + unsigned + other;
  const reconciles = Math.abs(sum - n(s.unbilled_total)) < 0.011;
  return { accepted, subSigned, unsigned, other, reconciles, acceptanceKnown, labelsShipped };
}

/**
 * The headline. `unbilled` is never printed alone.
 *
 * When every unbilled dollar is in ONE state the sentence names that state rather than listing a
 * split with two zeroes — which is the pair of cases the old card could not tell apart.
 */
export function unbilledLine(s: TmSummary): string {
  const sp = unbilledSplit(s);
  const total = n(s.unbilled_total);
  if (total <= 0) return `unbilled ${usd(0)} — every ticket is billed`;
  const parts: string[] = [];
  if (sp.accepted) parts.push(`${usd(sp.accepted)} GC-accepted`);
  if (sp.subSigned) parts.push(`${usd(sp.subSigned)} sub-signed, not GC-accepted`);
  if (sp.unsigned) parts.push(`${usd(sp.unsigned)} unsigned`);
  if (sp.other) parts.push(`${usd(sp.other)} in other states`);
  if (!parts.length) return `unbilled ${usd(total)} — the engine reported no per-state breakdown`;
  const only = parts.length === 1;
  return `unbilled ${usd(total)} (${only ? "all " : ""}${parts.join(" · ")})`;
}

/**
 * The caveat, or null when the split accounts for the figure and every label is this project's.
 *
 * Ordered worst-first: an unreconciled split invalidates the others, and not knowing the acceptance
 * set at all makes the GC-accepted bucket's absence meaningless rather than reassuring.
 */
export function unbilledCaveat(s: TmSummary): string | null {
  const sp = unbilledSplit(s);
  if (!sp.reconciles) {
    return "The per-state amounts do not sum to the unbilled total, so a workflow state has "
      + "arrived that this screen cannot place. Treat the split as incomplete, not the total.";
  }
  if (!sp.acceptanceKnown) {
    return "The server did not state which workflow states count as GC-accepted, so none of this "
      + "is shown as accepted — that is a gap in the response, not a finding about the money.";
  }
  const notes: string[] = [];
  if (sp.other) {
    notes.push(`${usd(sp.other)} sits in a workflow state this screen does not recognise and is `
      + "shown separately rather than counted as accepted or unsigned.");
  }
  if (!sp.labelsShipped && (sp.subSigned || sp.unsigned)) {
    notes.push("This project has replaced the T&M workflow, so “sub-signed” and "
      + "“unsigned” are the shipped workflow’s names; the GC-accepted figure is "
      + "resolved against the workflow in force.");
  }
  return notes.length ? notes.join(" ") : null;
}

/** True when any unbilled money is NOT yet GC-accepted — the case a bare total hid. */
export function hasUnacceptedClaims(s: TmSummary): boolean {
  const sp = unbilledSplit(s);
  return sp.subSigned > 0 || sp.unsigned > 0 || sp.other > 0;
}
